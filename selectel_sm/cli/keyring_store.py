"""The only module that touches secrets at rest.

Per the design's hard invariant, the service-user password and the cached token live **only** in
the OS keyring (Keychain / libsecret / Windows Credential Manager) — never in the config file.

Two entries per profile, namespaced under the ``selectel-sm`` keyring service:

* ``<profile>:password`` — the service-user password.
* ``<profile>:token``    — a JSON blob ``{value, expires_at, sm_base_url}`` so later invocations
  reuse a still-valid token *and* skip re-resolving the Keystone catalog.

If no keyring backend is available (headless, no D-Bus, ...) we do **not** silently fall back to a
plaintext file — we raise a clear :class:`~selectel_sm.cli.errors.CLIError`. Callers that can
operate without persistence should use ``store = none`` instead.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import keyring
from keyring.errors import KeyringError, NoKeyringError

from selectel_sm.cli.errors import CLIError

if TYPE_CHECKING:
    from selectel_sm.models import Token

__all__ = ["CachedToken", "clear", "load_token", "read_password", "save_token", "write_password"]

SERVICE = "selectel-sm"


def _password_key(profile: str) -> str:
    return f"{profile}:password"


def _token_key(profile: str) -> str:
    return f"{profile}:token"


def _unavailable(exc: Exception) -> CLIError:
    return CLIError(
        "No usable keyring backend is available. Use a profile with store='none' "
        "(credentials via env/prompt, nothing persisted) or run on a machine with a keyring. "
        f"({exc})",
        exit_code=1,
    )


@dataclass(frozen=True, slots=True)
class CachedToken:
    """A token cached in the keyring, with the metadata needed to reuse it offline."""

    value: str
    expires_at: datetime
    sm_base_url: str

    def is_fresh(self, *, margin_seconds: float) -> bool:
        """Whether the token is still valid, treating it as expired *margin_seconds* early."""
        remaining = (self.expires_at - datetime.now(UTC)).total_seconds()
        return remaining > margin_seconds

    def to_json(self) -> str:
        return json.dumps(
            {
                "value": self.value,
                "expires_at": self.expires_at.isoformat(),
                "sm_base_url": self.sm_base_url,
            }
        )

    @classmethod
    def from_json(cls, blob: str) -> CachedToken | None:
        try:
            data = json.loads(blob)
            return cls(
                value=data["value"],
                expires_at=datetime.fromisoformat(data["expires_at"]),
                sm_base_url=data["sm_base_url"],
            )
        except (ValueError, KeyError, TypeError):
            # A corrupt/legacy blob is treated as "no cache" — we just re-mint.
            return None


def _get(key: str) -> str | None:
    try:
        return keyring.get_password(SERVICE, key)
    except NoKeyringError as exc:
        raise _unavailable(exc) from exc
    except KeyringError as exc:
        raise CLIError(f"Keyring read failed: {exc}", exit_code=1) from exc


def _set(key: str, value: str) -> None:
    try:
        keyring.set_password(SERVICE, key, value)
    except NoKeyringError as exc:
        raise _unavailable(exc) from exc
    except KeyringError as exc:
        raise CLIError(f"Keyring write failed: {exc}", exit_code=1) from exc


def _delete(key: str) -> None:
    try:
        keyring.delete_password(SERVICE, key)
    except NoKeyringError as exc:
        raise _unavailable(exc) from exc
    except KeyringError:
        # Deleting a key that isn't there raises PasswordDeleteError; treat as already-absent.
        pass


def read_password(profile: str) -> str | None:
    return _get(_password_key(profile))


def write_password(profile: str, password: str) -> None:
    _set(_password_key(profile), password)


def load_token(profile: str) -> CachedToken | None:
    blob = _get(_token_key(profile))
    return CachedToken.from_json(blob) if blob else None


def save_token(profile: str, token: Token, sm_base_url: str) -> None:
    """Persist a freshly minted *token* plus its resolved SM endpoint."""
    cached = CachedToken(value=token.value, expires_at=token.expires_at, sm_base_url=sm_base_url)
    _set(_token_key(profile), cached.to_json())


def clear(profile: str) -> None:
    """Remove both secrets for *profile* (used by ``logout`` and ``profile remove``)."""
    _delete(_password_key(profile))
    _delete(_token_key(profile))
