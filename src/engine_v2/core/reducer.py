"""engine_v2 core 层 Reducer：authoritative state 的唯一 mutation 机制（P2-T01）。

依据 ``docs/v2/contracts/P2-kernel-pipeline-design.md``（下称"P2 设计规范"）
§2 全量 + ``docs/v2/contracts/P1-core-data-contracts.md``（下称"P1 设计"）
§3.5（reducer-only 三纪律）/ §10.1（条件 C3 写屏障义务）：

- **D-P2-04 结构效果词表**（§2.1）：Kernel 内置 7 个 ``core.*`` **结构性**
  effect type（create/remove entity、set/remove component、set/remove world
  variable、set scenario）——状态机构词汇，不预置任何 RPG 语义取值（Plan §10
  强制约束）；payload pydantic 模型公开导出（全部 ``extra="forbid"`` 继承
  :class:`ContractModel`）供 validation（P2-T04）与测试复用；
- **State mutation API**（§2.2）：7 个与结构效果一一对应的**纯函数**
  ``state_*`` 族（输入 WorldState，输出新 WorldState；self 不变、零别名、
  整体替换语义）——模块处理器（P5+ 语义模块）唯一可用的状态变更 API；
- **EffectHandlerRegistry**（§2.3，D-P2-05）：构造期预注册全部结构效果
  （由 ``state_*`` 派生的内置 handler，不可被覆盖）；未注册 effect type →
  ``resolve`` 返回 None（validation 侧 ``no_handler``；reducer 兜底抛错，
  **不静默推断语义**，Spec §20.2）；
- **应用纯函数**（§2.4）：``apply_committed_effects`` / ``apply_transaction``
  是 P2 唯一的状态变更公共路径（P1 设计 §3.5 纪律 3 预告的
  ``apply_transaction(state, txn) -> WorldState``）；内部经 kernel 私有暂存
  ``_WorkingWorld`` 批量应用（O(状态体积) 而非 O(n×状态)），全程纯函数——
  任何一步抛异常，输入 WorldState 不受影响（原子性的函数式基础，§6.3）；
- **异常族**（§2.5）：``ReducerError`` / ``EffectApplicationError``（携带
  ``sequence`` 与 ``effect_id``）/ ``HandlerConflictError`` /
  ``WriteBarrierError``；
- **写屏障**（§2.6，P1 §10.1 条件 C3 闭合，D-P2-07 三层防御中的层二/层三；
  层一静态 AST 审计归 kernel 测试）：

  1. **运行时逃逸拦截（opt-in）**：``install_write_barrier()`` 在**类级**包裹
     :class:`ContractModel` 的四条逃逸路径（``model_copy`` /
     ``model_construct`` / ``__copy__`` / ``__deepcopy__``）——逐一包裹是
     P1-T07 实测结论（pydantic 2.13 的 ``__copy__`` / ``__deepcopy__`` 经
     ``cls.__new__`` + ``_object_setattr`` 独立实现，**不经过**
     ``model_copy``）；22 个契约模型全部继承 ``ContractModel``，基类一处覆盖
     四个方法即全模型生效。**不修改任何 P1 源文件**（类级包裹而非源码修改，
     §1.4.1）；
  2. **令牌与豁免**：``WriteBarrier`` 上下文管理器 / ``write_barrier_exempt()``
     显式豁免窗口（仅供单元测试内部构建病态数据与诊断；被静态审计视为受控
     例外）共用一个线程局部"reducer 活动"令牌（threading.local，嵌套深度计
     数）；``apply_committed_effects`` / ``apply_transaction`` 内部在
     ``WriteBarrier()`` 上下文内运行——reducer 自身（及其 handler）合法使用
     不受阻；
  3. **guard() 只读门面**（层三，防绕过包装器）：``GuardedWorldState`` 交
     producer/trigger（K2 的运行时兜底，Spec §21.3 触发器求值入参）。
     ``.entities`` / ``.world_variables`` / ``.scenario_state`` 返回基于
     ``MappingProxyType`` 的递归深冻结只读视图（``_FrozenMapping`` /
     ``_freeze_deep``，P2-REMEDIATION B2 容器级泄漏闭合）：任何
     ``__setitem__`` / ``__delitem__`` / ``clear()`` / ``pop()`` 等原地
     修改抛 ``TypeError``，实体组件数据经 ``_GuardedEntityRecord`` /
     ``_GuardedScenarioState`` 门面同为只读深冻结。**G2 补充轮 1**：门面对
     权威状态的承载改为模块私有 token 注册表（``_GUARD_REGISTRY``）——
     实例唯一槽只持 int token，任何实例属性（槽 / ``__dict__`` /
     ``vars()`` / ``object.__getattribute__`` / name-mangling 惯例）不
     承载、不可解析出 wrapped 权威 WorldState 引用（旧
     ``_GuardedWorldState__wrapped`` 改名槽经描述符常规查找可达，已被
     证伪并消除）。**G2 补充轮 2（注册表纯快照化）**：注册表条目不再持
     活权威引用，仅存 ``guard()`` 时刻经 JSON roundtrip 构造的深冻结
     快照（独立副本、与活状态零别名）——对注册表条目的任何原地写只污染
     该条目自己的快照副本，任何时刻解析不到可变活权威状态。防护三层口径：guard 视图（本层，深冻结快照）+ 层二
     写屏障（4 条 pydantic 构造逃逸路径，opt-in 武装）+ 管线层 reducer
     重校验（commit_revision == base_revision + 1 与 L2 引用检查）；
     raw WorldState 嵌套容器本身仍原地可变（P1 D-15 advisory），producer
     只应获得 ``guard()`` 视图。

**import 边界**（P1 设计 §0.3 继承）：本模块只 import 标准库、pydantic 与
同包 ``src.engine_v2``——reducer 不调用 LLM（G2 静态确认之一）；无 IO、无
网络。``_with_*`` / ``_build_*`` 私有构造缝隙**仅限本模块调用**（§1.4.2，
静态审计白名单）。
"""

from __future__ import annotations

import copy
import itertools
import threading
import types
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from typing import Any, Final

from pydantic import Field, JsonValue, TypeAdapter, ValidationError

from src.engine_v2.core.components import (
    ComponentData,
    ComponentRegistry,
    ComponentTypeId,
    parse_component_type_id,
)
from src.engine_v2.core.effects import (
    CommittedEffect,
    EffectTypeId,
    EntityTarget,
    ProposedEffect,
    StateDomainTarget,
)
from src.engine_v2.core.entity import (
    ContractModel,
    EntityRecord,
    EntityView,
    _build_entities,
)
from src.engine_v2.core.ids import EntityId
from src.engine_v2.core.revision import Revision
from src.engine_v2.core.state import CONTRACT_SCHEMA_VERSION, ScenarioState, WorldState
from src.engine_v2.core.transaction import Transaction, TransactionStatus

__all__ = [
    # 结构效果词表（D-P2-04）
    "EFFECT_CREATE_ENTITY",
    "EFFECT_REMOVE_ENTITY",
    "EFFECT_SET_COMPONENT",
    "EFFECT_REMOVE_COMPONENT",
    "EFFECT_SET_WORLD_VARIABLE",
    "EFFECT_REMOVE_WORLD_VARIABLE",
    "EFFECT_SET_SCENARIO_DATA",
    "STRUCTURAL_EFFECT_TYPES",
    # 结构效果 payload 模型（§2.1；extra="forbid" 继承 ContractModel）
    "CreateEntityPayload",
    "EmptyPayload",
    "RemoveWorldVariablePayload",
    "SetScenarioDataPayload",
    "SetWorldVariablePayload",
    # State mutation API（§2.2 纯函数 state_* 族）
    "state_create_entity",
    "state_remove_entity",
    "state_set_component",
    "state_remove_component",
    "state_set_world_variable",
    "state_remove_world_variable",
    "state_set_scenario_state",
    # EffectHandlerRegistry（§2.3，D-P2-05）
    "EffectHandler",
    "EffectHandlerRegistry",
    "default_handler_registry",
    # 应用纯函数（§2.4；P2 唯一的状态变更公共路径）
    "apply_committed_effects",
    "apply_transaction",
    # 异常族（§2.5）
    "ReducerError",
    "EffectApplicationError",
    "HandlerConflictError",
    "WriteBarrierError",
    # 写屏障（§2.6，P1 §10.1 条件 C3 闭合）
    "WriteBarrier",
    "install_write_barrier",
    "uninstall_write_barrier",
    "write_barrier_installed",
    "write_barrier_exempt",
    # guard() 只读门面（§2.6.3）
    "GuardedWorldState",
    "guard",
    "is_guarded",
]

# —— 异常族（§2.5）——


class ReducerError(ValueError):
    """Reducer 错误基类（P2 设计规范 §2.5）。

    派生 ``ValueError``：与 P1 词法/数据校验错误族统一（
    ``ComponentConflictError`` / ``AuthorityError`` 同款纪律）。子类：

    - :class:`EffectApplicationError`：单条 committed effect 应用失败
      （携带 ``sequence`` / ``effect_id`` 定位）；
    - :class:`HandlerConflictError`：handler 注册冲突（D-P2-05）。
    """


class EffectApplicationError(ReducerError):
    """单条 committed effect 应用失败（P2 设计规范 §2.4 步骤 3 / §2.5）。

    携带定位属性（``trace`` 可解释性）：

    - ``sequence``：事务内应用序号（0 起）；
    - ``effect_id``：失败效果的 ``EffectId`` 字符串形态。

    由 :func:`apply_committed_effects` 对 handler / 结构前置条件错误统一
    包装产生；"未注册 effect_type" 的兜底抛错为 :class:`ReducerError`
    本体（批级 fatal，非单条应用失败，§2.4 步骤 3 原文口径）。
    """

    def __init__(self, *, sequence: int, effect_id: str, message: str) -> None:
        super().__init__(f"[seq={sequence} effect_id={effect_id}] {message}")
        self.sequence = sequence
        self.effect_id = effect_id


class HandlerConflictError(ValueError):
    """同 effect_type 重复注册了不同 handler（P2 设计规范 §2.3，D-P2-05）。

    注册语义：同一 handler 对象重复注册幂等；不同 handler → 本异常
    （结构效果内置 handler 于构造期注册且**不可被覆盖**，本错误即其防线）。
    """


class WriteBarrierError(RuntimeError):
    """写屏障拦截错误（P1 §10.1 条件 C3 / P2 设计规范 §2.6）。

    两条抛出路径：

    1. **运行时逃逸拦截**（层二）：屏障武装态下，未经"reducer 活动"令牌
       （``WriteBarrier`` / ``write_barrier_exempt()`` 窗口内）调用
       ``ContractModel`` 的四条逃逸路径（``model_copy`` /
       ``model_construct`` / ``__copy__`` / ``__deepcopy__``）；
    2. **只读门面拦截**（层三）：对 :class:`GuardedWorldState` 的写路径
       （``model_copy`` / ``model_construct`` / ``copy.copy`` /
       ``copy.deepcopy`` / 属性赋值 / 私有缝隙访问）——无条件拦截，
       与令牌无关（producer 侧永远拿不到写路径，K2 运行时兜底）。
    """


# —— 结构效果词表（§2.1，D-P2-04）——

EFFECT_CREATE_ENTITY: Final[EffectTypeId] = EffectTypeId("core.create_entity")
EFFECT_REMOVE_ENTITY: Final[EffectTypeId] = EffectTypeId("core.remove_entity")
EFFECT_SET_COMPONENT: Final[EffectTypeId] = EffectTypeId("core.set_component")
EFFECT_REMOVE_COMPONENT: Final[EffectTypeId] = EffectTypeId("core.remove_component")
EFFECT_SET_WORLD_VARIABLE: Final[EffectTypeId] = EffectTypeId("core.set_world_variable")
EFFECT_REMOVE_WORLD_VARIABLE: Final[EffectTypeId] = EffectTypeId("core.remove_world_variable")
EFFECT_SET_SCENARIO_DATA: Final[EffectTypeId] = EffectTypeId("core.set_scenario_data")

#: Kernel 内置的 7 个结构性 effect type（状态机构词汇，无 RPG 语义取值）。
#: 视为 public contract（值一经使用即稳定，G1 同款纪律，P2 设计规范 §14.1）。
STRUCTURAL_EFFECT_TYPES: Final[frozenset[EffectTypeId]] = frozenset(
    {
        EFFECT_CREATE_ENTITY,
        EFFECT_REMOVE_ENTITY,
        EFFECT_SET_COMPONENT,
        EFFECT_REMOVE_COMPONENT,
        EFFECT_SET_WORLD_VARIABLE,
        EFFECT_REMOVE_WORLD_VARIABLE,
        EFFECT_SET_SCENARIO_DATA,
    }
)


# —— 结构效果 payload 模型（§2.1；全部 extra="forbid" 继承 ContractModel）——


class EmptyPayload(ContractModel):
    """空 payload（``core.remove_entity`` / ``core.remove_component``）。

    无字段；``extra="forbid"`` 使任何多余键非法（结构动词不接受参数）。
    """


class CreateEntityPayload(ContractModel):
    """``core.create_entity`` payload（§2.1）。

    - ``entity_class`` / ``tags``：entity 身份预留维度（P2 authority
      selector 输入，Spec §17.2）；
    - ``components``：新建 entity 初始携带的组件数据（键为组件类型标识
      字符串，应用期经 :func:`parse_component_type_id` 词法校验后转为
      ``ComponentTypeId``）；
    - **``created_revision`` 不得携带**（``extra="forbid"`` 拒绝）——由
      reducer 强制置为 ``commit_revision``（§2.1 前置条件表）。
    """

    entity_class: str | None = None
    tags: list[str] = Field(default_factory=list)
    components: dict[str, ComponentData] = Field(default_factory=dict)


class SetWorldVariablePayload(ContractModel):
    """``core.set_world_variable`` payload（§2.1）。

    键不存在则为新增；存在则**整值替换**（KBC-4 防线：无部分覆写）。
    """

    key: str
    value: JsonValue


class RemoveWorldVariablePayload(ContractModel):
    """``core.remove_world_variable`` payload（§2.1）。前置条件：键存在。"""

    key: str


class SetScenarioDataPayload(ContractModel):
    """``core.set_scenario_data`` payload（§2.1）。

    应用后 ``ScenarioState`` **整体替换**（Kernel 只给信封，剧本语义归
    P9；严格 Optional 语义：``scenario_id`` / ``stage`` 缺省 None）。
    """

    scenario_id: str | None = None
    stage: str | None = None
    data: dict[str, JsonValue] = Field(default_factory=dict)


# —— 目标/ payload 校验助手（私有；错误统一为 ReducerError 语义）——

#: 组件数据（完整 JSON 对象）校验适配器：``core.set_component`` 的 payload
#: 即完整组件数据 dict（§2.1：整体替换，无部分合并）。
_JSON_OBJECT_ADAPTER: Final[TypeAdapter[dict[str, JsonValue]]] = TypeAdapter(
    dict[str, JsonValue]
)


def _require_entity_target(effect: ProposedEffect) -> EntityTarget:
    """结构效果目标必须为 ``EntityTarget``，否则 ``ReducerError``。"""
    target = effect.target
    if not isinstance(target, EntityTarget):
        raise ReducerError(
            f"effect {effect.effect_type} 要求 target 为 EntityTarget，"
            f"实际为 {type(target).__name__}"
        )
    return target


def _require_state_domain_target(effect: ProposedEffect, domain: str) -> StateDomainTarget:
    """结构效果目标必须为指定 domain 的 ``StateDomainTarget``，否则 ``ReducerError``。"""
    target = effect.target
    if not isinstance(target, StateDomainTarget):
        raise ReducerError(
            f"effect {effect.effect_type} 要求 target 为 StateDomainTarget，"
            f"实际为 {type(target).__name__}"
        )
    if target.domain != domain:
        raise ReducerError(
            f"effect {effect.effect_type} 要求 target.domain == {domain!r}，"
            f"实际为 {str(target.domain)!r}"
        )
    return target


def _validate_payload_model(
    model: type[ContractModel], payload: Mapping[str, JsonValue], effect_type: EffectTypeId
) -> ContractModel:
    """按 §2.1 payload 模型校验；``extra="forbid"`` 拒绝多余键。

    pydantic ``ValidationError`` 统一包装为 :class:`ReducerError`（无效
    payload 属结构前置条件违反，§2.1 前置条件表口径）。
    """
    try:
        return model.model_validate(dict(payload))
    except ValidationError as err:
        raise ReducerError(f"无效 payload（effect_type={effect_type}）：{err}") from err


def _validate_component_data(payload: object, effect_type: EffectTypeId) -> ComponentData:
    """``core.set_component`` 的 payload 即完整组件数据：必须为 JSON 对象。"""
    try:
        return _JSON_OBJECT_ADAPTER.validate_python(payload)
    except ValidationError as err:
        raise ReducerError(
            f"无效 payload（effect_type={effect_type}）：组件数据必须为完整 JSON 对象："
            f"{err}"
        ) from err


def _validate_component_schema(
    registry: ComponentRegistry, component_type: ComponentTypeId, data: ComponentData
) -> None:
    """ComponentRegistry 有 schema 时执行 ``validate_payload``（P1 决策 D-8
    校验点 (b) 的兑现，§2.4）。未注册组件类型放行（D-8 边界策略）。

    schema 校验失败（pydantic ``ValidationError``）包装为
    :class:`ReducerError`——应用期失败统一走 ``EffectApplicationError``
    包装路径（§2.4 步骤 3）。
    """
    try:
        registry.validate_payload(component_type, data)
    except ValidationError as err:
        raise ReducerError(
            f"组件 {component_type} 数据不符合已注册 schema：" f"{err}"
        ) from err


# —— State mutation API（§2.2：纯函数 state_* 族）——
#
# 七函数与结构效果一一对应：输入 WorldState，输出新 WorldState；self 不变、
# 零别名（产物经 ``model_dump(mode="json") → model_validate`` 重建，P1 纪律
# 2 入口深拷贝）、整体替换语义（KBC-4 防线）。违反结构前置条件抛
# ReducerError。这组函数是模块处理器（P5+ 语义模块）唯一可用的状态变更 API。


def state_create_entity(
    state: WorldState,
    entity_id: EntityId,
    *,
    entity_class: str | None = None,
    tags: Sequence[str] = (),
    components: Mapping[ComponentTypeId, ComponentData] = {},
    created_revision: Revision,
) -> WorldState:
    """纯函数：新建 entity（§2.2）。前置条件：entity 尚不存在。

    ``created_revision`` 由调用方指定——应用路径上恒为 ``commit_revision``
    （§2.1：reducer 强制置位）。产物经 ``_with_entities`` 缝隙重建（§1.4.2）。
    """
    if state.has_entity(entity_id):
        raise ReducerError(f"core.create_entity 前置条件不满足：entity 已存在：{entity_id}")
    record = EntityRecord(
        entity_id=entity_id,
        entity_class=entity_class,
        tags=list(tags),
        created_revision=created_revision,
        components={ct: dict(data) for ct, data in components.items()},
    )
    return state._with_entities({**state.entities, entity_id: record})


def state_remove_entity(state: WorldState, entity_id: EntityId) -> WorldState:
    """纯函数：删除 entity（§2.2）。前置条件：entity 存在。"""
    if not state.has_entity(entity_id):
        raise ReducerError(f"core.remove_entity 前置条件不满足：entity 不存在：{entity_id}")
    entities = {eid: record for eid, record in state.entities.items() if eid != entity_id}
    return state._with_entities(entities)


def state_set_component(
    state: WorldState, entity_id: EntityId, component_type: ComponentTypeId, data: ComponentData
) -> WorldState:
    """纯函数：设置组件（§2.2）。前置条件：entity 存在。

    **整体替换**，无部分合并（KBC-4 防线）：``data`` 为完整组件数据。
    """
    record = state.entities.get(entity_id)
    if record is None:
        raise ReducerError(f"core.set_component 前置条件不满足：entity 不存在：{entity_id}")
    new_record = record._with_components({**record.components, component_type: data})
    return state._with_entities({**state.entities, entity_id: new_record})


def state_remove_component(
    state: WorldState, entity_id: EntityId, component_type: ComponentTypeId
) -> WorldState:
    """纯函数：移除组件（§2.2）。前置条件：entity 存在且组件已挂载。

    组件未挂载 → 报错，**显式拒绝空操作歧义**（§2.1 前置条件表）。
    """
    record = state.entities.get(entity_id)
    if record is None:
        raise ReducerError(f"core.remove_component 前置条件不满足：entity 不存在：{entity_id}")
    if component_type not in record.components:
        raise ReducerError(
            f"core.remove_component 前置条件不满足：组件未挂载（显式拒绝空操作）："
            f"{entity_id}/{component_type}"
        )
    components = {ct: data for ct, data in record.components.items() if ct != component_type}
    new_record = record._with_components(components)
    return state._with_entities({**state.entities, entity_id: new_record})


def state_set_world_variable(state: WorldState, key: str, value: JsonValue) -> WorldState:
    """纯函数：设置世界变量（§2.2）。无前置条件：键不存在则新增，存在则整值替换。"""
    return state._with_world_variables({**state.world_variables, key: value})


def state_remove_world_variable(state: WorldState, key: str) -> WorldState:
    """纯函数：移除世界变量（§2.2）。前置条件：键存在。"""
    if key not in state.world_variables:
        raise ReducerError(f"core.remove_world_variable 前置条件不满足：键不存在：{key!r}")
    variables = {k: v for k, v in state.world_variables.items() if k != key}
    return state._with_world_variables(variables)


def state_set_scenario_state(state: WorldState, scenario: ScenarioState) -> WorldState:
    """纯函数：整体替换 ScenarioState（§2.2）。无前置条件。"""
    return state._with_scenario_state(scenario)


# —— _WorkingWorld 暂存上下文（§2.4 步骤 3；kernel 私有，不导出）——


class _WorkingWorld:
    """事务批量应用的私有暂存（P2 设计规范 §2.4 步骤 3；**不导出**）。

    持有 ``entities`` / ``world_variables`` / ``scenario_state`` 的**工作副
    本**，按 ``sequence`` 顺序就地应用各效果——O(状态体积) 而非 O(n×状态)；
    最终 :meth:`finalize` 经 ``_build_entities``（拒绝重复 ID，E4）+ 单次
    ``model_validate`` 重建（P1 纪律 2 入口深拷贝）+ ``_with_world_revision``
    置 revision（D-P2-06）组装为新 WorldState。暂存与输入状态零别名
    （``world_variables`` 深拷贝切断嵌套共享；``EntityRecord`` /
    ``ScenarioState`` 为 frozen 模型，替换即新实例）。
    """

    __slots__ = (
        "_base_revision",
        "_commit_revision",
        "_entities",
        "_world_variables",
        "_scenario_state",
    )

    def __init__(self, state: WorldState, commit_revision: Revision) -> None:
        self._base_revision = state.world_revision
        self._commit_revision = commit_revision
        self._entities: dict[EntityId, EntityRecord] = {
            eid: record for eid, record in state.entities.items()
        }
        # 深拷贝切断与输入状态的嵌套 dict 别名（JSON 契约值，copy 安全；
        # 契约模型的逃逸路径拦截不影响纯 dict 的 copy.deepcopy）
        self._world_variables: dict[str, JsonValue] = copy.deepcopy(state.world_variables)
        self._scenario_state: ScenarioState = state.scenario_state

    # —— 查询 ——

    def has_entity(self, entity_id: EntityId) -> bool:
        """entity 是否在工作副本中。"""
        return entity_id in self._entities

    # —— 七操作（与 state_* 同前置条件语义，作用于暂存）——

    def create_entity(
        self,
        entity_id: EntityId,
        *,
        entity_class: str | None,
        tags: Sequence[str],
        components: Mapping[ComponentTypeId, ComponentData],
        created_revision: Revision,
    ) -> None:
        if entity_id in self._entities:
            raise ReducerError(f"core.create_entity 前置条件不满足：entity 已存在：{entity_id}")
        self._entities[entity_id] = EntityRecord(
            entity_id=entity_id,
            entity_class=entity_class,
            tags=list(tags),
            created_revision=created_revision,
            components={ct: dict(data) for ct, data in components.items()},
        )

    def remove_entity(self, entity_id: EntityId) -> None:
        if entity_id not in self._entities:
            raise ReducerError(f"core.remove_entity 前置条件不满足：entity 不存在：{entity_id}")
        del self._entities[entity_id]

    def set_component(
        self, entity_id: EntityId, component_type: ComponentTypeId, data: ComponentData
    ) -> None:
        record = self._entities.get(entity_id)
        if record is None:
            raise ReducerError(f"core.set_component 前置条件不满足：entity 不存在：{entity_id}")
        self._entities[entity_id] = record._with_components(
            {**record.components, component_type: data}
        )

    def remove_component(
        self, entity_id: EntityId, component_type: ComponentTypeId
    ) -> None:
        record = self._entities.get(entity_id)
        if record is None:
            raise ReducerError(
                f"core.remove_component 前置条件不满足：entity 不存在：{entity_id}"
            )
        if component_type not in record.components:
            raise ReducerError(
                f"core.remove_component 前置条件不满足：组件未挂载（显式拒绝空操作）："
                f"{entity_id}/{component_type}"
            )
        components = {ct: data for ct, data in record.components.items() if ct != component_type}
        self._entities[entity_id] = record._with_components(components)

    def set_world_variable(self, key: str, value: JsonValue) -> None:
        self._world_variables[key] = value

    def remove_world_variable(self, key: str) -> None:
        if key not in self._world_variables:
            raise ReducerError(f"core.remove_world_variable 前置条件不满足：键不存在：{key!r}")
        del self._world_variables[key]

    def set_scenario_state(self, scenario: ScenarioState) -> None:
        self._scenario_state = scenario

    # —— 语义 handler 交互（§2.4 步骤 3：语义效果经 WorldState 门面）——

    def current_state(self) -> WorldState:
        """物化当前暂存为 WorldState（保持 base revision）——语义 handler 入参。"""
        return self._assemble(self._base_revision)

    def absorb(self, state: WorldState) -> None:
        """将语义 handler 返回的新 WorldState 回吸收到暂存容器。

        handler 纪律（§2.3 注册方契约）：纯函数、经 ``state_*`` API 产生新
        状态——本方法只搬运其结果容器（frozen 模型整体，零就地修改）。
        """
        self._entities = {eid: record for eid, record in state.entities.items()}
        self._world_variables = copy.deepcopy(state.world_variables)
        self._scenario_state = state.scenario_state

    def finalize(self) -> WorldState:
        """组装最终 WorldState：暂存 → 单次重建 → ``_with_world_revision``（D-P2-06）。"""
        assembled = self._assemble(self._base_revision)
        return assembled._with_world_revision(self._commit_revision)

    def _assemble(self, revision: Revision) -> WorldState:
        """暂存容器 → WorldState（``_build_entities`` 拒绝重复 ID，E4；
        键一致性由 P1 ``model_validator`` 复检，§2.4 步骤 4）。"""
        entities = _build_entities(self._entities.values())
        payload: dict[str, Any] = {
            "schema_version": CONTRACT_SCHEMA_VERSION,
            "world_revision": int(revision),
            "entities": {
                str(eid): record.model_dump(mode="json") for eid, record in entities.items()
            },
            "world_variables": dict(self._world_variables),
            "scenario_state": self._scenario_state.model_dump(mode="json"),
        }
        return WorldState.model_validate(payload)


# —— 结构效果内置 handler（§2.3：由 state_* 派生，target/payload → 参数映射）——

EffectHandler = Callable[[WorldState, ProposedEffect], WorldState]


def _handle_create_entity(state: WorldState, effect: ProposedEffect) -> WorldState:
    target = _require_entity_target(effect)
    payload = _validate_payload_model(CreateEntityPayload, effect.payload, effect.effect_type)
    components: dict[ComponentTypeId, ComponentData] = {}
    for raw_type, data in payload.components.items():
        try:
            component_type = parse_component_type_id(raw_type)
        except ValueError as err:
            raise ReducerError(f"payload 组件类型标识词法非法：{raw_type!r}") from err
        components[component_type] = data
    # created_revision 恒为 state.world_revision.next()：应用路径上暂存保持
    # base revision，next() 即 commit_revision（§2.4 步骤 2 已强制
    # commit_revision == base + 1）。
    return state_create_entity(
        state,
        target.entity_id,
        entity_class=payload.entity_class,
        tags=payload.tags,
        components=components,
        created_revision=state.world_revision.next(),
    )


def _handle_remove_entity(state: WorldState, effect: ProposedEffect) -> WorldState:
    target = _require_entity_target(effect)
    _validate_payload_model(EmptyPayload, effect.payload, effect.effect_type)
    return state_remove_entity(state, target.entity_id)


def _handle_set_component(state: WorldState, effect: ProposedEffect) -> WorldState:
    target = _require_entity_target(effect)
    if target.component_type is None:
        raise ReducerError(f"core.set_component 要求 target.component_type（effect_id={effect.effect_id}）")
    data = _validate_component_data(effect.payload, effect.effect_type)
    # 注：ComponentRegistry 的 schema 校验（D-8 校验点 (b)）在应用层
    # （apply_committed_effects 的 component_registry 参数）执行，§2.4。
    return state_set_component(state, target.entity_id, target.component_type, data)


def _handle_remove_component(state: WorldState, effect: ProposedEffect) -> WorldState:
    target = _require_entity_target(effect)
    if target.component_type is None:
        raise ReducerError(f"core.remove_component 要求 target.component_type（effect_id={effect.effect_id}）")
    _validate_payload_model(EmptyPayload, effect.payload, effect.effect_type)
    return state_remove_component(state, target.entity_id, target.component_type)


def _handle_set_world_variable(state: WorldState, effect: ProposedEffect) -> WorldState:
    _require_state_domain_target(effect, "world_variables")
    payload = _validate_payload_model(SetWorldVariablePayload, effect.payload, effect.effect_type)
    return state_set_world_variable(state, payload.key, payload.value)


def _handle_remove_world_variable(state: WorldState, effect: ProposedEffect) -> WorldState:
    _require_state_domain_target(effect, "world_variables")
    payload = _validate_payload_model(RemoveWorldVariablePayload, effect.payload, effect.effect_type)
    return state_remove_world_variable(state, payload.key)


def _handle_set_scenario_data(state: WorldState, effect: ProposedEffect) -> WorldState:
    _require_state_domain_target(effect, "scenario")
    payload = _validate_payload_model(SetScenarioDataPayload, effect.payload, effect.effect_type)
    scenario = ScenarioState(
        scenario_id=payload.scenario_id, stage=payload.stage, data=payload.data
    )
    return state_set_scenario_state(state, scenario)


#: 内置结构 handler 注册表（注册序 = §2.1 前置条件表行序，确定性）。
_STRUCTURAL_HANDLERS: Final[tuple[tuple[EffectTypeId, EffectHandler], ...]] = (
    (EFFECT_CREATE_ENTITY, _handle_create_entity),
    (EFFECT_REMOVE_ENTITY, _handle_remove_entity),
    (EFFECT_SET_COMPONENT, _handle_set_component),
    (EFFECT_REMOVE_COMPONENT, _handle_remove_component),
    (EFFECT_SET_WORLD_VARIABLE, _handle_set_world_variable),
    (EFFECT_REMOVE_WORLD_VARIABLE, _handle_remove_world_variable),
    (EFFECT_SET_SCENARIO_DATA, _handle_set_scenario_data),
)


# —— EffectHandlerRegistry（§2.3，D-P2-05）——


class EffectHandlerRegistry:
    """语义 effect 的纯函数处理器注册中心（P2 设计规范 §2.3，D-P2-05）。

    - 构造期**预注册全部结构效果**（§2.1 内置 handler，由 ``state_*`` 派
      生），不可被覆盖（重复注册不同 handler 抛
      :class:`HandlerConflictError`）；
    - 语义 effect type 经 :meth:`register` 注册（P5+ 模块）；handler 纪律
      （注册方契约）：纯函数、不调用 LLM/IO、不得绕过 ``state_*`` API 直接
      构造 WorldState 字段、不得静默推断 payload 之外的语义；
    - 未注册 effect type → :meth:`resolve` 返回 None（validation 侧
      ``no_handler`` 拒绝；reducer 兜底抛 :class:`ReducerError`——不推断，
      Spec §20.2）。
    """

    __slots__ = ("_handlers",)

    def __init__(self) -> None:
        # 预注册全部结构效果（注册序确定性：_STRUCTURAL_HANDLERS 元组序）
        self._handlers: dict[EffectTypeId, EffectHandler] = {
            effect_type: handler for effect_type, handler in _STRUCTURAL_HANDLERS
        }

    def register(self, effect_type: EffectTypeId, handler: EffectHandler) -> None:
        """注册语义 handler。同类型重复注册：同一 handler 幂等；不同
        handler → :class:`HandlerConflictError`（结构效果不可被覆盖）。"""
        existing = self._handlers.get(effect_type)
        if existing is not None:
            if existing is not handler:
                raise HandlerConflictError(
                    f"effect_type {effect_type} 已注册 handler（重复注册不同 handler "
                    f"被拒绝，D-P2-05；结构效果内置 handler 不可被覆盖）"
                )
            return
        self._handlers[effect_type] = handler

    def resolve(self, effect_type: EffectTypeId) -> EffectHandler | None:
        """解析 handler；未注册返回 None（不推断，D-P2-05）。"""
        return self._handlers.get(effect_type)

    def has(self, effect_type: EffectTypeId) -> bool:
        """effect_type 是否已注册。"""
        return effect_type in self._handlers

    def effect_types(self) -> tuple[EffectTypeId, ...]:
        """已注册 effect type（注册序，确定性）。"""
        return tuple(self._handlers)


def default_handler_registry() -> EffectHandlerRegistry:
    """默认 handler 注册表：每次新建实例（避免跨测试串扰，§2.3）。"""
    return EffectHandlerRegistry()


# —— 结构效果应用（作用于 _WorkingWorld；与 state_* 同前置条件）——


def _apply_structural(
    working: _WorkingWorld,
    proposed: ProposedEffect,
    component_registry: ComponentRegistry | None,
) -> None:
    """按 §2.1 前置条件表将一条结构效果应用于暂存；违反 → ``ReducerError``。

    ``component_registry`` 非 None 时，``core.set_component`` /
    ``core.create_entity``（其 components 逐项）执行 ``validate_payload``
    （P1 决策 D-8 校验点 (b) 的兑现，§2.4）。
    """
    effect_type = proposed.effect_type
    if effect_type == EFFECT_CREATE_ENTITY:
        target = _require_entity_target(proposed)
        payload = _validate_payload_model(CreateEntityPayload, proposed.payload, effect_type)
        components: dict[ComponentTypeId, ComponentData] = {}
        for raw_type, data in payload.components.items():
            try:
                component_type = parse_component_type_id(raw_type)
            except ValueError as err:
                raise ReducerError(f"payload 组件类型标识词法非法：{raw_type!r}") from err
            if component_registry is not None:
                _validate_component_schema(component_registry, component_type, data)
            components[component_type] = data
        working.create_entity(
            target.entity_id,
            entity_class=payload.entity_class,
            tags=payload.tags,
            components=components,
            created_revision=working._commit_revision,
        )
    elif effect_type == EFFECT_REMOVE_ENTITY:
        target = _require_entity_target(proposed)
        _validate_payload_model(EmptyPayload, proposed.payload, effect_type)
        working.remove_entity(target.entity_id)
    elif effect_type == EFFECT_SET_COMPONENT:
        target = _require_entity_target(proposed)
        if target.component_type is None:
            raise ReducerError(
                f"core.set_component 要求 target.component_type"
                f"（effect_id={proposed.effect_id}）"
            )
        data = _validate_component_data(proposed.payload, effect_type)
        if component_registry is not None:
            _validate_component_schema(component_registry, target.component_type, data)
        working.set_component(target.entity_id, target.component_type, data)
    elif effect_type == EFFECT_REMOVE_COMPONENT:
        target = _require_entity_target(proposed)
        if target.component_type is None:
            raise ReducerError(
                f"core.remove_component 要求 target.component_type"
                f"（effect_id={proposed.effect_id}）"
            )
        _validate_payload_model(EmptyPayload, proposed.payload, effect_type)
        working.remove_component(target.entity_id, target.component_type)
    elif effect_type == EFFECT_SET_WORLD_VARIABLE:
        _require_state_domain_target(proposed, "world_variables")
        payload = _validate_payload_model(SetWorldVariablePayload, proposed.payload, effect_type)
        working.set_world_variable(payload.key, payload.value)
    elif effect_type == EFFECT_REMOVE_WORLD_VARIABLE:
        _require_state_domain_target(proposed, "world_variables")
        payload = _validate_payload_model(RemoveWorldVariablePayload, proposed.payload, effect_type)
        working.remove_world_variable(payload.key)
    else:  # EFFECT_SET_SCENARIO_DATA
        _require_state_domain_target(proposed, "scenario")
        payload = _validate_payload_model(SetScenarioDataPayload, proposed.payload, effect_type)
        working.set_scenario_state(
            ScenarioState(
                scenario_id=payload.scenario_id, stage=payload.stage, data=payload.data
            )
        )


def _apply_semantic(working: _WorkingWorld, proposed: ProposedEffect, handler: EffectHandler) -> None:
    """语义效果：物化暂存 → handler(state, effect) → 回吸收结果（§2.4 步骤 3）。

    handler 纪律违规（返回非 WorldState）→ ``ReducerError``。handler 经
    ``state_*`` API 作用于其收到的 WorldState，本方法不代劳任何状态构造。
    """
    snapshot = working.current_state()
    new_state = handler(snapshot, proposed)
    if not isinstance(new_state, WorldState):
        raise ReducerError(
            f"effect_type {proposed.effect_type} 的 handler 必须返回 WorldState，"
            f"实际返回 {type(new_state).__name__}"
        )
    working.absorb(new_state)


# —— 应用纯函数（§2.4；P2 唯一的状态变更公共路径）——


def apply_committed_effects(
    world_state: WorldState,
    committed_effects: Sequence[CommittedEffect],
    *,
    component_registry: ComponentRegistry | None = None,
    handlers: EffectHandlerRegistry | None = None,
) -> WorldState:
    """纯函数：将已提交效果应用为世界新状态（P2 设计规范 §2.4 步骤 1-5）。

    Args:
        world_state: 输入世界状态（base revision）。**全程不变**（纯函数）。
        committed_effects: 同一事务的全部 CommittedEffect（到达序或任意序——
            按 ``sequence`` 重排后确定性应用）。
        component_registry: 非 None 时，``core.set_component`` /
            ``core.create_entity``（components 逐项）应用时执行
            ``validate_payload``（D-8 校验点 (b)）。
        handlers: handler 注册表；缺省 :func:`default_handler_registry`
            （每次新建，避免跨测试串扰）。

    Returns:
        新 WorldState：``world_revision == commit_revision``（== base + 1，
        D-P2-06）；与输入零别名。

    Raises:
        ReducerError: 防御性复检失败（共享 transaction_id / commit_revision /
            sequence 恰为 0..n-1 / commit_revision == base + 1 / **逐
            effect base_revision 一致性**——每个 ``effect.base_revision``
            必须等于 ``world_state.world_revision``，G2 补充轮 3 闭合直接
            调用与 P8 转录回放路径的暴露）或未注册 effect_type（不推断，
            D-P2-05）。base_revision 不一致时错误信息为单前缀
            ``base_revision_mismatch:`` + 全部不一致项
            ``<effect_id>:base=<实际> expected=<base>``（``"; "`` 连接），
            失败必发生在任何应用之前（输入 ``world_state`` 逐字节不变）。
        EffectApplicationError: 单条 effect 应用失败（结构前置条件 / 无效
            payload / handler 错误），携带 ``sequence`` 与 ``effect_id``。
            **任何异常下输入 ``world_state`` 均不受影响**（原子性的函数式
            基础，§6.3）。
    """
    if not committed_effects:
        # 步骤 1：空列表 → 原样返回（文档化；事务路径永不传空——P1 §5.6
        # 不变量 1 已保证 COMMITTED effects 非空）
        return world_state

    registry = handlers if handlers is not None else default_handler_registry()
    effects = list(committed_effects)

    # 步骤 2：防御性复检（与 Transaction 构造期不变量重复校验——纵深防御，
    # 对齐 C7 检查器的复检哲学）
    transaction_ids = {effect.transaction_id for effect in effects}
    if len(transaction_ids) != 1:
        raise ReducerError(
            "全部 CommittedEffect 必须共享同一 transaction_id："
            f"得到 {[str(t) for t in transaction_ids]}"
        )
    commit_revisions = {effect.commit_revision for effect in effects}
    if len(commit_revisions) != 1:
        raise ReducerError(
            "全部 CommittedEffect 必须共享同一 commit_revision："
            f"得到 {[int(r) for r in commit_revisions]}"
        )
    commit_revision = next(iter(commit_revisions))
    if commit_revision != world_state.world_revision.next():
        raise ReducerError(
            "commit_revision 必须等于 world_revision + 1："
            f"world_revision={int(world_state.world_revision)}，"
            f"commit_revision={int(commit_revision)}"
        )
    sequences = [effect.sequence for effect in effects]
    if sorted(sequences) != list(range(len(effects))):
        raise ReducerError(
            f"effects[*].sequence 必须恰为 0..{len(effects) - 1}：得到 {sequences}"
        )
    # 逐 effect base_revision 一致性复检（G2 补充轮 3，commit 路径步骤 6b 在
    # 本公共入口的镜像）：每个 effect.base_revision 必须等于 base 状态的
    # world_revision。缺本复检时，直接调用本入口（含 P8 转录回放路径）传入
    # base_revision 被篡改（future/stale/任意不一致）的效果批，只要
    # commit_revision == base + 1 且 sequence 合法即被静默应用，产生
    # "已提交效果记录与 base 状态自相矛盾"的世界状态。收集全部不一致项后
    # **单次**抛 ReducerError：本复检在本块全部复检之后、步骤 3 的
    # _WorkingWorld 构造与任何应用之前——失败时输入 world_state 逐字节不
    # 变（原子批级语义，与本块既有复检一致）。
    base_revision = world_state.world_revision
    base_mismatches = [
        f"{committed.effect.effect_id}:base={int(committed.effect.base_revision)}"
        f" expected={int(base_revision)}"
        for committed in effects
        if committed.effect.base_revision != base_revision
    ]
    if base_mismatches:
        raise ReducerError("base_revision_mismatch:" + "; ".join(base_mismatches))
    ordered = sorted(effects, key=lambda effect: effect.sequence)

    # 步骤 3：批量应用（O(状态体积)）——reducer 自身（及其 handler）在
    # WriteBarrier 令牌内运行，屏障武装态下合法使用不受阻（§2.6.2）
    working = _WorkingWorld(world_state, commit_revision)
    with WriteBarrier():
        for sequence, committed in enumerate(ordered):
            proposed = committed.effect
            effect_type = proposed.effect_type
            is_structural = effect_type in STRUCTURAL_EFFECT_TYPES
            handler: EffectHandler | None = None
            if not is_structural:
                handler = registry.resolve(effect_type)
                if handler is None:
                    # 不静默推断语义（D-P2-05 / Spec §20.2）：批级 fatal，
                    # ReducerError 本体（非 EffectApplicationError 包装）
                    raise ReducerError(
                        f"未注册 effect_type: {effect_type}"
                        f"（effect_id={proposed.effect_id}，seq={sequence}）："
                        "reducer 不静默推断语义（D-P2-05）"
                    )
            try:
                if is_structural:
                    _apply_structural(working, proposed, component_registry)
                else:
                    _apply_semantic(working, proposed, handler)
            except EffectApplicationError:
                raise
            except ReducerError as err:
                raise EffectApplicationError(
                    sequence=sequence,
                    effect_id=str(proposed.effect_id),
                    message=str(err),
                ) from err

    # 步骤 4：暂存组装为新 WorldState（_build_entities 拒绝重复 ID；键一致
    # 性由 P1 model_validator 复检），经 _with_world_revision 置 revision
    # （D-P2-06）。步骤 5：全程纯函数——任何异常下输入不受影响。
    return working.finalize()


def apply_transaction(
    state: WorldState,
    txn: Transaction,
    *,
    component_registry: ComponentRegistry | None = None,
    handlers: EffectHandlerRegistry | None = None,
) -> WorldState:
    """纯函数薄封装：``apply_transaction(state, txn) -> WorldState`` 唯一公共
    路径（P1 设计 §3.5 纪律 3 预告；P2 设计规范 §2.4）。

    要求 ``txn.status is COMMITTED``（否则 :class:`ReducerError`——ABORTED
    无 effects 可应用，§5.6 不变量 2），委托
    :func:`apply_committed_effects`（``state, txn.effects, ...``）。
    """
    if txn.status is not TransactionStatus.COMMITTED:
        raise ReducerError(
            f"apply_transaction 仅接受 COMMITTED 事务，得到 {txn.status.value}"
            "（ABORTED 无 effects 可应用，P1 §5.6 不变量 2）"
        )
    return apply_committed_effects(
        state,
        txn.effects,
        component_registry=component_registry,
        handlers=handlers,
    )


# —— 写屏障：层二 运行时逃逸拦截（§2.6.2，P1 §10.1 条件 C3 闭合）——
#
# 机制：install_write_barrier() 在**类级**包裹 ContractModel 的四条逃逸路径
# （model_copy / model_construct / __copy__ / __deepcopy__）。逐一包裹是实测
# 结论而非保守冗余：pydantic 2.13 的 __copy__/__deepcopy__ 经 cls.__new__ +
# _object_setattr 独立实现，不经过 model_copy，只包 model_copy 会漏掉
# copy.copy()/copy.deepcopy()。22 个契约模型全部继承 ContractModel，基类一处
# 覆盖四个方法即全模型生效。包裹层检查线程局部令牌：令牌置位（WriteBarrier
# 活动或 write_barrier_exempt() 内）→ 委托原方法；否则抛 WriteBarrierError。
#
# **opt-in**（不 import 自动安装）：pytest 单进程内若自动武装，P1 既有测试
# 将跨文件受染；武装时机由 kernel 运行时入口（CascadeExecutor.__init__，
# P2-T07）与测试夹具控制。卸载后全局状态复原，P1 测试零影响。


#: 四条逃逸路径（P1-T07 实测：均可绕过全部校验器与 frozen 语义）。
_WRAPPED_METHOD_NAMES: Final[tuple[str, ...]] = (
    "model_copy",
    "model_construct",
    "__copy__",
    "__deepcopy__",
)

#: 线程局部"reducer 活动"令牌（嵌套深度计数；threading.local，§2.6.2）。
_barrier_local = threading.local()

#: 已保存的原方法（name → 未绑定函数；uninstall 时经 delattr 恢复继承）。
_original_methods: dict[str, Any] = {}

#: 屏障武装标志（install 幂等的判据）。
_barrier_installed = False


def _write_scope_depth() -> int:
    """当前线程的令牌深度（0 = 无活动窗口）。"""
    return int(getattr(_barrier_local, "depth", 0))


def _enter_write_scope() -> None:
    _barrier_local.depth = _write_scope_depth() + 1


def _exit_write_scope() -> None:
    _barrier_local.depth = max(0, _write_scope_depth() - 1)


class WriteBarrier:
    """"reducer 活动"令牌上下文管理器（P2 设计规范 §2.6.2；threading.local）。

    上下文内，武装态的 ``ContractModel`` 四条逃逸路径委托原方法——
    ``apply_committed_effects`` / ``apply_transaction`` 内部即在
    ``with WriteBarrier():`` 内运行（reducer 自身合法使用不受阻）。可嵌套
    （深度计数）。
    """

    def __enter__(self) -> WriteBarrier:
        _enter_write_scope()
        return self

    def __exit__(self, *exc_info: object) -> None:
        _exit_write_scope()


@contextmanager
def write_barrier_exempt() -> Iterator[None]:
    """显式豁免窗口（P2 设计规范 §2.6.2）：仅供单元测试内部构建病态数据与
    诊断；被静态审计视为受控例外（测试目录允许）。

    窗口内，武装态的四条逃逸路径委托原方法；窗口外恢复拦截（最小豁免）。
    与 :class:`WriteBarrier` 共用同一线程局部令牌（深度计数，可嵌套）。
    """
    _enter_write_scope()
    try:
        yield
    finally:
        _exit_write_scope()


def _wrap_escape_method(name: str, original_func: Any) -> Any:
    """构造一条逃逸路径的拦截包装（§2.6.2 机制）。

    ``model_construct`` 为 classmethod：包装保持 classmethod 形态并以
    ``cls`` 委托原方法（子类调用时 cls 正确）；其余三条为实例方法。
    """
    if name == "model_construct":

        def _guarded_construct(cls: Any, *args: Any, **kwargs: Any) -> Any:
            if _write_scope_depth() > 0:
                return original_func(cls, *args, **kwargs)
            raise WriteBarrierError(
                f"写屏障拦截：未授权调用 ContractModel.model_construct（{cls.__name__}）——"
                "该路径绕过全部校验器与 frozen 语义（P1 §10.1 条件 C3；"
                "P2 设计规范 §2.6.2）；authoritative state 只能经 reducer 变更"
            )

        return classmethod(_guarded_construct)

    def _guarded(self: Any, *args: Any, **kwargs: Any) -> Any:
        if _write_scope_depth() > 0:
            return original_func(self, *args, **kwargs)
        raise WriteBarrierError(
            f"写屏障拦截：未授权调用 ContractModel.{name}（{type(self).__name__}）——"
            f"该路径绕过全部校验器与 frozen 语义（P1 §10.1 条件 C3；"
            "P2 设计规范 §2.6.2）；authoritative state 只能经 reducer 变更"
        )

    _guarded.__name__ = name
    return _guarded


def install_write_barrier() -> None:
    """武装运行时逃逸拦截（P2 设计规范 §2.6.2；**opt-in，幂等**）。

    在 :class:`ContractModel` **类级**包裹四条逃逸路径（``model_copy`` /
    ``model_construct`` / ``__copy__`` / ``__deepcopy__``）——22 个契约模型
    全部继承 ContractModel，基类一处覆盖即全模型生效（**不修改任何 P1 源
    文件**，§1.4.1）。已武装时再次调用为无操作（kernel 运行时入口
    ``CascadeExecutor.__init__`` 与测试夹具均按幂等语义调用）。
    """
    global _barrier_installed
    if _barrier_installed:
        return
    for name in _WRAPPED_METHOD_NAMES:
        original = getattr(ContractModel, name)
        # model_construct 是 classmethod：getattr 返回绑定描述符，取其
        # __func__ 未绑定函数以便以正确 cls 委托
        original_func = original.__func__ if name == "model_construct" else original
        _original_methods[name] = original_func
        setattr(ContractModel, name, _wrap_escape_method(name, original_func))
    _barrier_installed = True


def uninstall_write_barrier() -> None:
    """恢复原方法（P2 设计规范 §2.6.2；测试夹具用）。

    经 ``delattr`` 移除类级包裹，精确恢复"未武装"的继承态（四个方法本不
    定义在 ContractModel 上，继承自 pydantic BaseModel）。未武装时为无操作。
    卸载后 P1 语义复原（``model_construct`` 等可用），P1 既有测试零影响。
    """
    global _barrier_installed
    if not _barrier_installed:
        return
    for name in _WRAPPED_METHOD_NAMES:
        if name in vars(ContractModel):
            delattr(ContractModel, name)
    _original_methods.clear()
    _barrier_installed = False


def write_barrier_installed() -> bool:
    """屏障当前是否武装（P2 设计规范 §2.6.2 探测入口）。"""
    return _barrier_installed


# —— 写屏障：层三 guard() 只读门面（§2.6.3，防绕过包装器）——


class _FrozenMapping(Mapping):
    """深冻结只读映射（P2-REMEDIATION B2：容器级泄漏闭合）。

    基于 ``types.MappingProxyType`` 构造（内部持有代理，全部读路径委托之；
    CPython 的 mappingproxy 不可被继承，故以组合承载）：

    - **任何原地修改操作一律抛 ``TypeError``**——``__setitem__`` /
      ``__delitem__`` / ``clear`` / ``pop`` / ``popitem`` / ``setdefault`` /
      ``update``（MappingProxyType 本不承载可变方法，直接调用得
      AttributeError；本类补齐并统一错误种类为 TypeError——"只读容器不
      支持原地修改"，而非"方法不存在"）；
    - 构造期经 ``dict(data)`` 浅拷贝切断与入参容器的外层别名（嵌套值已由
      :func:`_freeze_deep` 递归冻结——视图是快照，权威侧任何变化不反射）；
    - ``==`` 语义与 dict/MappingProxyType 互通（内容相等即相等）。
    """

    __slots__ = ("_proxy",)

    def __init__(self, data: Mapping[Any, Any]) -> None:
        self._proxy = types.MappingProxyType(dict(data))

    # —— 只读读路径（委托内部 MappingProxyType）——

    def __getitem__(self, key: Any) -> Any:
        return self._proxy[key]

    def __iter__(self) -> Iterator[Any]:
        return iter(self._proxy)

    def __len__(self) -> int:
        return len(self._proxy)

    def __contains__(self, key: object) -> bool:
        return key in self._proxy

    # —— 原地修改一律 TypeError（B2 错误种类契约）——

    def __setitem__(self, key: Any, value: Any) -> None:
        raise TypeError("只读深冻结映射不支持原地修改（__setitem__；P2-REMEDIATION B2）")

    def __delitem__(self, key: Any) -> None:
        raise TypeError("只读深冻结映射不支持原地修改（__delitem__；P2-REMEDIATION B2）")

    def clear(self) -> None:
        raise TypeError("只读深冻结映射不支持原地修改（clear；P2-REMEDIATION B2）")

    def pop(self, *args: Any) -> Any:
        raise TypeError("只读深冻结映射不支持原地修改（pop；P2-REMEDIATION B2）")

    def popitem(self) -> tuple[Any, Any]:
        raise TypeError("只读深冻结映射不支持原地修改（popitem；P2-REMEDIATION B2）")

    def setdefault(self, *args: Any) -> Any:
        raise TypeError("只读深冻结映射不支持原地修改（setdefault；P2-REMEDIATION B2）")

    def update(self, *args: Any, **kwargs: Any) -> None:
        raise TypeError("只读深冻结映射不支持原地修改（update；P2-REMEDIATION B2）")

    # —— 值相等与表示 ——

    def __eq__(self, other: object) -> bool:
        if isinstance(other, _FrozenMapping):
            return self._proxy == other._proxy
        return self._proxy == other

    __hash__ = None  # 含可变语义容器的值对象不参与哈希（与契约模型同口径）

    # —— 复制出口：产出独立可变快照（零别名，非泄漏面）——
    #
    # producer 侧对读出的 JSON 值做 ``copy``/``deepcopy`` 取工作副本是合法
    # 模式；返回独立 dict 快照（映射代理本体不可 pickle，须显式承接）。

    def __copy__(self) -> dict[Any, Any]:
        return dict(self._proxy)

    def __deepcopy__(self, memo: Any = None) -> dict[Any, Any]:
        return copy.deepcopy(dict(self._proxy), memo)

    def __repr__(self) -> str:
        return f"_FrozenMapping({dict(self._proxy)!r})"


def _freeze_deep(value: Any) -> Any:
    """递归深冻结一个 JSON 值（复用 ``entity._freeze_value`` 模式，§2.6.3）。

    ``dict`` → :class:`_FrozenMapping`（嵌套递归冻结），``list``/``tuple``
    → ``tuple``，标量/None 原样返回。与 ``_freeze_value`` 的差异仅在映射
    载体：_FrozenMapping 对全部原地修改操作统一抛 ``TypeError``
    （P2-REMEDIATION B2 的容器级错误种类契约）。
    """
    if isinstance(value, dict):
        return _FrozenMapping({k: _freeze_deep(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_deep(v) for v in value)
    return value


# —— GuardedWorldState token 注册表（P2-REMEDIATION G2 补充轮 1：缝隙闭合 v2）——
#
# G2 门禁盲审发现：旧 ``_GuardedWorldState__wrapped`` 名称改写槽在属性
# **存在**时经描述符常规查找命中（``__getattr__`` 永不触发）——
# ``getattr(g, "_GuardedWorldState__wrapped")`` /
# ``object.__getattribute__(g, ...)`` 直接返回**活**的权威 WorldState，
# 其嵌套容器（world_variables / 组件 dict / scenario data）可被原地修改，
# revision 不变、无事件/trace——reducer 之外的权威状态写路径未闭合。
#
# 机制（G2 补充轮 1/2）：``guard()`` 每次发放单调递增 int token，
# ``guard()`` 时刻的**深冻结快照**（权威状态的独立副本，经 JSON roundtrip
# 构造、与活状态零别名——注册表条目上解析不出任何活权威状态引用）与其
# 深冻结视图快照（guard() 时一次性构造，快照语义不变）进入模块私有
# 注册表 :data:`_GUARD_REGISTRY`；GuardedWorldState 实例只持 token——任何
# 实例属性（槽 / ``__dict__`` / ``vars()`` / ``object.__getattribute__`` /
# name-mangling 惯例访问）都不承载、也解析不出 wrapped 权威状态引用；
# 注册表条目同理（G2 补充轮 2 纯快照化：轮 1 的 ``state`` 槽曾持**活**
# 权威引用，``token → 注册表 → 活状态 → 原地突变嵌套容器`` 构成无
# revision/事件/trace 的权威写路径；现对注册表条目的任何原地写只污染
# 该条目自己的快照副本，权威状态不受影响——E1 式"零权威引用泄漏"与
# 代码事实一致）。
#
# 生命周期：注册表条目寿命 == guard 实例寿命。实例 ``__del__`` 释放
# （CPython 引用计数下确定；guard 即便参与引用环，Python ≥3.4 的 gc 周期
# 回收仍会触发 ``__del__`` 清出）。级联触发器求值上下文（cascade §7.2）
# 仅在单轮求值期间持有 guard，求值结束 executor 释放引用 → 条目自动回收
# ——cascade 侧无需额外清理点（最小改动方案）。
_GUARD_REGISTRY: dict[int, "_GuardEntry"] = {}
_GUARD_TOKEN_COUNTER = itertools.count(1)


class _GuardEntry:
    """单个 ``guard()`` 的注册表条目：guard() 时刻深冻结快照 + guard() 时构造的深冻结视图快照。

    G2 补充轮 2（纯快照化）：``state`` 槽持**深冻结快照**——权威状态的
    独立副本（经 JSON roundtrip 构造，嵌套容器 ``entities`` / 组件 dict /
    ``world_variables`` / scenario ``data`` 全部为重建的独立对象，与活状态
    **零别名**），不再持活权威 WorldState 引用：对快照的任何原地写只
    污染该条目自己的副本，权威状态的内容 / revision / 事件 / trace 不受
    影响——任何时刻 ``_GUARD_REGISTRY[token]`` 都解析不到可变活权威状态
    （轮 1 的"注册表持活引用"缝隙由此闭合，勘误 R4）。

    视图快照语义不变：guard() 时一次构造、恒有效（被包装状态为 frozen
    契约）；raw 状态嵌套容器若被原地突变，快照不反射（P1 D-15 advisory
    边界，见 :func:`guard`）。
    """

    __slots__ = ("state", "entities_view", "world_variables_view", "scenario_view")

    def __init__(
        self,
        state: WorldState,
        entities_view: _FrozenMapping,
        world_variables_view: Any,
        scenario_view: "_GuardedScenarioState",
    ) -> None:
        self.state = state
        self.entities_view = entities_view
        self.world_variables_view = world_variables_view
        self.scenario_view = scenario_view


def _register_guard(
    state: WorldState,
    entities_view: _FrozenMapping,
    world_variables_view: Any,
    scenario_view: _GuardedScenarioState,
) -> int:
    """注册深冻结快照（guard() 时刻独立副本）+ 视图快照，返回 guard token
    （单调递增、不复用）。

    G2 补充轮 2（注册表纯快照化）：条目 ``state`` 槽存放的不再是活权威
    引用，而是 ``guard()`` 时刻经 JSON roundtrip 构造的深冻结快照——与
    ``state.py`` 的 ``_with_*`` 私有构造缝隙同一机制（``WorldState.
    model_validate(state.model_dump(mode="json"))``）：全部嵌套容器经
    序列化重建为独立对象，与活状态零别名。任何经注册表解析出的快照被
    原地突变时，只污染该条目自己的快照副本；权威状态（内容 / revision /
    事件 / trace）不受影响。委托读取（world_revision / 实体视图 /
    scenario 视图 / model_dump 等）全部自该快照计算，快照与活状态在
    ``guard()`` 时刻值相等，门面读值口径不变。
    """
    token = next(_GUARD_TOKEN_COUNTER)
    snapshot = WorldState.model_validate(state.model_dump(mode="json"))
    _GUARD_REGISTRY[token] = _GuardEntry(
        snapshot, entities_view, world_variables_view, scenario_view
    )
    return token


class _GuardedEntityRecord:
    """EntityRecord 的只读门面（§2.6.3 容器级泄漏防御；P2-REMEDIATION B2/G2 补充轮 1）。

    :class:`GuardedWorldState` 的 ``entities`` 只读视图以本门面逐条承载：

    - ``components`` 为 ``MappingProxyType`` 深冻结视图（复用
      :func:`entity._freeze_value` 模式）——组件数据嵌套 dict 的任何
      ``__setitem__`` / ``__delitem__`` / ``clear()`` / ``pop()`` 原地修改
      抛 ``TypeError``；组件容器本身同为只读代理；
    - ``tags`` 构造期转为 tuple（原 ``list[str]`` 可经 ``append`` 就地突变，
      别名泄漏面一并封堵）；
    - **G2 补充轮 1**：wrapped 活记录槽移除——实例只持构造期拷贝的
      标量字段（``entity_id`` / ``entity_class`` / ``created_revision``）
      + 深冻结视图，任何实例属性都解析不出活 :class:`EntityRecord`
      引用（旧 ``_GuardedEntityRecord__wrapped`` 名称改写槽经描述符
      常规查找可达，返回活记录、其 ``components`` dict 可被原地突变，
      缝隙已闭合）；
    - 属性赋值 / 删除 / 私有缝隙访问一律 :class:`WriteBarrierError`
      （无条件拦截，与层三门面同语义）；不暴露被包装记录对象本身。

    ``__eq__`` 按字段值判定（与 ``EntityRecord`` 值相等互认，视图判等
    口径不变）；不参与哈希（与 pydantic 契约模型同语义）。
    """

    __slots__ = (
        "_GuardedEntityRecord__entity_id",
        "_GuardedEntityRecord__entity_class",
        "_GuardedEntityRecord__created_revision",
        "_GuardedEntityRecord__components",
        "_GuardedEntityRecord__tags",
    )

    def __init__(self, record: EntityRecord) -> None:
        # G2 补充轮 1：只持标量字段拷贝 + 深冻结视图（经 object.__setattr__
        # 绕过本类的 __setattr__ 拦截——构造期唯一一次实例状态写入）
        object.__setattr__(self, "_GuardedEntityRecord__entity_id", record.entity_id)
        object.__setattr__(self, "_GuardedEntityRecord__entity_class", record.entity_class)
        object.__setattr__(
            self, "_GuardedEntityRecord__created_revision", record.created_revision
        )
        object.__setattr__(
            self,
            "_GuardedEntityRecord__components",
            _FrozenMapping(
                {
                    component_type: _freeze_deep(data)
                    for component_type, data in record.components.items()
                }
            ),
        )
        object.__setattr__(self, "_GuardedEntityRecord__tags", tuple(record.tags))

    # —— 只读属性 ——

    @property
    def entity_id(self) -> EntityId:
        return self.__entity_id

    @property
    def entity_class(self) -> str | None:
        return self.__entity_class

    @property
    def tags(self) -> tuple[str, ...]:
        return self.__tags

    @property
    def created_revision(self) -> Revision:
        return self.__created_revision

    @property
    def components(self) -> Mapping[ComponentTypeId, Mapping[str, JsonValue]]:
        """组件数据深冻结只读视图（MappingProxyType，嵌套递归冻结）。"""
        return self.__components

    def model_dump(self, **kwargs: Any) -> Any:
        """序列化出口：以同字段值重建独立记录后委托 ``model_dump``。

        G2 补充轮 1：实例不再持活记录，出口由拷贝的字段值重建——重建记录
        与被包装记录值相等，dump 输出（含任意 kwargs 语义）与原记录一致。
        """
        return EntityRecord(
            entity_id=self.__entity_id,
            entity_class=self.__entity_class,
            tags=list(self.__tags),
            created_revision=self.__created_revision,
            components={ct: dict(data) for ct, data in self.__components.items()},
        ).model_dump(**kwargs)

    # —— 值相等（按字段值判定）与写路径拦截 ——

    def __eq__(self, other: object) -> bool:
        if isinstance(other, _GuardedEntityRecord):
            return (
                self.__entity_id == other._GuardedEntityRecord__entity_id
                and self.__entity_class == other._GuardedEntityRecord__entity_class
                and self.__tags == other._GuardedEntityRecord__tags
                and self.__created_revision
                == other._GuardedEntityRecord__created_revision
                and self.__components == other._GuardedEntityRecord__components
            )
        if isinstance(other, EntityRecord):
            return (
                self.__entity_id == other.entity_id
                and self.__entity_class == other.entity_class
                and self.__tags == tuple(other.tags)
                and self.__created_revision == other.created_revision
                and self.__components == other.components
            )
        return NotImplemented

    __hash__ = None  # 与 EntityRecord 同语义：含可变容器的值对象不参与哈希

    def __setattr__(self, name: str, value: Any) -> None:
        raise WriteBarrierError(
            f"写屏障拦截：只读门面 _GuardedEntityRecord 禁止属性赋值（{name!r}）"
        )

    def __delattr__(self, name: str) -> None:
        raise WriteBarrierError(
            f"写屏障拦截：只读门面 _GuardedEntityRecord 禁止属性删除（{name!r}）"
        )

    def __copy__(self) -> Any:
        raise WriteBarrierError("写屏障拦截：只读门面 _GuardedEntityRecord 禁止 copy.copy")

    def __deepcopy__(self, memo: Any = None) -> Any:
        raise WriteBarrierError("写屏障拦截：只读门面 _GuardedEntityRecord 禁止 copy.deepcopy")

    def __getattr__(self, name: str) -> Any:
        """常规查找失败的兜底：私有缝隙一律拦截（同 GuardedWorldState）。"""
        if name.startswith("_"):
            raise WriteBarrierError(
                f"写屏障拦截：只读门面 _GuardedEntityRecord 禁止私有缝隙访问（{name!r}）"
            )
        raise AttributeError(f"{type(self).__name__!r} object has no attribute {name!r}")

    def __repr__(self) -> str:
        return f"_GuardedEntityRecord(entity_id={self.__entity_id})"


class _GuardedScenarioState:
    """ScenarioState 的只读门面（§2.6.3 容器级泄漏防御；P2-REMEDIATION B2/G2 补充轮 1）。

    pydantic ``frozen=True`` 只阻断字段再赋值——``scenario_state.data`` 的
    可变 dict 原可经 ``data['k'] = v`` 就地突变权威状态。本门面以
    ``MappingProxyType`` 深冻结视图暴露 ``data``（复用
    :func:`entity._freeze_value` 模式），任何 ``__setitem__`` /
    ``__delitem__`` / ``clear()`` / ``pop()`` 抛 ``TypeError``；属性赋值 /
    删除 / 私有缝隙访问一律 :class:`WriteBarrierError`。

    **G2 补充轮 1**：wrapped 活模型槽移除——实例只持构造期拷贝的标量
    字段（``scenario_id`` / ``stage``）+ 深冻结 ``data`` 视图，任何实例
    属性都解析不出活 :class:`ScenarioState` 引用（旧
    ``_GuardedScenarioState__wrapped`` 名称改写槽经描述符常规查找可达，
    返回活模型、其 ``data`` dict 可被原地突变，缝隙已闭合）。

    ``__eq__`` 按字段值判定（与 ``ScenarioState`` 值相等互认）。
    """

    __slots__ = (
        "_GuardedScenarioState__scenario_id",
        "_GuardedScenarioState__stage",
        "_GuardedScenarioState__data",
    )

    def __init__(self, scenario: ScenarioState) -> None:
        # G2 补充轮 1：只持标量字段拷贝 + 深冻结 data 视图
        object.__setattr__(self, "_GuardedScenarioState__scenario_id", scenario.scenario_id)
        object.__setattr__(self, "_GuardedScenarioState__stage", scenario.stage)
        object.__setattr__(self, "_GuardedScenarioState__data", _freeze_deep(scenario.data))

    # —— 只读属性 ——

    @property
    def scenario_id(self) -> str | None:
        return self.__scenario_id

    @property
    def stage(self) -> str | None:
        return self.__stage

    @property
    def data(self) -> Mapping[str, JsonValue]:
        """scenario 数据深冻结只读视图（MappingProxyType，嵌套递归冻结）。"""
        return self.__data

    def model_dump(self, **kwargs: Any) -> Any:
        """序列化出口：以同字段值重建独立模型后委托 ``model_dump``。

        G2 补充轮 1：实例不再持活模型，出口由拷贝的字段值重建——重建模型
        与被包装模型值相等，dump 输出（含任意 kwargs 语义）与原模型一致。
        """
        return ScenarioState(
            scenario_id=self.__scenario_id,
            stage=self.__stage,
            data=dict(self.__data),
        ).model_dump(**kwargs)

    # —— 值相等（按字段值判定）与写路径拦截 ——

    def __eq__(self, other: object) -> bool:
        if isinstance(other, _GuardedScenarioState):
            return (
                self.__scenario_id == other._GuardedScenarioState__scenario_id
                and self.__stage == other._GuardedScenarioState__stage
                and self.__data == other._GuardedScenarioState__data
            )
        if isinstance(other, ScenarioState):
            return (
                self.__scenario_id == other.scenario_id
                and self.__stage == other.stage
                and self.__data == other.data
            )
        return NotImplemented

    __hash__ = None  # 与 ScenarioState 同语义：含可变容器的值对象不参与哈希

    def __setattr__(self, name: str, value: Any) -> None:
        raise WriteBarrierError(
            f"写屏障拦截：只读门面 _GuardedScenarioState 禁止属性赋值（{name!r}）"
        )

    def __delattr__(self, name: str) -> None:
        raise WriteBarrierError(
            f"写屏障拦截：只读门面 _GuardedScenarioState 禁止属性删除（{name!r}）"
        )

    def __copy__(self) -> Any:
        raise WriteBarrierError("写屏障拦截：只读门面 _GuardedScenarioState 禁止 copy.copy")

    def __deepcopy__(self, memo: Any = None) -> Any:
        raise WriteBarrierError("写屏障拦截：只读门面 _GuardedScenarioState 禁止 copy.deepcopy")

    def __getattr__(self, name: str) -> Any:
        """常规查找失败的兜底：私有缝隙一律拦截（同 GuardedWorldState）。"""
        if name.startswith("_"):
            raise WriteBarrierError(
                f"写屏障拦截：只读门面 _GuardedScenarioState 禁止私有缝隙访问（{name!r}）"
            )
        raise AttributeError(f"{type(self).__name__!r} object has no attribute {name!r}")

    def __repr__(self) -> str:
        return f"_GuardedScenarioState(scenario_id={self.__scenario_id})"


def guard(state: WorldState) -> GuardedWorldState:
    """将 WorldState 包装为只读运行时门面（P2 设计规范 §2.6.3；G2 补充轮 1）。

    交 producer/trigger（级联触发器 §7.2 的求值入参即本类型）。门面对外
    只暴露：容器深冻结只读视图（guard() 时一次构造的快照）+ 标量字段只读
    委托 + 序列化出口；任何容器原地修改抛 ``TypeError``，门面属性赋值 /
    copy 路径 / 私有缝隙访问抛 :class:`WriteBarrierError`。

    **G2 补充轮 1/2（name-mangling 槽缝隙 + 注册表活引用缝隙闭合）**：
    实例不再持有任何指向 wrapped 权威状态的槽——旧
    ``_GuardedWorldState__wrapped`` 名称改写槽在属性存在时经描述符常规
    查找命中（``__getattr__`` 永不触发），``getattr(g, ...)`` /
    ``object.__getattribute__(g, ...)`` 返回活 WorldState，其嵌套容器可
    被原地突变（revision 不变、无事件/trace）——reducer 之外的权威状态
    写路径。现 ``guard()`` 发放单调递增 int token，``guard()`` 时刻的
    **深冻结快照**（权威状态的独立副本，经 JSON roundtrip 构造、与活
    状态零别名——G2 补充轮 2：注册表条目不再持活权威引用，对注册表
    条目的任何原地写只污染该条目自己的快照副本）与其深冻结视图快照进入
    模块私有注册表 :data:`_GUARD_REGISTRY`，实例只持 token（任何实例
    属性都不承载、也解析不出权威状态引用；注册表条目同理——任何时刻
    都解析不到可变活权威状态）。

    生命周期：注册表条目寿命 == guard 实例寿命，实例 ``__del__`` 释放
    （CPython 引用计数下确定；引用环场景由 gc 周期回收触发
    ``__del__``）。级联触发器求值上下文仅在单轮求值期间持有 guard，
    求值结束 executor 释放引用 → 条目自动回收，cascade 侧无额外清理点。

    如实边界（防护三层口径）：raw WorldState 嵌套容器本身仍原地可变
    （P1 D-15 advisory）——若 producer 持有 raw WorldState 引用，仍可能
    原地突变嵌套容器（revision 不反映）。防护来自三层：本层 guard 视图
    （深冻结快照 + 零权威引用泄漏——实例槽与注册表条目均不承载活权威
    引用，注册表现仅存 guard() 时刻深冻结快照）、层二写屏障（包裹 4 条
    pydantic 构造逃逸路径，opt-in 武装）、管线层 reducer 重校验
    （commit_revision == base_revision + 1 与 L2 引用检查拦截 stale/伪造
    revision）。producer 只应获得 ``guard()`` 视图。

    Raises:
        TypeError: 入参不是 ``WorldState``。
    """
    if not isinstance(state, WorldState):
        raise TypeError(f"guard 只接受 WorldState，得到 {type(state).__name__}")
    return GuardedWorldState(state)


def is_guarded(obj: object) -> bool:
    """obj 是否为 :class:`GuardedWorldState` 只读门面（§2.6.3 判定谓词）。"""
    return isinstance(obj, GuardedWorldState)


class GuardedWorldState:
    """交 producer/trigger 的只读运行时门面（P2 设计规范 §2.6.3；G2 补充轮 1）。

    - **委托** WorldState 的 4 个只读门面（``entity_view`` /
      ``component_view`` / ``entities_with_component`` / ``has_entity``）+
      ``model_dump`` / ``model_dump_json``（序列化出口）；公共字段
      （``schema_version`` / ``world_revision`` / ``entities`` /
      ``world_variables`` / ``scenario_state``）只读；
    - **容器级深冻结**（P2-REMEDIATION B2）：``entities`` /
      ``world_variables`` / ``scenario_state`` 一律返回基于
      ``MappingProxyType`` 的**递归深冻结只读视图**（复用
      :func:`entity._freeze_value` 模式）——``entities`` 逐条经
      :class:`_GuardedEntityRecord` 承载（组件数据深冻结、tags 转
      tuple），``scenario_state`` 经 :class:`_GuardedScenarioState` 承载
      （``data`` 深冻结）。任何 ``__setitem__`` / ``__delitem__`` /
      ``clear()`` / ``pop()`` 等容器原地修改均抛 ``TypeError``，属性赋值
      等写路径抛 :class:`WriteBarrierError`；
    - **G2 补充轮 1/2（name-mangling 槽缝隙 + 注册表活引用缝隙闭合）**：
      实例不再持有指向 wrapped 权威状态的槽——唯一槽只持 ``guard()``
      发放的 int token，``guard()`` 时刻的深冻结快照（权威状态的独立
      副本，经 JSON roundtrip 构造、与活状态零别名——G2 补充轮 2：
      注册表条目不再持活权威引用）与其深冻结视图快照存于模块私有注册表
      :data:`_GUARD_REGISTRY`；任何实例属性（槽 / ``__dict__`` /
      ``vars()`` / ``object.__getattribute__`` / name-mangling 惯例
      访问）都不承载、也解析不出 wrapped 权威 WorldState 引用，注册表
      条目任何时刻都解析不到可变活权威状态（对条目快照的原地写只污染
      该条目自己的副本）。旧 ``_GuardedWorldState__wrapped`` 名称改写
      槽在属性存在时经描述符常规查找命中（``__getattr__`` 永不触发），
      ``getattr(g, ...)`` 返回活权威状态、其嵌套容器可被原地突变——
      该缝隙已消除；
    - **一律抛 :class:`WriteBarrierError`**：``model_copy`` /
      ``model_construct`` / ``copy.copy`` / ``copy.deepcopy`` /
      ``pickle``（不参与 round-trip）/ 属性赋值 / 属性删除 / 私有缝隙
      访问（``_with_*`` 等）——无条件拦截（与层二令牌无关）：门面不
      提供任何复制或序列化路径；
    - 不继承 ``BaseModel``，不是契约模型，不参与 round-trip。

    深冻结视图快照构造于 guard() 时一次、恒有效（被包装状态为 frozen
    契约；raw 状态嵌套容器若被原地突变，快照不反射——P1 D-15
    advisory，见 :func:`guard`）；判等口径不变——``entities`` /
    ``world_variables`` / ``scenario_state`` 视图与被包装状态对应字段
    ``==`` 相等（委托值相等）。
    """

    # 唯一实例槽：guard() 发放的 int token（P2-REMEDIATION G2 补充轮 1）。
    # token 仅索引模块私有注册表 _GUARD_REGISTRY，本身不承载任何状态引用
    # （name-mangling 惯例访问 ``g._GuardedWorldState__token`` 返回的是 int
    # 令牌，无状态信息可泄漏）；其余私有名一律经 __getattr__ 缝隙拦截。
    __slots__ = ("_GuardedWorldState__token",)

    def __init__(self, state: WorldState) -> None:
        # 容器级深冻结只读视图（P2-REMEDIATION B2）：_FrozenMapping
        # （基于 MappingProxyType）+ _freeze_deep 递归冻结，原地修改统一抛
        # TypeError——guard() 时一次构造、恒有效（快照语义）
        entities_view = _FrozenMapping(
            {
                entity_id: _GuardedEntityRecord(record)
                for entity_id, record in state.entities.items()
            }
        )
        world_variables_view = _freeze_deep(state.world_variables)
        scenario_view = _GuardedScenarioState(state.scenario_state)
        # 实例只持 token（经 object.__setattr__ 绕过本类的 __setattr__
        # 拦截——构造期唯一一次实例状态写入）；_register_guard 内将
        # guard() 时刻深冻结快照（JSON roundtrip 独立副本，G2 补充轮 2：
        # 不存活引用）+ 视图快照入注册表条目
        object.__setattr__(
            self,
            "_GuardedWorldState__token",
            _register_guard(state, entities_view, world_variables_view, scenario_view),
        )

    def __del__(self) -> None:
        """释放注册表条目（条目寿命 == 本实例寿命）。

        CPython 引用计数下确定；guard 参与引用环时由 gc 周期回收触发本
        钩子。防御式：解释器关停期模块 globals 可能已清空（此时条目随
        模块消亡，无需清出）；构造早期失败时槽可能尚未写入。
        """
        registry = globals().get("_GUARD_REGISTRY")
        if registry is None:
            return
        try:
            token = self._GuardedWorldState__token
        except Exception:
            return
        registry.pop(token, None)

    def _entry(self) -> _GuardEntry:
        """token → 注册表条目（常规查找命中；私有缝隙路径不经过此处）。"""
        entry = _GUARD_REGISTRY.get(self._GuardedWorldState__token)
        if entry is None:
            raise WriteBarrierError(
                f"写屏障拦截：GuardedWorldState token {self._GuardedWorldState__token} 已失效（条目已释放）"
            )
        return entry

    # —— 只读门面委托（§2.6.3）——

    def entity_view(self, eid: EntityId) -> EntityView | None:
        """只读门面委托：entity 深冻结视图（entity 不存在返回 None）。"""
        return self._entry().state.entity_view(eid)

    def component_view(
        self, eid: EntityId, ct: ComponentTypeId
    ) -> Mapping[str, JsonValue] | None:
        """只读门面委托：组件数据深冻结视图（缺失返回 None）。"""
        return self._entry().state.component_view(eid, ct)

    def entities_with_component(self, ct: ComponentTypeId) -> tuple[EntityId, ...]:
        """只读门面委托：挂载组件 ct 的 entity id 序列。"""
        return self._entry().state.entities_with_component(ct)

    def has_entity(self, eid: EntityId) -> bool:
        """只读门面委托：entity 是否存在。"""
        return self._entry().state.has_entity(eid)

    # —— 序列化出口 ——

    def model_dump(self, **kwargs: Any) -> Any:
        """序列化出口：委托被包装 WorldState 的 ``model_dump``。"""
        return self._entry().state.model_dump(**kwargs)

    def model_dump_json(self, **kwargs: Any) -> str:
        """序列化出口：委托被包装 WorldState 的 ``model_dump_json``。"""
        return self._entry().state.model_dump_json(**kwargs)

    # —— 公共字段只读访问 ——

    @property
    def schema_version(self) -> int:
        return self._entry().state.schema_version

    @property
    def world_revision(self) -> Revision:
        return self._entry().state.world_revision

    @property
    def entities(self) -> Mapping[EntityId, _GuardedEntityRecord]:
        """只读深冻结视图（P2-REMEDIATION B2）：MappingProxyType 承载
        :class:`_GuardedEntityRecord` 门面——容器 ``__setitem__`` /
        ``__delitem__`` / ``clear()`` / ``pop()`` 与记录内组件数据的任何
        原地修改均被拦截（TypeError / WriteBarrierError）。"""
        return self._entry().entities_view

    @property
    def world_variables(self) -> Mapping[str, JsonValue]:
        """只读深冻结视图（P2-REMEDIATION B2）：``_freeze_deep`` 递归冻结，
        顶层与嵌套 dict 的 ``__setitem__`` / ``__delitem__`` / ``clear()`` /
        ``pop()`` 等原地修改一律抛 TypeError。"""
        return self._entry().world_variables_view

    @property
    def scenario_state(self) -> _GuardedScenarioState:
        """只读深冻结门面（P2-REMEDIATION B2）：``data`` 经 MappingProxyType
        深冻结，字段属性只读——原地修改与属性赋值一律被拦截。"""
        return self._entry().scenario_view

    # —— 写路径拦截（§2.6.3：一律 WriteBarrierError，无条件）——

    def __setattr__(self, name: str, value: Any) -> None:
        raise WriteBarrierError(
            f"写屏障拦截：只读门面 GuardedWorldState 禁止属性赋值（{name!r}）"
        )

    def __delattr__(self, name: str) -> None:
        raise WriteBarrierError(
            f"写屏障拦截：只读门面 GuardedWorldState 禁止属性删除（{name!r}）"
        )

    def model_copy(self, *args: Any, **kwargs: Any) -> Any:
        raise WriteBarrierError("写屏障拦截：只读门面 GuardedWorldState 无 model_copy")

    @classmethod
    def model_construct(cls, *args: Any, **kwargs: Any) -> Any:
        raise WriteBarrierError("写屏障拦截：只读门面 GuardedWorldState 无 model_construct")

    def __copy__(self) -> GuardedWorldState:
        raise WriteBarrierError("写屏障拦截：只读门面 GuardedWorldState 禁止 copy.copy")

    def __deepcopy__(self, memo: Any = None) -> GuardedWorldState:
        raise WriteBarrierError("写屏障拦截：只读门面 GuardedWorldState 禁止 copy.deepcopy")

    def __reduce__(self):
        # G2 补充轮 1：pickle 属"复制路径"族——若允许序列化，同进程
        # round-trip 将产生共享同一 token 的第二实例，其一回收时
        # __del__ 清出条目将致另一实例 token 失效（静默破坏）。门面本就
        # 不参与 round-trip（非契约模型），与 copy/deepcopy 同口径拦截。
        raise WriteBarrierError(
            "写屏障拦截：只读门面 GuardedWorldState 不参与 pickle 序列化（无复制路径）"
        )

    def __getattr__(self, name: str) -> Any:
        """实例/类常规查找失败后的兜底：私有缝隙访问一律拦截。

        常规命中（只读门面 / 序列化出口 / 公共字段 property / 拦截方法）不
        经本方法；落在此处的即门面不承载的属性——下划线前缀（``_with_*``
        等私有缝隙、``__wrapped`` 等）抛 :class:`WriteBarrierError`，其余
        抛 ``AttributeError``。G2 补充轮 1 后不存在任何承载权威状态的
        实例属性——本拦截器只负责错误种类契约，不再承担"藏住槽"的职责
        （槽本身已无状态引用）。
        """
        if name.startswith("_"):
            raise WriteBarrierError(
                f"写屏障拦截：只读门面 GuardedWorldState 禁止私有缝隙访问（{name!r}）"
            )
        raise AttributeError(f"{type(self).__name__!r} object has no attribute {name!r}")

    def __repr__(self) -> str:
        state = self._entry().state
        return (
            f"GuardedWorldState(world_revision={int(state.world_revision)}, "
            f"entities={len(state.entities)})"
        )
