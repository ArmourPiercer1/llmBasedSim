"""engine_v2 core 层 Transaction 装配与原子提交执行器（P2 设计规范 §6；
P2-T06 实现载体）。

**行为与契约分文件（D-P2-02）**：``transaction.py`` 是冻结的数据契约
（G1：public 字段/不变量冻结），事务**装配与提交行为**落在本文件，对
``transaction.py`` 零改动。两个公开函数：

- :func:`commit_transaction`（§6.2）：线性装配 + L2 终检接线 + reducer
  应用 + 事件发射 1:1 映射（D-P2-12）。成功 →
  ``(新 WorldState, COMMITTED Transaction, list[DomainEvent])``，
  ``commit_revision == base + 1``（Spec §9 恰 +1）；L2 终检或 reducer
  应用失败 → ``(base_state 原样, ABORTED Transaction, [])``，revision
  不动（D-P2-10 两层校验语义的 L2 侧；Plan 必须测试 3 的落点，§6.3）；
- :func:`abort_transaction`（§6.5）：ABORTED 事务的数据形态构造器
  （``commit_revision is None``、``effects == []``——部分提交在数据层
  不可表达，P1 §5.6 不变量 2）。

**原子性机制（§6.3）**：两类原子失败源统一表现为 ABORTED 事务 + 状态/
revision 原样——

1. **终检失败**：装配后调用 :func:`check_transaction_references`
   （P1 §10.1 义务 C2 的 core 实现，P2-T04 交付）报告
   ``missing_entity`` / ``stale_revision`` / ``duplicated_effect_id``
   → ``abort_reason="reference_check_failed: " + "; ".join(issues)``；
2. **reducer 应用失败**：``apply_transaction`` 抛
   :class:`EffectApplicationError`（携带 ``sequence``/``effect_id``）或
   批级 :class:`ReducerError`（防御性复检 / 未注册 effect_type）→
   ``abort_reason="reducer_failed[seq=<i>]: <detail>"``（单效果失败）或
   ``abort_reason="reducer_failed: <detail>"``（批级失败无单一 seq）。

纯函数保证 ``base_state`` 在任何路径下不被触碰——原子性零成本成立；
输入 :class:`WorldState` 全程不变，成功路径的新状态经 reducer 的
``_with_*`` 缝隙（model_dump → model_validate 重建）产出，与原状态
三向零别名（P1 §3.5 reducer-only 三纪律）。

**事件发射映射（D-P2-12，§6.4）**：每个 CommittedEffect 发射**恰好一
个** :class:`DomainEvent`，``event_type == effect_type``（1:1，EffectType
Id 与 EventTypeId 同词法空间），``cause_ids = [CauseRef(EFFECT,
effect_id)] + effect.cause_ids``，``provenance`` 的 origin 经
``producer_registry.origin_of``（未注册缺省 ``OriginKind.SYSTEM``）；
事件 ID 在事务构造**前**预分配（frozen 契约不可回填，§6.2 步骤 3）。

**实现纪律**：本模块不出现 ``model_copy(update=...)`` / ``model_construct``
（写屏障静态审计口径，§2.6.1——本文件不在白名单内）；写屏障的运行时武装
归 kernel 运行时入口（``CascadeExecutor.__init__``，P2-T07），本模块
依赖 reducer 内部 ``WriteBarrier()`` 作用域，自身不安装/卸载。

Import 边界（P1 设计 §0.3 继承）：只允许 stdlib + pydantic + 同包
``src.engine_v2``。
"""

from __future__ import annotations

from collections.abc import Sequence

from src.engine_v2.core.authority import ProducerRegistry
from src.engine_v2.core.components import ComponentRegistry
from src.engine_v2.core.effects import CommittedEffect, ProposedEffect
from src.engine_v2.core.events import DomainEvent
from src.engine_v2.core.ids import EventId, TransactionId, new_event_id
from src.engine_v2.core.provenance import (
    CascadeContext,
    CauseKind,
    CauseRef,
    OriginKind,
    Provenance,
)
from src.engine_v2.core.reducer import (
    EffectApplicationError,
    EffectHandlerRegistry,
    ReducerError,
    apply_transaction,
)
from src.engine_v2.core.revision import Revision
from src.engine_v2.core.state import WorldState
from src.engine_v2.core.transaction import Transaction, TransactionStatus
from src.engine_v2.core.validation import check_transaction_references

__all__ = [
    "commit_transaction",
    "abort_transaction",
]


def _reducer_failure_reason(err: ReducerError) -> str:
    """reducer 应用失败 → abort_reason（§6.2 步骤 7 / §6.3 失败源 2）。

    单效果失败（:class:`EffectApplicationError`，携带 ``sequence`` /
    ``effect_id``）→ ``reducer_failed[seq=<i>]: <detail>``，其中
    ``<detail>`` 为底层错误文本（剥离异常自身的 ``[seq=... effect_id=...]``
    定位前缀，避免 seq 双写）；批级失败（防御性复检 / 未注册 effect_type
    的 :class:`ReducerError`，无单一效果 seq）→ ``reducer_failed:
    <detail>``。
    """
    if isinstance(err, EffectApplicationError):
        prefix = f"[seq={err.sequence} effect_id={err.effect_id}] "
        text = str(err)
        detail = text[len(prefix) :] if text.startswith(prefix) else text
        return f"reducer_failed[seq={err.sequence}]: {detail}"
    return f"reducer_failed: {err}"


def _build_domain_event(
    committed: CommittedEffect,
    event_id: EventId,
    *,
    tx_id: TransactionId,
    commit_revision: Revision,
    logical_tick: int | None,
    cascade: CascadeContext | None,
    producer_registry: ProducerRegistry | None,
) -> DomainEvent:
    """CommittedEffect → DomainEvent 的 1:1 发射映射（D-P2-12，§6.4）。

    ``event_type == effect_type``（同词法空间）；``world_revision ==
    commit_revision``（Spec §21.1）；``cause_ids`` = EFFECT 自引用 +
    提案原 ``cause_ids`` 原样拼接（K6 因果链在事件上自包含可查）；
    ``source_system`` = 提案者（K6"谁提出"）；事件级 ``provenance`` 的
    origin 经 ``producer_registry.origin_of`` 解析（registry 缺省或
    producer 未注册 → ``OriginKind.SYSTEM``，与 ``origin_of`` 缺省语义
    一致）；``payload`` 为最小事实载荷（effect_id + target JSON 形态），
    语义载荷归 P5+ 模块。
    """
    effect = committed.effect
    origin = (
        producer_registry.origin_of(effect.source)
        if producer_registry is not None
        else OriginKind.SYSTEM
    )
    return DomainEvent(
        event_id=event_id,
        event_type=effect.effect_type,
        world_revision=commit_revision,
        logical_tick=logical_tick,
        transaction_id=tx_id,
        payload={
            "effect_id": str(effect.effect_id),
            "target": effect.target.model_dump(mode="json"),
        },
        cause_ids=[CauseRef(kind=CauseKind.EFFECT, ref_id=str(effect.effect_id))]
        + list(effect.cause_ids),
        source_system=effect.source,
        provenance=Provenance(producer_id=effect.source, origin=origin),
        cascade=cascade,
    )


def commit_transaction(
    base_state: WorldState,
    accepted_effects: Sequence[ProposedEffect],
    tx_id: TransactionId,
    producer: Provenance,
    *,
    logical_tick: int | None = None,
    cascade: CascadeContext | None = None,
    component_registry: ComponentRegistry | None = None,
    handlers: EffectHandlerRegistry | None = None,
    producer_registry: ProducerRegistry | None = None,
) -> tuple[WorldState, Transaction, list[DomainEvent]]:
    """事务装配与原子提交（§6.2；Spec §20.1 atomic commit 的行为侧）。

    全部确定性、无 IO、无 LLM；线性实现（无重试循环）。

    Args:
        base_state: 提交基线世界状态（base revision）。**任何路径下不被
            触碰**（纯函数原子性的输入侧保证，§6.3）。
        accepted_effects: 本回合被接受的提案批次（到达序）。空批次 →
            ``ValueError``（空事务不消耗 revision，P1 §5.6 不变量 1 的
            行为侧镜像；空回合不 commit 的管道语义，§7.3 步骤 5）。
        tx_id: 事务 ID（WorldInstance 内唯一，调用方经
            ``new_transaction_id()`` 签发）。
        producer: 事务级 Provenance（装配者，入 ``Transaction.
            provenance``）——与各 effect 提案者分层（事务装配者 ≠ 各
            effect 提案者是合法常态，§6.4 注）。
        logical_tick: 透传（D-P2-18：P2 管道不拥有时钟，缺省 None；
            tick 推进归 P3）。
        cascade: 级联上下文透传（可空，入事务与全部事件，Spec §21.3）。
        component_registry: 非 None 时 reducer 对结构组件效果执行
            ``validate_payload``（P1 D-8 校验点 (b)，经
            ``apply_transaction`` 透传）。
        handlers: effect handler 注册表（缺省经 reducer 的
            ``default_handler_registry()``）。
        producer_registry: 事件级 provenance 的 origin 解析输入（§6.4；
            缺省 None → 事件 origin 恒 ``OriginKind.SYSTEM``）。

    Returns:
        成功：``(new_state, txn, events)``——``txn.status`` COMMITTED、
        ``txn.commit_revision == base_state.world_revision + 1``（Spec §9
        恰 +1）、``new_state.world_revision == txn.commit_revision``、
        ``len(events) == len(accepted_effects)``（1:1 发射，D-P2-12）；
        ``new_state`` 与 ``base_state`` 三向零别名。
        失败（L2 终检 / reducer 应用）：``(base_state, aborted, [])``——
        返回**原状态对象**（原样）、``aborted.status`` ABORTED、
        ``commit_revision is None``、``effects == []``、``abort_reason``
        非空（格式见模块 docstring 原子性机制）。

    Raises:
        ValueError: ``accepted_effects`` 为空；或批次含重复 effect_id
            （P1 构造期不变量 KBC-2 在 ``Transaction`` 构造时自动生效——
            §6.2 步骤 5"构造期不变量自动生效"，部分提交在此同样不可达）。
    """
    # 步骤 1：非空守卫（P1 §5.6 不变量 1 的行为侧镜像）
    effects = list(accepted_effects)
    if not effects:
        raise ValueError(
            "commit_transaction 拒绝空 accepted_effects——空事务不产生状态"
            "变化，不应消耗 revision（P1 §5.6 不变量 1 的行为侧镜像，"
            "P2 设计规范 §6.2 步骤 1；空回合不 commit，§7.3 步骤 5）"
        )

    # 步骤 2：base / commit revision（Spec §9：恰 +1）
    base_revision = base_state.world_revision
    commit_revision = base_revision.next()

    # 步骤 3：事件 ID 预分配（数量在此固定；frozen 契约不可回填，
    # 事件本体在步骤 8 组装）
    event_ids: list[EventId] = [new_event_id() for _ in effects]

    # 步骤 4：装配 CommittedEffect（sequence = 下标 = 到达序）
    committed: list[CommittedEffect] = [
        CommittedEffect(
            effect=effect,
            transaction_id=tx_id,
            commit_revision=commit_revision,
            sequence=index,
        )
        for index, effect in enumerate(effects)
    ]

    # 步骤 5：构造 COMMITTED Transaction（P1 构造期不变量自动生效——
    # 重复 effect_id / sequence 断裂等在此即 ValueError，不产生部分提交）
    txn = Transaction(
        transaction_id=tx_id,
        status=TransactionStatus.COMMITTED,
        base_revision=base_revision,
        commit_revision=commit_revision,
        logical_tick=logical_tick,
        effects=committed,
        event_ids=event_ids,
        cascade=cascade,
        provenance=producer,
    )

    # 步骤 6：L2 终检（D-P2-10；C2 晋升的 core 检查器，只报告不处置）
    issues = check_transaction_references(base_state, txn)
    if issues:
        aborted = abort_transaction(
            base_state,
            tx_id,
            reason="reference_check_failed: " + "; ".join(issues),
            producer=producer,
            rejected_effects=effects,
            logical_tick=logical_tick,
            cascade=cascade,
        )
        return base_state, aborted, []

    # 步骤 7：reducer 应用（唯一公共状态变更路径，§2.4）
    try:
        new_state = apply_transaction(
            base_state,
            txn,
            component_registry=component_registry,
            handlers=handlers,
        )
    except ReducerError as err:  # 含 EffectApplicationError（其子类）
        aborted = abort_transaction(
            base_state,
            tx_id,
            reason=_reducer_failure_reason(err),
            producer=producer,
            rejected_effects=effects,
            logical_tick=logical_tick,
            cascade=cascade,
        )
        return base_state, aborted, []

    # 步骤 8：事件发射（D-P2-12 1:1 映射，用步骤 3 预分配的 event_ids）
    events: list[DomainEvent] = [
        _build_domain_event(
            committed_effect,
            event_id,
            tx_id=tx_id,
            commit_revision=commit_revision,
            logical_tick=logical_tick,
            cascade=cascade,
            producer_registry=producer_registry,
        )
        for committed_effect, event_id in zip(committed, event_ids)
    ]
    return new_state, txn, events


def abort_transaction(
    base_state: WorldState,
    tx_id: TransactionId,
    reason: str,
    producer: Provenance,
    *,
    rejected_effects: Sequence[ProposedEffect] = (),
    logical_tick: int | None = None,
    cascade: CascadeContext | None = None,
) -> Transaction:
    """ABORTED 事务构造器（§6.5）：原子失败的数据形态。

    返回 ``base_revision == base_state.world_revision``、``commit_revision
    is None``、``effects == []``、``abort_reason == reason`` 的 ABORTED
    事务（P1 §5.6 不变量 2：部分提交在数据层不可表达）；``base_state``
    原样不动、revision 不递增（Spec §9：只有 COMMITTED 才 +1）。

    Args:
        base_state: 提交基线状态（只读取其 ``world_revision``）。
        tx_id: 被中止事务的 ID（与 :func:`commit_transaction` 同一 ID
            空间，供 trace 关联"谁被原子失败"）。
        reason: 中止原因（``commit_transaction`` 的失败路径按模块
            docstring 的格式约定填充；直接调用方自拟，非空为宜）。
        producer: 事务级 Provenance（装配者，入 ``Transaction.
            provenance``）。
        rejected_effects: 被拒提案批次。**不进事务**（ABORTED ⇒
            ``effects == []``，数据层不可表达，§6.5）——调用方负责将其
            写入 trace（``TraceKind.TRANSACTION`` payload 附加键
            ``rejected_effect_ids: [str]`` + ``PAYLOAD_RECORD_KEY`` 内嵌
            事务记录，§9 汇总表），供审计"atomic failure"。
        logical_tick: 透传（D-P2-18，缺省 None）。
        cascade: 级联上下文透传（可空）。

    Returns:
        ABORTED :class:`Transaction`（纯数据构造，不触碰 ``base_state``，
        无事件发射——中止无状态变化，无事件可言）。
    """
    return Transaction(
        transaction_id=tx_id,
        status=TransactionStatus.ABORTED,
        base_revision=base_state.world_revision,
        commit_revision=None,
        logical_tick=logical_tick,
        effects=[],
        event_ids=[],
        cascade=cascade,
        provenance=producer,
        abort_reason=reason,
    )
