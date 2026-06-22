"""
Tests for the enterprise RAG control plane (app/rag_chain.py).

The non-negotiable behavior under test: below the similarity floor the app
REFUSES without ever calling the model, and above it the app generates with
full citations. Plus the audit log hashes the question instead of storing it.
"""
import json
from unittest.mock import MagicMock

import pytest

import app.rag_chain as rc
from app.config import SIMILARITY_FLOOR


@pytest.fixture(autouse=True)
def silence_audit_log(monkeypatch):
    """Replace the CloudWatch client so tests never touch AWS."""
    monkeypatch.setattr(rc, "cw_logs", MagicMock())
    yield


def _rows(top_score):
    # (s3_key, page, chunk_index, chunk_text, score)
    return [("policies/handbook.md", 1, 0, "encrypted at rest", top_score)]


def test_refuses_below_floor_without_calling_model(monkeypatch):
    monkeypatch.setattr(rc, "retrieve", lambda c, q, k: (_rows(0.20), [0.0]))
    gen = MagicMock(return_value="should never be called")
    monkeypatch.setattr(rc, "generate", gen)

    result = rc.run_rag(client=object(), question="unrelated question")

    assert result["refused"] is True
    assert result["answer"] == rc.REFUSAL
    assert result["citations"] == []
    gen.assert_not_called()


def test_empty_retrieval_refuses(monkeypatch):
    monkeypatch.setattr(rc, "retrieve", lambda c, q, k: ([], []))
    gen = MagicMock()
    monkeypatch.setattr(rc, "generate", gen)

    result = rc.run_rag(client=object(), question="anything")

    assert result["refused"] is True
    assert result["confidence"] == 0.0
    gen.assert_not_called()


def test_generates_with_citations_above_floor(monkeypatch):
    monkeypatch.setattr(rc, "retrieve", lambda c, q, k: (_rows(0.82), [0.0]))
    monkeypatch.setattr(rc, "generate", lambda q, ctx: "Data is encrypted [policies/handbook.md | page 1 | chunk 0].")

    result = rc.run_rag(client=object(), question="How is data encrypted?")

    assert result["refused"] is False
    assert result["confidence"] == 0.82
    assert result["citations"][0]["s3_key"] == "policies/handbook.md"
    assert result["citations"][0]["chunk_index"] == 0


def test_boundary_exactly_at_floor_generates(monkeypatch):
    """score == floor is NOT below the floor, so it should generate (>=)."""
    monkeypatch.setattr(rc, "retrieve", lambda c, q, k: (_rows(SIMILARITY_FLOOR), [0.0]))
    monkeypatch.setattr(rc, "generate", lambda q, ctx: "answer")

    result = rc.run_rag(client=object(), question="q")
    assert result["refused"] is False


def test_audit_log_hashes_question_not_plaintext(monkeypatch):
    monkeypatch.setattr(rc, "retrieve", lambda c, q, k: (_rows(0.9), [0.0]))
    monkeypatch.setattr(rc, "generate", lambda q, ctx: "answer")
    fake_logs = MagicMock()
    monkeypatch.setattr(rc, "cw_logs", fake_logs)

    secret_q = "What is the CEO's home address?"
    rc.run_rag(client=object(), question=secret_q)

    fake_logs.put_log_events.assert_called_once()
    logged = fake_logs.put_log_events.call_args.kwargs["logEvents"][0]["message"]
    entry = json.loads(logged)
    assert secret_q not in logged  # plaintext question must not be persisted
    assert len(entry["question_sha256"]) == 16
    assert entry["refused"] is False


def test_query_id_returned(monkeypatch):
    monkeypatch.setattr(rc, "retrieve", lambda c, q, k: (_rows(0.9), [0.0]))
    monkeypatch.setattr(rc, "generate", lambda q, ctx: "answer")
    result = rc.run_rag(client=object(), question="q")
    assert "query_id" in result and result["query_id"]
