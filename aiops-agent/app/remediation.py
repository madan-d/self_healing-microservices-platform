import time
import logging
from typing import Tuple
from .models import RootCauseAnalysisResult, RemediationActionEnum, CauseCategoryEnum
from .k8s_client import KubernetesContextClient
from .config import settings

logger = logging.getLogger("aiops.remediation")


class RemediationEngine:
    def __init__(self, k8s_client: KubernetesContextClient):
        self.k8s_client = k8s_client
        # In-memory rate limiting: {resource_name: [timestamp1, timestamp2]}
        self.restart_history = {}

    def _check_rate_limit(self, resource_key: str) -> bool:
        """Ensures we do not restart a workload repeatedly in a tight loop."""
        now = time.time()
        one_hour_ago = now - 3600
        history = self.restart_history.get(resource_key, [])
        # Filter to events in last hour
        history = [ts for ts in history if ts > one_hour_ago]
        self.restart_history[resource_key] = history

        if len(history) >= settings.MAX_AUTO_RESTARTS_PER_HOUR:
            logger.warning(f"Rate limit exceeded for auto-restarting {resource_key} ({len(history)} restarts in past hour).")
            return False
        return True

    def evaluate_and_remediate(self, rca: RootCauseAnalysisResult) -> Tuple[bool, str]:
        """
        Executes safe auto-remediation for transient issues.
        Enforces human-in-the-loop for destructive actions (like rollback or scale-up).
        """
        if not settings.AUTO_REMEDIATION_ENABLED:
            return False, "Auto-remediation disabled by configuration."

        # Scenario 1: Safe Auto-Remediation for Transient Infra issues (e.g. hung worker or transient deadlock)
        if rca.recommended_action == RemediationActionEnum.AUTO_RESTART and rca.category == CauseCategoryEnum.TRANSIENT_INFRA:
            deployment_name = self._resolve_deployment_name(rca.target_resource)
            resource_key = f"{rca.namespace}/{deployment_name}"

            if not self._check_rate_limit(resource_key):
                return False, f"Auto-restart skipped: Exceeded max {settings.MAX_AUTO_RESTARTS_PER_HOUR} restarts per hour."

            success = self.k8s_client.restart_deployment(namespace=rca.namespace, deployment_name=deployment_name)
            if success:
                self.restart_history[resource_key].append(time.time())
                return True, f"Successfully executed safe rolling restart on deployment '{deployment_name}' in namespace '{rca.namespace}'."
            else:
                return False, f"Failed to patch deployment '{deployment_name}' for rollout restart."

        # Scenario 2: Code Exception / Bad Release -> Requires Human-in-the-Loop approval
        if rca.recommended_action == RemediationActionEnum.APPROVE_ROLLBACK:
            return False, "Code bug or release anomaly identified. Auto-remediation requires Human-in-the-Loop approval via Slack/ArgoCD."

        # Scenario 3: OOMKilled -> Requires resource limit edit
        if rca.recommended_action == RemediationActionEnum.SCALE_UP:
            return False, "OOM memory limit exceeded. Requires GitOps pull request or values.yaml limit increase."

        return False, "No automated action taken; routed for manual engineer investigation."

    def _resolve_deployment_name(self, resource_name: str) -> str:
        """Extracts deployment name from pod name (e.g. backend-service-7489b6447-cqkf7 -> backend-service)."""
        if "backend-service" in resource_name:
            return "backend-service"
        if "frontend-service" in resource_name:
            return "frontend-service"
        parts = resource_name.split("-")
        if len(parts) >= 3 and len(parts[-1]) <= 6:
            return "-".join(parts[:-2])
        return resource_name
