"""
Asynchronous Secrets Manager client (skeleton).

Mirror of :class:`selectel_sm.client.SecretsManagerClient` over the async transport. Secret and
version operations land in a follow-up at the marked extension point.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from selectel_sm._transport.async_ import AsyncTransport
from selectel_sm.auth.password import PasswordAuth
from selectel_sm.auth.static import StaticTokenAuth
from selectel_sm.client import _make_config
from selectel_sm.config import IDENTITY_URL_RU, Config
from selectel_sm.resources.secrets import AsyncSecretsResource

if TYPE_CHECKING:
    from types import TracebackType

    import httpx

    from selectel_sm.auth.base import AuthProvider

__all__ = ["AsyncSecretsManagerClient"]


class AsyncSecretsManagerClient:
    def __init__(
        self,
        config: Config,
        auth: AuthProvider,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """
        Wire up the async transport and resource namespaces from a config + auth provider.

        Prefer the :meth:`from_credentials` / :meth:`from_token` factories for the common cases.

        :param config: Connection settings.
        :param auth: The authentication provider that mints/refreshes tokens.
        :param client: Optional pre-built async httpx client (otherwise one is created).
        """
        self._config: Config = config
        self._auth: AuthProvider = auth
        self._transport: AsyncTransport = AsyncTransport(config, auth, client=client)
        self.secrets: AsyncSecretsResource = AsyncSecretsResource(self._transport)
        # self.versions = AsyncVersionsResource(self._transport)  # next operation

    async def __aenter__(self) -> AsyncSecretsManagerClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    @classmethod
    def from_credentials(
        cls,
        *,
        region: str,
        account_id: str,
        username: str,
        password: str,
        project_name: str,
        identity_url: str = IDENTITY_URL_RU,
        interface: str = "public",
        timeout: httpx.Timeout | None = None,
        verify: bool = True,
        sm_base_url: str | None = None,
    ) -> AsyncSecretsManagerClient:
        """
        Build a client that authenticates with service-user credentials.

        :param region: Region whose Secrets Manager endpoint to use (e.g. ``ru-7``).
        :param account_id: Selectel account id (Keystone domain name).
        :param username: Service-user name.
        :param password: Service-user password.
        :param project_name: Project to scope the token to.
        :param identity_url: Keystone v3 identity base URL.
        :param interface: Catalog interface to resolve (``public`` by default).
        :param timeout: Optional httpx timeout; the library default is used when ``None``.
        :param verify: Whether to verify TLS certificates.
        :param sm_base_url: Optional explicit SM base URL, bypassing catalog resolution.
        :returns: A ready-to-use async client.
        """
        config = _make_config(
            region=region,
            identity_url=identity_url,
            interface=interface,
            account_id=account_id,
            project_name=project_name,
            timeout=timeout,
            verify=verify,
            sm_base_url=sm_base_url,
        )
        auth = PasswordAuth(
            identity_url=identity_url,
            account_id=account_id,
            username=username,
            password=password,
            project_name=project_name,
        )
        return cls(config, auth)

    @classmethod
    def from_token(
        cls,
        *,
        region: str,
        token: str,
        identity_url: str | None = None,
        sm_base_url: str | None = None,
        interface: str = "public",
        timeout: httpx.Timeout | None = None,
        verify: bool = True,
    ) -> AsyncSecretsManagerClient:
        """
        Build a client from an existing project-scoped token (see the sync client).

        :param region: Region whose Secrets Manager endpoint to use (e.g. ``ru-7``).
        :param token: An existing project-scoped IAM token.
        :param identity_url: Keystone v3 identity base URL used to introspect the token.
        :param sm_base_url: Optional explicit SM base URL; when set, introspection is skipped.
        :param interface: Catalog interface to resolve (``public`` by default).
        :param timeout: Optional httpx timeout; the library default is used when ``None``.
        :param verify: Whether to verify TLS certificates.
        :returns: A ready-to-use async client.
        """
        if sm_base_url is None and identity_url is None:
            identity_url = IDENTITY_URL_RU
        config = _make_config(
            region=region,
            identity_url=identity_url or IDENTITY_URL_RU,
            interface=interface,
            timeout=timeout,
            verify=verify,
            sm_base_url=sm_base_url,
        )
        auth = StaticTokenAuth(token, identity_url=identity_url)
        return cls(config, auth)

    async def aclose(self) -> None:
        """
        Close the underlying async transport and its httpx client.
        """
        await self._transport.aclose()
