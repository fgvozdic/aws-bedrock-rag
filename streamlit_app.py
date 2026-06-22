"""
Entrypoint:  streamlit run streamlit_app.py

This app runs LOCALLY (or on EC2) against real AWS - it needs an IAM role to
reach Bedrock, S3, SSM, and KMS, so it is intentionally NOT hosted as a public
Space. That "no public endpoint" property is the security story, not a gap.
"""
import streamlit as st

from app.config import QDRANT_URL, SIMILARITY_FLOOR
from app.logging_setup import ensure_log_stream
from app.rate_limit import (
    LIMIT_MSG,
    RATE_LIMIT,
    can_query,
    init_rate_limit,
    record_query,
    remaining,
)

st.set_page_config(page_title="AWS Bedrock RAG (private)", page_icon="🔒")


@st.cache_resource
def _bootstrap():
    """One-time startup: ensure the CloudWatch log stream + a Qdrant client.

    Cached so we don't recreate the client (or re-fetch the SSM key) on every
    rerun. Returns the Qdrant client used for the whole session.
    """
    from app.vector_store import get_client

    ensure_log_stream()
    return get_client(QDRANT_URL)


def main() -> None:
    init_rate_limit()

    st.title("🔒 Private Document Q&A — AWS Bedrock RAG")
    st.caption(
        "Documents and inference stay inside AWS. IAM-scoped, KMS-encrypted, "
        "every query audited in CloudWatch."
    )

    try:
        client = _bootstrap()
    except Exception as exc:  # noqa: BLE001 - surface setup failures clearly
        st.error(
            "**Startup failed.** Check AWS credentials (IAM role), the Qdrant URL, "
            "and that the §0.1 prerequisites are done (Bedrock model access enabled, "
            "SSM parameter set).\n\n"
            f"Details: `{exc}`"
        )
        st.stop()

    st.caption(f"Demo queries remaining: {remaining()} / {RATE_LIMIT}")

    # Replay prior turns in this session.
    for turn in st.session_state.get("history", []):
        with st.chat_message(turn["role"]):
            st.markdown(turn["content"])

    if prompt := st.chat_input("Ask about the documents..."):
        if not can_query():
            st.warning(LIMIT_MSG)
            return

        record_query()
        st.session_state.setdefault("history", []).append(
            {"role": "user", "content": prompt}
        )
        with st.chat_message("user"):
            st.markdown(prompt)

        from app.rag_chain import run_rag

        with st.chat_message("assistant"):
            with st.spinner("Retrieving and grounding..."):
                result = run_rag(client, prompt)
            st.markdown(result["answer"])

            refused = result["refused"]
            badge = f"Confidence (top match): {result['confidence']:.2f}"
            if refused:
                badge += f"  ·  refused (below {SIMILARITY_FLOOR:.2f} floor)"
            st.caption(badge)

            if result["citations"]:
                with st.expander("Sources (full audit trail)"):
                    for c in result["citations"]:
                        st.write(
                            f"- `{c['s3_key']}` · page {c['page']} · "
                            f"chunk {c['chunk_index']} · score {c['score']:.2f}"
                        )

        st.session_state["history"].append(
            {"role": "assistant", "content": result["answer"]}
        )


main()
