"""API resource namespaces (``client.secrets``, ``client.versions``, ...)."""

from __future__ import annotations

from selectel_sm.resources.models import (
    Secret,
    SecretSummary,
    SecretType,
    SecretVersion,
    SecretWithVersions,
)
from selectel_sm.resources.secrets import AsyncSecretsResource, SecretsResource

__all__ = [
    "AsyncSecretsResource",
    "Secret",
    "SecretSummary",
    "SecretType",
    "SecretVersion",
    "SecretWithVersions",
    "SecretsResource",
]
