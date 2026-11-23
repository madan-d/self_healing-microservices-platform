import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from kubernetes import client, config

logger = logging.getLogger("aiops.k8s")


class KubernetesContextClient:
    def __init__(self):
        self._init_client()

    def _init_client(self):
        try:
            config.load_incluster_config()
            logger.info("Loaded in-cluster Kubernetes configuration.")
        except Exception:
            try:
                config.load_kube_config()
                logger.info("Loaded local kubeconfig file.")
            except Exception as exc:
                logger.warning(f"Could not load Kubernetes configuration: {exc}. Using mock/fallback.")
                self.core_v1 = None
                self.apps_v1 = None
                return

        self.core_v1 = client.CoreV1Api()
        self.apps_v1 = client.AppsV1Api()

    def get_pod_context(self, namespace: str, pod_name: str) -> Dict[str, Any]:
        """Gathers pod status, restart counts, termination reasons, and exit codes."""
        if not self.core_v1:
            return {"status": "unreachable", "pod_name": pod_name, "namespace": namespace}

        try:
            pod = self.core_v1.read_namespaced_pod(name=pod_name, namespace=namespace)
            container_statuses = []
            if pod.status.container_statuses:
                for cs in pod.status.container_statuses:
                    last_state = cs.last_state
                    terminated = last_state.terminated if last_state else None
                    waiting = cs.state.waiting if cs.state else None
                    container_statuses.append({
                        "name": cs.name,
                        "restart_count": cs.restart_count,
                        "ready": cs.ready,
                        "waiting_reason": waiting.reason if waiting else None,
                        "waiting_message": waiting.message if waiting else None,
                        "terminated_reason": terminated.reason if terminated else None,
                        "exit_code": terminated.exit_code if terminated else None,
                    })

            return {
                "pod_name": pod.metadata.name,
                "namespace": pod.metadata.namespace,
                "node_name": pod.spec.node_name,
                "phase": pod.status.phase,
                "labels": pod.metadata.labels or {},
                "container_statuses": container_statuses,
            }
        except Exception as exc:
            logger.error(f"Error fetching pod {pod_name} in {namespace}: {exc}")
            return {"error": str(exc), "pod_name": pod_name, "namespace": namespace}

    def get_pod_events(self, namespace: str, pod_name: str) -> List[str]:
        """Gathers recent Kubernetes events related to the pod (e.g. BackOff, Unhealthy, FailedScheduling)."""
        if not self.core_v1:
            return ["Kubernetes client offline; simulated event: Back-off restarting failed container"]

        try:
            events = self.core_v1.list_namespaced_event(
                namespace=namespace,
                field_selector=f"involvedObject.name={pod_name}"
            )
            event_messages = []
            for ev in events.items[-10:]:  # Keep last 10 events
                event_messages.append(f"[{ev.type}] Reason={ev.reason}: {ev.message}")
            return event_messages or ["No recent events recorded for this pod."]
        except Exception as exc:
            logger.error(f"Error fetching events for {pod_name}: {exc}")
            return [f"Failed to fetch events: {exc}"]

    def get_pod_logs(self, namespace: str, pod_name: str, container_name: Optional[str] = None, tail_lines: int = 80) -> str:
        """Fetches recent pod logs, inspecting both current and previous (crashed) container runs."""
        if not self.core_v1:
            return "Simulated Pod Log:\n[CRITICAL] Fatal exception: Memory limit exceeded or unhandled crash."

        logs_collected = []
        try:
            # First attempt reading previous container logs (in case it restarted)
            try:
                prev_logs = self.core_v1.read_namespaced_pod_log(
                    name=pod_name,
                    namespace=namespace,
                    container=container_name,
                    previous=True,
                    tail_lines=tail_lines
                )
                if prev_logs.strip():
                    logs_collected.append("--- PREVIOUS CONTAINER INSTANCE LOGS (BEFORE CRASH) ---")
                    logs_collected.append(prev_logs)
            except Exception:
                pass  # Container may not have a previous instance

            # Read current container logs
            current_logs = self.core_v1.read_namespaced_pod_log(
                name=pod_name,
                namespace=namespace,
                container=container_name,
                previous=False,
                tail_lines=tail_lines
            )
            if current_logs.strip():
                logs_collected.append("--- CURRENT CONTAINER INSTANCE LOGS ---")
                logs_collected.append(current_logs)

            return "\n".join(logs_collected) if logs_collected else "No log output recorded."
        except Exception as exc:
            logger.error(f"Error reading logs for {pod_name}: {exc}")
            return f"Logs unavailable: {exc}"

    def restart_deployment(self, namespace: str, deployment_name: str) -> bool:
        """Executes a rolling restart of the target deployment by updating its restart timestamp annotation."""
        if not self.apps_v1:
            logger.warning("Kubernetes apps_v1 client not initialized. Simulating rollout restart.")
            return True

        try:
            now_iso = datetime.utcnow().isoformat()
            patch_body = {
                "spec": {
                    "template": {
                        "metadata": {
                            "annotations": {
                                "kubectl.kubernetes.io/restartedAt": now_iso,
                                "aiops.remediation/reason": "Automated incident restart by AIOps agent"
                            }
                        }
                    }
                }
            }
            self.apps_v1.patch_namespaced_deployment(
                name=deployment_name,
                namespace=namespace,
                body=patch_body
            )
            logger.info(f"Successfully triggered rollout restart for deployment {deployment_name} in {namespace}")
            return True
        except Exception as exc:
            logger.error(f"Failed to restart deployment {deployment_name}: {exc}")
            return False
