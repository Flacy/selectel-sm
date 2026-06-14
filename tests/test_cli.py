"""CLI tests — HTTP and keyring are mocked; no real network or OS keyring is touched.

Covers the behaviors the design calls out as load-bearing: value masking by default, ``--raw``
emitting bare bytes, value-never-positional, fail-closed confirmations, exit-code mapping, profile
precedence, the ``none`` vs ``keyring`` persistence policies, and the implicit ephemeral profile.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import httpx
import keyring
import pytest
from assertpy import assert_that
from keyring.backend import KeyringBackend
from keyring.errors import PasswordDeleteError
from typer.testing import CliRunner

from selectel_sm import SecretsManagerClient, __version__
from selectel_sm._core import encoding
from selectel_sm.cli import context, keyring_store, output
from selectel_sm.cli.app import app
from selectel_sm.cli.config import STORE_KEYRING, STORE_NONE, Config, Profile
from selectel_sm.cli.context import AppState, ResolvedProfile, build_client, resolve_profile
from selectel_sm.config import Config as ClientConfig
from selectel_sm.models import Token
from tests.conftest import FakeAuth

if TYPE_CHECKING:
    from collections.abc import Callable

    Handler = Callable[[httpx.Request], httpx.Response]

runner = CliRunner()


# --------------------------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------------------------- #


class _MemoryKeyring(KeyringBackend):
    """An in-memory keyring backend so tests never touch the real OS keyring."""

    priority = 1  # type: ignore[assignment]

    def __init__(self) -> None:
        super().__init__()
        self._store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self._store.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self._store[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        try:
            del self._store[(service, username)]
        except KeyError as exc:
            raise PasswordDeleteError("not set") from exc


@pytest.fixture(autouse=True)
def memory_keyring() -> object:
    """Install an in-memory keyring for every test; restore the real one afterwards."""
    previous = keyring.get_keyring()
    backend = _MemoryKeyring()
    keyring.set_keyring(backend)
    yield backend
    keyring.set_keyring(previous)


@pytest.fixture(autouse=True)
def isolated_config(tmp_path: object, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the config at a temp XDG dir so tests never read/write the user's config."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    # Clear any inherited credentials so resolution is deterministic.
    for var in (
        "SELECTEL_SM_PROFILE",
        "SELECTEL_SM_TOKEN",
        "SELECTEL_SM_PASSWORD",
        "SELECTEL_SM_REGION",
        "SELECTEL_SM_USERNAME",
        "SELECTEL_SM_ACCOUNT_ID",
        "SELECTEL_SM_PROJECT",
        "SELECTEL_SM_NO_STORE",
    ):
        monkeypatch.delenv(var, raising=False)


def _token() -> Token:
    return Token(
        value="tok",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        issued_at=None,
        project=None,
        user=None,
    )


def _secret_body(value: bytes) -> dict[str, object]:
    return {
        "name": "api_key",
        "description": "Third-party API key",
        "version": {
            "version_id": 3,
            "created_at": "2026-06-11T18:03:55Z",
            "is_current": True,
            "value": encoding.encode_value(value),
        },
        "created_at": "2026-06-11T18:03:55Z",
    }


def _patch_client(monkeypatch: pytest.MonkeyPatch, handler: Handler) -> None:
    """Replace build_client so secrets commands run against a MockTransport."""

    def factory(resolved: ResolvedProfile) -> SecretsManagerClient:
        http = httpx.Client(transport=httpx.MockTransport(handler))
        cfg = ClientConfig(region=resolved.region, sm_base_url="https://sm.example.com")
        return SecretsManagerClient(cfg, FakeAuth(_token()), client=http)

    monkeypatch.setattr("selectel_sm.cli.app.build_client", factory)


# Env that yields a valid ephemeral profile (so resolve_profile passes before build_client runs).
_ENV = {"SELECTEL_SM_TOKEN": "env-token", "SELECTEL_SM_REGION": "ru-7"}


def _ok(body: dict[str, object], status: int = 200) -> Handler:
    return lambda request: httpx.Response(status, json=body)


# --------------------------------------------------------------------------------------------- #
# Root / version
# --------------------------------------------------------------------------------------------- #


def test_root_version_flag() -> None:
    result = runner.invoke(app, ["--version"])
    assert_that(result.exit_code).is_equal_to(0)
    assert_that(result.stdout).contains(__version__)


def test_no_args_shows_help() -> None:
    result = runner.invoke(app, [])
    assert_that(result.output).contains("secrets")
    assert_that(result.output).contains("login")


# --------------------------------------------------------------------------------------------- #
# Value output: masking, --raw, --reveal, json
# --------------------------------------------------------------------------------------------- #


def test_get_masks_value_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_client(monkeypatch, _ok(_secret_body(b"s3cr3t")))
    result = runner.invoke(app, ["secrets", "get", "api_key"], env=_ENV)
    assert_that(result.exit_code).is_equal_to(0)
    assert_that(result.stdout).contains("••••••")
    assert_that(result.stdout).does_not_contain("s3cr3t")


def test_get_raw_emits_bytes_without_trailing_newline(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_client(monkeypatch, _ok(_secret_body(b"s3cr3t")))
    result = runner.invoke(app, ["secrets", "get", "api_key", "--raw"], env=_ENV)
    assert_that(result.exit_code).is_equal_to(0)
    assert_that(result.stdout_bytes).is_equal_to(b"s3cr3t")


def test_get_reveal_shows_value(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_client(monkeypatch, _ok(_secret_body(b"s3cr3t")))
    result = runner.invoke(app, ["secrets", "get", "api_key", "--reveal"], env=_ENV)
    assert_that(result.exit_code).is_equal_to(0)
    assert_that(result.stdout).contains("s3cr3t")


def test_get_json_masks_unless_reveal(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_client(monkeypatch, _ok(_secret_body(b"s3cr3t")))
    masked = runner.invoke(app, ["secrets", "get", "api_key", "-o", "json"], env=_ENV)
    assert_that(masked.exit_code).is_equal_to(0)
    assert_that(masked.stdout).does_not_contain("s3cr3t")
    assert_that(masked.stdout).does_not_contain("value")

    import base64

    revealed = runner.invoke(
        app, ["secrets", "get", "api_key", "-o", "json", "--reveal"], env=_ENV
    )
    assert_that(revealed.stdout).contains(base64.b64encode(b"s3cr3t").decode())


def test_raw_and_json_conflict(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_client(monkeypatch, _ok(_secret_body(b"x")))
    result = runner.invoke(app, ["secrets", "get", "api_key", "--raw", "-o", "json"], env=_ENV)
    assert_that(result.exit_code).is_equal_to(2)


# --------------------------------------------------------------------------------------------- #
# Date / duration formatting
# --------------------------------------------------------------------------------------------- #


def test_format_duration() -> None:
    assert_that(output.format_duration(86379)).is_equal_to("23h 59m 39s")
    assert_that(output.format_duration(59)).is_equal_to("59s")
    assert_that(output.format_duration(3600)).is_equal_to("1h")
    assert_that(output.format_duration(90061)).is_equal_to("1d 1h 1m 1s")
    assert_that(output.format_duration(0)).is_equal_to("expired")
    assert_that(output.format_duration(-5)).is_equal_to("expired")


def test_format_datetime_is_local_and_human_readable() -> None:
    dt = datetime(2026, 6, 11, 18, 3, 55, tzinfo=UTC)
    rendered = output.format_datetime(dt)
    assert_that(rendered).does_not_contain("T")
    # Local-time conversion + the agreed "%d %b %Y, %H:%M:%S" shape.
    assert_that(rendered).is_equal_to(dt.astimezone().strftime("%d %b %Y, %H:%M:%S"))


def test_get_table_uses_human_date_but_json_keeps_iso(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_client(monkeypatch, _ok(_secret_body(b"x")))
    table = runner.invoke(app, ["secrets", "get", "api_key"], env=_ENV)
    assert_that(table.stdout).contains("Jun 2026")
    assert_that(table.stdout).does_not_contain("2026-06-11T")

    js = runner.invoke(app, ["secrets", "get", "api_key", "-o", "json"], env=_ENV)
    assert_that(js.stdout).contains("2026-06-11T18:03:55")


# --------------------------------------------------------------------------------------------- #
# Value input: never positional
# --------------------------------------------------------------------------------------------- #


def test_create_value_is_not_positional(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_client(monkeypatch, _ok(_secret_body(b"x"), status=200))
    # A second positional (the value) must be rejected as a usage error.
    result = runner.invoke(app, ["secrets", "create", "api_key", "s3cr3t"], env=_ENV)
    assert_that(result.exit_code).is_equal_to(2)


def test_create_reads_value_from_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["content"] = request.content
        return httpx.Response(200, json=_secret_body(b"piped"))

    _patch_client(monkeypatch, handler)
    result = runner.invoke(
        app, ["secrets", "create", "api_key", "--stdin"], input="piped", env=_ENV
    )
    assert_that(result.exit_code).is_equal_to(0)
    assert_that(seen["content"]).contains(encoding.encode_value(b"piped").encode())


# --------------------------------------------------------------------------------------------- #
# Confirmations fail closed
# --------------------------------------------------------------------------------------------- #


def test_delete_without_yes_non_tty_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_client(monkeypatch, _ok({}, status=204))
    result = runner.invoke(app, ["secrets", "delete", "api_key"], env=_ENV)
    assert_that(result.exit_code).is_equal_to(2)
    assert_that(result.output).contains("--yes")


def test_delete_with_yes_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_client(monkeypatch, _ok({}, status=204))
    result = runner.invoke(app, ["secrets", "delete", "api_key", "--yes"], env=_ENV)
    assert_that(result.exit_code).is_equal_to(0)


# --------------------------------------------------------------------------------------------- #
# Exit-code mapping
# --------------------------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("status", "code"),
    [(404, 4), (403, 5), (409, 6), (400, 8), (500, 7)],
)
def test_exit_code_mapping(monkeypatch: pytest.MonkeyPatch, status: int, code: int) -> None:
    _patch_client(monkeypatch, _ok({"message": "boom"}, status=status))
    result = runner.invoke(app, ["secrets", "get", "api_key"], env=_ENV)
    assert_that(result.exit_code).is_equal_to(code)


# --------------------------------------------------------------------------------------------- #
# Profile precedence & resolution (unit level)
# --------------------------------------------------------------------------------------------- #


def _two_profiles() -> Config:
    return Config(
        default_profile="laptop",
        profiles={
            "laptop": Profile(name="laptop", region="ru-7", store=STORE_KEYRING),
            "prod": Profile(name="prod", region="ru-9", store=STORE_NONE),
        },
    )


def test_flag_beats_default() -> None:
    state = AppState(profile="prod", config=_two_profiles())
    assert_that(resolve_profile(state).name).is_equal_to("prod")


def test_env_profile_beats_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SELECTEL_SM_PROFILE", "prod")
    state = AppState(config=_two_profiles())
    assert_that(resolve_profile(state).name).is_equal_to("prod")


def test_default_profile_used() -> None:
    state = AppState(config=_two_profiles())
    assert_that(resolve_profile(state).name).is_equal_to("laptop")


def test_no_store_forces_none() -> None:
    state = AppState(config=_two_profiles(), no_store=True)
    assert_that(resolve_profile(state).store).is_equal_to(STORE_NONE)


def test_env_overrides_profile_field(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SELECTEL_SM_REGION", "ru-1")
    state = AppState(config=_two_profiles())
    assert_that(resolve_profile(state).region).is_equal_to("ru-1")


def test_implicit_ephemeral_profile_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SELECTEL_SM_TOKEN", "abc")
    monkeypatch.setenv("SELECTEL_SM_REGION", "ru-7")
    resolved = resolve_profile(AppState())
    assert_that(resolved.ephemeral).is_true()
    assert_that(resolved.store).is_equal_to(STORE_NONE)
    assert_that(resolved.env_token).is_equal_to("abc")


def test_no_profile_and_no_env_errors() -> None:
    from selectel_sm.cli.errors import CLIError

    with pytest.raises(CLIError) as caught:
        resolve_profile(AppState())
    assert_that(caught.value.exit_code).is_equal_to(3)


# --------------------------------------------------------------------------------------------- #
# Persistence policy: keyring vs none
# --------------------------------------------------------------------------------------------- #


def _credential_profile(store: str) -> ResolvedProfile:
    return ResolvedProfile(
        name="laptop",
        region="ru-7",
        account_id="123",
        project_name="proj",
        username="svc",
        interface="public",
        identity_url="https://identity",
        sm_base_url=None,
        store=store,
        env_token=None,
        ephemeral=False,
    )


def test_keyring_policy_persists_minted_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(context, "_resolve_password", lambda resolved: "pw")
    monkeypatch.setattr(context, "mint_token", lambda resolved, pw: (_token(), "https://sm"))
    build_client(_credential_profile(STORE_KEYRING)).close()
    cached = keyring_store.load_token("laptop")
    assert_that(cached).is_not_none()
    assert_that(cached.sm_base_url).is_equal_to("https://sm")  # type: ignore[union-attr]


def test_none_policy_persists_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(context, "_resolve_password", lambda resolved: "pw")
    monkeypatch.setattr(context, "mint_token", lambda resolved, pw: (_token(), "https://sm"))
    build_client(_credential_profile(STORE_NONE)).close()
    assert_that(keyring_store.load_token("laptop")).is_none()


def test_fresh_cached_token_is_reused(monkeypatch: pytest.MonkeyPatch) -> None:
    keyring_store.save_token("laptop", _token(), "https://sm")

    def fail(*args: object, **kwargs: object) -> object:
        raise AssertionError("should not mint when a fresh token is cached")

    monkeypatch.setattr(context, "mint_token", fail)
    build_client(_credential_profile(STORE_KEYRING)).close()  # must not raise


# --------------------------------------------------------------------------------------------- #
# Profiles + logout (config/keyring integration)
# --------------------------------------------------------------------------------------------- #


def test_profile_list_marks_default_and_creds() -> None:
    _two_profiles().save()
    keyring_store.write_password("laptop", "pw")
    result = runner.invoke(app, ["profile", "list"])
    assert_that(result.exit_code).is_equal_to(0)
    assert_that(result.stdout).contains("laptop")
    assert_that(result.stdout).contains("prod")


def test_logout_clears_only_secrets() -> None:
    _two_profiles().save()
    keyring_store.write_password("laptop", "pw")
    keyring_store.save_token("laptop", _token(), "https://sm")
    result = runner.invoke(app, ["logout", "--profile", "laptop"])
    assert_that(result.exit_code).is_equal_to(0)
    assert_that(keyring_store.read_password("laptop")).is_none()
    assert_that(keyring_store.load_token("laptop")).is_none()
    # Metadata is kept.
    from selectel_sm.cli.config import load_config

    assert_that(load_config().get("laptop")).is_not_none()
