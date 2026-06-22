#!/usr/bin/env bash
# Upload the demo corpus to S3. Server-side encryption is enforced by the bucket
# policy (deny unencrypted PutObject), and --sse aws:kms makes it explicit here.
set -euo pipefail

BUCKET="${S3_BUCKET:-rag-demo-docs}"
SRC="$(dirname "$0")/../data/sample_docs"

echo "Syncing ${SRC} -> s3://${BUCKET}/ (SSE-KMS)"
aws s3 sync "${SRC}" "s3://${BUCKET}/" \
  --sse aws:kms \
  --exclude "*" \
  --include "*.pdf" --include "*.txt" --include "*.md"

echo "Done. Now run:  python -m ingest.ingest"
