"""Typer + rich command-line interface.

Kept minimal for the foundation: just enough to prove the plumbing end-to-end (``version`` and
``auth check``). Secret/version commands arrive with the corresponding library operations.
``typer``/``rich`` are imported only here, so the core library has no hard dependency on them.
"""

from __future__ import annotations

import httpx
import typer
from rich.console import Console
from rich.table import Table

from selectel_sm import __version__
from selectel_sm._transport import _common
from selectel_sm.auth.password import PasswordAuth
from selectel_sm.config import IDENTITY_URL_RU, Config
from selectel_sm.exceptions import SelectelSMError

app = typer.Typer(
    name="selectel-sm",
    help="Client for Selectel Secrets Manager.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()
err_console = Console(stderr=True)


@app.command()
def version() -> None:
    """Print the installed selectel-sm version."""
    console.print(f"selectel-sm {__version__}")


@app.command("auth-check")
def auth_check(
    region: str = typer.Option(..., envvar="SELECTEL_REGION", help="Region, e.g. 'ru-7'."),
    account_id: str = typer.Option(..., envvar="SELECTEL_ACCOUNT_ID"),
    username: str = typer.Option(..., envvar="SELECTEL_USERNAME"),
    password: str = typer.Option(..., envvar="SELECTEL_PASSWORD", prompt=True, hide_input=True),
    project_name: str = typer.Option(..., envvar="SELECTEL_PROJECT"),
    interface: str = typer.Option("public", envvar="SELECTEL_INTERFACE"),
    identity_url: str = typer.Option(IDENTITY_URL_RU, envvar="SELECTEL_IDENTITY_URL"),
) -> None:
    """Authenticate and report the token expiry + resolved Secrets Manager endpoint.

    Useful for confirming credentials produce a *project-scoped* token and that the catalog
    contains an endpoint for the chosen region/interface.
    """
    config = Config(
        region=region,
        identity_url=identity_url,
        interface=interface,
        account_id=account_id,
        project_name=project_name,
    )
    auth = PasswordAuth(
        identity_url=identity_url,
        account_id=account_id,
        username=username,
        password=password,
        project_name=project_name,
    )
    try:
        with httpx.Client(timeout=config.timeout, verify=config.verify) as client:
            token = auth.authenticate(client)
            endpoint = _common.resolve_base(token, config)
    except SelectelSMError as exc:
        err_console.print(f"[bold red]Auth failed:[/] {exc}")
        raise typer.Exit(code=1) from exc

    table = Table(show_header=False, box=None)
    table.add_row("Project", token.project.name if token.project else "-")
    table.add_row("User", token.user.name if token.user else "-")
    table.add_row("Expires at", token.expires_at.isoformat())
    table.add_row("Region", region)
    table.add_row("SM endpoint", endpoint)
    console.print("[bold green]Authentication OK[/]")
    console.print(table)


if __name__ == "__main__":
    app()
