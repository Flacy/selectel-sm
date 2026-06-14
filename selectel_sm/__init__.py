"""
selectel-sm — a Python client for Selectel Secrets Manager (sync + async).
"""

from __future__ import annotations

from selectel_sm.aclient import AsyncSecretsManagerClient
from selectel_sm.auth import AuthProvider, PasswordAuth, StaticTokenAuth
from selectel_sm.client import SecretsManagerClient
from selectel_sm.config import IDENTITY_URL_INTL, IDENTITY_URL_RU, Config
from selectel_sm.exceptions import (
    APIError,
    AuthenticationError,
    BadRequestError,
    ConflictError,
    EndpointNotFoundError,
    ForbiddenError,
    NotFoundError,
    SelectelSMError,
    ServerError,
    TransportError,
)
from selectel_sm.models import Endpoint, ServiceCatalog, Token
from selectel_sm.resources import (
    Secret,
    SecretSummary,
    SecretType,
    SecretVersion,
    SecretWithVersions,
)

__version__: str = "0.2.0"
__all__ = [
    "IDENTITY_URL_INTL",
    "IDENTITY_URL_RU",
    "APIError",
    "AsyncSecretsManagerClient",
    "AuthProvider",
    "AuthenticationError",
    "BadRequestError",
    "Config",
    "ConflictError",
    "Endpoint",
    "EndpointNotFoundError",
    "ForbiddenError",
    "NotFoundError",
    "PasswordAuth",
    "Secret",
    "SecretSummary",
    "SecretType",
    "SecretVersion",
    "SecretWithVersions",
    "SecretsManagerClient",
    "SelectelSMError",
    "ServerError",
    "ServiceCatalog",
    "StaticTokenAuth",
    "Token",
    "TransportError",
    "__version__",
]
