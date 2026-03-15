terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "s3" {
    # Fill in before first apply:
    # bucket         = "your-tfstate-bucket"
    # key            = "datasearchpy/prod/terraform.tfstate"
    # region         = "us-east-1"
    # dynamodb_table = "terraform-locks"
    # encrypt        = true
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "datasearchpy"
      Environment = "prod"
      ManagedBy   = "terraform"
    }
  }
}

module "datasearchpy" {
  source = "../../"

  aws_region      = var.aws_region
  environment     = "prod"
  project         = "datasearchpy"
  container_image = var.container_image
  db_name         = var.db_name
  db_username     = var.db_username

  service_desired_count = 2
  service_min_count     = 1
  service_max_count     = 6
  task_cpu              = 1024
  task_memory           = 2048
}
