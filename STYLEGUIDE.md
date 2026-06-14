# selectel-sm — Code Style Guide

This document defines the code-style rules for `selectel-sm`. Examples are drawn from the
project's own source. Tooling baseline (`pyproject.toml`): ruff `line-length = 99`,
lint set `E,F,I,UP,B,SIM,TCH,RUF`; mypy `strict`.

## 1. Docstrings: reStructuredText, complete for public API

Every public function/method/class/module has a docstring. Public callables document their
**arguments, return value, raised exceptions**, and any quirk a caller must know. Use reST
fields: `:param name:`, `:returns:`, `:raises ExcType:`. Do **not** repeat types via
`:type:`/`:rtype:` — they already live in the annotations.

When a public method delegates to another public callable, document **both**, but make the
**outermost** one the more thorough — never let a caller face a thin wrapper over hidden magic.
Inner helpers (e.g. `build_*` / `parse_*`) may stay summary-only.

```python
# Outer public API method — full reST.
def create(self, name: str, value: bytes | str, *, description: str | None = None) -> Secret:
    """
    Create a secret together with its first version.

    The value is plain data and is base64-encoded for you; callers never deal with encoding.

    :param name: Secret name; used verbatim as a single URL path segment.
    :param value: Plain secret payload, encoded before sending.
    :param description: Optional human-readable description; omitted from the body when ``None``.
    :returns: The created secret, including its first version.
    :raises NotFoundError: If the project scope cannot be resolved.
    :raises SelectelSMError: On any other API-level failure.
    """
    response = self._transport.send(build_create(name, value, description))
    return parse_secret(name, response.json())
```

```python
# Inner helper — summary only (still multiline, see rule 4).
def build_create(name: str, value: bytes | str, description: str | None = None) -> RequestSpec:
    """
    Build the request that creates a secret with its first version.
    """
    body: dict[str, str] = {"value": encoding.encode_value(value)}
    if description is not None:
        body["description"] = description
    return RequestSpec("POST", quote(name, safe=""), json=body)
```

## 2. Prefer `elif` over sequential `if`

When the second (and later) `if` is mutually exclusive with the first, use `elif`.

```python
# Bad
if value is None:
    return default
if value < 0:
    return 0

# Good
if value is None:
    return default
elif value < 0:
    return 0
```

## 3. Separate logical blocks; comment only the non-obvious

Split logical blocks with a blank line. When a block does something **unusual**, add a comment
**above** it explaining why. Do not comment self-evident code — separate it with whitespace only.

```python
# Good — comment explains a non-obvious server quirk.
def build_list() -> RequestSpec:
    """
    Build the request for listing all secrets.
    """
    # The ``?list=`` flag is mandatory and its value is ignored by the server; the root path
    # must end in a slash or the API returns ``404 page not found``.
    return RequestSpec("GET", "", params={LIST_QUERY_FLAG: "true"}, trailing_slash=True)

# Bad — comment restates the obvious.
# increment the counter
counter += 1
```

## 4. Docstrings always open on their own line

A docstring **always** starts with `"""` immediately followed by a newline; the description
begins on the next line; the closing `"""` is on its own line. No text after the opening quotes,
even for one-liners.

```python
# Bad
def get(self, name: str) -> Secret:
    """Fetch a secret by name."""

# Bad
def get(self, name: str) -> Secret:
    """Fetch a secret by name.
    """

# Good
def get(self, name: str) -> Secret:
    """
    Fetch a secret by name.
    """
```

## 5. Walrus operator when it stays readable

Use `:=` when it simplifies; drop it when it makes the expression harder to read.

```python
# Good
if token := os.environ.get("SEL_TOKEN"):
    return StaticTokenAuth(token)

# Bad — nesting + side effects make it hard to follow; use plain statements.
while (chunk := stream.read(size := pick_size(remaining, cap))) and validate(chunk, size):
    ...
```

## 6. One-line `if/else` only for a single condition

A ternary is allowed when there is exactly one condition. With more than one condition, use a
multi-line `if/else`.

```python
# Good
params = {"activate": "true"} if activate else None

# Bad — two conditions on one line.
mode = "rw" if writable and not locked else "ro"

# Good
if writable and not locked:
    mode = "rw"
else:
    mode = "ro"
```

## 7. Line length: 99 characters max

Enforced by ruff (`line-length = 99`).

## 8. Long argument lists: one argument per line

When arguments overflow, put **each** argument on its own line rather than wrapping several
onto one continuation line.

```python
# Bad
auth = PasswordAuth(identity_url=identity_url, account_id=account_id,
                    username=username, password=password, project_name=project_name)

# Good
auth = PasswordAuth(
    identity_url=identity_url,
    account_id=account_id,
    username=username,
    password=password,
    project_name=project_name,
)
```

## 9. Honor ruff and mypy semantics

Follow ruff and mypy unless a rule genuinely breaks the code's logic. When you must deviate,
use a **scoped** ignore with a reason.

```python
# pyperclip ships no type stubs; it is only used here behind a thin wrapper.
import pyperclip  # type: ignore[import-untyped]
```

## 10. Group declarations by kind; separate groups with a blank line

Types, constants, and variables may coexist, but each kind is its own block. No blank line
**between** items of the same kind; **one** blank line between different kinds.

```python
# Types, then constants, then variables (see rule 14), grouped:
ResponseBody: TypeAlias = dict[str, Any]

IDENTITY_URL_RU: str = "https://cloud.api.selcloud.ru/identity/v3"
IDENTITY_URL_INTL: str = "https://cloud.api.selcloud.com/identity/v3"
DEFAULT_INTERFACE: str = "public"

session: httpx.Client = httpx.Client()
attempts: int = 0
```

## 11. Annotate constants too

Type annotations are mandatory — including module-level constants.

```python
# Bad
DEFAULT_INTERFACE = "public"

# Good
DEFAULT_INTERFACE: str = "public"
LIST_QUERY_FLAG: str = "list"
```

## 13. Annotate class attributes; mirror them in `__init__`

Class attributes are annotated. In `__init__(self)`, the assigned attributes carry the same
types as their source arguments.

```python
class PasswordAuth(AuthProvider):
    def __init__(
        self,
        *,
        identity_url: str,
        account_id: str,
        username: str,
        password: str,
        project_name: str,
    ) -> None:
        super().__init__()
        self._identity_url: str = identity_url.rstrip("/")
        self._account_id: str = account_id
        self._username: str = username
        self._password: str = password
        self._project_name: str = project_name
```

## 14. Declaration order: types, then constants, then variables

Within a module or class body, declare type aliases first, constants second, variables last.
(Grouping/spacing follows rule 10.)

```python
ResponseBody: TypeAlias = dict[str, Any]

DEFAULT_TIMEOUT: httpx.Timeout = httpx.Timeout(30.0)

client: httpx.Client = httpx.Client(timeout=DEFAULT_TIMEOUT)
```

## 15. Member order within classes/modules

Strict order: **dunder methods → classmethods → staticmethods → properties → private methods →
public methods.**

```python
class SecretsManagerClient:
    # 1. dunder methods
    def __init__(self, config: Config, auth: AuthProvider) -> None: ...
    def __enter__(self) -> SecretsManagerClient: ...
    def __exit__(self, *exc: object) -> None: ...

    # 2. classmethods
    @classmethod
    def from_credentials(cls, ...) -> SecretsManagerClient: ...
    @classmethod
    def from_token(cls, ...) -> SecretsManagerClient: ...

    # 3. staticmethods
    @staticmethod
    def _check(response: httpx.Response) -> None: ...

    # 4. properties
    @property
    def _url(self) -> str: ...

    # 5. private methods
    def _body(self) -> dict[str, object]: ...

    # 6. public methods
    def close(self) -> None: ...
```

## 16. Use public/private members deliberately

Actively distinguish public vs. private (`_name`) attributes and variables. Reserve
name-mangled "protected" members (`__name`) for the rare cases that truly need it.

```python
class TokenCache:
    def __init__(self) -> None:
        self._token: Token | None = None   # internal state — private
        self.lock = threading.Lock()       # part of the public contract
```

## 17. f-strings everywhere

Use f-strings for interpolation, except where impossible or where they would overload the line.

```python
# Good
raise AuthenticationError(f"Keystone authentication failed (HTTP {response.status_code}).")

# Bad
raise AuthenticationError("Keystone authentication failed (HTTP %d)." % response.status_code)
```

## 18. Every module/package declares `__all__`

`__all__` lists exactly what may be imported. Place it among the other dunder names, with **no**
blank lines separating it from them.

```python
"""
Module docstring.
"""

from __future__ import annotations

from selectel_sm._core.request import RequestSpec

__all__ = ["AsyncSecretsResource", "SecretsResource"]
```
