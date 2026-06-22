# Manual setup / click-path fallback

Use this if you are not deploying `cloudformation.yaml`. Order matters — the two
prerequisites at the top are the most common live-demo killers.

## 0. Prerequisites (do these FIRST)

1. **Enable Bedrock model access** (Console → Bedrock → Model access). Enable
   BOTH in **us-east-1**:
   - `anthropic.claude-3-haiku-20240307-v1:0`
   - `amazon.titan-embed-text-v2:0`

   This is one-time, manual, and NOT created by CloudFormation/IAM. Skipping it
   gives `AccessDeniedException` on the first `InvokeModel` call.

2. **Set the $10/month Budget alarm** before provisioning anything:

   ```bash
   aws budgets create-budget \
     --account-id <ACCOUNT_ID> \
     --budget '{"BudgetName":"rag-demo-monthly-ceiling","BudgetLimit":{"Amount":"10","Unit":"USD"},"TimeUnit":"MONTHLY","BudgetType":"COST"}' \
     --notifications-with-subscribers '[{"Notification":{"NotificationType":"ACTUAL","ComparisonOperator":"GREATER_THAN","Threshold":80,"ThresholdType":"PERCENTAGE"},"Subscribers":[{"SubscriptionType":"EMAIL","Address":"you@example.com"}]}]'
   ```

## 1. KMS key

Create a customer-managed key (symmetric, encrypt/decrypt). Note its key id /
ARN — it goes into `iam-policy.json` (`<KMS_KEY_ID>`) and the S3 bucket default
encryption.

## 2. S3 bucket (`rag-demo-docs`)

- Block Public Access: **ON** (all four toggles).
- Default encryption: **SSE-KMS** with the key from step 1.
- Versioning: **ON**.
- Attach `s3-bucket-policy.json` (deny unencrypted `PutObject`, deny non-TLS).

## 3. SSM SecureString — Qdrant API key

Create a free 1 GB cluster at cloud.qdrant.io (no credit card), copy its API key:

```bash
aws ssm put-parameter \
  --name "/rag-demo/qdrant-api-key" \
  --value "<paste-qdrant-api-key>" \
  --type SecureString
```

Standard parameters are free. The IAM role reads it via `ssm:GetParameter`.

## 4. IAM role (`bedrock-rag-demo-role`)

- Trust policy: `iam-role.json` (EC2 service principal).
- Permission policy: `iam-policy.json` — replace `<ACCOUNT_ID>` and
  `<KMS_KEY_ID>`. **Attach it in full**, including the `SsmGetQdrantApiKey`
  statement (omitting it is the silent first-query `AccessDeniedException`).
- For EC2: create an instance profile with this role.

## 5. CloudWatch log group

```bash
aws logs create-log-group --log-group-name /rag-demo/app
```

The app creates the log *stream* (`queries`) at startup; the group must exist.

## 6. S3 Gateway Endpoint (free — replaces a NAT Gateway for the S3 path)

```bash
# VPC_ID + PRIVATE_RTB_ID for your environment first.
aws ec2 create-vpc-endpoint \
  --vpc-id "$VPC_ID" \
  --vpc-endpoint-type Gateway \
  --service-name com.amazonaws.us-east-1.s3 \
  --route-table-ids "$PRIVATE_RTB_ID"
```

- The S3 gateway endpoint is **free** and keeps S3 traffic on the AWS backbone.
- Bedrock is reached over the public HTTPS endpoint (TLS 1.2+, data stays in
  AWS). The production isolation upgrade is a **VPC Interface Endpoint** for
  `bedrock-runtime` (~$7.30/mo, single AZ) — not needed for the demo.
- **Do not create a NAT Gateway.** If you ever see one in this account, treat it
  as the budget-alarm trigger to investigate.
