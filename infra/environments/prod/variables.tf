variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "container_image" {
  description = "ECR image URI for the datasearchpy app"
  type        = string
}

variable "db_name" {
  type    = string
  default = "datasearch"
}

variable "db_username" {
  type    = string
  default = "datasearch"
}
