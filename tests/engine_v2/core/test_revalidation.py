"""P3-T07 收尾验收：revalidation（P3 设计规范 §3.9 全量行为）。

依据 ``docs/v2/contracts/P3-scheduler-time-action-design.md``（下称"P3
设计规范"）§3.9 代码块契约、§6.1 单测要点与 §6.3 A1/A1 变体：

- 5 步顺序：ACCEPT 全过 / stale → REJECT ``stale_revision``（details 含两
  revision 值，§6.1）/ ``valid_until`` 过期 → REJECT
  ``valid_until_expired`` / **两条件同时满足 → ``valid_until_expired``
  （F2-05 过期优先，不随实现顺序漂移）** / actor 缺失 → REJECT
  ``actor_missing`` / ``actor_alive_check`` 假 → REJECT
  ``actor_not_alive``；
- ``current == valid_until`` 不陈旧（``revision.py:82`` 口径边界 → ACCEPT）；
- REBASE：``allow_rebase=True`` + actor 存活 → REBASE，
  ``rebased_proposal.base_world_revision == current``、其余字段逐字保持、
  原实例不 mutate；``allow_rebase=True`` + actor 不存活 → REJECT（非
  REBASE）；``allow_rebase=False`` + stale → REJECT；
- ``actor_alive_check`` 钩子契约：入参为 ``guard(state)`` 只读视图
  （``GuardedWorldState``，构造一次复用）+ actor ID；
- ``actor_state_revision`` 陈旧 → 仅 details 诊断不 REJECT（D-12 口径：
  记录"读取时"revision，不作 REJECT 依据）；``observation_id`` → details
  （内容级一致性检查属 P4 观察管线扩展位）；
- **单一实现**：对 NPC/LLM/玩家三类 ``provenance`` 行为一致（producer
  无关断言，G2 移交 3）；
- effect 侧复用探针：同一 (base, current) 对，P2
  ``check_transaction_references`` 报 ``stale_revision`` 与 P3 提案级
  REJECT 口径一致（``is_stale`` 单源，§3.2 测试口径）；
- **REPAIR 范围（R4/E-P3-26）**：P3 测试**不得把结果域钉死为三值集合**
  （不得断言 结果域 == {accept,rebase,reject} 为词表不变量）——本文件仅
  做"每次调用产出的 outcome 非 REPAIR"的行为断言；
- ``current`` 缺省 = ``state.world_revision``，显式 ``current`` 覆盖；
- 判定结果 = 数据（REJECT/REBASE 不抛异常）；``RevalidationDecision`` 为
  ``ContractModel``，JSON round-trip 类型保持。

布局（P2 勘误 E4 沿袭）：位于 ``tests/engine_v2/core/``；直接从子模块
import，不经包级导出；全部用例无网络、无 LLM、无 API key。
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from src.engine_v2.core.actions import (
    ActionProposal,
    ActionTiming,
    ActionTypeId,
    FallbackSpec,
)
from src.engine_v2.core.effects import (
    CommittedEffect,
    EntityTarget,
    EffectTypeId,
    ProposedEffect,
)
from src.engine_v2.core.ids import (
    ActionInstanceId,
    EntityId,
    ObservationId,
    ProducerId,
    new_effect_id,
    new_transaction_id,
)
from src.engine_v2.core.provenance import OriginKind, Provenance
from src.engine_v2.core.reducer import GuardedWorldState
from src.engine_v2.core.revalidation import (
    RevalidationDecision,
    rebase_proposal,
    revalidate_proposal,
)
from src.engine_v2.core.revision import RevalidationOutcome, Revision, is_stale
from src.engine_v2.core.serialization import dump_json, load_json
from src.engine_v2.core.state import EntityRecord, WorldState
from src.engine_v2.core.transaction import Transaction, TransactionStatus
from src.engine_v2.core.validation import check_transaction_references

_ALICE = EntityId("ent_alice")
_GHOST = EntityId("ent_ghost")


# —— 确定性构造助手 ——


def _record(eid: EntityId) -> EntityRecord:
    return EntityRecord(
        entity_id=eid,
        entity_class="npc",
        tags=["test"],
        created_revision=Revision(0),
        components={"space.position": {"x": 1, "y": 2}},
    )


def _state(world_revision: int, *, with_alice: bool = True) -> WorldState:
    """确定性世界：可选 alice 实体 + 指定 world_revision。"""
    return WorldState(
        world_revision=Revision(world_revision),
        entities={_ALICE: _record(_ALICE)} if with_alice else {},
    )


def _provenance(
    origin: OriginKind = OriginKind.BEHAVIOR_POLICY,
    producer: str = "policy.alice",
) -> Provenance:
    return Provenance(producer_id=ProducerId(producer), origin=origin)


def _proposal(
    *,
    actor: EntityId = _ALICE,
    base: int = 0,
    valid_until: int | None = None,
    state_rev: int | None = None,
    observation_id: ObservationId | None = None,
    provenance: Provenance | None = None,
    pid: str = "act_p1",
) -> ActionProposal:
    """字段面完整的确定性提案（REBASE 逐字比较需要非平凡字段）。"""
    return ActionProposal(
        proposal_id=ActionInstanceId(pid),
        actor_id=actor,
        action_id=ActionTypeId("travel"),
        arguments={"destination": {"x": 3, "y": 4}, "speed": 2},
        intent="移动到目标点",
        timing=ActionTiming(earliest_start_tick=5, deadline_tick=50),
        confidence=0.8,
        fallback_action=FallbackSpec(
            action_id=ActionTypeId("idle"), arguments={"reason": "blocked"}
        ),
        base_world_revision=Revision(base),
        observation_id=observation_id,
        actor_state_revision=Revision(state_rev) if state_rev is not None else None,
        valid_until=Revision(valid_until) if valid_until is not None else None,
        provenance=provenance if provenance is not None else _provenance(),
    )


def _dump_without_base(proposal: ActionProposal) -> dict[str, Any]:
    """base_world_revision 以外的全部字段（JSON 形态）——"逐字保持"比较面。"""
    dumped = proposal.model_dump(mode="json")
    dumped.pop("base_world_revision")
    return dumped


class TestAcceptPath:
    """步骤 5：全过 → ACCEPT（含步骤 4 诊断落 details）。"""

    def test_fresh_proposal_all_pass_accepts(self) -> None:
        state = _state(world_revision=7)
        proposal = _proposal(base=7)
        decision = revalidate_proposal(state, proposal)
        assert decision.outcome is RevalidationOutcome.ACCEPT
        assert decision.reason == "accept"
        assert decision.proposal_id == proposal.proposal_id
        assert decision.at_revision == 7
        assert type(decision.at_revision) is Revision
        assert decision.details == ()
        assert decision.rebased_proposal is None

    def test_current_equal_valid_until_boundary_not_stale(self) -> None:
        """``current == valid_until`` 不陈旧（revision.py:82 口径边界）。"""
        state = _state(world_revision=7)
        proposal = _proposal(base=7, valid_until=7)
        decision = revalidate_proposal(state, proposal)
        assert decision.outcome is RevalidationOutcome.ACCEPT
        assert decision.reason == "accept"

    def test_future_valid_until_not_stale(self) -> None:
        state = _state(world_revision=7)
        proposal = _proposal(base=7, valid_until=9)
        decision = revalidate_proposal(state, proposal)
        assert decision.outcome is RevalidationOutcome.ACCEPT


class TestStaleReject:
    """步骤 1：is_stale 为真 → REBASE 或 REJECT（F2-05 原因优先级）。"""

    def test_stale_base_below_current_rejects_stale_revision(self) -> None:
        state = _state(world_revision=813)
        proposal = _proposal(base=812)
        decision = revalidate_proposal(state, proposal)
        assert decision.outcome is RevalidationOutcome.REJECT
        assert decision.reason == "stale_revision"
        assert decision.at_revision == 813
        assert decision.rebased_proposal is None
        # §6.1：details 含两 revision 值
        assert any(
            "812" in detail and "813" in detail for detail in decision.details
        )

    def test_valid_until_expired_rejects(self) -> None:
        state = _state(world_revision=7)
        proposal = _proposal(base=7, valid_until=5)
        decision = revalidate_proposal(state, proposal)
        assert decision.outcome is RevalidationOutcome.REJECT
        assert decision.reason == "valid_until_expired"
        assert decision.at_revision == 7
        assert decision.rebased_proposal is None
        assert any("5" in detail and "7" in detail for detail in decision.details)

    def test_both_conditions_prefers_valid_until_expired(self) -> None:
        """F2-05 过期优先（§6.3 A1 变体）：base<current ∧ current>valid_until
        同时满足 → 报 ``valid_until_expired``，不随实现顺序漂移。"""
        state = _state(world_revision=813)
        proposal = _proposal(base=812, valid_until=812)
        decision = revalidate_proposal(state, proposal)
        assert decision.outcome is RevalidationOutcome.REJECT
        assert decision.reason == "valid_until_expired"

    def test_allow_rebase_false_stale_rejects(self) -> None:
        state = _state(world_revision=5)
        proposal = _proposal(base=2)
        decision = revalidate_proposal(state, proposal, allow_rebase=False)
        assert decision.outcome is RevalidationOutcome.REJECT
        assert decision.reason == "stale_revision"
        assert decision.rebased_proposal is None


class TestRebase:
    """REBASE：allow_rebase + actor 存活 → 纯变换；actor 不存活 → REJECT。"""

    def test_allow_rebase_actor_alive_rebases(self) -> None:
        state = _state(world_revision=5)
        proposal = _proposal(base=2)
        decision = revalidate_proposal(state, proposal, allow_rebase=True)
        assert decision.outcome is RevalidationOutcome.REBASE
        assert decision.reason == "rebased"
        assert decision.at_revision == 5
        rebased = decision.rebased_proposal
        assert rebased is not None
        # base_world_revision → current
        assert rebased.base_world_revision == 5
        assert type(rebased.base_world_revision) is Revision
        # 其余字段逐字保持
        assert _dump_without_base(rebased) == _dump_without_base(proposal)

    def test_rebase_does_not_mutate_original(self) -> None:
        state = _state(world_revision=5)
        proposal = _proposal(base=2)
        decision = revalidate_proposal(state, proposal, allow_rebase=True)
        assert proposal.base_world_revision == 2
        assert decision.rebased_proposal is not proposal

    def test_allow_rebase_actor_not_alive_rejects_not_rebase(self) -> None:
        state = _state(world_revision=5)
        proposal = _proposal(base=2)
        decision = revalidate_proposal(
            state,
            proposal,
            allow_rebase=True,
            actor_alive_check=lambda view, actor: False,
        )
        assert decision.outcome is RevalidationOutcome.REJECT
        assert decision.rebased_proposal is None

    def test_rebase_proposal_pure_transformation(self) -> None:
        proposal = _proposal(base=2)
        current = Revision(9)
        rebased = rebase_proposal(proposal, current)
        assert rebased is not proposal
        assert rebased.base_world_revision == 9
        assert type(rebased.base_world_revision) is Revision
        assert _dump_without_base(rebased) == _dump_without_base(proposal)
        assert proposal.base_world_revision == 2

    def test_rebase_proposal_no_op_revision_still_rebuilds(self) -> None:
        """base == current 亦产出字段值相同的新实例（纯变换不依赖输入）。"""
        proposal = _proposal(base=3)
        rebased = rebase_proposal(proposal, Revision(3))
        assert rebased is not proposal
        assert rebased.base_world_revision == 3
        assert _dump_without_base(rebased) == _dump_without_base(proposal)


class TestActorChecks:
    """步骤 2/3：actor 存在性与存活钩子。"""

    def test_actor_missing_rejects(self) -> None:
        state = _state(world_revision=4, with_alice=False)
        proposal = _proposal(base=4)
        decision = revalidate_proposal(state, proposal)
        assert decision.outcome is RevalidationOutcome.REJECT
        assert decision.reason == "actor_missing"
        assert str(_ALICE) in " ".join(decision.details)
        assert decision.rebased_proposal is None

    def test_actor_not_alive_custom_check_rejects(self) -> None:
        state = _state(world_revision=4)
        proposal = _proposal(base=4)
        decision = revalidate_proposal(
            state,
            proposal,
            actor_alive_check=lambda view, actor: False,
        )
        assert decision.outcome is RevalidationOutcome.REJECT
        assert decision.reason == "actor_not_alive"
        assert decision.rebased_proposal is None

    def test_actor_alive_check_receives_guarded_view_and_actor_id(self) -> None:
        """钩子契约：入参 = guard(state) 只读视图 + actor ID（构造一次复用）。"""
        state = _state(world_revision=4)
        proposal = _proposal(base=4)
        calls: list[tuple[Any, Any]] = []

        def _check(view: GuardedWorldState, actor: EntityId) -> bool:
            calls.append((view, actor))
            return True

        decision = revalidate_proposal(state, proposal, actor_alive_check=_check)
        assert decision.outcome is RevalidationOutcome.ACCEPT
        assert len(calls) == 1
        view, actor = calls[0]
        assert isinstance(view, GuardedWorldState)
        assert actor == proposal.actor_id

    def test_actor_alive_check_not_called_when_actor_missing(self) -> None:
        """actor 缺失时存活判定无对象可查（钩子零调用，确定性）。"""
        state = _state(world_revision=4, with_alice=False)
        proposal = _proposal(base=4)
        calls: list[Any] = []

        def _check(view: GuardedWorldState, actor: EntityId) -> bool:
            calls.append(actor)
            return True

        decision = revalidate_proposal(state, proposal, actor_alive_check=_check)
        assert decision.outcome is RevalidationOutcome.REJECT
        assert decision.reason == "actor_missing"
        assert calls == []


class TestStep4Diagnostics:
    """步骤 4：ACCEPT 路径诊断（仅 details，不作 REJECT 依据）。"""

    def test_actor_state_revision_stale_diagnostic_only(self) -> None:
        """D-12 口径：记录"读取时"revision，仅诊断，不 REJECT。"""
        state = _state(world_revision=9)
        proposal = _proposal(base=9, state_rev=7)
        decision = revalidate_proposal(state, proposal)
        assert decision.outcome is RevalidationOutcome.ACCEPT
        assert decision.reason == "accept"
        assert any(
            "actor_state_revision" in detail and "7" in detail and "9" in detail
            for detail in decision.details
        )

    def test_actor_state_revision_current_no_diagnostic(self) -> None:
        state = _state(world_revision=9)
        proposal = _proposal(base=9, state_rev=9)
        decision = revalidate_proposal(state, proposal)
        assert decision.outcome is RevalidationOutcome.ACCEPT
        assert decision.details == ()

    def test_observation_id_recorded_in_details(self) -> None:
        state = _state(world_revision=6)
        proposal = _proposal(base=6, observation_id=ObservationId("obs_991"))
        decision = revalidate_proposal(state, proposal)
        assert decision.outcome is RevalidationOutcome.ACCEPT
        assert any("obs_991" in detail for detail in decision.details)


class TestRepairScopeEP326:
    """REPAIR 范围（R4/E-P3-26）：P3 同步 tick 循环 revalidation 不产 REPAIR。

    **口径纪律（§6.1）**：不得把结果域钉死为三值集合（不得断言结果域 ==
    {accept, rebase, reject} 为词表不变量——词表已冻结四值，P4 异步路径
    保留 REPAIR 产出能力）。本组仅做**逐次调用行为断言**：
    ``revalidate_proposal`` 的每次返回 outcome 非 REPAIR。
    """

    @pytest.mark.parametrize("base_offset", (0, -2, -5))
    @pytest.mark.parametrize("valid_until_offset", (None, -2, 0, 3))
    @pytest.mark.parametrize("allow_rebase", (False, True))
    @pytest.mark.parametrize("with_alice", (True, False))
    @pytest.mark.parametrize("alive", (None, True, False))
    def test_p3_never_emits_repair(
        self,
        base_offset: int,
        valid_until_offset: int | None,
        allow_rebase: bool,
        with_alice: bool,
        alive: bool | None,
    ) -> None:
        current = 10
        state = _state(world_revision=current, with_alice=with_alice)
        proposal = _proposal(
            base=current + base_offset,
            valid_until=(current + valid_until_offset)
            if valid_until_offset is not None
            else None,
        )
        check = (
            (lambda view, actor: alive)
            if alive is not None
            else None
        )
        decision = revalidate_proposal(
            state, proposal, allow_rebase=allow_rebase, actor_alive_check=check
        )
        assert decision.outcome is not RevalidationOutcome.REPAIR

    def test_p3_anchor_outcomes_within_documented_domain(self) -> None:
        """锚点组合的结果与 §3.9 步骤映射逐字一致（不扩大为词表不变量）。"""
        current = 10
        # 全过 → ACCEPT
        fresh = revalidate_proposal(_state(current), _proposal(base=current))
        assert fresh.outcome is RevalidationOutcome.ACCEPT
        # stale + allow_rebase + actor 存活 → REBASE
        rebased = revalidate_proposal(
            _state(current), _proposal(base=current - 2), allow_rebase=True
        )
        assert rebased.outcome is RevalidationOutcome.REBASE
        # stale + 禁止 rebase → REJECT
        rejected = revalidate_proposal(_state(current), _proposal(base=current - 2))
        assert rejected.outcome is RevalidationOutcome.REJECT


class TestProducerAgnostic:
    """单一实现（G2 移交 3）：NPC/LLM/玩家三类 provenance 行为一致。"""

    @pytest.mark.parametrize(
        ("origin", "producer"),
        (
            (OriginKind.BEHAVIOR_POLICY, "policy.npc_alice"),  # NPC
            (OriginKind.RULE, "llm.planner_bob"),  # LLM
            (OriginKind.DEVELOPER, "developer.carol"),  # 玩家（devtools）
        ),
    )
    def test_same_outcome_across_provenance_origins(
        self, origin: OriginKind, producer: str
    ) -> None:
        state = _state(world_revision=813)
        proposal = _proposal(
            base=812,
            valid_until=812,
            provenance=_provenance(origin=origin, producer=producer),
        )
        decision = revalidate_proposal(state, proposal)
        assert decision.outcome is RevalidationOutcome.REJECT
        assert decision.reason == "valid_until_expired"
        # producer 无关：details/at_revision 与 origin 无关（逐字恒定）
        expected_details = (
            "valid_until_expired: valid_until 812 < current 813",
        )
        assert decision.details == expected_details
        assert decision.at_revision == 813


class TestCurrentResolution:
    """current 缺省 = state.world_revision；显式 current 覆盖。"""

    def test_current_defaults_to_state_world_revision(self) -> None:
        proposal = _proposal(base=5)
        fresh = revalidate_proposal(_state(world_revision=5), proposal)
        assert fresh.outcome is RevalidationOutcome.ACCEPT
        assert fresh.at_revision == 5
        stale = revalidate_proposal(_state(world_revision=6), _proposal(base=5))
        assert stale.outcome is RevalidationOutcome.REJECT
        assert stale.at_revision == 6

    def test_explicit_current_overrides_state_world_revision(self) -> None:
        state = _state(world_revision=6)
        # base=5 < state.world_revision=6，但显式 current=5 → 不陈旧
        decision = revalidate_proposal(
            state, _proposal(base=5), current=Revision(5)
        )
        assert decision.outcome is RevalidationOutcome.ACCEPT
        assert decision.at_revision == 5


class TestDecisionIsData:
    """判定结果 = 数据（不是异常）+ 契约模型不变量与序列化。"""

    def test_reject_and_rebase_return_decisions_without_raising(self) -> None:
        state = _state(world_revision=5)
        stale_reject = revalidate_proposal(state, _proposal(base=2))
        rebase = revalidate_proposal(state, _proposal(base=2), allow_rebase=True)
        missing_reject = revalidate_proposal(
            _state(world_revision=5, with_alice=False), _proposal(base=5)
        )
        for decision in (stale_reject, rebase, missing_reject):
            assert isinstance(decision, RevalidationDecision)
            assert decision.outcome in (
                RevalidationOutcome.ACCEPT,
                RevalidationOutcome.REBASE,
                RevalidationOutcome.REJECT,
            )

    def test_revalidate_does_not_mutate_state_or_proposal(self) -> None:
        state = _state(world_revision=5)
        proposal = _proposal(base=2, valid_until=1)
        before_state = state.model_dump(mode="json")
        before_proposal = proposal.model_dump(mode="json")
        revalidate_proposal(state, proposal, allow_rebase=True)
        assert state.model_dump(mode="json") == before_state
        assert proposal.model_dump(mode="json") == before_proposal

    def test_decision_rebase_invariant_enforced_at_construction(self) -> None:
        """K7 可检查不静默：outcome==REBASE ⇔ rebased_proposal 非空。"""
        proposal = _proposal(base=2)
        with pytest.raises(ValidationError, match="outcome==REBASE"):
            RevalidationDecision(
                proposal_id=proposal.proposal_id,
                outcome=RevalidationOutcome.REBASE,
                reason="rebased",
                at_revision=Revision(5),
                rebased_proposal=None,
            )
        with pytest.raises(ValidationError, match="outcome==REBASE"):
            RevalidationDecision(
                proposal_id=proposal.proposal_id,
                outcome=RevalidationOutcome.ACCEPT,
                reason="accept",
                at_revision=Revision(5),
                rebased_proposal=rebase_proposal(proposal, Revision(5)),
            )

    def test_decision_json_roundtrip_preserves_types(self) -> None:
        state = _state(world_revision=5)
        decision = revalidate_proposal(state, _proposal(base=2), allow_rebase=True)
        restored = load_json(RevalidationDecision, dump_json(decision))
        assert restored == decision
        assert type(restored.at_revision) is Revision
        assert isinstance(restored.outcome, RevalidationOutcome)
        assert restored.rebased_proposal is not None
        assert type(restored.rebased_proposal) is ActionProposal
        assert type(restored.rebased_proposal.base_world_revision) is Revision


class TestEffectSideReuseProbe:
    """effect 侧复用探针（§6.1/§3.2）：is_stale 单源口径一致。

    构造 stale effect 批 → P2 ``check_transaction_references`` 报
    ``stale_revision``，与 P3 提案级 REJECT（同 (base, current) 对）口径
    一致——两路判定共享 ``revision.is_stale`` 单源，不各自实现。
    """

    def test_stale_effect_batch_matches_proposal_level_reject(self) -> None:
        base = Revision(2)
        current = Revision(5)
        state = _state(world_revision=5)

        # P3 提案级：同一 (base, current) 对
        decision = revalidate_proposal(state, _proposal(base=2))
        assert decision.outcome is RevalidationOutcome.REJECT
        assert decision.reason == "stale_revision"

        # P2 effect 级：stale effect 批（target 实体在场，隔离 stale 维度）
        txn_id = new_transaction_id()
        effect = ProposedEffect(
            effect_id=new_effect_id(),
            effect_type=EffectTypeId("test.stale_probe"),
            source=ProducerId("policy.alice"),
            target=EntityTarget(entity_id=_ALICE),
            payload={"delta": 1},
            base_revision=base,
        )
        txn = Transaction(
            transaction_id=txn_id,
            status=TransactionStatus.COMMITTED,
            base_revision=Revision(4),
            commit_revision=current,
            effects=[
                CommittedEffect(
                    effect=effect,
                    transaction_id=txn_id,
                    commit_revision=current,
                    sequence=0,
                )
            ],
        )
        issues = check_transaction_references(state, txn)
        assert any(issue.startswith(f"stale_revision:{str(effect.effect_id)}") for issue in issues)
        # 口径一致：同 (base, current) 对两路同判陈旧
        assert is_stale(base, current) is True
        assert (
            f"stale_revision:{str(effect.effect_id)}:base={int(base)}"
            f" current={int(current)}" in issues
        )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
