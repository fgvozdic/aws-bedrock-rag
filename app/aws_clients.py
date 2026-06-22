"""
boto3 clients built from the default credential provider chain.

No keys are passed in. boto3 resolves credentials automatically:
  EC2   -> instance profile (IMDSv2)            [preferred for deployed demo]
  Local -> AWS SSO / assumed-role / shared profile

This is the whole "IAM roles, not static keys" story in two lines of code.
"""
import boto3

from app.config import AWS_REGION

session = boto3.Session(region_name=AWS_REGION)

bedrock = session.client("bedrock-runtime")
s3 = session.client("s3")
logs = session.client("logs")
