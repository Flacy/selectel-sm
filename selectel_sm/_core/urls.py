"""
URL helpers for catalog endpoints.

Selectel's service catalog returns Secrets Manager URLs with quirks that need cleaning before
use, e.g. ``https://cloud.api.selcloud.ru//secrets-manager/`` (a double slash in the path and a
trailing slash), and without the ``/v1`` API version segment. These helpers normalize such URLs
and join API paths onto them with exactly one slash between each part.
"""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

__all__ = ["join", "normalize"]


def normalize(url: str) -> str:
    """
    Return *url* with collapsed duplicate path slashes and no trailing slash.

    The scheme/host are left untouched; only the path is cleaned. The query and fragment are
    preserved (catalog URLs don't use them, but we don't want to silently drop them).

    >>> normalize("https://cloud.api.selcloud.ru//secrets-manager/")
    'https://cloud.api.selcloud.ru/secrets-manager'
    """
    parts = urlsplit(url)
    segments = [segment for segment in parts.path.split("/") if segment]
    path = "/" + "/".join(segments)
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))


def join(base: str, *segments: str, trailing_slash: bool = False) -> str:
    """
    Join *base* with path *segments*, normalizing slashes.

    *base* is normalized first; each segment may itself contain slashes and is split, so callers
    can pass either ``join(base, "v1", "name")`` or ``join(base, "v1/name")``. Set
    *trailing_slash* to keep a single ``/`` at the end (some endpoints require it).

    >>> join("https://host//secrets-manager/", "v1", "my-secret")
    'https://host/secrets-manager/v1/my-secret'
    >>> join("https://host//secrets-manager/", "v1", trailing_slash=True)
    'https://host/secrets-manager/v1/'
    """
    parts = urlsplit(normalize(base))
    path_segments = [segment for segment in parts.path.split("/") if segment]
    for segment in segments:
        path_segments.extend(piece for piece in segment.split("/") if piece)

    path = "/" + "/".join(path_segments)
    if trailing_slash and not path.endswith("/"):
        path += "/"
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))
