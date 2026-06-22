"""
The enterprise RAG control plane: retrieve, refuse on low confidence, surface
the score, build cited context, generate, and write ONE audit line per query.

The confidence gate is the non-negotiable bit: if the top retrieved chunk
scores below SIMILARITY_FLOOR, the app refuses BEFORE calling the model. In a
compliance context a confident wrong answer is a liability, not a feature.
"""
import hashlib
import json
import logging
import time
import uuid

from qdrant_client import QdrantClient

from app.aws_clients import logs as cw_logs
from app.bedrock import generate
from app.config import (
    CLOUDWATCH_LOG_GROUP,
    CLOUDWATCH_LOG_STREAM,
    GEN_MODEL,
    SIMILARITY_FLOOR,
    TOP_K,
)
from app.retriever import retrieve
from app.vector_store import Row

logger = logging.getLogger(__name__)

REFUSAL = "I cannot find this in the provided documents."


def _format_context(rows: list[Row]) -> str:
    """Tag each chunk with its source so the model can cite [s3_key | page | chunk]."""
    return "\n\n".join(
        f"[{r[0]} | page {r[1]} | chunk {r[2]}]\n{r[3]}" for r in rows
    )


def _citations(rows: list[Row]) -> list[dict]:
    return [
        {"s3_key": r[0], "page": r[1], "chunk_index": r[2], "score": round(r[4], 4)}
        for r in rows
    ]


def run_rag(client: QdrantClient, question: str) -> dict:
    """Embed -> search -> confidence gate -> (refuse | generate) -> audit log."""
    t0 = time.time()
    query_id = str(uuid.uuid4())

    rows, _ = retrieve(client, question, k=TOP_K)
    top_score = rows[0][4] if rows else 0.0

    if top_score < SIMILARITY_FLOOR:
        # Hard refuse - do NOT call the model.
        result = {
            "answer": REFUSAL,
            "confidence": round(top_score, 4),
            "citations": [],
            "refused": True,
        }
    else:
        answer = generate(question, _format_context(rows))
        result = {
            "answer": answer,
            "confidence": round(top_score, 4),
            "citations": _citations(rows),
            "refused": False,
        }

    _audit_log(query_id, question, result, time.time() - t0)
    return result | {"query_id": query_id}


def _audit_log(query_id: str, question: str, result: dict, elapsed: float) -> None:
    """Write ONE structured audit line per query to CloudWatch.

    The question is logged as a SHA-256 hash (not plaintext), so the trail proves
    THAT a query happened and WHAT was retrieved without persisting potentially
    sensitive question text. Swap to plaintext only if a client's policy requires
    full-text logging. Failures here are swallowed - the answer already returned.
    """
    entry = {
        "query_id": query_id,
        "question_sha256": hashlib.sha256(question.encode()).hexdigest()[:16],
        "confidence": result["confidence"],
        "refused": result["refused"],
        "cited_sources": [
            f"{c['s3_key']}#chunk{c['chunk_index']}" for c in result["citations"]
        ],
        "model_id": GEN_MODEL,
        "latency_ms": round(elapsed * 1000),
    }
    try:
        cw_logs.put_log_events(
            logGroupName=CLOUDWATCH_LOG_GROUP,
            logStreamName=CLOUDWATCH_LOG_STREAM,
            logEvents=[
                {"timestamp": int(time.time() * 1000), "message": json.dumps(entry)}
            ],
        )
    except Exception as exc:  # noqa: BLE001 - audit logging must never break a query
        logger.warning("Audit log write failed: %s", exc)
