"""Shared test fixtures and helpers (all I/O is mocked via httpx.MockTransport)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
import pytest

from selectel_sm._core import keystone
from selectel_sm.auth.base import AuthProvider
from selectel_sm.models import Token

if TYPE_CHECKING:
    from collections.abc import Callable

FIXTURES = Path(__file__).parent / "fixtures"

SUBJECT_TOKEN = "test-subject-token"


@pytest.fixture
def token_body() -> dict[str, Any]:
    """The sanitized Keystone token body (full catalog, fake identifiers)."""
    return json.loads((FIXTURES / "keystone_token.json").read_text())


@pytest.fixture
def token(token_body: dict[str, Any]) -> Token:
    return Token.from_response(SUBJECT_TOKEN, token_body)


def make_client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def make_async_client(
    handler: Callable[[httpx.Request], httpx.Response],
) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def keystone_handler(
    body: dict[str, Any],
    *,
    status: int = httpx.codes.CREATED,
    counter: list[int] | None = None,
) -> Callable[[httpx.Request], httpx.Response]:
    """A handler that answers Keystone auth/introspection requests with *body*."""

    def handler(request: httpx.Request) -> httpx.Response:
        if counter is not None:
            counter.append(1)
        return httpx.Response(
            status,
            headers={keystone.SUBJECT_TOKEN_HEADER: SUBJECT_TOKEN},
            json=body,
        )

    return handler


class FakeAuth(AuthProvider):
    """An auth provider that returns a pre-built token without any network call."""

    def __init__(self, token: Token) -> None:
        super().__init__()
        self._token = token
        self.fetches = 0

    def _fetch(self, client: httpx.Client) -> Token:
        self.fetches += 1
        return self._token

    async def _afetch(self, client: httpx.AsyncClient) -> Token:
        self.fetches += 1
        return self._token
