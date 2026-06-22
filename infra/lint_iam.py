#!/usr/bin/env python3
"""Lint the rag-demo IAM policy with parliament (least-privilege analysis).

Uses parliament's Python API directly (not its CLI) so the check is portable and
not subject to the CLI's PATH / temp-file quirks.

Two wrinkles this wrapper handles so the check is honest and reproducible:

1. infra/iam-policy.json is the *published* artifact, so its ARNs are redacted
   with <ACCOUNT_ID> / <KMS_KEY_ID> placeholders. Parliament needs syntactically
   valid ARNs, so we substitute dummy-but-valid values before linting. Only the
   policy *structure* (actions, resource scoping, wildcards) is what gets checked.

2. Parliament's bundled IAM data does not recognise the Bedrock foundation-model
   resource ARN, because the model id legitimately contains a colon
   (e.g. ...claude-3-haiku-20240307-v1:0). It reports a RESOURCE_MISMATCH for
   bedrock:InvokeModel that is a FALSE POSITIVE — the ARN is valid and is exactly
   the intended least-privilege scoping. We drop that single finding by
   (issue + action); every other finding, at every severity, still fails the run.

Usage:  python infra/lint_iam.py [path/to/policy.json]
Exit 0 if no real findings remain, 1 otherwise.
"""
from __future__ import annotations

import pathlib
import sys
import warnings

DEFAULT_POLICY = pathlib.Path(__file__).resolve().parent / "iam-policy.json"
DUMMY_ACCOUNT = "123456789012"
DUMMY_KMS_KEY = "1234abcd-12ab-34cd-56ef-1234567890ab"


def is_known_false_positive(issue: str, detail: object) -> bool:
    """parliament can't match the foundation-model ARN (colon in the model id)."""
    return issue == "RESOURCE_MISMATCH" and "bedrock:InvokeModel" in str(detail)


def main() -> int:
    warnings.filterwarnings("ignore")  # silence pkg_resources deprecation notice
    from parliament import analyze_policy_string, enhance_finding

    policy_path = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_POLICY
    policy = policy_path.read_text(encoding="utf-8")
    policy = policy.replace("<ACCOUNT_ID>", DUMMY_ACCOUNT)
    policy = policy.replace("<KMS_KEY_ID>", DUMMY_KMS_KEY)

    result = analyze_policy_string(policy)
    remaining = []
    for finding in result.findings:
        finding = enhance_finding(finding)
        if not is_known_false_positive(finding.issue, finding.detail):
            remaining.append(finding)

    if remaining:
        print(f"parliament: {len(remaining)} finding(s) detected in {policy_path.name}\n")
        for finding in remaining:
            print(f"  {finding.severity} {finding.issue}: {finding.detail}")
        return 1

    print("parliament: clean (1 documented Bedrock false positive filtered)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
