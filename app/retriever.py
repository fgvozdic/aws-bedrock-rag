"""
Retrieval orchestration: embed the question, then run the vector search.

Kept as a thin seam between bedrock.embed() and vector_store.similarity_search()
so rag_chain stays focused on the confidence gate, generation, and audit log.
"""
from qdrant_client import QdrantClient

from app.bedrock import embed
from app.config import TOP_K
from app.vector_store import Row, similarity_search


def retrieve(client: QdrantClient, question: str, k: int = TOP_K) -> tuple[list[Row], list[float]]:
    """Embed the question and return (rows best-first, query_vector)."""
    qvec = embed(question)
    rows = similarity_search(client, qvec, k=k)
    return rows, qvec
