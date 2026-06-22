# Private Document Q&A — AWS Bedrock RAG

[![CI](https://github.com/fgvozdic/aws-bedrock-rag/actions/workflows/iac-validate.yml/badge.svg)](https://github.com/fgvozdic/aws-bedrock-rag/actions/workflows/iac-validate.yml)

<!-- CI runs four jobs with NO AWS account and provisions nothing: cfn-lint
     (strict), checkov (IaC security scan), parliament (IAM least-privilege),
     and the offline pytest suite. The IaC is the artifact — validated on every
     push, never deployed. -->

> **Portfolio demo for security-conscious / enterprise clients.** A document
> Q&A (RAG) app where the source documents live in your S3, generation runs on
> Amazon Bedrock, and the only thing that leaves AWS is the answer text. IAM
> roles instead of static keys, KMS encryption, and one CloudWatch audit line
> per query.

**Selling point:** *Your data never leaves AWS. Every call is IAM-controlled.
The architecture is the same shape you'd ship to production.*

There is **intentionally no public URL** — the app needs an IAM role to reach
Bedrock, S3, SSM, and KMS, and hosting it publicly would contradict the entire
security story. It runs locally against real AWS, or on EC2 behind an ALB. See
[Why no public link](#why-no-public-link).

## Architecture

```
                 ┌──────────────────────────┐
                 │   Streamlit UI            │
                 │   (laptop or EC2)         │
                 └─────────────┬─────────────┘
==================== AWS ACCOUNT (us-east-1) =====================
                               │ query
                 ┌─────────────▼─────────────┐
                 │  RAG App (Python + boto3)  │  ── audit log ──┐
                 │  runs under IAM ROLE       │                 │
                 └──┬───────┬──────────┬──────┘                 ▼
       1. embed     │       │ 2. search│ 3. fetch        ┌────────────┐
          (Titan)   ▼       │ (Qdrant) │  source (S3)    │ CloudWatch │
              ┌──────────┐  │          ▼                 └────────────┘
              │ Bedrock  │  ▼      ┌────────┐  ┌──────────┐
              │ Titan V2 │  ┌──────────┐    │  │ S3 docs  │
              └──────────┘  │ Qdrant   │    │  │ SSE-KMS  │
       4. prompt+ctx        │ Cloud    │────┘  │ block pub│
              ┌──────────┐  │ free tier│       └──────────┘
              │ Bedrock  │  └──────────┘
              │ Claude 3 │  (vectors + citation metadata only;
              │ Haiku    │   source documents never leave S3)
              └────┬─────┘
        5. cited   │
           answer  ▼  (App → UI)

  Identity: IAM role (no static keys)   Encryption: KMS (S3 + SSM SecureString)
  Networking: free S3 Gateway Endpoint, NO NAT Gateway
  Egress out of AWS: answer text + query/chunk vectors to Qdrant only
```

## Enterprise RAG controls (why this isn't "another chatbot")

- **Confidence gate / hard refusal.** If the best retrieved chunk scores below
  `0.35` cosine, the app returns *"I cannot find this in the provided
  documents."* **before** calling the model. A confident wrong answer is a
  compliance liability, not a feature.
- **`temperature=0`** — deterministic, reproducible answers.
- **Full citations.** Every answer cites `s3_key | page | chunk_index`, so a
  reviewer can trace any fact to its exact source.
- **One audit line per query** in CloudWatch — confidence, what was retrieved,
  what was cited, latency, refusal flag. The question is logged as a **SHA-256
  hash**, not plaintext.
- **Least-privilege IAM** — five scoped statements, zero wildcards on actions,
  zero `*` resources. See [infra/iam-policy.json](infra/iam-policy.json).

## Prerequisites — do these FIRST

These are the two most common live-demo killers. Both fail at *first invoke*,
not at startup, so the app looks fine until you ask a question. See
[infra/setup_notes.md](infra/setup_notes.md) for the full click-path.

1. **Enable Bedrock model access** (Console → Bedrock → Model access) for
   **both** `anthropic.claude-3-haiku-20240307-v1:0` and
   `amazon.titan-embed-text-v2:0` in `us-east-1`. One-time, manual, **not**
   created by CloudFormation.
2. **Set a $10/month AWS Budget alarm** before provisioning anything.

## Local setup (points at real AWS)

> **Full step-by-step deploy manual:** [DEPLOY.md](DEPLOY.md) — from a fresh AWS
> account to a running app, with checkpoints, EC2/ALB paths, troubleshooting, and
> tear-down. The condensed version is below.

### Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) — `pip install uv`
- AWS CLI v2, authenticated **without static keys** (SSO preferred)
- A free 1 GB [Qdrant Cloud](https://cloud.qdrant.io) cluster (no credit card)

### Install & provision

```bash
git clone <repo>
cd aws-bedrock-rag

uv venv
uv pip install -r requirements.txt

# 1. Authenticate (no static keys)
aws sso login --profile rag-demo
export AWS_PROFILE=rag-demo          # PowerShell: $env:AWS_PROFILE="rag-demo"

# 2. Provision infra (S3 + KMS + IAM role + log group)
aws cloudformation deploy \
  --template-file infra/cloudformation.yaml \
  --stack-name rag-demo \
  --capabilities CAPABILITY_NAMED_IAM

# 3. Store the Qdrant API key in SSM Parameter Store (SecureString, free)
aws ssm put-parameter \
  --name "/rag-demo/qdrant-api-key" \
  --value "<paste-qdrant-api-key>" \
  --type SecureString

# 4. Configure non-secret env, then load the corpus + build the index
cp .env.example .env                  # edit QDRANT_URL (+ S3_BUCKET if changed)
bash scripts/upload_docs_to_s3.sh
uv run python -m ingest.ingest

# 5. Run
uv run streamlit run streamlit_app.py # http://localhost:8501
```

### Run tests

```bash
uv run pytest -q          # 23 tests, fully offline — no AWS creds needed
```

The tests mock Bedrock, Qdrant, SSM, and CloudWatch, so the confidence gate,
citation contract, chunker, rate limiter, and SSM fetch are all verified without
touching AWS.

## Configuration

`.env` holds **non-secret config only** (region, bucket, model ids, Qdrant URL).
The one secret — the Qdrant API key — lives in **SSM Parameter Store as a
KMS-encrypted SecureString** and is fetched at runtime via the role's
`ssm:GetParameter`. No credentials are ever read from a file the app owns; boto3
resolves the IAM role automatically. See [.env.example](.env.example).

## Cost

Steady state is **~$2–3/month** at demo volume — essentially KMS at ~$1/mo plus
light Bedrock usage. There is no always-on AWS compute in the data path (no RDS,
no NAT, no interface endpoint), so nothing bleeds money at idle. The 10-query
session cap and the mandatory $10/mo Budget alarm bound spend.

| Choice | Why |
|--------|-----|
| Qdrant Cloud free tier (vs OpenSearch Serverless) | avoids a ~$300/mo idle floor |
| Free S3 Gateway Endpoint (vs NAT Gateway) | $0 vs ~$32/mo + data |
| SSM SecureString (vs Secrets Manager) | same KMS-encrypted fetch, $0 vs ~$0.40/mo |
| Claude 3 Haiku + Titan V2 | a fraction of a cent per query |

## Why no public link

Hosting this on a public Space would mean exposing AWS credentials — the
opposite of the security story. Present it instead as:

1. A ~3-minute Loom walkthrough showing the app working (cited answer, the
   refusal on an out-of-corpus question, the 10-query limit), then the AWS
   console: Bedrock invocation activity, the CloudWatch audit log, the IAM role.
2. The safe artifacts published on GitHub: the [IAM policy](infra/iam-policy.json),
   the architecture diagram, the [bucket policy](infra/s3-bucket-policy.json),
   and the [CloudFormation template](infra/cloudformation.yaml) — account ids and
   secrets redacted.
3. *"There is intentionally no public endpoint. The fact that you can't reach it
   from the open internet is exactly the security property an enterprise wants."*

## Project structure

```
aws-bedrock-rag/
├── streamlit_app.py          # entrypoint: streamlit run streamlit_app.py
├── app/
│   ├── config.py             # env loading + get_qdrant_api_key() (SSM)
│   ├── aws_clients.py         # boto3 clients via default cred chain (role-based)
│   ├── bedrock.py             # embed() + generate() wrappers
│   ├── vector_store.py        # Qdrant client + similarity_search() (citation contract)
│   ├── retriever.py           # embed → search orchestration
│   ├── rag_chain.py           # confidence gate + citations + per-query audit log
│   ├── rate_limit.py          # session-based 10-query limiter
│   └── logging_setup.py       # CloudWatch log-stream init
├── ingest/
│   ├── chunking.py            # per-page word-window chunker
│   └── ingest.py              # S3 docs → Titan → Qdrant (one-time, offline)
├── infra/                     # IaC + manual click-path
│   ├── iam-role.json          # trust policy
│   ├── iam-policy.json        # least-privilege permission policy
│   ├── s3-bucket-policy.json  # block public + enforce SSE-KMS + deny non-TLS
│   ├── cloudformation.yaml    # S3 + KMS + IAM + log group
│   └── setup_notes.md         # manual fallback + prerequisites
├── scripts/
│   ├── upload_docs_to_s3.sh   # sync demo corpus to S3 (SSE-KMS)
│   └── deploy_ec2.sh          # t2.micro HTTP/IP-locked quick-run (private demos)
├── data/sample_docs/          # demo corpus to pre-upload to S3
└── tests/                     # 5 test files, offline, no AWS creds needed
```

The full technical blueprint (model/vector-store/networking decisions, security
architecture summary for a CISO, TCO breakdown) is in
[`demo-blueprints/04-aws-bedrock-rag.md`](../demo-blueprints/04-aws-bedrock-rag.md).
