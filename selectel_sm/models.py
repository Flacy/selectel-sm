"""
Typed models for the Keystone token and its service catalog.

These are intentionally plain, frozen dataclasses built from the JSON Keystone returns. Only the
fields this library needs are modeled; unknown fields are ignored so Selectel can extend the
payload without breaking parsing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from selectel_sm._core import timestamps, urls
from selectel_sm.exceptions import EndpointNotFoundError

__all__ = [
    "Domain",
    "Endpoint",
    "Project",
    "Role",
    "Service",
    "ServiceCatalog",
    "Token",
    "User",
]

SECRETS_MANAGER_SERVICE: str = "secrets-manager"


@dataclass(frozen=True, slots=True)
class Domain:
    """
    A Keystone domain (account) reference.
    """

    id: str | None
    name: str | None

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> Domain:
        """
        Build a :class:`Domain` from a raw Keystone object.
        """
        return cls(id=raw.get("id"), name=raw.get("name"))


@dataclass(frozen=True, slots=True)
class Project:
    """
    A Keystone project the token is scoped to.
    """

    id: str | None
    name: str | None
    domain: Domain | None

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> Project:
        """
        Build a :class:`Project` from a raw Keystone object.
        """
        domain = raw.get("domain")
        return cls(
            id=raw.get("id"),
            name=raw.get("name"),
            domain=Domain.from_raw(domain) if domain else None,
        )


@dataclass(frozen=True, slots=True)
class User:
    """
    The Keystone user the token was issued to.
    """

    id: str | None
    name: str | None
    domain: Domain | None

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> User:
        """
        Build a :class:`User` from a raw Keystone object.
        """
        domain = raw.get("domain")
        return cls(
            id=raw.get("id"),
            name=raw.get("name"),
            domain=Domain.from_raw(domain) if domain else None,
        )


@dataclass(frozen=True, slots=True)
class Role:
    """
    A Keystone role granted by the token.
    """

    id: str | None
    name: str | None

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> Role:
        """
        Build a :class:`Role` from a raw Keystone object.
        """
        return cls(id=raw.get("id"), name=raw.get("name"))


@dataclass(frozen=True, slots=True)
class Endpoint:
    """
    A single service endpoint (one interface in one region).
    """

    interface: str
    region: str
    url: str

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> Endpoint:
        """
        Build an :class:`Endpoint` from a raw catalog entry.
        """
        return cls(
            interface=raw["interface"],
            # Some catalog entries use ``region``, others ``region_id``; prefer ``region``.
            region=raw.get("region") or raw.get("region_id", ""),
            url=raw["url"],
        )


@dataclass(frozen=True, slots=True)
class Service:
    """
    A catalog service and its endpoints.
    """

    type: str
    name: str | None
    endpoints: tuple[Endpoint, ...]

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> Service:
        """
        Build a :class:`Service` from a raw catalog entry.
        """
        return cls(
            type=raw["type"],
            name=raw.get("name"),
            endpoints=tuple(Endpoint.from_raw(e) for e in raw.get("endpoints", ())),
        )


@dataclass(frozen=True, slots=True)
class ServiceCatalog:
    """
    The service catalog from a Keystone token, used to resolve endpoint URLs.
    """

    services: tuple[Service, ...]

    @classmethod
    def from_raw(cls, raw: list[dict[str, Any]]) -> ServiceCatalog:
        """
        Build a :class:`ServiceCatalog` from the raw ``catalog`` list.
        """
        return cls(services=tuple(Service.from_raw(s) for s in raw))

    def service(self, service_type: str) -> Service | None:
        """
        Return the catalog service of *service_type*, or ``None`` when absent.
        """
        return next((s for s in self.services if s.type == service_type), None)

    def endpoint_url(
        self,
        service_type: str,
        region: str,
        interface: str = "public",
    ) -> str:
        """
        Return the normalized URL for *service_type* in *region* and *interface*.

        :param service_type: The catalog service type to look up.
        :param region: The desired region (e.g. ``ru-7``).
        :param interface: The desired interface (e.g. ``public``).
        :returns: The normalized endpoint URL.
        :raises EndpointNotFoundError: If no endpoint matches; the error lists the regions that
            *are* available for the service/interface.
        """
        service = self.service(service_type)
        endpoints = service.endpoints if service else ()
        for endpoint in endpoints:
            if endpoint.region == region and endpoint.interface == interface:
                return urls.normalize(endpoint.url)

        available = [e.region for e in endpoints if e.interface == interface]
        raise EndpointNotFoundError(service_type, region, interface, available)


@dataclass(frozen=True, slots=True)
class Token:
    """
    An IAM token plus the metadata Keystone returns alongside it.
    """

    value: str
    expires_at: datetime
    issued_at: datetime | None
    project: Project | None
    user: User | None
    roles: tuple[Role, ...] = field(default_factory=tuple)
    catalog: ServiceCatalog = field(default_factory=lambda: ServiceCatalog(()))

    @classmethod
    def from_response(cls, value: str, body: dict[str, Any]) -> Token:
        """
        Build a token from the ``X-Subject-Token`` header *value* and the JSON *body*.
        """
        token = body.get("token", {})
        project = token.get("project")
        user = token.get("user")
        return cls(
            value=value,
            expires_at=timestamps.parse(token["expires_at"]),
            issued_at=timestamps.parse_optional(token.get("issued_at")),
            project=Project.from_raw(project) if project else None,
            user=User.from_raw(user) if user else None,
            roles=tuple(Role.from_raw(r) for r in token.get("roles", ())),
            catalog=ServiceCatalog.from_raw(token.get("catalog", [])),
        )

    def header(self) -> dict[str, str]:
        """
        The header used to authenticate API requests.

        :returns: A mapping with the ``X-Auth-Token`` header set to this token's value.
        """
        return {"X-Auth-Token": self.value}

    def is_expired(self, *, now: datetime | None = None, margin_seconds: float = 0.0) -> bool:
        """
        Whether the token is expired, treating it as expired *margin_seconds* early.

        :param now: Reference time; defaults to the current UTC time.
        :param margin_seconds: Treat the token as expired this many seconds before its real expiry.
        :returns: ``True`` when the token is (about to be) expired.
        """
        now = now or datetime.now(UTC)
        return (self.expires_at - now).total_seconds() <= margin_seconds
