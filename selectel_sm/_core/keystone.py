"""Pure helpers for the Keystone v3 identity API.

Kept transport-agnostic so the sync and async auth providers share request building and response
parsing. Nothing here performs I/O.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from selectel_sm.exceptions import AuthenticationError
from selectel_sm.models import Token

if TYPE_CHECKING:
    import httpx

__all__ = [
    "AUTH_TOKENS_PATH",
    "SUBJECT_TOKEN_HEADER",
    "build_password_auth",
    "parse_token",
]

# Appended to the configured identity base URL (which already ends with ``/v3``).
AUTH_TOKENS_PATH = "/auth/tokens"
SUBJECT_TOKEN_HEADER = "X-Subject-Token"


def build_password_auth(
    *,
    account_id: str,
    username: str,
    password: str,
    project_name: str,
) -> dict[str, Any]:
    """Build a **project-scoped** password-auth request body.

    Secrets Manager requires a project-scoped token, so the scope is always ``project`` (the
    public docs' account scope does not work for SM).
    """
    domain = {"name": account_id}
    return {
        "auth": {
            "identity": {
                "methods": ["password"],
                "password": {
                    "user": {
                        "name": username,
                        "domain": domain,
                        "password": password,
                    }
                },
            },
            "scope": {"project": {"name": project_name, "domain": domain}},
        }
    }


def parse_token(response: httpx.Response) -> Token:
    """Parse a Keystone auth/introspection response into a :class:`Token`.

    The token value comes from the ``X-Subject-Token`` header; everything else from the body.
    Raises :class:`AuthenticationError` if the header is missing or the body is malformed.
    """
    value = response.headers.get(SUBJECT_TOKEN_HEADER)
    if not value:
        raise AuthenticationError(
            f"Keystone response is missing the {SUBJECT_TOKEN_HEADER} header."
        )
    try:
        body = response.json()
    except ValueError as exc:
        raise AuthenticationError("Keystone response body is not valid JSON.") from exc
    try:
        return Token.from_response(value, body)
    except (KeyError, TypeError, ValueError) as exc:
        raise AuthenticationError(f"Malformed Keystone token body: {exc}") from exc
