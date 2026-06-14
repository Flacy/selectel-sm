"""
Resolve the effective profile and build a configured client.

This is where flags, environment variables, the config file, and the keyring are combined into a
ready-to-use :class:`~selectel_sm.SecretsManagerClient`, following the precedence agreed in the
design:

* **profile selection:** ``--profile`` > ``SELECTEL_SM_PROFILE`` > ``default_profile`` > an
  implicit ephemeral profile synthesized from env (the zero-config CI/prod path);
* **field overrides:** every profile field can be overridden by its ``SELECTEL_SM_*`` env var;
* **persistence:** the profile's ``store`` policy, forced to ``none`` by ``--no-store`` /
  ``SELECTEL_SM_NO_STORE`` or when running non-interactively without a configured profile.

Token reuse goes through the keyring cache (:mod:`selectel_sm.cli.keyring_store`): a cached token
that is still fresh is used directly (skipping Keystone entirely); otherwise we mint a new one
from credentials and persist it (when the policy is ``keyring``) until its real ``expires_at``.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import httpx
import typer

from selectel_sm import SecretsManagerClient
from selectel_sm._transport import _common
from selectel_sm.auth._cache import DEFAULT_REFRESH_MARGIN_SECONDS
from selectel_sm.auth.password import PasswordAuth
from selectel_sm.cli import keyring_store
from selectel_sm.cli.config import STORE_KEYRING, STORE_NONE, Config, Profile
from selectel_sm.cli.errors import CLIError
from selectel_sm.config import DEFAULT_TIMEOUT, IDENTITY_URL_RU
from selectel_sm.config import Config as ClientConfig

if TYPE_CHECKING:
    from selectel_sm.models import Token

__all__ = ["AppState", "ResolvedProfile", "build_client", "mint_token", "resolve_profile"]

# Env var that names the active profile (its fields are overridden by the per-field vars below).
ENV_PROFILE: str = "SELECTEL_SM_PROFILE"
ENV_NO_STORE: str = "SELECTEL_SM_NO_STORE"
ENV_TOKEN: str = "SELECTEL_SM_TOKEN"
ENV_PASSWORD: str = "SELECTEL_SM_PASSWORD"
# Per-field overrides; keys are Profile attribute names.
ENV_FIELDS: dict[str, str] = {
    "region": "SELECTEL_SM_REGION",
    "account_id": "SELECTEL_SM_ACCOUNT_ID",
    "project_name": "SELECTEL_SM_PROJECT",
    "username": "SELECTEL_SM_USERNAME",
    "interface": "SELECTEL_SM_INTERFACE",
    "identity_url": "SELECTEL_SM_IDENTITY_URL",
}


@dataclass(slots=True)
class AppState:
    """
    Global flags from the root callback, shared with every command via the Typer context.
    """

    profile: str | None = None
    output: str = "table"
    no_color: bool = False
    quiet: bool = False
    no_store: bool = False
    config: Config = field(default_factory=Config)

    @property
    def json_output(self) -> bool:
        """
        Whether machine JSON output was requested (``-o json``).
        """
        return self.output == "json"


@dataclass(slots=True)
class ResolvedProfile:
    """
    The effective, merged connection context for one command invocation.
    """

    name: str
    region: str
    account_id: str | None
    project_name: str | None
    username: str | None
    interface: str
    identity_url: str
    sm_base_url: str | None
    store: str
    env_token: str | None
    ephemeral: bool

    @property
    def persists(self) -> bool:
        """
        Whether this profile's secrets are persisted in the keyring.
        """
        return self.store == STORE_KEYRING


def _env(name: str) -> str | None:
    """
    Return environment variable *name*, normalizing the empty string to ``None``.
    """
    value = os.environ.get(name)
    return value or None


def _resolve_name(state: AppState) -> str | None:
    """
    Pick the active profile name from flags, env, then the configured default.
    """
    return state.profile or _env(ENV_PROFILE) or state.config.default_profile


def _has_env_credentials() -> bool:
    """
    Whether the environment alone can authenticate (token, or username+password).
    """
    if _env(ENV_TOKEN):
        return True
    return bool(_env(ENV_PASSWORD) and _env(ENV_FIELDS["username"]))


def resolve_profile(state: AppState) -> ResolvedProfile:
    """
    Merge config + env into the effective profile for this invocation.

    :param state: Shared app state holding flags and the loaded config.
    :returns: The merged, ready-to-use profile.
    :raises CLIError: If a named profile is missing, or no profile is configured and the
        environment cannot stand in.
    """
    name = _resolve_name(state)
    profile = state.config.get(name) if name else None
    ephemeral = False

    if profile is None:
        if name is not None:
            raise CLIError(f"No such profile: {name!r}.", exit_code=4)
        elif not _has_env_credentials():
            raise CLIError(
                "No profile configured and no credentials in the environment. "
                "Run 'selectel-sm login' or set SELECTEL_SM_* variables.",
                exit_code=3,
            )
        # Zero-config path: synthesize an ephemeral, non-persisting profile from env.
        profile = Profile(name="(env)", store=STORE_NONE)
        ephemeral = True

    return _merge(profile, state, ephemeral=ephemeral)


def _merge(profile: Profile, state: AppState, *, ephemeral: bool) -> ResolvedProfile:
    """
    Apply env overrides on top of *profile* and resolve the persistence policy.

    :raises CLIError: If no region can be determined.
    """

    def pick(attr: str, default: str | None = None) -> str | None:
        return _env(ENV_FIELDS[attr]) or getattr(profile, attr) or default

    region = pick("region")
    if not region:
        raise CLIError(
            "No region set. Pass it via the profile, --region on login, or SELECTEL_SM_REGION.",
            exit_code=3,
        )

    # Two conditions, so a block per style rule 6 (SIM108 would prefer a ternary here).
    if state.no_store or _env(ENV_NO_STORE):  # noqa: SIM108
        store = STORE_NONE
    else:
        store = profile.store

    return ResolvedProfile(
        name=profile.name,
        region=region,
        account_id=pick("account_id"),
        project_name=pick("project_name"),
        username=pick("username"),
        interface=pick("interface", "public") or "public",
        identity_url=pick("identity_url", IDENTITY_URL_RU) or IDENTITY_URL_RU,
        sm_base_url=profile.sm_base_url,
        store=store,
        env_token=_env(ENV_TOKEN),
        ephemeral=ephemeral,
    )


def _client_config(resolved: ResolvedProfile) -> ClientConfig:
    """
    Build the library :class:`~selectel_sm.config.Config` from a resolved profile.
    """
    return ClientConfig(
        region=resolved.region,
        identity_url=resolved.identity_url,
        interface=resolved.interface,
        account_id=resolved.account_id,
        project_name=resolved.project_name,
        sm_base_url=resolved.sm_base_url,
        timeout=DEFAULT_TIMEOUT,
    )


def mint_token(resolved: ResolvedProfile, password: str) -> tuple[Token, str]:
    """
    Authenticate with credentials and resolve the SM endpoint (no client kept).

    Used both by ``login`` (to validate + persist) and by :func:`build_client` on the credential
    path.

    :param resolved: The merged profile providing the credential fields.
    :param password: The service-user password.
    :returns: The freshly minted token and its resolved Secrets Manager base URL.
    :raises CLIError: If required credential fields are missing.
    :raises AuthenticationError: If Keystone rejects the credentials.
    :raises TransportError: If Keystone cannot be reached.
    """
    missing = [
        label
        for label, value in (
            ("account_id", resolved.account_id),
            ("project_name", resolved.project_name),
            ("username", resolved.username),
        )
        if not value
    ]
    if missing:
        raise CLIError(f"Missing required credential fields: {', '.join(missing)}.", exit_code=3)

    config = _client_config(resolved)
    auth = PasswordAuth(
        identity_url=resolved.identity_url,
        account_id=resolved.account_id or "",
        username=resolved.username or "",
        password=password,
        project_name=resolved.project_name or "",
    )
    with httpx.Client(timeout=config.timeout, verify=config.verify) as client:
        token = auth.authenticate(client)
        endpoint = _common.resolve_base(token, config)
    return token, endpoint


def _resolve_password(resolved: ResolvedProfile) -> str:
    """
    Find the service-user password: keyring (if persisting) → env → interactive prompt.

    :raises CLIError: If no password is available and stdin is not a TTY.
    """
    if resolved.persists:
        stored = keyring_store.read_password(resolved.name)
        if stored is not None:
            return stored

    env_password = _env(ENV_PASSWORD)
    if env_password is not None:
        return env_password

    if not sys.stdin.isatty():
        raise CLIError(
            "No password available (not stored, not in SELECTEL_SM_PASSWORD, and stdin is not "
            "a TTY). Run 'selectel-sm login' or set SELECTEL_SM_PASSWORD.",
            exit_code=3,
        )
    return str(typer.prompt("Password", hide_input=True))


def build_client(resolved: ResolvedProfile) -> SecretsManagerClient:
    """
    Build a ready client, reusing a cached token when possible, minting otherwise.

    :param resolved: The merged profile for this invocation.
    :returns: A configured :class:`~selectel_sm.SecretsManagerClient`.
    :raises CLIError: If credentials/region are missing or the keyring is unavailable.
    :raises AuthenticationError: If minting a token from credentials fails.
    :raises TransportError: If Keystone cannot be reached.
    """
    # 1. An explicit token from the environment wins (the bring-your-own-token path).
    if resolved.env_token:
        if resolved.sm_base_url:
            return SecretsManagerClient.from_token(
                region=resolved.region,
                token=resolved.env_token,
                sm_base_url=resolved.sm_base_url,
                interface=resolved.interface,
            )
        return SecretsManagerClient.from_token(
            region=resolved.region,
            token=resolved.env_token,
            identity_url=resolved.identity_url,
            interface=resolved.interface,
        )

    # 2. A still-fresh cached token (keyring policy): use it directly, no Keystone round-trip.
    if resolved.persists:
        cached = keyring_store.load_token(resolved.name)
        if cached is not None and cached.is_fresh(margin_seconds=DEFAULT_REFRESH_MARGIN_SECONDS):
            return SecretsManagerClient.from_token(
                region=resolved.region,
                token=cached.value,
                sm_base_url=cached.sm_base_url,
                interface=resolved.interface,
            )

    # 3. Mint from credentials; persist the new token when the policy allows.
    password = _resolve_password(resolved)
    token, endpoint = mint_token(resolved, password)
    if resolved.persists:
        keyring_store.save_token(resolved.name, token, endpoint)
    return SecretsManagerClient.from_token(
        region=resolved.region,
        token=token.value,
        sm_base_url=endpoint,
        interface=resolved.interface,
    )
