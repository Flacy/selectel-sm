# selectel-sm

[![Tests](https://github.com/Flacy/selectel-sm/actions/workflows/tests.yml/badge.svg)](https://github.com/Flacy/selectel-sm/actions/workflows/tests.yml)
[![Lint](https://github.com/Flacy/selectel-sm/actions/workflows/lint.yml/badge.svg)](https://github.com/Flacy/selectel-sm/actions/workflows/lint.yml)
[![codecov](https://codecov.io/gh/Flacy/selectel-sm/branch/main/graph/badge.svg)](https://codecov.io/gh/Flacy/selectel-sm)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/selectel-sm)

A typed Python client for [Selectel Secrets Manager](https://docs.selectel.ru/api/secrets-manager/),
with both **synchronous and asynchronous** clients sharing a single transport-agnostic core.

> ## ⚠️ Disclaimer
>
> This is a **non-commercial, community project built out of pure enthusiasm**. I am **not** an
> employee of Selectel and have no affiliation with them whatsoever. I built this simply because
> I couldn't find a maintained library for working with Selectel's Secrets Manager.

## Installation

```bash
pip install selectel-sm          # library
pip install "selectel-sm[cli]"   # + CLI (typer + rich)
```

Requires Python 3.12+.

## Authentication

Secrets Manager requires a **project-scoped** IAM token. (The public docs mention an
account-scoped token, but in practice SM rejects it — a project-scoped token is required.) The
library obtains one for you from service-user credentials, caches it, and refreshes it before
expiry:

```python
from selectel_sm import SecretsManagerClient

with SecretsManagerClient.from_credentials(
    region="ru-7",
    account_id="123456",
    username="my-service-user",
    password="...",
    project_name="my-project",
) as client:
    secret = client.secrets.get("database_password")
    print(secret.value)  # -> b"..."
```

Or bring your own project-scoped token (the client introspects it to discover the service
catalog):

```python
client = SecretsManagerClient.from_token(region="ru-7", token="gAAAAAB...")
```

The async client mirrors the same API:

```python
from selectel_sm import AsyncSecretsManagerClient

async with AsyncSecretsManagerClient.from_credentials(region="ru-7", ...) as client:
    secret = await client.secrets.get("database_password")
```

## Endpoint resolution

The Secrets Manager URL is **not hardcoded**. After authenticating, the library reads the
service catalog returned in the Keystone token and resolves the `secrets-manager` endpoint for
the configured `region` and `interface` (default `public`). Set `sm_base_url` on the client to
bypass catalog resolution (e.g. for testing).

## Usage

All operations live under `client.secrets` (and identically on the async client with `await`).

### Secrets

```python
# Create a secret with its first version. `value` is plain data (bytes or str);
# it is base64-encoded for you before being sent.
client.secrets.create("api_key", "s3cr3t", description="Third-party API key")

# Read the current value.
secret = client.secrets.get("api_key")
secret.value          # b"s3cr3t"
secret.description    # "Third-party API key"  ("" from the API becomes None)
secret.version        # the current SecretVersion

# Update / clear the description (None clears it).
client.secrets.update_description("api_key", "Rotated key")

# List all secrets (metadata only — no values).
for summary in client.secrets.list():
    print(summary.name, summary.type, summary.description, summary.created_at)

# Delete a secret and all of its versions.
client.secrets.delete("api_key")
```

### Versions

```python
# Add a new version. Pass activate=True to make it the current version.
client.secrets.create_version("api_key", "rotated-secret", activate=True)

# The secret plus metadata for all of its versions (no values).
sv = client.secrets.get_versions("api_key")
sv.versions           # tuple[SecretVersion, ...]
sv.current            # the version flagged is_current, if any

# A single version, including its value.
version = client.secrets.get_version("api_key", version_id=1)
version.value         # b"..."

# Make a specific version current.
client.secrets.activate_version("api_key", version_id=1)
```

### Error handling

Every error derives from `SelectelSMError`, so you can catch broadly or narrowly:

```python
from selectel_sm import NotFoundError, SelectelSMError

try:
    client.secrets.get("does-not-exist")
except NotFoundError:
    ...
except SelectelSMError:
    ...
```

HTTP statuses map to `BadRequestError` (400), `ForbiddenError` (403), `NotFoundError` (404),
`ConflictError` (409), and `ServerError` (5xx). Authentication and endpoint-resolution problems
raise `AuthenticationError` and `EndpointNotFoundError` respectively.

## A note on quirks

Selectel's Secrets Manager API has a few undocumented behaviors this client handles for you,
for example:

- Listing requires a `?list=<any value>` flag **and** a trailing slash (`/v1/?list=true`),
  otherwise it returns `404 page not found`.
- Secret values must be valid base64 — the client always encodes plain input for you.
- `activate version` is documented as `204 No Content` but actually returns `200` with the
  version's metadata.

## Support & maintenance

Because I don't work with Selectel, **I may not be aware of the latest changes to their API, and
something could break unexpectedly.** I do my best to keep this library up to date, but that
isn't always possible. Contributions, bug reports, and help with its development are very
welcome — please open an issue or a pull request.

## Development

```bash
uv sync
uv run ruff check . && uv run ruff format --check .
uv run mypy selectel_sm
uv run pytest
```

## License

[MIT](LICENSE) © Andrew Krylov
