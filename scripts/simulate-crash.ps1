# Fault Simulator & AIOps Triage Demonstrator (PowerShell)
param (
    [ValidateSet("crash", "oom", "5xx")]
    [string]$Scenario = "crash"
)

Write-Host "🧪 AIOps Incident Simulator: Triggering scenario '$Scenario'..." -ForegroundColor Cyan

# Automatically detect whether agent is reached via Ingress (127.0.0.1) or port-forward (127.0.0.1:8000)
$baseUrl = "http://127.0.0.1"
try {
    $null = Invoke-RestMethod -Uri "http://127.0.0.1/api/v1/incidents" -TimeoutSec 2 -ErrorAction Stop
    $baseUrl = "http://127.0.0.1"
} catch {
    try {
        $null = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/incidents" -TimeoutSec 2 -ErrorAction Stop
        $baseUrl = "http://127.0.0.1:8000"
    } catch {
        $baseUrl = "http://localhost:8000"
    }
}

$agentUrl = "$baseUrl/webhook/alertmanager"

switch ($Scenario) {
    "crash" {
        Write-Host "💥 Dispatching PodCrashLoopBackOff Alertmanager payload..." -ForegroundColor Red
        $payload = @{
            version = "4"
            status = "firing"
            receiver = "aiops-webhook"
            alerts = @(
                @{
                    status = "firing"
                    labels = @{
                        alertname = "PodCrashLoopBackOff"
                        namespace = "app"
                        pod = "backend-service-local"
                        container = "backend"
                        severity = "critical"
                    }
                    annotations = @{
                        summary = "Pod backend-service-local is in CrashLoopBackOff"
                        description = "Simulated fatal process crash. Exit code 1."
                    }
                    startsAt = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
                }
            )
        } | ConvertTo-Json -Depth 5
    }

    "oom" {
        Write-Host "🚨 Dispatching PodOOMKilled Alertmanager payload..." -ForegroundColor Yellow
        $payload = @{
            version = "4"
            status = "firing"
            receiver = "aiops-webhook"
            alerts = @(
                @{
                    status = "firing"
                    labels = @{
                        alertname = "PodOOMKilled"
                        namespace = "app"
                        pod = "backend-service-local"
                        container = "backend"
                        severity = "critical"
                    }
                    annotations = @{
                        summary = "Pod backend-service-local terminated due to OOMKilled"
                        description = "Container exceeded memory limits."
                    }
                    startsAt = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
                }
            )
        } | ConvertTo-Json -Depth 5
    }

    "5xx" {
        Write-Host "📉 Dispatching ServiceHigh5xxRate Alertmanager payload..." -ForegroundColor Magenta
        $payload = @{
            version = "4"
            status = "firing"
            receiver = "aiops-webhook"
            alerts = @(
                @{
                    status = "firing"
                    labels = @{
                        alertname = "ServiceHigh5xxRate"
                        namespace = "app"
                        pod = "backend-service-local"
                        app = "backend-service"
                        severity = "critical"
                    }
                    annotations = @{
                        summary = "Backend service 5xx error rate exceeded 5%"
                        description = "Surge in HTTP 500 errors after deployment."
                    }
                    startsAt = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
                }
            )
        } | ConvertTo-Json -Depth 5
    }
}

try {
    $res = Invoke-RestMethod -Uri $agentUrl -Method Post -Body $payload -ContentType "application/json"
    Write-Host "✅ Alert dispatched to AIOps Agent successfully!" -ForegroundColor Green
    Write-Host ($res | ConvertTo-Json)

    Write-Host "`nWaiting 2 seconds for LLM triage completion..." -ForegroundColor Yellow
    Start-Sleep -Seconds 2

    $incidents = Invoke-RestMethod -Uri "$baseUrl/api/v1/incidents"
    Write-Host "`n📋 Recent Triaged Incident from AIOps Agent:" -ForegroundColor Cyan
    Write-Host ($incidents.incidents[-1] | ConvertTo-Json -Depth 5)
} catch {
    Write-Error "Could not connect to AIOps Agent at $agentUrl. Is it running? (In Kind, access http://localhost/api/v1/incidents or run 'kubectl port-forward svc/aiops-agent 8000:8000 -n aiops')"
}
