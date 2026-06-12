"""Public models for Secrets Manager resources.

Shared across resources (a :class:`Secret` embeds the current :class:`SecretVersion`, and the
versions resource returns the same ``SecretVersion``). Values arrive base64-encoded and are
decoded eagerly; the full payload is kept in ``raw`` so fields not yet modeled stay reachable.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from selectel_sm._core import encoding, timestamps
from selectel_sm.exceptions import SelectelSMError

if TYPE_CHECKING:
    from datetime import datetime

__all__ = [
    "Secret",
    "SecretSummary",
    "SecretType",
    "SecretVersion",
    "SecretWithVersions",
]


def _blank_to_none(value: str | None) -> str | None:
    """Treat the API's empty-string description as absent."""
    return value or None


class SecretType(StrEnum):
    """The ``type`` of an entry returned by listing.

    The API documentation is empty on this field, but in practice every entry is ``Secret``.
    We model it as a single-member enum on purpose: any other value the API might return raises
    instead of being silently accepted, so a new type surfaces loudly for us to handle.
    """

    SECRET = "Secret"

    @classmethod
    def parse(cls, value: str) -> SecretType:
        try:
            return cls(value)
        except ValueError as exc:
            known = ", ".join(repr(member.value) for member in cls)
            raise SelectelSMError(
                f"Unexpected secret type {value!r} (known types: {known})."
            ) from exc


@dataclass(frozen=True, slots=True)
class SecretVersion:
    """A single version of a secret.

    ``value`` is only returned by endpoints that expose the payload (get secret / get version);
    the versions listing returns metadata only, so ``value`` is ``None`` there.
    """

    version_id: int
    created_at: datetime
    is_current: bool
    value: bytes | None
    raw: dict[str, Any]

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> SecretVersion:
        encoded = raw.get("value")
        return cls(
            version_id=int(raw["version_id"]),
            created_at=timestamps.parse(raw["created_at"]),
            is_current=bool(raw["is_current"]),
            value=encoding.decode_value(encoded) if encoded is not None else None,
            raw=raw,
        )


@dataclass(frozen=True, slots=True)
class SecretSummary:
    """A lightweight secret entry as returned by listing (no value, no version).

    Listing wraps each secret's descriptive fields under a ``metadata`` block; this flattens the
    parts we model while keeping the whole entry in ``raw``.
    """

    name: str
    type: SecretType
    description: str | None
    created_at: datetime
    raw: dict[str, Any]

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> SecretSummary:
        metadata = raw.get("metadata") or {}
        return cls(
            name=raw["name"],
            type=SecretType.parse(raw["type"]),
            description=_blank_to_none(metadata.get("description")),
            created_at=timestamps.parse(metadata["created_at"]),
            raw=raw,
        )


@dataclass(frozen=True, slots=True)
class Secret:
    """A secret and the version returned alongside it (the current version on a plain GET)."""

    name: str
    description: str | None
    created_at: datetime
    version: SecretVersion | None
    raw: dict[str, Any]

    @property
    def value(self) -> bytes | None:
        """Convenience accessor for the embedded version's decoded value."""
        return self.version.value if self.version else None

    @classmethod
    def from_response(cls, name: str, body: dict[str, Any]) -> Secret:
        version = body.get("version")
        return cls(
            name=body.get("name") or name,
            description=_blank_to_none(body.get("description")),
            created_at=timestamps.parse(body["created_at"]),
            version=SecretVersion.from_raw(version) if version else None,
            raw=body,
        )


@dataclass(frozen=True, slots=True)
class SecretWithVersions:
    """A secret together with metadata for all of its versions (no values)."""

    name: str
    description: str | None
    created_at: datetime
    versions: tuple[SecretVersion, ...]
    raw: dict[str, Any]

    @property
    def current(self) -> SecretVersion | None:
        """The version flagged ``is_current``, if any."""
        return next((version for version in self.versions if version.is_current), None)

    @classmethod
    def from_response(cls, name: str, body: dict[str, Any]) -> SecretWithVersions:
        return cls(
            name=body.get("name") or name,
            description=_blank_to_none(body.get("description")),
            created_at=timestamps.parse(body["created_at"]),
            versions=tuple(SecretVersion.from_raw(v) for v in body.get("versions", [])),
            raw=body,
        )
