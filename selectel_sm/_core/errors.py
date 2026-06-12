"""Map HTTP responses to the library's exception hierarchy.

Shared by both transports so error handling is identical for sync and async.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from selectel_sm.exceptions import (
    APIError,
    BadRequestError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ServerError,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    import httpx

__all__ = ["raise_for_status"]

_STATUS_EXCEPTIONS: dict[int, type[APIError]] = {
    400: BadRequestError,
    403: ForbiddenError,
    404: NotFoundError,
    409: ConflictError,
}


def _message(response: httpx.Response) -> str:
    """Best-effort human-readable message from a response body."""
    try:
        body = response.json()
    except ValueError:
        text = response.text.strip()
        return text or f"HTTP {response.status_code}"
    if isinstance(body, dict):
        for key in ("message", "error", "detail"):
            value = body.get(key)
            if isinstance(value, str) and value:
                return value
    return f"HTTP {response.status_code}"


def raise_for_status(response: httpx.Response, expected: Sequence[int]) -> None:
    """Raise the appropriate :class:`APIError` subclass if *response* is not expected."""
    if response.status_code in expected:
        return
    message = _message(response)
    status = response.status_code
    exc_type: type[APIError]
    exc_type = ServerError if status >= 500 else _STATUS_EXCEPTIONS.get(status, APIError)
    raise exc_type(message, status_code=status, response=response)
