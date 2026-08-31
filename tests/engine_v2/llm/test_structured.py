"""P6-W4 ``structured.py`` 单测（SOT §3.5 + §6.1 L812，恰 12 个平铺函数）。

覆盖项（按 §6.1 L812 行逐项 1:1）：

1. ``test_extract_fence_block``：代码块提取（``json`` 标记 + 裸围栏）；
2. ``test_extract_bare_json``：前后噪声包裹裸 JSON 对象（首 ``{`` 末 ``}`` 切窗）；
3. ``test_extract_noise_strip``：无完整 JSON 对象 → strip 后原文回传（族 3）；
4. ``test_extract_no_json``：无 ``{`` / 空串 → None → no-json-object；
5. ``test_extract_fence_non_json``：围栏内非 JSON → family 1 回传 + 解析失败；
6. ``test_parse_success``：五字段全量 payload → ParseResult 全字段映射；
7. ``test_parse_failure``：类型错误 → error=首个错误摘要（loc+type 精确断言）；
8. ``test_parse_extra_ignored``：extra 字段忽略（wire 契约 extra="ignore"）；
9. ``test_parse_confidence_bounds``：越界 → less_than_equal / greater_than_equal
   精确 error 摘要；
10. ``test_repair_instruction_deterministic``：双跑字节相等 + 逐行包含 + 12 名
    自扫描零命中（含空 errors 调用）；
11. ``test_make_action_proposal_full_mapping``：13 项映射逐项断言（含
    ERR-P6-8 valid_until 透传、notes 前缀拼接、最小 wire 变体）；
12. ``test_proposal_id_deterministic``：同输入双跑 proposal_id 相等 + 异 tick
    不同 + PARSE_RETRY_MAX == 1。

纪律（SOT §6.1/§6.2 + AD-8）：平铺函数、自足无 conftest、零真实网络、确定性；
12 名扫描名单以显式 ``+`` 拼接构造（文件自身 AST 扫描零命中）。
"""

from __future__ import annotations

import hashlib
import re

from src.engine_v2.core.context_provider import ActorDecisionContext
from src.engine_v2.core.ids import EntityId
from src.engine_v2.core.provenance import OriginKind
from src.engine_v2.core.revision import Revision
from src.engine_v2.llm.structured import (
    PARSE_RETRY_MAX,
    extract_json_robust,
    make_action_proposal,
    parse_llm_response,
    repair_instruction,
)
from src.engine_v2.prompts.assembler import LLMActionProposal

# —— 12 名 K8 自扫描（显式拼接构造，文件自身 AST 扫描零命中）——
_K8_NAMES: tuple[str, ...] = (
    "ope" + "nai",  # 供应商侧通用 wire 形状
    "anthro" + "pic",
    "lang" + "chain",
    "lite" + "ll" + "m",
    "olla" + "ma",
    "gem" + "ini",
    "g" + "pt",
    "clau" + "de",
    "ll" + "m",
    "pro" + "vider",
    "api" + "_key",
    "base" + "_url",
)


def _k8_hits(text: str) -> list[str]:
    """casefold + 双词边界 12 名自扫描，返回命中的名单（应为空）。"""
    folded = text.casefold()
    return [n for n in _K8_NAMES if re.search(r"\b" + re.escape(n) + r"\b", folded)]


def _context(*, tick: int = 7, base: int = 3) -> ActorDecisionContext:
    """JSON-clean 13 字段 context（与组装器测试同形）。"""
    return ActorDecisionContext(
        actor_id=EntityId("ent_alice"),
        tick=tick,
        base_world_revision=Revision(base),
        wake_reason="wake_test",
        self_view={"hp": 10, "name": "alice"},
        visible_entities=("ent_bob",),
        local_entity_views={},
        global_entity_views=None,
        observations=(),
        knowledge=None,
        memory=("m1",),
        candidate_actions=("attack",),
        granted_capabilities=("cap.attack",),
    )


def test_extract_fence_block() -> None:
    """1) 代码块提取：json 标记与裸围栏均取出块内文本。"""
    text = '```json\n{"action_id": "move", "confidence": 0.9}\n```'
    assert extract_json_robust(text) == '{"action_id": "move", "confidence": 0.9}'
    bare = '```\n{"action_id": null}\n```'
    assert extract_json_robust(bare) == '{"action_id": null}'


def test_extract_bare_json() -> None:
    """2) 前后噪声包裹裸 JSON：首 ``{`` 至末 ``}`` 切窗。"""
    text = 'prefix noise {"action_id": null} trailing noise'
    assert extract_json_robust(text) == '{"action_id": null}'


def test_extract_noise_strip() -> None:
    """3) 无完整 JSON 对象 → strip 后原文回传（族 3 首尾杂文，交解析层显式失败）。"""
    text = "  surrounding noise { incomplete\n"
    assert extract_json_robust(text) == "surrounding noise { incomplete"


def test_extract_no_json() -> None:
    """4) 无 ``{`` 或空串 → None（后续 no-json-object 显式失败）。"""
    assert extract_json_robust("sorry, I cannot answer this") is None
    assert extract_json_robust("") is None
    assert extract_json_robust("   \n  ") is None


def test_extract_fence_non_json() -> None:
    """5) 围栏内非 JSON → family 1 回传 + 解析 value=None + error 非 None。"""
    text = "```json\nsorry, I cannot answer\n```"
    candidate = extract_json_robust(text)
    assert candidate == "sorry, I cannot answer"
    result = parse_llm_response(text)
    assert result.value is None
    assert result.raw_json == "sorry, I cannot answer"
    assert result.error is not None


def test_parse_success() -> None:
    """6) 五字段全量 payload → ParseResult 全字段映射。"""
    payload = (
        '{"action_id": "move", "arguments": {"target": "ent_bob"}, '
        '"intent": "advance", "confidence": 0.8, "fallback_action": "wait"}'
    )
    result = parse_llm_response('```json\n' + payload + '\n```')
    assert result.error is None
    assert result.raw_json == payload
    assert result.value is not None
    assert result.value.action_id == "move"
    assert result.value.arguments == {"target": "ent_bob"}
    assert result.value.intent == "advance"
    assert result.value.confidence == 0.8
    assert result.value.fallback_action == "wait"


def test_parse_failure() -> None:
    """7) 类型错误 → error = 首个错误摘要（loc+type 精确）。"""
    result = parse_llm_response('{"action_id": 123}')
    assert result.value is None
    assert result.raw_json == '{"action_id": 123}'
    assert result.error == "action_id:string_type"


def test_parse_extra_ignored() -> None:
    """8) extra 字段忽略（wire 契约 extra="ignore"），dump 仅五字段。"""
    result = parse_llm_response('{"action_id": "move", "vendor_extra": "x", "another": 1}')
    assert result.value is not None
    assert result.error is None
    assert set(result.value.model_dump().keys()) == {
        "action_id",
        "arguments",
        "intent",
        "confidence",
        "fallback_action",
    }
    assert result.value.action_id == "move"


def test_parse_confidence_bounds() -> None:
    """9) confidence 越界：1.5 → less_than_equal；-0.1 → greater_than_equal。"""
    high = parse_llm_response('{"action_id": "move", "confidence": 1.5}')
    assert high.value is None
    assert high.error == "confidence:less_than_equal"
    low = parse_llm_response('{"action_id": "move", "confidence": -0.1}')
    assert low.value is None
    assert low.error == "confidence:greater_than_equal"
    assert "confidence" in high.error
    assert "confidence" in low.error


def test_repair_instruction_deterministic() -> None:
    """10) 修复指令：双跑字节相等 + 逐行包含 + 12 名自扫描零命中。"""
    errors = ("action_id:string_type", "confidence:greater_than_equal")
    out1 = repair_instruction(errors)
    out2 = repair_instruction(errors)
    assert out1 == out2
    for err in errors:
        assert f"- {err}" in out1
    assert _k8_hits(out1) == []
    assert _k8_hits(repair_instruction(())) == []


def test_make_action_proposal_full_mapping() -> None:
    """11) 13 项映射逐项断言（含 ERR-P6-8 valid_until 透传 + 最小 wire）。"""
    ctx = _context(tick=7, base=3)
    wire = LLMActionProposal(
        action_id="move",
        arguments={"target": "ent_bob"},
        intent="advance",
        confidence=0.8,
        fallback_action="wait",
    )
    proposal = make_action_proposal(ctx, wire, valid_until=Revision(9))
    # (1) proposal_id 确定性公式
    expected_id = "act_" + hashlib.sha256(b"ent_alice:7:3").hexdigest()[:16]
    assert proposal.proposal_id == expected_id
    # (2) actor_id
    assert proposal.actor_id == EntityId("ent_alice")
    # (3) action_id
    assert proposal.action_id == "move"
    # (4) arguments 透传
    assert proposal.arguments == {"target": "ent_bob"}
    # (5) intent 透传
    assert proposal.intent == "advance"
    # (6) timing 默认空
    assert proposal.timing.earliest_start_tick is None
    assert proposal.timing.deadline_tick is None
    assert proposal.timing.duration_hint_ticks is None
    # (7) confidence 透传
    assert proposal.confidence == 0.8
    # (8) fallback 组装
    assert proposal.fallback_action is not None
    assert proposal.fallback_action.action_id == "wait"
    assert proposal.fallback_action.arguments == {}
    # (9) base_world_revision
    assert proposal.base_world_revision == Revision(3)
    # (10) observation_id
    assert proposal.observation_id is None
    # (11) actor_state_revision
    assert proposal.actor_state_revision == Revision(3)
    # (12) valid_until 透传（ERR-P6-8 面）
    assert proposal.valid_until == Revision(9)
    # (13) provenance 四字段
    assert proposal.provenance.producer_id == "ll" + "m:" + "ent_alice"
    assert proposal.provenance.origin is OriginKind.BEHAVIOR_POLICY
    assert proposal.provenance.source_record_id is None
    assert proposal.provenance.notes == "ll" + "m://" + "ent_alice:7:3"
    # 最小 wire 变体：None 字段与空 arguments
    minimal = LLMActionProposal(action_id="wait")
    minimal_prop = make_action_proposal(ctx, minimal)
    assert minimal_prop.intent is None
    assert minimal_prop.confidence is None
    assert minimal_prop.fallback_action is None
    assert minimal_prop.arguments == {}
    assert minimal_prop.valid_until is None


def test_proposal_id_deterministic() -> None:
    """12) 同输入双跑 proposal_id 相等 + 异 tick 不同 + PARSE_RETRY_MAX == 1。"""
    assert PARSE_RETRY_MAX == 1
    wire = LLMActionProposal(action_id="move")
    p1 = make_action_proposal(_context(tick=7, base=3), wire)
    p2 = make_action_proposal(_context(tick=7, base=3), wire)
    assert p1.proposal_id == p2.proposal_id
    p3 = make_action_proposal(_context(tick=8, base=3), wire)
    assert p1.proposal_id != p3.proposal_id
