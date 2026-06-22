"""
Text splitting helpers for the ingestion pipeline.

Chunking is done PER PAGE so every chunk keeps an accurate page number for
citations. Splitting is word-based with a fixed overlap - simple, deterministic,
and dependency-free (no tokenizer download needed for a demo corpus).
"""
from dataclasses import dataclass

CHUNK_WORDS = 220  # ~ a dense paragraph; comfortably inside Titan's input limit
CHUNK_OVERLAP_WORDS = 40  # carry context across chunk boundaries


@dataclass(frozen=True)
class Chunk:
    """One retrievable unit with the metadata needed to cite it."""

    s3_key: str
    page: int
    chunk_index: int
    text: str


def _split_words(text: str, size: int, overlap: int) -> list[str]:
    """Greedy word-window split with overlap. Returns [] for blank text."""
    words = text.split()
    if not words:
        return []
    if overlap >= size:
        raise ValueError("overlap must be smaller than size")

    step = size - overlap
    out: list[str] = []
    for start in range(0, len(words), step):
        window = words[start : start + size]
        if window:
            out.append(" ".join(window))
        if start + size >= len(words):
            break
    return out


def chunk_pages(
    s3_key: str,
    pages: list[str],
    size: int = CHUNK_WORDS,
    overlap: int = CHUNK_OVERLAP_WORDS,
) -> list[Chunk]:
    """Split each page into overlapping chunks; chunk_index is global per document.

    Args:
        s3_key: the source object key (citation anchor).
        pages: page texts, ordered. pages[0] is page 1.
    """
    chunks: list[Chunk] = []
    idx = 0
    for page_num, page_text in enumerate(pages, start=1):
        for piece in _split_words(page_text, size, overlap):
            chunks.append(
                Chunk(s3_key=s3_key, page=page_num, chunk_index=idx, text=piece)
            )
            idx += 1
    return chunks
