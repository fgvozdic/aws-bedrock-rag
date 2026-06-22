"""Tests for the ingestion chunker (ingest/chunking.py)."""
import pytest

from ingest.chunking import Chunk, _split_words, chunk_pages


def test_blank_text_yields_no_chunks():
    assert _split_words("", 10, 2) == []
    assert _split_words("   \n  ", 10, 2) == []


def test_short_text_is_one_chunk():
    out = _split_words("one two three", size=10, overlap=2)
    assert out == ["one two three"]


def test_overlap_must_be_smaller_than_size():
    with pytest.raises(ValueError):
        _split_words("a b c d", size=5, overlap=5)


def test_windows_overlap_by_configured_amount():
    words = " ".join(str(i) for i in range(10))  # "0 1 2 ... 9"
    out = _split_words(words, size=4, overlap=2)
    # step = size - overlap = 2 -> starts at 0, 2, 4, 6
    assert out[0] == "0 1 2 3"
    assert out[1] == "2 3 4 5"  # overlaps previous by 2 words
    assert out[-1].endswith("9")


def test_chunk_pages_assigns_page_numbers_and_global_index():
    pages = ["alpha beta", "gamma delta"]
    chunks = chunk_pages("policies/handbook.md", pages, size=10, overlap=2)
    assert all(isinstance(c, Chunk) for c in chunks)
    assert [c.page for c in chunks] == [1, 2]
    assert [c.chunk_index for c in chunks] == [0, 1]  # global, monotonic
    assert all(c.s3_key == "policies/handbook.md" for c in chunks)


def test_chunk_pages_skips_blank_pages():
    chunks = chunk_pages("k", ["", "real content here", ""], size=10, overlap=2)
    assert len(chunks) == 1
    assert chunks[0].page == 2
    assert chunks[0].chunk_index == 0
