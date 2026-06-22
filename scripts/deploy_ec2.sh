#!/usr/bin/env bash
# EC2 quick-run — HTTP, security-group IP-locked, for PRIVATE 1:1 demos only.
# This is NOT the TLS path. There is no TLS in transit on this path; it is locked
# down only by a security group that allows your single IP. For TLS in transit,
# use the ALB + ACM deployment described in the README (§11.3 of the blueprint).
#
# Prerequisites already done (run on the instance after launching it):
#   1. t2.micro (Amazon Linux 2023) in the VPC that has the S3 gateway endpoint.
#   2. Instance profile  bedrock-rag-demo-role  attached (NO keys copied to box).
#   3. Security group: allow 8501 ONLY from your single IP; allow 443 egress
#      (Bedrock + Qdrant Cloud).
set -euo pipefail

REPO_URL="${REPO_URL:?set REPO_URL to your git remote}"

sudo dnf install -y python3.11 git

git clone "${REPO_URL}" aws-bedrock-rag
cd aws-bedrock-rag

python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # edit QDRANT_URL etc. before first run

# Credentials come from the instance profile via IMDSv2 — nothing on disk.
# The Qdrant API key is fetched at runtime from SSM SecureString.
nohup streamlit run streamlit_app.py \
  --server.port 8501 --server.address 0.0.0.0 >streamlit.log 2>&1 &

echo "Streamlit starting on http://<ec2-public-ip>:8501 (HTTP only; SG-locked to your IP)"
