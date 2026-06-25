"""Render PlayerPercept to Rich formatted output."""

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

console = Console()


def render_percept(percept: dict | None) -> None:
    """Render a PlayerPercept dict as formatted terminal output."""
    if not percept:
        console.print("[dim](你什么也没有感知到)[/dim]")
        return

    # ── Self-action panel (what the player character actually did) ──
    self_action = percept.get("self_action_summary", "")
    if self_action:
        self_panel = Panel(
            self_action,
            title="[bold yellow]你做了什么[/bold yellow]",
            border_style="yellow",
            padding=(1, 2),
        )
        console.print(self_panel)
        console.print()

    summary = percept.get("summary", "")
    senses = percept.get("senses", [])
    hidden = percept.get("hidden_event_count", 0)

    sense_icons = {
        "sight": "[看]",
        "sound": "[听]",
        "smell": "[闻]",
        "touch": "[触]",
    }

    lines = []
    for s in senses:
        sense_type = s.get("sense", "")
        desc = s.get("description", "")
        icon = sense_icons.get(sense_type, "*")
        confidence = s.get("confidence", 1.0)
        if confidence < 1.0:
            lines.append(f"[dim]{icon} {desc} (不太确定)[/dim]")
        else:
            lines.append(f"{icon} {desc}")

    content = "\n".join(lines) if lines else summary
    if summary and lines:
        content = f"[bold]{summary}[/bold]\n\n{content}"

    panel = Panel(
        content,
        title=f"[bold green]你感知到的[/bold green]",
        border_style="green",
        padding=(1, 2),
    )
    console.print(panel)

    if hidden > 0:
        console.print(f"[dim](有 {hidden} 件事发生了，但你没有察觉)[/dim]")


def render_event_log(event_log: list[str], max_lines: int = 5) -> None:
    """Render the most recent events from the event log for debugging."""
    if not event_log:
        return
    recent = event_log[-max_lines:]
    console.print("\n[dim]── 最近事件（调试）──[/dim]")
    for e in recent:
        console.print(f"[dim]  {e}[/dim]")
