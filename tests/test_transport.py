from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
import pytest
from assertpy import assert_that

from selectel_sm._core.request import RequestSpec
from selectel_sm._transport.async_ import AsyncTransport
from selectel_sm._transport.sync import SyncTransport
from selectel_sm.config import Config
from selectel_sm.exceptions import (
    BadRequestError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ServerError,
)
from tests.conftest import FakeAuth

if TYPE_CHECKING:
    from collections.abc import Callable

    from selectel_sm.models import Token

    Handler = Callable[[httpx.Request], httpx.Response]

SM_URL = "https://cloud.api.selcloud.ru/secrets-manager/v1/my-secret"


def _config(**overrides: object) -> Config:
    return Config(region="ru-7", **overrides)  # type: ignore[arg-type]


def _sync(token: Token, handler: Handler, **cfg: object) -> SyncTransport:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return SyncTransport(_config(**cfg), FakeAuth(token), client=client)


def _async(token: Token, handler: Handler, **cfg: object) -> AsyncTransport:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return AsyncTransport(_config(**cfg), FakeAuth(token), client=client)


def _ok_handler(captured: list[httpx.Request]) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"ok": True})

    return handler


def test_resolves_base_from_catalog_and_sends(token: Token) -> None:
    captured: list[httpx.Request] = []
    with _sync(token, _ok_handler(captured)) as transport:
        response = transport.send(RequestSpec("GET", "my-secret"))
    assert_that(response.status_code).is_equal_to(200)
    request = captured[0]
    assert_that(str(request.url)).is_equal_to(SM_URL)
    assert_that(request.headers["X-Auth-Token"]).is_equal_to(token.value)


def test_sm_base_url_override_bypasses_catalog(token: Token) -> None:
    captured: list[httpx.Request] = []
    handler = _ok_handler(captured)
    with _sync(token, handler, sm_base_url="https://override.example//secrets-manager/") as t:
        t.send(RequestSpec("GET", ""))
    assert_that(str(captured[0].url)).is_equal_to("https://override.example/secrets-manager/v1")


@pytest.mark.parametrize(
    ("status", "exc"),
    [
        (400, BadRequestError),
        (403, ForbiddenError),
        (404, NotFoundError),
        (409, ConflictError),
        (500, ServerError),
        (503, ServerError),
    ],
)
def test_status_mapping(token: Token, status: int, exc: type[Exception]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"message": "boom"})

    with _sync(token, handler) as transport, pytest.raises(exc):
        transport.send(RequestSpec("GET", "x"))


def test_expected_status_not_raised(token: Token) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    with _sync(token, handler) as transport:
        response = transport.send(RequestSpec("GET", "x", expected_status=(200, 404)))
    assert_that(response.status_code).is_equal_to(404)


@pytest.mark.asyncio
async def test_async_transport_parity(token: Token) -> None:
    captured: list[httpx.Request] = []
    async with _async(token, _ok_handler(captured)) as transport:
        response = await transport.send(RequestSpec("GET", "my-secret"))
    assert_that(response.status_code).is_equal_to(200)
    assert_that(str(captured[0].url)).is_equal_to(SM_URL)
    assert_that(captured[0].headers["X-Auth-Token"]).is_equal_to(token.value)
