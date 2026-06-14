"""
Synchronous HTTP transport.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

from selectel_sm._core import errors
from selectel_sm._transport import _common
from selectel_sm.exceptions import TransportError

if TYPE_CHECKING:
    from types import TracebackType

    from selectel_sm._core.request import RequestSpec
    from selectel_sm.auth.base import AuthProvider
    from selectel_sm.config import Config

__all__ = ["SyncTransport"]


class SyncTransport:
    """
    Sends :class:`RequestSpec`s against Secrets Manager using a blocking httpx client.

    The base URL is resolved from the auth token's catalog on first use (or taken from
    ``config.sm_base_url``) and cached for the transport's lifetime.
    """

    def __init__(
        self,
        config: Config,
        auth: AuthProvider,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        self._config: Config = config
        self._auth: AuthProvider = auth
        self._client: httpx.Client = client or httpx.Client(
            timeout=config.timeout, verify=config.verify
        )
        self._base: str | None = None

    def __enter__(self) -> SyncTransport:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def send(self, spec: RequestSpec) -> httpx.Response:
        """
        Execute *spec* and return the raw response, raising on an unexpected status.
        """
        token = self._auth.authenticate(self._client)
        if self._base is None:
            self._base = _common.resolve_base(token, self._config)

        prepared = _common.prepare(spec, self._base, token)
        try:
            response = self._client.request(
                prepared.method,
                prepared.url,
                params=prepared.params,
                json=prepared.json,
                headers=prepared.headers,
            )
        except httpx.HTTPError as exc:
            raise TransportError(f"Request to {prepared.url} failed: {exc}") from exc
        errors.raise_for_status(response, spec.expected_status)
        return response

    def close(self) -> None:
        """
        Close the underlying httpx client.
        """
        self._client.close()
