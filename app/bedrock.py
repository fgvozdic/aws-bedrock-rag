"""
Amazon Bedrock call wrappers: embed() for Titan Text Embeddings V2,
generate() for Claude 3 Haiku.

Both run over Bedrock's public HTTPS endpoint (TLS 1.2+); the request stays
inside AWS datacenters and prompts/outputs are not used to train base models.
"""
import json

from app.aws_clients import bedrock
from app.config import EMBED_DIM, EMBED_MODEL, GEN_MODEL

SYSTEM_PROMPT = (
    "You are a precise assistant. Answer ONLY from the provided context. "
    "If the answer is not in the context, say "
    "'I cannot find this in the provided documents.' "
    "Never use prior knowledge. "
    "Cite every claim with its source as [s3_key | page | chunk_index]."
)


def embed(text: str) -> list[float]:
    """Embed a single string with Titan Text Embeddings V2 -> EMBED_DIM vector."""
    resp = bedrock.invoke_model(
        modelId=EMBED_MODEL,
        body=json.dumps(
            {"inputText": text, "dimensions": EMBED_DIM, "normalize": True}
        ),
    )
    return json.loads(resp["body"].read())["embedding"]


def generate(question: str, context: str) -> str:
    """Answer the question grounded in context. temperature=0 -> deterministic."""
    resp = bedrock.invoke_model(
        modelId=GEN_MODEL,
        body=json.dumps(
            {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 800,
                "temperature": 0,  # non-negotiable: deterministic, no fabrication
                "system": SYSTEM_PROMPT,
                "messages": [
                    {
                        "role": "user",
                        "content": f"<context>\n{context}\n</context>\n\nQ: {question}",
                    }
                ],
            }
        ),
    )
    return json.loads(resp["body"].read())["content"][0]["text"]
