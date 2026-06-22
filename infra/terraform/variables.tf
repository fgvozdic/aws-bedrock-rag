variable "region" {
  description = "AWS region. Bedrock model access must be enabled here (us-east-1 for the demo)."
  type        = string
  default     = "us-east-1"
}

variable "bucket_name" {
  description = "Name of the S3 bucket holding the demo source documents."
  type        = string
  default     = "rag-demo-docs"
}

variable "log_group_name" {
  description = "CloudWatch log group for the per-query audit line."
  type        = string
  default     = "/rag-demo/app"
}
