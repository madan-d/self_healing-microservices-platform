#!/usr/bin/env bash
set -e

echo "🚀 Starting Local CloudOps Platform Setup (Kind)..."

# 1. Verify Prerequisites
for tool in docker kind kubectl helm; do
  if ! command -v $tool &> /dev/null; then
    echo "⚠️ Warning: $tool is not installed. Please install it."
  fi
done

# 2. Spin up Kind Cluster with Ingress Port Mappings
cat <<EOF | kind create cluster --name aiops-cluster --config=-
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
EOF

# 3. Setup NGINX Ingress
echo "🌐 Installing NGINX Ingress Controller..."
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml
kubectl wait --namespace ingress-nginx --for=condition=ready pod --selector=app.kubernetes.io/component=controller --timeout=90s

# 4. Create Namespaces
kubectl create namespace app --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace aiops --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace monitoring --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace argocd --dry-run=client -o yaml | kubectl apply -f -

# 5. Build and Load Local Images
echo "🔨 Building Docker images..."
docker build -t ghcr.io/devops-portfolio/backend:v1.0.0 ./app/backend
docker build -t ghcr.io/devops-portfolio/frontend:v1.0.0 ./app/frontend
docker build -t ghcr.io/devops-portfolio/aiops-agent:v1.0.0 ./aiops-agent

echo "🚚 Sideloading images into Kind..."
kind load docker-image ghcr.io/devops-portfolio/backend:v1.0.0 --name aiops-cluster
kind load docker-image ghcr.io/devops-portfolio/frontend:v1.0.0 --name aiops-cluster
kind load docker-image ghcr.io/devops-portfolio/aiops-agent:v1.0.0 --name aiops-cluster

# 6. Deploy Microservices & AIOps Agent
helm upgrade --install microservices ./k8s/helm-charts/microservices-app -n app
kubectl apply -f ./aiops-agent/k8s/rbac.yaml
kubectl apply -f ./aiops-agent/k8s/deployment.yaml
kubectl apply -f ./aiops-agent/k8s/service.yaml

echo "✅ Local Environment Initialized!"
echo "Access App at: http://localhost"
