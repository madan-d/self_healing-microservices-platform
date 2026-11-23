# Local Kubernetes Cluster Setup Script (PowerShell)
# Sets up a local Kind cluster with NGINX Ingress, Namespaces, App, and Observability

Write-Host "🚀 Starting Local CloudOps Platform Setup..." -ForegroundColor Cyan

# 1. Check Prerequisites
$tools = @("docker", "kind", "kubectl", "helm")
foreach ($tool in $tools) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        Write-Warning "Missing tool: $tool. Please install it or verify your PATH."
    }
}

# 2. Create Kind Cluster config
$kindConfig = @"
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
- role: control-plane
  kubeadmConfigPatches:
  - |
    kind: InitConfiguration
    nodeRegistration:
      kubeletExtraArgs:
        node-labels: "ingress-ready=true"
  extraPortMappings:
  - containerPort: 80
    hostPort: 80
    protocol: TCP
  - containerPort: 443
    hostPort: 443
    protocol: TCP
"@

$kindConfigFile = [System.IO.Path]::GetTempFileName()
Set-Content -Path $kindConfigFile -Value $kindConfig

Write-Host "📦 Creating Kind cluster 'aiops-cluster'..." -ForegroundColor Green
kind create cluster --name aiops-cluster --config $kindConfigFile
Remove-Item $kindConfigFile -ErrorAction SilentlyContinue

# 3. Install NGINX Ingress Controller
Write-Host "🌐 Installing NGINX Ingress Controller..." -ForegroundColor Green
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml
Write-Host "⏳ Waiting for Ingress Controller to become ready..." -ForegroundColor Yellow
kubectl wait --namespace ingress-nginx --for=condition=ready pod --selector=app.kubernetes.io/component=controller --timeout=90s

# 4. Create Namespaces
Write-Host "📁 Creating Namespaces (app, aiops, monitoring, argocd)..." -ForegroundColor Green
kubectl create namespace app --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace aiops --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace monitoring --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace argocd --dry-run=client -o yaml | kubectl apply -f -

# 5. Build and Load Docker Images into Kind
Write-Host "🔨 Building local application & AIOps images..." -ForegroundColor Green
docker build -t ghcr.io/devops-portfolio/backend:v1.0.0 ./app/backend
docker build -t ghcr.io/devops-portfolio/frontend:v1.0.0 ./app/frontend
docker build -t ghcr.io/devops-portfolio/aiops-agent:v1.0.0 ./aiops-agent

Write-Host "🚚 Sideloading images into Kind cluster nodes..." -ForegroundColor Green
kind load docker-image ghcr.io/devops-portfolio/backend:v1.0.0 --name aiops-cluster
kind load docker-image ghcr.io/devops-portfolio/frontend:v1.0.0 --name aiops-cluster
kind load docker-image ghcr.io/devops-portfolio/aiops-agent:v1.0.0 --name aiops-cluster

# 6. Deploy App via Helm
Write-Host "🚀 Deploying 3-tier microservices application via Helm..." -ForegroundColor Green
helm upgrade --install microservices ./k8s/helm-charts/microservices-app -n app

# 7. Deploy AIOps Agent
Write-Host "🤖 Deploying AIOps Incident Agent, RBAC & Ingress..." -ForegroundColor Green
kubectl apply -f ./aiops-agent/k8s/rbac.yaml
kubectl apply -f ./aiops-agent/k8s/deployment.yaml
kubectl apply -f ./aiops-agent/k8s/service.yaml
kubectl apply -f ./aiops-agent/k8s/ingress.yaml

Write-Host "`n✅ Local Platform Cluster Ready!" -ForegroundColor Cyan
Write-Host "Frontend App:    http://localhost"
Write-Host "AIOps Incidents: http://localhost/api/v1/incidents (or port-forward to 8000)"
Write-Host "To test triage:  Run .\scripts\simulate-crash.ps1"
