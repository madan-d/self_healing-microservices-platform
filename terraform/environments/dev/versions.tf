terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.50"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
  }

  # Production remote state backend with state locking via DynamoDB
  # Uncomment and configure with your S3 bucket & DynamoDB table for production deployment:
  # backend "s3" {
  #   bucket         = "my-aiops-terraform-state"
  #   key            = "dev/terraform.tfstate"
  #   region         = "us-east-1"
  #   dynamodb_table = "terraform-locks"
  #   encrypt        = true
  # }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "AIOps-K8s-Platform"
      Environment = var.environment
      ManagedBy   = "Terraform"
    }
  }
}
