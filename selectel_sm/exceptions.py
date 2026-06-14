"""
Exception hierarchy for selectel-sm.

All errors raised by this library derive from :class:`SelectelSMError`, so callers can catch
everything with a single ``except``. More specific subclasses let them react to particular
failure modes (auth, missing endpoint, HTTP status, transport).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import httpx

__all__ = [
    "APIError",
    "AuthenticationError",
    "BadRequestError",
    "ConflictError",
    "EndpointNotFoundError",
    "ForbiddenError",
    "NotFoundError",
    "SelectelSMError",
    "ServerError",
    "TransportError",
]


class SelectelSMError(Exception):
    """
    Base class for every error raised by selectel-sm.
    """


class AuthenticationError(SelectelSMError):
    """
    Raised when obtaining or introspecting an IAM token fails.
    """


class EndpointNotFoundError(SelectelSMError):
    """
    Raised when the service catalog has no endpoint for the requested region/interface.
    """

    def __init__(
        self,
        service_type: str,
        region: str,
        interface: str,
        available_regions: list[str],
    ) -> None:
        """
        :param service_type: The catalog service type that was searched.
        :param region: The requested region.
        :param interface: The requested interface (e.g. ``public``).
        :param available_regions: Regions that *do* exist for the service/interface.
        """
        self.service_type: str = service_type
        self.region: str = region
        self.interface: str = interface
        self.available_regions: list[str] = available_regions
        available = ", ".join(sorted(available_regions)) or "<none>"
        super().__init__(
            f"No '{service_type}' endpoint for region={region!r} interface={interface!r}. "
            f"Available regions: {available}."
        )


class TransportError(SelectelSMError):
    """
    Raised when the underlying HTTP transport fails (connection error, timeout, ...).
    """


class APIError(SelectelSMError):
    """
    Raised when the API returns an unexpected (non-success) HTTP status.

    Subclasses map to specific status codes; :func:`selectel_sm._core.errors.map_response`
    picks the right one. ``status_code`` is also kept for the base/unknown case.
    """

    status_code: int | None = None

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        response: httpx.Response | None = None,
    ) -> None:
        """
        :param message: Human-readable error message.
        :param status_code: The HTTP status code, when known.
        :param response: The originating response, when available.
        """
        if status_code is not None:
            self.status_code = status_code
        self.response: httpx.Response | None = response
        super().__init__(message)


class BadRequestError(APIError):
    """
    HTTP 400.
    """

    status_code = 400


class ForbiddenError(APIError):
    """
    HTTP 403.
    """

    status_code = 403


class NotFoundError(APIError):
    """
    HTTP 404.
    """

    status_code = 404


class ConflictError(APIError):
    """
    HTTP 409.
    """

    status_code = 409


class ServerError(APIError):
    """
    HTTP 5xx.
    """

    status_code = 500
