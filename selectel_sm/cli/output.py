"""Rendering: human (rich) tables, machine JSON, masking, ``--raw`` bytes, and clipboard.

A secrets tool must never splat a value into a terminal/log by accident, so:

* values are **masked** by default (human and JSON output alike);
* ``--reveal`` opts in to showing the value;
* ``--raw`` writes the *raw value bytes* to stdout with no trailing newline (the ``$(...)`` capture
  mode), so binary values survive and pipes stay byte-exact;
* ``--copy`` puts the value on the clipboard and prints nothing sensitive.

Human output auto-simplifies when stdout is not a TTY and honors ``NO_COLOR``/``--no-color``.
"""

from __future__ import annotations

import base64
import json
import sys
from typing import TYPE_CHECKING, Any

from rich.console import Console
from rich.table import Table

from selectel_sm.cli.errors import CLIError

if TYPE_CHECKING:
    from datetime import datetime

    from selectel_sm.cli.context import AppState

__all__ = [
    "MASK",
    "configure",
    "console",
    "copy_to_clipboard",
    "decode_for_display",
    "err_console",
    "format_datetime",
    "format_duration",
    "key_value_table",
    "print_info",
    "print_json",
    "write_raw",
]

MASK = "••••••"


def format_datetime(value: datetime) -> str:
    """Render a UTC timestamp in the machine's **local** time, human-readably.

    e.g. ``11 Jun 2026, 18:03:55``. Timestamps from the API are UTC; ``astimezone()`` (with no
    argument) converts to the local zone. Used for human (table) output only — JSON keeps ISO.
    """
    return value.astimezone().strftime("%d %b %Y, %H:%M:%S")


def format_duration(seconds: int) -> str:
    """Render a span of *seconds* as e.g. ``23h 59m 23s`` (``expired`` when non-positive)."""
    if seconds <= 0:
        return "expired"
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if secs or not parts:
        parts.append(f"{secs}s")
    return " ".join(parts)


# Rich detects TTY/NO_COLOR on its own; ``configure`` rebuilds these to honor ``--no-color``.
console = Console()
err_console = Console(stderr=True)


def configure(state: AppState) -> None:
    """Rebuild the shared consoles from global flags (``--no-color``)."""
    global console, err_console
    no_color = state.no_color or None
    console = Console(no_color=no_color)
    err_console = Console(stderr=True, no_color=no_color)


def print_info(message: str, state: AppState) -> None:
    """Print a non-sensitive notice to stderr (suppressed by ``--quiet``), keeping stdout clean."""
    if not state.quiet:
        err_console.print(message)


def print_json(obj: Any) -> None:
    """Print machine JSON to stdout (compact, stable key order)."""
    console.print_json(json.dumps(obj))


def key_value_table(rows: list[tuple[str, str]]) -> Table:
    """Build a borderless two-column table for human key/value output."""
    table = Table(show_header=False, box=None)
    table.add_column(style="bold")
    table.add_column(overflow="fold")
    for key, value in rows:
        table.add_row(key, value)
    return table


def decode_for_display(value: bytes) -> tuple[str, bool]:
    """Return (*text*, *is_binary*): UTF-8 text when decodable, else base64 with a binary flag."""
    try:
        return value.decode("utf-8"), False
    except UnicodeDecodeError:
        return base64.b64encode(value).decode("ascii"), True


def write_raw(value: bytes) -> None:
    """Write raw value bytes to stdout with **no** trailing newline."""
    sys.stdout.buffer.write(value)
    sys.stdout.buffer.flush()


def copy_to_clipboard(value: bytes, name: str, state: AppState) -> None:
    """Copy a value to the clipboard; never echo it. Fails clearly if unsupported/binary."""
    import pyperclip  # local import: only needed for --copy, keeps cold start cheap

    text, is_binary = decode_for_display(value)
    if is_binary:
        raise CLIError(
            "Value is binary and cannot be placed on the clipboard as text. "
            "Use --raw or --file instead.",
            exit_code=1,
        )
    try:
        pyperclip.copy(text)
    except pyperclip.PyperclipException as exc:
        raise CLIError(
            "Clipboard is unavailable. On Linux install xclip, xsel, or wl-clipboard, "
            f"or use --raw. ({exc})",
            exit_code=1,
        ) from exc
    print_info(f"Copied value of {name!r} to clipboard.", state)
