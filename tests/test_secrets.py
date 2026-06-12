from __future__ import annotations

import json
from typing import TYPE_CHECKING

import httpx
import pytest
from assertpy import assert_that

from selectel_sm import SecretsManagerClient
from selectel_sm._core import encoding
from selectel_sm.aclient import AsyncSecretsManagerClient
from selectel_sm.config import Config
from selectel_sm.exceptions import NotFoundError, SelectelSMError
from selectel_sm.resources import secrets
from selectel_sm.resources.models import SecretType
from tests.conftest import FakeAuth

CREATED_AT = "2026-06-11T18:03:55Z"

if TYPE_CHECKING:
    from collections.abc import Callable

    from selectel_sm.models import Token

    Handler = Callable[[httpx.Request], httpx.Response]


def _config() -> Config:
    return Config(region="ru-7")


def _sync_client(token: Token, handler: Handler) -> SecretsManagerClient:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return SecretsManagerClient(_config(), FakeAuth(token), client=client)


def _async_client(token: Token, handler: Handler) -> AsyncSecretsManagerClient:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return AsyncSecretsManagerClient(_config(), FakeAuth(token), client=client)


# --- pure operation tests -----------------------------------------------------------------


def test_build_get_uses_name_as_single_segment() -> None:
    spec = secrets.build_get("my-secret")
    assert_that(spec.method).is_equal_to("GET")
    assert_that(spec.path).is_equal_to("my-secret")


def test_build_get_quotes_reserved_characters() -> None:
    spec = secrets.build_get("a/b c")
    assert_that(spec.path).is_equal_to("a%2Fb%20c")


def _secret_body(value: bytes, **extra: object) -> dict[str, object]:
    """A response body shaped like the real Get-secret response."""
    return {
        "name": "database_password",
        "description": "PostgreSQL cluster password",
        "version": {
            "version_id": 1,
            "created_at": "2026-06-11T18:03:55Z",
            "is_current": True,
            "value": encoding.encode_value(value),
        },
        "created_at": "2026-06-11T18:03:55Z",
        **extra,
    }


def test_parse_secret_decodes_nested_version_value() -> None:
    body = _secret_body(b"s3cr3t")
    secret = secrets.parse_secret("requested-name", body)
    # The body's own name wins over the requested name.
    assert_that(secret.name).is_equal_to("database_password")
    assert_that(secret.description).is_equal_to("PostgreSQL cluster password")
    assert_that(secret.value).is_equal_to(b"s3cr3t")
    assert_that(secret.created_at).is_not_none()
    assert_that(secret.raw).is_equal_to(body)


def test_parse_secret_version_metadata() -> None:
    secret = secrets.parse_secret("n", _secret_body(b"x"))
    assert_that(secret.version).is_not_none()
    assert secret.version is not None  # narrow for the type checker
    assert_that(secret.version.version_id).is_equal_to(1)
    assert_that(secret.version.is_current).is_true()
    assert_that(secret.version.value).is_equal_to(b"x")


def test_parse_secret_falls_back_to_requested_name() -> None:
    secret = secrets.parse_secret(
        "requested", {"description": "no name field", "created_at": CREATED_AT}
    )
    assert_that(secret.name).is_equal_to("requested")


def test_parse_secret_without_version() -> None:
    body = {"name": "m", "description": "meta only", "created_at": CREATED_AT}
    secret = secrets.parse_secret("m", body)
    assert_that(secret.version).is_none()
    assert_that(secret.value).is_none()


def test_parse_secret_invalid_base64_raises() -> None:
    body = {
        "name": "m",
        "created_at": CREATED_AT,
        "version": {
            "version_id": 1,
            "created_at": CREATED_AT,
            "is_current": True,
            "value": "!!!not-base64!!!",
        },
    }
    with pytest.raises(SelectelSMError):
        secrets.parse_secret("m", body)


# --- client integration tests -------------------------------------------------------------


def test_client_get_secret(token: Token) -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=_secret_body(b"hunter2"))

    with _sync_client(token, handler) as client:
        secret = client.secrets.get("db-password")

    assert_that(secret.value).is_equal_to(b"hunter2")
    assert_that(str(captured[0].url)).is_equal_to(
        "https://cloud.api.selcloud.ru/secrets-manager/v1/db-password"
    )
    assert_that(captured[0].method).is_equal_to("GET")


def test_client_get_missing_secret_raises_not_found(token: Token) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "not found"})

    with _sync_client(token, handler) as client, pytest.raises(NotFoundError):
        client.secrets.get("missing")


@pytest.mark.asyncio
async def test_async_client_get_secret(token: Token) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_secret_body(b"async-secret"))

    async with _async_client(token, handler) as client:
        secret = await client.secrets.get("db-password")

    assert_that(secret.value).is_equal_to(b"async-secret")


# --- create -------------------------------------------------------------------------------


def test_build_create_base64_encodes_value() -> None:
    spec = secrets.build_create("my-secret", "hunter2", description="db")
    assert_that(spec.method).is_equal_to("POST")
    assert_that(spec.path).is_equal_to("my-secret")
    assert_that(spec.json).is_equal_to(
        {"value": encoding.encode_value("hunter2"), "description": "db"}
    )


def test_build_create_accepts_bytes() -> None:
    spec = secrets.build_create("s", b"\x00\x01\x02")
    assert_that(spec.json).is_equal_to({"value": encoding.encode_value(b"\x00\x01\x02")})


def test_build_create_omits_description_when_none() -> None:
    spec = secrets.build_create("s", "v")
    assert_that(spec.json).does_not_contain_key("description")


def test_client_create_secret(token: Token) -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=_secret_body(b"hunter2"))

    with _sync_client(token, handler) as client:
        secret = client.secrets.create("test", "hunter2", description="db")

    assert_that(secret.value).is_equal_to(b"hunter2")
    request = captured[0]
    assert_that(request.method).is_equal_to("POST")
    assert_that(str(request.url)).is_equal_to(
        "https://cloud.api.selcloud.ru/secrets-manager/v1/test"
    )
    # The value reaches the API base64-encoded, not as plain text.
    assert_that(json.loads(request.content)).is_equal_to(
        {"value": "aHVudGVyMg==", "description": "db"}
    )


@pytest.mark.asyncio
async def test_async_client_create_secret(token: Token) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_secret_body(b"x"))

    async with _async_client(token, handler) as client:
        secret = await client.secrets.create("test", "x")

    assert_that(secret.value).is_equal_to(b"x")


# --- update description -------------------------------------------------------------------


def test_build_update_description() -> None:
    spec = secrets.build_update_description("my-secret", "new desc")
    assert_that(spec.method).is_equal_to("PUT")
    assert_that(spec.path).is_equal_to("my-secret")
    assert_that(spec.json).is_equal_to({"description": "new desc"})


def test_build_update_description_none_clears() -> None:
    spec = secrets.build_update_description("s", None)
    # The key is always present (None clears the description).
    assert_that(spec.json).is_equal_to({"description": None})


def test_client_update_description(token: Token) -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(204)

    with _sync_client(token, handler) as client:
        result = client.secrets.update_description("test", "updated")

    assert_that(result).is_none()
    request = captured[0]
    assert_that(request.method).is_equal_to("PUT")
    assert_that(str(request.url)).is_equal_to(
        "https://cloud.api.selcloud.ru/secrets-manager/v1/test"
    )
    assert_that(json.loads(request.content)).is_equal_to({"description": "updated"})


@pytest.mark.asyncio
async def test_async_client_update_description(token: Token) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(204)

    async with _async_client(token, handler) as client:
        result = await client.secrets.update_description("test", None)

    assert_that(result).is_none()


# --- list ---------------------------------------------------------------------------------

# Representative listing body (real shape, fake names — see response-list.json for the source).
_LIST_BODY = {
    "keys": [
        {
            "name": "alpha",
            "type": "Secret",
            "metadata": {"description": "first", "created_at": "2026-06-11T18:03:55Z"},
        },
        {
            "name": "beta",
            "type": "Secret",
            "metadata": {"description": "second", "created_at": "2026-06-11T18:10:29Z"},
        },
    ]
}


def test_build_list_sends_list_flag() -> None:
    spec = secrets.build_list()
    assert_that(spec.method).is_equal_to("GET")
    assert_that(spec.path).is_equal_to("")
    assert_that(spec.params).is_equal_to({"list": "true"})
    # The root listing 404s without a trailing slash.
    assert_that(spec.trailing_slash).is_true()


def test_parse_list_flattens_metadata() -> None:
    summaries = secrets.parse_list(_LIST_BODY)
    assert_that(summaries).is_length(2)
    first = summaries[0]
    assert_that(first.name).is_equal_to("alpha")
    assert_that(first.type).is_equal_to(SecretType.SECRET)
    assert_that(first.description).is_equal_to("first")
    assert_that(first.created_at).is_not_none()
    assert_that(first.raw).is_equal_to(_LIST_BODY["keys"][0])


def test_parse_list_empty() -> None:
    assert_that(secrets.parse_list({})).is_empty()
    assert_that(secrets.parse_list({"keys": []})).is_empty()


def test_empty_description_becomes_none() -> None:
    # The API returns "" for secrets created without a description.
    summary_body = {
        "keys": [
            {
                "name": "test",
                "type": "Secret",
                "metadata": {"description": "", "created_at": CREATED_AT},
            }
        ]
    }
    assert_that(secrets.parse_list(summary_body)[0].description).is_none()

    secret_body = {"name": "test", "description": "", "created_at": CREATED_AT}
    assert_that(secrets.parse_secret("test", secret_body).description).is_none()


def test_parse_list_unknown_type_raises() -> None:
    body = {"keys": [{"name": "x", "type": "Certificate", "metadata": {"created_at": CREATED_AT}}]}
    with pytest.raises(SelectelSMError):
        secrets.parse_list(body)


def test_secret_type_parse() -> None:
    assert_that(SecretType.parse("Secret")).is_equal_to(SecretType.SECRET)
    with pytest.raises(SelectelSMError):
        SecretType.parse("Nonexistent")


def test_client_list_secrets(token: Token) -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=_LIST_BODY)

    with _sync_client(token, handler) as client:
        summaries = client.secrets.list()

    assert_that([s.name for s in summaries]).is_equal_to(["alpha", "beta"])
    # Trailing slash before the query is required by the API.
    assert_that(str(captured[0].url)).is_equal_to(
        "https://cloud.api.selcloud.ru/secrets-manager/v1/?list=true"
    )


@pytest.mark.asyncio
async def test_async_client_list_secrets(token: Token) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_LIST_BODY)

    async with _async_client(token, handler) as client:
        summaries = await client.secrets.list()

    assert_that([s.name for s in summaries]).is_equal_to(["alpha", "beta"])


# --- get versions -------------------------------------------------------------------------

# Real shape: secret metadata + a versions list carrying NO value (metadata only).
_VERSIONS_BODY = {
    "name": "test",
    "description": "",
    "versions": [
        {"version_id": 2, "created_at": "2026-06-12T08:08:23Z", "is_current": False},
        {"version_id": 1, "created_at": "2026-06-12T08:01:43Z", "is_current": True},
    ],
    "created_at": "2026-06-12T08:01:43Z",
}


def test_build_get_versions_path() -> None:
    spec = secrets.build_get_versions("my-secret")
    assert_that(spec.method).is_equal_to("GET")
    assert_that(spec.path).is_equal_to("my-secret/versions")


def test_parse_secret_versions() -> None:
    result = secrets.parse_secret_versions("test", _VERSIONS_BODY)
    assert_that(result.name).is_equal_to("test")
    assert_that(result.description).is_none()  # "" normalized to None
    assert_that([v.version_id for v in result.versions]).is_equal_to([2, 1])
    # Versions in this listing carry no value.
    assert_that([v.value for v in result.versions]).is_equal_to([None, None])
    # The current version is found regardless of ordering.
    assert_that(result.current).is_not_none()
    assert result.current is not None  # narrow for the type checker
    assert_that(result.current.version_id).is_equal_to(1)


def test_client_get_versions(token: Token) -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=_VERSIONS_BODY)

    with _sync_client(token, handler) as client:
        result = client.secrets.get_versions("test")

    assert_that(result.versions).is_length(2)
    assert_that(str(captured[0].url)).is_equal_to(
        "https://cloud.api.selcloud.ru/secrets-manager/v1/test/versions"
    )


@pytest.mark.asyncio
async def test_async_client_get_versions(token: Token) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_VERSIONS_BODY)

    async with _async_client(token, handler) as client:
        result = await client.secrets.get_versions("test")

    assert_that(result.current).is_not_none()


# --- get version --------------------------------------------------------------------------

# Real shape: a single version including its value.
_VERSION_BODY = {
    "version_id": 1,
    "created_at": "2026-06-12T08:01:43Z",
    "is_current": True,
    "value": "dGVzdA==",  # "test"
}


def test_build_get_version_path() -> None:
    spec = secrets.build_get_version("my-secret", 3)
    assert_that(spec.method).is_equal_to("GET")
    assert_that(spec.path).is_equal_to("my-secret/versions/3")


def test_parse_version_decodes_value() -> None:
    version = secrets.parse_version(_VERSION_BODY)
    assert_that(version.version_id).is_equal_to(1)
    assert_that(version.is_current).is_true()
    assert_that(version.value).is_equal_to(b"test")


def test_client_get_version(token: Token) -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=_VERSION_BODY)

    with _sync_client(token, handler) as client:
        version = client.secrets.get_version("test", 1)

    assert_that(version.value).is_equal_to(b"test")
    assert_that(str(captured[0].url)).is_equal_to(
        "https://cloud.api.selcloud.ru/secrets-manager/v1/test/versions/1"
    )


@pytest.mark.asyncio
async def test_async_client_get_version(token: Token) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_VERSION_BODY)

    async with _async_client(token, handler) as client:
        version = await client.secrets.get_version("test", 1)

    assert_that(version.value).is_equal_to(b"test")


# --- create version -----------------------------------------------------------------------


def test_build_create_version_default_no_activate() -> None:
    spec = secrets.build_create_version("my-secret", "hunter2")
    assert_that(spec.method).is_equal_to("POST")
    assert_that(spec.path).is_equal_to("my-secret/versions")
    assert_that(spec.json).is_equal_to({"value": encoding.encode_value("hunter2")})
    assert_that(spec.params).is_none()


def test_build_create_version_activate_flag() -> None:
    spec = secrets.build_create_version("s", "v", activate=True)
    assert_that(spec.params).is_equal_to({"activate": "true"})


def test_client_create_version(token: Token) -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=_VERSION_BODY)

    with _sync_client(token, handler) as client:
        version = client.secrets.create_version("test", "hunter2", activate=True)

    assert_that(version.version_id).is_equal_to(1)
    request = captured[0]
    assert_that(request.method).is_equal_to("POST")
    assert_that(str(request.url)).is_equal_to(
        "https://cloud.api.selcloud.ru/secrets-manager/v1/test/versions?activate=true"
    )
    assert_that(json.loads(request.content)).is_equal_to({"value": "aHVudGVyMg=="})


@pytest.mark.asyncio
async def test_async_client_create_version(token: Token) -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=_VERSION_BODY)

    async with _async_client(token, handler) as client:
        version = await client.secrets.create_version("test", "x")

    assert_that(version.value).is_equal_to(b"test")
    # No activate flag by default.
    assert_that(str(captured[0].url)).is_equal_to(
        "https://cloud.api.selcloud.ru/secrets-manager/v1/test/versions"
    )


# --- activate version ---------------------------------------------------------------------

# Real shape (docs claim 204/no body): 200 + version metadata, NO value.
_ACTIVATE_BODY = {
    "version_id": 1,
    "created_at": "2026-06-12T08:30:24Z",
    "is_current": True,
}


def test_build_activate_version_path() -> None:
    spec = secrets.build_activate_version("my-secret", 2)
    assert_that(spec.method).is_equal_to("POST")
    assert_that(spec.path).is_equal_to("my-secret/versions/2/activate")


def test_client_activate_version(token: Token) -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=_ACTIVATE_BODY)

    with _sync_client(token, handler) as client:
        version = client.secrets.activate_version("test", 1)

    assert_that(version.version_id).is_equal_to(1)
    assert_that(version.is_current).is_true()
    assert_that(version.value).is_none()  # activate response carries no value
    request = captured[0]
    assert_that(request.method).is_equal_to("POST")
    assert_that(str(request.url)).is_equal_to(
        "https://cloud.api.selcloud.ru/secrets-manager/v1/test/versions/1/activate"
    )


@pytest.mark.asyncio
async def test_async_client_activate_version(token: Token) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_ACTIVATE_BODY)

    async with _async_client(token, handler) as client:
        version = await client.secrets.activate_version("test", 1)

    assert_that(version.is_current).is_true()
    assert_that(version.value).is_none()


# --- delete -------------------------------------------------------------------------------


def test_build_delete_path() -> None:
    spec = secrets.build_delete("my-secret")
    assert_that(spec.method).is_equal_to("DELETE")
    assert_that(spec.path).is_equal_to("my-secret")


def test_client_delete_secret(token: Token) -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(204)

    with _sync_client(token, handler) as client:
        result = client.secrets.delete("test")

    assert_that(result).is_none()
    assert_that(captured[0].method).is_equal_to("DELETE")
    assert_that(str(captured[0].url)).is_equal_to(
        "https://cloud.api.selcloud.ru/secrets-manager/v1/test"
    )


def test_client_delete_missing_secret_raises_not_found(token: Token) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "not found"})

    with _sync_client(token, handler) as client, pytest.raises(NotFoundError):
        client.secrets.delete("missing")


@pytest.mark.asyncio
async def test_async_client_delete_secret(token: Token) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(204)

    async with _async_client(token, handler) as client:
        result = await client.secrets.delete("test")

    assert_that(result).is_none()
