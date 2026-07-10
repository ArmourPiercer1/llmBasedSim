import pytest

import src.graph.game_graph as game_graph
from src.graph.game_graph import build_game_graph
from src.models.events import NarrativeOutput, PhysicsResolution, PlayerAction, PlayerPercept


class _PromptLoader:
    def render(self, _name, _context):
        return "prompt"


async def _fake_generate_structured(_llm, _messages, output_model, max_retries=2):
    if output_model is PlayerAction:
        return PlayerAction(
            raw_input="新行动",
            interpreted_intent="执行新行动",
            action_type="observe",
            action_description="执行新行动",
            duration_minutes=0.0,
            continue_until="",
        )
    if output_model is PhysicsResolution:
        return PhysicsResolution(outcomes=[])
    if output_model is PlayerPercept:
        return PlayerPercept(summary="感知摘要", senses=[])
    if output_model is NarrativeOutput:
        return NarrativeOutput(narrative="叙事文本")
    return output_model()


def _state(player_input):
    return {
        "tick": 0,
        "max_ticks": 10,
        "game_phase": "running",
        "player_input": player_input,
        "player": {"name": "测试者", "attributes": {}},
        "characters": {},
        "objects": {},
        "locations": {},
        "environment": {},
        "world_rules": {"tick_speed": {"default": 2.0, "max_minutes": 2.0}},
        "action_continuation": {
            "raw_input": "旧长任务",
            "interpreted_intent": "继续旧长任务",
            "action_type": "interact",
            "action_description": "继续旧长任务",
            "target_object_id": None,
            "feasibility": "allowed",
            "duration_minutes": 10.0,
            "continue_until": "done",
        },
        "event_log": [],
        "narrative_history": [],
    }


@pytest.mark.asyncio
async def test_continue_command_continues_long_task(monkeypatch):
    monkeypatch.setattr(game_graph, "generate_structured", _fake_generate_structured)
    graph = build_game_graph(None, _PromptLoader())

    result = await graph.ainvoke(_state("/c"), {"configurable": {"thread_id": "continue_long_task"}})

    assert "[系统] 继续长任务。" in result["event_log"]
    assert result["action_continuation"]["action_description"] == "继续旧长任务"


@pytest.mark.asyncio
async def test_non_continue_input_interrupts_long_task(monkeypatch):
    monkeypatch.setattr(game_graph, "generate_structured", _fake_generate_structured)
    graph = build_game_graph(None, _PromptLoader())

    result = await graph.ainvoke(_state("新行动"), {"configurable": {"thread_id": "interrupt_long_task"}})

    assert "[系统] 长任务已被新输入打断。" in result["event_log"]
    assert result["action_continuation"] is None
    assert any(event == "[玩家意图] 执行新行动" for event in result["event_log"])
