from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from assertpy import assert_that

from selectel_sm.exceptions import EndpointNotFoundError

if TYPE_CHECKING:
    from selectel_sm.models import Token


def test_resolves_and_normalizes_sm_endpoint(token: Token) -> None:
    url = token.catalog.endpoint_url("secrets-manager", "ru-7", "public")
    # Double slash collapsed, trailing slash stripped, /v1 NOT included.
    assert_that(url).is_equal_to("https://cloud.api.selcloud.ru/secrets-manager")


def test_unknown_region_raises_with_available(token: Token) -> None:
    with pytest.raises(EndpointNotFoundError) as exc_info:
        token.catalog.endpoint_url("secrets-manager", "ru-999", "public")
    assert_that(exc_info.value.available_regions).contains("ru-7", "ru-2")


def test_unknown_interface_raises(token: Token) -> None:
    with pytest.raises(EndpointNotFoundError):
        token.catalog.endpoint_url("secrets-manager", "ru-7", "internal")


def test_unknown_service_raises(token: Token) -> None:
    with pytest.raises(EndpointNotFoundError):
        token.catalog.endpoint_url("does-not-exist", "ru-7", "public")


def test_token_metadata(token: Token) -> None:
    assert_that(token.project.name).is_equal_to("test-project")
    assert_that(token.user.name).is_equal_to("test-user")
    assert_that([r.name for r in token.roles]).is_equal_to(["member"])
