"""P6-W5 ``staleness.py`` 单测（SOT §3.7 + §6.1 L814，恰 8 个平铺函数）。

覆盖项（按 §6.1 L814 行逐项 1:1）：

1. ``test_committable_outcomes_closed``：COMMITTABLE_OUTCOMES 封闭
   （== {"ACCEPT", "REBASE"} 精确等值）；
2. ``test_effective_valid_until_none_passthrough``：ttl None → None
   （无显式上界透传，Spec §9 L656 optional 语义）；
3. ``test_effective_valid_until_ttl``：TTL 计算 = base + ttl（Revision
   类型 + 值双断言）；
4. ``test_effective_valid_until_invalid``：ttl 非法（0 / 负）→ ValueError；
5. ``test_is_stale_boundary``：is_stale 边界（current == valid_until 不
   stale；current > valid_until stale；base 落后 1 stale——
   revision.py:78-88 既有口径原样消费）；
6. ``test_handle_result_four_states``：handle_result 四态（大写规范串
   映射面）；
7. ``test_handle_result_rebase_face``：REBASE rebased_proposal 非空面
   （构造期不变量 + 宿主提交语义）；
8. ``test_is_acceptable_four_values``：is_acceptable 四值（ACCEPT/
   REBASE 可提交，REPAIR/REJECT 不可）。

本文件自包含（conftest 面仅消费 §6.2 W5 允许集：alice_context）；
hermetic、纯函数面、无 I/O。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.engine_v2.core.actions import ActionProposal, ActionTypeId
from src.engine_v2.core.ids import ActionInstanceId, EntityId, ProducerId
from src.engine_v2.core.provenance import OriginKind, Provenance
from src.engine_v2.core.revision import Revision, RevalidationOutcome, is_stale
from src.engine_v2.core.revalidation import RevalidationDecision
from src.engine_v2.llm.staleness import (
    COMMITTABLE_OUTCOMES,
    effective_valid_until,
    handle_result,
    is_acceptable,
)


def _proposal() -> ActionProposal:
    """最小合法 ActionProposal（确定性假值；供 handle_result 消费面）。"""
    return ActionProposal(
        proposal_id=ActionInstanceId("act_test_01"),
        actor_id=EntityId("ent_alice"),
        action_id=ActionTypeId("attack"),
        base_world_revision=Revision(3),
        provenance=Provenance(
            producer_id=ProducerId("policy.alice"),
            origin=OriginKind.BEHAVIOR_POLICY,
        ),
    )


def _decision(
    outcome: RevalidationOutcome, *, rebased: ActionProposal | None = None
) -> RevalidationDecision:
    """最小合法 RevalidationDecision（reason 开放词表确定性取值）。"""
    return RevalidationDecision(
        proposal_id=ActionInstanceId("act_test_01"),
        outcome=outcome,
        reason="accept" if outcome is RevalidationOutcome.ACCEPT else "stale_revision",
        at_revision=Revision(4),
        rebased_proposal=rebased,
    )


def test_committable_outcomes_closed() -> None:
    """1) COMMITTABLE_OUTCOMES 封闭：== {"ACCEPT", "REBASE"} 精确等值。"""
    assert COMMITTABLE_OUTCOMES == frozenset({"ACCEPT", "REBASE"})
    assert len(COMMITTABLE_OUTCOMES) == 2
    assert "REPAIR" not in COMMITTABLE_OUTCOMES
    assert "REJECT" not in COMMITTABLE_OUTCOMES


def test_effective_valid_until_none_passthrough(alice_context) -> None:
    """2) ttl None → None（无显式上界；纯靠 base 对比 + 提交期
    revalidation 拦截，Spec §9 L656 optional 语义）。"""
    assert effective_valid_until(alice_context, None) is None


def test_effective_valid_until_ttl(alice_context) -> None:
    """3) TTL 计算：Revision(base_world_revision + ttl_ticks)（类型 +
    值双断言；TTL 从 context 基线起算）。"""
    result = effective_valid_until(alice_context, 5)
    assert result == Revision(int(alice_context.base_world_revision) + 5)
    assert type(result) is Revision


def test_effective_valid_until_invalid(alice_context) -> None:
    """4) ttl 非法（0 / 负）= 输入违例 → ValueError（不静默接纳）。"""
    with pytest.raises(ValueError, match="ttl_ticks"):
        effective_valid_until(alice_context, 0)
    with pytest.raises(ValueError, match="ttl_ticks"):
        effective_valid_until(alice_context, -1)


def test_is_stale_boundary() -> None:
    """5) is_stale 边界（revision.py:78-88 既有口径原样消费，P6 不发明
    第二套）：base == current == valid_until → 不 stale（边界含等号）；
    current > valid_until（base 同步）→ stale；base 落后 1 → stale。"""
    # base == current == valid_until（边界含等号）→ 不 stale
    assert is_stale(Revision(4), Revision(4), valid_until=Revision(4)) is False
    # base 同步但 current > valid_until → stale
    assert is_stale(Revision(5), Revision(5), valid_until=Revision(4)) is True
    # base 落后 1（base < current，无 valid_until）→ stale
    assert is_stale(Revision(2), Revision(3), valid_until=None) is True
    # base == current 且无 valid_until → 不 stale
    assert is_stale(Revision(3), Revision(3), valid_until=None) is False


def test_handle_result_four_states() -> None:
    """6) handle_result 四态：decision.outcome → 大写规范串（Spec §9
    L673-677 词表；词表 .value 小写，.name 大写 = 规范化面）。"""
    for outcome, expected in (
        (RevalidationOutcome.ACCEPT, "ACCEPT"),
        (RevalidationOutcome.REBASE, "REBASE"),
        (RevalidationOutcome.REPAIR, "REPAIR"),
        (RevalidationOutcome.REJECT, "REJECT"),
    ):
        rebased = _proposal() if outcome is RevalidationOutcome.REBASE else None
        decision = _decision(outcome, rebased=rebased)
        assert handle_result(decision, _proposal()) == expected


def test_handle_result_rebase_face() -> None:
    """7) REBASE rebased_proposal 非空面：outcome==REBASE ⇔
    rebased_proposal 非 None（构造期不变量，revalidation.py:91）；
    rebased 提案由宿主提交——P6 不自动重提交（#10 面）。"""
    rebased = _proposal()
    decision = _decision(RevalidationOutcome.REBASE, rebased=rebased)
    assert decision.rebased_proposal is rebased
    assert handle_result(decision, _proposal()) == "REBASE"
    # 不变量反证：REBASE 缺 rebased_proposal → 构造失败（K7 可检查）
    with pytest.raises(ValidationError):
        _decision(RevalidationOutcome.REBASE, rebased=None)


def test_is_acceptable_four_values() -> None:
    """8) is_acceptable 四值：ACCEPT/REBASE 可提交；REPAIR/REJECT 不可
    （outcome ∈ COMMITTABLE_OUTCOMES 判定面）。"""
    assert is_acceptable("ACCEPT") is True
    assert is_acceptable("REBASE") is True
    assert is_acceptable("REPAIR") is False
    assert is_acceptable("REJECT") is False
