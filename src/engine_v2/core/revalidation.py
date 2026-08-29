"""engine_v2 core 层通用 stale 提案 revalidation 与 REBASE 纯变换（P3-T07）。

依据 ``docs/v2/contracts/P3-scheduler-time-action-design.md``（下称"设计文档"）
§3.9（全量）：

- **单一实现（G2 移交 3）**：:func:`revalidate_proposal` 对任意 producer
  （NPC/LLM/玩家）行为一致——判定只依赖 ``(WorldState, ActionProposal,
  current, allow_rebase, actor_alive_check)``，不读取 ``provenance`` 语义
  （provenance 仅在构造期已由 P1 词法校验）；
- **判定结果 = 数据，不是异常**：:class:`RevalidationDecision`（继承 P1
  :class:`~src.engine_v2.core.entity.ContractModel`）承载 outcome（复用 P1
  :class:`~src.engine_v2.core.revision.RevalidationOutcome` 四值冻结词表）/
  reason / details / at_revision / rebased_proposal；REJECT/REBASE 路径
  不抛异常；
- **5 步顺序（§3.9）**：1) ``is_stale``（复用 ``revision.py:78``，import 不
  重定义）为真 → ``allow_rebase`` 且 actor 存活 → REBASE（
  ``rebased_proposal = rebase_proposal(proposal, current)``）；否则 REJECT——
  REJECT 原因优先级钉死（F2-05，过期优先）：``valid_until`` 非 None 且
  ``current > valid_until`` → ``valid_until_expired``；否则 →
  ``stale_revision``（两条件同时满足时不随实现顺序漂移）；2) actor 存在性
  （``state.has_entity``）否 → REJECT ``actor_missing``；3)
  ``actor_alive_check``（P5/P4 钩子；缺省恒真）假 → REJECT
  ``actor_not_alive``；4) ``actor_state_revision`` 非空且 is_stale → 仅
  details 诊断（D-12 口径：记录"读取时"revision，不作 REJECT 依据）；
  ``observation_id`` 仅词法在 P1 构造期已校验，P3 记录 details（内容级
  一致性检查属 P4 观察管线，扩展位）；5) 全过 → ACCEPT；
- **REBASE 纯变换**：:func:`rebase_proposal` 把 ``base_world_revision``
  推进到 ``current``（rebuild 模式：``model_copy(update=...)``，其余字段
  逐字保持，不 mutate 原实例）；调用方（``submit_proposal``）决定何时允许
  REBASE（默认关闭）；
- **REPAIR 范围声明（R4/E-P3-26）**：``RevalidationOutcome.REPAIR`` 不产生
  于 P3 同步 tick 循环 revalidation（见 :func:`revalidate_proposal`
  docstring 末尾声明）。

依赖面（§3.2 依赖图，箭头单向无环）：P1 ``revision``（``is_stale`` 口径
单源）/ ``state``（``has_entity``）/ ``actions`` / ``ids`` / ``entity``
（``ContractModel`` 基类）+ P2 ``reducer``（``GuardedWorldState`` 视图类型
与 ``guard()``——P2 模块不 import 任何 P3 模块，无环）。P3 专项 import
黑名单（``datetime``/``time``/``random``/``asyncio``）对本模块生效：
零墙钟、零隐式随机、零协程（§3.2/§8.3）。
"""

from __future__ import annotations

from collections.abc import Callable

from pydantic import model_validator

from src.engine_v2.core.actions import ActionProposal
from src.engine_v2.core.entity import ContractModel
from src.engine_v2.core.ids import ActionInstanceId, EntityId
from src.engine_v2.core.reducer import GuardedWorldState, guard
from src.engine_v2.core.revision import RevalidationOutcome, Revision, is_stale
from src.engine_v2.core.state import WorldState

__all__ = [
    "RevalidationDecision",
    "revalidate_proposal",
    "rebase_proposal",
]


class RevalidationDecision(ContractModel):
    """stale 提案 revalidation 判定结果（设计文档 §3.9；判定结果 = 数据）。

    字段逐项（§3.9 代码块）：

    - ``proposal_id``：被判定提案的实例 ID（= ``ActionProposal.proposal_id``，
      决策 D-3 贯穿 ID）；
    - ``outcome``：复用 P1 四值冻结词表 ``RevalidationOutcome``
      （``revision.py:91-101``；P1 只落数据词表，判定行为属本模块）；
    - ``reason``：判定原因字符串（``"accept"`` / ``"stale_revision"`` /
      ``"valid_until_expired"`` / ``"actor_missing"`` / ``"actor_not_alive"``
      / ``"rebased"`` / …——开放词表，新增原因不破坏契约）；
    - ``details``：诊断串（确定性纯文本；REJECT 的 revision 类原因携带两
      revision 值，§6.1 口径；ACCEPT 路径可含 D-12/observation 诊断）；
    - ``at_revision``：判定时刻的世界 revision（= 解析后的 ``current``）；
    - ``rebased_proposal``：仅 ``outcome == REBASE`` 时非空（REBASE 纯变换
      产物；构造期不变量强制）。

    构造期不变量（K7 可检查不静默）：``outcome == REBASE`` ⇔
    ``rebased_proposal is not None``——与 §3.9 字段注记逐字一致，违反即
    构造失败。
    """

    proposal_id: ActionInstanceId
    outcome: RevalidationOutcome
    reason: str
    details: tuple[str, ...] = ()
    at_revision: Revision
    rebased_proposal: ActionProposal | None = None

    @model_validator(mode="after")
    def _check_rebase_invariant(self) -> "RevalidationDecision":
        """``outcome == REBASE`` 与 ``rebased_proposal`` 非空互为充要（§3.9）。"""
        if (self.outcome is RevalidationOutcome.REBASE) != (
            self.rebased_proposal is not None
        ):
            raise ValueError(
                "rebased_proposal 必须恰在 outcome==REBASE 时非空"
                f"（outcome={self.outcome.value!r}，"
                f"rebased_proposal={'non-None' if self.rebased_proposal is not None else 'None'}）"
            )
        return self


def revalidate_proposal(
    state: WorldState,
    proposal: ActionProposal,
    *,
    current: Revision | None = None,
    allow_rebase: bool = False,
    actor_alive_check: Callable[[GuardedWorldState, EntityId], bool] | None = None,
) -> RevalidationDecision:
    """通用 stale 提案 revalidation（**任意 producer 单一实现**，G2 移交 3）。

    5 步顺序（设计文档 §3.9，步骤间严格次序；判定结果 = 数据，REJECT/
    REBASE 均不抛异常）：

    1. ``is_stale(proposal.base_world_revision, current, proposal.valid_until)``
       （复用 ``revision.py:78`` 口径：``base < current`` 或
       ``current > valid_until``（``valid_until`` 非 None 时）即陈旧，
       ``current == valid_until`` 不陈旧）为真 →
       ``allow_rebase`` 且 actor 存活（存在且 ``actor_alive_check`` 非假）
       → REBASE（``rebased_proposal = rebase_proposal(proposal, current)``）；
       否则 REJECT——**REJECT 原因优先级钉死（F2-05，过期优先）**：若
       ``valid_until`` 非 None 且 ``current > valid_until`` →
       ``valid_until_expired``；否则 → ``stale_revision``（两条件同时满足
       时不随实现顺序漂移，§6.3 A1 变体口径）；
    2. actor 存在性：``state.has_entity(proposal.actor_id)`` 否 → REJECT
       ``actor_missing``；
    3. ``actor_alive_check``（P5/P4 钩子，如昏迷判定；缺省恒真）假 →
       REJECT ``actor_not_alive``——视图 ``view = guard(state)`` 构造一次
       复用（P2 深冻结只读门面，不暴露可写权威状态）；
    4. 诊断（仅 ACCEPT 路径落 details，不作 REJECT 依据）：
       ``actor_state_revision`` 非空且 is_stale → 仅 details 诊断（D-12
       口径：记录"读取时"revision，不作 REJECT 依据）；``observation_id``
       仅词法在 P1 构造期已校验，P3 记录 details（内容级一致性检查属 P4
       观察管线，扩展位）；
    5. 全过 → ACCEPT。

    参数：

    - ``state``：判定时刻的权威世界状态（只读消费，不 mutate）；
    - ``proposal``：被判定提案（只读消费，不 mutate）；
    - ``current``：判定参照 revision，缺省 ``state.world_revision``；
    - ``allow_rebase``：是否允许 REBASE 出典（缺省 False——调用方
      ``submit_proposal`` 决定何时允许，§3.9 ``rebase_proposal`` 注记）；
    - ``actor_alive_check``：actor 存活钩子（P5/P4 注册，如昏迷判定），
      入参为 ``guard(state)`` 只读视图与 actor ID，返回 False 判
      ``actor_not_alive``；缺省恒真。

    返回：:class:`RevalidationDecision`（``at_revision`` = 解析后的
    ``current``）。

    **REPAIR 范围声明（R4/E-P3-26）**：``RevalidationOutcome.REPAIR``
    （``revision.py:91-101`` 四值冻结词表之一）**不产生于 P3 同步 tick 循环
    revalidation**——REPAIR 属 Spec §9 异步结果 revalidation 语境（P4 携带
    base_world_revision/observation_id/actor_state_revision/valid_until 的
    异步结果路径）；**P3 ``revalidate_proposal`` 结果域 = {ACCEPT, REBASE,
    REJECT}**，P4 异步路径保留 REPAIR 产出能力（词表已冻结，P3 不扩展
    不缩减）。
    """
    if current is None:
        current = state.world_revision
    view = guard(state)  # 构造一次复用（§3.9 步骤 3 口径）

    actor_present = state.has_entity(proposal.actor_id)
    actor_alive = actor_present
    if actor_alive and actor_alive_check is not None:
        actor_alive = actor_alive_check(view, proposal.actor_id)

    # —— 步骤 1：世界 revision 陈旧性（is_stale 单源，revision.py:78）——
    if is_stale(proposal.base_world_revision, current, proposal.valid_until):
        if allow_rebase and actor_alive:
            return RevalidationDecision(
                proposal_id=proposal.proposal_id,
                outcome=RevalidationOutcome.REBASE,
                reason="rebased",
                details=(
                    f"rebased: base_world_revision {int(proposal.base_world_revision)}"
                    f" -> current {int(current)}",
                ),
                at_revision=current,
                rebased_proposal=rebase_proposal(proposal, current),
            )
        # REJECT 原因优先级钉死（F2-05，过期优先）：两条件同时满足时
        # 不随实现顺序漂移（§6.3 A1 变体口径）。
        if proposal.valid_until is not None and current > proposal.valid_until:
            return RevalidationDecision(
                proposal_id=proposal.proposal_id,
                outcome=RevalidationOutcome.REJECT,
                reason="valid_until_expired",
                details=(
                    f"valid_until_expired: valid_until {int(proposal.valid_until)}"
                    f" < current {int(current)}",
                ),
                at_revision=current,
            )
        return RevalidationDecision(
            proposal_id=proposal.proposal_id,
            outcome=RevalidationOutcome.REJECT,
            reason="stale_revision",
            details=(
                f"stale_revision: base_world_revision {int(proposal.base_world_revision)}"
                f" < current {int(current)}",
            ),
            at_revision=current,
        )

    # —— 步骤 2：actor 存在性 ——
    if not actor_present:
        return RevalidationDecision(
            proposal_id=proposal.proposal_id,
            outcome=RevalidationOutcome.REJECT,
            reason="actor_missing",
            details=(f"actor_missing: actor {str(proposal.actor_id)} not in world",),
            at_revision=current,
        )

    # —— 步骤 3：actor 存活（P5/P4 钩子；缺省恒真）——
    if not actor_alive:
        return RevalidationDecision(
            proposal_id=proposal.proposal_id,
            outcome=RevalidationOutcome.REJECT,
            reason="actor_not_alive",
            details=(
                f"actor_not_alive: actor {str(proposal.actor_id)}"
                " reported not alive by actor_alive_check",
            ),
            at_revision=current,
        )

    # —— 步骤 4：ACCEPT 路径诊断（均不作 REJECT 依据）——
    details: list[str] = []
    if proposal.actor_state_revision is not None and is_stale(
        proposal.actor_state_revision, current
    ):
        # D-12 口径：记录"读取时"revision，仅诊断，不作 REJECT 依据。
        details.append(
            f"actor_state_revision_stale: {int(proposal.actor_state_revision)}"
            f" < current {int(current)} (D-12: diagnostic only, not a REJECT basis)"
        )
    if proposal.observation_id is not None:
        # 词法 P1 构造期已校验；内容级一致性检查属 P4 观察管线（扩展位）。
        details.append(
            f"observation_id: {str(proposal.observation_id)} recorded"
            " (content-level consistency check is the P4 observation pipeline extension point)"
        )

    # —— 步骤 5：全过 → ACCEPT ——
    return RevalidationDecision(
        proposal_id=proposal.proposal_id,
        outcome=RevalidationOutcome.ACCEPT,
        reason="accept",
        details=tuple(details),
        at_revision=current,
    )


def rebase_proposal(proposal: ActionProposal, current: Revision) -> ActionProposal:
    """REBASE 纯变换：``base_world_revision`` → ``current``（rebuild 模式）。

    其余字段逐字保持；经 ``model_copy(update=...)`` 产出新实例——不 mutate
    原提案（ContractModel 浅冻结 + 嵌套不可变的语义保证下，未更新字段
    与原实例共享同一不可变对象，即"逐字保持"）。

    调用方（``submit_proposal``）决定何时允许 REBASE（默认关闭）；本函数
    本身无条件执行变换（``base == current`` 时产出字段值相同的新实例，
    纯函数语义不依赖输入）。
    """
    return proposal.model_copy(update={"base_world_revision": current})
