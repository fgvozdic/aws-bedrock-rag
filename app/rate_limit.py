"""
Session-based rate limiter (10 queries / browser session).

Implemented with Streamlit session state - no extra infra, resets per browser
session. This is a COST GUARD for a demo, not a security control: session state
is per-browser and resettable. A real deployment enforces limits server-side
(API Gateway usage plans, per-IP DynamoDB counter, Bedrock account quotas).
"""
import streamlit as st

from app.config import RATE_LIMIT_PER_SESSION

RATE_LIMIT = RATE_LIMIT_PER_SESSION
LIMIT_MSG = (
    "🚧 Demo limit reached (10 queries). "
    "This is a portfolio demo - **message me on Upwork for full access** "
    "or a tailored build on your own AWS account."
)


def init_rate_limit() -> None:
    st.session_state.setdefault("query_count", 0)


def can_query() -> bool:
    return st.session_state.get("query_count", 0) < RATE_LIMIT


def record_query() -> None:
    st.session_state["query_count"] = st.session_state.get("query_count", 0) + 1


def remaining() -> int:
    return max(0, RATE_LIMIT - st.session_state.get("query_count", 0))
