#!/usr/bin/env bash
if [ "$1" == "--cloud" ]; then
  echo "⚠️ Cloud Teardown: Destroying AWS Terraform Resources..."
  cd terraform/environments/dev
  terraform destroy -auto-approve
  echo "✅ AWS Infrastructure destroyed."
else
  echo "🧹 Deleting local Kind cluster..."
  kind delete cluster --name aiops-cluster
  echo "✅ Local Kind cluster removed."
fi
