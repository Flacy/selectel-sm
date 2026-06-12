"""Asynchronous Secrets Manager client (skeleton).

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
        self._config = config
        self._auth = auth
        self._transport = AsyncTransport(config, auth, client=client)
        self.secrets = AsyncSecretsResource(self._transport)
        # self.versions = AsyncVersionsResource(self._transport)  # next operation

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
        """Build a client that authenticates with service-user credentials."""
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
        """Build a client from an existing project-scoped token (see the sync client)."""
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
        await self._transport.aclose()

    async def __aenter__(self) -> AsyncSecretsManagerClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()
