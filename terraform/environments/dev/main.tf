data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  azs = slice(data.aws_availability_zones.available.names, 0, 3)
}

# 1. Modular VPC Network
module "vpc" {
  source = "../../modules/vpc"

  environment        = var.environment
  cluster_name       = var.cluster_name
  availability_zones = local.azs
}

# 2. Managed EKS Cluster
module "eks" {
  source = "../../modules/eks"

  environment  = var.environment
  cluster_name = var.cluster_name
  vpc_id       = module.vpc.vpc_id
  subnet_ids   = module.vpc.private_subnet_ids

  node_instance_types = ["t3.medium", "t3a.medium"]
  desired_nodes       = 2
  min_nodes           = 1
  max_nodes           = 4
}

# 3. ECR Repositories for Microservices & AIOps Bot
module "ecr" {
  source = "../../modules/ecr"

  environment      = var.environment
  repository_names = ["frontend", "backend", "aiops-agent"]
}
