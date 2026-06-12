from __future__ import annotations

import pytest
from assertpy import assert_that

from selectel_sm._core import encoding
from selectel_sm.exceptions import SelectelSMError


def test_encode_decode_roundtrip_bytes() -> None:
    assert_that(encoding.decode_value(encoding.encode_value(b"s3cr3t"))).is_equal_to(b"s3cr3t")


def test_encode_accepts_str() -> None:
    assert_that(encoding.encode_value("hello")).is_equal_to("aGVsbG8=")


def test_decode_rejects_invalid_base64() -> None:
    with pytest.raises(SelectelSMError):
        encoding.decode_value("not base64!!!")
