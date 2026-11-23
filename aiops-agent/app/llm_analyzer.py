import json
import logging
from typing import Dict, Any, Optional
from .models import (
    RootCauseAnalysisResult,
    SeverityEnum,
    CauseCategoryEnum,
    RemediationActionEnum
)
from .config import settings

logger = logging.getLogger("aiops.llm")


SYSTEM_PROMPT = """You are an elite Site Reliability Engineer (SRE) and Kubernetes AIOps expert.
You investigate Kubernetes alerts by analyzing alert metadata, pod container exit codes, recent kubectl events, and pod logs.

Your task:
1. Identify the root cause category:
   - TRANSIENT_INFRA: Transient network timeout, brief resource contention, deadlocked worker thread.
   - CODE_EXCEPTION: Unhandled application exception, Python traceback, null pointer, syntax error.
   - CONFIG_ERROR: Invalid configuration, missing environment variable, database authentication failure.
   - OOM_MEMORY_LEAK: Container killed by Linux OOM killer (exit code 137).
   - DEPENDENCY_FAILURE: External upstream or persistent database unavailable.

2. Recommend the safe action:
   - AUTO_RESTART: Safe for transient deadlocks or transient socket timeouts.
   - APPROVE_ROLLBACK: Mandatory for code bugs, new bad deployments, syntax errors, or regression spikes.
   - SCALE_UP: For OOM or resource starvation under legitimate load.
   - MANUAL_INVESTIGATION: For unknown, ambiguous, or multi-service cascading failures.

3. Return ONLY a valid JSON object matching this exact schema:
{
  "alert_name": "<string>",
  "target_resource": "<string>",
  "namespace": "<string>",
  "severity": "CRITICAL" | "HIGH" | "MEDIUM" | "LOW",
  "category": "TRANSIENT_INFRA" | "CODE_EXCEPTION" | "CONFIG_ERROR" | "OOM_MEMORY_LEAK" | "DEPENDENCY_FAILURE",
  "summary": "<1-2 sentence high-level summary of the incident>",
  "detailed_root_cause": "<Detailed technical breakdown explaining why it happened>",
  "recommended_action": "AUTO_RESTART" | "APPROVE_ROLLBACK" | "SCALE_UP" | "MANUAL_INVESTIGATION",
  "exact_fix_instructions": "<Step-by-step resolution command or GitOps action>",
  "confidence_score": <float between 0.0 and 1.0>
}
"""


class LLMAnalyzer:
    def __init__(self):
        self.provider = settings.LLM_PROVIDER.lower()
        self._init_provider()

    def _init_provider(self):
        if self.provider == "auto":
            if settings.OPENAI_API_KEY:
                self.provider = "openai"
            else:
                # Default to heuristic/bedrock
                self.provider = "heuristic"
        logger.info(f"Initialized LLM Analyzer with provider: {self.provider}")

    async def analyze(
        self,
        alert_name: str,
        resource_name: str,
        namespace: str,
        alert_details: Dict[str, Any],
        pod_context: Dict[str, Any],
        events: list,
        logs: str,
        git_info: Dict[str, Any]
    ) -> RootCauseAnalysisResult:
        """Executes LLM Root Cause Analysis with fallbacks."""
        user_prompt = f"""
--- INCIDENT REPORT FOR INVESTIGATION ---
Alert Name: {alert_name}
Target Resource: {resource_name}
Namespace: {namespace}
Alert Labels & Annotations: {json.dumps(alert_details, indent=2)}

--- KUBERNETES POD RUNTIME CONTEXT ---
Pod Status: {json.dumps(pod_context, indent=2)}

--- KUBERNETES POD EVENTS (kubectl describe events) ---
{chr(10).join(events[:8])}

--- RECENT POD LOGS ---
{logs[-2500:] if logs else "No logs captured."}

--- GITOPS / ARGO CD CONTEXT ---
Git Revision: {git_info.get('revision')}
Sync Status: {git_info.get('sync_status')}
"""

        if self.provider == "openai" and settings.OPENAI_API_KEY:
            try:
                import openai
                client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
                response = await client.chat.completions.create(
                    model=settings.OPENAI_MODEL,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.1
                )
                raw_json = response.choices[0].message.content
                data = json.loads(raw_json)
                return self._parse_to_model(data, alert_name, resource_name, namespace, logs, events, git_info)
            except Exception as exc:
                logger.error(f"OpenAI analysis failed: {exc}. Falling back to heuristic engine.")

        elif self.provider == "bedrock":
            try:
                import boto3
                bedrock = boto3.client("bedrock-runtime", region_name=settings.AWS_REGION)
                body = json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 1024,
                    "system": SYSTEM_PROMPT,
                    "messages": [{"role": "user", "content": user_prompt}],
                    "temperature": 0.1
                })
                res = bedrock.invoke_model(modelId=settings.BEDROCK_MODEL_ID, body=body)
                resp_body = json.loads(res["body"].read().decode("utf-8"))
                text_content = resp_body["content"][0]["text"]
                # Extract JSON
                start = text_content.find("{")
                end = text_content.rfind("}") + 1
                data = json.loads(text_content[start:end])
                return self._parse_to_model(data, alert_name, resource_name, namespace, logs, events, git_info)
            except Exception as exc:
                logger.error(f"AWS Bedrock analysis failed: {exc}. Falling back to heuristic engine.")

        # High-precision deterministic heuristic fallback engine
        return self._heuristic_analysis(alert_name, resource_name, namespace, pod_context, events, logs, git_info)

    def _heuristic_analysis(
        self,
        alert_name: str,
        resource_name: str,
        namespace: str,
        pod_context: Dict[str, Any],
        events: list,
        logs: str,
        git_info: Dict[str, Any]
    ) -> RootCauseAnalysisResult:
        """Deterministic SRE heuristics for local offline verification."""
        lower_logs = logs.lower()
        events_str = " ".join(events).lower()

        # Check for OOM
        is_oom = "oomkilled" in lower_logs or "oomkilled" in events_str or "137" in str(pod_context) or "memory limit exceeded" in lower_logs
        if is_oom or "podoomkilled" in alert_name.lower():
            return RootCauseAnalysisResult(
                alert_name=alert_name,
                target_resource=resource_name,
                namespace=namespace,
                severity=SeverityEnum.CRITICAL,
                category=CauseCategoryEnum.OOM_MEMORY_LEAK,
                summary=f"Pod {resource_name} terminated with OOMKilled (Exit Code 137).",
                detailed_root_cause="The container memory consumption crossed its configured cgroup limit. The Linux kernel OOM-killer killed the process.",
                recommended_action=RemediationActionEnum.SCALE_UP,
                exact_fix_instructions="Increase memory limits in k8s/helm-charts/microservices-app/values.yaml under backend.resources.limits.memory (e.g., from 256Mi to 512Mi).",
                confidence_score=0.96,
                evidence_logs=logs[-400:],
                evidence_events="; ".join(events[:3]),
                git_commit_info=git_info.get("revision")
            )

        # Check for Code Crash / Bad Deployment / 5xx errors
        is_bad_release = (
            "traceback" in lower_logs or
            "syntaxerror" in lower_logs or
            "fatal exception" in lower_logs or
            "crash signal dispatched" in lower_logs or
            "servicehigh5xxrate" in alert_name.lower() or
            "500 internal server error" in lower_logs
        )
        if is_bad_release:
            return RootCauseAnalysisResult(
                alert_name=alert_name,
                target_resource=resource_name,
                namespace=namespace,
                severity=SeverityEnum.CRITICAL,
                category=CauseCategoryEnum.CODE_EXCEPTION,
                summary=f"Code crash or 5xx spike detected in {resource_name} following recent release.",
                detailed_root_cause=f"Application encountered an unhandled exception or critical fault resulting in crash/failure rate surge. Associated with Git revision {git_info.get('revision')}.",
                recommended_action=RemediationActionEnum.APPROVE_ROLLBACK,
                exact_fix_instructions="Trigger immediate GitOps rollback via ArgoCD to the previous stable release commit, and fix the exception in app/backend/main.py.",
                confidence_score=0.94,
                evidence_logs=logs[-400:],
                evidence_events="; ".join(events[:3]),
                git_commit_info=git_info.get("revision")
            )

        # Check for Database Connection / Config error
        is_db_down = "database unreachable" in lower_logs or "connection refused" in lower_logs or "psycopg2.operationalerror" in lower_logs
        if is_db_down:
            return RootCauseAnalysisResult(
                alert_name=alert_name,
                target_resource=resource_name,
                namespace=namespace,
                severity=SeverityEnum.HIGH,
                category=CauseCategoryEnum.DEPENDENCY_FAILURE,
                summary=f"Upstream PostgreSQL database connection refused for {resource_name}.",
                detailed_root_cause="Backend API cannot reach postgres-service:5432. The database pod may be rebooting or credentials/networking misconfigured.",
                recommended_action=RemediationActionEnum.MANUAL_INVESTIGATION,
                exact_fix_instructions="Check PostgreSQL pod status with `kubectl get pods -l app=postgres-service -n app` and verify service endpoints.",
                confidence_score=0.91,
                evidence_logs=logs[-400:],
                evidence_events="; ".join(events[:3]),
                git_commit_info=git_info.get("revision")
            )

        # Default transient CrashLoopBackOff: Auto-restart deployment
        return RootCauseAnalysisResult(
            alert_name=alert_name,
            target_resource=resource_name,
            namespace=namespace,
            severity=SeverityEnum.HIGH,
            category=CauseCategoryEnum.TRANSIENT_INFRA,
            summary=f"Transient failure or pod restart loop observed on {resource_name}.",
            detailed_root_cause="Pod encountered a transient worker deadlock or temporary health check timeout.",
            recommended_action=RemediationActionEnum.AUTO_RESTART,
            exact_fix_instructions="Execute safe rolling restart on deployment backend-service via Kubernetes API.",
            confidence_score=0.88,
            evidence_logs=logs[-300:] if logs else "No fatal stack traces found in logs.",
            evidence_events="; ".join(events[:3]),
            git_commit_info=git_info.get("revision")
        )

    def _parse_to_model(
        self,
        data: Dict[str, Any],
        alert_name: str,
        resource_name: str,
        namespace: str,
        logs: str,
        events: list,
        git_info: Dict[str, Any]
    ) -> RootCauseAnalysisResult:
        return RootCauseAnalysisResult(
            alert_name=data.get("alert_name", alert_name),
            target_resource=data.get("target_resource", resource_name),
            namespace=data.get("namespace", namespace),
            severity=SeverityEnum(data.get("severity", "HIGH")),
            category=CauseCategoryEnum(data.get("category", "TRANSIENT_INFRA")),
            summary=data.get("summary", "Root cause analyzed by LLM."),
            detailed_root_cause=data.get("detailed_root_cause", ""),
            recommended_action=RemediationActionEnum(data.get("recommended_action", "MANUAL_INVESTIGATION")),
            exact_fix_instructions=data.get("exact_fix_instructions", ""),
            confidence_score=float(data.get("confidence_score", 0.90)),
            evidence_logs=logs[-400:],
            evidence_events="; ".join(events[:3]),
            git_commit_info=git_info.get("revision")
        )
