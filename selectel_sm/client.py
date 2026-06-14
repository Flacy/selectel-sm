"""
Synchronous Secrets Manager client.

Wires together config + auth + transport, owns the connection lifecycle, and exposes the API
resource namespaces (``.secrets``, and ``.versions`` once implemented), each delegating to
``self._transport.send(...)``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from selectel_sm._transport.sync import SyncTransport
from selectel_sm.auth.password import PasswordAuth
from selectel_sm.auth.static import StaticTokenAuth
from selectel_sm.config import DEFAULT_TIMEOUT, IDENTITY_URL_RU, Config
from selectel_sm.resources.secrets import SecretsResource

if TYPE_CHECKING:
    from types import TracebackType

    import httpx

    from selectel_sm.auth.base import AuthProvider

__all__ = ["SecretsManagerClient"]


class SecretsManagerClient:
    def __init__(
        self,
        config: Config,
        auth: AuthProvider,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        """
        Wire up the transport and resource namespaces from an explicit config + auth provider.

        Prefer the :meth:`from_credentials` / :meth:`from_token` factories for the common cases.

        :param config: Connection settings.
        :param auth: The authentication provider that mints/refreshes tokens.
        :param client: Optional pre-built httpx client (otherwise one is created).
        """
        self._config: Config = config
        self._auth: AuthProvider = auth
        self._transport: SyncTransport = SyncTransport(config, auth, client=client)
        self.secrets: SecretsResource = SecretsResource(self._transport)
        # self.versions = VersionsResource(self._transport)  # next operation

    def __enter__(self) -> SecretsManagerClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

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
    ) -> SecretsManagerClient:
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
        :returns: A ready-to-use client.
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
    ) -> SecretsManagerClient:
        """
        Build a client from an existing project-scoped token.

        Without ``sm_base_url`` the token is introspected against ``identity_url`` (defaulting to
        the RU identity endpoint) to discover the Secrets Manager endpoint.

        :param region: Region whose Secrets Manager endpoint to use (e.g. ``ru-7``).
        :param token: An existing project-scoped IAM token.
        :param identity_url: Keystone v3 identity base URL used to introspect the token.
        :param sm_base_url: Optional explicit SM base URL; when set, introspection is skipped.
        :param interface: Catalog interface to resolve (``public`` by default).
        :param timeout: Optional httpx timeout; the library default is used when ``None``.
        :param verify: Whether to verify TLS certificates.
        :returns: A ready-to-use client.
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

    def close(self) -> None:
        """
        Close the underlying transport and its httpx client.
        """
        self._transport.close()


def _make_config(
    *,
    region: str,
    identity_url: str,
    interface: str,
    account_id: str | None = None,
    project_name: str | None = None,
    timeout: httpx.Timeout | None,
    verify: bool,
    sm_base_url: str | None,
) -> Config:
    """
    Build a :class:`~selectel_sm.config.Config`, applying the default timeout when unset.
    """
    return Config(
        region=region,
        identity_url=identity_url,
        interface=interface,
        account_id=account_id,
        project_name=project_name,
        timeout=timeout if timeout is not None else DEFAULT_TIMEOUT,
        verify=verify,
        sm_base_url=sm_base_url,
    )
