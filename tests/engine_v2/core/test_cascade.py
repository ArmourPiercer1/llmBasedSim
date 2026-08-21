"""P2-T07/T08 CascadeExecutor 级联执行器验收（P2 设计规范 §1/§7 全量）。

覆盖（任务包 P2-T07/T08 测试要求逐项落位）：

- **级联触发器机制与 CascadeContext**（D-P2-13/D-P2-14，§7.1/§7.2）：
  ``SyncTrigger`` / ``CascadeTriggerRegistry``（别名 ``TriggerRegistry``）
  注册序求值串联、同名幂等/冲突、协议守卫、只读门面强制（K2）；
  级联树装配——根事件 ``depth=0``、级联触发 ``depth+1``、全部事务/事件
  携带 ``CascadeContext(cascade_id, causal_root_id, depth)`` 且
  cascade_id / root 一致（§7.6 因果树验收的运行时侧）；
- **多层级联触发**：0 → 1 → 2 层触发成功（3 个 COMMITTED、revision 恰
  +3、事件 depth 0/1/2、K6 cause_ids 链 effect↔event 交替衔接至根提案）；
  触发器停发后级联收敛；无触发器单回合执行器；
- **深度熔断**（§7.1，D-P2-13）：默认 ``max_cascade_depth=8`` 下自持
  触发链至多在 depth 9 启动前停（至多 9 个 COMMITTED）+ 诊断
  ``cascade_depth_exceeded`` + SYSTEM trace（§7.4 冻结 payload 键名）；
  自定义上限（2 / 0）同机制；``CascadeConfig(strict=True)`` → 抛
  ``CascadeDepthExceededError``（携带 depth / max_cascade_depth /
  cascade_id）；
- **环路检测**（§7.5，D-P2-14；CycleDetector）：冲突位置重访（HP变化→
  规则→又改HP 的 spec 原型）直接环路熔断——命中提案丢弃（过滤语义）、
  诊断 ``cycle_detected``（detail 重建 "深度/位置" 链、含祖先深度）、
  级联正常收敛（无异常）；间接环路（A→B→A 两步链）同机制熔断；
  ``location_revisit="allow"`` 退化为仅深度上限；``strict=True`` → 抛
  ``CascadeCycleError``（携带 hit.ancestor_depth / hit.key）；不同位置
  的合法级联不误熔断（防过熔断）；CycleDetector 单元面（observe/check/
  首次深度保留 / allow 模式 / 词法守卫 / 类型守卫）；
- **CascadeExecutor 端到端流水线**（§7.3）：AuthorityPolicy →
  EffectValidator → ConflictResolver → TransactionExecutor → Reducer →
  Triggers → Cascade Loop 串联——混合批（授权拒绝 / 校验失败 / 双写冲突
  FIFO 拍板 / 合法提交 + 触发器续级）的完整审计面：PROPOSED_EFFECT /
  AUTHORITY_DECISION / VALIDATION_DECISION / CONFLICT_RESOLUTION /
  TRANSACTION（含 ABORTED + rejected_effect_ids）/ DOMAIN_EVENT / SYSTEM
  trace 逐类断言 + 坐标填充（revision / cascade_id / transaction_id /
  producer_id）；ABORTED 回合级联停止（reducer 应用失败 → 原子失败审计，
  状态 / revision 原样）；空初始提案零回合；全拒批空回合不消耗 revision；
  DEFER 再入队机制（域解析器钩子 + 深度上限兜底 + 终态残留入
  ``result.deferred``，§5.5/§14 OQ3）；域解析器 WINNER 拍板路径；
  ``__init__`` 自动安装写屏障（§2.6.2 kernel 运行时入口）；
  ``CascadeResult`` 六元组 + ``cascade_statistics`` 级联统计（任务包表面）；
- **导出面**（D-P2-19 / §10.3）：``from src.engine_v2.core import <名称>``
  直接可用且与模块定义同一对象；别名（``TriggerRegistry`` /
  ``CascadeExecutionResult``）同一性；模块 ``__all__`` 恰为 18 项；
  异常族层级（``ValueError`` 族）。

写屏障为 **opt-in**（§2.6.2）：本文件 autouse 夹具每用例前后全局复原，
不跨文件受染（CascadeExecutor 构造会武装全局屏障）。

全部用例无网络、无 LLM、无 API key。
"""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from typing import Any

import pytest

import src.engine_v2.core as core_pkg
from src.engine_v2.core import (
    CASCADE_DIAGNOSTIC_KINDS as pkg_CASCADE_DIAGNOSTIC_KINDS,
)
from src.engine_v2.core import (
    CascadeConfig as pkg_CascadeConfig,
)
from src.engine_v2.core import (
    CascadeCycleError as pkg_CascadeCycleError,
)
from src.engine_v2.core import (
    CascadeDepthExceededError as pkg_CascadeDepthExceededError,
)
from src.engine_v2.core import (
    CascadeDiagnostic as pkg_CascadeDiagnostic,
)
from src.engine_v2.core import (
    CascadeError as pkg_CascadeError,
)
from src.engine_v2.core import (
    CascadeExecutionResult as pkg_CascadeExecutionResult,
)
from src.engine_v2.core import (
    CascadeExecutor as pkg_CascadeExecutor,
)
from src.engine_v2.core import (
    CascadeResult as pkg_CascadeResult,
)
from src.engine_v2.core import (
    CascadeStatistics as pkg_CascadeStatistics,
)
from src.engine_v2.core import (
    CascadeTrigger as pkg_CascadeTrigger,
)
from src.engine_v2.core import (
    CascadeTriggerRegistry as pkg_CascadeTriggerRegistry,
)
from src.engine_v2.core import (
    CycleDetector as pkg_CycleDetector,
)
from src.engine_v2.core import (
    CycleHit as pkg_CycleHit,
)
from src.engine_v2.core import (
    DEFAULT_MAX_CASCADE_DEPTH as pkg_DEFAULT_MAX_CASCADE_DEPTH,
)
from src.engine_v2.core import (
    SyncTrigger as pkg_SyncTrigger,
)
from src.engine_v2.core import (
    TriggerConflictError as pkg_TriggerConflictError,
)
from src.engine_v2.core import (
    TriggerRegistry as pkg_TriggerRegistry,
)
from src.engine_v2.core.authority import AuthorityPolicy, AuthorityRule, AuthoritySelector
from src.engine_v2.core.cascade import (
    CASCADE_DIAGNOSTIC_KINDS,
    CascadeConfig,
    CascadeCycleError,
    CascadeDepthExceededError,
    CascadeDiagnostic,
    CascadeError,
    CascadeExecutionResult,
    CascadeExecutor,
    CascadeResult,
    CascadeStatistics,
    CascadeTrigger,
    CascadeTriggerRegistry,
    CycleDetector,
    CycleHit,
    DEFAULT_MAX_CASCADE_DEPTH,
    SyncTrigger,
    TriggerConflictError,
    TriggerRegistry,
)
from src.engine_v2.core.components import ComponentTypeId
from src.engine_v2.core.conflicts import ConflictAction, ConflictKey, ConflictResolution
from src.engine_v2.core.effects import (
    EffectTypeId,
    EntityTarget,
    ProposedEffect,
    StateDomainId,
    StateDomainTarget,
)
from src.engine_v2.core.entity import EntityRecord
from src.engine_v2.core.events import DomainEvent, EventTypeId
from src.engine_v2.core.ids import EffectId, EntityId, ProducerId, new_event_id
from src.engine_v2.core.provenance import (
    CauseKind,
    CauseRef,
    OriginKind,
    Provenance,
)
from src.engine_v2.core.reducer import (
    ReducerError,
    default_handler_registry,
    guard,
    is_guarded,
    uninstall_write_barrier,
    write_barrier_installed,
)
from src.engine_v2.core.revision import Revision
from src.engine_v2.core.state import ScenarioState, WorldState
from src.engine_v2.core.trace import TraceKind
from src.engine_v2.core.transaction import TransactionStatus


# —— 确定性构造助手（固定 ID 词表、无墙钟；test_transaction_executor 同款纪律）——


def _base_state(world_revision: int = 0) -> WorldState:
    """确定性基线世界：2 实体（ent_x 带 attrs.hp；ent_alice 带 space.position）
    + 世界变量 + scenario 信封。"""
    return WorldState(
        world_revision=Revision(world_revision),
        entities={
            EntityId("ent_x"): EntityRecord(
                entity_id=EntityId("ent_x"),
                entity_class="npc",
                tags=[],
                created_revision=Revision(0),
                components={ComponentTypeId("attrs"): {"hp": 10}},
            ),
            EntityId("ent_alice"): EntityRecord(
                entity_id=EntityId("ent_alice"),
                entity_class="npc",
                tags=["shopkeeper"],
                created_revision=Revision(0),
                components={ComponentTypeId("space.position"): {"x": 1, "y": 2}},
            ),
        },
        world_variables={"gold": 0, "silver": 0},
        scenario_state=ScenarioState(scenario_id="scn_main", stage="act1", data={}),
    )


def _origin() -> Provenance:
    """事务级 Provenance（装配者）。"""
    return Provenance(producer_id=ProducerId("dev.kernel"), origin=OriginKind.SYSTEM)


class _EffectFactory:
    """确定性效果构造：eff_casc id 按工厂序号唯一。"""

    def __init__(self) -> None:
        self._n = 0

    def proposed(
        self,
        effect_type: str,
        target: EntityTarget | StateDomainTarget,
        payload: dict[str, Any],
        *,
        base_revision: int = 0,
        source: str = "rule.test",
        cause_ids: list[CauseRef] | None = None,
    ) -> ProposedEffect:
        self._n += 1
        return ProposedEffect(
            effect_id=EffectId(f"eff_casc_{self._n:03d}"),
            effect_type=EffectTypeId(effect_type),
            source=ProducerId(source),
            target=target,
            payload=payload,
            base_revision=Revision(base_revision),
            cause_ids=list(cause_ids or []),
        )


@pytest.fixture()
def f() -> _EffectFactory:
    return _EffectFactory()


def _permissive_policy(writers: tuple[str, ...] = ("rule.test",)) -> AuthorityPolicy:
    """catch-all 授权规则（指定 writers 全放行；其余 producer rule_deny）。"""
    return AuthorityPolicy(
        rules=[
            AuthorityRule(
                selector=AuthoritySelector(),
                allowed_writers=[ProducerId(w) for w in writers],
                priority=1,
                rule_id="allow_writers",
            )
        ]
    )


def _gold_target() -> StateDomainTarget:
    return StateDomainTarget(domain=StateDomainId("world_variables"))


def _hp_target() -> EntityTarget:
    """spec §11 类别 5 原型位置：(ent_x, attrs.hp)。"""
    return EntityTarget(entity_id=EntityId("ent_x"), component_type=ComponentTypeId("attrs"))


@pytest.fixture(autouse=True)
def _ensure_barrier_unarmed() -> None:
    """写屏障 opt-in 纪律（§2.6.2）：每用例前后全局复原，不跨文件受染。

    前置 uninstall 是防御性兜底：前序用例若在 install 后异常退出，残留武装
    不得污染后续用例（CascadeExecutor 构造会经 kernel 运行时入口武装全局
    屏障）。
    """
    uninstall_write_barrier()
    yield
    uninstall_write_barrier()


def _traces_of(kind: TraceKind, records: tuple) -> list[dict[str, Any]]:
    """按 TraceKind 过滤 trace 并取 payload（审计面断言辅助）。"""
    return [record.payload for record in records if record.kind is kind]


def _dummy_event() -> DomainEvent:
    """触发器串联测试的最小事件载体（uuid ID 空间，确定性无碰撞）。"""
    return DomainEvent(
        event_id=new_event_id(),
        event_type=EventTypeId("core.set_world_variable"),
        world_revision=Revision(0),
        payload={"effect_id": "eff_casc_dummy", "target": {}},
        source_system=ProducerId("rule.test"),
        provenance=Provenance(producer_id=ProducerId("rule.test"), origin=OriginKind.RULE),
    )


# —— 配置与诊断载体（§7.1/§7.4；D-P2-13）——


class TestCascadeConfig:
    """CascadeConfig：缺省值、frozen、构造期守卫（§7.1）。"""

    def test_defaults_match_design_spec(self) -> None:
        config = CascadeConfig()
        assert config.max_cascade_depth == 8
        assert config.location_revisit == "forbid"
        assert config.strict is False
        assert DEFAULT_MAX_CASCADE_DEPTH == 8

    def test_is_frozen(self) -> None:
        config = CascadeConfig()
        with pytest.raises(dataclasses.FrozenInstanceError):
            config.max_cascade_depth = 3  # type: ignore[misc]

    def test_invalid_location_revisit_rejected(self) -> None:
        with pytest.raises(CascadeError, match="location_revisit"):
            CascadeConfig(location_revisit="sometimes")

    def test_negative_or_bool_max_depth_rejected(self) -> None:
        with pytest.raises(CascadeError, match="max_cascade_depth"):
            CascadeConfig(max_cascade_depth=-1)
        with pytest.raises(CascadeError, match="max_cascade_depth"):
            CascadeConfig(max_cascade_depth=True)  # bool 显式排除

    def test_non_bool_strict_rejected(self) -> None:
        with pytest.raises(CascadeError, match="strict"):
            CascadeConfig(strict="yes")  # type: ignore[arg-type]

    def test_zero_depth_allowed(self) -> None:
        # max_cascade_depth=0 = 仅根回合（depth 0），合法配置
        config = CascadeConfig(max_cascade_depth=0)
        assert config.max_cascade_depth == 0


class TestCascadeDiagnostic:
    """CascadeDiagnostic：冻结词表 + 构造期守卫（§7.4）。"""

    def test_frozen_vocabulary(self) -> None:
        assert CASCADE_DIAGNOSTIC_KINDS == frozenset(
            {"cascade_depth_exceeded", "cycle_detected", "trigger_output_dropped"}
        )

    def test_valid_construction(self) -> None:
        diag = CascadeDiagnostic(kind="cycle_detected", depth=1, detail="d")
        assert diag.kind == "cycle_detected" and diag.depth == 1

    def test_invalid_kind_rejected(self) -> None:
        with pytest.raises(CascadeError, match="kind"):
            CascadeDiagnostic(kind="round_aborted", depth=0, detail="d")

    def test_invalid_depth_or_detail_rejected(self) -> None:
        with pytest.raises(CascadeError, match="depth"):
            CascadeDiagnostic(kind="cycle_detected", depth=True, detail="d")
        with pytest.raises(CascadeError, match="detail"):
            CascadeDiagnostic(kind="cycle_detected", depth=0, detail="")


# —— 触发器协议与注册表（§7.2；任务包 P2-T07 表面）——


class TestSyncTrigger:
    """SyncTrigger：监听 DomainEvent 并同步产生新的 ProposedEffect 提议。"""

    def test_protocol_surface_and_delegation(self, f: _EffectFactory) -> None:
        state = guard(_base_state())

        def fn(events: list[DomainEvent], st: Any, depth: int) -> list[ProposedEffect]:
            if not events:
                return []
            return [
                f.proposed(
                    "core.set_world_variable",
                    _gold_target(),
                    {"key": "gold", "value": 1},
                    base_revision=int(st.world_revision),
                    cause_ids=[CauseRef(kind=CauseKind.EVENT, ref_id=str(events[0].event_id))],
                )
            ]

        trigger = SyncTrigger("rule.on_any", fn)
        assert trigger.trigger_id == "rule.on_any"
        # 协议面：trigger_id + 可调用 evaluate（@runtime_checkable 属性存在性）
        assert isinstance(trigger, CascadeTrigger)
        # 无事件 → 空产出（触发器自行决定无反应）
        assert trigger.evaluate([], state, 0) == []

    def test_guards_on_construction(self) -> None:
        with pytest.raises(CascadeError, match="trigger_id"):
            SyncTrigger("", lambda events, state, depth: [])
        with pytest.raises(CascadeError, match="evaluate_fn"):
            SyncTrigger("rule.x", "not-callable")  # type: ignore[arg-type]

    def test_evaluate_requires_guarded_state(self) -> None:
        """K2 运行时兜底：裸 WorldState 直传即拒绝（必须 guard 门面，§2.6.3）。"""
        trigger = SyncTrigger("rule.x", lambda events, state, depth: [])
        with pytest.raises(CascadeError, match="GuardedWorldState"):
            trigger.evaluate([], _base_state(), 0)  # type: ignore[arg-type]


class TestTriggerRegistry:
    """CascadeTriggerRegistry：注册序串联、幂等/冲突、协议守卫（§7.2）。"""

    def test_evaluate_all_concatenates_in_registration_order(
        self, f: _EffectFactory
    ) -> None:
        state = guard(_base_state())

        def make(tag: str) -> SyncTrigger:
            def fn(
                events: list[DomainEvent], st: Any, depth: int
            ) -> list[ProposedEffect]:
                return [
                    f.proposed(
                        "core.set_world_variable",
                        _gold_target(),
                        {"key": tag, "value": 1},
                        base_revision=int(st.world_revision),
                        cause_ids=[
                            CauseRef(kind=CauseKind.EVENT, ref_id=str(events[0].event_id))
                        ],
                    )
                ]

            return SyncTrigger(f"rule.{tag}", fn)

        registry = CascadeTriggerRegistry()
        first = make("first")
        second = make("second")
        registry.register(first)
        registry.register(second)
        assert registry.trigger_ids() == ("rule.first", "rule.second")
        event = _dummy_event()
        outputs = registry.evaluate_all([event], state, 0)
        assert [e.payload["key"] for e in outputs] == ["first", "second"]

    def test_empty_registry_returns_empty(self) -> None:
        registry = CascadeTriggerRegistry()
        assert registry.evaluate_all([], guard(_base_state()), 0) == []

    def test_same_instance_register_is_idempotent(self) -> None:
        registry = CascadeTriggerRegistry()
        trigger = SyncTrigger("rule.dup", lambda events, state, depth: [])
        registry.register(trigger)
        registry.register(trigger)  # 同实例幂等
        assert registry.trigger_ids() == ("rule.dup",)

    def test_same_id_different_instance_conflicts(self) -> None:
        registry = CascadeTriggerRegistry()
        registry.register(SyncTrigger("rule.dup", lambda events, state, depth: []))
        with pytest.raises(TriggerConflictError, match="rule.dup"):
            registry.register(SyncTrigger("rule.dup", lambda events, state, depth: []))

    def test_protocol_nonconformance_rejected(self) -> None:
        registry = CascadeTriggerRegistry()
        with pytest.raises(CascadeError, match="CascadeTrigger"):
            registry.register(object())  # type: ignore[arg-type]

        class _NoEvaluate:
            trigger_id: str = "rule.bad"

        with pytest.raises(CascadeError, match="evaluate"):
            registry.register(_NoEvaluate())  # type: ignore[arg-type]


# —— 环路检测器单元面（§7.5；P2-T08；D-P2-14）——


class TestCycleDetectorUnit:
    """CycleDetector：observe_commit / check / mode 语义。"""

    def _hp_effect(self, base: int = 0) -> ProposedEffect:
        return ProposedEffect(
            effect_id=EffectId("eff_cyc_probe"),
            effect_type=EffectTypeId("core.set_component"),
            source=ProducerId("rule.test"),
            target=EntityTarget(
                entity_id=EntityId("ent_x"), component_type=ComponentTypeId("attrs")
            ),
            payload={"hp": 5},
            base_revision=Revision(base),
        )

    def _hp_lock(self) -> ConflictKey:
        return ConflictKey(
            kind="entity", entity_id=EntityId("ent_x"),
            component_type=ComponentTypeId("attrs"),
        )

    def test_check_before_observe_is_none(self) -> None:
        assert CycleDetector().check(self._hp_effect()) is None

    def test_revisit_hits_with_ancestor_depth(self) -> None:
        detector = CycleDetector()
        detector.observe_commit(0, frozenset({self._hp_lock()}))
        hit = detector.check(self._hp_effect())
        assert isinstance(hit, CycleHit)
        assert hit is not None
        assert hit.ancestor_depth == 0
        assert hit.key == self._hp_lock()
        assert hit.key.render() == "entity:ent_x:comp:attrs"

    def test_first_commit_depth_is_retained(self) -> None:
        """同位置重复登记保留首次深度（ancestor_depth 语义，§7.5）。"""
        detector = CycleDetector()
        detector.observe_commit(2, frozenset({self._hp_lock()}))
        detector.observe_commit(0, frozenset({self._hp_lock()}))
        hit = detector.check(self._hp_effect())
        assert hit is not None
        assert hit.ancestor_depth == 0

    def test_distinct_position_no_hit(self) -> None:
        detector = CycleDetector()
        detector.observe_commit(0, frozenset({self._hp_lock()}))
        other = ProposedEffect(
            effect_id=EffectId("eff_cyc_other"),
            effect_type=EffectTypeId("core.set_component"),
            source=ProducerId("rule.test"),
            target=EntityTarget(
                entity_id=EntityId("ent_alice"), component_type=ComponentTypeId("attrs")
            ),
            payload={"hp": 1},
            base_revision=Revision(0),
        )
        assert detector.check(other) is None

    def test_allow_mode_always_none(self) -> None:
        detector = CycleDetector(mode="allow")
        detector.observe_commit(0, frozenset({self._hp_lock()}))
        assert detector.check(self._hp_effect()) is None

    def test_invalid_mode_rejected(self) -> None:
        with pytest.raises(CascadeError, match="mode"):
            CycleDetector(mode="forbit")

    def test_check_type_guard(self) -> None:
        with pytest.raises(CascadeError, match="ProposedEffect"):
            CycleDetector().check("not-an-effect")  # type: ignore[arg-type]


# —— 级联树装配与多层触发（D-P2-13；任务包测试要求 1）——


class _ChainTriggers:
    """线性多级触发链构造器：每层在**不同位置**续级（与环路检测正交），
    每个触发器只响应**上一层**的组件/域事件（每回合恰一个提案），
    ``depth >= stops_at`` 时停发。

    层 0 触发器响应根提案的 world_variables 域事件；层 i 触发器响应层
    i-1 的组件事件（``component_tags[i-1]``）。
    """

    def __init__(
        self,
        factory: _EffectFactory,
        *,
        stops_at: int,
        component_tags: list[str],
        source: str = "rule.chain",
    ) -> None:
        self._f = factory
        self._stops_at = stops_at
        self._tags = component_tags
        self._source = source

    def build_registry(self) -> CascadeTriggerRegistry:
        registry = CascadeTriggerRegistry()
        for index, tag in enumerate(self._tags):
            prev = self._tags[index - 1] if index > 0 else None
            registry.register(self._make(tag, prev))
        return registry

    def _make(self, tag: str, prev: str | None) -> SyncTrigger:
        def fn(events: list[DomainEvent], state: Any, depth: int) -> list[ProposedEffect]:
            if not events or depth >= self._stops_at:
                return []
            matched = [e for e in events if self._matches(e, prev)]
            if not matched:
                return []
            return [
                self._f.proposed(
                    "core.set_component",
                    EntityTarget(
                        entity_id=EntityId("ent_x"),
                        component_type=ComponentTypeId(tag),
                    ),
                    {"v": depth + 1},
                    base_revision=int(state.world_revision),
                    source=self._source,
                    cause_ids=[
                        CauseRef(kind=CauseKind.EVENT, ref_id=str(matched[0].event_id))
                    ],
                )
            ]

        return SyncTrigger(f"rule.on_{prev if prev is not None else 'root'}", fn)

    @staticmethod
    def _matches(event: DomainEvent, prev: str | None) -> bool:
        target = event.payload.get("target")
        if not isinstance(target, dict):
            return False
        if prev is None:  # 根层：world_variables 域事件
            return target.get("kind") == "state_domain" and target.get("domain") == "world_variables"
        return target.get("entity_id") == "ent_x" and target.get("component_type") == prev


class TestCascadeTreeAssembly:
    """根 depth=0、级联 depth+1、CascadeContext 全链一致（§7.1/§7.6）。"""

    def test_root_only_rounds_carry_depth_zero_context(self, f: _EffectFactory) -> None:
        executor = CascadeExecutor(policy=_permissive_policy())
        result = executor.run(
            [
                f.proposed(
                    "core.set_world_variable", _gold_target(), {"key": "gold", "value": 5}
                )
            ],
            _base_state(),
            causal_root_id="act_root_a",
            origin=_origin(),
        )
        assert len(result.transactions) == 1
        txn = result.transactions[0]
        assert txn.cascade is not None
        assert txn.cascade.depth == 0
        assert txn.cascade.causal_root_id == "act_root_a"
        assert len(result.events) == 1
        event = result.events[0]
        assert event.cascade is not None
        assert event.cascade == txn.cascade  # 同一 cascade_id / root / depth
        # 事件 world_revision == 事务 commit_revision（Spec §21.1）
        assert event.world_revision == txn.commit_revision

    def test_three_level_chain_depths_and_causal_tree(self, f: _EffectFactory) -> None:
        """0 → 1 → 2 层触发成功：depth 0/1/2、revision 恰 +3、K6 因果链。"""
        registry = _ChainTriggers(f, stops_at=2, component_tags=["layer.d1", "layer.d2"]).build_registry()
        policy = _permissive_policy(writers=("rule.test", "rule.chain"))
        executor = CascadeExecutor(policy=policy, triggers=registry)
        root_state = _base_state()
        result = executor.run(
            [
                f.proposed(
                    "core.set_world_variable",
                    _gold_target(),
                    {"key": "gold", "value": 5},
                )
            ],
            root_state,
            causal_root_id="act_root_b",
            origin=_origin(),
        )
        # 三层全部提交，depth 严格递增
        assert [t.cascade.depth for t in result.transactions] == [0, 1, 2]
        assert all(t.status is TransactionStatus.COMMITTED for t in result.transactions)
        # revision 恰 +3（Spec §9：每个 COMMITTED 恰 +1，连续无跳号）
        assert result.final_state.world_revision == Revision(3)
        assert [int(t.commit_revision) for t in result.transactions] == [1, 2, 3]
        assert root_state.world_revision == Revision(0)  # 输入状态不被触碰
        # cascade_id / root 全链一致（§7.6 因果树验收）
        cascade_ids = {str(t.cascade.cascade_id) for t in result.transactions}
        roots = {t.cascade.causal_root_id for t in result.transactions}
        assert len(cascade_ids) == 1
        assert roots == {"act_root_b"}
        for event in result.events:
            assert event.cascade is not None
            assert str(event.cascade.cascade_id) in cascade_ids
            assert event.cascade.causal_root_id == "act_root_b"
        # 事件 depth 与所在事务一致
        for event in result.events:
            owner = next(
                t for t in result.transactions if t.transaction_id == event.transaction_id
            )
            assert event.cascade is not None and owner.cascade is not None
            assert event.cascade.depth == owner.cascade.depth
        assert len(result.events) == 3
        # K6 cause_ids 链：depth-d 事件 → EFFECT ref → depth-d 提案 →
        # EVENT ref → depth-(d-1) 事件（effect↔event 交替衔接）
        by_depth = {t.cascade.depth: t for t in result.transactions}
        for depth in (1, 2):
            event = next(
                e for e in result.events if e.cascade is not None and e.cascade.depth == depth
            )
            effect_ref = next(c.ref_id for c in event.cause_ids if c.kind is CauseKind.EFFECT)
            committed = by_depth[depth].effects
            effect = next(
                ce.effect for ce in committed if str(ce.effect.effect_id) == effect_ref
            )
            prior_event_ids = {
                str(e.event_id)
                for e in result.events
                if e.cascade is not None and e.cascade.depth == depth - 1
            }
            cause_refs = [c.ref_id for c in effect.cause_ids if c.kind is CauseKind.EVENT]
            assert cause_refs and all(ref in prior_event_ids for ref in cause_refs)

    def test_causal_tree_traceable_back_to_root_proposal(self, f: _EffectFactory) -> None:
        """任一深度的提案可沿 cause_ids 回溯至 depth 0 的根提案（§7.6）。"""
        registry = _ChainTriggers(f, stops_at=2, component_tags=["layer.d1", "layer.d2"]).build_registry()
        policy = _permissive_policy(writers=("rule.test", "rule.chain"))
        executor = CascadeExecutor(policy=policy, triggers=registry)
        root_proposal = f.proposed(
            "core.set_world_variable", _gold_target(), {"key": "gold", "value": 5}
        )
        result = executor.run(
            [root_proposal],
            _base_state(),
            causal_root_id="act_root_c",
            origin=_origin(),
        )
        # depth-2 提案 → depth-1 事件 → depth-1 提案 → depth-0 事件 → 根提案
        depth2_effect = result.transactions[2].effects[0].effect
        depth1_event = next(
            e
            for e in result.events
            if str(e.event_id)
            == next(c.ref_id for c in depth2_effect.cause_ids if c.kind is CauseKind.EVENT)
        )
        assert depth1_event.cascade is not None and depth1_event.cascade.depth == 1
        depth1_effect = next(
            ce.effect
            for ce in result.transactions[1].effects
            if str(ce.effect.effect_id)
            == next(c.ref_id for c in depth1_event.cause_ids if c.kind is CauseKind.EFFECT)
        )
        root_event = next(
            e
            for e in result.events
            if str(e.event_id)
            == next(c.ref_id for c in depth1_effect.cause_ids if c.kind is CauseKind.EVENT)
        )
        assert root_event.cascade is not None and root_event.cascade.depth == 0
        # 根事件回指根提案（EFFECT 自引用，§6.4）
        assert any(
            c.kind is CauseKind.EFFECT and c.ref_id == str(root_proposal.effect_id)
            for c in root_event.cause_ids
        )


class TestMultiLevelCascade:
    """多层级联触发逻辑（任务包测试要求：0 → 1 → 2 层触发成功）。"""

    def test_zero_to_two_trigger_success(self, f: _EffectFactory) -> None:
        registry = _ChainTriggers(f, stops_at=2, component_tags=["layer.d1", "layer.d2"]).build_registry()
        policy = _permissive_policy(writers=("rule.test", "rule.chain"))
        executor = CascadeExecutor(policy=policy, triggers=registry)
        result = executor.run(
            [
                f.proposed(
                    "core.set_world_variable",
                    _gold_target(),
                    {"key": "gold", "value": 5},
                )
            ],
            _base_state(),
            causal_root_id="act_root_m1",
            origin=_origin(),
        )
        assert [t.cascade.depth for t in result.transactions] == [0, 1, 2]
        final = result.final_state
        entity = final.entities[EntityId("ent_x")]
        # 每层落在不同位置（触发链设计），全部生效
        component_ids = {str(k) for k in entity.components}
        assert "layer.d1" in component_ids
        assert "layer.d2" in component_ids
        assert final.world_variables["gold"] == 5
        assert result.diagnostics == ()
        assert result.deferred == ()

    def test_cascade_converges_when_triggers_stop(self, f: _EffectFactory) -> None:
        """触发器只响应一次（depth 0 事件）→ 级联在 depth 1 后收敛。"""
        fired = {"n": 0}

        def fn(events: list[DomainEvent], state: Any, depth: int) -> list[ProposedEffect]:
            if not events or depth != 0 or fired["n"] >= 1:
                return []
            fired["n"] += 1
            return [
                f.proposed(
                    "core.set_component",
                    EntityTarget(
                        entity_id=EntityId("ent_x"),
                        component_type=ComponentTypeId("layer.once"),
                    ),
                    {"v": 1},
                    base_revision=int(state.world_revision),
                    source="rule.chain",
                    cause_ids=[
                        CauseRef(kind=CauseKind.EVENT, ref_id=str(events[0].event_id))
                    ],
                )
            ]

        registry = CascadeTriggerRegistry()
        registry.register(SyncTrigger("rule.once", fn))
        policy = _permissive_policy(writers=("rule.test", "rule.chain"))
        executor = CascadeExecutor(policy=policy, triggers=registry)
        result = executor.run(
            [
                f.proposed(
                    "core.set_world_variable", _gold_target(), {"key": "gold", "value": 9}
                )
            ],
            _base_state(),
            causal_root_id="act_root_m2",
            origin=_origin(),
        )
        assert [t.cascade.depth for t in result.transactions] == [0, 1]
        assert result.final_state.world_revision == Revision(2)
        assert result.diagnostics == ()

    def test_no_triggers_single_round(self, f: _EffectFactory) -> None:
        """无触发器 = 单回合执行器（depth 0 后收敛）。"""
        executor = CascadeExecutor(policy=_permissive_policy())
        result = executor.run(
            [
                f.proposed(
                    "core.set_world_variable", _gold_target(), {"key": "gold", "value": 3}
                )
            ],
            _base_state(),
            causal_root_id="act_root_m3",
            origin=_origin(),
        )
        assert len(result.transactions) == 1
        assert result.final_state.world_revision == Revision(1)


# —— 深度熔断（§7.1/§7.3；任务包测试要求 2）——


class _SelfSustainingTriggers:
    """自持触发链：每回合在任何事件后续级一个新位置（component
    ``depth.<d>`` 每层唯一 → 与环路检测正交，纯测深度熔断）。"""

    def __init__(self, factory: _EffectFactory) -> None:
        self._f = factory

    def build_registry(self) -> CascadeTriggerRegistry:
        def fn(events: list[DomainEvent], state: Any, depth: int) -> list[ProposedEffect]:
            if not events:
                return []
            return [
                self._f.proposed(
                    "core.set_component",
                    EntityTarget(
                        entity_id=EntityId("ent_x"),
                        component_type=ComponentTypeId(f"depth.d{depth}"),
                    ),
                    {"v": depth},
                    base_revision=int(state.world_revision),
                    source="rule.sustain",
                    cause_ids=[
                        CauseRef(kind=CauseKind.EVENT, ref_id=str(events[0].event_id))
                    ],
                )
            ]

        registry = CascadeTriggerRegistry()
        registry.register(SyncTrigger("rule.sustain", fn))
        return registry


class TestDepthFuse:
    """深度熔断：默认 8（至多 9 COMMITTED）/ 自定义上限 / strict 异常。"""

    def test_default_cap_stops_before_depth_nine(self, f: _EffectFactory) -> None:
        """D-P2-13：depth 0..8 至多 9 个 COMMITTED，depth 9 不启动 + 诊断。"""
        policy = _permissive_policy(writers=("rule.test", "rule.sustain"))
        executor = CascadeExecutor(
            policy=policy, triggers=_SelfSustainingTriggers(f).build_registry()
        )
        result = executor.run(
            [
                f.proposed(
                    "core.set_world_variable", _gold_target(), {"key": "gold", "value": 1}
                )
            ],
            _base_state(),
            causal_root_id="act_root_depth",
            origin=_origin(),
        )
        # 至多 9 个 COMMITTED（depth 0..8），revision 至多 +9
        committed = [t for t in result.transactions if t.status is TransactionStatus.COMMITTED]
        assert len(committed) == 9
        assert [t.cascade.depth for t in committed] == list(range(9))
        assert result.final_state.world_revision == Revision(9)
        # 深度熔断诊断：被拒回合 depth = 9（= max + 1）
        assert len(result.diagnostics) == 1
        diag = result.diagnostics[0]
        assert diag.kind == "cascade_depth_exceeded"
        assert diag.depth == 9
        assert "max_cascade_depth=8" in diag.detail
        # SYSTEM trace 冻结 payload 键名（§7.4）
        system = _traces_of(TraceKind.SYSTEM, result.trace_records)
        assert len(system) == 1
        assert system[0]["diagnostic"] == "cascade_depth_exceeded"
        assert system[0]["depth"] == 9
        assert set(system[0]) == {"diagnostic", "cascade_id", "depth", "detail"}
        assert str(committed[0].cascade.cascade_id) == system[0]["cascade_id"]

    def test_custom_cap(self, f: _EffectFactory) -> None:
        policy = _permissive_policy(writers=("rule.test", "rule.sustain"))
        executor = CascadeExecutor(
            policy=policy,
            triggers=_SelfSustainingTriggers(f).build_registry(),
            config=CascadeConfig(max_cascade_depth=2),
        )
        result = executor.run(
            [
                f.proposed(
                    "core.set_world_variable", _gold_target(), {"key": "gold", "value": 1}
                )
            ],
            _base_state(),
            causal_root_id="act_root_depth2",
            origin=_origin(),
        )
        assert [t.cascade.depth for t in result.transactions] == [0, 1, 2]
        assert result.final_state.world_revision == Revision(3)
        assert [d.kind for d in result.diagnostics] == ["cascade_depth_exceeded"]
        assert result.diagnostics[0].depth == 3

    def test_zero_cap_root_only(self, f: _EffectFactory) -> None:
        policy = _permissive_policy(writers=("rule.test", "rule.sustain"))
        executor = CascadeExecutor(
            policy=policy,
            triggers=_SelfSustainingTriggers(f).build_registry(),
            config=CascadeConfig(max_cascade_depth=0),
        )
        result = executor.run(
            [
                f.proposed(
                    "core.set_world_variable", _gold_target(), {"key": "gold", "value": 1}
                )
            ],
            _base_state(),
            causal_root_id="act_root_depth0",
            origin=_origin(),
        )
        assert [t.cascade.depth for t in result.transactions] == [0]
        assert result.final_state.world_revision == Revision(1)
        assert [d.kind for d in result.diagnostics] == ["cascade_depth_exceeded"]

    def test_strict_mode_raises(self, f: _EffectFactory) -> None:
        """strict 模式：同一熔断点抛出 CascadeDepthExceededError（任务包表面）。"""
        policy = _permissive_policy(writers=("rule.test", "rule.sustain"))
        executor = CascadeExecutor(
            policy=policy,
            triggers=_SelfSustainingTriggers(f).build_registry(),
            config=CascadeConfig(max_cascade_depth=2, strict=True),
        )
        with pytest.raises(CascadeDepthExceededError) as exc_info:
            executor.run(
                [
                    f.proposed(
                        "core.set_world_variable",
                        _gold_target(),
                        {"key": "gold", "value": 1},
                    )
                ],
                _base_state(),
                causal_root_id="act_root_strict",
                origin=_origin(),
            )
        err = exc_info.value
        assert err.depth == 3
        assert err.max_cascade_depth == 2
        assert isinstance(err, CascadeError)
        assert isinstance(err, ValueError)
        # cascade_id 为合法 CascadeId 形态（csc_ 前缀，ids.py）
        assert err.cascade_id.startswith("csc_")


# —— 环路检测与熔断（§7.5；任务包测试要求 3；P2-T08）——


class _HpLoopTrigger:
    """spec §11 类别 5 原型：HP 变化 → 触发规则 → 又改 HP。"""

    def __init__(self, factory: _EffectFactory) -> None:
        self._f = factory

    def build_registry(self) -> CascadeTriggerRegistry:
        def fn(events: list[DomainEvent], state: Any, depth: int) -> list[ProposedEffect]:
            if not events:
                return []
            # 仅对 (ent_x, attrs) 组件位置的事件回环（target 载荷判定）
            hp_events = [
                e
                for e in events
                if e.payload.get("target", {}).get("entity_id") == "ent_x"
                and e.payload.get("target", {}).get("component_type") == "attrs"
            ]
            if not hp_events:
                return []
            return [
                self._f.proposed(
                    "core.set_component",
                    _hp_target(),
                    {"hp": 5},
                    base_revision=int(state.world_revision),
                    source="rule.on_hp_changed",
                    cause_ids=[
                        CauseRef(kind=CauseKind.EVENT, ref_id=str(hp_events[0].event_id))
                    ],
                )
            ]

        registry = CascadeTriggerRegistry()
        registry.register(SyncTrigger("rule.on_hp_changed", fn))
        return registry


class TestCycleDetection:
    """直接/间接环路检测并熔断（CycleDetector；D-P2-14）。"""

    def test_direct_cycle_hp_loop_fuses_and_converges(self, f: _EffectFactory) -> None:
        """HP变化→规则→又改HP：depth 1 回环提案被丢弃 + 诊断，无异常收敛。"""
        policy = _permissive_policy(writers=("rule.test", "rule.on_hp_changed"))
        executor = CascadeExecutor(
            policy=policy, triggers=_HpLoopTrigger(f).build_registry()
        )
        result = executor.run(
            [f.proposed("core.set_component", _hp_target(), {"hp": 10})],
            _base_state(),
            causal_root_id="act_root_hp",
            origin=_origin(),
        )
        # 级联正常收敛（无异常）：仅根回合提交
        assert len(result.transactions) == 1
        assert result.transactions[0].status is TransactionStatus.COMMITTED
        assert result.transactions[0].cascade.depth == 0
        # 回环提案被丢弃：状态停在根回合结果（hp=10，非触发器的 5）
        entity = result.final_state.entities[EntityId("ent_x")]
        assert entity.components[ComponentTypeId("attrs")] == {"hp": 10}
        assert result.final_state.world_revision == Revision(1)
        # 环路诊断：depth=1、detail 重建 "深度/位置" 链（含祖先深度）
        assert len(result.diagnostics) == 1
        diag = result.diagnostics[0]
        assert diag.kind == "cycle_detected"
        assert diag.depth == 1
        assert "[depth0]" in diag.detail
        assert "entity:ent_x:comp:attrs" in diag.detail
        # SYSTEM trace 冻结 payload 键名
        system = _traces_of(TraceKind.SYSTEM, result.trace_records)
        assert len(system) == 1
        assert system[0]["diagnostic"] == "cycle_detected"
        assert system[0]["depth"] == 1
        assert set(system[0]) == {"diagnostic", "cascade_id", "depth", "detail"}
        assert result.deferred == ()

    def test_indirect_cycle_two_step_loop_fuses(self, f: _EffectFactory) -> None:
        """间接环路：A → B → A 两步链，重访 A 已提交位置时熔断。"""

        def respond_on(component: str, next_component: str) -> SyncTrigger:
            def fn(events: list[DomainEvent], state: Any, depth: int) -> list[ProposedEffect]:
                if not events:
                    return []
                matched = [
                    e
                    for e in events
                    if e.payload.get("target", {}).get("entity_id") == "ent_x"
                    and e.payload.get("target", {}).get("component_type") == component
                ]
                if not matched:
                    return []
                return [
                    f.proposed(
                        "core.set_component",
                        EntityTarget(
                            entity_id=EntityId("ent_x"),
                            component_type=ComponentTypeId(next_component),
                        ),
                        {"v": 1},
                        base_revision=int(state.world_revision),
                        source="rule.loop",
                        cause_ids=[
                            CauseRef(kind=CauseKind.EVENT, ref_id=str(matched[0].event_id))
                        ],
                    )
                ]

            return SyncTrigger(f"rule.on_{component.replace('.', '_')}", fn)

        registry = CascadeTriggerRegistry()
        registry.register(respond_on("attrs.a", "attrs.b"))
        registry.register(respond_on("attrs.b", "attrs.a"))
        policy = _permissive_policy(writers=("rule.test", "rule.loop"))
        executor = CascadeExecutor(policy=policy, triggers=registry)
        result = executor.run(
            [
                f.proposed(
                    "core.set_component",
                    EntityTarget(
                        entity_id=EntityId("ent_x"),
                        component_type=ComponentTypeId("attrs.a"),
                    ),
                    {"v": 1},
                )
            ],
            _base_state(),
            causal_root_id="act_root_loop2",
            origin=_origin(),
        )
        # depth 0 提交 A；depth 1 提交 B（新位置，非重访）；
        # depth 2 回环 A → 重访祖先已提交位置 → 熔断
        assert [t.cascade.depth for t in result.transactions] == [0, 1]
        assert [t.status for t in result.transactions] == [
            TransactionStatus.COMMITTED,
            TransactionStatus.COMMITTED,
        ]
        assert result.final_state.world_revision == Revision(2)
        assert len(result.diagnostics) == 1
        diag = result.diagnostics[0]
        assert diag.kind == "cycle_detected"
        assert diag.depth == 2
        assert "[depth0]" in diag.detail  # A 首次提交于 depth 0
        assert "entity:ent_x:comp:attrs.a" in diag.detail

    def test_allow_mode_degrades_to_depth_cap_only(self, f: _EffectFactory) -> None:
        """location_revisit='allow'：同位置回环不熔断，仅深度上限收敛。"""
        policy = _permissive_policy(writers=("rule.test", "rule.on_hp_changed"))
        executor = CascadeExecutor(
            policy=policy,
            triggers=_HpLoopTrigger(f).build_registry(),
            config=CascadeConfig(location_revisit="allow", max_cascade_depth=2),
        )
        result = executor.run(
            [f.proposed("core.set_component", _hp_target(), {"hp": 10})],
            _base_state(),
            causal_root_id="act_root_allow",
            origin=_origin(),
        )
        # 无环路诊断；同位置回环一直持续到深度上限（3 个 COMMITTED）
        assert [t.cascade.depth for t in result.transactions] == [0, 1, 2]
        assert [d.kind for d in result.diagnostics] == ["cascade_depth_exceeded"]
        # 每回合触发器都把 hp 写回 5 → 终态 hp=5（depth-2 提交值）
        entity = result.final_state.entities[EntityId("ent_x")]
        assert entity.components[ComponentTypeId("attrs")] == {"hp": 5}

    def test_strict_mode_raises_cycle_error(self, f: _EffectFactory) -> None:
        """strict 模式：环路熔断抛出 CascadeCycleError（任务包表面）。"""
        policy = _permissive_policy(writers=("rule.test", "rule.on_hp_changed"))
        executor = CascadeExecutor(
            policy=policy,
            triggers=_HpLoopTrigger(f).build_registry(),
            config=CascadeConfig(strict=True),
        )
        with pytest.raises(CascadeCycleError) as exc_info:
            executor.run(
                [f.proposed("core.set_component", _hp_target(), {"hp": 10})],
                _base_state(),
                causal_root_id="act_root_strict_cycle",
                origin=_origin(),
            )
        err = exc_info.value
        assert err.depth == 1
        assert err.hit is not None
        assert err.hit.ancestor_depth == 0
        assert err.hit.key == ConflictKey(
            kind="entity",
            entity_id=EntityId("ent_x"),
            component_type=ComponentTypeId("attrs"),
        )
        assert "entity:ent_x:comp:attrs" in err.detail
        assert err.cascade_id.startswith("csc_")
        assert isinstance(err, CascadeError)

    def test_distinct_positions_do_not_false_fuse(self, f: _EffectFactory) -> None:
        """防过熔断：不同位置的级联（含同实体不同组件）不误报环路。"""

        def fn(events: list[DomainEvent], state: Any, depth: int) -> list[ProposedEffect]:
            if not events or depth >= 2:
                return []
            tag = "inv.gold" if depth == 0 else "inv.gem"
            matched = [
                e
                for e in events
                if e.payload.get("target", {}).get("entity_id") == "ent_x"
                and e.payload.get("target", {}).get("component_type") == "attrs"
            ] if depth == 0 else [
                e
                for e in events
                if e.payload.get("target", {}).get("entity_id") == "ent_alice"
                and e.payload.get("target", {}).get("component_type") == "inv.gold"
            ]
            if not matched:
                return []
            return [
                f.proposed(
                    "core.set_component",
                    EntityTarget(
                        entity_id=EntityId("ent_alice"),
                        component_type=ComponentTypeId(tag),
                    ),
                    {"n": depth},
                    base_revision=int(state.world_revision),
                    source="rule.chain",
                    cause_ids=[
                        CauseRef(kind=CauseKind.EVENT, ref_id=str(matched[0].event_id))
                    ],
                )
            ]

        registry = CascadeTriggerRegistry()
        registry.register(SyncTrigger("rule.distinct", fn))
        policy = _permissive_policy(writers=("rule.test", "rule.chain"))
        executor = CascadeExecutor(policy=policy, triggers=registry)
        result = executor.run(
            [f.proposed("core.set_component", _hp_target(), {"hp": 20})],
            _base_state(),
            causal_root_id="act_root_nocycle",
            origin=_origin(),
        )
        # 根（ent_x/attrs）→ depth 1（ent_alice/inv.gold）→ depth 2
        # （ent_alice/inv.gem）：全部新位置，零诊断
        assert [t.cascade.depth for t in result.transactions] == [0, 1, 2]
        assert result.diagnostics == ()
        assert len(result.events) == 3


# —— CascadeExecutor 端到端流水线（§7.3；任务包测试要求 4）——


class TestEndToEndPipeline:
    """从初始提案到最终状态与事件流的完整管道 + 审计面。"""

    def test_mixed_batch_full_audit_surface(self, f: _EffectFactory) -> None:
        """混合批：deny / 校验失败 / 双写冲突 / 合法提交 + 触发器续级。"""
        # 初始批（到达序）：
        #   e1 set gold=10        → 授权 + 通过 → 冲突组胜者（FIFO）
        #   e2 set silver=1       → 授权拒绝（intruder 不在 writers）
        #   e3 set comp ent_missing → 校验失败（missing_entity）
        #   e4 set gold=20        → 授权 + 通过 → 冲突组落选
        #   e5 set gold=30        → 授权 + 通过 → 冲突组落选
        e1 = f.proposed("core.set_world_variable", _gold_target(), {"key": "gold", "value": 10})
        e2 = f.proposed(
            "core.set_world_variable",
            _gold_target(),
            {"key": "silver", "value": 1},
            source="intruder",
        )
        e3 = f.proposed(
            "core.set_component",
            EntityTarget(
                entity_id=EntityId("ent_missing"), component_type=ComponentTypeId("attrs")
            ),
            {"hp": 1},
        )
        e4 = f.proposed(
            "core.set_world_variable", _gold_target(), {"key": "gold", "value": 20}
        )
        e5 = f.proposed(
            "core.set_world_variable", _gold_target(), {"key": "gold", "value": 30}
        )

        # 触发器：对 depth-0 事件续级一个新组件位置（depth 1）
        def fn(events: list[DomainEvent], state: Any, depth: int) -> list[ProposedEffect]:
            if not events or depth != 0:
                return []
            return [
                f.proposed(
                    "core.set_component",
                    EntityTarget(
                        entity_id=EntityId("ent_alice"),
                        component_type=ComponentTypeId("e2e.probe"),
                    ),
                    {"ok": True},
                    base_revision=int(state.world_revision),
                    source="rule.e2e",
                    cause_ids=[
                        CauseRef(kind=CauseKind.EVENT, ref_id=str(events[0].event_id))
                    ],
                )
            ]

        registry = CascadeTriggerRegistry()
        registry.register(SyncTrigger("rule.e2e", fn))
        policy = _permissive_policy(writers=("rule.test", "rule.e2e"))
        executor = CascadeExecutor(policy=policy, triggers=registry)
        initial_state = _base_state()
        result = executor.run(
            [e1, e2, e3, e4, e5],
            initial_state,
            causal_root_id="act_root_e2e",
            origin=_origin(),
        )

        # —— 最终状态：胜者 gold=10（FIFO），败者不落，触发器组件生效 ——
        assert result.final_state.world_variables["gold"] == 10
        assert result.final_state.world_variables["silver"] == 0  # deny 不落
        assert not result.final_state.has_entity(EntityId("ent_missing"))
        alice = result.final_state.entities[EntityId("ent_alice")]
        assert alice.components[ComponentTypeId("e2e.probe")] == {"ok": True}
        assert result.final_state.world_revision == Revision(2)
        # 输入状态不被触碰（纯函数管道）
        assert initial_state.world_variables["gold"] == 0
        assert initial_state.world_revision == Revision(0)

        # —— 事务：depth 0 / 1 各一个 COMMITTED ——
        assert [t.status for t in result.transactions] == [
            TransactionStatus.COMMITTED,
            TransactionStatus.COMMITTED,
        ]
        assert [t.cascade.depth for t in result.transactions] == [0, 1]
        root_txn = result.transactions[0]
        assert [ce.effect.effect_id for ce in root_txn.effects] == [e1.effect_id]
        assert root_txn.commit_revision == Revision(1)
        assert result.transactions[1].commit_revision == Revision(2)

        # —— 事件：1:1 于已提交 effect（2 条），K6 六要素 ——
        assert len(result.events) == 2
        for event in result.events:
            assert event.transaction_id in {
                t.transaction_id for t in result.transactions
            }
            assert event.cascade is not None
            assert event.cascade.cascade_id == root_txn.cascade.cascade_id
            assert event.cascade.causal_root_id == "act_root_e2e"
            assert event.world_revision == event.cascade.depth + 1  # == commit_revision
            assert any(c.kind is CauseKind.EFFECT for c in event.cause_ids)
        root_event = result.events[0]
        assert root_event.source_system == e1.source
        assert any(
            c.kind is CauseKind.EFFECT and c.ref_id == str(e1.effect_id)
            for c in root_event.cause_ids
        )

        # —— trace 审计面（§9 汇总表）——
        records = result.trace_records
        proposed = _traces_of(TraceKind.PROPOSED_EFFECT, records)
        assert len(proposed) == 6  # 初始 5 + 触发器 1
        trigger_effect_id = result.transactions[1].effects[0].effect.effect_id
        assert {p["record"]["effect_id"] for p in proposed} == {
            str(x.effect_id) for x in (e1, e2, e3, e4, e5)
        } | {trigger_effect_id}
        # 坐标填充：cascade_id 全记录关联
        assert all(r.cascade_id is not None for r in records)
        for record in records:
            if record.kind is TraceKind.PROPOSED_EFFECT:
                assert record.cascade_id == root_txn.cascade.cascade_id

        authority = _traces_of(TraceKind.AUTHORITY_DECISION, records)
        assert len(authority) == 6  # 每个入回合提案各一条（初始 5 + 触发器 1）
        by_effect = {a["effect_id"]: a for a in authority}
        assert by_effect[str(e2.effect_id)]["decision"] == "deny"
        assert "rule_deny" in by_effect[str(e2.effect_id)]["reason"]
        for allowed in (e1, e3, e4, e5):
            assert by_effect[str(allowed.effect_id)]["decision"] == "allow"
        assert by_effect[str(trigger_effect_id)]["decision"] == "allow"

        validation = _traces_of(TraceKind.VALIDATION_DECISION, records)
        assert len(validation) == 5  # e2 被 authority 过滤，未进校验
        v_by_effect = {v["effect_id"]: v for v in validation}
        assert v_by_effect[str(e3.effect_id)]["decision"] == "fail"
        assert "missing_entity" in v_by_effect[str(e3.effect_id)]["reason"]
        for passed in (e1, e4, e5):
            assert v_by_effect[str(passed.effect_id)]["decision"] == "pass"
        assert v_by_effect[str(trigger_effect_id)]["decision"] == "pass"

        conflicts = _traces_of(TraceKind.CONFLICT_RESOLUTION, records)
        assert len(conflicts) == 1
        assert conflicts[0]["decision"] == "winner"
        assert conflicts[0]["effect_id"] == str(e1.effect_id)  # 胜者（FIFO）
        assert "entity_fifo" in conflicts[0]["reason"]

        transactions = _traces_of(TraceKind.TRANSACTION, records)
        assert len(transactions) == 2
        for tx_trace in transactions:
            assert tx_trace["record"]["status"] == "committed"
            assert tx_trace["record"]["cascade"]["depth"] in (0, 1)

        events_trace = _traces_of(TraceKind.DOMAIN_EVENT, records)
        assert len(events_trace) == 2
        for ev_trace in events_trace:
            assert ev_trace["record"]["cascade"]["causal_root_id"] == "act_root_e2e"

        # —— 级联统计（任务包表面）——
        assert result.cascade_statistics == CascadeStatistics(
            committed=2,
            aborted=0,
            max_committed_depth=1,
            events_emitted=2,
            diagnostic_count=0,
        )
        assert result.diagnostics == ()
        assert result.deferred == ()

    def test_input_state_not_mutated_on_success(self, f: _EffectFactory) -> None:
        executor = CascadeExecutor(policy=_permissive_policy())
        initial = _base_state()
        result = executor.run(
            [
                f.proposed(
                    "core.set_world_variable", _gold_target(), {"key": "gold", "value": 7}
                )
            ],
            initial,
            causal_root_id="act_root_imm",
            origin=_origin(),
        )
        assert initial.world_revision == Revision(0)
        assert initial.world_variables["gold"] == 0
        assert result.final_state is not initial
        assert result.final_state.world_variables["gold"] == 7

    def test_aborted_round_stops_cascade(self, f: _EffectFactory) -> None:
        """reducer 应用失败 → 整事务 ABORTED → 级联停止（原子失败审计）。"""
        handlers = default_handler_registry()

        def boom_handler(state: WorldState, effect: ProposedEffect) -> WorldState:
            raise ReducerError("rule.boom 处理器故障（模拟 reducer 应用失败）")

        handlers.register(EffectTypeId("rule.boom"), boom_handler)

        def fn(events: list[DomainEvent], state: Any, depth: int) -> list[ProposedEffect]:
            if not events:
                return []
            return [
                f.proposed(
                    "rule.boom",
                    EntityTarget(entity_id=EntityId("ent_x")),
                    {"arm": True},
                    base_revision=int(state.world_revision),
                    source="rule.boom",
                    cause_ids=[
                        CauseRef(kind=CauseKind.EVENT, ref_id=str(events[0].event_id))
                    ],
                )
            ]

        registry = CascadeTriggerRegistry()
        registry.register(SyncTrigger("rule.trigger_boom", fn))
        policy = _permissive_policy(writers=("rule.test", "rule.boom"))
        executor = CascadeExecutor(policy=policy, triggers=registry, handlers=handlers)
        initial = _base_state()
        result = executor.run(
            [
                f.proposed(
                    "core.set_world_variable", _gold_target(), {"key": "gold", "value": 5}
                )
            ],
            initial,
            causal_root_id="act_root_abort",
            origin=_origin(),
        )
        # 根回合提交；depth-1 回合 reducer 失败 → ABORTED → 级联停止
        assert [t.status for t in result.transactions] == [
            TransactionStatus.COMMITTED,
            TransactionStatus.ABORTED,
        ]
        aborted = result.transactions[1]
        assert aborted.cascade is not None and aborted.cascade.depth == 1
        assert aborted.commit_revision is None
        assert aborted.effects == []  # 部分提交不可表达（P1 §5.6 不变量 2）
        assert aborted.abort_reason is not None
        assert aborted.abort_reason.startswith("reducer_failed")
        # 状态停在根回合（gold=5，revision 1）；boom 未生效
        assert result.final_state.world_revision == Revision(1)
        assert result.final_state.world_variables["gold"] == 5
        assert initial.world_revision == Revision(0)
        # ABORTED 事务 trace 携带 rejected_effect_ids（§6.3/§9）
        transactions = _traces_of(TraceKind.TRANSACTION, result.trace_records)
        assert len(transactions) == 2
        aborted_trace = transactions[1]
        assert aborted_trace["record"]["status"] == "aborted"
        assert "rejected_effect_ids" in aborted_trace
        # 无 DOMAIN_EVENT（ABORTED 无事件）
        assert len(_traces_of(TraceKind.DOMAIN_EVENT, result.trace_records)) == 1

    def test_empty_initial_proposals_zero_rounds(self, f: _EffectFactory) -> None:
        executor = CascadeExecutor(policy=_permissive_policy())
        result = executor.run(
            [], _base_state(), causal_root_id="act_root_empty", origin=_origin()
        )
        assert result.transactions == ()
        assert result.events == ()
        assert result.trace_records == ()
        assert result.diagnostics == ()
        assert result.deferred == ()
        assert result.cascade_statistics == CascadeStatistics(
            committed=0, aborted=0, max_committed_depth=None,
            events_emitted=0, diagnostic_count=0,
        )

    def test_all_denied_round_is_empty_no_revision(self, f: _EffectFactory) -> None:
        """全拒批：空回合不消耗 revision（P1 §5.6 不变量 1 的管道镜像）。"""
        executor = CascadeExecutor(policy=_permissive_policy())
        initial = _base_state()
        result = executor.run(
            [
                f.proposed(
                    "core.set_world_variable",
                    _gold_target(),
                    {"key": "gold", "value": 1},
                    source="intruder",
                )
            ],
            initial,
            causal_root_id="act_root_denied",
            origin=_origin(),
        )
        assert result.transactions == ()
        assert result.events == ()
        assert result.final_state is initial  # 零提交：原状态对象
        assert result.final_state.world_revision == Revision(0)
        # 审计面仍在：提案 + 授权拒绝各一条
        assert len(_traces_of(TraceKind.PROPOSED_EFFECT, result.trace_records)) == 1
        authority = _traces_of(TraceKind.AUTHORITY_DECISION, result.trace_records)
        assert authority[0]["decision"] == "deny"
        assert result.diagnostics == ()

    def test_run_input_guards(self, f: _EffectFactory) -> None:
        executor = CascadeExecutor(policy=_permissive_policy())
        proposal = f.proposed(
            "core.set_world_variable", _gold_target(), {"key": "gold", "value": 1}
        )
        state = _base_state()
        with pytest.raises(CascadeError, match="ProposedEffect"):
            executor.run(
                ["not-an-effect"],  # type: ignore[list-item]
                state,
                causal_root_id="act_g",
                origin=_origin(),
            )
        with pytest.raises(CascadeError, match="WorldState"):
            executor.run(
                [proposal], "not-a-state",  # type: ignore[arg-type]
                causal_root_id="act_g",
                origin=_origin(),
            )
        with pytest.raises(CascadeError, match="causal_root_id"):
            executor.run([proposal], state, causal_root_id="", origin=_origin())
        with pytest.raises(CascadeError, match="Provenance"):
            executor.run(
                [proposal], state, causal_root_id="act_g",
                origin="not-provenance",  # type: ignore[arg-type]
            )

    def test_constructor_guards(self) -> None:
        with pytest.raises(CascadeError, match="AuthorityPolicy"):
            CascadeExecutor(policy="not-a-policy")  # type: ignore[arg-type]
        with pytest.raises(CascadeError, match="config"):
            CascadeExecutor(policy=_permissive_policy(), config="not-config")  # type: ignore[arg-type]
        with pytest.raises(CascadeError, match="cycle_detector"):
            CascadeExecutor(
                policy=_permissive_policy(), cycle_detector="not-detector"  # type: ignore[arg-type]
            )

    def test_init_installs_write_barrier(self) -> None:
        """kernel 运行时入口：构造即武装写屏障（§2.6.2，幂等）。"""
        assert write_barrier_installed() is False
        CascadeExecutor(policy=_permissive_policy())
        assert write_barrier_installed() is True
        CascadeExecutor(policy=_permissive_policy())  # 幂等，不抛
        assert write_barrier_installed() is True

    def test_trigger_receives_guarded_state(self, f: _EffectFactory) -> None:
        """管道面：触发器收到的是 GuardedWorldState 只读门面（§2.6.3/K2）。"""
        seen: dict[str, bool] = {}

        def fn(events: list[DomainEvent], state: Any, depth: int) -> list[ProposedEffect]:
            seen["guarded"] = is_guarded(state)
            seen["write_path_blocked"] = False
            try:
                state.model_copy(update={"world_revision": 99})
            except Exception:
                seen["write_path_blocked"] = True
            return []

        registry = CascadeTriggerRegistry()
        registry.register(SyncTrigger("rule.observe", fn))
        executor = CascadeExecutor(policy=_permissive_policy(), triggers=registry)
        executor.run(
            [
                f.proposed(
                    "core.set_world_variable", _gold_target(), {"key": "gold", "value": 1}
                )
            ],
            _base_state(),
            causal_root_id="act_root_guard",
            origin=_origin(),
        )
        assert seen["guarded"] is True
        assert seen["write_path_blocked"] is True

    def test_trigger_output_without_event_cause_is_dropped(self, f: _EffectFactory) -> None:
        """因果闭合检查（K6，§7.2 末段）：未回指本回合事件 → 丢弃 + 诊断。"""

        def fn(events: list[DomainEvent], state: Any, depth: int) -> list[ProposedEffect]:
            if not events:
                return []
            # 无 EVENT cause（空 cause_ids）→ 因果闭合失败
            return [
                ProposedEffect(
                    effect_id=EffectId("eff_casc_orphan"),
                    effect_type=EffectTypeId("core.set_component"),
                    source=ProducerId("rule.orphan"),
                    target=EntityTarget(
                        entity_id=EntityId("ent_x"),
                        component_type=ComponentTypeId("orphan.probe"),
                    ),
                    payload={"v": 1},
                    base_revision=int(state.world_revision),
                )
            ]

        registry = CascadeTriggerRegistry()
        registry.register(SyncTrigger("rule.orphan", fn))
        policy = _permissive_policy(writers=("rule.test", "rule.orphan"))
        executor = CascadeExecutor(policy=policy, triggers=registry)
        result = executor.run(
            [
                f.proposed(
                    "core.set_world_variable", _gold_target(), {"key": "gold", "value": 1}
                )
            ],
            _base_state(),
            causal_root_id="act_root_orphan",
            origin=_origin(),
        )
        # 孤儿提案被丢弃：级联仅根回合
        assert [t.cascade.depth for t in result.transactions] == [0]
        assert [d.kind for d in result.diagnostics] == ["trigger_output_dropped"]
        assert "eff_casc_orphan" in result.diagnostics[0].detail
        system = _traces_of(TraceKind.SYSTEM, result.trace_records)
        assert system[0]["diagnostic"] == "trigger_output_dropped"

    def test_defer_requeue_mechanics_and_residual(self, f: _EffectFactory) -> None:
        """DEFER 再入队机制（§5.5/§14 OQ3）：桩域解析器 + 深度上限兜底。"""

        class _StubDeferStrategy:
            name = "stub_defer"

            def resolve(self, group: Any, ctx: Any) -> ConflictResolution | None:
                return ConflictResolution(
                    action=ConflictAction.DEFER,
                    strategy=self.name,
                    accepted=tuple(e.effect_id for e in group.effects),
                    dropped=(),
                    reason="桩 DEFER：全部再入队（机制正确性测试）",
                )

        def defer_factory(group: Any, ctx: Any) -> Any:
            return _StubDeferStrategy()

        # 两个同锁提案（world_variables 域）→ 冲突组 → 桩 DEFER 全组
        d1 = f.proposed("core.set_world_variable", _gold_target(), {"key": "gold", "value": 1})
        d2 = f.proposed("core.set_world_variable", _gold_target(), {"key": "gold", "value": 2})
        policy = _permissive_policy()
        executor = CascadeExecutor(
            policy=policy,
            resolvers=defer_factory,
            config=CascadeConfig(max_cascade_depth=2),
        )
        result = executor.run(
            [d1, d2],
            _base_state(),
            causal_root_id="act_root_defer",
            origin=_origin(),
        )
        # 三回合（depth 0/1/2）全部 DEFER 空转 → depth 3 深度熔断
        assert result.transactions == ()
        assert result.final_state.world_revision == Revision(0)
        # 终态残留：两个 DEFER 提案未消化 → result.deferred（原到达序）
        assert result.deferred == (d1, d2)
        # 诊断：仅深度熔断（DEFER 本身无诊断 kind）
        assert [d.kind for d in result.diagnostics] == ["cascade_depth_exceeded"]
        # 审计面：CONFLICT_RESOLUTION trace decision=defer（逐回合各一条）
        conflicts = _traces_of(TraceKind.CONFLICT_RESOLUTION, result.trace_records)
        assert len(conflicts) == 3
        assert all(c["decision"] == "defer" for c in conflicts)
        assert all("stub_defer" in c["reason"] for c in conflicts)
        # PROPOSED_EFFECT trace：每回合都 trace 再入队提案（3 回合 × 2）
        assert len(_traces_of(TraceKind.PROPOSED_EFFECT, result.trace_records)) == 6

    def test_domain_resolver_winner_path(self, f: _EffectFactory) -> None:
        """域解析器钩子：拍板 WINNER 优先生效（弃权回落默认链）。"""

        class _StubWinnerStrategy:
            name = "stub_winner"

            def resolve(self, group: Any, ctx: Any) -> ConflictResolution | None:
                winner = group.effects[0].effect_id
                losers = tuple(
                    e.effect_id for e in group.effects if e.effect_id != winner
                )
                return ConflictResolution(
                    action=ConflictAction.WINNER,
                    strategy=self.name,
                    accepted=(winner,),
                    dropped=losers,
                    reason="桩域解析器拍板首个",
                )

        def winner_factory(group: Any, ctx: Any) -> Any:
            return _StubWinnerStrategy()

        w1 = f.proposed("core.set_world_variable", _gold_target(), {"key": "gold", "value": 11})
        w2 = f.proposed("core.set_world_variable", _gold_target(), {"key": "gold", "value": 22})
        policy = _permissive_policy()
        executor = CascadeExecutor(policy=policy, resolvers=winner_factory)
        result = executor.run(
            [w1, w2], _base_state(), causal_root_id="act_root_dres", origin=_origin()
        )
        assert result.final_state.world_variables["gold"] == 11
        conflicts = _traces_of(TraceKind.CONFLICT_RESOLUTION, result.trace_records)
        assert conflicts[0]["decision"] == "winner"
        assert "stub_winner" in conflicts[0]["reason"]

    # —— core.create_entity 管道路径（P2-REMEDIATION B1）——

    def test_create_entity_with_init_component_single_round(
        self, f: _EffectFactory
    ) -> None:
        """P2-REMEDIATION B1：同回合 create + 初始化 component.set 是暂存
        依赖——conflicts 不判冲突、L1/L2 放行、reducer 顺序应用落地。"""
        create = f.proposed(
            "core.create_entity",
            EntityTarget(entity_id=EntityId("ent_summoned")),
            {"entity_class": "item", "tags": ["treasure"], "components": {}},
        )
        init_pos = f.proposed(
            "core.set_component",
            EntityTarget(
                entity_id=EntityId("ent_summoned"),
                component_type=ComponentTypeId("space.position"),
            ),
            {"x": 3, "y": 4},
        )
        init_hp = f.proposed(
            "core.set_component",
            EntityTarget(
                entity_id=EntityId("ent_summoned"),
                component_type=ComponentTypeId("attrs"),
            ),
            {"hp": 5},
        )
        executor = CascadeExecutor(policy=_permissive_policy())
        result = executor.run(
            [create, init_pos, init_hp],
            _base_state(),
            causal_root_id="act_root_create",
            origin=_origin(),
        )

        assert len(result.transactions) == 1
        txn = result.transactions[0]
        assert txn.status is TransactionStatus.COMMITTED
        assert txn.commit_revision == Revision(1)
        assert result.final_state.world_revision == Revision(1)
        rec = result.final_state.entities[EntityId("ent_summoned")]
        assert rec.entity_class == "item"
        assert rec.tags == ["treasure"]
        assert rec.components == {
            ComponentTypeId("space.position"): {"x": 3, "y": 4},
            ComponentTypeId("attrs"): {"hp": 5},
        }
        assert len(result.events) == 3, "事件 1:1 发射（D-P2-12）"
        # 暂存依赖不判冲突：无 CONFLICT_RESOLUTION trace；L1 全通过
        assert _traces_of(TraceKind.CONFLICT_RESOLUTION, result.trace_records) == []
        validation = _traces_of(TraceKind.VALIDATION_DECISION, result.trace_records)
        assert len(validation) == 3
        assert all(v["decision"] == "pass" for v in validation)

    def test_cascade_trigger_followup_on_created_entity(self, f: _EffectFactory) -> None:
        """级联链：create_entity 事件触发第二回合对新实体的效果，完整落地
        （depth 0 create → depth 1 组件初始化，revision 恰 +2）。"""
        created_entity_id = EntityId("ent_summoned")

        def on_create(
            events: Sequence[DomainEvent], state: Any, depth: int
        ) -> list[ProposedEffect]:
            if depth != 0:
                return []
            out: list[ProposedEffect] = []
            for event in events:
                if str(event.event_type) != "core.create_entity":
                    continue
                entity_id = event.payload.get("target", {}).get("entity_id")
                if entity_id != str(created_entity_id):
                    continue
                out.append(
                    f.proposed(
                        "core.set_component",
                        EntityTarget(
                            entity_id=EntityId(entity_id),
                            component_type=ComponentTypeId("attrs"),
                        ),
                        {"hp": 12},
                        base_revision=int(state.world_revision),
                        cause_ids=[
                            CauseRef(
                                kind=CauseKind.EVENT, ref_id=str(event.event_id)
                            )
                        ],
                    )
                )
            return out

        registry = CascadeTriggerRegistry()
        registry.register(SyncTrigger("rule.on_create", on_create))
        policy = _permissive_policy()
        executor = CascadeExecutor(policy=policy, triggers=registry)

        create = f.proposed(
            "core.create_entity",
            EntityTarget(entity_id=created_entity_id),
            {"entity_class": "npc"},
        )
        result = executor.run(
            [create], _base_state(), causal_root_id="act_root_followup", origin=_origin()
        )

        assert [t.status for t in result.transactions] == [
            TransactionStatus.COMMITTED,
            TransactionStatus.COMMITTED,
        ]
        assert result.final_state.world_revision == Revision(2)
        rec = result.final_state.entities[created_entity_id]
        assert rec.components == {ComponentTypeId("attrs"): {"hp": 12}}
        assert [t.cascade.depth for t in result.transactions if t.cascade] == [0, 1]


# —— 导出面（D-P2-19 / §10.3）——


class TestExports:
    """cascade 模块导出面与包级 re-export 同一性。"""

    EXPECTED_MODULE_ALL: tuple[str, ...] = (
        "CASCADE_DIAGNOSTIC_KINDS",
        "CascadeConfig",
        "CascadeCycleError",
        "CascadeDepthExceededError",
        "CascadeDiagnostic",
        "CascadeError",
        "CascadeExecutionResult",
        "CascadeExecutor",
        "CascadeResult",
        "CascadeStatistics",
        "CascadeTrigger",
        "CascadeTriggerRegistry",
        "CycleDetector",
        "CycleHit",
        "DEFAULT_MAX_CASCADE_DEPTH",
        "SyncTrigger",
        "TriggerConflictError",
        "TriggerRegistry",
    )

    #: 包级 re-export 名 → 模块定义 的逐一配对（每个 pkg_* 导入恰被消费一次）。
    PAIRINGS: tuple[tuple[Any, Any], ...] = (
        (pkg_CASCADE_DIAGNOSTIC_KINDS, CASCADE_DIAGNOSTIC_KINDS),
        (pkg_CascadeConfig, CascadeConfig),
        (pkg_CascadeCycleError, CascadeCycleError),
        (pkg_CascadeDepthExceededError, CascadeDepthExceededError),
        (pkg_CascadeDiagnostic, CascadeDiagnostic),
        (pkg_CascadeError, CascadeError),
        (pkg_CascadeExecutionResult, CascadeExecutionResult),
        (pkg_CascadeExecutor, CascadeExecutor),
        (pkg_CascadeResult, CascadeResult),
        (pkg_CascadeStatistics, CascadeStatistics),
        (pkg_CascadeTrigger, CascadeTrigger),
        (pkg_CascadeTriggerRegistry, CascadeTriggerRegistry),
        (pkg_CycleDetector, CycleDetector),
        (pkg_CycleHit, CycleHit),
        (pkg_DEFAULT_MAX_CASCADE_DEPTH, DEFAULT_MAX_CASCADE_DEPTH),
        (pkg_SyncTrigger, SyncTrigger),
        (pkg_TriggerConflictError, TriggerConflictError),
        (pkg_TriggerRegistry, TriggerRegistry),
    )

    def test_module_all_surface(self) -> None:
        import src.engine_v2.core.cascade as module

        assert set(module.__all__) == set(self.EXPECTED_MODULE_ALL)
        assert len(module.__all__) == len(set(module.__all__)) == 18

    def test_package_reexport_same_object(self) -> None:
        for pkg_name, module_name in self.PAIRINGS:
            assert pkg_name is module_name, f"{module_name.__name__}: 包级 re-export 与模块定义不是同一对象"

    def test_aliases_same_class(self) -> None:
        """任务包别名：TriggerRegistry / CascadeExecutionResult 同一性。"""
        assert TriggerRegistry is CascadeTriggerRegistry
        assert CascadeExecutionResult is CascadeResult

    def test_exception_hierarchy(self) -> None:
        assert issubclass(CascadeDepthExceededError, CascadeError)
        assert issubclass(CascadeCycleError, CascadeError)
        assert issubclass(TriggerConflictError, CascadeError)
        assert issubclass(CascadeError, ValueError)

    def test_package_all_contains_cascade_names(self) -> None:
        assert set(self.EXPECTED_MODULE_ALL) <= set(core_pkg.__all__)

    def test_cascade_context_single_source(self) -> None:
        """CascadeContext 仍由 provenance 单一来源导出（cascade 不双源）。"""
        from src.engine_v2.core.provenance import CascadeContext as P1_CascadeContext

        assert core_pkg.CascadeContext is P1_CascadeContext
