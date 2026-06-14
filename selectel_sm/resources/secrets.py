"""
The ``secrets`` resource.

This module establishes the pattern every resource follows:

* public models live in :mod:`selectel_sm.resources.models` (:class:`Secret`,
  :class:`SecretSummary`, :class:`SecretWithVersions`);
* pure, transport-agnostic functions that build a :class:`RequestSpec` and parse a response
  (``build_*`` / ``parse_*``) — written once, used by both clients;
* thin sync/async resource classes (:class:`SecretsResource` / :class:`AsyncSecretsResource`)
  that only differ in blocking vs ``await``.

All operations are implemented: get, create, update description, delete, list, get versions,
get version, create version, and activate version.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from selectel_sm._core import encoding
from selectel_sm._core.request import RequestSpec
from selectel_sm.resources.models import (
    Secret,
    SecretSummary,
    SecretVersion,
    SecretWithVersions,
)

if TYPE_CHECKING:
    from selectel_sm._transport.async_ import AsyncTransport
    from selectel_sm._transport.sync import SyncTransport

__all__ = ["AsyncSecretsResource", "SecretsResource"]

# Listing requires a ``list`` query parameter to be present. This is a server-side quirk: the
# endpoint only lists secrets when the flag is there, and it accepts *any* value (the value is
# ignored, only presence matters). We always send "true".
LIST_QUERY_FLAG: str = "list"


def build_get(name: str) -> RequestSpec:
    """
    Build the request for fetching a single secret by name.
    """
    # Encode the whole name as one path segment so names with reserved characters are safe.
    return RequestSpec("GET", quote(name, safe=""))


def parse_secret(name: str, body: dict[str, Any]) -> Secret:
    """
    Parse a get/create response body into a :class:`Secret`.
    """
    return Secret.from_response(name, body)


def build_list() -> RequestSpec:
    """
    Build the request for listing all secrets.

    Two server-side quirks are handled here:

    * The ``?list=`` query flag is mandatory: without it the API does not return the secret
      list. Its value is irrelevant to the server (any value works), so we send ``list=true``.
    * The root path must end with a slash (``/v1/?list=true``); without it the API responds
      ``404 page not found``. Hence ``trailing_slash=True``.
    """
    return RequestSpec("GET", "", params={LIST_QUERY_FLAG: "true"}, trailing_slash=True)


def parse_list(body: dict[str, Any]) -> list[SecretSummary]:
    """
    Parse a listing response body into a list of :class:`SecretSummary`.
    """
    return [SecretSummary.from_raw(entry) for entry in body.get("keys", [])]


def build_get_versions(name: str) -> RequestSpec:
    """
    Build the request for fetching a secret together with all of its version metadata.
    """
    return RequestSpec("GET", f"{quote(name, safe='')}/versions")


def parse_secret_versions(name: str, body: dict[str, Any]) -> SecretWithVersions:
    """
    Parse a get-versions response body into a :class:`SecretWithVersions`.
    """
    return SecretWithVersions.from_response(name, body)


def build_get_version(name: str, version_id: int) -> RequestSpec:
    """
    Build the request for fetching a single version of a secret (value included).
    """
    return RequestSpec("GET", f"{quote(name, safe='')}/versions/{version_id}")


def parse_version(body: dict[str, Any]) -> SecretVersion:
    """
    Parse a single-version response body into a :class:`SecretVersion`.
    """
    return SecretVersion.from_raw(body)


def build_activate_version(name: str, version_id: int) -> RequestSpec:
    """
    Build the request for making a specific version the current one.

    The documentation claims this returns ``204 No Content``, but in reality the API responds
    ``200 OK`` with the version's metadata (``version_id``, ``created_at``, ``is_current``) and
    no ``value`` — so the returned :class:`SecretVersion` has ``value=None``.
    """
    return RequestSpec("POST", f"{quote(name, safe='')}/versions/{version_id}/activate")


def build_create_version(name: str, value: bytes | str, activate: bool = False) -> RequestSpec:
    """
    Build the request for adding a new version to an existing secret.

    *value* is plain data (``bytes`` or ``str``), base64-encoded for you — see
    :func:`build_create` for the API's base64-validation quirk.

    When *activate* is true, the ``?activate=true`` query flag makes the new version current
    (``is_current``); otherwise the version is created without changing the current one.
    """
    body = {"value": encoding.encode_value(value)}
    params = {"activate": "true"} if activate else None
    return RequestSpec("POST", f"{quote(name, safe='')}/versions", params=params, json=body)


def build_create(name: str, value: bytes | str, description: str | None = None) -> RequestSpec:
    """
    Build the request for creating a secret with its first version.

    *value* is plain data (``bytes`` or ``str``); we base64-encode it here so callers never deal
    with encoding themselves. The API *does* validate that the stored value is valid base64, so
    sending raw plain text is generally rejected — the string ``"test"`` is a confusing
    exception only because it happens to be valid base64 itself (decoding to arbitrary bytes,
    not the text "test"). Since we always encode *value* for you, you pass plain data and this
    server-side quirk never surfaces; values round-trip correctly through :class:`SecretVersion`.

    *description* is optional and omitted from the body when ``None``.
    """
    body: dict[str, str] = {"value": encoding.encode_value(value)}
    if description is not None:
        body["description"] = description
    return RequestSpec("POST", quote(name, safe=""), json=body)


def build_update_description(name: str, description: str | None) -> RequestSpec:
    """
    Build the request for updating a secret's description.

    The ``description`` key is always sent (this operation exists to set it), so passing ``None``
    clears the description.
    """
    return RequestSpec("PUT", quote(name, safe=""), json={"description": description})


def build_delete(name: str) -> RequestSpec:
    """
    Build the request for deleting a secret (and all of its versions).
    """
    return RequestSpec("DELETE", quote(name, safe=""))


class SecretsResource:
    """
    Synchronous operations on secrets.
    """

    def __init__(self, transport: SyncTransport) -> None:
        self._transport: SyncTransport = transport

    def get(self, name: str) -> Secret:
        """
        Fetch a secret by name, including its current version's value.

        :param name: Secret name.
        :returns: The secret with its current version embedded.
        :raises NotFoundError: If no secret named *name* exists.
        :raises APIError: On any other unexpected API status.
        :raises TransportError: If the request cannot be completed.
        """
        response = self._transport.send(build_get(name))
        return parse_secret(name, response.json())

    def create(self, name: str, value: bytes | str, *, description: str | None = None) -> Secret:
        """
        Create a secret together with its first version.

        *value* is plain data (``bytes`` or ``str``) and is base64-encoded for you.

        :param name: Secret name; used verbatim as a single URL path segment.
        :param value: Plain secret payload, encoded before sending.
        :param description: Optional description; omitted from the body when ``None``.
        :returns: The created secret, including its first version.
        :raises ConflictError: If a secret named *name* already exists.
        :raises APIError: On any other unexpected API status.
        :raises TransportError: If the request cannot be completed.
        """
        response = self._transport.send(build_create(name, value, description))
        return parse_secret(name, response.json())

    def update_description(self, name: str, description: str | None) -> None:
        """
        Set (or clear) a secret's description.

        :param name: Secret name.
        :param description: New description; pass ``None`` to clear it.
        :returns: Nothing.
        :raises NotFoundError: If no secret named *name* exists.
        :raises APIError: On any other unexpected API status.
        :raises TransportError: If the request cannot be completed.
        """
        self._transport.send(build_update_description(name, description))

    def list(self) -> list[SecretSummary]:
        """
        List all secrets (metadata only; values are not returned).

        :returns: One :class:`SecretSummary` per secret (empty list when there are none).
        :raises APIError: On any unexpected API status.
        :raises TransportError: If the request cannot be completed.
        """
        response = self._transport.send(build_list())
        return parse_list(response.json())

    def get_versions(self, name: str) -> SecretWithVersions:
        """
        Fetch a secret with metadata for all of its versions (no values).

        :param name: Secret name.
        :returns: The secret together with all of its version metadata.
        :raises NotFoundError: If no secret named *name* exists.
        :raises APIError: On any other unexpected API status.
        :raises TransportError: If the request cannot be completed.
        """
        response = self._transport.send(build_get_versions(name))
        return parse_secret_versions(name, response.json())

    def get_version(self, name: str, version_id: int) -> SecretVersion:
        """
        Fetch a single version of a secret, including its value.

        :param name: Secret name.
        :param version_id: Identifier of the version to read.
        :returns: The requested version, with its decoded value.
        :raises NotFoundError: If the secret or the version does not exist.
        :raises APIError: On any other unexpected API status.
        :raises TransportError: If the request cannot be completed.
        """
        response = self._transport.send(build_get_version(name, version_id))
        return parse_version(response.json())

    def create_version(
        self, name: str, value: bytes | str, *, activate: bool = False
    ) -> SecretVersion:
        """
        Add a new version to an existing secret.

        *value* is plain data (``bytes`` or ``str``) and is base64-encoded for you.

        :param name: Secret name.
        :param value: Plain secret payload, encoded before sending.
        :param activate: When true, make the new version current.
        :returns: The created version (its value is included).
        :raises NotFoundError: If no secret named *name* exists.
        :raises APIError: On any other unexpected API status.
        :raises TransportError: If the request cannot be completed.
        """
        response = self._transport.send(build_create_version(name, value, activate))
        return parse_version(response.json())

    def activate_version(self, name: str, version_id: int) -> SecretVersion:
        """
        Make *version_id* the current version.

        :param name: Secret name.
        :param version_id: Identifier of the version to activate.
        :returns: The activated version's metadata (its ``value`` is ``None``).
        :raises NotFoundError: If the secret or the version does not exist.
        :raises APIError: On any other unexpected API status.
        :raises TransportError: If the request cannot be completed.
        """
        response = self._transport.send(build_activate_version(name, version_id))
        return parse_version(response.json())

    def delete(self, name: str) -> None:
        """
        Delete a secret and all of its versions.

        :param name: Secret name.
        :returns: Nothing.
        :raises NotFoundError: If no secret named *name* exists.
        :raises APIError: On any other unexpected API status.
        :raises TransportError: If the request cannot be completed.
        """
        self._transport.send(build_delete(name))


class AsyncSecretsResource:
    """
    Asynchronous counterpart of :class:`SecretsResource`.
    """

    def __init__(self, transport: AsyncTransport) -> None:
        self._transport: AsyncTransport = transport

    async def get(self, name: str) -> Secret:
        """
        Fetch a secret by name, including its current version's value.

        :param name: Secret name.
        :returns: The secret with its current version embedded.
        :raises NotFoundError: If no secret named *name* exists.
        :raises APIError: On any other unexpected API status.
        :raises TransportError: If the request cannot be completed.
        """
        response = await self._transport.send(build_get(name))
        return parse_secret(name, response.json())

    async def create(
        self, name: str, value: bytes | str, *, description: str | None = None
    ) -> Secret:
        """
        Create a secret together with its first version.

        *value* is plain data (``bytes`` or ``str``) and is base64-encoded for you.

        :param name: Secret name; used verbatim as a single URL path segment.
        :param value: Plain secret payload, encoded before sending.
        :param description: Optional description; omitted from the body when ``None``.
        :returns: The created secret, including its first version.
        :raises ConflictError: If a secret named *name* already exists.
        :raises APIError: On any other unexpected API status.
        :raises TransportError: If the request cannot be completed.
        """
        response = await self._transport.send(build_create(name, value, description))
        return parse_secret(name, response.json())

    async def update_description(self, name: str, description: str | None) -> None:
        """
        Set (or clear) a secret's description.

        :param name: Secret name.
        :param description: New description; pass ``None`` to clear it.
        :returns: Nothing.
        :raises NotFoundError: If no secret named *name* exists.
        :raises APIError: On any other unexpected API status.
        :raises TransportError: If the request cannot be completed.
        """
        await self._transport.send(build_update_description(name, description))

    async def list(self) -> list[SecretSummary]:
        """
        List all secrets (metadata only; values are not returned).

        :returns: One :class:`SecretSummary` per secret (empty list when there are none).
        :raises APIError: On any unexpected API status.
        :raises TransportError: If the request cannot be completed.
        """
        response = await self._transport.send(build_list())
        return parse_list(response.json())

    async def get_versions(self, name: str) -> SecretWithVersions:
        """
        Fetch a secret with metadata for all of its versions (no values).

        :param name: Secret name.
        :returns: The secret together with all of its version metadata.
        :raises NotFoundError: If no secret named *name* exists.
        :raises APIError: On any other unexpected API status.
        :raises TransportError: If the request cannot be completed.
        """
        response = await self._transport.send(build_get_versions(name))
        return parse_secret_versions(name, response.json())

    async def get_version(self, name: str, version_id: int) -> SecretVersion:
        """
        Fetch a single version of a secret, including its value.

        :param name: Secret name.
        :param version_id: Identifier of the version to read.
        :returns: The requested version, with its decoded value.
        :raises NotFoundError: If the secret or the version does not exist.
        :raises APIError: On any other unexpected API status.
        :raises TransportError: If the request cannot be completed.
        """
        response = await self._transport.send(build_get_version(name, version_id))
        return parse_version(response.json())

    async def create_version(
        self, name: str, value: bytes | str, *, activate: bool = False
    ) -> SecretVersion:
        """
        Add a new version to an existing secret.

        *value* is plain data (``bytes`` or ``str``) and is base64-encoded for you.

        :param name: Secret name.
        :param value: Plain secret payload, encoded before sending.
        :param activate: When true, make the new version current.
        :returns: The created version (its value is included).
        :raises NotFoundError: If no secret named *name* exists.
        :raises APIError: On any other unexpected API status.
        :raises TransportError: If the request cannot be completed.
        """
        response = await self._transport.send(build_create_version(name, value, activate))
        return parse_version(response.json())

    async def activate_version(self, name: str, version_id: int) -> SecretVersion:
        """
        Make *version_id* the current version.

        :param name: Secret name.
        :param version_id: Identifier of the version to activate.
        :returns: The activated version's metadata (its ``value`` is ``None``).
        :raises NotFoundError: If the secret or the version does not exist.
        :raises APIError: On any other unexpected API status.
        :raises TransportError: If the request cannot be completed.
        """
        response = await self._transport.send(build_activate_version(name, version_id))
        return parse_version(response.json())

    async def delete(self, name: str) -> None:
        """
        Delete a secret and all of its versions.

        :param name: Secret name.
        :returns: Nothing.
        :raises NotFoundError: If no secret named *name* exists.
        :raises APIError: On any other unexpected API status.
        :raises TransportError: If the request cannot be completed.
        """
        await self._transport.send(build_delete(name))
