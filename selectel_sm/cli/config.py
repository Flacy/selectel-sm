"""
Profile storage: the non-secret context that lives in a TOML config file.

The hard invariant: **no secret ever touches this file.**
Only non-confidential connection context is stored here — service-user password and cached token
live exclusively in the keyring (:mod:`selectel_sm.cli.keyring_store`).

Format is TOML (read with stdlib :mod:`tomllib`, written with ``tomli_w``), located via XDG at
``$XDG_CONFIG_HOME/selectel-sm/config.toml`` (default ``~/.config/selectel-sm/config.toml``).
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

import tomli_w

from selectel_sm.cli.errors import CLIError

__all__ = ["Config", "Profile", "config_path", "load_config"]

# Persistence policies a profile may declare. The middle "token-on-disk" mode was deliberately
# rejected during design — do not add it.
STORE_KEYRING: str = "keyring"
STORE_NONE: str = "none"
VALID_STORES: tuple[str, ...] = (STORE_KEYRING, STORE_NONE)


def config_path() -> Path:
    """
    Return the path to the config file, honoring ``XDG_CONFIG_HOME``.
    """
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "selectel-sm" / "config.toml"


@dataclass(slots=True)
class Profile:
    """
    One named profile's non-secret connection context.
    """

    name: str
    region: str | None = None
    account_id: str | None = None
    project_name: str | None = None
    username: str | None = None
    store: str = STORE_KEYRING
    interface: str = "public"
    identity_url: str | None = None
    sm_base_url: str | None = None

    # TOML keys that map to dataclass fields (``name`` is the table key, not a field in the body).
    _TOML_FIELDS: ClassVar[tuple[str, ...]] = (
        "region",
        "account_id",
        "project_name",
        "username",
        "store",
        "interface",
        "identity_url",
        "sm_base_url",
    )

    @classmethod
    def from_toml(cls, name: str, raw: dict[str, Any]) -> Profile:
        """
        Build a :class:`Profile` named *name* from a parsed TOML table body.
        """
        kwargs: dict[str, Any] = {"name": name}
        for key in cls._TOML_FIELDS:
            if key in raw:
                kwargs[key] = raw[key]
        return cls(**kwargs)

    def to_toml(self) -> dict[str, Any]:
        """
        Serialize to a TOML table body (omitting unset optional fields).
        """
        body: dict[str, Any] = {}
        for key in self._TOML_FIELDS:
            value = getattr(self, key)
            if value is not None:
                body[key] = value
        return body


@dataclass(slots=True)
class Config:
    """
    The whole config file: a default-profile pointer plus named profiles.
    """

    default_profile: str | None = None
    profiles: dict[str, Profile] = field(default_factory=dict)

    def get(self, name: str) -> Profile | None:
        """
        Return the profile named *name*, or ``None`` when it is not configured.
        """
        return self.profiles.get(name)

    def require(self, name: str) -> Profile:
        """
        Return the profile named *name*, raising when it does not exist.

        :raises CLIError: If no profile named *name* is configured (exit code 4).
        """
        profile = self.profiles.get(name)
        if profile is None:
            raise CLIError(f"No such profile: {name!r}.", exit_code=4)
        return profile

    def upsert(self, profile: Profile) -> None:
        """
        Insert or replace *profile* by its name.
        """
        self.profiles[profile.name] = profile

    def remove(self, name: str) -> None:
        """
        Remove the profile named *name*, clearing the default pointer if it matched.
        """
        self.profiles.pop(name, None)
        if self.default_profile == name:
            self.default_profile = None

    def save(self, path: Path | None = None) -> None:
        """
        Write the config to *path* (default :func:`config_path`) with ``0600`` permissions.
        """
        path = path or config_path()
        path.parent.mkdir(parents=True, exist_ok=True)

        document: dict[str, Any] = {}
        if self.default_profile is not None:
            document["default_profile"] = self.default_profile
        if self.profiles:
            document["profiles"] = {
                name: profile.to_toml() for name, profile in self.profiles.items()
            }

        # Config dir may hold a token-less file; still 0600 it since it names users/projects.
        path.write_text(tomli_w.dumps(document), encoding="utf-8")
        path.chmod(0o600)


def load_config(path: Path | None = None) -> Config:
    """
    Load the config file, returning an empty :class:`Config` when it does not exist.

    :param path: Config file path; defaults to :func:`config_path`.
    :returns: The parsed config (empty when the file is absent).
    :raises CLIError: If the file exists but cannot be read or parsed.
    """
    path = path or config_path()
    if not path.exists():
        return Config()

    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise CLIError(f"Failed to read config at {path}: {exc}", exit_code=1) from exc

    profiles = {
        name: Profile.from_toml(name, body) for name, body in (raw.get("profiles") or {}).items()
    }
    return Config(default_profile=raw.get("default_profile"), profiles=profiles)
