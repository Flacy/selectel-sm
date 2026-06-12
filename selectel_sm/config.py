"""Client configuration.

The bootstrap *identity* URL is the only endpoint that cannot be discovered from a catalog
(we need it to authenticate before any catalog exists), so it lives here with sensible defaults.
The Secrets Manager endpoint itself is resolved at request time from the token's catalog using
``region`` + ``interface`` — see :meth:`selectel_sm.models.ServiceCatalog.endpoint_url`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import httpx

__all__ = [
    "DEFAULT_INTERFACE",
    "IDENTITY_URL_INTL",
    "IDENTITY_URL_RU",
    "Config",
]

# Keystone v3 identity endpoints used to obtain a token (docs.selectel.ru/api/urls).
IDENTITY_URL_RU = "https://cloud.api.selcloud.ru/identity/v3"
IDENTITY_URL_INTL = "https://cloud.api.selcloud.com/identity/v3"
DEFAULT_INTERFACE = "public"
DEFAULT_TIMEOUT = httpx.Timeout(30.0)


@dataclass(frozen=True, slots=True)
class Config:
    """Connection settings for a Secrets Manager client.

    ``region`` is required: Selectel has no implicit default region, and the catalog lists an
    endpoint per region. Set ``sm_base_url`` to bypass catalog resolution entirely (handy for
    tests or a bring-your-own-token flow without introspection).
    """

    region: str
    identity_url: str = IDENTITY_URL_RU
    interface: str = DEFAULT_INTERFACE
    account_id: str | None = None
    project_name: str | None = None
    sm_base_url: str | None = None
    timeout: httpx.Timeout = field(default_factory=lambda: DEFAULT_TIMEOUT)
    verify: bool = True

    def __post_init__(self) -> None:
        if not self.region:
            raise ValueError("Config.region is required (e.g. 'ru-7').")
