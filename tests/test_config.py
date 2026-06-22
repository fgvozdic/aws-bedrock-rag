"""Tests for app/config.py - the SSM SecureString fetch contract."""
from unittest.mock import MagicMock

import app.config as config


def test_get_qdrant_api_key_decrypts_via_ssm(monkeypatch):
    fake_ssm = MagicMock()
    fake_ssm.get_parameter.return_value = {"Parameter": {"Value": "secret-key"}}
    fake_boto3 = MagicMock()
    fake_boto3.client.return_value = fake_ssm
    monkeypatch.setattr(config, "boto3", fake_boto3, raising=False)
    # config imports boto3 lazily inside the function, so patch the module it pulls.
    import sys

    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)

    key = config.get_qdrant_api_key()

    assert key == "secret-key"
    # Must request KMS decryption and use the configured parameter name.
    _, kwargs = fake_ssm.get_parameter.call_args
    assert kwargs["WithDecryption"] is True
    assert kwargs["Name"] == config.QDRANT_API_KEY_PARAM
