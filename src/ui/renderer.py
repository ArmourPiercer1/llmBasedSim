"""Render PlayerPercept to Rich formatted output."""

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

console = Console()


def _format_attribute_value(attr: dict) -> str:
    value = attr.get("value", 0)
    maximum = attr.get("max")
    unit = attr.get("unit", "")
    if isinstance(value, list):
        value_text = ", ".join(str(v) for v in value) if value else "(无)"
    elif isinstance(value, bool):
        value_text = "是" if value else "否"
    elif isinstance(value, str):
        value_text = value
    else:
        try:
            value_text = f"{float(value):g}"
        except (TypeError, ValueError):
            value_text = str(value)
    if maximum is not None:
        try:
            text = f"{value_text}/{float(maximum):g}"
        except (TypeError, ValueError):
            text = f"{value_text}/{maximum}"
    else:
        text = value_text
    if unit:
        text += f" {unit}"
    return text


def _format_attribute_lines(attributes: dict, *, include_hidden: bool = False) -> list[str]:
    lines = []
    for key, attr in attributes.items():
        if not isinstance(attr, dict):
            continue
        if attr.get("hidden") and not include_hidden:
            continue
        name = attr.get("name") or key
        hidden_marker = " [dim](hidden)[/dim]" if attr.get("hidden") else ""
        lines.append(f"[cyan]{name}[/cyan]: {_format_attribute_value(attr)}{hidden_marker}")
    return lines


def render_percept(percept: dict | None) -> None:
    """Render a PlayerPercept dict as formatted terminal output.

    Only the narrative text and player attributes are shown by default.
    Self-action is hidden — use /idid to see it.
    """
    if not percept:
        console.print("[dim](你什么也没有感知到)[/dim]")
        return

    player_attributes = percept.get("player_attributes", {})

    if player_attributes:
        attr_lines = _format_attribute_lines(player_attributes)
        if attr_lines:
            attr_panel = Panel(
                "\n".join(attr_lines),
                title="[bold cyan]你的状态[/bold cyan]",
                border_style="cyan",
                padding=(1, 2),
            )
            console.print(attr_panel)
            console.print()

    narrative = percept.get("narrative", "")
    if narrative:
        panel = Panel(
            narrative,
            title="[bold green]你感知到的[/bold green]",
            border_style="green",
            padding=(1, 2),
        )
        console.print(panel)
    else:
        summary = percept.get("summary", "")
        senses = percept.get("senses", [])
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
            title="[bold green]你感知到的[/bold green]",
            border_style="green",
            padding=(1, 2),
        )
        console.print(panel)

    hidden = percept.get("hidden_event_count", 0)
    if hidden > 0:
        console.print(f"[dim](有 {hidden} 件事发生了，但你没有察觉)[/dim]")


def render_status(state: dict) -> None:
    """Render player numeric attributes on demand."""
    player = state.get("player", {}) if isinstance(state, dict) else {}
    attributes = player.get("attributes", {}) if isinstance(player, dict) else {}
    lines = _format_attribute_lines(attributes, include_hidden=True)
    if not lines:
        lines = ["[dim]当前没有可显示的玩家数值属性。[/dim]"]
    title_name = player.get("name", "玩家") if isinstance(player, dict) else "玩家"
    panel = Panel(
        "\n".join(lines),
        title=f"[bold cyan]{title_name}的数值状态[/bold cyan]",
        border_style="cyan",
        padding=(1, 2),
    )
    console.print(panel)


def render_self_action(percept: dict | None) -> None:
    """Render what the player character actually did this turn."""
    if not percept:
        console.print("[dim](你什么也没有做)[/dim]")
        return
    self_action = percept.get("self_action_summary", "")
    if not self_action:
        console.print("[dim](你本回合没有特别的行为)[/dim]")
        return
    panel = Panel(
        self_action,
        title="[bold yellow]你做了什么[/bold yellow]",
        border_style="yellow",
        padding=(1, 2),
    )
    console.print(panel)


def render_attribute_debug(state: dict) -> None:
    """Render player and NPC attributes for debug mode."""
    if not isinstance(state, dict):
        return
    sections = []
    player = state.get("player", {}) if isinstance(state.get("player"), dict) else {}
    player_lines = _format_attribute_lines(player.get("attributes", {}), include_hidden=True)
    if player_lines:
        sections.append(f"[bold]玩家 {player.get('name', '玩家')}[/bold]\n" + "\n".join(f"  {line}" for line in player_lines))

    npc_sections = []
    characters = state.get("characters", {}) if isinstance(state.get("characters"), dict) else {}
    for cid, char in characters.items():
        if not isinstance(char, dict):
            continue
        lines = _format_attribute_lines(char.get("attributes", {}), include_hidden=True)
        if lines:
            npc_sections.append(f"[bold]{char.get('name', cid)}[/bold] ({cid})\n" + "\n".join(f"  {line}" for line in lines))
    sections.extend(npc_sections)

    if sections:
        console.print("\n[dim]── 数值状态（调试）──[/dim]")
        for section in sections:
            console.print(section)


def render_event_log(event_log: list[str], max_lines: int = 5) -> None:
    """Render the most recent events from the event log for debugging."""
    if not event_log:
        return
    recent = event_log[-max_lines:]
    console.print("\n[dim]── 最近事件（调试）──[/dim]")
    for e in recent:
        console.print(f"[dim]  {e}[/dim]")


_SENSE_LABELS: dict[str, str] = {
    "sight": "看到",
    "sound": "听到",
    "smell": "闻到",
    "touch": "触到",
}

_SENSE_COLORS: dict[str, str] = {
    "sight": "cyan",
    "sound": "yellow",
    "smell": "magenta",
    "touch": "blue",
}


def render_sense_category(percept: dict | None, sense_type: str) -> None:
    """Render only the sense entries of a specific type (sight/sound/smell/touch)."""
    if not percept:
        console.print("[dim](你什么也没有感知到)[/dim]")
        return

    senses = percept.get("senses", [])
    filtered = [s for s in senses if s.get("sense") == sense_type]

    label = _SENSE_LABELS.get(sense_type, sense_type)
    color = _SENSE_COLORS.get(sense_type, "white")

    if not filtered:
        console.print(f"[dim](你没有{label}任何特别的东西)[/dim]")
        return

    lines = []
    for s in filtered:
        desc = s.get("description", "")
        confidence = s.get("confidence", 1.0)
        if confidence < 1.0:
            lines.append(f"[dim]{desc} (不太确定)[/dim]")
        else:
            lines.append(desc)

    panel = Panel(
        "\n".join(lines),
        title=f"[bold {color}]你{label}的[/bold {color}]",
        border_style=color,
        padding=(1, 2),
    )
    console.print(panel)
