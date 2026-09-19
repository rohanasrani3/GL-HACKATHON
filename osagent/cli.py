"""osagent command line. Thin: every command delegates immediately."""
from __future__ import annotations

import sys
from pathlib import Path

import typer
from rich.console import Console

from . import __version__
from .config import CONFIG, HOST_OS

# UI labels are arbitrary app text and routinely contain glyphs cp1252 cannot
# encode, which would crash printing rather than the thing being printed.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

app = typer.Typer(add_completion=False, no_args_is_help=True,
                  help="Record a GUI task once, replay it deterministically, verify the result.")
console = Console()

NOT_YET = "[yellow]not implemented yet[/] - this lands in build step {n}."


@app.command()
def doctor(elements: int = typer.Option(25, help="How many UI elements to print."),
           delay: float = typer.Option(0.0, "--delay",
                                       help="Seconds to wait before the snapshot, so you can focus another app."),
           no_snapshot: bool = typer.Option(False, "--no-snapshot", help="Skip the live UI dump.")) -> None:
    """Check OS, permissions, deps and Ollama, then dump the frontmost app's UI tree."""
    from .doctor import run_checks, snapshot_frontmost
    from .render import render_checks, render_snapshot

    results = run_checks()
    render_checks(console, results, __version__, HOST_OS)
    if not no_snapshot:
        console.print()
        if delay:
            import time
            console.print(f"[dim]focus the app you want to inspect - snapshotting in {delay:g}s[/]")
            time.sleep(delay)
        try:
            render_snapshot(console, *snapshot_frontmost(elements))
        except Exception as e:
            console.print(f"[red]snapshot failed:[/] {type(e).__name__}: {e}")
            results.append(("snapshot", False, str(e)))
    failed = [name for name, ok, _ in results if not ok]
    if failed:
        console.print(f"\n[red]not ready[/] - fix: {', '.join(failed)}")
        raise typer.Exit(1)
    console.print("\n[green]ready[/]")


@app.command()
def record(name: str = typer.Argument(..., help="Recording name, saved to recordings/NAME.json")) -> None:
    """Record a demonstration. ESC stops."""
    console.print(NOT_YET.format(n=3) + f" (would write {CONFIG.dir('recordings') / (name + '.json')})")
    raise typer.Exit(1)


@app.command("compile")
def compile_cmd(name: str = typer.Argument(..., help="Recording name to compile.")) -> None:
    """Compile recordings/NAME.json into workflows/NAME.json using the LLM."""
    console.print(NOT_YET.format(n=6))
    raise typer.Exit(1)


@app.command()
def run(name: str = typer.Argument(..., help="Workflow name in workflows/."),
        input: Path | None = typer.Option(None, "--input", help="CSV of parameter rows."),
        dry_run: bool = typer.Option(True, "--dry-run/--execute",
                                     help="Dry run is the default; --execute really drives the UI."),
        yes: bool = typer.Option(False, "--yes", help="Skip confirmation on destructive steps."),
        no_overlay: bool = typer.Option(False, "--no-overlay", help="Do not draw the target highlight.")) -> None:
    """Replay a workflow. Dry run unless --execute is passed."""
    mode = "[cyan]DRY RUN[/]" if dry_run else "[red]EXECUTE[/]"
    console.print(f"{mode} {name}  input={input}  overlay={not no_overlay}  yes={yes}")
    console.print(NOT_YET.format(n=4))
    raise typer.Exit(1)


@app.command("replay-last")
def replay_last(dry_run: bool = typer.Option(True, "--dry-run/--execute")) -> None:
    """Re-run the most recently executed workflow."""
    console.print(NOT_YET.format(n=4))
    raise typer.Exit(1)


@app.command()
def ui(port: int = typer.Option(None, help="Override the configured port.")) -> None:
    """Serve the live trace dashboard."""
    console.print(f"would serve on :{port or CONFIG.ui.get('port', 8765)}")
    console.print(NOT_YET.format(n=7))
    raise typer.Exit(1)


@app.command()
def version() -> None:
    """Print the version and resolved configuration."""
    console.print(f"osagent {__version__} on {HOST_OS}")
    console.print(f"model: {CONFIG.model.provider}/{CONFIG.model.name} at {CONFIG.model.base_url}")
    console.print(f"config: {CONFIG.source or 'defaults'}")


if __name__ == "__main__":
    app()
