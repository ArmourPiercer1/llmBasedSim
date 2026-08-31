"""P6-W6 critic 单元测试（SOT §6.1 test_critic 行：8 个平铺函数）。

断言面（1:1 对应 SOT §6.1 计数行）：

1. no-op 跳过：``action_id is None`` → ok，不查任何字段（即使目标字段违规）；
2. action 不在候选：``action-not-in-candidates``；
3. 目标不可见：标量目标字段值 ∉ 可见并集 → ``target-not-visible``；
4. 目标键封闭集：未知键不查；已知键非 str 值不查；
5. 全过：候选内 + 目标可见（visible_entities / local / global 三域各验一次）；
6. ``critique_instruction`` 确定性：同输入同输出 + 一行一错 + 重申只输出 JSON；
7. 多错排序：检查 2 先于检查 3，检查 3 内按 arguments 键序（不短路）；
8. ``CRITIC_DEFAULT_ENABLED`` 值钉死（默认关）。

D4：只消费 conftest JSON-clean 孪生 context（``dataclasses.replace`` 变体），
不构造真实 P4 类型。
"""

from __future__ import annotations

import dataclasses

from src.engine_v2.core.actions import ActionTypeId
from src.engine_v2.llm.critic import (
    CRITIC_DEFAULT_ENABLED,
    CriticResult,
    critique,
    critique_instruction,
)
from src.engine_v2.prompts.assembler import LLMActionProposal

ATTACK = ActionTypeId("attack")


def test_critic_noop_skips_all_checks(alice_context) -> None:
    """1) no-op 跳过：action_id None → ok；即使目标字段指向不可见实体也不查。"""
    wire = LLMActionProposal(
        action_id=None, arguments={"target_id": "ent_ghost", "entity_id": "ent_phantom"}
    )
    result = critique(alice_context, wire)
    assert result.ok is True
    assert result.errors == ()


def test_critic_action_not_in_candidates(alice_context) -> None:
    """2) action 不在候选：恰一条 action-not-in-candidates。"""
    wire = LLMActionProposal(action_id=ActionTypeId("cast"), arguments={})
    result = critique(alice_context, wire)
    assert result.ok is False
    assert result.errors == ("action-not-in-candidates",)


def test_critic_target_not_visible(alice_context) -> None:
    """3) 目标不可见：每个违规值一条 target-not-visible（键序）。"""
    wire = LLMActionProposal(action_id=ATTACK, arguments={"target_id": "ent_carol"})
    result = critique(alice_context, wire)
    assert result.ok is False
    assert result.errors == ("target-not-visible",)


def test_critic_target_key_closed_set(alice_context) -> None:
    """4) 目标键封闭集：未知键不查；已知键非 str 标量不查。"""
    wire = LLMActionProposal(
        action_id=ATTACK,
        arguments={"speed": "ent_ghost", "note": "ent_phantom", "target_id": 42},
    )
    result = critique(alice_context, wire)
    assert result.ok is True
    assert result.errors == ()


def test_critic_all_pass_three_visibility_domains(alice_context) -> None:
    """5) 全过：三可见域（visible_entities / local_entity_views / global）各验一次。"""
    # visible_entities 域（fixture 自带 ent_bob）。
    wire = LLMActionProposal(action_id=ATTACK, arguments={"target_id": "ent_bob"})
    assert critique(alice_context, wire) is not None
    assert critique(alice_context, wire).ok is True
    # local_entity_views 域。
    local_ctx = dataclasses.replace(alice_context, local_entity_views={"ent_local": {}})
    wire_local = LLMActionProposal(action_id=ATTACK, arguments={"target_id": "ent_local"})
    assert critique(local_ctx, wire_local).ok is True
    # global_entity_views 域。
    global_ctx = dataclasses.replace(alice_context, global_entity_views={"ent_global": {}})
    wire_global = LLMActionProposal(action_id=ATTACK, arguments={"target_id": "ent_global"})
    assert critique(global_ctx, wire_global).ok is True
    # 目标键封闭集内其余键同域（entity_id / target / actor_id）。
    wire_multi = LLMActionProposal(
        action_id=ATTACK,
        arguments={
            "entity_id": "ent_bob",
            "target": "ent_bob",
            "actor_id": "ent_bob",
            "target_id": "ent_bob",
        },
    )
    assert critique(alice_context, wire_multi).ok is True


def test_critic_instruction_deterministic(alice_context) -> None:
    """6) critique_instruction 确定性 + 一行一错 + 重申只输出 JSON。"""
    errors = ("action-not-in-candidates", "target-not-visible")
    first = critique_instruction(errors)
    second = critique_instruction(errors)
    assert first == second
    lines = first.split("\n")
    assert lines[1] == "- action-not-in-candidates"
    assert lines[2] == "- target-not-visible"
    assert "只输出" in first
    assert "JSON" in first
    # 空错列表也确定性（防御面：不抛、返回稳定串）。
    assert critique_instruction(()) == critique_instruction(())


def test_critic_multi_error_ordering_no_short_circuit(alice_context) -> None:
    """7) 多错排序：检查 2 先于检查 3；检查 3 按 arguments 键序；不短路。"""
    ctx = dataclasses.replace(alice_context, candidate_actions=(ActionTypeId("travel"),))
    wire = LLMActionProposal(
        action_id=ATTACK,
        arguments={"target_id": "ent_x", "entity_id": "ent_y"},
    )
    result = critique(ctx, wire)
    assert result.ok is False
    assert result.errors == (
        "action-not-in-candidates",
        "target-not-visible",
        "target-not-visible",
    )
    # 结果类型冻结面。
    try:
        result.ok = False  # type: ignore[misc]
    except Exception as exc:
        assert type(exc).__name__ == "ValidationError"
    else:  # pragma: no cover - pydantic 冻结必然抛错
        raise AssertionError("CriticResult 应为冻结模型")
    assert isinstance(result, CriticResult)


def test_critic_default_enabled_value() -> None:
    """8) CRITIC_DEFAULT_ENABLED 值钉死（默认关，Leader-A6）。"""
    assert CRITIC_DEFAULT_ENABLED is False
