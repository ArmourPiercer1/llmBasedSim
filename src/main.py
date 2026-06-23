"""Main entry point for the LLM-based multi-agent simulation game."""

import asyncio
import os
import sys
from pathlib import Path

import structlog
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from rich.console import Console

# Load .env from project root
_load_dotenv_path = Path(__file__).resolve().parent.parent / ".env"
if _load_dotenv_path.exists():
    load_dotenv(_load_dotenv_path)

from src.agents.init import init_game, init_file_to_game_state, load_init_file
from src.config.loader import ConfigLoader
from src.graph.game_graph import build_game_graph
from src.graph.game_state import reset_tick_transients
from src.prompts.loader import PromptLoader
from src.ui.cli import GameUI

logger = structlog.get_logger()
console = Console()


async def main():
    # Load config
    config_loader = ConfigLoader("config")
    sim_config = config_loader.load_simulation()

    # Check API key
    api_key_env = sim_config.llm.api_key_env
    api_key = os.environ.get(api_key_env)
    if not api_key:
        console.print(f"[red]错误: 环境变量 {api_key_env} 未设置[/red]")
        console.print(f"请设置: set {api_key_env}=your-deepseek-api-key")
        sys.exit(1)

    # Initialize services
    llm = ChatOpenAI(
        model=sim_config.llm.model,
        base_url=sim_config.llm.base_url,
        api_key=api_key,
        temperature=sim_config.llm.temperature,
        max_tokens=sim_config.llm.max_tokens,
    )
    prompt_loader = PromptLoader("prompts")
    ui = GameUI()

    # ── Init Phase ──
    init_file_arg = None
    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == "--init-file" and i + 1 < len(args):
            init_file_arg = args[i + 1]
            break

    if init_file_arg:
        ui.display_title("=== LLM 互动模拟游戏 ===\n")
        ui.display(f"[dim]从初始化文件加载: {init_file_arg}[/dim]")
        try:
            raw = load_init_file(init_file_arg)
            game_state = init_file_to_game_state(raw)
        except Exception as e:
            console.print(f"[red]加载初始化文件失败: {e}[/red]")
            logger.exception("init file load failed", error=str(e))
            sys.exit(1)
    else:
        ui.display_title("=== LLM 互动模拟游戏 ===\n")
        ui.display("[dim]欢迎！让我们先来设定你的游戏世界。[/dim]")

        try:
            game_state = await init_game(llm, prompt_loader, ui)
        except Exception as e:
            console.print(f"[red]初始化失败: {e}[/red]")
            logger.exception("init failed", error=str(e))
            sys.exit(1)

    # Show starting scene
    event_log = game_state.get("event_log", [])
    if event_log:
        starting_desc = event_log[0].replace("[系统] 游戏开始: ", "")
        ui.display(f"\n[bold green]{starting_desc}[/bold green]\n")

    # ── Build Game Graph ──
    graph = build_game_graph(llm, prompt_loader)

    max_ticks = game_state.get("max_ticks", 100)

    # ── Main Game Loop ──
    ui.display("\n[dim]输入 /quit 退出游戏，输入 /help 查看帮助[/dim]")

    current_state = game_state

    for tick_num in range(max_ticks):
        # Fresh thread_id per tick so the graph doesn't short-circuit at END
        thread_config = {"configurable": {"thread_id": f"tick_{tick_num}"}}
        try:
            result = await graph.ainvoke(current_state, thread_config)
        except Exception as e:
            console.print(f"[red]模拟出错 (tick {tick_num}): {e}[/red]")
            logger.exception("simulation error", tick=tick_num, error=str(e))
            break

        if result.get("game_phase") == "ended":
            break

        # Render player percept
        ui.render_percept(result.get("player_percept"))

        # Debug: show recent events
        debug_events = result.get("event_log", [])
        ui.render_debug(debug_events)

        # Collect player input
        player_input = await ui.collect_input()

        if player_input.strip().lower() in ("/quit", "/exit"):
            break
        if player_input.strip().lower() == "/help":
            ui.display("[dim]命令: /quit 退出, /help 帮助, /save 保存(未实现)[/dim]")
            player_input = None

        # Build next state from current result + player input
        current_state = reset_tick_transients(result, player_input)

    ui.display_goodbye()


if __name__ == "__main__":
    asyncio.run(main())
