"""Typer + rich command-line interface for Selectel Secrets Manager.

Command surface:

* auth/profiles: ``login``, ``logout``, ``whoami``, ``profile list|use|remove``;
* secrets: ``secrets list|get|create|set-description|delete``;
* versions: ``secrets version list|add|activate`` (reading a value lives **only** in
  ``secrets get NAME [--version ID]``).

``typer``/``rich`` are imported only under :mod:`selectel_sm.cli`, so the core library keeps no
hard dependency on them.
"""

from __future__ import annotations

import base64
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import typer

from selectel_sm import __version__
from selectel_sm.cli import keyring_store, output
from selectel_sm.cli.config import STORE_KEYRING, Profile, load_config
from selectel_sm.cli.context import (
    ENV_FIELDS,
    AppState,
    ResolvedProfile,
    build_client,
    mint_token,
    resolve_profile,
)
from selectel_sm.cli.errors import CLIError, handle_errors
from selectel_sm.config import IDENTITY_URL_RU

if TYPE_CHECKING:
    from selectel_sm.client import SecretsManagerClient
    from selectel_sm.resources.models import SecretVersion

app = typer.Typer(
    name="selectel-sm",
    help="Client for Selectel Secrets Manager.",
    no_args_is_help=True,
    add_completion=False,
)
profile_app = typer.Typer(help="Manage connection profiles.", no_args_is_help=True)
secrets_app = typer.Typer(help="Manage secrets.", no_args_is_help=True)
version_app = typer.Typer(help="Manage secret versions.", no_args_is_help=True)
app.add_typer(profile_app, name="profile")
app.add_typer(secrets_app, name="secrets")
secrets_app.add_typer(version_app, name="version")


# --------------------------------------------------------------------------------------------- #
# Root callback + shared helpers
# --------------------------------------------------------------------------------------------- #


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"selectel-sm {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    ctx: typer.Context,
    no_color: bool = typer.Option(False, "--no-color", help="Disable colored output."),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress non-essential messages."),
    _version: bool = typer.Option(
        False,
        "--version",
        help="Show the CLI version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    """Set up shared state for every command."""
    state = AppState(no_color=no_color, quiet=quiet, config=load_config())
    output.configure(state)
    ctx.obj = state


def _state(ctx: typer.Context) -> AppState:
    return cast("AppState", ctx.obj)


def _apply(
    state: AppState,
    *,
    profile: str | None = None,
    out: str | None = None,
    no_store: bool = False,
) -> None:
    """Fold per-command global flags into the shared state before resolution."""
    if profile is not None:
        state.profile = profile
    if out is not None:
        state.output = out
    if no_store:
        state.no_store = True


def _open(state: AppState) -> tuple[SecretsManagerClient, ResolvedProfile]:
    resolved = resolve_profile(state)
    return build_client(resolved), resolved


def _confirm(prompt: str, *, yes: bool) -> None:
    """Confirm a destructive action; fail closed when non-interactive without ``--yes``."""
    if yes:
        return
    if not sys.stdin.isatty():
        raise CLIError(
            "Refusing to proceed without confirmation: pass --yes (stdin is not a TTY).",
            exit_code=2,
        )
    if not typer.confirm(prompt):
        raise typer.Abort()


def _read_value(*, stdin: bool, file: str | None) -> bytes:
    """Read a secret value from --stdin, --file, or a hidden prompt (never a positional arg)."""
    if stdin and file is not None:
        raise CLIError("Use only one of --stdin or --file.", exit_code=2)
    if stdin:
        return sys.stdin.buffer.read()
    if file is not None:
        try:
            return Path(file).read_bytes()
        except OSError as exc:
            raise CLIError(f"Cannot read value file: {exc}", exit_code=2) from exc
    if not sys.stdin.isatty():
        raise CLIError(
            "No value provided: pass --stdin or --file (stdin is not a TTY).", exit_code=2
        )
    return str(typer.prompt("Secret value", hide_input=True)).encode()


def _require_field(value: str | None, label: str, prompt_text: str) -> str:
    """Return *value*, prompting for it when interactive, else failing with a clear message."""
    if value:
        return value
    if not sys.stdin.isatty():
        raise CLIError(f"Missing required field: {label}.", exit_code=2)
    return str(typer.prompt(prompt_text))


# --------------------------------------------------------------------------------------------- #
# Auth & profiles
# --------------------------------------------------------------------------------------------- #


@app.command()
@handle_errors
def login(
    ctx: typer.Context,
    profile: str | None = typer.Option(None, "--profile", help="Profile to create/update."),
    username: str | None = typer.Option(None, "--username"),
    account_id: str | None = typer.Option(None, "--account-id"),
    region: str | None = typer.Option(None, "--region", help="Region, e.g. 'ru-7'."),
    project: str | None = typer.Option(None, "--project", help="Project name."),
    interface: str | None = typer.Option(None, "--interface"),
) -> None:
    """Authenticate and persist a profile (config metadata + keyring secrets)."""
    state = _state(ctx)
    name = profile or state.config.default_profile or "default"

    region = _require_field(region, "region", "Region (e.g. ru-7)")
    account_id = _require_field(account_id, "account_id", "Account ID")
    project = _require_field(project, "project_name", "Project name")
    username = _require_field(username, "username", "Username")
    interface = interface or "public"
    existing = state.config.get(name)
    identity_url = os.environ.get(ENV_FIELDS["identity_url"]) or (
        existing.identity_url if existing else None
    )
    password = os.environ.get("SELECTEL_SM_PASSWORD") or typer.prompt("Password", hide_input=True)

    resolved = ResolvedProfile(
        name=name,
        region=region,
        account_id=account_id,
        project_name=project,
        username=username,
        interface=interface,
        identity_url=identity_url or IDENTITY_URL_RU,
        sm_base_url=None,
        store=STORE_KEYRING,
        env_token=None,
        ephemeral=False,
    )
    token, endpoint = mint_token(resolved, password)

    keyring_store.write_password(name, password)
    keyring_store.save_token(name, token, endpoint)
    state.config.upsert(
        Profile(
            name=name,
            region=region,
            account_id=account_id,
            project_name=project,
            username=username,
            store=STORE_KEYRING,
            interface=interface,
            identity_url=identity_url,
        )
    )
    if state.config.default_profile is None:
        state.config.default_profile = name
    state.config.save()

    output.print_info(
        f"[green]Logged in[/] as {username!r} on profile {name!r}. "
        f"Token expires at {token.expires_at.isoformat()}.",
        state,
    )


@app.command()
@handle_errors
def logout(
    ctx: typer.Context,
    profile: str | None = typer.Option(None, "--profile", help="Profile to clear."),
    all_profiles: bool = typer.Option(False, "--all", help="Clear secrets for every profile."),
) -> None:
    """Remove stored secrets from the keyring (profile metadata is kept)."""
    state = _state(ctx)
    if all_profiles:
        names = list(state.config.profiles)
        for profile_name in names:
            keyring_store.clear(profile_name)
        output.print_info(f"Cleared stored secrets for {len(names)} profile(s).", state)
        return
    name = profile or state.profile or state.config.default_profile
    if not name:
        raise CLIError("No profile to log out of. Pass --profile or --all.", exit_code=2)
    keyring_store.clear(name)
    output.print_info(f"Cleared stored secrets for profile {name!r}.", state)


@app.command()
@handle_errors
def whoami(
    ctx: typer.Context,
    profile: str | None = typer.Option(None, "--profile"),
    output_format: str = typer.Option("table", "-o", "--output", help="table|json."),
    no_store: bool = typer.Option(False, "--no-store"),
) -> None:
    """Show the active profile and its cached-token status."""
    state = _state(ctx)
    _apply(state, profile=profile, out=output_format, no_store=no_store)
    resolved = resolve_profile(state)

    source = "none"
    cached_at: datetime | None = None
    if resolved.env_token:
        source = "environment"
    elif resolved.persists:
        cached = keyring_store.load_token(resolved.name)
        if cached is not None:
            source = "keyring"
            cached_at = cached.expires_at

    remaining = (
        int((cached_at - datetime.now(UTC)).total_seconds()) if cached_at is not None else None
    )

    if state.json_output:
        output.print_json(
            {
                "profile": resolved.name,
                "ephemeral": resolved.ephemeral,
                "store": resolved.store,
                "region": resolved.region,
                "project_name": resolved.project_name,
                "username": resolved.username,
                "interface": resolved.interface,
                "token": {
                    "source": source,
                    "expires_at": cached_at.isoformat() if cached_at else None,
                    "expires_in_seconds": remaining,
                },
            }
        )
        return

    rows = [
        ("Profile", resolved.name + (" (ephemeral)" if resolved.ephemeral else "")),
        ("Store", resolved.store),
        ("Region", resolved.region),
        ("Project", resolved.project_name or "-"),
        ("Username", resolved.username or "-"),
        ("Interface", resolved.interface),
        ("Token source", source),
    ]
    if cached_at is not None:
        rows.append(("Token expires", output.format_datetime(cached_at)))
        rows.append(("Expires in", output.format_duration(remaining or 0)))
    output.console.print(output.key_value_table(rows))


@profile_app.command("list")
@handle_errors
def profile_list(
    ctx: typer.Context,
    output_format: str = typer.Option("table", "-o", "--output", help="table|json."),
) -> None:
    """List configured profiles."""
    state = _state(ctx)
    _apply(state, out=output_format)
    profiles = state.config.profiles
    default = state.config.default_profile

    def creds(prof: Profile) -> str:
        if prof.store != STORE_KEYRING:
            return "-"
        try:
            return "yes" if keyring_store.read_password(prof.name) is not None else "no"
        except CLIError:
            return "?"

    if state.json_output:
        output.print_json(
            [
                {
                    "name": prof.name,
                    "default": prof.name == default,
                    "region": prof.region,
                    "project_name": prof.project_name,
                    "store": prof.store,
                    "has_credentials": creds(prof),
                }
                for prof in profiles.values()
            ]
        )
        return

    if not profiles:
        output.print_info("No profiles configured. Run 'selectel-sm login'.", state)
        return

    from rich.table import Table

    table = Table(box=None)
    for column in ("", "Profile", "Region", "Project", "Store", "Creds"):
        table.add_column(column)
    for prof in profiles.values():
        marker = "*" if prof.name == default else " "
        table.add_row(
            marker,
            prof.name,
            prof.region or "-",
            prof.project_name or "-",
            prof.store,
            creds(prof),
        )
    output.console.print(table)


@profile_app.command("use")
@handle_errors
def profile_use(ctx: typer.Context, name: str = typer.Argument(...)) -> None:
    """Set the default profile."""
    state = _state(ctx)
    state.config.require(name)
    state.config.default_profile = name
    state.config.save()
    output.print_info(f"Default profile is now {name!r}.", state)


@profile_app.command("remove")
@handle_errors
def profile_remove(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    yes: bool = typer.Option(False, "--yes", help="Skip confirmation."),
) -> None:
    """Delete a profile entirely (config metadata + keyring secrets)."""
    state = _state(ctx)
    state.config.require(name)
    _confirm(f"Remove profile {name!r} and its stored secrets?", yes=yes)
    keyring_store.clear(name)
    state.config.remove(name)
    state.config.save()
    output.print_info(f"Removed profile {name!r}.", state)


# --------------------------------------------------------------------------------------------- #
# Secrets
# --------------------------------------------------------------------------------------------- #


@secrets_app.command("list")
@handle_errors
def secrets_list(
    ctx: typer.Context,
    profile: str | None = typer.Option(None, "--profile"),
    output_format: str = typer.Option("table", "-o", "--output", help="table|json."),
    no_store: bool = typer.Option(False, "--no-store"),
) -> None:
    """List secrets (metadata only — no values)."""
    state = _state(ctx)
    _apply(state, profile=profile, out=output_format, no_store=no_store)
    client, _ = _open(state)
    with client:
        summaries = client.secrets.list()

    if state.json_output:
        output.print_json(
            [
                {
                    "name": s.name,
                    "type": str(s.type),
                    "description": s.description,
                    "created_at": s.created_at.isoformat(),
                }
                for s in summaries
            ]
        )
        return

    if not summaries:
        output.print_info("No secrets.", state)
        return

    from rich.table import Table

    table = Table(box=None)
    for column in ("Name", "Description", "Created"):
        table.add_column(column, overflow="fold")
    for s in summaries:
        table.add_row(s.name, s.description or "-", output.format_datetime(s.created_at))
    output.console.print(table)


@secrets_app.command("get")
@handle_errors
def secrets_get(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    version: int | None = typer.Option(None, "--version", help="Read a specific version."),
    raw: bool = typer.Option(False, "--raw", help="Write raw value bytes to stdout (no newline)."),
    copy: bool = typer.Option(False, "--copy", help="Copy the value to the clipboard."),
    reveal: bool = typer.Option(False, "--reveal", help="Show the value instead of masking it."),
    profile: str | None = typer.Option(None, "--profile"),
    output_format: str = typer.Option("table", "-o", "--output", help="table|json."),
    no_store: bool = typer.Option(False, "--no-store"),
) -> None:
    """Read a secret. The value is masked unless --raw, --copy, or --reveal is given."""
    state = _state(ctx)
    _apply(state, profile=profile, out=output_format, no_store=no_store)
    if raw and copy:
        raise CLIError("Use only one of --raw or --copy.", exit_code=2)
    if raw and state.json_output:
        raise CLIError("--raw cannot be combined with -o json.", exit_code=2)

    client, _ = _open(state)
    with client:
        if version is not None:
            ver = client.secrets.get_version(name, version)
            value = ver.value
            description: str | None = None
            created_at = ver.created_at
            version_id: int | None = ver.version_id
        else:
            secret = client.secrets.get(name)
            value = secret.value
            description = secret.description
            created_at = secret.created_at
            version_id = secret.version.version_id if secret.version else None

    if raw:
        if value is None:
            raise CLIError("Secret has no value to output.", exit_code=1)
        output.write_raw(value)
        return
    if copy:
        if value is None:
            raise CLIError("Secret has no value to copy.", exit_code=1)
        output.copy_to_clipboard(value, name, state)
        return

    if state.json_output:
        payload: dict[str, Any] = {
            "name": name,
            "description": description,
            "created_at": created_at.isoformat(),
            "version_id": version_id,
        }
        if reveal and value is not None:
            payload["value"] = base64.b64encode(value).decode("ascii")
        output.print_json(payload)
        return

    rows = [("Name", name)]
    if description is not None:
        rows.append(("Description", description))
    if version_id is not None:
        rows.append(("Version", str(version_id)))
    rows.append(("Created", output.format_datetime(created_at)))
    rows.append(("Value", _value_cell(value, reveal=reveal)))
    output.console.print(output.key_value_table(rows))


def _value_cell(value: bytes | None, *, reveal: bool) -> str:
    if value is None:
        return "-"
    if not reveal:
        return output.MASK
    text, is_binary = output.decode_for_display(value)
    return f"{text}  (base64; binary)" if is_binary else text


@secrets_app.command("create")
@handle_errors
def secrets_create(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    description: str | None = typer.Option(None, "--description"),
    stdin: bool = typer.Option(False, "--stdin", help="Read the value from stdin."),
    file: str | None = typer.Option(None, "--file", help="Read the value from a file."),
    profile: str | None = typer.Option(None, "--profile"),
    no_store: bool = typer.Option(False, "--no-store"),
) -> None:
    """Create a secret with its first version (value via --stdin, --file, or prompt)."""
    state = _state(ctx)
    _apply(state, profile=profile, no_store=no_store)
    value = _read_value(stdin=stdin, file=file)
    client, _ = _open(state)
    with client:
        client.secrets.create(name, value, description=description)
    output.print_info(f"Created secret {name!r}.", state)


@secrets_app.command("set-description")
@handle_errors
def secrets_set_description(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    text: str | None = typer.Argument(None),
    clear: bool = typer.Option(False, "--clear", help="Clear the description."),
    profile: str | None = typer.Option(None, "--profile"),
    no_store: bool = typer.Option(False, "--no-store"),
) -> None:
    """Set or clear a secret's description."""
    state = _state(ctx)
    _apply(state, profile=profile, no_store=no_store)
    if clear and text is not None:
        raise CLIError("Pass either TEXT or --clear, not both.", exit_code=2)
    if not clear and text is None:
        raise CLIError("Provide a description TEXT or --clear.", exit_code=2)
    client, _ = _open(state)
    with client:
        client.secrets.update_description(name, None if clear else text)
    output.print_info(f"{'Cleared' if clear else 'Updated'} description for {name!r}.", state)


@secrets_app.command("delete")
@handle_errors
def secrets_delete(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    yes: bool = typer.Option(False, "--yes", help="Skip confirmation."),
    profile: str | None = typer.Option(None, "--profile"),
    no_store: bool = typer.Option(False, "--no-store"),
) -> None:
    """Delete a secret and all of its versions."""
    state = _state(ctx)
    _apply(state, profile=profile, no_store=no_store)
    _confirm(f"Delete secret {name!r} and all of its versions?", yes=yes)
    client, _ = _open(state)
    with client:
        client.secrets.delete(name)
    output.print_info(f"Deleted secret {name!r}.", state)


# --------------------------------------------------------------------------------------------- #
# Versions (management only — reading a value lives in `secrets get`)
# --------------------------------------------------------------------------------------------- #


@version_app.command("list")
@handle_errors
def version_list(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    profile: str | None = typer.Option(None, "--profile"),
    output_format: str = typer.Option("table", "-o", "--output", help="table|json."),
    no_store: bool = typer.Option(False, "--no-store"),
) -> None:
    """List a secret's versions (metadata only; marks the current one)."""
    state = _state(ctx)
    _apply(state, profile=profile, out=output_format, no_store=no_store)
    client, _ = _open(state)
    with client:
        sv = client.secrets.get_versions(name)

    if state.json_output:
        output.print_json(
            [
                {
                    "version_id": v.version_id,
                    "created_at": v.created_at.isoformat(),
                    "is_current": v.is_current,
                }
                for v in sv.versions
            ]
        )
        return

    if not sv.versions:
        output.print_info(f"Secret {name!r} has no versions.", state)
        return

    from rich.table import Table

    table = Table(box=None)
    for column in ("", "Version", "Created"):
        table.add_column(column)
    for v in sv.versions:
        table.add_row(
            "*" if v.is_current else " ",
            str(v.version_id),
            output.format_datetime(v.created_at),
        )
    output.console.print(table)


@version_app.command("add")
@handle_errors
def version_add(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    activate: bool = typer.Option(False, "--activate", help="Make the new version current."),
    stdin: bool = typer.Option(False, "--stdin", help="Read the value from stdin."),
    file: str | None = typer.Option(None, "--file", help="Read the value from a file."),
    profile: str | None = typer.Option(None, "--profile"),
    no_store: bool = typer.Option(False, "--no-store"),
) -> None:
    """Add a new version to an existing secret (value via --stdin, --file, or prompt)."""
    state = _state(ctx)
    _apply(state, profile=profile, no_store=no_store)
    value = _read_value(stdin=stdin, file=file)
    client, _ = _open(state)
    with client:
        ver: SecretVersion = client.secrets.create_version(name, value, activate=activate)
    suffix = " (now current)" if ver.is_current else ""
    output.print_info(f"Added version {ver.version_id} to {name!r}{suffix}.", state)


@version_app.command("activate")
@handle_errors
def version_activate(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    version_id: int = typer.Argument(...),
    profile: str | None = typer.Option(None, "--profile"),
    no_store: bool = typer.Option(False, "--no-store"),
) -> None:
    """Make a specific version current (no confirmation — the change is reversible)."""
    state = _state(ctx)
    _apply(state, profile=profile, no_store=no_store)
    client, _ = _open(state)
    with client:
        client.secrets.activate_version(name, version_id)
    output.print_info(f"Activated version {version_id} of {name!r}.", state)


if __name__ == "__main__":
    app()
