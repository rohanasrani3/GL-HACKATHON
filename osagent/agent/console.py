"""Rich console renderer for a live agent run, used by `osagent agent`."""
from __future__ import annotations

from rich.console import Console
from rich.markup import escape

ICON = {"start": "*", "step": ">", "perceive": "~", "think": "?", "action": "!",
        "actuate": " ", "reject": "x", "error": "x", "finish": "="}


def make_emitter(console: Console, verbose: bool = False):
    def emit(kind: str, data: dict) -> None:
        mark = ICON.get(kind, " ")
        if kind == "start":
            mode = "[cyan]DRY RUN[/]" if data["dry_run"] else "[red bold]LIVE[/]"
            console.print(f"\n{mode}  goal: [bold]{escape(data['goal'])}[/]")
            console.print(f"[dim]ESC aborts ({'armed' if data['kill_switch'] else 'UNAVAILABLE'}), "
                          f"max {data['max_steps']} steps[/]\n")
        elif kind == "step":
            console.rule(f"[dim]step {data['n']}/{data['max']}[/]", style="dim")
        elif kind == "perceive":
            console.print(f"[dim]{mark} {escape(data['app'])} - {escape(data['window'])[:50]} "
                          f"({data['count']} elements)[/]")
        elif kind == "think":
            if data.get("thought"):
                console.print(f"[magenta]{mark}[/] {escape(data['thought'])}")
        elif kind == "action":
            console.print(f"[bold yellow]{mark}[/] {escape(data['describe'])}")
        elif kind == "actuate" and verbose:
            console.print(f"[dim]    {data['verb']} {escape(str(data['detail']))}[/]")
        elif kind in ("reject", "error"):
            console.print(f"[red]{mark}[/] {escape(data['error'])}")
        elif kind == "finish":
            colour = {"done": "green", "failed": "red", "aborted": "yellow"}.get(data["status"], "yellow")
            console.print(f"\n[{colour} bold]{data['status'].upper()}[/] {escape(data['reason'])}")
            console.print(f"[dim]{data['steps']} steps, {data['llm_calls']} llm calls, "
                          f"{data['llm_tokens']} tokens, {data['elapsed_s']}s[/]")
    return emit
