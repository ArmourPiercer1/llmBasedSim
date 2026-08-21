"""engine_v2 core 层 Event Cascade 级联执行器（P2 设计规范 §1/§7；
P2-T07/P2-T08 实现载体）。

**职责**（P2 设计规范 §1.2 / §7；Spec §21.3）：K2 管道末段的
**级联回合循环**——串联 AuthorityPolicy → EffectValidator →
ConflictResolver → TransactionExecutor → Reducer → Triggers →
Cascade Loop（§1.1 数据流），承载级联五要素的运行时侧：

- ``cascade_id`` / ``causal_root_id`` / ``depth``：经 P1 数据契约
  :class:`~src.engine_v2.core.provenance.CascadeContext` 随 Transaction /
  DomainEvent 传播（§5.0/§5.7；数据契约侧由 P1 落位，本模块是**签发与
  递增**的运行时——根事务 ``depth=0``，由 depth=d 事务事件触发的提案在
  ``depth=d+1`` 提交，D-P2-13）；
- ``max cascade depth``（:class:`CascadeConfig`，默认
  :data:`DEFAULT_MAX_CASCADE_DEPTH` = 8）与 **cycle diagnostics**
  （:class:`CycleDetector` / :class:`CascadeDiagnostic`，D-P2-14）——
  P1 明示二者是执行器运行时配置与诊断输出，不是数据字段。

**触发器（§7.2；任务包 P2-T07 表面）**：

- :class:`CascadeTrigger`（Protocol）——``trigger_id`` + 同步
  ``evaluate(events, state, depth) -> 新提案``；求值入参的 state 是
  :class:`~src.engine_v2.core.reducer.GuardedWorldState` 只读门面
  （§2.6.3：触发器物理上拿不到写路径，K2 运行时兜底）；
- :class:`SyncTrigger`（任务包表面"监听 DomainEvent 并同步产生新的
  ProposedEffect 提议"的具名实现）——纯函数回调载体，构造期词法/类型
  守卫，evaluate 强制只读门面；
- :class:`CascadeTriggerRegistry`（别名 :data:`TriggerRegistry`）——
  按注册序逐触发器求值串联（确定性）；同名重复注册同实例幂等、异实例
  → :class:`TriggerConflictError`（与 ProducerRegistry /
  EffectHandlerRegistry 同款纪律）。

**触发输出因果闭合检查（K6，§7.2 末段）**：执行器对触发器产出的每个
提案校验——其 ``cause_ids`` 必须含 ≥1 个 ``CauseKind.EVENT`` 且
``ref_id`` ∈ 本回合事件 ID 集；不满足的提案被丢弃 + SYSTEM 诊断
（``trigger_output_dropped``）。级联链由此保证可完整重建（P1 errata C1
口径：级联串联由 cause_ids 承载）。

**深度熔断（§7.1/§7.3，D-P2-13）**：根提案在 ``depth=0`` 提交；
``depth > max_cascade_depth`` 的回合**不启动**，记 SYSTEM 诊断
（``cascade_depth_exceeded``）后收敛退出（缺省语义，P2-T09 类别 5 的
"至多 9 个 COMMITTED"断言基础）。任务包 P2-T07/T08 表面：
``CascadeConfig(strict=True)`` 时同一熔断点改为抛出
:class:`CascadeDepthExceededError`（严格熔断异常，携带
depth / max_cascade_depth / cascade_id）。

**环路检测（§7.5，D-P2-14；任务包 P2-T08 表面）**：

- 环路口径 = 触发链上的**冲突位置重访**：某触发提案的目标锁位置
  （:func:`extract_effect_locks`，ConflictKey 访问路径）已出现在本
  cascade 链祖先回合的已提交位置集中（HP变化→规则→又改HP 即此形态）。
  重访判定取**键精确成员**（spec 原文 "锁 ∈ 祖先位置集"）；
- :class:`CycleDetector` 逐回合装配前对 accepted effects 逐个
  ``check``：命中即**丢弃**该提案（过滤语义，不触发整事务失败）+
  SYSTEM 诊断（``cycle_detected``，detail 重建 "深度/位置" 链）+
  :class:`CascadeDiagnostic`；本回合 accepted 全部被环路丢弃 → 回合
  空转、级联收敛（缺省语义，P2-T09 类别 5 的"级联正常收敛（无异常）"
  断言基础）。``CascadeConfig(strict=True)`` 时同一熔断点改为抛出
  :class:`CascadeCycleError`（携带 hit：ancestor_depth + 重访位置）；
- ``location_revisit="allow"`` 使检测器退化为恒 None（仅深度上限，
  §7.1）；
- 提交位置登记：每个 COMMITTED 事务经
  ``observe_commit(depth, 本回合全部已提交锁)`` 入集（ABORTED 不登记——
  未提交无位置可言）。

**执行器（§7.3）**：

- :class:`CascadeExecutor.__init__` 调用 :func:`install_write_barrier`
  武装写屏障（kernel 运行时入口，幂等；§2.6.2——不 import 自动安装，
  由本入口与测试夹具控制）；
- ``run(initial_proposals, state, *, causal_root_id, origin)`` 主循环
  （回合结构，§7.3 伪代码的逐行落位）::

      cascade_id = new_cascade_id(); depth = 0; pending = initial
      while pending 非空:
          if depth > config.max_cascade_depth:
              SYSTEM 诊断(cascade_depth_exceeded)；strict → 抛异常；break
          run_round(state, pending, depth, CascadeContext(..., depth))
              ├─ 1. trace 每个提案（PROPOSED_EFFECT）
              ├─ 2. authority（deny → 丢弃 + AUTHORITY_DECISION trace）
              ├─ 3. validation L1（fail → 丢弃 + VALIDATION_DECISION trace）
              ├─ 4. conflicts（detect_conflicts + 域解析器钩子 + 默认四策；
              │      逐组 CONFLICT_RESOLUTION trace；DEFER → 下回合再入队）
              ├─ 5. CycleDetector 逐个 check（命中 → 丢弃 + 诊断/异常）
              └─ 6. 空 → 回合空转不 commit；否则 commit_transaction
                     （TRANSACTION trace 含 ABORTED + 每事件 DOMAIN_EVENT trace）
          txn ABORTED → 级联停止（无事件可触发；审计经 ABORTED 事务
              trace，§6.3）
          pending = 触发器输出（因果闭合过滤）+ 本回合 DEFER 再入队者
          depth += 1

- 产出 :class:`CascadeResult`（别名 :data:`CascadeExecutionResult`）：
  最终 WorldState、全部事务（含 ABORTED——审计原子失败）、全部事件、
  全部 TraceRecord（§9 汇总表 payload 约定）、DEFER 再入队残留、诊断
  列表；``cascade_statistics`` 计算属性提供级联统计（任务包表面）。

**因果树重建（§7.6，K6 验收）**：任一 CascadeResult 满足——全部事件
携带同一 cascade_id 与 causal_root_id、depth 与所在事务一致；
cause_ids 链 effect↔event 交替衔接至根（由触发输出因果闭合检查 +
§6.4 事件发射映射机械保证）。

**Trace 坐标约定（§9 末段）**：全部 TraceRecord 填充
``world_revision`` = 记录时 state 的 revision、``logical_tick=None``
（P2 无时钟，D-P2-18）、``cascade_id``、相关 ``transaction_id`` /
``producer_id``。

Import 边界（P1 设计 §0.3 继承）：只允许 stdlib + pydantic + 同包
``src.engine_v2``；本模块不出现 ``model_copy(update=...)`` /
``model_construct``（写屏障静态审计口径，§2.6.1）。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Final, Protocol, runtime_checkable

from src.engine_v2.core.authority import (
    AuthorityDecision,
    AuthorityEvaluationResult,
    AuthorityPolicy,
    ProducerRegistry,
    check_authority,
)
from src.engine_v2.core.components import ComponentRegistry
from src.engine_v2.core.conflicts import (
    ConflictAction,
    ConflictGroup,
    ConflictKey,
    ConflictResolution,
    ConflictResolutionReport,
    DefaultConflictResolver,
    DomainResolverFactory,
    ResolutionContext,
    detect_conflicts,
    extract_effect_locks,
)
from src.engine_v2.core.effects import ProposedEffect
from src.engine_v2.core.events import DomainEvent
from src.engine_v2.core.ids import (
    CascadeId,
    EffectId,
    new_cascade_id,
    new_trace_record_id,
    new_transaction_id,
)
from src.engine_v2.core.provenance import CascadeContext, CauseKind, Provenance
from src.engine_v2.core.revision import Revision
from src.engine_v2.core.reducer import (
    EffectHandlerRegistry,
    GuardedWorldState,
    default_handler_registry,
    guard,
    install_write_barrier,
    is_guarded,
)
from src.engine_v2.core.state import WorldState
from src.engine_v2.core.trace import PAYLOAD_RECORD_KEY, TraceKind, TraceRecord
from src.engine_v2.core.transaction import Transaction, TransactionStatus
from src.engine_v2.core.transaction_executor import commit_transaction
from src.engine_v2.core.validation import EffectValidator, ValidationContext

__all__ = [
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
]


# —— 配置与诊断（§7.1/§7.4；D-P2-13/D-P2-14）——


#: 默认最大级联深度（§7.1；任务包口径：默认 8）。深度语义（精确口径，
#: D-P2-13）：根提案在 ``depth=0`` 提交；由 depth=d 事务的事件触发的提案
#: 在 ``depth=d+1`` 提交；``depth > max_cascade_depth`` 的回合**不启动**。
#: 默认配置下至多 9 个 COMMITTED 事务（depth 0..8）、revision 至多 +9。
DEFAULT_MAX_CASCADE_DEPTH: Final[int] = 8

#: location_revisit 配置词表（§7.1）：``forbid``（环路熔断，D-P2-14）/
#: ``allow``（退化为仅深度上限）。
_LOCATION_REVISIT_MODES: Final[frozenset[str]] = frozenset({"forbid", "allow"})

#: 诊断 kind 冻结词表（§7.4；对应 SYSTEM trace payload 约定
#: ``{"diagnostic": <kind>, "cascade_id": str, "depth": int, "detail": str}``）。
CASCADE_DIAGNOSTIC_KINDS: Final[frozenset[str]] = frozenset(
    {"cascade_depth_exceeded", "cycle_detected", "trigger_output_dropped"}
)


class CascadeError(ValueError):
    """级联执行器异常基类（P2-T07/T08 任务包表面；``ValueError`` 族）。

    与 P2 各行为模块错误族统一（``AuthorityError`` / ``ConflictError`` /
    ``ReducerError`` 同款纪律，派生 ``ValueError``，调用方可按 ``ValueError``
    一类捕获）。角色：

    - **输入契约守卫**——配置非法（:class:`CascadeConfig` 词表/值域）、
      触发器协议不符（无 ``trigger_id`` / ``evaluate``）、注册冲突
      （:class:`TriggerConflictError`）、执行器构造/调用入参类型错误；
    - **严格熔断**——``CascadeConfig(strict=True)`` 下深度超限 / 环路命中
      的熔断异常（:class:`CascadeDepthExceededError` /
      :class:`CascadeCycleError`）。

    缺省（非 strict）语义下管道**不抛本族异常**：深度超限记诊断后收敛、
    环路命中丢弃提案后收敛（P2 设计规范 §7.3 主循环 / §7.5 过滤语义 /
    §11 类别 5"级联正常收敛（无异常）"口径）。
    """


class TriggerConflictError(CascadeError):
    """触发器注册冲突（§7.2"同名重复注册幂等/冲突"的冲突分支）。

    同一 ``trigger_id`` 已注册**不同实例**时抛出（同实例重复注册幂等，
    与 ``ProducerRegistry`` / ``EffectHandlerRegistry`` 同款纪律）。
    """


class CascadeDepthExceededError(CascadeError):
    """深度熔断异常（任务包 P2-T07/T08 表面；``CascadeConfig.strict=True``）。

    缺省语义下 ``depth > max_cascade_depth`` 的回合不启动、记 SYSTEM 诊断
    后收敛（§7.3 主循环）；strict 模式下同一熔断点抛出本异常。

    属性（机可解析）：

    - ``depth``：尝试启动而被熔断的回合深度（= max_cascade_depth + 1，
      默认配置下 = 9）；
    - ``max_cascade_depth``：生效的最大触发深度；
    - ``cascade_id``：所属级联 ID（字符串形态）。
    """

    def __init__(self, *, depth: int, max_cascade_depth: int, cascade_id: str) -> None:
        self.depth = depth
        self.max_cascade_depth = max_cascade_depth
        self.cascade_id = cascade_id
        super().__init__(
            f"级联深度熔断：depth={depth} 超过最大触发深度 "
            f"max_cascade_depth={max_cascade_depth}（cascade_id={cascade_id}；"
            "P2 设计规范 §7.1/D-P2-13）"
        )


class CascadeCycleError(CascadeError):
    """环路熔断异常（任务包 P2-T08 表面；``strict=True`` 且
    ``location_revisit='forbid'``）。

    缺省语义下冲突位置重访（HP变化→规则→又改HP，D-P2-14）丢弃该提案、
    记诊断后收敛（§7.5 过滤语义）；strict 模式下同一熔断点抛出本异常。

    属性（机可解析）：

    - ``depth``：触发检查的回合深度；
    - ``cascade_id``：所属级联 ID（字符串形态）；
    - ``hit``：命中的 :class:`CycleHit`（``ancestor_depth`` = 被重访位置
      首次提交的深度、``key`` = 重访的冲突位置）；
    - ``detail``：人可读 + 机可解析的结构化链串（与诊断 detail 同形）。
    """

    def __init__(self, *, depth: int, cascade_id: str, hit: "CycleHit", detail: str) -> None:
        self.depth = depth
        self.cascade_id = cascade_id
        self.hit = hit
        self.detail = detail
        super().__init__(
            f"级联环路熔断：[depth{depth}] 重访 [depth{hit.ancestor_depth}] "
            f"已提交位置 {hit.key.render()}（cascade_id={cascade_id}；"
            "P2 设计规范 §7.5/D-P2-14）"
        )


@dataclass(frozen=True)
class CascadeConfig:
    """级联运行时配置（§7.1，D-P2-13/D-P2-14；frozen，构造期守卫）。

    - ``max_cascade_depth``：允许的最大触发深度（depth 0..8 至多 9 个
      事务；非负 int，bool 显式排除）；
    - ``location_revisit``：``forbid``（环路熔断，缺省）/ ``allow``（仅
      深度上限，检测器退化为恒 None，§7.5）；
    - ``strict``（任务包 P2-T07/T08 表面扩展，缺省 False）：False =
      设计规范缺省语义——深度超限 / 环路命中记 SYSTEM 诊断后收敛，
      ``run`` 恒返回 :class:`CascadeResult`（§11 类别 5 口径）；True =
      严格熔断——同一熔断点改为抛出
      :class:`CascadeDepthExceededError` / :class:`CascadeCycleError`。
      触发输出因果闭合丢弃（``trigger_output_dropped``）在两种模式下
      均为诊断记录（非熔断事件，§7.4 词表定位）。
    """

    max_cascade_depth: int = DEFAULT_MAX_CASCADE_DEPTH
    location_revisit: str = "forbid"
    strict: bool = False

    def __post_init__(self) -> None:
        if isinstance(self.max_cascade_depth, bool) or not isinstance(self.max_cascade_depth, int):
            raise CascadeError(
                "CascadeConfig.max_cascade_depth 必须为非负 int，得到 "
                f"{type(self.max_cascade_depth).__name__}（bool 显式排除）"
            )
        if self.max_cascade_depth < 0:
            raise CascadeError(
                f"CascadeConfig.max_cascade_depth 必须 >= 0，得到 {self.max_cascade_depth}"
            )
        if self.location_revisit not in _LOCATION_REVISIT_MODES:
            raise CascadeError(
                f"CascadeConfig.location_revisit 必须是 "
                f"{sorted(_LOCATION_REVISIT_MODES)} 之一，得到 {self.location_revisit!r}"
            )
        if not isinstance(self.strict, bool):
            raise CascadeError(
                f"CascadeConfig.strict 必须为 bool，得到 {type(self.strict).__name__}"
            )


@dataclass(frozen=True)
class CascadeDiagnostic:
    """级联诊断载体（§7.4；P2-T07 交付一半、P2-T08 补全）。

    - ``kind``：:data:`CASCADE_DIAGNOSTIC_KINDS` 词表；
    - ``depth``：诊断发生的回合深度（深度熔断 = 被拒回合深度，环路/触发
      丢弃 = 检查所在回合深度）；
    - ``detail``：人可读 + 机可解析的结构化串（环路诊断重建 "深度/位置"
      链，§7.5 示例口径）。

    对应 SYSTEM trace payload 约定（冻结键名，§7.4 末行）：
    ``{"diagnostic": <kind>, "cascade_id": str, "depth": int, "detail": str}``。
    """

    kind: str
    depth: int
    detail: str

    def __post_init__(self) -> None:
        if self.kind not in CASCADE_DIAGNOSTIC_KINDS:
            raise CascadeError(
                f"CascadeDiagnostic.kind 必须是 {sorted(CASCADE_DIAGNOSTIC_KINDS)} 之一，"
                f"得到 {self.kind!r}"
            )
        if isinstance(self.depth, bool) or not isinstance(self.depth, int):
            raise CascadeError(
                f"CascadeDiagnostic.depth 必须为 int，得到 {type(self.depth).__name__}"
            )
        if not isinstance(self.detail, str) or self.detail == "":
            raise CascadeError("CascadeDiagnostic.detail 必须为非空字符串")


# —— 环路检测（§7.5；P2-T08；D-P2-14）——


@dataclass(frozen=True)
class CycleHit:
    """环路命中（§7.5）：某提案锁位置重访了祖先回合已提交位置。

    - ``ancestor_depth``：被重访位置**首次**提交的深度；
    - ``key``：重访的冲突位置（:class:`ConflictKey`；
      :meth:`~ConflictKey.render` 提供链串形态）。
    """

    ancestor_depth: int
    key: ConflictKey


class CycleDetector:
    """冲突位置重访检测器（§7.5，D-P2-14；任务包 P2-T08 表面）。

    **环路口径**（spec 原文）：触发链上的**冲突位置重访**——某触发提案的
    目标锁位置（ConflictKey 访问路径，:func:`extract_effect_locks`）已
    出现在本 cascade 链祖先回合的已提交位置集中。重访判定取**键精确
    成员**（"锁 ∈ 祖先位置集"，ConflictKey frozen 全等语义）；域锁的
    粗粒度（同域任意两写互撞）是 ConflictKey 既有粒度口径（§5.1
    "域级粗粒度，保守"），本检测器不另行细化。

    用法（执行器接线，§7.5"接线位置"）：

    1. 每个 COMMITTED 事务后 ``observe_commit(depth, 本回合全部已提交
       锁)`` 登记位置（同位置重复登记保留**首次**深度——
       ``ancestor_depth`` 语义）；ABORTED 不登记；
    2. 下一回合装配前对 accepted 提案逐个 ``check``：命中 →
       :class:`CycleHit`（调用方按过滤语义丢弃 + 诊断/异常，§7.5）。

    ``mode='allow'`` 时 :meth:`check` 恒返回 None（退化为仅深度上限，
    §7.1）；``observe_commit`` 仍登记（模式切换不改历史）。

    本检测器是**级联链作用域**状态：执行器缺省按每次 ``run()`` 新建
    （跨级联不串位）；注入实例跨 run 复用由调用方负责生命周期（§7.5
    T07 注入钩子）。
    """

    __slots__ = ("mode", "_positions")

    def __init__(self, mode: str = "forbid") -> None:
        """以配置模式构造（``mode`` = ``CascadeConfig.location_revisit``）。

        Raises:
            CascadeError: ``mode`` 不在 ``forbid`` / ``allow`` 词表。
        """
        if mode not in _LOCATION_REVISIT_MODES:
            raise CascadeError(
                f"CycleDetector.mode 必须是 {sorted(_LOCATION_REVISIT_MODES)} 之一，"
                f"得到 {mode!r}"
            )
        self.mode = mode
        # 已提交位置集：ConflictKey → 首次提交深度（祖先链登记，§7.5）
        self._positions: dict[ConflictKey, int] = {}

    def observe_commit(self, depth: int, locations: frozenset[ConflictKey]) -> None:
        """登记一个已提交回合的锁位置集（§7.5；仅 COMMITTED 调用）。

        Args:
            depth: 该事务的级联深度（CascadeContext.depth）。
            locations: 本回合全部已提交 effect 的锁集合（执行器以
                ``frozenset().union(*[extract_effect_locks(e) for e in
                committed])`` 构造）。

        同位置重复登记保留**最小**深度（= 正常顺序下首次提交深度；对乱序
        登记亦给出 "首次提交" 语义，防御性加固）。
        """
        for key in locations:
            current = self._positions.get(key)
            if current is None or depth < current:
                self._positions[key] = depth

    def check(self, effect: ProposedEffect) -> CycleHit | None:
        """环路检查（§7.5）：effect 任一锁 ∈ 祖先深度已提交位置并集 → 命中。

        确定性：多锁命中时按 ``ConflictKey.render`` 序报告**首个**命中。
        ``mode='allow'`` → 恒 None（退化为仅深度上限）。

        Args:
            effect: 装配前的 accepted 提案（输入契约守卫：非
                ``ProposedEffect`` → :class:`CascadeError`）。

        Returns:
            :class:`CycleHit`（命中）或 None（无重访 / allow 模式）。
        """
        if self.mode != "forbid":
            return None
        if not isinstance(effect, ProposedEffect):
            raise CascadeError(
                f"CycleDetector.check 需要 ProposedEffect，得到 {type(effect).__name__}"
            )
        for key in sorted(extract_effect_locks(effect), key=lambda candidate: candidate.render()):
            if key in self._positions:
                return CycleHit(ancestor_depth=self._positions[key], key=key)
        return None


# —— 触发器协议与注册表（§7.2；任务包 P2-T07 表面）——


#: SyncTrigger 的求值回调签名（私有类型别名；协议侧以
#: :class:`CascadeTrigger` 为契约）。纯函数：无 IO、无 LLM、无写路径
#: （state 为只读门面，§2.6.3）。
_TriggerEvaluateFn = Callable[
    [Sequence[DomainEvent], GuardedWorldState, int], Sequence[ProposedEffect]
]


@runtime_checkable
class CascadeTrigger(Protocol):
    """级联触发器协议（§7.2；结构化子类型）。

    - ``trigger_id``：诊断名（如 ``"rule.on_hp_changed"``）；
    - ``evaluate``：同步求值（Spec §21.3 "evaluate synchronous triggers"）。
      **纯函数**：同一 ``(events, state, depth)`` 恒产出同一提案序列；
      入参 ``state`` 为 :class:`GuardedWorldState`（§2.6.3——触发器物理上
      拿不到写路径，K2）；
    - 产出提案的 ``cause_ids`` 必须回指本回合事件（≥1 个
      ``CauseKind.EVENT`` 且 ``ref_id`` ∈ 本回合事件 ID 集）——不满足者
      被执行器因果闭合检查丢弃（§7.2 末段，K6）。

    ``@runtime_checkable``：``isinstance`` 仅检查协议**属性存在性**
    （``trigger_id`` / ``evaluate``），不做类型验证——执行器侧注册守卫
    （:meth:`CascadeTriggerRegistry.register`）承担更强的契约检查
    （``trigger_id`` 非空字符串、``evaluate`` 可调用）。
    """

    trigger_id: str

    def evaluate(
        self,
        events: Sequence[DomainEvent],
        state: GuardedWorldState,
        depth: int,
    ) -> Sequence[ProposedEffect]:
        """对本回合事件同步求值，返回新提案序列（空序列 = 无反应）。"""
        ...


class SyncTrigger:
    """同步级联触发器（任务包 P2-T07 表面：监听 DomainEvent 并同步产生
    新的 ProposedEffect 提议；:class:`CascadeTrigger` 协议的具名实现）。

    - ``trigger_id``：诊断名（非空字符串，构造期守卫）；
    - ``evaluate_fn``：纯函数回调 ``(events, state, depth) -> 新提案``
      （无 IO / 无 LLM；state 为只读门面，拿到写路径即违反 K2 纪律）；
    - :meth:`evaluate` 委托回调并强制入参契约：``state`` 必须是
      :class:`GuardedWorldState`（``guard(state)`` 产物）——裸 WorldState
      直接传入即 :class:`CascadeError`（K2 运行时兜底的触发器侧执行）。

    产出提案的因果闭合义务（cause_ids 回指事件）由**执行器**统一校验
    （§7.2 末段）——本类不重复检查（单一职责）。
    """

    __slots__ = ("_trigger_id", "_evaluate_fn")

    def __init__(self, trigger_id: str, evaluate_fn: _TriggerEvaluateFn) -> None:
        """构造同步触发器（构造期守卫，输入契约不满足即抛异常）。

        Raises:
            CascadeError: ``trigger_id`` 非非空字符串，或 ``evaluate_fn``
                不可调用。
        """
        if not isinstance(trigger_id, str) or trigger_id == "":
            raise CascadeError(
                f"SyncTrigger.trigger_id 必须为非空字符串，得到 {trigger_id!r}"
            )
        if not callable(evaluate_fn):
            raise CascadeError(
                "SyncTrigger.evaluate_fn 必须可调用，得到 "
                f"{type(evaluate_fn).__name__}"
            )
        self._trigger_id = trigger_id
        self._evaluate_fn = evaluate_fn

    @property
    def trigger_id(self) -> str:
        """诊断名（协议属性，只读）。"""
        return self._trigger_id

    def evaluate(
        self,
        events: Sequence[DomainEvent],
        state: GuardedWorldState,
        depth: int,
    ) -> list[ProposedEffect]:
        """同步求值（协议方法）：委托纯函数回调，返回提案列表。

        Args:
            events: 本回合事务发射的 DomainEvent 序列（触发输入）。
            state: 提交后世界状态的**只读门面**（必须 ``guard(...)``
                产物；裸 WorldState → :class:`CascadeError`）。
            depth: 当前级联深度（D-P2-13 口径；回调可据此做深度敏感行为）。

        Returns:
            新提案列表（到达序 = 回调返回序；空列表 = 无反应）。

        Raises:
            CascadeError: ``state`` 不是 ``GuardedWorldState`` 只读门面。
        """
        if not is_guarded(state):
            raise CascadeError(
                "SyncTrigger.evaluate 的 state 必须是 GuardedWorldState 只读门面"
                "（guard(state) 产物）——触发器物理上拿不到写路径（K2；"
                f"P2 设计规范 §2.6.3/§7.2），得到 {type(state).__name__}"
            )
        return list(self._evaluate_fn(events, state, depth))


class CascadeTriggerRegistry:
    """级联触发器注册表（§7.2；运行时对象，非契约模型、不进 round-trip）。

    - :meth:`register`：同名重复注册**同实例幂等**、**异实例冲突**（
      :class:`TriggerConflictError`，与 ``ProducerRegistry`` /
      ``EffectHandlerRegistry`` 同款纪律）；协议符合性构造期守卫（缺
      ``trigger_id`` / ``evaluate`` → :class:`CascadeError`）；
    - :meth:`evaluate_all`：**按注册序**逐触发器求值并串联结果
      （确定性；空注册表 → 空列表）。
    """

    __slots__ = ("_triggers",)

    def __init__(self) -> None:
        self._triggers: dict[str, CascadeTrigger] = {}

    def register(self, trigger: CascadeTrigger) -> None:
        """注册触发器（协议守卫 + 幂等/冲突纪律，§7.2）。

        Raises:
            CascadeError: ``trigger`` 不符合 :class:`CascadeTrigger` 协议
                （``trigger_id`` 非非空字符串或 ``evaluate`` 不可调用）。
            TriggerConflictError: 同 ``trigger_id`` 已注册不同实例。
        """
        trigger_id = getattr(trigger, "trigger_id", None)
        if not isinstance(trigger_id, str) or trigger_id == "":
            raise CascadeError(
                f"CascadeTriggerRegistry.register 需要 CascadeTrigger（trigger_id 为"
                f"非空字符串），得到 {type(trigger).__name__}（trigger_id={trigger_id!r}）"
            )
        evaluate = getattr(trigger, "evaluate", None)
        if not callable(evaluate):
            raise CascadeError(
                f"CascadeTriggerRegistry.register 需要可调用 evaluate 的触发器，"
                f"得到 {type(trigger).__name__}"
            )
        existing = self._triggers.get(trigger_id)
        if existing is None:
            self._triggers[trigger_id] = trigger
        elif existing is trigger:
            return  # 同实例重复注册幂等
        else:
            raise TriggerConflictError(
                f"trigger_id {trigger_id!r} 已注册不同实例（幂等仅限同实例；"
                "P2 设计规范 §7.2 同款纪律）"
            )

    def evaluate_all(
        self,
        events: Sequence[DomainEvent],
        state: GuardedWorldState,
        depth: int,
    ) -> list[ProposedEffect]:
        """按注册序逐触发器求值并串联结果（§7.2；确定性）。

        Args:
            events: 本回合事务发射的 DomainEvent 序列。
            state: 提交后世界状态（只读门面；透传各触发器）。
            depth: 当前级联深度。

        Returns:
            全部触发器产出提案的串联列表（注册序 → 触发器内到达序；
            空注册表 → 空列表）。因果闭合过滤归执行器（§7.2 末段）。
        """
        outputs: list[ProposedEffect] = []
        for trigger in self._triggers.values():
            outputs.extend(trigger.evaluate(events, state, depth))
        return outputs

    def trigger_ids(self) -> tuple[str, ...]:
        """已注册触发器诊断名（注册序；确定性）。"""
        return tuple(self._triggers)


#: 任务包 P2-T07 表面的注册表别名（与 ``conflicts.effect_locks =
#: extract_effect_locks`` 同款 re-export 同一性纪律：两名字同一类对象，
#: closeout "同一对象" 断言对两名字同时成立）。
TriggerRegistry = CascadeTriggerRegistry


# —— 结果与统计（§7.3；任务包 P2-T07 表面）——


@dataclass(frozen=True)
class CascadeStatistics:
    """级联统计（任务包 P2-T07 表面：``CascadeResult.cascade_statistics``
    计算属性的产出形状；全部字段由结果六元组可推导，无隐藏状态）。

    - ``committed``：COMMITTED 事务数（= world_revision 净增量，Spec §9
      恰 +1 的批级形态）；
    - ``aborted``：ABORTED 事务数（审计原子失败，§6.3）；
    - ``max_committed_depth``：已提交事务的最大级联深度（None = 零提交）；
    - ``events_emitted``：发射的 DomainEvent 数（1:1 映射下 = 已提交
      effect 总数，D-P2-12）；
    - ``diagnostic_count``：诊断总数（:class:`CascadeDiagnostic` 列表长度）。
    """

    committed: int
    aborted: int
    max_committed_depth: int | None
    events_emitted: int
    diagnostic_count: int


@dataclass(frozen=True)
class CascadeResult:
    """级联执行结果（§7.3；一次 ``CascadeExecutor.run`` 的完整产出）。

    - ``final_state``：级联收敛后的世界状态（零提交时 = 输入状态同对象）；
    - ``transactions``：全部事务（**含 ABORTED**——审计原子失败，§9）；
      COMMITTED 事务的 ``commit_revision`` 严格连续（base 起恰 +1 逐个
      递增，Spec §9）；
    - ``events``：全部发射的 DomainEvent（1:1 于已提交 effect，D-P2-12；
      全部携带同一 cascade_id / causal_root_id 的 CascadeContext，depth
      与所在事务一致，§7.6 因果树验收）；
    - ``trace_records``：全部决策/诊断记录（§9 汇总表 payload 约定；
      只追加序）；
    - ``deferred``：域解析器 DEFER 的再入队残留（终态未消化者——深度
      熔断 / ABORTED 停止时仍滞留 pending 的 DEFER 提案；正常收敛时恒
      空，§5.5）；
    - ``diagnostics``：诊断列表（§7.4/§7.5；``kind`` 词表
      :data:`CASCADE_DIAGNOSTIC_KINDS`）。
    """

    final_state: WorldState
    transactions: tuple[Transaction, ...]
    events: tuple[DomainEvent, ...]
    trace_records: tuple[TraceRecord, ...]
    deferred: tuple[ProposedEffect, ...]
    diagnostics: tuple[CascadeDiagnostic, ...]

    @property
    def cascade_statistics(self) -> CascadeStatistics:
        """级联统计（计算属性：由结果字段纯函数推导，确定性）。"""
        committed = [t for t in self.transactions if t.status is TransactionStatus.COMMITTED]
        aborted = [t for t in self.transactions if t.status is TransactionStatus.ABORTED]
        max_depth: int | None = None
        for txn in committed:
            ctx = txn.cascade
            if ctx is not None:
                max_depth = ctx.depth if max_depth is None else max(max_depth, ctx.depth)
        return CascadeStatistics(
            committed=len(committed),
            aborted=len(aborted),
            max_committed_depth=max_depth,
            events_emitted=len(self.events),
            diagnostic_count=len(self.diagnostics),
        )


#: 任务包 P2-T07 表面的结果别名（设计规范 §1.2 名称为 ``CascadeResult``；
#: 同一类对象，closeout "同一对象" 断言对两名字同时成立）。
CascadeExecutionResult = CascadeResult


# —— 回合内部结构（私有）——


@dataclass(frozen=True)
class _RoundOutcome:
    """单回合产出（``_run_round`` 返回值；私有结构，不进 ``__all__``）。

    - ``state``：回合后状态（COMMITTED → 新状态；ABORTED / 空回合 → 原状态）；
    - ``txn``：本回合事务（空回合 → None，不消耗 revision，P1 §5.6 不变量
      1 的管道镜像）；
    - ``events``：COMMITTED 时发射的事件（ABORTED / 空回合 → 空元组）；
    - ``committed_locks``：本回合已提交 effect 的锁集合（仅 COMMITTED
      有意义；供 ``CycleDetector.observe_commit`` 登记，§7.5）；
    - ``deferred``：本回合 DEFER 裁决的再入队提案（原 cause_ids / 原相对
      到达序，§5.5）。
    """

    state: WorldState
    txn: Transaction | None
    events: tuple[DomainEvent, ...]
    committed_locks: frozenset[ConflictKey]
    deferred: tuple[ProposedEffect, ...]


def _guard_proposed_effects(items: Sequence[object], where: str) -> list[ProposedEffect]:
    """输入契约守卫：全体元素为 ``ProposedEffect``（确定性管道纪律）。"""
    out: list[ProposedEffect] = []
    for item in items:
        if not isinstance(item, ProposedEffect):
            raise CascadeError(
                f"{where} 需要 Sequence[ProposedEffect]，得到含 {type(item).__name__} 元素的序列"
            )
        out.append(item)
    return out


# —— 执行器（§7.3；P2-T07 主体 + P2-T08 默认接线）——


class CascadeExecutor:
    """级联执行器（§7.3；K2 管道的运行时编排体）。

    构造（全部依赖注入；缺省值即"开箱即用"的 kernel 运行时配置）：

    - ``policy``：**必填**——权限策略（§3.3；closed-by-default）；
    - ``component_registry`` / ``producer_registry``：透传 authority
      匹配（entity_tag/domain_tag 维）、validation（schema 语义）与事件
      provenance origin 解析（§6.4）；
    - ``handlers``：effect handler 注册表；None → ``default_handler
      _registry()``（validation 的 no_handler 阶段与 reducer 应用**共享
      同一注册表**——未注册语义型 effect 在 L1 即过滤（D-P2-05），reducer
      兜底抛错路径为纵深防御）；
    - ``triggers``：触发器注册表；None → 空注册表（无触发器 = 单回合
      执行器）；
    - ``resolvers``：域解析器工厂（§5.5 扩展位；None → 纯默认四策链；
      工厂按组返回专用策略或 None 弃权回落默认链——DEFER 语义
      机制正确性经本钩子兑现）；
    - ``validator``：L1 校验器；None → 缺省 ``EffectValidator()``（固定
      七阶段管道）；
    - ``config``：级联配置；None → 缺省 ``CascadeConfig()``（深度 8 /
      forbid / 非 strict）；
    - ``cycle_detector``（T07 注入钩子）：注入实例跨 run 复用（调用方
      负责生命周期）；None → 每次 ``run()`` 按 ``config.location_revisit``
      新建（级联链作用域，防跨级联串位）。

    :meth:`__init__` 调用 :func:`install_write_barrier` 武装写屏障
    （kernel 运行时入口，幂等；§2.6.2——opt-in 武装时机即此处与测试夹具）。
    """

    def __init__(
        self,
        *,
        policy: AuthorityPolicy,
        component_registry: ComponentRegistry | None = None,
        producer_registry: ProducerRegistry | None = None,
        handlers: EffectHandlerRegistry | None = None,
        triggers: CascadeTriggerRegistry | None = None,
        resolvers: DomainResolverFactory | None = None,
        validator: EffectValidator | None = None,
        config: CascadeConfig | None = None,
        cycle_detector: CycleDetector | None = None,
    ) -> None:
        install_write_barrier()  # kernel 运行时入口武装屏障（幂等，§2.6.2）
        if not isinstance(policy, AuthorityPolicy):
            raise CascadeError(
                f"CascadeExecutor 需要 AuthorityPolicy，得到 {type(policy).__name__}"
            )
        if component_registry is not None and not isinstance(component_registry, ComponentRegistry):
            raise CascadeError(
                f"CascadeExecutor.component_registry 需要 ComponentRegistry，得到 "
                f"{type(component_registry).__name__}"
            )
        if producer_registry is not None and not isinstance(producer_registry, ProducerRegistry):
            raise CascadeError(
                f"CascadeExecutor.producer_registry 需要 ProducerRegistry，得到 "
                f"{type(producer_registry).__name__}"
            )
        if handlers is not None and not isinstance(handlers, EffectHandlerRegistry):
            raise CascadeError(
                f"CascadeExecutor.handlers 需要 EffectHandlerRegistry，得到 "
                f"{type(handlers).__name__}"
            )
        if triggers is not None and not isinstance(triggers, CascadeTriggerRegistry):
            raise CascadeError(
                f"CascadeExecutor.triggers 需要 CascadeTriggerRegistry，得到 "
                f"{type(triggers).__name__}"
            )
        if validator is not None and not isinstance(validator, EffectValidator):
            raise CascadeError(
                f"CascadeExecutor.validator 需要 EffectValidator，得到 {type(validator).__name__}"
            )
        if config is not None and not isinstance(config, CascadeConfig):
            raise CascadeError(
                f"CascadeExecutor.config 需要 CascadeConfig，得到 {type(config).__name__}"
            )
        if cycle_detector is not None and not isinstance(cycle_detector, CycleDetector):
            raise CascadeError(
                f"CascadeExecutor.cycle_detector 需要 CycleDetector，得到 "
                f"{type(cycle_detector).__name__}"
            )
        self._policy = policy
        self._component_registry = component_registry
        self._producer_registry = producer_registry
        self._handlers = handlers if handlers is not None else default_handler_registry()
        self._triggers = triggers if triggers is not None else CascadeTriggerRegistry()
        self._resolvers = resolvers
        self._validator = validator if validator is not None else EffectValidator()
        self._config = config if config is not None else CascadeConfig()
        self._cycle_detector = cycle_detector
        # 无状态策略链：跨 run 共享安全（§5.3 纯函数纪律）
        self._default_resolver = DefaultConflictResolver()

    @property
    def config(self) -> CascadeConfig:
        """本执行器的级联配置（只读视图）。"""
        return self._config

    # —— 主入口 ——

    def run(
        self,
        initial_proposals: Sequence[ProposedEffect],
        state: WorldState,
        *,
        causal_root_id: str,
        origin: Provenance,
    ) -> CascadeResult:
        """执行一次完整级联（§7.3 主循环；模块 docstring 的伪代码落位）。

        Args:
            initial_proposals: 根提案批次（到达序；空批次 → 零回合结果，
                状态原样）。全体元素必须为 ``ProposedEffect``。
            state: 级联起始世界状态（base revision；**任何路径下不被
                触碰**——纯函数管道，§6.3）。
            causal_root_id: **必填**（Spec §21.3）——级联根（调用方传入
                ActionInstanceId / EventId 的字符串形态；执行器自身不发明
                根身份，P3 调度器启动级联时以 action 实例为根）。
            origin: 事务级 Provenance（装配者，入全部事务
                ``provenance``；与各 effect 提案者分层，§6.4 注）。

        Returns:
            :class:`CascadeResult`（六元组 + ``cascade_statistics`` 计算
            属性）——缺省（非 strict）语义下**恒返回**：深度超限记诊断后
            收敛（§7.3），环路命中丢弃提案后收敛（§7.5），ABORTED 停止
            经 ABORTED 事务 trace 审计（§6.3）。

        Raises:
            CascadeError: 输入契约违规（非 ``ProposedEffect`` 元素 /
                非 ``WorldState`` 状态 / ``causal_root_id`` 非非空字符串 /
                非 ``Provenance`` origin）。
            CascadeDepthExceededError: ``config.strict`` 且
                ``depth > max_cascade_depth`` 的回合尝试启动（§7.1）。
            CascadeCycleError: ``config.strict`` 且 ``location_revisit =
                forbid`` 且提案锁位置重访祖先已提交位置（§7.5）。
        """
        proposals = _guard_proposed_effects(initial_proposals, "CascadeExecutor.run")
        if not isinstance(state, WorldState):
            raise CascadeError(f"CascadeExecutor.run 需要 WorldState，得到 {type(state).__name__}")
        if not isinstance(causal_root_id, str) or causal_root_id == "":
            raise CascadeError(
                f"causal_root_id 必填且必须为非空字符串（Spec §21.3；调用方传入 "
                f"ActionInstanceId/EventId），得到 {causal_root_id!r}"
            )
        if not isinstance(origin, Provenance):
            raise CascadeError(
                f"CascadeExecutor.run 的 origin 需要 Provenance，得到 {type(origin).__name__}"
            )

        config = self._config
        # 级联链作用域检测器：缺省每次 run 新建（防跨级联串位，§7.5）
        cycle = self._cycle_detector
        if cycle is None:
            cycle = CycleDetector(mode=config.location_revisit)

        cascade_id = new_cascade_id()
        depth = 0
        pending = list(proposals)
        # DEFER 再入队残留跟踪（终态未消化者 → result.deferred，§5.5）
        deferred_pending: list[ProposedEffect] = []
        current = state
        transactions: list[Transaction] = []
        events: list[DomainEvent] = []
        traces: list[TraceRecord] = []
        diagnostics: list[CascadeDiagnostic] = []

        while pending:
            # —— 深度熔断（§7.1/§7.3：depth > max 的回合不启动）——
            if depth > config.max_cascade_depth:
                diag = CascadeDiagnostic(
                    kind="cascade_depth_exceeded",
                    depth=depth,
                    detail=(
                        f"depth={depth} 超过最大触发深度 max_cascade_depth="
                        f"{config.max_cascade_depth}：本回合不启动，级联收敛"
                        f"（已提交深度 0..{config.max_cascade_depth}，D-P2-13）"
                    ),
                )
                diagnostics.append(diag)
                traces.append(
                    _system_trace(diag, cascade_id, current.world_revision)
                )
                if config.strict:
                    raise CascadeDepthExceededError(
                        depth=depth,
                        max_cascade_depth=config.max_cascade_depth,
                        cascade_id=str(cascade_id),
                    )
                break

            cascade_ctx = CascadeContext(
                cascade_id=cascade_id, causal_root_id=causal_root_id, depth=depth
            )
            outcome = self._run_round(
                current, pending, depth, cascade_ctx, origin, traces, diagnostics, cycle
            )
            current = outcome.state
            pending = []
            deferred_pending = []

            if outcome.txn is not None:
                transactions.append(outcome.txn)
                if outcome.txn.status is TransactionStatus.COMMITTED:
                    events.extend(outcome.events)
                    # 登记本回合已提交位置集（§7.5：ABORTED 不登记）
                    cycle.observe_commit(depth, outcome.committed_locks)
                    # 触发器求值 + 因果闭合过滤（§7.2；无事件不评估——
                    # 闭合检查恒丢弃，等价且省调用）
                    if outcome.events:
                        pending.extend(
                            self._collect_trigger_outputs(
                                outcome.events, current, depth, cascade_ctx,
                                traces, diagnostics,
                            )
                        )
                        # DEFER 再入队（§5.5：原 cause_ids / 原相对到达序）
                        pending.extend(outcome.deferred)
                        deferred_pending.extend(outcome.deferred)
                else:
                    # ABORTED → 级联停止：无事件可触发（§7.3 主循环；审计
                    # 经 ABORTED 事务 trace，§6.3——§7.4 诊断词表无对应
                    # kind，不另造词）
                    deferred_pending.extend(outcome.deferred)
                    break
            else:
                # 空回合（无事务）：无事件可触发；DEFER 残留再入队下一回合
                # （深度上限兜底防无限 defer，§14 OQ3）
                pending.extend(outcome.deferred)
                deferred_pending.extend(outcome.deferred)
            depth += 1

        return CascadeResult(
            final_state=current,
            transactions=tuple(transactions),
            events=tuple(events),
            trace_records=tuple(traces),
            deferred=tuple(deferred_pending),
            diagnostics=tuple(diagnostics),
        )

    # —— 回合管道（§7.3 run_round 六步 + §7.5 装配前环路检查）——

    def _run_round(
        self,
        state: WorldState,
        pending: Sequence[ProposedEffect],
        depth: int,
        cascade_ctx: CascadeContext,
        origin: Provenance,
        traces: list[TraceRecord],
        diagnostics: list[CascadeDiagnostic],
        cycle: CycleDetector,
    ) -> _RoundOutcome:
        """单回合执行（D-P2-03：一回合一个事务；§7.3 步骤 1-6）。

        步骤（trace 只追加序）：

        1. trace 每个提案（``PROPOSED_EFFECT``，``PAYLOAD_RECORD_KEY``
           内嵌记录，§9）；
        2. **authority**：逐 effect ``check_authority``；deny → 丢弃 +
           ``AUTHORITY_DECISION`` trace（decision=deny，reason=reason
           code[+rule index]，§3.5/§9）；
        3. **validation L1**：``validate_batch``；fail → 丢弃 +
           ``VALIDATION_DECISION`` trace（decision=fail，reason=issues
           ``to_trace_str`` 分号串接；pass → reason 空串，§9）；
        4. **conflicts**：``detect_conflicts`` 连通分量分组 → 逐组解析
           （域解析器钩子优先，弃权回落默认四策，§5.5）；逐组
           ``CONFLICT_RESOLUTION`` trace（胜者或组成员串 + 策略名 +
           detail，§9）；DEFER 裁决的 accepted → 本回合再入队（不进事务）；
        5. **环路检查**（§7.5 装配前）：accepted 逐个 ``cycle.check``；
           命中 → 丢弃 + SYSTEM 诊断（``cycle_detected``）+ trace，
           strict → 抛 :class:`CascadeCycleError`（过滤语义，不触发整
           事务失败）；全被丢弃 → 回合空转（无事务、无事件）；
        6. **装配与提交**：accepted 按到达序；空 → 本回合无事务（不消耗
           revision，P1 §5.6 不变量 1 的管道镜像）；否则
           ``commit_transaction``（L2 终检 + reducer + 事件发射）；
           ``TRANSACTION`` trace（含 ABORTED + ``rejected_effect_ids``）
           + 每事件 ``DOMAIN_EVENT`` trace（§9）。
        """
        rev = state.world_revision

        # 步骤 1：trace 每个提案（PROPOSED_EFFECT）
        for effect in pending:
            traces.append(
                TraceRecord(
                    record_id=new_trace_record_id(),
                    kind=TraceKind.PROPOSED_EFFECT,
                    world_revision=rev,
                    producer_id=effect.source,
                    cascade_id=cascade_ctx.cascade_id,
                    payload={PAYLOAD_RECORD_KEY: effect.model_dump(mode="json")},
                )
            )

        # 步骤 2：authority（逐 effect；deny → 丢弃 + trace）
        authority_decisions: dict[EffectId, AuthorityEvaluationResult] = {}
        allowed: list[ProposedEffect] = []
        for effect in pending:
            decision = check_authority(
                effect, self._policy, state, component_registry=self._component_registry
            )
            authority_decisions[effect.effect_id] = decision
            traces.append(
                TraceRecord(
                    record_id=new_trace_record_id(),
                    kind=TraceKind.AUTHORITY_DECISION,
                    world_revision=rev,
                    producer_id=effect.source,
                    cascade_id=cascade_ctx.cascade_id,
                    payload=decision.to_trace_payload(),
                )
            )
            if decision.decision is AuthorityDecision.ALLOW:
                allowed.append(effect)

        # 步骤 3：validation L1（过滤语义，D-P2-10）
        vctx = ValidationContext(
            state,
            component_registry=self._component_registry,
            handlers=self._handlers,
        )
        vreport = self._validator.validate_batch(allowed, vctx)
        validated = list(vreport.accepted)
        for effect in allowed:
            issues = vreport.issues_for(str(effect.effect_id))
            traces.append(
                TraceRecord(
                    record_id=new_trace_record_id(),
                    kind=TraceKind.VALIDATION_DECISION,
                    world_revision=rev,
                    producer_id=effect.source,
                    cascade_id=cascade_ctx.cascade_id,
                    payload={
                        "effect_id": str(effect.effect_id),
                        "decision": "pass" if not issues else "fail",
                        "reason": ";".join(issue.to_trace_str() for issue in issues),
                    },
                )
            )

        # 步骤 4：conflicts（分组 + 逐组解析；DEFER → 再入队）
        if validated:
            rctx = ResolutionContext.from_batch(
                validated,
                authority_decisions=authority_decisions,
                producer_registry=self._producer_registry,
            )
            creport = self._resolve_batch(validated, rctx)
        else:
            creport = ConflictResolutionReport(resolutions=(), accepted=(), dropped=())
        for resolution in creport.resolutions:
            traces.append(
                TraceRecord(
                    record_id=new_trace_record_id(),
                    kind=TraceKind.CONFLICT_RESOLUTION,
                    world_revision=rev,
                    cascade_id=cascade_ctx.cascade_id,
                    payload=resolution.to_trace_payload(),
                )
            )
        by_id = {effect.effect_id: effect for effect in validated}
        deferred: list[ProposedEffect] = []
        deferred_ids: set[EffectId] = set()
        for resolution in creport.resolutions:
            if resolution.action is ConflictAction.DEFER:
                # §5.5：DEFER 裁决的 accepted 作为下一回合提案再入队
                # （保留原 cause_ids、原相对到达序）；dropped 仍进 trace
                deferred_ids.update(resolution.accepted)
                for effect_id in resolution.accepted:
                    effect = by_id.get(effect_id)
                    if effect is not None:
                        deferred.append(effect)
        accepted_ids = [eid for eid in creport.accepted if eid not in deferred_ids]

        # 步骤 5：环路检查（装配前，§7.5；过滤语义）
        survivors: list[ProposedEffect] = []
        for effect_id in accepted_ids:
            effect = by_id[effect_id]
            hit = cycle.check(effect)
            if hit is None:
                survivors.append(effect)
                continue
            detail = (
                f"[depth{depth}] {effect.effect_type}@{hit.key.render()} 重访 "
                f"[depth{hit.ancestor_depth}] 已提交位置（effect_id={effect.effect_id}）"
            )
            diag = CascadeDiagnostic(kind="cycle_detected", depth=depth, detail=detail)
            diagnostics.append(diag)
            traces.append(_system_trace(diag, cascade_ctx.cascade_id, rev))
            if self._config.strict:
                raise CascadeCycleError(
                    depth=depth,
                    cascade_id=str(cascade_ctx.cascade_id),
                    hit=hit,
                    detail=detail,
                )

        # 步骤 6：装配与提交（空 → 回合空转，不消耗 revision）
        if not survivors:
            return _RoundOutcome(
                state=state, txn=None, events=(), committed_locks=frozenset(),
                deferred=tuple(deferred),
            )
        tx_id = new_transaction_id()
        new_state, txn, round_events = commit_transaction(
            state,
            survivors,
            tx_id,
            origin,
            cascade=cascade_ctx,
            component_registry=self._component_registry,
            handlers=self._handlers,
            producer_registry=self._producer_registry,
        )
        tx_payload: dict[str, Any] = {PAYLOAD_RECORD_KEY: txn.model_dump(mode="json")}
        if txn.status is TransactionStatus.ABORTED:
            tx_payload["rejected_effect_ids"] = [str(e.effect_id) for e in survivors]
        traces.append(
            TraceRecord(
                record_id=new_trace_record_id(),
                kind=TraceKind.TRANSACTION,
                world_revision=new_state.world_revision,
                transaction_id=tx_id,
                producer_id=origin.producer_id,
                cascade_id=cascade_ctx.cascade_id,
                payload=tx_payload,
            )
        )
        for event in round_events:
            traces.append(
                TraceRecord(
                    record_id=new_trace_record_id(),
                    kind=TraceKind.DOMAIN_EVENT,
                    world_revision=event.world_revision,
                    transaction_id=tx_id,
                    producer_id=event.source_system,
                    cascade_id=cascade_ctx.cascade_id,
                    payload={PAYLOAD_RECORD_KEY: event.model_dump(mode="json")},
                )
            )
        committed_locks: frozenset[ConflictKey] = frozenset()
        for effect in survivors:
            committed_locks = committed_locks | extract_effect_locks(effect)
        return _RoundOutcome(
            state=new_state,
            txn=txn,
            events=tuple(round_events),
            committed_locks=committed_locks,
            deferred=tuple(deferred),
        )

    # —— 冲突解析批入口（默认四策 + §5.5 域解析器钩子）——

    def _resolve_batch(
        self, effects: Sequence[ProposedEffect], ctx: ResolutionContext
    ) -> ConflictResolutionReport:
        """批级冲突解析（§7.3 步骤 4）。

        无域解析器：直通 ``DefaultConflictResolver.resolve_all``（含输入
        守卫）。有域解析器：``detect_conflicts`` 分组后逐组——工厂按组
        返回专用策略（其裁决拍板，弃权 None 回落默认链；DEFER/MERGE/
        REPAIR 五值全兼容透传，§5.3/§5.5）。
        """
        if self._resolvers is None:
            return self._default_resolver.resolve_all(effects, ctx)
        effect_ids = [effect.effect_id for effect in effects]
        if len(set(effect_ids)) != len(effect_ids):
            raise CascadeError(
                "run_round 冲突解析输入批含重复 effect_id（KBC-2；应由 "
                "validation L1 'duplicated_effect_id' 上游过滤）"
            )
        missing = [eid for eid in effect_ids if eid not in ctx.arrival]
        if missing:
            raise CascadeError(
                "ctx.arrival 未覆盖批内全部 effects（到达序是唯一权威序）："
                + ", ".join(str(eid) for eid in missing)
            )
        groups = detect_conflicts(effects)
        resolutions = tuple(self._resolve_group(group, ctx) for group in groups)
        dropped_ids = {eid for res in resolutions for eid in res.dropped}
        return ConflictResolutionReport(
            resolutions=resolutions,
            accepted=tuple(eid for eid in effect_ids if eid not in dropped_ids),
            dropped=tuple(eid for eid in effect_ids if eid in dropped_ids),
        )

    def _resolve_group(
        self, group: ConflictGroup, ctx: ResolutionContext
    ) -> ConflictResolution:
        """单组解析：域解析器钩子优先（弃权回落默认策略链，§5.5）。"""
        if self._resolvers is not None:
            domain_strategy = self._resolvers(group, ctx)
            if domain_strategy is not None:
                resolution = domain_strategy.resolve(group, ctx)
                if resolution is not None:
                    return resolution
        return self._default_resolver.resolve_group(group, ctx)

    # —— 触发器求值与因果闭合检查（§7.2 末段，K6）——

    def _collect_trigger_outputs(
        self,
        round_events: Sequence[DomainEvent],
        state: WorldState,
        depth: int,
        cascade_ctx: CascadeContext,
        traces: list[TraceRecord],
        diagnostics: list[CascadeDiagnostic],
    ) -> list[ProposedEffect]:
        """触发器求值 + 因果闭合过滤（§7.2 末段；K6 级联链可完整重建）。

        对每个触发器产出提案校验：``cause_ids`` 必须含 ≥1 个
        ``CauseKind.EVENT`` 且 ``ref_id`` ∈ 本回合事件 ID 集；不满足（含
        非 ``ProposedEffect`` 产出）→ 丢弃 + SYSTEM 诊断
        （``trigger_output_dropped``）+ trace。该丢弃两种 strict 模式下
        均为诊断记录（非深度/环路熔断事件，§7.4 词表定位）。
        """
        raw = self._triggers.evaluate_all(round_events, guard(state), depth)
        event_ids = {str(event.event_id) for event in round_events}
        outputs: list[ProposedEffect] = []
        for proposed in raw:
            if not isinstance(proposed, ProposedEffect):
                _record_trigger_drop(
                    depth,
                    cascade_ctx,
                    state.world_revision,
                    f"触发器产出非 ProposedEffect（{type(proposed).__name__}）：丢弃",
                    traces,
                    diagnostics,
                )
                continue
            has_event_cause = any(
                cause.kind is CauseKind.EVENT and cause.ref_id in event_ids
                for cause in proposed.cause_ids
            )
            if not has_event_cause:
                _record_trigger_drop(
                    depth,
                    cascade_ctx,
                    state.world_revision,
                    (
                        f"触发提案 {proposed.effect_id} 未回指本回合事件"
                        f"（cause_ids 须含 ≥1 个 EVENT 且 ref_id ∈ 本回合事件"
                        f" ID 集，K6 因果闭合，P2 设计规范 §7.2）：丢弃"
                    ),
                    traces,
                    diagnostics,
                )
                continue
            outputs.append(proposed)
        return outputs


def _record_trigger_drop(
    depth: int,
    cascade_ctx: CascadeContext,
    world_revision: Revision,
    detail: str,
    traces: list[TraceRecord],
    diagnostics: list[CascadeDiagnostic],
) -> None:
    """触发输出丢弃的 SYSTEM 诊断 + trace 落档（§7.4 payload 约定）。"""
    diag = CascadeDiagnostic(kind="trigger_output_dropped", depth=depth, detail=detail)
    diagnostics.append(diag)
    traces.append(_system_trace(diag, cascade_ctx.cascade_id, world_revision))


def _system_trace(
    diag: CascadeDiagnostic, cascade_id: CascadeId, world_revision: Revision
) -> TraceRecord:
    """诊断 → SYSTEM TraceRecord（§7.4 冻结 payload 键名约定）。

    ``{"diagnostic": <kind>, "cascade_id": str, "depth": int, "detail":
    str}``；坐标按 §9 末段填充（``world_revision`` = 记录时 state 的
    revision、``logical_tick=None``、``cascade_id`` 关联键）。
    """
    return TraceRecord(
        record_id=new_trace_record_id(),
        kind=TraceKind.SYSTEM,
        world_revision=world_revision,
        cascade_id=cascade_id,
        payload={
            "diagnostic": diag.kind,
            "cascade_id": str(cascade_id),
            "depth": diag.depth,
            "detail": diag.detail,
        },
    )
