"""Bring-your-own-token auth.

The caller supplies an existing project-scoped token. To discover the service catalog (needed to
resolve the Secrets Manager endpoint), the provider validates/introspects the token against
Keystone. If no ``identity_url`` is given, no catalog is available — in that case set
``Config.sm_base_url`` so the transport can skip catalog resolution.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx

from selectel_sm._core import keystone
from selectel_sm.auth.base import AuthProvider
from selectel_sm.exceptions import AuthenticationError, TransportError
from selectel_sm.models import ServiceCatalog, Token

__all__ = ["StaticTokenAuth"]

# A synthetic token (no introspection) gets a long, fixed lifetime so it is never "refreshed":
# we have nothing to refresh it from, and the real expiry is the caller's concern.
_SYNTHETIC_TTL = timedelta(days=3650)


class StaticTokenAuth(AuthProvider):
    def __init__(self, token: str, *, identity_url: str | None = None) -> None:
        super().__init__()
        self._token = token
        self._identity_url = identity_url.rstrip("/") if identity_url else None

    @property
    def _url(self) -> str | None:
        if self._identity_url is None:
            return None
        return self._identity_url + keystone.AUTH_TOKENS_PATH

    def _headers(self) -> dict[str, str]:
        # X-Auth-Token authorizes the call; X-Subject-Token names the token being validated.
        return {"X-Auth-Token": self._token, keystone.SUBJECT_TOKEN_HEADER: self._token}

    def _synthetic(self) -> Token:
        return Token(
            value=self._token,
            expires_at=datetime.now(UTC) + _SYNTHETIC_TTL,
            issued_at=None,
            project=None,
            user=None,
            roles=(),
            catalog=ServiceCatalog(()),
        )

    def _from_body(self, body: object) -> Token:
        if not isinstance(body, dict):
            raise AuthenticationError("Keystone introspection body is not a JSON object.")
        try:
            # Use the caller-supplied token value rather than trusting the echoed header.
            return Token.from_response(self._token, body)
        except (KeyError, TypeError, ValueError) as exc:
            raise AuthenticationError(f"Malformed introspection body: {exc}") from exc

    @staticmethod
    def _check(response: httpx.Response) -> None:
        if not response.is_success:
            raise AuthenticationError(f"Token introspection failed (HTTP {response.status_code}).")

    def _fetch(self, client: httpx.Client) -> Token:
        url = self._url
        if url is None:
            return self._synthetic()
        try:
            response = client.get(url, headers=self._headers())
        except httpx.HTTPError as exc:
            raise TransportError(f"Failed to reach Keystone: {exc}") from exc
        self._check(response)
        return self._from_body(self._json(response))

    async def _afetch(self, client: httpx.AsyncClient) -> Token:
        url = self._url
        if url is None:
            return self._synthetic()
        try:
            response = await client.get(url, headers=self._headers())
        except httpx.HTTPError as exc:
            raise TransportError(f"Failed to reach Keystone: {exc}") from exc
        self._check(response)
        return self._from_body(self._json(response))

    @staticmethod
    def _json(response: httpx.Response) -> object:
        try:
            return response.json()
        except ValueError as exc:
            raise AuthenticationError("Introspection response is not valid JSON.") from exc
