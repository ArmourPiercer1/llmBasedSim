"""Interactive CLI for the game using Rich."""

import asyncio
from typing import Any

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt

from src.ui.renderer import render_percept, render_event_log, render_status, render_attribute_debug

console = Console()


class GameUI:
    """Terminal-based game UI using Rich."""

    def display_title(self, text: str) -> None:
        console.print(f"[bold blue]{text}[/bold blue]")

    def display(self, text: str) -> None:
        console.print(text)

    def display_markdown(self, text: str) -> None:
        md = Markdown(text)
        console.print(md)

    def render_percept(self, percept: dict[str, Any] | None) -> None:
        render_percept(percept)

    def render_debug(self, state: dict[str, Any]) -> None:
        render_event_log(state.get("event_log", []))
        render_attribute_debug(state)

    def render_status(self, state: dict[str, Any]) -> None:
        render_status(state)

    async def collect_input(self, prompt: str = "\n[bold yellow]> [/bold yellow]") -> str:
        """Collect player input asynchronously."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: Prompt.ask(prompt, console=console)
        )

    def display_goodbye(self) -> None:
        console.print("\n[bold blue]感谢游玩！再见。[/bold blue]")
