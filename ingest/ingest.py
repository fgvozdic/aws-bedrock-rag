"""
One-time, OFFLINE ingestion: S3 docs -> page text -> chunks -> Titan embeddings
-> Qdrant collection (with citation metadata in each point's payload).

Run by the operator ahead of the demo so the collection is pre-populated. This
is NOT part of the live request path.

    python -m ingest.ingest

Reads every object under the S3 bucket, supports .pdf / .txt / .md. Each Qdrant
point carries {s3_key, page, chunk_index, chunk_text} so every retrieved vector
traces back to its exact source location.
"""
import io
import sys
import uuid

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from app.aws_clients import s3
from app.bedrock import embed
from app.config import EMBED_DIM, QDRANT_COLLECTION, QDRANT_URL, S3_BUCKET, get_qdrant_api_key
from ingest.chunking import Chunk, chunk_pages

SUPPORTED_SUFFIXES = (".pdf", ".txt", ".md")


def _read_pages(key: str, body: bytes) -> list[str]:
    """Extract page texts. PDFs split by page; text/markdown are a single page."""
    if key.lower().endswith(".pdf"):
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(body))
        return [(page.extract_text() or "") for page in reader.pages]
    return [body.decode("utf-8", errors="replace")]


def _list_keys(bucket: str) -> list[str]:
    keys: list[str] = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket):
        for obj in page.get("Contents", []):
            if obj["Key"].lower().endswith(SUPPORTED_SUFFIXES):
                keys.append(obj["Key"])
    return keys


def _collect_chunks(bucket: str) -> list[Chunk]:
    chunks: list[Chunk] = []
    for key in _list_keys(bucket):
        body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
        pages = _read_pages(key, body)
        doc_chunks = chunk_pages(key, pages)
        print(f"  {key}: {len(pages)} page(s) -> {len(doc_chunks)} chunk(s)")
        chunks.extend(doc_chunks)
    return chunks


def main() -> None:
    print(f"Ingesting from s3://{S3_BUCKET} into Qdrant collection '{QDRANT_COLLECTION}'")
    chunks = _collect_chunks(S3_BUCKET)
    if not chunks:
        print("No supported documents found - nothing to ingest.", file=sys.stderr)
        sys.exit(1)

    client = QdrantClient(url=QDRANT_URL, api_key=get_qdrant_api_key())
    client.recreate_collection(
        collection_name=QDRANT_COLLECTION,
        vectors_config=VectorParams(size=EMBED_DIM, distance=Distance.COSINE),
    )

    points = [
        PointStruct(
            id=str(uuid.uuid4()),
            vector=embed(c.text),
            payload={
                "s3_key": c.s3_key,
                "page": c.page,
                "chunk_index": c.chunk_index,
                "chunk_text": c.text,
            },
        )
        for c in chunks
    ]
    client.upsert(collection_name=QDRANT_COLLECTION, points=points)
    print(f"Done. Upserted {len(points)} vectors.")


if __name__ == "__main__":
    main()
