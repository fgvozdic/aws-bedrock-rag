"""Tests for the Qdrant retrieval contract (app/vector_store.py).

The point of these tests is the CITATION CONTRACT: similarity_search must return
(s3_key, page, chunk_index, chunk_text, score) tuples, best-first, so the rest of
the pipeline (confidence gate + citations) can rely on that shape.
"""
from types import SimpleNamespace

from app.vector_store import similarity_search


def _hit(s3_key, page, chunk_index, chunk_text, score):
    return SimpleNamespace(
        score=score,
        payload={
            "s3_key": s3_key,
            "page": page,
            "chunk_index": chunk_index,
            "chunk_text": chunk_text,
        },
    )


class _FakeClient:
    def __init__(self, hits):
        self._hits = hits
        self.last_call = None

    def search(self, collection_name, query_vector, limit, with_payload):
        self.last_call = {
            "collection_name": collection_name,
            "limit": limit,
            "with_payload": with_payload,
        }
        return self._hits


def test_maps_payload_to_citation_tuple():
    client = _FakeClient([_hit("doc.md", 2, 7, "the text", 0.81)])
    rows = similarity_search(client, [0.0] * 4, k=5)
    assert rows == [("doc.md", 2, 7, "the text", 0.81)]


def test_preserves_order_so_row0_is_top_score():
    client = _FakeClient(
        [_hit("a", 1, 0, "x", 0.9), _hit("b", 1, 1, "y", 0.4)]
    )
    rows = similarity_search(client, [0.0], k=2)
    assert rows[0][4] == 0.9
    assert rows[1][4] == 0.4


def test_requests_payload_and_passes_k():
    client = _FakeClient([])
    similarity_search(client, [0.0], k=3)
    assert client.last_call["with_payload"] is True
    assert client.last_call["limit"] == 3
