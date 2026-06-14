"""
The auth-provider contract and shared caching logic.

A provider turns credentials (or an existing token) into a fresh
:class:`~selectel_sm.models.Token`. It is handed the active httpx client so it can talk to
Keystone on the same connection pool instead of owning a client of its own.

Subclasses implement only ``_fetch`` / ``_afetch``; the caching and double-checked locking that
prevent redundant/concurrent token fetches live here.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from selectel_sm.auth._cache import TokenCache

if TYPE_CHECKING:
    import httpx

    from selectel_sm.models import Token

__all__ = ["AuthProvider"]


class AuthProvider(ABC):
    def __init__(self, *, cache: TokenCache | None = None) -> None:
        self._cache: TokenCache = cache or TokenCache()

    @abstractmethod
    def _fetch(self, client: httpx.Client) -> Token:
        """
        Obtain a fresh token synchronously (network I/O happens here).
        """

    @abstractmethod
    async def _afetch(self, client: httpx.AsyncClient) -> Token:
        """
        Obtain a fresh token asynchronously (network I/O happens here).
        """

    def authenticate(self, client: httpx.Client) -> Token:
        """
        Return a cached fresh token, fetching a new one if needed (thread-safe).

        A still-fresh cached token is returned without any network call. Otherwise the fetch is
        guarded by double-checked locking so concurrent callers mint at most one new token.

        :param client: The active httpx client used to reach Keystone when a fetch is needed.
        :returns: A token that is fresh (not within its refresh margin of expiry).
        :raises AuthenticationError: If Keystone rejects the credentials or returns a bad body.
        :raises TransportError: If Keystone cannot be reached.
        """
        fresh = self._cache.get_fresh()
        if fresh is not None:
            return fresh

        with self._cache.lock:
            fresh = self._cache.get_fresh()
            if fresh is not None:
                return fresh
            token = self._fetch(client)
            self._cache.set(token)
            return token

    async def aauthenticate(self, client: httpx.AsyncClient) -> Token:
        """
        Return a cached fresh token, fetching a new one if needed (async-safe).

        Async counterpart of :meth:`authenticate`; the cache fetch is guarded by an
        :class:`asyncio.Lock` so concurrent tasks mint at most one new token.

        :param client: The active async httpx client used to reach Keystone when a fetch is needed.
        :returns: A token that is fresh (not within its refresh margin of expiry).
        :raises AuthenticationError: If Keystone rejects the credentials or returns a bad body.
        :raises TransportError: If Keystone cannot be reached.
        """
        fresh = self._cache.get_fresh()
        if fresh is not None:
            return fresh

        async with self._cache.alock:
            fresh = self._cache.get_fresh()
            if fresh is not None:
                return fresh
            token = await self._afetch(client)
            self._cache.set(token)
            return token
