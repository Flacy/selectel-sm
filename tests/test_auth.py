from __future__ import annotations

import copy
from typing import Any

import pytest
from assertpy import assert_that

from selectel_sm.auth.password import PasswordAuth
from selectel_sm.auth.static import StaticTokenAuth
from selectel_sm.exceptions import AuthenticationError
from tests.conftest import keystone_handler, make_async_client, make_client


def _body_expiring(token_body: dict[str, Any], expires_at: str) -> dict[str, Any]:
    body = copy.deepcopy(token_body)
    body["token"]["expires_at"] = expires_at
    return body


def _password_auth() -> PasswordAuth:
    return PasswordAuth(
        identity_url="https://identity.example/v3",
        account_id="000000",
        username="svc",
        password="secret",
        project_name="test-project",
    )


def test_password_auth_caches_token(token_body: dict[str, Any]) -> None:
    body = _body_expiring(token_body, "2099-01-01T00:00:00.000000Z")
    counter: list[int] = []
    auth = _password_auth()
    with make_client(keystone_handler(body, counter=counter)) as client:
        first = auth.authenticate(client)
        second = auth.authenticate(client)
    assert_that(first.value).is_equal_to(second.value)
    assert_that(len(counter)).is_equal_to(1)


def test_password_auth_refreshes_when_expired(token_body: dict[str, Any]) -> None:
    body = _body_expiring(token_body, "2000-01-01T00:00:00.000000Z")
    counter: list[int] = []
    auth = _password_auth()
    with make_client(keystone_handler(body, counter=counter)) as client:
        auth.authenticate(client)
        auth.authenticate(client)
    assert_that(len(counter)).is_equal_to(2)


def test_password_auth_non_201_raises(token_body: dict[str, Any]) -> None:
    auth = _password_auth()
    with (
        make_client(keystone_handler(token_body, status=401)) as client,
        pytest.raises(AuthenticationError),
    ):
        auth.authenticate(client)


@pytest.mark.asyncio
async def test_password_auth_async(token_body: dict[str, Any]) -> None:
    body = _body_expiring(token_body, "2099-01-01T00:00:00.000000Z")
    counter: list[int] = []
    auth = _password_auth()
    async with make_async_client(keystone_handler(body, counter=counter)) as client:
        await auth.aauthenticate(client)
        await auth.aauthenticate(client)
    assert_that(len(counter)).is_equal_to(1)


def test_static_token_synthetic_without_identity_url() -> None:
    auth = StaticTokenAuth("my-token")
    with make_client(keystone_handler({})) as client:
        token = auth.authenticate(client)
    assert_that(token.value).is_equal_to("my-token")
    assert_that(token.catalog.service("secrets-manager")).is_none()


def test_static_token_introspects_for_catalog(token_body: dict[str, Any]) -> None:
    auth = StaticTokenAuth("my-token", identity_url="https://identity.example/v3")
    counter: list[int] = []
    with make_client(keystone_handler(token_body, status=200, counter=counter)) as client:
        token = auth.authenticate(client)
    assert_that(token.value).is_equal_to("my-token")
    assert_that(token.catalog.service("secrets-manager")).is_not_none()
    assert_that(len(counter)).is_equal_to(1)


def test_static_token_introspection_failure_raises(token_body: dict[str, Any]) -> None:
    auth = StaticTokenAuth("my-token", identity_url="https://identity.example/v3")
    with (
        make_client(keystone_handler(token_body, status=401)) as client,
        pytest.raises(AuthenticationError),
    ):
        auth.authenticate(client)
