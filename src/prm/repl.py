"""Interactive REPL shell for prmanager.

Provides a persistent prompt where commands are entered with a leading '/',
e.g. `/list --state open`, `/sync`, `/show 42`. Each slash command maps to the
exact same command available on the regular `prm` CLI.
"""

from __future__ import annotations

import shlex

import typer
from rich.console import Console
from rich.table import Table

try:  # standalone click, if installed
    import click
except ImportError:  # typer >= 0.26 vendors click as typer._click
    from typer import _click as click  # type: ignore

try:  # line editing + history if available
    import readline  # noqa: F401
except ImportError:  # pragma: no cover - platform dependent
    pass

console = Console()

BANNER = r"""
[bold cyan]prmanager[/] interactive shell
Type [bold]/help[/] for commands, [bold]/quit[/] to exit. Prefix commands with '/'.
"""

# Meta commands handled by the REPL itself, not the CLI app.
_META = {"help", "?", "quit", "exit", "q"}


def _print_help(command: click.Group) -> None:
    table = Table(title="Slash commands", show_header=True, header_style="bold")
    table.add_column("Command", style="cyan", no_wrap=True)
    table.add_column("Description")
    for name in sorted(command.commands):
        cmd = command.commands[name]
        table.add_row(f"/{name}", (cmd.help or "").strip().split("\n")[0])
    table.add_row("/help", "Show this help.")
    table.add_row("/quit", "Exit the shell.")
    console.print(table)
    console.print(
        "[dim]Add --help to any command for its options, e.g. /list --help[/]"
    )


def run(app: typer.Typer) -> None:
    """Start the interactive shell for the given Typer app."""
    command = typer.main.get_command(app)
    console.print(BANNER)

    while True:
        try:
            raw = input("prm> ").strip()
        except EOFError:
            console.print()
            break
        except KeyboardInterrupt:
            console.print("\n[dim]^C — type /quit to exit[/]")
            continue

        if not raw:
            continue

        line = raw[1:].strip() if raw.startswith("/") else raw
        if not line:
            continue

        try:
            parts = shlex.split(line)
        except ValueError as e:
            console.print(f"[red]parse error:[/] {e}")
            continue

        verb = parts[0].lower()
        if verb in _META:
            if verb in ("quit", "exit", "q"):
                break
            _print_help(command)
            continue

        # Dispatch to the Click/Typer command set without exiting the process.
        try:
            command.main(args=parts, prog_name="prm", standalone_mode=False)
        except click.exceptions.Exit:
            pass
        except click.exceptions.Abort:
            console.print("[dim]aborted[/]")
        except click.ClickException as e:
            e.show()
        except SystemExit:
            pass

    console.print("[dim]bye[/]")
