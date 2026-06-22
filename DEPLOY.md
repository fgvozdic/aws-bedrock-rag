# Deployment Manual — AWS Bedrock RAG

A complete, ordered walkthrough from a fresh AWS account to a running app. Follow
it top to bottom the first time. Each phase ends with a **✅ checkpoint** so you
can confirm it worked before moving on.

There are three paths at the end:
- **A. Local** — run on your laptop against real AWS (start here; best for the Loom demo).
- **B. EC2 quick-run** — HTTP, IP-locked, for a private 1:1 demo.
- **C. EC2 + ALB + ACM** — the real TLS deployment.

> **Region:** everything uses **us-east-1**. If you change it, change it
> *everywhere* (env, IAM ARNs, CloudFormation, Bedrock model access).

---

## Phase 0 — One-time prerequisites (DO THESE FIRST)

These two steps are the most common live-demo killers. Both fail at *first
question*, not at startup — the app looks fine until a client asks something.

### 0.1 Install tooling

| Tool | Check | Install |
|------|-------|---------|
| AWS CLI v2 | `aws --version` | https://aws.amazon.com/cli/ |
| Python 3.12+ | `python --version` | https://www.python.org/ |
| uv | `uv --version` | `pip install uv` |
| Git | `git --version` | https://git-scm.com/ |

### 0.2 Enable Bedrock model access (manual, NOT automatic)

1. AWS Console → **Bedrock** → **Model access** (left nav) → **Modify model access**.
2. Enable **both**:
   - `Anthropic — Claude 3 Haiku`
   - `Amazon — Titan Text Embeddings V2`
3. Submit. Access usually activates in minutes (can take longer for some
   accounts), so do this early.

> Skipping this gives `AccessDeniedException` on the first `InvokeModel` call.
> It is **not** granted by default and **not** created by CloudFormation.

**✅ Checkpoint:** both models show **Access granted** on the Model access page.

### 0.3 Set the $10/month Budget alarm (mandatory cost ceiling)

Replace the account id and email:

```bash
aws budgets create-budget \
  --account-id <ACCOUNT_ID> \
  --budget '{"BudgetName":"rag-demo-monthly-ceiling","BudgetLimit":{"Amount":"10","Unit":"USD"},"TimeUnit":"MONTHLY","BudgetType":"COST"}' \
  --notifications-with-subscribers '[{"Notification":{"NotificationType":"ACTUAL","ComparisonOperator":"GREATER_THAN","Threshold":80,"ThresholdType":"PERCENTAGE"},"Subscribers":[{"SubscriptionType":"EMAIL","Address":"you@example.com"}]},{"Notification":{"NotificationType":"ACTUAL","ComparisonOperator":"GREATER_THAN","Threshold":100,"ThresholdType":"PERCENTAGE"},"Subscribers":[{"SubscriptionType":"EMAIL","Address":"you@example.com"}]}]'
```

> Find your account id with `aws sts get-caller-identity --query Account --output text`.

**✅ Checkpoint:** the budget appears under Console → **Billing → Budgets**, and
you received a confirmation email to approve the SNS subscription.

---

## Phase 1 — Create the Qdrant Cloud cluster (vector store)

1. Sign up at https://cloud.qdrant.io (no credit card).
2. Create a **Free** cluster (1 GB). Pick the region closest to us-east-1.
3. When it's ready, copy two things:
   - The **cluster URL**, e.g. `https://<id>.<region>.aws.cloud.qdrant.io:6333`
   - An **API key** (Data Access → API Keys → Create).

Keep the URL for Phase 4 (`.env`) and the API key for Phase 3 (SSM).

**✅ Checkpoint:** cluster status is green; you have the URL and an API key.

---

## Phase 2 — Provision AWS infrastructure

This creates the KMS key, the SSE-KMS S3 bucket, the least-privilege IAM role +
instance profile, and the CloudWatch log group.

### Option A — CloudFormation (recommended)

```bash
cd aws-bedrock-rag

aws cloudformation deploy \
  --template-file infra/cloudformation.yaml \
  --stack-name rag-demo \
  --region us-east-1 \
  --capabilities CAPABILITY_NAMED_IAM
```

Read the outputs (bucket name, KMS key ARN, role ARN, log group):

```bash
aws cloudformation describe-stacks --stack-name rag-demo \
  --query "Stacks[0].Outputs" --output table
```

> Want a different bucket name? Add `--parameter-overrides BucketName=my-unique-bucket`
> and use that name everywhere below. S3 bucket names are globally unique, so if
> `rag-demo-docs` is taken you **must** override it.

### Option B — Manual click-path

Follow [infra/setup_notes.md](infra/setup_notes.md) steps 1–5 (KMS, S3 + bucket
policy, IAM role, log group). Use this if you can't run CloudFormation.

**✅ Checkpoint:**
```bash
aws s3 ls | grep rag-demo-docs                       # bucket exists
aws iam get-role --role-name bedrock-rag-demo-role    # role exists
aws logs describe-log-groups --log-group-name-prefix /rag-demo/app
```

---

## Phase 3 — Store the Qdrant API key in SSM (the one secret)

The key never goes in a file. It lives in SSM Parameter Store as a KMS-encrypted
SecureString and is fetched at runtime by the IAM role.

```bash
aws ssm put-parameter \
  --name "/rag-demo/qdrant-api-key" \
  --value "<paste-qdrant-api-key>" \
  --type SecureString \
  --region us-east-1
```

**✅ Checkpoint:** this returns the value (proves decryption works):
```bash
aws ssm get-parameter --name /rag-demo/qdrant-api-key --with-decryption \
  --query "Parameter.Value" --output text
```

---

## Phase 4 — Configure the app

```bash
cd aws-bedrock-rag
uv venv
uv pip install -r requirements.txt

cp .env.example .env
```

Edit `.env` and set at minimum:

```ini
AWS_REGION=us-east-1
S3_BUCKET=rag-demo-docs                # match your CloudFormation bucket name
QDRANT_URL=https://<id>.<region>.aws.cloud.qdrant.io:6333   # from Phase 1
QDRANT_API_KEY_PARAM=/rag-demo/qdrant-api-key               # SSM name, not the key
```

The remaining values (model ids, collection name, rate limit, similarity floor)
have working defaults — leave them unless you have a reason to change them.

**✅ Checkpoint:** `uv run pytest -q` → **23 passed** (offline; confirms the code
is wired correctly before you touch live AWS).

---

## Phase 5 — Authenticate to AWS (no static keys)

Use temporary, auto-expiring credentials. **Do not** put access keys in `.env`.

**Preferred — IAM Identity Center (SSO):**
```bash
aws configure sso          # one-time: set up the profile "rag-demo"
aws sso login --profile rag-demo
export AWS_PROFILE=rag-demo            # PowerShell: $env:AWS_PROFILE="rag-demo"
```

**Alternative — assume-role profile** in `~/.aws/config`:
```ini
[profile rag-demo]
role_arn = arn:aws:iam::<ACCOUNT_ID>:role/bedrock-rag-demo-role
source_profile = default
region = us-east-1
```

**✅ Checkpoint:** `aws sts get-caller-identity` returns your account/identity.

---

## Phase 6 — Load the corpus and build the index (one-time, offline)

Replace the sample document under `data/sample_docs/` with the client's real
documents first if you have them (`.pdf`, `.txt`, `.md` are supported).

```bash
# Upload documents to S3 (server-side KMS encryption enforced by the bucket policy)
bash scripts/upload_docs_to_s3.sh

# Chunk → embed (Titan) → write vectors + citation metadata to Qdrant
uv run python -m ingest.ingest
```

You should see per-document output and a final `Upserted N vectors.`

**✅ Checkpoint:**
```bash
aws s3 ls s3://rag-demo-docs --recursive        # your docs are there
```
and the ingest command finished without an error. (A first-run
`AccessDeniedException` here almost always means the SSM statement or Bedrock
model access from Phase 0/2/3 is missing.)

---

## Path A — Run locally (start here)

```bash
uv run streamlit run streamlit_app.py
```

Open http://localhost:8501 and ask a question the corpus can answer, then one it
can't (to show the refusal + sub-0.35 confidence).

**✅ Checkpoint:** you get a cited answer, and the **Sources** panel shows
`s3_key · page · chunk · score`. Then verify the audit trail:
```bash
aws logs tail /rag-demo/app --follow
```
You should see one JSON line per query (with the question as a SHA-256 hash).

> **Why local and not a public Space:** the app needs the IAM role to reach
> Bedrock/S3/SSM/KMS. Hosting it publicly would expose AWS credentials — the
> opposite of the security story. Local-against-real-AWS (or EC2) is the correct
> posture, and saying so is itself a selling point.

---

## Path B — EC2 quick-run (HTTP, IP-locked, private demos only)

> **No TLS on this path.** It's plain HTTP on `0.0.0.0:8501`, locked to your
> single IP by a security group. Fine for a private 1:1 demo; **not** the
> "encrypted in transit" deployment — for that use Path C.

1. **Networking:** put the instance in a VPC that has the **free S3 Gateway
   Endpoint** (so S3 traffic stays on the AWS backbone). Create it once:
   ```bash
   aws ec2 create-vpc-endpoint \
     --vpc-id "$VPC_ID" --vpc-endpoint-type Gateway \
     --service-name com.amazonaws.us-east-1.s3 \
     --route-table-ids "$PRIVATE_RTB_ID"
   ```
   **Do not create a NAT Gateway.** If you ever see one, it's the budget-alarm
   trigger to investigate.
2. **Launch** a `t2.micro` (Amazon Linux 2023).
3. **Attach the instance profile** `bedrock-rag-demo-role` — no keys copied to
   the box; boto3 pulls temporary creds from IMDSv2.
4. **Security group:** allow inbound `8501` from **your single IP only**; allow
   outbound `443` (Bedrock + Qdrant).
5. **On the instance**, run [scripts/deploy_ec2.sh](scripts/deploy_ec2.sh)
   (set `REPO_URL` first), then edit `.env` with your `QDRANT_URL`.
6. Visit `http://<ec2-public-ip>:8501`.

**✅ Checkpoint:** the page loads from your IP only; a different network is
refused by the security group.

---

## Path C — EC2 + ALB + ACM (the TLS deployment)

This backs the "TLS in transit" claim. Streamlit still listens on plain HTTP on
the instance, but it's never exposed directly — an ALB terminates TLS with a free
ACM certificate, and only the ALB can reach the instance.

```
Browser ──HTTPS (ACM cert)──► ALB ──HTTP, private──► EC2:8501 (Streamlit)
```

1. Request a **free public certificate in ACM** for your demo domain
   (e.g. `rag-demo.yourdomain.com`); validate via DNS.
2. Create an **internet-facing ALB** in public subnets; target group → `EC2:8501`.
3. ALB listeners:
   - `HTTPS :443` → forward to the target group (attach the ACM cert)
   - `HTTP :80` → redirect to `:443`
4. Security groups:
   - **ALB SG:** allow `443` (and `80` for redirect) from the demo viewer's IP.
   - **EC2 SG:** allow `8501` **only from the ALB SG** (no public access to 8501).
5. Point a DNS record at the ALB; visit `https://rag-demo.yourdomain.com`.

**✅ Checkpoint:** the site loads over HTTPS with a valid certificate, and hitting
`http://<ec2-ip>:8501` directly is refused (only the ALB SG can reach 8501).

---

## Optional — production network isolation for Bedrock

For the demo, Bedrock is reached over its public HTTPS endpoint (TLS 1.2+, data
stays in AWS). The documented production upgrade is a **VPC Interface Endpoint**
(~$7.30/mo, single AZ). No app code changes are needed — `--private-dns-enabled`
makes the SDK resolve to the private ENI automatically:

```bash
aws ec2 create-vpc-endpoint \
  --vpc-id "$VPC_ID" --vpc-endpoint-type Interface \
  --service-name com.amazonaws.us-east-1.bedrock-runtime \
  --subnet-ids "$PRIVATE_SUBNET_ID" --security-group-ids "$VPCE_SG_ID" \
  --private-dns-enabled
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `AccessDeniedException` on the **first question** (after embed/Bedrock works) | Missing `ssm:GetParameter` in the IAM policy | Re-attach [infra/iam-policy.json](infra/iam-policy.json) **in full**, including `SsmGetQdrantApiKey` |
| `AccessDeniedException` on **first invoke** | Bedrock model access not enabled | Phase 0.2 — enable both models in this region |
| `ResourceNotFoundException` writing logs | Log group missing | Phase 2 created `/rag-demo/app`; or `aws logs create-log-group --log-group-name /rag-demo/app` |
| App refuses everything (confidence ~0) | Collection empty / wrong `QDRANT_URL` or collection name | Re-run `uv run python -m ingest.ingest`; check `.env` |
| `Could not connect to Qdrant` | Wrong URL or API key | Verify `QDRANT_URL`; re-check the SSM SecureString value (Phase 3 checkpoint) |
| Startup error about credentials | Not authenticated / profile expired | `aws sso login --profile rag-demo` (Phase 5) |
| Costs creeping up | A forgotten NAT Gateway / RDS / OpenSearch | The $10 budget alarm should fire; check for stray always-on resources |

---

## Tear-down (stop all charges)

```bash
# 1. Delete the EC2 instance + ALB if you created them (Console or CLI).
# 2. Empty + delete the bucket, then the stack.
aws s3 rm s3://rag-demo-docs --recursive
aws cloudformation delete-stack --stack-name rag-demo

# 3. Remove the SSM parameter and (optionally) the Qdrant cluster.
aws ssm delete-parameter --name /rag-demo/qdrant-api-key
```

> The KMS key is scheduled for deletion with the stack (CloudFormation handles a
> waiting period). After tear-down, steady-state cost returns to $0.
