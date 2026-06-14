"""
Pieces shared by the sync and async transports.

The only thing the two transports should differ in is *how* they send the request (blocking vs
awaiting). Everything else — base-URL resolution, URL/headers/params assembly, error mapping —
lives here so the two stay in lockstep.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, NamedTuple

from selectel_sm._core import urls
from selectel_sm.models import SECRETS_MANAGER_SERVICE, Token

if TYPE_CHECKING:
    from selectel_sm._core.request import RequestSpec
    from selectel_sm.config import Config

__all__ = ["API_VERSION", "PreparedRequest", "prepare", "resolve_base"]

# Secrets Manager API version segment. Catalog URLs don't include it, so we append it ourselves.
API_VERSION: str = "v1"


class PreparedRequest(NamedTuple):
    """
    Concrete arguments for a single httpx request, assembled from a :class:`RequestSpec`.
    """

    method: str
    url: str
    params: dict[str, Any] | None
    json: Any | None
    headers: dict[str, str]


def resolve_base(token: Token, config: Config) -> str:
    """
    Resolve the Secrets Manager base URL: explicit override, else from the token catalog.
    """
    if config.sm_base_url:
        return urls.normalize(config.sm_base_url)
    return token.catalog.endpoint_url(SECRETS_MANAGER_SERVICE, config.region, config.interface)


def prepare(spec: RequestSpec, base: str, token: Token) -> PreparedRequest:
    """
    Turn a :class:`RequestSpec` plus resolved base/token into concrete request arguments.
    """
    return PreparedRequest(
        method=spec.method,
        url=urls.join(base, API_VERSION, spec.path, trailing_slash=spec.trailing_slash),
        params=dict(spec.params) if spec.params else None,
        json=spec.json,
        headers=token.header(),
    )
