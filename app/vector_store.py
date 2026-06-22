"""
Qdrant Cloud connection + similarity search.

The retrieval interface - similarity_search() returning
(s3_key, page, chunk_index, chunk_text, score) tuples ordered best-first - is
identical to what a pgvector-on-RDS implementation would return, so swapping
Qdrant for in-account pgvector is a localized change behind this module.
"""
from qdrant_client import QdrantClient

from app.config import QDRANT_COLLECTION, QDRANT_URL, get_qdrant_api_key

# Row shape returned by similarity_search(): the citation contract.
Row = tuple[str, int, int, str, float]


def get_client(url: str = QDRANT_URL) -> QdrantClient:
    """Build a Qdrant client. API key is fetched from SSM SecureString."""
    return QdrantClient(url=url, api_key=get_qdrant_api_key())


def similarity_search(
    client: QdrantClient, query_vec: list[float], k: int = 5
) -> list[Row]:
    """Top-k cosine ANN search. Returns rows best-first; row[0][4] is top score."""
    hits = client.search(
        collection_name=QDRANT_COLLECTION,
        query_vector=query_vec,
        limit=k,
        with_payload=True,  # citation metadata lives in the point payload
    )
    return [
        (
            h.payload["s3_key"],
            h.payload["page"],
            h.payload["chunk_index"],
            h.payload["chunk_text"],
            h.score,  # cosine similarity
        )
        for h in hits
    ]
