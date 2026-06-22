"""
CloudWatch log stream initialization.

The log GROUP is created by CloudFormation (infra/cloudformation.yaml). The
STREAM must be created by the app at startup; put_log_events raises
ResourceNotFoundException otherwise. logs:CreateLogStream is already in the IAM
policy. Audit logging is observability, not a hard dependency for answering
questions, so failures here warn rather than crash the app.

Note: AWS removed the sequenceToken requirement for put_log_events in 2023, so
the audit-log call in rag_chain does not pass one - the stream just has to exist.
"""
import logging

from botocore.exceptions import ClientError

from app.aws_clients import logs
from app.config import CLOUDWATCH_LOG_GROUP, CLOUDWATCH_LOG_STREAM

logger = logging.getLogger(__name__)


def ensure_log_stream() -> None:
    """Create the CloudWatch log stream if it doesn't already exist (idempotent)."""
    try:
        logs.create_log_stream(
            logGroupName=CLOUDWATCH_LOG_GROUP, logStreamName=CLOUDWATCH_LOG_STREAM
        )
        logger.info(
            "CloudWatch log stream created: %s/%s",
            CLOUDWATCH_LOG_GROUP,
            CLOUDWATCH_LOG_STREAM,
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ResourceAlreadyExistsException":
            pass  # normal on every restart except the first
        else:
            logger.warning("Could not create log stream: %s", exc)
