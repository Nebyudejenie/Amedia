"""Webhook signature verification and signing."""
import hmac
import hashlib
import json
from typing import Union


def sign_payload(payload: Union[dict, bytes], secret: str) -> str:
    """
    Sign payload with HMAC-SHA256.

    Args:
        payload: Data to sign (dict or bytes)
        secret: Signing secret

    Returns:
        Signature in format: sha256=<hex>
    """
    if isinstance(payload, dict):
        payload = json.dumps(payload, sort_keys=True).encode()
    elif isinstance(payload, str):
        payload = payload.encode()

    signature = hmac.new(
        secret.encode(), payload, hashlib.sha256
    ).hexdigest()

    return f"sha256={signature}"


def verify_signature(
    payload: Union[dict, bytes, str],
    secret: str,
    signature: str,
) -> bool:
    """
    Verify webhook signature.

    Args:
        payload: Original payload (dict, bytes, or str)
        secret: Signing secret
        signature: Signature from webhook header (sha256=...)

    Returns:
        True if signature is valid
    """
    if isinstance(payload, dict):
        payload = json.dumps(payload, sort_keys=True).encode()
    elif isinstance(payload, str):
        payload = payload.encode()

    expected = sign_payload(payload, secret)

    return hmac.compare_digest(expected, signature)


def generate_secret() -> str:
    """Generate a random webhook secret."""
    import secrets
    return secrets.token_urlsafe(32)
