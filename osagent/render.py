"""Rich rendering for CLI output. Kept apart from cli.py so commands stay thin."""
from __future__ import annotations

from rich.console import Console
from rich.markup import escape
from rich.table import Table


def render_checks(console: Console, results, version: str, host_os: str) -> None:
    table = Table(title=f"osagent {version} doctor  ({host_os})", title_style="bold",
                  header_style="dim", show_lines=False)
    table.add_column("", width=3)
    table.add_column("check", style="bold", no_wrap=True)
    table.add_column("detail", overflow="fold")
    for name, ok, detail in results:
        table.add_row("[green]OK[/]" if ok else "[red]XX[/]", name, detail)
    console.print(table)


def render_snapshot(console: Console, app: str, window: str, elements, total: int) -> None:
    console.print(f"[bold]frontmost:[/] {app or '<unknown>'}  [dim]|[/]  {window or '<no title>'}")
    console.print(f"[dim]{total} element(s) in the tree, showing {len(elements)}[/]")
    table = Table(header_style="dim", show_lines=False, box=None, pad_edge=False)
    table.add_column("id", style="dim", no_wrap=True)
    table.add_column("role", style="cyan", no_wrap=True)
    table.add_column("name", overflow="ellipsis", max_width=44)
    table.add_column("value", overflow="ellipsis", max_width=20, style="dim")
    table.add_column("bbox", style="dim", no_wrap=True)
    for el in elements:
        x, y, w, h = el.bbox
        table.add_row(el.id, el.role, _safe(el.name) or "[dim]-[/]", _safe(el.value),
                      f"{x},{y} {w}x{h}")
    console.print(table)


def _safe(s: str) -> str:
    """Element text is arbitrary app content: flatten it and never let Rich parse
    it as markup, or a control whose label contains [brackets] blows up the table."""
    if not s:
        return ""
    return escape(" ".join(s.split()))
