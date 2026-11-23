variable "repository_names" {
  type        = list(string)
  description = "List of ECR repository names to create"
  default     = ["frontend", "backend", "aiops-agent"]
}

variable "environment" {
  type        = string
  description = "Environment identifier"
  default     = "dev"
}
