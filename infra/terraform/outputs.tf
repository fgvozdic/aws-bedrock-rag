output "bucket_name" {
  description = "Name of the S3 bucket holding the demo documents."
  value       = aws_s3_bucket.docs.bucket
}

output "kms_key_arn" {
  description = "ARN of the customer-managed KMS key."
  value       = aws_kms_key.rag.arn
}

output "role_arn" {
  description = "ARN of the IAM role the RAG app runs under."
  value       = aws_iam_role.bedrock_rag.arn
}

output "log_group_name" {
  description = "CloudWatch log group for the per-query audit line."
  value       = aws_cloudwatch_log_group.app.name
}
