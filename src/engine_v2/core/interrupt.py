"""engine_v2 core 层决策边界（decision boundary）与声明式条件求值（P3-T05）。

依据 ``docs/v2/contracts/P3-scheduler-time-action-design.md``（下称"设计文档"）
§3.7（全量）：

- **声明式模型（禁闭包）**：:class:`InterruptCondition`（``kind`` + ``parameters``
  声明式；条件求值纯函数、无闭包状态）与 :class:`DecisionBoundary`（P3 新增
  单列类型，Spec §23.2 decision boundary 概念的落地；``kind`` 互斥校验——
  ``scheduled`` ⇒ ``due_tick`` 必填且 ``condition`` 禁声明，``condition`` ⇒
  ``condition`` 必填且 ``due_tick`` 禁声明，词表外 kind 拒绝；可检查不静默）；
- **内置 4 kind（D-P3-09/D-P3-17，纯求值）**：``event_type``（匹配
  ``DomainEvent.event_type`` 真实字段——本刻提交事件流中出现该类型事件即命中）/
  ``world_variable``（键值 op 比较）/ ``entity_component``（field_path 点分
  嵌套取值后 op 比较）/ ``time``（当前逻辑刻经 ``tick`` 入参**显式**传入，
  D-P3-21——guard 视图与事件流均不携带当前刻；op 缺省 ``gte``）；op 词表
  ``gt``/``gte``/``lt``/``lte``/``eq``；
- **扩展位（P5/P9）**：:class:`ConditionResolver` 协议（命名注册，禁闭包）+
  :class:`ConditionResolverRegistry`；:data:`BUILTIN_CONDITION_RESOLVERS` 为
  内置 4 kind 的**共享缺省实例**——对其调用 ``register`` 属配置错误、构造期
  语义下 ``register`` 直接拒绝（自定义 kind 须自建 registry 传入，E-P3-39④）；
- **边界报告**：:func:`evaluate_boundaries` 按注册序求值（确定性）；scheduled
  边界仅 ``due_tick <= tick`` 时参评；blocking 判定 = ``boundary.blocking``
  且 actor ∈ ``player_actor_ids``（D-P3-10）——玩家 blocking 命中置
  ``player_blocking``，其余命中入 ``npc_notices``（wakeup 建议，§2.4 npc
  分支 → scheduler 侧 ``enqueue_actor_wakeup`` 双记录口径，不受
  ``pause_on_player_boundary`` 辖制）；
- **错误可检查性（D-P3-16）**：kind 非内置且传入 registry 未注册 →
  :class:`UnknownConditionError`；参数缺失/非法（含 op 词表外、类型不符）→
  :class:`SchedulerError`——可检查不静默。状态性缺席（世界变量未设、实体/
  组件/字段路径缺失）是**条件不成立**（miss → False），非配置错误。

确定性纪律（设计文档 §0.3/§8.3）：仅 stdlib + pydantic + 同包
``src.engine_v2`` 导入；P3 专项黑名单 ``datetime`` / ``time`` / ``random`` /
``asyncio`` 对本模块生效——零墙钟、零隐式随机、零协程。本模块**不 import
``scheduler.py``**（Leader 裁定 (A)：scheduler 为刻后求值调用方、interrupt
为纯求值被调方，单向依赖防环；interrupt 只依赖 P1 state/events/ids/
actions + P2 ``reducer.guard()`` 视图类型 + ``clock.py`` 错误基类）。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final, Protocol

from pydantic import Field, JsonValue, model_validator

from src.engine_v2.core.actions import ActionLifecycleStatus
from src.engine_v2.core.clock import SchedulerError
from src.engine_v2.core.components import ComponentTypeId
from src.engine_v2.core.entity import ContractModel
from src.engine_v2.core.events import DomainEvent
from src.engine_v2.core.ids import ActionInstanceId, EntityId
from src.engine_v2.core.reducer import GuardedWorldState
from src.engine_v2.core.state import RuntimeState

__all__ = [
    "CONDITION_KINDS",
    "InterruptCondition",
    "DecisionBoundary",
    "ConditionResolver",
    "ConditionResolverRegistry",
    "BUILTIN_CONDITION_RESOLVERS",
    "BoundaryReport",
    "evaluate_condition",
    "evaluate_boundaries",
    "UnknownConditionError",
]

#: 内置声明式 kind 词表（D-P3-09/D-P3-17）
CONDITION_KINDS: Final[frozenset[str]] = frozenset(
    {"event_type", "world_variable", "entity_component", "time"}
)

#: op 比较词表（``world_variable`` / ``entity_component`` / ``time`` 共用）
_OP_VOCABULARY: Final[frozenset[str]] = frozenset({"gt", "gte", "lt", "lte", "eq"})

#: 边界 kind 词表（``DecisionBoundary.kind`` 互斥校验用）
_BOUNDARY_KINDS: Final[frozenset[str]] = frozenset({"scheduled", "condition"})


class InterruptCondition(ContractModel):
    """声明式中断条件（设计文档 §3.7；禁闭包——参数全部显式声明、可序列化）。

    - ``condition_id``：条件标识（诊断/trace 用自由串）；
    - ``kind``：:data:`CONDITION_KINDS` 或已注册 resolver 名（命名注册扩展位，
      未注册且非内置 → :class:`UnknownConditionError`，D-P3-16）；
    - ``parameters``：各 kind 的参数契约（求值纯函数、view 为 ``guard()``
      深冻结视图）：

      - ``event_type``：``{"event_type": str}``——匹配
        ``DomainEvent.event_type``（真实字段，events.py 无 kind 字段；事件
        类型恒等于 effect 类型，transaction_executor.py:146）——本刻提交事件
        流中出现该 event_type 的事件即命中（D-P3-17）；
      - ``world_variable``：``{"key": str, "op": "gt|gte|lt|lte|eq",
        "value": JsonValue}``——世界变量缺席 = 条件不成立（miss）；
      - ``entity_component``：``{"entity_id": EntityId, "component_type": str,
        "field_path": str, "op": 同上, "value": JsonValue}``——field_path 点分
        嵌套取值；实体/组件/路径缺失 = miss；
      - ``time``：``{"tick": int}``（op 同上一律支持、缺省 ``gte``）——当前
        逻辑刻经 :func:`evaluate_condition` 的 ``tick`` 入参显式传入（D-P3-21）。
    """

    condition_id: str
    kind: str
    parameters: dict[str, JsonValue] = Field(default_factory=dict)


class DecisionBoundary(ContractModel):
    """决策边界（设计文档 §3.7；Spec §23.2 decision boundary 概念，Spec L1305；
    P3 新增单列类型，定位为 §23.3 SHOULD 显式状态清单的扩展项——清单为 SHOULD
    非穷举，扩展不构成违背）。

    - ``kind``：``"scheduled"``（刻到即候选——仅 ``due_tick <= tick`` 时参评；
      队列停靠条目由 scheduler 循环前播种，D-P3-22）| ``"condition"``
      （每刻提交后条件求值）；两形态**恰居其一（互斥，均声明式）**：
      ``scheduled`` ⇒ ``due_tick`` 必填且 ``condition`` 禁声明，
      ``condition`` ⇒ ``condition`` 必填且 ``due_tick`` 禁声明（构造期拒绝，
      可检查不静默）；
    - ``blocking``：True 且 actor ∈ ``player_actor_ids`` 才触发调度暂停
      （D-P3-10）；
    - ``interrupt``：命中时是否中断该 actor 的 ACTIVE interruptible 行动
      （非阻塞/非中断边界命中 → 不迁 INTERRUPTED、不暂停；中断后其后
      checkpoint 刻守卫 no-op 诊断 ``checkpoint_skipped_interrupted`` 与收敛
      路径见 D-P3-25）；
    - ``reason``：可空自由文本（迁移记录 reason 原样透传，§3.6）。
    """

    boundary_id: str
    actor_id: EntityId
    kind: str
    due_tick: int | None = None  # kind=="scheduled" 必填
    condition: InterruptCondition | None = None  # kind=="condition" 必填
    blocking: bool = False
    interrupt: bool = True
    reason: str | None = None

    @model_validator(mode="after")
    def _validate_kind_exclusivity(self) -> DecisionBoundary:
        """kind 词表 + scheduled/condition 双形态互斥（构造期拒绝）。"""
        if self.kind not in _BOUNDARY_KINDS:
            raise ValueError(
                f"kind 必须为 'scheduled' 或 'condition'（实际 {self.kind!r}）"
                "——词表外 kind 构造期拒绝，可检查不静默"
            )
        if self.kind == "scheduled":
            if self.due_tick is None:
                raise ValueError(
                    f"scheduled 边界 {self.boundary_id!r} 必须声明 due_tick"
                    "（kind='scheduled' ⇒ due_tick 必填）"
                )
            if self.condition is not None:
                raise ValueError(
                    f"scheduled 边界 {self.boundary_id!r} 不得声明 condition"
                    "（scheduled/condition 双形态互斥）"
                )
        else:  # kind == "condition"
            if self.condition is None:
                raise ValueError(
                    f"condition 边界 {self.boundary_id!r} 必须声明 condition"
                    "（kind='condition' ⇒ condition 必填）"
                )
            if self.due_tick is not None:
                raise ValueError(
                    f"condition 边界 {self.boundary_id!r} 不得声明 due_tick"
                    "（scheduled/condition 双形态互斥）"
                )
        return self


class ConditionResolver(Protocol):
    """条件 resolver 协议（设计文档 §3.7；P5/P9 扩展位、命名注册）。

    求值纯函数（禁闭包状态）：``tick`` = 当前逻辑刻（D-P3-21——``time`` kind
    的唯一来源；view 为世界态视图，WorldState 无 logical_tick 字段，事件
    ``logical_tick`` 恒 None（D-P2-18））。
    """

    def evaluate(
        self,
        condition: InterruptCondition,
        view: GuardedWorldState,
        events: Sequence[DomainEvent],
        *,
        tick: int,
    ) -> bool: ...


class ConditionResolverRegistry:
    """条件 resolver 命名注册表（普通类：持 callable，非状态）。

    - ``register``：同 kind 重复注册 → :class:`SchedulerError`（命名注册每
      kind 唯一——确定性纪律 K7，构造点拒绝、不静默覆盖）；
    - ``resolve``：未注册 → ``None``（调用方按 D-P3-16 抛
      :class:`UnknownConditionError`，本类不吞错）；
    - 共享缺省实例 :data:`BUILTIN_CONDITION_RESOLVERS`（内部
      ``_shared_default`` 标记位）拒绝任何 ``register``——自定义 kind 须自建
      本类实例并传入 scheduler（E-P3-39④；对共享缺省实例调用 register 属
      配置错误、直接可检查拒绝）。
    """

    __slots__ = ("_resolvers", "_shared_default")

    def __init__(self, *, _shared_default: bool = False) -> None:
        self._resolvers: dict[str, ConditionResolver] = {}
        self._shared_default = _shared_default

    def register(self, kind: str, resolver: ConditionResolver) -> None:
        if self._shared_default:
            raise SchedulerError(
                "对 BUILTIN_CONDITION_RESOLVERS 共享缺省实例调用 register 属配置错误"
                "——自定义 kind 请自建 ConditionResolverRegistry 并传入"
                "（E-P3-39④）"
            )
        if kind in self._resolvers:
            raise SchedulerError(
                f"同 kind 重复注册：{kind!r}（命名注册每 kind 唯一——"
                "可检查不静默，确定性纪律 K7）"
            )
        self._resolvers[kind] = resolver

    def resolve(self, kind: str) -> ConditionResolver | None:
        return self._resolvers.get(kind)


# —— 内置 4 kind 纯求值（私有实现；对外仅 BUILTIN_CONDITION_RESOLVERS）——


def _require_param(condition: InterruptCondition, key: str) -> Any:
    if key not in condition.parameters:
        raise SchedulerError(
            f"条件 {condition.condition_id!r}（kind={condition.kind!r}）缺失必填"
            f"参数 {key!r}——可检查不静默"
        )
    return condition.parameters[key]


def _require_str_param(condition: InterruptCondition, key: str) -> str:
    value = _require_param(condition, key)
    if not isinstance(value, str):
        raise SchedulerError(
            f"条件 {condition.condition_id!r}（kind={condition.kind!r}）参数 "
            f"{key!r} 须为 str（实际 {type(value).__name__}）——可检查不静默"
        )
    return value


def _require_op(condition: InterruptCondition) -> str:
    value = _require_param(condition, "op")
    if not isinstance(value, str) or value not in _OP_VOCABULARY:
        raise SchedulerError(
            f"条件 {condition.condition_id!r}（kind={condition.kind!r}）参数 "
            f"'op' 须为 {'/'.join(sorted(_OP_VOCABULARY))} 之一（实际 {value!r}）"
            "——可检查不静默"
        )
    return value


def _require_entity_param(condition: InterruptCondition, key: str) -> EntityId:
    value = _require_param(condition, key)
    if not isinstance(value, str):
        raise SchedulerError(
            f"条件 {condition.condition_id!r}（kind={condition.kind!r}）参数 "
            f"{key!r} 须为 EntityId 字符串（实际 {type(value).__name__}）"
            "——可检查不静默"
        )
    return EntityId(value)


def _compare(actual: Any, op: str, expected: Any) -> bool:
    """op 词表比较（eq 不要求同型；序比较类型不符 → 可检查拒绝）。"""
    if op == "eq":
        return actual == expected
    try:
        if op == "gt":
            return actual > expected
        if op == "gte":
            return actual >= expected
        if op == "lt":
            return actual < expected
        return actual <= expected
    except TypeError as exc:
        raise SchedulerError(
            f"op={op!r} 比较类型不符：actual={actual!r} expected={expected!r}"
            "——可检查不静默"
        ) from exc


class _BuiltinResolver:
    """内置 kind 纯求值基类（私有；``evaluate`` 抽象）。"""

    __slots__ = ()

    def evaluate(
        self,
        condition: InterruptCondition,
        view: GuardedWorldState,
        events: Sequence[DomainEvent],
        *,
        tick: int,
    ) -> bool:
        raise NotImplementedError


class _BuiltinEventTypeName(_BuiltinResolver):
    """``event_type``：本刻提交事件流中出现该 event_type 的事件即命中（D-P3-17）。"""

    def evaluate(
        self,
        condition: InterruptCondition,
        view: GuardedWorldState,
        events: Sequence[DomainEvent],
        *,
        tick: int,
    ) -> bool:
        expected = _require_str_param(condition, "event_type")
        return any(str(event.event_type) == expected for event in events)


class _BuiltinWorldVariable(_BuiltinResolver):
    """``world_variable``：世界变量 op 比较；变量缺席 = miss（False）。"""

    def evaluate(
        self,
        condition: InterruptCondition,
        view: GuardedWorldState,
        events: Sequence[DomainEvent],
        *,
        tick: int,
    ) -> bool:
        key = _require_str_param(condition, "key")
        if key not in view.world_variables:
            return False
        return _compare(
            view.world_variables[key],
            _require_op(condition),
            _require_param(condition, "value"),
        )


class _BuiltinEntityComponent(_BuiltinResolver):
    """``entity_component``：field_path 点分嵌套取值后 op 比较；
    实体/组件/路径任一缺失 = miss（False）。"""

    def evaluate(
        self,
        condition: InterruptCondition,
        view: GuardedWorldState,
        events: Sequence[DomainEvent],
        *,
        tick: int,
    ) -> bool:
        entity_id = _require_entity_param(condition, "entity_id")
        component_type = _require_str_param(condition, "component_type")
        field_path = _require_str_param(condition, "field_path")
        entity = view.entities.get(entity_id)
        if entity is None:
            return False
        component = entity.components.get(ComponentTypeId(component_type))
        if component is None:
            return False
        current: Any = component
        for part in field_path.split("."):
            if not isinstance(current, Mapping) or part not in current:
                return False
            current = current[part]
        return _compare(
            current,
            _require_op(condition),
            _require_param(condition, "value"),
        )


class _BuiltinTime(_BuiltinResolver):
    """``time``：当前逻辑刻（显式 ``tick`` 入参，D-P3-21）op 比较；
    op 缺省 ``gte``。"""

    def evaluate(
        self,
        condition: InterruptCondition,
        view: GuardedWorldState,
        events: Sequence[DomainEvent],
        *,
        tick: int,
    ) -> bool:
        target = _require_param(condition, "tick")
        if isinstance(target, bool) or not isinstance(target, int):
            raise SchedulerError(
                f"条件 {condition.condition_id!r}（kind='time'）参数 'tick' "
                f"须为 int（实际 {type(target).__name__}）——可检查不静默"
            )
        op = condition.parameters.get("op", "gte")
        if not isinstance(op, str) or op not in _OP_VOCABULARY:
            raise SchedulerError(
                f"条件 {condition.condition_id!r}（kind='time'）参数 'op' 缺省 "
                f"gte、显式时须为 {'/'.join(sorted(_OP_VOCABULARY))} 之一"
                f"（实际 {op!r}）——可检查不静默"
            )
        return _compare(tick, op, target)


def _build_builtin_registry() -> ConditionResolverRegistry:
    registry = ConditionResolverRegistry(_shared_default=True)
    registry._resolvers.update(
        {
            "event_type": _BuiltinEventTypeName(),
            "world_variable": _BuiltinWorldVariable(),
            "entity_component": _BuiltinEntityComponent(),
            "time": _BuiltinTime(),
        }
    )
    return registry


#: 内置 4 kind 纯实现（共享缺省实例；``register`` 拒绝，E-P3-39④）
BUILTIN_CONDITION_RESOLVERS: Final[ConditionResolverRegistry] = (
    _build_builtin_registry()
)


class BoundaryReport(ContractModel):
    """刻后求值结果（设计文档 §3.7；D-P3-09/10 顺序固定）。

    - ``fired``：``(boundary_id, 被中断实例)`` 对——**注册序**（确定性）；
      ``DecisionBoundary.interrupt=False`` 或命中 actor 无 ACTIVE
      interruptible 行动时实例列表为空（仍记 fired——E-P3-36 record-only
      留痕口径、D-P3-24⑥ 无 INTERRUPTED 背书边缘的一次性暂停亦据此）；
    - ``player_blocking``：是否触发调度暂停（D-P3-10：``boundary.blocking``
      且 actor ∈ ``player_actor_ids``）；
    - ``npc_notices``：非暂停命中（含 NPC 命中与非阻塞玩家命中）→
      ``(boundary_id, actor_id)`` wakeup 建议（§2.4 npc 分支 → scheduler 侧
      ``enqueue_actor_wakeup``，双记录口径 §2.5 尾注；不受
      ``pause_on_player_boundary`` 辖制）。
    """

    tick: int
    fired: list[tuple[str, list[ActionInstanceId]]]
    player_blocking: bool = False
    npc_notices: list[tuple[str, EntityId]] = Field(default_factory=list)


class UnknownConditionError(SchedulerError):
    """未知条件 kind（设计文档 §3.7 / D-P3-16）：kind 非内置且传入 registry
    未注册——于 :func:`evaluate_condition` 抛出（可检查不静默）。"""


def evaluate_condition(
    condition: InterruptCondition,
    view: GuardedWorldState,
    events: Sequence[DomainEvent],
    *,
    tick: int,
    registry: ConditionResolverRegistry,
) -> bool:
    """单条件求值（设计文档 §3.7）。

    内置 kind → :data:`BUILTIN_CONDITION_RESOLVERS`（内置恒在、优先于传入
    registry 的同名注册——内置词表封闭、不可被覆盖）；否则查传入 ``registry``
    （命名注册扩展位）；两者皆无 → :class:`UnknownConditionError`（可检查
    不静默，D-P3-16）。``tick`` = 当前逻辑刻（``evaluate_boundaries`` 已有
    入参、直接透传，D-P3-21）。
    """
    kind = condition.kind
    if kind in CONDITION_KINDS:
        resolver = BUILTIN_CONDITION_RESOLVERS.resolve(kind)
        if resolver is None:  # 防御：内置词表封闭，恒在（构造期已注册）
            raise UnknownConditionError(
                f"内置条件 kind {kind!r} 未在 BUILTIN_CONDITION_RESOLVERS 注册"
                "——内部不变量违例，可检查不静默"
            )
        return resolver.evaluate(condition, view, events, tick=tick)
    resolver = registry.resolve(kind)
    if resolver is None:
        raise UnknownConditionError(
            f"未知条件 kind：{kind!r}（非内置 {'/'.join(sorted(CONDITION_KINDS))}"
            f"、且传入 registry 未注册；condition_id={condition.condition_id!r}）"
            "——可检查不静默（D-P3-16）"
        )
    return resolver.evaluate(condition, view, events, tick=tick)


def evaluate_boundaries(
    view: GuardedWorldState,
    runtime: RuntimeState,
    *,
    tick: int,
    events: Sequence[DomainEvent],
    boundaries: Sequence[DecisionBoundary],
    registry: ConditionResolverRegistry,
    player_actor_ids: frozenset[EntityId],
) -> BoundaryReport:
    """刻后边界求值（设计文档 §2.4 刻后求值块 / §3.7；顺序固定，D-P3-09/10）。

    按注册序逐边界求值（确定性）：

    - ``kind=="scheduled"``：仅 ``due_tick <= tick`` 时参评（刻到即候选；
      队列停靠条目由 scheduler 循环前播种，D-P3-22）；
    - ``kind=="condition"``：经 :func:`evaluate_condition` 求值（tick 显式
      传入，D-P3-21）；
    - 命中 → blocking 判定 = ``boundary.blocking`` 且
      ``boundary.actor_id ∈ player_actor_ids``（D-P3-10）：玩家 blocking
      命中置 ``player_blocking=True``（scheduler 侧按
      ``pause_on_player_boundary`` 决定是否暂停）；其余命中入
      ``npc_notices``（wakeup 建议，不受该标志辖制）；
    - 被中断实例 = 命中 actor 的 ``status==ACTIVE`` 且 ``interruptible`` 的
      行动实例（注册/插入序，确定性）；``boundary.interrupt=False`` → 实例
      列表为空（仍记 fired）。

    纯函数：不迁移任何行动（INTERRUPTED 迁移属 scheduler 侧，经
    ``transition_action`` 唯一迁移入口，Leader 裁定 (B)）、不入队、不改
    ``view`` / ``runtime``。
    """
    fired: list[tuple[str, list[ActionInstanceId]]] = []
    npc_notices: list[tuple[str, EntityId]] = []
    player_blocking = False
    for boundary in boundaries:
        if boundary.kind == "scheduled":
            # 构造期已保证 due_tick 非 None（互斥校验）
            if boundary.due_tick is None or boundary.due_tick > tick:
                continue
        else:
            assert boundary.condition is not None  # 构造期互斥校验保证
            if not evaluate_condition(
                boundary.condition,
                view,
                events,
                tick=tick,
                registry=registry,
            ):
                continue
        if boundary.blocking and boundary.actor_id in player_actor_ids:
            player_blocking = True
        else:
            npc_notices.append((boundary.boundary_id, boundary.actor_id))
        instances: list[ActionInstanceId] = []
        if boundary.interrupt:
            instances = [
                action.instance_id
                for action in runtime.active_actions.values()
                if action.actor_id == boundary.actor_id
                and action.status is ActionLifecycleStatus.ACTIVE
                and action.interruptible
            ]
        fired.append((boundary.boundary_id, instances))
    return BoundaryReport(
        tick=tick,
        fired=fired,
        player_blocking=player_blocking,
        npc_notices=npc_notices,
    )
