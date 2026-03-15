variable "name_prefix" {
  type = string
}

variable "message_retention_seconds" {
  type    = number
  default = 1209600 # 14 days
}

variable "visibility_timeout_seconds" {
  type    = number
  default = 300
}

variable "max_receive_count" {
  description = "Number of times a message is received before moving to DLQ"
  type        = number
  default     = 3
}
