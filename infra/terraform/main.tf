# AWS Bedrock RAG demo — data plane + identity (Terraform port of
# infra/cloudformation.yaml). Creates the KMS key, the SSE-KMS S3 bucket
# (block public access + enforce encryption/TLS), the KMS-encrypted CloudWatch
# log group, and the least-privilege IAM role + instance profile.
#
# NOT created here (deliberately, same as the CloudFormation template):
#   - The Qdrant API key SSM SecureString. Terraform *can* manage it, but that
#     would place the secret in Terraform state. Keep it a one-time CLI step:
#       aws ssm put-parameter --name /rag-demo/qdrant-api-key \
#         --value <key> --type SecureString
#     The IAM role below already grants ssm:GetParameter on /rag-demo/*.
#   - The S3 Gateway Endpoint (VPC-specific) — see infra/setup_notes.md.
#   - Bedrock model access — a one-time manual Console step.

data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}
data "aws_region" "current" {}

locals {
  partition  = data.aws_partition.current.partition
  account_id = data.aws_caller_identity.current.account_id
  region     = data.aws_region.current.name
}

# --- KMS ---------------------------------------------------------------------

data "aws_iam_policy_document" "kms" {
  # The three skips below fire on the EnableRootAccountAdmin statement. This is
  # the AWS-recommended default KMS *key policy* root statement: in a resource
  # policy, Resource "*" means "this key", and account-root already has full
  # access. CKV_AWS_109/111/356 target identity policies; they false-positive on
  # a key policy. Removing the statement can make the key unmanageable.
  #checkov:skip=CKV_AWS_109: Resource-policy root statement (this key only), not an identity policy.
  #checkov:skip=CKV_AWS_111: Resource-policy root statement (this key only), not an identity policy.
  #checkov:skip=CKV_AWS_356: KMS key policies are scoped to the key; "*" means this key.
  statement {
    sid       = "EnableRootAccountAdmin"
    effect    = "Allow"
    actions   = ["kms:*"]
    resources = ["*"]
    principals {
      type        = "AWS"
      identifiers = ["arn:${local.partition}:iam::${local.account_id}:root"]
    }
  }

  statement {
    sid    = "AllowCloudWatchLogsEncryption"
    effect = "Allow"
    actions = [
      "kms:Encrypt",
      "kms:Decrypt",
      "kms:ReEncrypt*",
      "kms:GenerateDataKey*",
      "kms:DescribeKey",
    ]
    resources = ["*"]
    principals {
      type        = "Service"
      identifiers = ["logs.${local.region}.amazonaws.com"]
    }
    condition {
      test     = "ArnEquals"
      variable = "kms:EncryptionContext:aws:logs:arn"
      values   = ["arn:${local.partition}:logs:${local.region}:${local.account_id}:log-group:${var.log_group_name}"]
    }
  }
}

resource "aws_kms_key" "rag" {
  description             = "Customer-managed key for S3 objects + SSM SecureString (rag-demo)"
  enable_key_rotation     = true
  deletion_window_in_days = 7
  policy                  = data.aws_iam_policy_document.kms.json
}

resource "aws_kms_alias" "rag" {
  name          = "alias/rag-demo"
  target_key_id = aws_kms_key.rag.key_id
}

# --- S3 ----------------------------------------------------------------------

resource "aws_s3_bucket" "docs" {
  #checkov:skip=CKV_AWS_18: Single-bucket portfolio demo; access logging needs a
  #  second log-target bucket (which itself can't be logged). Out of demo scope.
  #checkov:skip=CKV_AWS_144: Cross-region replication is unnecessary for a demo
  #  corpus that is re-ingestible from source at any time.
  #checkov:skip=CKV2_AWS_61: Lifecycle configuration unneeded for a small, static
  #  demo corpus.
  #checkov:skip=CKV2_AWS_62: Event notifications unneeded; ingestion is a manual,
  #  one-time offline step.
  bucket = var.bucket_name
}

resource "aws_s3_bucket_versioning" "docs" {
  bucket = aws_s3_bucket.docs.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "docs" {
  bucket                  = aws_s3_bucket.docs.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "docs" {
  bucket = aws_s3_bucket.docs.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.rag.arn
    }
    bucket_key_enabled = true
  }
}

data "aws_iam_policy_document" "bucket" {
  statement {
    sid       = "DenyUnencryptedObjectUploads"
    effect    = "Deny"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.docs.arn}/*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "StringNotEquals"
      variable = "s3:x-amz-server-side-encryption"
      values   = ["aws:kms"]
    }
  }

  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.docs.arn, "${aws_s3_bucket.docs.arn}/*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "docs" {
  bucket = aws_s3_bucket.docs.id
  policy = data.aws_iam_policy_document.bucket.json
}

# --- CloudWatch Logs ---------------------------------------------------------

resource "aws_cloudwatch_log_group" "app" {
  #checkov:skip=CKV_AWS_338: 30-day retention is a deliberate cost choice for a
  #  demo; the audit line is short-lived evidence, not long-term compliance data.
  name              = var.log_group_name
  retention_in_days = 30
  kms_key_id        = aws_kms_key.rag.arn
}

# --- IAM ---------------------------------------------------------------------

data "aws_iam_policy_document" "assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "permissions" {
  statement {
    sid     = "BedrockInvokeSpecificModels"
    effect  = "Allow"
    actions = ["bedrock:InvokeModel"]
    resources = [
      "arn:${local.partition}:bedrock:${local.region}::foundation-model/anthropic.claude-3-haiku-20240307-v1:0",
      "arn:${local.partition}:bedrock:${local.region}::foundation-model/amazon.titan-embed-text-v2:0",
    ]
  }

  statement {
    sid       = "S3ReadDemoDocsOnly"
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:ListBucket"]
    resources = [aws_s3_bucket.docs.arn, "${aws_s3_bucket.docs.arn}/*"]
  }

  statement {
    sid       = "KmsDecryptForEncryptedData"
    effect    = "Allow"
    actions   = ["kms:Decrypt", "kms:DescribeKey"]
    resources = [aws_kms_key.rag.arn]
  }

  statement {
    sid       = "SsmGetQdrantApiKey"
    effect    = "Allow"
    actions   = ["ssm:GetParameter"]
    resources = ["arn:${local.partition}:ssm:${local.region}:${local.account_id}:parameter/rag-demo/*"]
  }

  statement {
    sid       = "CloudWatchAppLogs"
    effect    = "Allow"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["arn:${local.partition}:logs:${local.region}:${local.account_id}:log-group:/rag-demo/*"]
  }
}

resource "aws_iam_role" "bedrock_rag" {
  name               = "bedrock-rag-demo-role"
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

resource "aws_iam_role_policy" "bedrock_rag" {
  name   = "bedrock-rag-demo-policy"
  role   = aws_iam_role.bedrock_rag.id
  policy = data.aws_iam_policy_document.permissions.json
}

resource "aws_iam_instance_profile" "bedrock_rag" {
  name = "bedrock-rag-demo-role"
  role = aws_iam_role.bedrock_rag.name
}
