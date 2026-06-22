# Terraform — AWS Bedrock RAG demo

A 1:1 port of [`../cloudformation.yaml`](../cloudformation.yaml). Same resources,
same security posture: customer-managed KMS key (with the CloudWatch Logs grant),
SSE-KMS S3 bucket with public access blocked and TLS/encryption enforced via
bucket policy, a KMS-encrypted log group, and a least-privilege IAM role +
instance profile.

## Validate without an AWS account (nothing is provisioned)

```bash
terraform -chdir=infra/terraform init -backend=false
terraform -chdir=infra/terraform fmt -check
terraform -chdir=infra/terraform validate
tflint --chdir=infra/terraform
checkov -d infra/terraform
```

All five run with **no AWS credentials**. This is what CI runs on every push.

## Provision (requires AWS credentials)

```bash
terraform -chdir=infra/terraform init
terraform -chdir=infra/terraform apply
```

`terraform plan`/`apply` are the only commands that need credentials. The Qdrant
API key is deliberately **not** managed here — Terraform could create the SSM
SecureString, but that would put the secret in Terraform state. Set it once via
the CLI instead (see the root README), which the IAM role already allows reading.

## checkov skips

Eight checks are skipped with inline `#checkov:skip=` justifications: four S3
controls unneeded for a single static demo bucket (access logging, cross-region
replication, lifecycle, event notifications), the 30-day log retention (a
deliberate cost choice), and three identity-policy checks that false-positive on
the standard KMS key-policy root statement.
