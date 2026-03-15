variable "name_prefix" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "subnet_ids" {
  type = list(string)
}

variable "security_group_id" {
  type = string
}

variable "task_role_arn" {
  description = "ARN of the ECS task role that needs access to OpenSearch"
  type        = string
}
