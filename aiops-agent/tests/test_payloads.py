"""Sample Alertmanager payloads for unit & integration testing."""

PAYLOAD_CRASHLOOP = {
    "version": "4",
    "status": "firing",
    "receiver": "aiops-webhook",
    "alerts": [
        {
            "status": "firing",
            "labels": {
                "alertname": "PodCrashLoopBackOff",
                "namespace": "app",
                "pod": "backend-service-65b89df597-x8k2p",
                "container": "backend",
                "severity": "critical"
            },
            "annotations": {
                "summary": "Pod backend-service is in CrashLoopBackOff",
                "description": "Pod has restarted 5 times in the last 5 minutes."
            },
            "startsAt": "2026-11-23T14:30:00Z"
        }
    ]
}

PAYLOAD_OOMKILLED = {
    "version": "4",
    "status": "firing",
    "receiver": "aiops-webhook",
    "alerts": [
        {
            "status": "firing",
            "labels": {
                "alertname": "PodOOMKilled",
                "namespace": "app",
                "pod": "backend-service-65b89df597-lm91z",
                "container": "backend",
                "severity": "critical"
            },
            "annotations": {
                "summary": "Pod backend-service terminated with OOMKilled",
                "description": "Container exceeded 256Mi memory limit and was killed."
            },
            "startsAt": "2026-11-23T14:31:00Z"
        }
    ]
}

PAYLOAD_5XX_SPIKE = {
    "version": "4",
    "status": "firing",
    "receiver": "aiops-webhook",
    "alerts": [
        {
            "status": "firing",
            "labels": {
                "alertname": "ServiceHigh5xxRate",
                "namespace": "app",
                "pod": "backend-service-65b89df597-a4g89",
                "app": "backend-service",
                "severity": "critical"
            },
            "annotations": {
                "summary": "Service backend-service experiencing > 5% HTTP 5xx errors",
                "description": "Error rate surged following commit release."
            },
            "startsAt": "2026-11-23T14:32:00Z"
        }
    ]
}
