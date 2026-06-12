"""A small, lock-equipped holder for a cached :class:`~selectel_sm.models.Token`.

Holds both a :class:`threading.Lock` and an :class:`asyncio.Lock` so the same provider instance
can be used from sync and async code; the double-checked locking that uses them lives in
:class:`selectel_sm.auth.base.AuthProvider`.
"""

from __future__ import annotations

import asyncio
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from selectel_sm.models import Token

__all__ = ["DEFAULT_REFRESH_MARGIN_SECONDS", "TokenCache"]

# Refresh this many seconds before the token actually expires, to avoid using a token that
# lapses mid-request.
DEFAULT_REFRESH_MARGIN_SECONDS = 300.0


class TokenCache:
    def __init__(self, *, margin_seconds: float = DEFAULT_REFRESH_MARGIN_SECONDS) -> None:
        self._token: Token | None = None
        self._margin = margin_seconds
        self.lock = threading.Lock()
        self.alock = asyncio.Lock()

    def get_fresh(self) -> Token | None:
        """Return the cached token if present and not within the refresh margin of expiry."""
        token = self._token
        if token is not None and not token.is_expired(margin_seconds=self._margin):
            return token
        return None

    def set(self, token: Token) -> None:
        self._token = token
