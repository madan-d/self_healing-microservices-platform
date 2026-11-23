variable "aws_region" {
  type        = string
  description = "AWS region for deployment"
  default     = "us-east-1"
}

variable "environment" {
  type        = string
  description = "Deployment environment"
  default     = "dev"
}

variable "cluster_name" {
  type        = string
  description = "Name of the EKS Cluster"
  default     = "aiops-dev-eks"
}
