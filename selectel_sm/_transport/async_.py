"""
Asynchronous HTTP transport (mirror of :mod:`selectel_sm._transport.sync`).
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

__all__ = ["AsyncTransport"]


class AsyncTransport:
    """
    Async counterpart of :class:`~selectel_sm._transport.sync.SyncTransport`.
    """

    def __init__(
        self,
        config: Config,
        auth: AuthProvider,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._config: Config = config
        self._auth: AuthProvider = auth
        self._client: httpx.AsyncClient = client or httpx.AsyncClient(
            timeout=config.timeout, verify=config.verify
        )
        self._base: str | None = None

    async def __aenter__(self) -> AsyncTransport:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def send(self, spec: RequestSpec) -> httpx.Response:
        """
        Execute *spec* and return the raw response, raising on an unexpected status.
        """
        token = await self._auth.aauthenticate(self._client)
        if self._base is None:
            self._base = _common.resolve_base(token, self._config)

        prepared = _common.prepare(spec, self._base, token)
        try:
            response = await self._client.request(
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

    async def aclose(self) -> None:
        """
        Close the underlying async httpx client.
        """
        await self._client.aclose()
