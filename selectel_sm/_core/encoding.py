"""
Base64 helpers for secret values.

Secrets Manager stores secret values base64-encoded on the wire. These helpers centralize the
encode/decode so every operation handles values the same way.
"""

from __future__ import annotations

import base64
import binascii

from selectel_sm.exceptions import SelectelSMError

__all__ = ["decode_value", "encode_value"]


def encode_value(value: bytes | str) -> str:
    """
    Base64-encode a secret value for sending to the API.
    """
    raw = value.encode() if isinstance(value, str) else value
    return base64.b64encode(raw).decode("ascii")


def decode_value(value: str) -> bytes:
    """
    Base64-decode a secret value received from the API.

    :raises SelectelSMError: If the API returns something that is not valid base64.
    """
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise SelectelSMError(f"Secret value is not valid base64: {exc}") from exc
