"""P0-T03 characterization 测试共享工具：FakeLLM、canned JSON 构造器、状态工厂。

本模块为 `src/graph/game_graph.py` 11 节点流程的 behavior-characterization 测试
提供可配置的 LLM 替身。设计原则：

- FakeLLM 工作在 `llm.ainvoke(messages)` 层（而不是 monkeypatch
  `generate_structured`），因此 `src/llm/parser.py::generate_structured` 的
  JSON 提取、Pydantic 校验与"解析失败重试（max_retries=2）"逻辑全部被真实执行。
- 路由依据 messages[0]（SystemMessage）内容中的唯一标记：每个图节点使用不同的
  system 模板，渲染结果包含可区分的开头句；character_system.j2 还包含
  ``- 名字：{{ name }}``，可按 NPC 名字精确路由。
- 每条路由是一个响应队列；队列耗尽后重复最后一个响应（sticky），便于
  "前 N 次返回垃圾 JSON、之后恢复"或"永远失败"这类场景。
- 响应可以是：JSON 字符串（包成 AIMessage 返回）、Exception 实例/类（抛出，
  模拟网络/API 失败）、或 callable(messages, call_index)（动态生成）。

Characterization 纪律：本文件与配套测试只记录 v1 当前行为；看起来像 bug 的
行为按现状断言，并在注释中标记 ``known-bug-candidate``。
"""

from __future__ import annotations

import uuid
from collections import Counter
from typing import Any, Callable

from langchain_core.messages import AIMessage

from src.graph.game_graph import build_game_graph
from src.models.events import (
    ActionIntent,
    AttributeChange,
    AttributeUpdateResolution,
    NarrativeOutput,
    PhysicsOutcome,
    PhysicsResolution,
    PlayerAction,
    PlayerPercept,
    SenseDetail,
)
from src.prompts.loader import PromptLoader

# ── 路由标记（各节点 system prompt 的唯一开头句） ──────────────────────────
M_INTENT = "你是玩家输入处理器"            # player_intent_process
M_RESOLVE = "你是玩家行动可行性处理器"      # player_action_resolve
M_CHAR = "你是一个角色扮演引擎"            # characters_all_decide（通用）
M_PHYSICS = "你是一个确定性物理模拟引擎"    # physics_resolve
M_ATTR = "你是角色属性更新引擎"            # attribute_update
M_SENSORY = "你是一个感官模拟引擎"         # sensory_filter
M_NARRATIVE = "你是一位文学叙事者"         # narrative_stylize

# 无法提取出 JSON 的垃圾回复（无花括号 → parser 回退原文 → Pydantic 校验失败）
GARBAGE = "抱歉，我无法按要求输出结构化结果。"


class FakeLLM:
    """满足 generate_structured 调用约定（async ainvoke → 含 JSON 字符串的消息）。"""

    def __init__(self, routes: dict[str, list[Any]] | None = None, default: Any = None):
        # dict 保序：按插入顺序匹配第一个命中的标记
        self.routes: dict[str, list[Any]] = dict(routes or {})
        self.default = default
        self.calls: list[tuple[str | None, list]] = []  # (matched_marker, messages)
        self._counts: Counter[str] = Counter()

    async def ainvoke(self, messages):
        sys_text = messages[0].content if messages else ""
        matched = None
        for marker in self.routes:
            if marker in sys_text:
                matched = marker
                break
        self.calls.append((matched, messages))
        if matched is None:
            if self.default is None:
                raise AssertionError(f"FakeLLM: 无匹配路由，system prompt 开头: {sys_text[:60]!r}")
            resp: Any = self.default
            idx = 0
        else:
            idx = self._counts[matched]
            self._counts[matched] += 1
            queue = self.routes[matched]
            resp = queue[min(idx, len(queue) - 1)]  # sticky last
        if callable(resp):
            resp = resp(messages, idx)
        if isinstance(resp, BaseException):
            raise resp
        if isinstance(resp, type) and issubclass(resp, BaseException):
            raise resp()
        return AIMessage(content=resp)

    # ── 断言辅助 ──
    def call_count(self, marker: str) -> int:
        return self._counts.get(marker, 0)

    def calls_for(self, marker: str) -> list[list]:
        return [msgs for mk, msgs in self.calls if mk == marker]

    def user_prompt_of(self, marker: str, call_index: int = 0) -> str:
        """返回某路由第 N 次调用的最后一条消息内容（user prompt + JSON 指令）。"""
        msgs = self.calls_for(marker)[call_index]
        return msgs[-1].content


# ── canned JSON 构造器 ─────────────────────────────────────────────────────

def player_action_json(**overrides: Any) -> str:
    base: dict[str, Any] = dict(
        interpreted_intent="默认意图",
        action_type="observe",
        action_description="默认行动",
        duration_minutes=0.0,
        continue_until="",
    )
    base.update(overrides)
    return PlayerAction(**base).model_dump_json()


def intent_json(character_id: str = "npc1", **overrides: Any) -> str:
    base: dict[str, Any] = dict(
        character_id=character_id,
        action_type="wait",
        action_description="原地等待",
    )
    base.update(overrides)
    return ActionIntent(**base).model_dump_json()


def physics_json(outcomes: list[dict[str, Any]] | None = None, reasoning: str = "") -> str:
    return PhysicsResolution(
        outcomes=[PhysicsOutcome(**o) for o in (outcomes or [])],
        reasoning=reasoning,
    ).model_dump_json()


def attr_update_json(changes: list[dict[str, Any]] | None = None, reasoning: str = "") -> str:
    return AttributeUpdateResolution(
        changes=[AttributeChange(**c) for c in (changes or [])],
        reasoning=reasoning,
    ).model_dump_json()


def percept_json(**overrides: Any) -> str:
    senses = [SenseDetail(**s) for s in overrides.pop("senses", [])]
    base: dict[str, Any] = dict(summary="默认感知摘要", hidden_event_count=0)
    base.update(overrides)
    return PlayerPercept(senses=senses, **base).model_dump_json()


def narrative_json(text: str) -> str:
    return NarrativeOutput(narrative=text).model_dump_json()


# ── 状态工厂 ───────────────────────────────────────────────────────────────

def make_char(
    char_id: str,
    name: str,
    pos: dict[str, float],
    traits: list[str] | None = None,
    attributes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """构造贴近真实剧本加载结果的 NPC dict。

    注意：真实剧本经 src/agents/init.py 加载后，character dict 会保留 YAML 中的
    ``position`` 键（character_positions 另行存放权威坐标）。character_user.j2 /
    sensory_user.j2 模板直接访问 ``char.position.x``，因此该键缺失会导致相应节点
    降级（known-bug-candidate，见配套测试）。
    """
    return {
        "character_id": char_id,
        "name": name,
        "position": dict(pos),
        "personality": {
            "traits": traits or ["冷静"],
            "motivations": ["观察周围"],
            "speech_style": "平稳",
            "background": f"{name}的背景故事",
        },
        "speech_examples": [],
        "relationships": {},
        "attributes": (
            attributes if attributes is not None
            else {"mood": {"name": "心情", "value": 50, "max": 100}}
        ),
        "memory": [],
        "inventory": [],
    }


def make_base_state(**overrides: Any) -> dict[str, Any]:
    """E2E 可用的完整 GameState（字段命名与真实剧本加载一致）。"""
    state: dict[str, Any] = {
        "tick": 0,
        "max_ticks": 100,
        "game_phase": "running",
        "player_input": "环顾四周",
        "player": {
            "name": "测试者",
            "position": {"x": 0, "y": 0, "z": 0},
            "capabilities": {"sight_range_m": 50, "hearing_range_m": 100},
            "physical_profile": {},
            "attributes": {
                "stamina": {"name": "体力", "value": 80, "max": 100},
                # hidden 属性：用于验证 visible_player_attributes 过滤
                "sanity": {"name": "理智", "value": 50, "max": 100, "hidden": True},
            },
            "inventory": [],
        },
        "characters": {
            "npc1": make_char("npc1", "艾拉", {"x": 2, "y": 0, "z": 0}, ["好奇"]),
            "npc2": make_char("npc2", "布鲁诺", {"x": 5, "y": 0, "z": 0}, ["沉稳"]),
        },
        "character_positions": {
            "npc1": {"x": 2, "y": 0, "z": 0},
            "npc2": {"x": 5, "y": 0, "z": 0},
        },
        "objects": {
            "crate": {
                "object_id": "crate",
                "name": "木箱",
                "description": "一只普通的木箱",
                "position": {"x": 1, "y": 0, "z": 0},
                "state": {},
                "properties": {"portable": True},
            },
        },
        "locations": {
            "square": {"name": "广场", "description": "开阔的广场", "objects": ["crate"]},
        },
        "environment": {"time_of_day": "上午", "weather": "晴", "temperature_c": 20.0},
        "world_rules": {"tick_speed": {"default": 2.0, "min_minutes": 0.1, "max_minutes": 30.0}},
        "narrative_style": {"style_description": "测试风格", "style_example": "样例文本"},
        # 带 day 键，用于刻画 advance_game_time 丢弃 day 的行为（known-bug-candidate）
        "game_time": {"day": 1, "hour": 8, "minute": 0},
        "ticks_per_game_minute": 0.2,
        "event_log": ["[初始] 游戏开始"],
        "narrative_history": [],
        "action_intents": [],
    }
    state.update(overrides)
    return state


def default_routes() -> dict[str, list[Any]]:
    """与 make_base_state 配套的 7 条路由（物理路由实际不会被调用，见 F821 测试）。"""
    return {
        M_INTENT: [player_action_json(
            interpreted_intent="环顾四周",
            action_type="observe",
            action_description="环顾四周",
        )],
        M_RESOLVE: [player_action_json(
            interpreted_intent="环顾四周",
            action_type="observe",
            action_description="环顾四周",
            feasibility="allowed",
            feasibility_reason="可以",
        )],
        "名字：艾拉": [intent_json(
            "npc1", action_type="speak", action_description="向布鲁诺问好",
            target_character_id="npc2", emotion="友好", duration_minutes=1.0,
        )],
        "名字：布鲁诺": [intent_json(
            "npc2", action_type="move", action_description="走向木箱",
            target_position={"x": 1, "y": 0, "z": 0}, duration_minutes=3.0,
        )],
        M_ATTR: [attr_update_json(changes=[
            {"entity_type": "player", "attribute_key": "stamina", "delta": -2.0, "reason": "累了"},
        ])],
        M_PHYSICS: [physics_json(outcomes=[
            {"outcome_type": "sound", "description": "风声掠过广场"},
        ])],
        M_SENSORY: [percept_json(
            senses=[{"sense": "sight", "description": "看到开阔的广场"}],
            summary="广场很安静",
        )],
        M_NARRATIVE: [narrative_json("叙事文本E2E")],
    }


# ── 图构建与节点提取 ───────────────────────────────────────────────────────

def build_test_graph(llm: Any):
    """用真实 PromptLoader 构建图（模板渲染也是被测行为的一部分）。"""
    return build_game_graph(llm, PromptLoader("prompts"))


def get_node(graph, name: str) -> Callable:
    """从编译后的图中提取节点原始函数（同步取 func，异步取 afunc）。

    用于节点级隔离 characterization（含 F821 路径）——不需要、也不允许修改 src/。
    """
    bound = graph.nodes[name].bound
    if bound.func is not None:
        return bound.func
    return bound.afunc


def new_thread_id() -> str:
    return f"char-{uuid.uuid4().hex[:12]}"


def char_marker_for(name: str) -> str:
    """character_system.j2 按 NPC 名字路由用的标记。"""
    return f"名字：{name}"
