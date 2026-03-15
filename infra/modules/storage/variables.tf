variable "name_prefix" {
  type = string
}

variable "lake_lifecycle_ia_days" {
  description = "Days after which lake objects transition to S3 Infrequent Access"
  type        = number
  default     = 30
}

variable "lake_lifecycle_glacier_days" {
  description = "Days after which lake objects transition to Glacier"
  type        = number
  default     = 90
}
