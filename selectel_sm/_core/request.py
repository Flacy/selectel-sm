"""Transport-agnostic description of an HTTP request.

A :class:`RequestSpec` is a pure-data description of a single Secrets Manager call. The sync and
async transports both know how to execute one, so the (future) SM operations can be written once
as functions that build a ``RequestSpec`` and parse the response — with no sync/async
duplication.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

__all__ = ["RequestSpec"]

# Status codes treated as success when an operation doesn't specify its own.
DEFAULT_EXPECTED_STATUS: tuple[int, ...] = (200, 201, 204)


@dataclass(frozen=True, slots=True)
class RequestSpec:
    """A single HTTP call against the Secrets Manager API.

    ``path`` is relative to the resolved, version-prefixed base URL (e.g. ``"my-secret"`` or
    ``"my-secret/versions"``); the transport joins it onto ``<sm_base>/<api_version>``.

    ``trailing_slash`` requests a trailing ``/`` on the final URL path. Some endpoints are
    picky: the root listing only works as ``/v1/?list=true`` and 404s without the slash.
    """

    method: str
    path: str = ""
    params: Mapping[str, Any] | None = None
    json: Any | None = None
    expected_status: Sequence[int] = field(default=DEFAULT_EXPECTED_STATUS)
    trailing_slash: bool = False
