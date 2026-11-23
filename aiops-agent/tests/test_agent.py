import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.llm_analyzer import LLMAnalyzer
from app.models import SeverityEnum, CauseCategoryEnum, RemediationActionEnum
from tests.test_payloads import PAYLOAD_CRASHLOOP, PAYLOAD_OOMKILLED, PAYLOAD_5XX_SPIKE

client = TestClient(app)


def test_healthz():
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_webhook_receiver_queues_alerts():
    response = client.post("/webhook/alertmanager", json=PAYLOAD_CRASHLOOP)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "accepted"
    assert data["alerts_queued"] == 1


def test_webhook_ignores_resolved():
    payload = dict(PAYLOAD_CRASHLOOP)
    payload["status"] = "resolved"
    response = client.post("/webhook/alertmanager", json=payload)
    assert response.status_code == 200
    assert response.json()["status"] == "ignored"


@pytest.mark.asyncio
async def test_llm_analyzer_diagnoses_oom():
    analyzer = LLMAnalyzer()
    analyzer.provider = "heuristic"

    pod_context = {"container_statuses": [{"terminated_reason": "OOMKilled", "exit_code": 137}]}
    events = ["Killing container backend: memory limit exceeded (OOMKilled)"]
    logs = "Fatal Error: Memory limit exceeded. Kernel killed process."
    git_info = {"revision": "feat-mem-c891", "sync_status": "Synced"}

    result = await analyzer.analyze(
        alert_name="PodOOMKilled",
        resource_name="backend-service-abc-123",
        namespace="app",
        alert_details={"alertname": "PodOOMKilled"},
        pod_context=pod_context,
        events=events,
        logs=logs,
        git_info=git_info
    )

    assert result.severity == SeverityEnum.CRITICAL
    assert result.category == CauseCategoryEnum.OOM_MEMORY_LEAK
    assert result.recommended_action == RemediationActionEnum.SCALE_UP
    assert "values.yaml" in result.exact_fix_instructions


@pytest.mark.asyncio
async def test_llm_analyzer_diagnoses_bad_release_for_rollback():
    analyzer = LLMAnalyzer()
    analyzer.provider = "heuristic"

    pod_context = {"container_statuses": [{"terminated_reason": "Error", "exit_code": 1}]}
    events = ["Back-off restarting failed container"]
    logs = "Traceback (most recent call last):\n  File 'main.py', line 89\nSyntaxError: invalid syntax"
    git_info = {"revision": "bad-commit-67e4", "sync_status": "Synced"}

    result = await analyzer.analyze(
        alert_name="ServiceHigh5xxRate",
        resource_name="backend-service-bad-456",
        namespace="app",
        alert_details={"alertname": "ServiceHigh5xxRate"},
        pod_context=pod_context,
        events=events,
        logs=logs,
        git_info=git_info
    )

    assert result.severity == SeverityEnum.CRITICAL
    assert result.category == CauseCategoryEnum.CODE_EXCEPTION
    assert result.recommended_action == RemediationActionEnum.APPROVE_ROLLBACK


def test_rollback_endpoint():
    response = client.post(
        "/actions/rollback",
        json={
            "application_name": "microservices-app",
            "namespace": "app",
            "reason": "AI Bot identified code exception on latest commit."
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["action"] == "ROLLBACK_EXECUTED"
