"""Parsing for the ISO-8601 timestamps Selectel returns.

Selectel emits timestamps in a couple of shapes — with microseconds and a ``Z`` suffix
(``2026-06-13T02:03:58.000000Z``, Keystone) and without (``2026-06-11T18:03:55Z``, Secrets
Manager). Both are handled here and normalized to aware UTC.
"""

from __future__ import annotations

from datetime import UTC, datetime

__all__ = ["parse", "parse_optional"]


def parse(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def parse_optional(value: str | None) -> datetime | None:
    return parse(value) if value else None
