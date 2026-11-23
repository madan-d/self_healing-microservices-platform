variable "cluster_name" {
  type        = string
  description = "Name of the EKS cluster"
}

variable "cluster_version" {
  type        = string
  description = "Kubernetes version"
  default     = "1.30"
}

variable "vpc_id" {
  type        = string
  description = "VPC ID where EKS will be deployed"
}

variable "subnet_ids" {
  type        = list(string)
  description = "Private Subnet IDs for EKS node groups and control plane"
}

variable "environment" {
  type        = string
  description = "Environment identifier"
  default     = "dev"
}

variable "node_instance_types" {
  type        = list(string)
  description = "EC2 instance types for the managed node group"
  default     = ["t3.medium", "t3a.medium"]
}

variable "desired_nodes" {
  type        = number
  description = "Desired number of worker nodes"
  default     = 2
}

variable "min_nodes" {
  type        = number
  description = "Minimum number of worker nodes"
  default     = 1
}

variable "max_nodes" {
  type        = number
  description = "Maximum number of worker nodes"
  default     = 4
}
