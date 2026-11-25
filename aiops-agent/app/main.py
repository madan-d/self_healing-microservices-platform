import uuid
import logging
from typing import List, Dict, Any
from fastapi import FastAPI, BackgroundTasks, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .models import (
    AlertmanagerPayload,
    RootCauseAnalysisResult,
    RollbackRequest
)
from .k8s_client import KubernetesContextClient
from .loki_client import LokiClient
from .gitops_client import GitOpsClient
from .llm_analyzer import LLMAnalyzer
from .notification import NotificationService
from .remediation import RemediationEngine

# Logging Setup
logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("aiops.agent")

# Initialize services
k8s_client = KubernetesContextClient()
loki_client = LokiClient()
gitops_client = GitOpsClient()
llm_analyzer = LLMAnalyzer()
notification_service = NotificationService()
remediation_engine = RemediationEngine(k8s_client)

app = FastAPI(
    title="AIOps Incident Triage & Self-Healing Agent",
    version="1.0.0",
    description="Automated triage bot for Alertmanager alerts with LLM root cause analysis and GitOps remediation."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory history of recent triaged incidents
incident_history: List[Dict[str, Any]] = []


@app.get("/healthz", tags=["Health"])
def health_check():
    return {"status": "healthy", "service": settings.APP_NAME}


@app.get("/api/v1/incidents", tags=["Incidents"])
def list_incidents():
    """Lists recent triaged incidents, LLM root-causes, and actions taken."""
    return {"count": len(incident_history), "incidents": incident_history[-20:]}


async def process_alert_item(alert, incident_id: str):
    alert_name = alert.labels.get("alertname", "UnknownAlert")
    namespace = alert.labels.get("namespace", "app")
    pod_name = alert.labels.get("pod") or alert.labels.get("instance", "backend-service")
    container_name = alert.labels.get("container", "backend")

    logger.info(f"🔍 [Triage Started] Incident {incident_id}: Alert={alert_name}, Pod={pod_name}, Namespace={namespace}")

    # 1. Gather Kubernetes Context
    pod_context = k8s_client.get_pod_context(namespace, pod_name)
    events = k8s_client.get_pod_events(namespace, pod_name)

    # 2. Gather Logs (Check Loki first, fallback to K8s API)
    logs = await loki_client.query_logs(namespace, pod_name)
    if not logs:
        logs = k8s_client.get_pod_logs(namespace, pod_name, container_name)

    # 3. Gather GitOps Context (ArgoCD sync & commit hash)
    git_info = await gitops_client.get_application_info("microservices-app")

    # 4. Perform AI Root-Cause Analysis
    rca: RootCauseAnalysisResult = await llm_analyzer.analyze(
        alert_name=alert_name,
        resource_name=pod_name,
        namespace=namespace,
        alert_details=alert.labels,
        pod_context=pod_context,
        events=events,
        logs=logs,
        git_info=git_info
    )

    # 5. Execute Auto-Remediation or prepare Human-in-the-Loop notification
    remediated, action_message = remediation_engine.evaluate_and_remediate(rca)

    # 6. Notify Engineers (Slack Block Kit / Discord)
    await notification_service.notify_rca(rca, auto_remediated=remediated)

    # Record in history
    incident_record = {
        "incident_id": incident_id,
        "timestamp": alert.startsAt,
        "alert_name": alert_name,
        "target_resource": pod_name,
        "namespace": namespace,
        "severity": rca.severity,
        "category": rca.category,
        "summary": rca.summary,
        "recommended_action": rca.recommended_action,
        "auto_remediated": remediated,
        "action_taken": action_message,
        "exact_fix": rca.exact_fix_instructions
    }
    incident_history.append(incident_record)
    logger.info(f"✅ [Triage Completed] Incident {incident_id} processed: Remediated={remediated}")


@app.post("/webhook/alertmanager", tags=["Webhook"])
async def alertmanager_webhook(payload: AlertmanagerPayload, background_tasks: BackgroundTasks):
    """
    Alertmanager Webhook Receiver:
    Fired by Alertmanager when anomalies (CrashLoopBackOff, OOMKilled, 5xx spike) are detected.
    """
    logger.info(f"Received Alertmanager webhook payload with {len(payload.alerts)} alert(s). Status={payload.status}")

    if payload.status != "firing":
        logger.info("Alert status is resolved or non-firing. No triage required.")
        return {"status": "ignored", "reason": "non-firing"}

    for alert in payload.alerts:
        incident_id = f"inc-{uuid.uuid4().hex[:8]}"
        background_tasks.add_task(process_alert_item, alert, incident_id)

    return {
        "status": "accepted",
        "alerts_queued": len(payload.alerts),
        "message": "AIOps context gathering and LLM triage running asynchronously."
    }


@app.post("/actions/rollback", tags=["Remediation"])
async def trigger_rollback(req: RollbackRequest):
    """
    Human-in-the-Loop Rollback Endpoint:
    Triggered when an engineer clicks 'Approve Rollback' in Slack or via the dashboard.
    """
    logger.warning(f"🚨 Human-in-the-Loop Rollback approved for {req.application_name} by operator. Reason: {req.reason}")
    success = await gitops_client.trigger_rollback(req.application_name, req.target_revision)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to trigger GitOps rollback in ArgoCD")

    return {
        "status": "success",
        "application": req.application_name,
        "action": "ROLLBACK_EXECUTED",
        "message": "ArgoCD synced application back to previous stable release."
    }


@app.get("/actions/rollback", response_class=HTMLResponse, tags=["Remediation"])
async def approve_rollback_ui(app: str = Query("microservices-app"), namespace: str = Query("app")):
    """
    Interactive Web confirmation page when clicking the 'Approve Rollback' button from Slack.
    """
    success = await gitops_client.trigger_rollback(app)
    status_text = "Rollback Triggered Successfully" if success else "Rollback Failed"

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
      <title>AIOps Rollback Confirmation</title>
      <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-slate-900 text-white min-h-screen flex items-center justify-center p-4">
      <div class="max-w-md w-full bg-slate-800 rounded-2xl p-8 border border-slate-700 shadow-2xl text-center">
        <div class="w-16 h-16 rounded-full mx-auto mb-4 flex items-center justify-center bg-emerald-500/20 text-emerald-400">
          <svg class="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
          </svg>
        </div>
        <h1 class="text-xl font-bold mb-2">{status_text}</h1>
        <p class="text-sm text-slate-300 mb-6">
          ArgoCD has been instructed to rollback deployment <strong>{app}</strong> in namespace <strong>{namespace}</strong> to the previous stable Git revision.
        </p>
        <div class="p-3 bg-slate-900 rounded-lg text-xs font-mono text-slate-400 mb-6">
          Status: Synced & Healthy<br>Target: Previous Commit
        </div>
        <a href="/" class="px-5 py-2.5 bg-sky-500 hover:bg-sky-600 text-white text-sm font-semibold rounded-lg transition inline-block">
          Return to Platform Dashboard
        </a>
      </div>
    </body>
    </html>
    """
