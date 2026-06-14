"""
Credentials-based auth: exchange service-user credentials for a project-scoped token.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

from selectel_sm._core import keystone
from selectel_sm.auth.base import AuthProvider
from selectel_sm.exceptions import AuthenticationError, TransportError

if TYPE_CHECKING:
    from selectel_sm.models import Token

__all__ = ["PasswordAuth"]


class PasswordAuth(AuthProvider):
    """
    Obtain a project-scoped IAM token from service-user credentials.

    The resulting token (and its catalog) is cached and refreshed automatically before expiry by
    the base :class:`~selectel_sm.auth.base.AuthProvider`.
    """

    def __init__(
        self,
        *,
        identity_url: str,
        account_id: str,
        username: str,
        password: str,
        project_name: str,
    ) -> None:
        """
        Store the service-user credentials used to mint project-scoped tokens.

        :param identity_url: Keystone v3 identity base URL (a trailing slash is stripped).
        :param account_id: Selectel account id; used as the Keystone domain name.
        :param username: Service-user name.
        :param password: Service-user password.
        :param project_name: Project to scope the token to (Secrets Manager needs project scope).
        """
        super().__init__()
        self._identity_url: str = identity_url.rstrip("/")
        self._account_id: str = account_id
        self._username: str = username
        self._password: str = password
        self._project_name: str = project_name

    @staticmethod
    def _check(response: httpx.Response) -> None:
        if response.status_code != httpx.codes.CREATED:
            raise AuthenticationError(
                f"Keystone authentication failed (HTTP {response.status_code})."
            )

    @property
    def _url(self) -> str:
        return self._identity_url + keystone.AUTH_TOKENS_PATH

    def _body(self) -> dict[str, object]:
        return keystone.build_password_auth(
            account_id=self._account_id,
            username=self._username,
            password=self._password,
            project_name=self._project_name,
        )

    def _fetch(self, client: httpx.Client) -> Token:
        try:
            response = client.post(self._url, json=self._body())
        except httpx.HTTPError as exc:
            raise TransportError(f"Failed to reach Keystone: {exc}") from exc
        self._check(response)
        return keystone.parse_token(response)

    async def _afetch(self, client: httpx.AsyncClient) -> Token:
        try:
            response = await client.post(self._url, json=self._body())
        except httpx.HTTPError as exc:
            raise TransportError(f"Failed to reach Keystone: {exc}") from exc
        self._check(response)
        return keystone.parse_token(response)
