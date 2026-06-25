"""Shared status display for live pipeline progress during graph execution."""

from rich.console import Console, ConsoleOptions, RenderResult
from rich.live import Live
from rich.panel import Panel
from rich.text import Text


class TurnStatus:
    def __init__(self, console: Console):
        self._console = console
        self._live: Live | None = None
        self.step: str = ""
        self.sub_count: int = 0
        self.sub_total: int = 0

    def __rich_console__(self, _console: Console, _options: ConsoleOptions) -> RenderResult:
        text = Text(self.step or "等待中...", style="bold cyan")
        if self.sub_total > 0:
            text.append(f"  ({self.sub_count}/{self.sub_total})", style="dim")
        yield Panel(text, border_style="cyan", padding=(0, 2))

    def update(self, step: str, sub_count: int = 0, sub_total: int = 0):
        self.step = step
        self.sub_count = sub_count
        self.sub_total = sub_total
        if self._live:
            self._live.refresh()

    def live(self):
        self._live = Live(self, console=self._console, refresh_per_second=10, transient=True)
        return self._live
