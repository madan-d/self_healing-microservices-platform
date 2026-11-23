#!/usr/bin/env bash
SCENARIO=${1:-crash}
# Detect if running via Ingress port 80 or port-forward 8000
if curl -s -f http://localhost/api/v1/incidents > /dev/null 2>&1; then
  BASE_URL="http://localhost"
else
  BASE_URL="http://localhost:8000"
fi
AGENT_URL="$BASE_URL/webhook/alertmanager"

echo "🧪 AIOps Incident Simulator: Triggering scenario '$SCENARIO'..."

if [ "$SCENARIO" == "crash" ]; then
  ALERT_NAME="PodCrashLoopBackOff"
  SUMMARY="Pod backend-service is in CrashLoopBackOff"
elif [ "$SCENARIO" == "oom" ]; then
  ALERT_NAME="PodOOMKilled"
  SUMMARY="Pod backend-service terminated due to OOMKilled"
else
  ALERT_NAME="ServiceHigh5xxRate"
  SUMMARY="Backend service experiencing > 5% 5xx errors"
fi

PAYLOAD=$(cat <<EOF
{
  "version": "4",
  "status": "firing",
  "receiver": "aiops-webhook",
  "alerts": [
    {
      "status": "firing",
      "labels": {
        "alertname": "$ALERT_NAME",
        "namespace": "app",
        "pod": "backend-service-local",
        "container": "backend",
        "severity": "critical"
      },
      "annotations": {
        "summary": "$SUMMARY"
      },
      "startsAt": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
    }
  ]
}
EOF
)

curl -X POST "$AGENT_URL" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD"

echo ""
echo "Sleeping 2s for LLM analysis..."
sleep 2

curl -s "$BASE_URL/api/v1/incidents" | jq '.[-1]'
