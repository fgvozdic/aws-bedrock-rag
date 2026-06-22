"""Tests for the session rate-limiter (app/rate_limit.py)."""
import pytest
import streamlit as st

from app.rate_limit import (
    RATE_LIMIT,
    can_query,
    init_rate_limit,
    record_query,
    remaining,
)


@pytest.fixture(autouse=True)
def fresh_session(monkeypatch):
    """Reset st.session_state before each test."""
    monkeypatch.setattr(st, "session_state", {})
    yield


def test_init_sets_count_to_zero():
    init_rate_limit()
    assert st.session_state["query_count"] == 0


def test_init_does_not_overwrite_existing():
    st.session_state["query_count"] = 3
    init_rate_limit()
    assert st.session_state["query_count"] == 3


def test_can_query_true_when_under_limit():
    st.session_state["query_count"] = 0
    assert can_query() is True


def test_can_query_false_at_limit():
    st.session_state["query_count"] = RATE_LIMIT
    assert can_query() is False


def test_remaining_counts_down():
    st.session_state["query_count"] = 1
    assert remaining() == RATE_LIMIT - 1


def test_record_query_increments():
    st.session_state["query_count"] = 0
    record_query()
    assert st.session_state["query_count"] == 1


def test_blocked_after_full_quota_consumed():
    st.session_state["query_count"] = 0
    for _ in range(RATE_LIMIT):
        assert can_query() is True
        record_query()
    assert can_query() is False
    assert remaining() == 0
