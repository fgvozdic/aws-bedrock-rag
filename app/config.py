"""
Central configuration for the AWS Bedrock RAG demo.

Principle: the app code contains ZERO credentials and reads ZERO secret values
from files it owns. Non-secret config comes from environment variables (see
.env.example). The single secret - the Qdrant Cloud API key - lives in SSM
Parameter Store as a KMS-encrypted SecureString and is fetched at runtime via
the IAM role's ssm:GetParameter permission.
"""
import os

from dotenv import load_dotenv

load_dotenv()

# --- AWS ---
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
S3_BUCKET = os.getenv("S3_BUCKET", "rag-demo-docs")

# --- Bedrock models (must be enabled in Console -> Bedrock -> Model access) ---
EMBED_MODEL = os.getenv("BEDROCK_EMBED_MODEL", "amazon.titan-embed-text-v2:0")
GEN_MODEL = os.getenv("BEDROCK_GEN_MODEL", "anthropic.claude-3-haiku-20240307-v1:0")
EMBED_DIM = int(os.getenv("EMBED_DIM", "1024"))

# --- Qdrant Cloud (vector store) ---
QDRANT_URL = os.getenv("QDRANT_URL", "")
QDRANT_API_KEY_PARAM = os.getenv("QDRANT_API_KEY_PARAM", "/rag-demo/qdrant-api-key")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "doc_chunks")

# --- Observability ---
CLOUDWATCH_LOG_GROUP = os.getenv("CLOUDWATCH_LOG_GROUP", "/rag-demo/app")
CLOUDWATCH_LOG_STREAM = "queries"

# --- Demo guardrails ---
RATE_LIMIT_PER_SESSION = int(os.getenv("RATE_LIMIT_PER_SESSION", "10"))
TOP_K = int(os.getenv("TOP_K", "5"))
# Hard refusal below this cosine similarity - the model is NOT called.
SIMILARITY_FLOOR = float(os.getenv("SIMILARITY_FLOOR", "0.35"))


def get_qdrant_api_key() -> str:
    """Fetch the Qdrant Cloud API key from SSM Parameter Store (SecureString).

    The key is KMS-decrypted via the customer-managed key already granted in the
    IAM policy (SsmGetQdrantApiKey + KmsDecryptForEncryptedData). Missing the
    ssm:GetParameter statement is the #1 silent first-query AccessDeniedException
    - see infra/iam-policy.json.
    """
    import boto3

    ssm = boto3.client("ssm", region_name=AWS_REGION)
    resp = ssm.get_parameter(Name=QDRANT_API_KEY_PARAM, WithDecryption=True)
    return resp["Parameter"]["Value"]
