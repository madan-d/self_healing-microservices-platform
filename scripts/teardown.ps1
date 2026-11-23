# Cost-Safe Teardown Script (PowerShell)
param (
    [switch]$Cloud,
    [switch]$Local
)

if ($Cloud) {
    Write-Host "⚠️ DEPLOYING CLOUD TEARDOWN: Running Terraform Destroy..." -ForegroundColor Red
    Set-Location terraform/environments/dev
    terraform destroy -auto-approve
    Set-Location ../../..
    Write-Host "✅ AWS EKS, VPC, and ECR resources destroyed cleanly." -ForegroundColor Green
} else {
    Write-Host "🧹 Deleting local Kind cluster 'aiops-cluster'..." -ForegroundColor Yellow
    kind delete cluster --name aiops-cluster
    Write-Host "✅ Local cluster cleaned up." -ForegroundColor Green
}
