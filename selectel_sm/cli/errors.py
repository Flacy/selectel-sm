"""Map the library's exception hierarchy to CLI exit codes and stderr rendering.

The exit-code contract is part of the CLI's public interface (scripts branch on it), so it lives
in one place. Errors are printed to *stderr* (human-readable) while machine output and secret
values go to stdout, keeping pipes clean.
"""

from __future__ import annotations

import functools
from typing import TYPE_CHECKING

import typer

from selectel_sm.exceptions import (
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

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = ["CLIError", "exit_code_for", "handle_errors", "render_error"]

# Most-specific first; the first matching ``isinstance`` wins. Subclasses of ``APIError``
# (Bad/Forbidden/NotFound/Conflict/Server) are siblings here, so ordering among them is moot, but
# they precede nothing they derive from. Anything not listed falls through to 1 ("unexpected").
_EXIT_CODES: tuple[tuple[type[SelectelSMError], int], ...] = (
    (AuthenticationError, 3),
    (NotFoundError, 4),
    (ForbiddenError, 5),
    (ConflictError, 6),
    (ServerError, 7),
    (BadRequestError, 8),
    (EndpointNotFoundError, 9),
    (TransportError, 10),
)


class CLIError(SelectelSMError):
    """A CLI-level failure that is not an API/transport error (bad usage, missing creds, ...).

    Carries its own exit code so call sites can choose the right one (e.g. 2 for usage, 3 when no
    credentials are available to authenticate with).
    """

    def __init__(self, message: str, *, exit_code: int = 1) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def exit_code_for(exc: SelectelSMError) -> int:
    """Return the CLI exit code for a library/CLI exception."""
    if isinstance(exc, CLIError):
        return exc.exit_code
    for exc_type, code in _EXIT_CODES:
        if isinstance(exc, exc_type):
            return code
    return 1


def render_error(exc: BaseException) -> None:
    """Print *exc* to stderr in red (plain when stderr is not a TTY / NO_COLOR)."""
    from selectel_sm.cli.output import err_console

    err_console.print(f"[bold red]Error:[/] {exc}")


def handle_errors[F: Callable[..., None]](func: F) -> F:
    """Wrap a command so library/CLI exceptions become a stderr message + mapped exit code."""

    @functools.wraps(func)
    def wrapper(*args: object, **kwargs: object) -> None:
        try:
            func(*args, **kwargs)
        except SelectelSMError as exc:
            render_error(exc)
            raise typer.Exit(code=exit_code_for(exc)) from exc

    return wrapper  # type: ignore[return-value]
