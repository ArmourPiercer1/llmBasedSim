"""engine_v2 core 层状态容器（P1-T02）。

依据 ``docs/v2/contracts/P1-core-data-contracts.md``（下称"设计文档"）§4：

- §4.1 :class:`WorldState` —— 权威世界事实（Spec §8.1），六项内容逐项落位：
  entities / components（嵌入 EntityRecord，决策 D-7）/ world variables /
  scenario state / knowledge 承载位（组件；Kernel 无内置，P9 注册）/
  persistent gameplay state（组件 + world_variables）。四个特点的契约保证：
  authoritative（K1 唯一权威表示，ViewState/trace 不得反向写回）/
  serializable（§0.2）/ revisioned（``world_revision``）/ reducer-only
  mutation（§3.5 三纪律）；
- §4.2 :class:`RuntimeState` —— 运行时控制状态（Spec §8.2）：逻辑时钟、
  调度队列、active actions、actor wakeups、gameplay contexts/modes、RNG
  state、pending proposals、生命周期状态，以及 BackendState 引用
  （:class:`BackendStateRef`，决策 D-10，ADR-003）。**占位字段纪律**：
  ``scheduler_queue`` / ``actor_wakeups`` / ``active_modes`` /
  ``mode_context`` 等在 P1 只有数据结构与 round-trip 保证，**无**排序、
  触发、合并语义（Plan P3/P4 实现）；字段命名与 Spec §8.2 清单一一对应，
  P3/P4 不得改名（public contract 冻结）；
- §4.3 snapshot/trace 归属总表：WorldState/RuntimeState 全部字段进
  Snapshot（Spec §30.2）；BackendState 仅 ``backend_refs``（引用 + 能力
  声明）进快照，真实 checkpoint 外置（决策 D-10）；trace 记录"变化"，
  不复制状态本体（``trace.py``，测试口径 S2 的程序化断言对象）；
- **决策 D-5**（revision 归属）：``world_revision`` 只随 WorldState 事务
  提交递增；RuntimeState 变更（调度簿记、proposal 入队）**不**推进它；
  快照一致性由 Snapshot 信封同时固化两个状态达成（T05，§7.3）；
- **决策 D-6**（时间语义）：``logical_tick`` 单一单调计数即 P1 的逻辑时钟；
  Spec §23.1 六层时间的其余层由 P3 在其上定义。**日历时间（day/hour/
  minute）不是 RuntimeState 字段**——它是世界事实，归 WorldState
  （``world_variables`` 或 P9 模块组件），且必须**整体结构化**存取。
  此为对 v1 **KBC-4**（``game_time`` 的 ``day`` 键首回合即丢失）的直接
  规避：v2 中任何"时间推进"只能通过带完整 payload 的 effect 完成
  （payload schema 校验拒绝残缺结构，P2 行为）；RuntimeState 只有单一
  ``logical_tick``，不存在可被部分覆写的复合时钟；
- **决策 D-9**：``WorldState`` 本体**不**内嵌 world_instance_id——保持
  状态实例无关，使 snapshot 可载入新实例/分支实例而无需改写；instance
  身份记录在 Snapshot 信封（T05）与运行时容器上。

§3.5 reducer-only 三纪律在本模块的落位：

1. **零公共写 API**：全部模型 ``frozen=True``（:class:`ContractModel`）
   阻断字段再赋值；:class:`WorldState` 的公共方法只有四个只读门面
   （§4.1），无任何 mutator；
2. **入口深拷贝**：一切外部数据经 ``model_validate`` 进入即重建容器，
   调用方持有的可变 dict 不被别名进状态树（T06 J3 口径）；
3. **唯一变更缝隙**：:class:`WorldState` 提供 ``_with_*`` 前缀的**私有**
   构造助手（供测试与未来 P2 reducer 的纯函数 ``apply_transaction``
   使用，Plan P2-T06），**不**导出为公共 API（不在 ``__all__``）。缝隙
   一律走 ``model_dump(mode="json") → model_validate`` 重建（§6.1 规则 1
   唯一合法出入口），产物与现状态零别名，且为**整体替换**——不提供
   部分覆写（KBC-4 防线）。

:class:`ContractModel` 基类复用 T03 ``entity.py`` 的内联定义（其 docstring
明确"后续 T02/T04 模块可复用或内联"）。

:data:`CONTRACT_SCHEMA_VERSION` 定义于本模块：设计文档 §6.3 将其与
``SNAPSHOT_FORMAT_VERSION`` 一并列于 ``snapshot.py``（T05），但执行次序上
T02 先行（§1.2），``WorldState.schema_version`` / ``RuntimeState.
schema_version`` 需要该常量——T05 的 ``snapshot.py`` 应从本模块 import
复用，避免双源（数值 §6.3 定为 1）。

本模块只 import 标准库、pydantic 与同包 ``src.engine_v2``（§0.3 import
边界白名单），不触碰 v1。
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum
from typing import Final

from pydantic import Field, JsonValue, model_validator

from src.engine_v2.core.actions import ActionProposal, ActiveAction
from src.engine_v2.core.components import ComponentTypeId
from src.engine_v2.core.entity import (
    ContractModel,
    EntityRecord,
    EntityView,
    _entity_ids_with_component,
)
from src.engine_v2.core.ids import ActionInstanceId, EntityId, ScheduledEntryId
from src.engine_v2.core.revision import INITIAL_WORLD_REVISION, Revision

__all__ = [
    "CONTRACT_SCHEMA_VERSION",
    "ScenarioState",
    "RuntimeLifecycle",
    "RngState",
    "ScheduledEvent",
    "ActorWakeup",
    "BackendStateRef",
    "RuntimeState",
    "WorldState",
]

#: P1 契约版本（设计文档 §6.3）：任何 public 字段变更必须 +1 并过 Gate。
#: 定义于本模块的原因见模块 docstring（T05 的 snapshot.py 应复用此常量）。
CONTRACT_SCHEMA_VERSION: Final[int] = 1


class ScenarioState(ContractModel):
    """Spec §8.1 scenario state 的 Kernel 侧最小表达（设计文档 §4.1）。

    Kernel 只给信封，剧本语义由 P9 scenario 模块填充（设计文档 §8 非目标：
    Kernel 不预置 RPG 语义）。严格 Optional 语义（KBC-7）：``scenario_id`` /
    ``stage`` 缺省为 None，与空串不可互换。
    """

    scenario_id: str | None = None
    stage: str | None = None
    data: dict[str, JsonValue] = Field(default_factory=dict)


class RuntimeLifecycle(str, Enum):
    """运行时生命周期状态（设计文档 §4.2；Spec §8.2 runtime lifecycle state）。

    ``STEPPING`` 为开发单步（Spec §22 pause/step 的承载态）。状态迁移行为
    属 Plan P3；P1 只落数据词表。枚举一律 ``class Xxx(str, Enum)``，JSON
    值为字符串字面量（设计文档 §0.1）。
    """

    CREATED = "created"
    RUNNING = "running"
    PAUSED = "paused"
    STEPPING = "stepping"
    STOPPED = "stopped"


class RngState(ContractModel):
    """Spec §8.2 RNG state（设计文档 §4.2）。

    Kernel 不固定算法（Spec §15.4 determinism: seeded 由 backend 声明）；
    ``algorithm`` 如 ``"pcg32"``、``"mt19937"``，由 P3 运行时决定；
    ``state`` 为算法私有状态（seed/counter/…），开放 JSON dict，必须可
    序列化（测试口径：RNG state 可序列化）。
    """

    algorithm: str
    state: dict[str, JsonValue] = Field(default_factory=dict)


class ScheduledEvent(ContractModel):
    """Spec §8.2 scheduler queue 条目（设计文档 §4.2；P1 仅占位数据）。

    调度语义（排序/触发/同刻规则）属 Plan P3。``kind`` 如
    ``"action_checkpoint"`` / ``"wakeup"``（P3 定词表）；``payload`` 如
    ``{"instance_id": "act_…"}``。K7 要求调度状态可检查 → 队列条目必须有
    身份（``entry_id``，``ids.py`` 决策依据）。
    """

    entry_id: ScheduledEntryId
    due_tick: int
    kind: str
    payload: dict[str, JsonValue] = Field(default_factory=dict)


class ActorWakeup(ContractModel):
    """Spec §8.2 actor wakeups 占位（设计文档 §4.2；语义属 Plan P4 Actor/Context）。

    Actor 是世界实体（Spec §12.1），故 ``actor_id`` 为 ``EntityId``。
    """

    actor_id: EntityId
    due_tick: int
    reason: str | None = None


class BackendStateRef(ContractModel):
    """Spec §8.3 BackendState 的 Kernel 侧表达：只存引用与能力声明（决策 D-10）。

    ADR-003 明确 BackendState "不进入 WorldState 快照"：GPU buffer/外部
    solver 等本质上不可 JSON 化。故 Kernel 只存**引用 + 三项能力声明**
    （Spec §8.3 checkpointable/restorable/replayable），真实 checkpoint 由
    PersistenceBackend（Plan P8）外置管理，经 ``checkpoint_ref`` 定位串
    关联（由其解析）；backend 不支持 checkpoint 时 branch/replay 能力降级
    （Spec §8.3/§30.5），数据上表现为 ``checkpointable=False``（缺省）。

    ``backend_id`` 运行时内唯一；``backend_kind`` 如 ``"dynamics"`` /
    ``"space"`` / ``"inference_host"``。
    """

    backend_id: str
    backend_kind: str
    checkpointable: bool = False
    restorable: bool = False
    replayable: bool = False
    checkpoint_ref: str | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class RuntimeState(ContractModel):
    """运行时控制状态（设计文档 §4.2；Spec §8.2）。

    字段与 Spec §8.2 清单一一对应（public contract 冻结，P3/P4 不得改名）：

    - ``logical_tick``：Spec §8.2 logical clock（决策 D-6：单一单调计数；
      Spec §23.1 六层时间中 P1 只固化 world logical time 的最小载体）；
    - ``lifecycle``：runtime lifecycle state（:class:`RuntimeLifecycle`）；
    - ``scheduler_queue``：scheduler queue 占位（P3 语义）；
    - ``active_actions``：active actions（§23.4 字段，T04 ``ActiveAction``；
      K7：全部字段可序列化、可检查，可恢复）；
    - ``actor_wakeups``：actor wakeups 占位（P4 语义）；
    - ``active_modes`` / ``mode_context``：gameplay contexts/modes
      （overlay 语义 Spec §25，Plan P4）；
    - ``rng_state``：RNG state（:class:`RngState`，可空）；
    - ``pending_proposals``：pending proposals（T04 ``ActionProposal``）；
    - ``backend_refs``：BackendState 引用（决策 D-10；进快照的只有引用与
      能力声明，设计文档 §4.3 归属总表）。

    决策 D-5：RuntimeState 变更（调度簿记、proposal 入队）**不**推进
    ``world_revision``。占位字段纪律：P1 无排序/触发/合并语义，无调度语义
    函数被导出（测试口径 S3）。本模型不提供公共 mutator（§3.5 纪律 1），
    P3 的调度语义实现负责以重建构造产生新实例。
    """

    schema_version: int = CONTRACT_SCHEMA_VERSION
    logical_tick: int = 0
    lifecycle: RuntimeLifecycle = RuntimeLifecycle.CREATED
    scheduler_queue: list[ScheduledEvent] = Field(default_factory=list)
    active_actions: dict[ActionInstanceId, ActiveAction] = Field(default_factory=dict)
    actor_wakeups: list[ActorWakeup] = Field(default_factory=list)
    active_modes: list[str] = Field(default_factory=list)
    mode_context: dict[str, JsonValue] = Field(default_factory=dict)
    rng_state: RngState | None = None
    pending_proposals: list[ActionProposal] = Field(default_factory=list)
    backend_refs: dict[str, BackendStateRef] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_active_action_key_consistency(self) -> "RuntimeState":
        """active_actions 键必须与 ActiveAction.instance_id 逐字一致。

        dict 语义不阻止"键与记录身份不一致"的畸形数据；若放行，按键查询与
        记录自身身份（D-3：贯穿 proposal→ActiveAction 的实例 ID）将静默
        分裂——与 KBC-3（双份事实源）同型的陷阱，在数据层拒绝。
        """
        for key, action in self.active_actions.items():
            if action.instance_id != key:
                raise ValueError(
                    "active_actions 键与 ActiveAction.instance_id 不一致："
                    f"键 {str(key)!r} != 记录 {str(action.instance_id)!r}"
                )
        return self


class WorldState(ContractModel):
    """权威世界事实（设计文档 §4.1；Spec §8.1）。

    Spec §8.1 六项内容逐项落位：

    - entities → ``entities``（EntityRecord 的 entity_id/tags/class，§3.1）；
    - components → ``entities[*].components``（§3.4 决策 D-7，entity-centric）；
    - world variables → ``world_variables``（通用键值；Kernel 不预置键名）；
    - scenario state → ``scenario_state``（Kernel 只给信封，语义归 P9）；
    - knowledge / belief components → **组件**（``entities[*].components`` 中
      注册的 knowledge 类组件；Kernel 无内置，P9 knowledge 模块注册组件类型，
      避免"标准 RPG 字段进 Kernel"）；
    - persistent gameplay state → 组件 + ``world_variables``。

    四个特点（Spec §8.1）的契约保证：authoritative（K1：唯一权威表示，
    ViewState/trace 不得反向写回）、serializable（§0.2）、revisioned
    （``world_revision`` 字段）、reducer-only mutation（§3.5 三纪律，
    模块 docstring）。

    决策 D-9：本体**不**内嵌 world_instance_id；EntityId 的 WorldInstance
    内唯一性由构造期 dict 键唯一性（builder 助手显式拒绝重复，E4）+ P2
    reducer 的新增 entity 检查强制。

    数据完整性：``entities`` 键必须与 ``EntityRecord.entity_id`` 逐字一致
    （``_check_entities_key_consistency``），否则门面查询（按键）与视图身份
    （按记录）静默分裂。
    """

    schema_version: int = CONTRACT_SCHEMA_VERSION
    #: Spec §9：每次 COMMITTED transaction commit +1（决策 D-5）
    world_revision: Revision = INITIAL_WORLD_REVISION
    entities: dict[EntityId, EntityRecord] = Field(default_factory=dict)
    #: Spec §8.1 world variables；日历时间等世界事实亦承载于此（决策 D-6）
    world_variables: dict[str, JsonValue] = Field(default_factory=dict)
    scenario_state: ScenarioState = Field(default_factory=ScenarioState)

    @model_validator(mode="after")
    def _check_entities_key_consistency(self) -> "WorldState":
        """entities 键必须与 EntityRecord.entity_id 逐字一致（§3.1/§3.4）。

        重复 EntityId 的显式拒绝由 builder 助手 ``_build_entities``
        （entity.py，测试口径 E4）承担；本校验补上"键与记录身份不一致"
        这一类畸形数据（KBC-3 同型陷阱的数据层防线）。
        """
        for key, record in self.entities.items():
            if record.entity_id != key:
                raise ValueError(
                    f"entities 键与 EntityRecord.entity_id 不一致："
                    f"键 {str(key)!r} != 记录 {str(record.entity_id)!r}"
                )
        return self

    # —— 只读门面（设计文档 §4.1；非字段。不提供任何写方法，§3.5 纪律 1）——

    def entity_view(self, eid: EntityId) -> EntityView | None:
        """返回指定 entity 的只读深冻结视图；entity 不存在返回 None。

        视图携带构造时的 ``world_revision`` 作为有效性判据（KBC-3 防线：
        视图由当前 revision 派生，禁止持有跨 revision 的权威副本）。非法
        引用的"判定"属 P2 validation，P1 只保证查询安全（测试口径 E5）。
        """
        record = self.entities.get(eid)
        if record is None:
            return None
        return EntityView._from_record(record, self.world_revision)

    def component_view(self, eid: EntityId, ct: ComponentTypeId) -> Mapping[str, JsonValue] | None:
        """返回指定 entity 指定组件类型的数据视图；entity 或组件缺失返回 None。"""
        view = self.entity_view(eid)
        if view is None:
            return None
        return view.get_component(ct)

    def entities_with_component(self, ct: ComponentTypeId) -> tuple[EntityId, ...]:
        """返回挂载组件 ``ct`` 的 entity id 序列（顺序 = 插入顺序，确定性）。"""
        return _entity_ids_with_component(self.entities, ct)

    def has_entity(self, eid: EntityId) -> bool:
        """entity 是否存在于本状态。"""
        return eid in self.entities

    # —— 私有构造缝隙（§3.5 纪律 3；供测试与未来 P2 reducer 使用，不导出）——
    #
    # 统一走 model_dump(mode="json") → model_validate 重建（§6.1 规则 1 唯一
    # 合法出入口）：产物与现状态、与调用方输入零别名；整体替换，不提供部分
    # 覆写（KBC-4 防线）。

    def _with_world_revision(self, world_revision: Revision) -> "WorldState":
        """私有构造缝隙：返回替换 world_revision 后的新 WorldState；self 不变。

        语义约束（决策 D-5）：world_revision 只因 COMMITTED transaction 递增；
        本缝隙仅供 P2 reducer（``apply_transaction`` 唯一公共路径）与测试使用。
        """
        payload = self.model_dump(mode="json")
        payload["world_revision"] = int(world_revision)
        return WorldState.model_validate(payload)

    def _with_entities(self, entities: Mapping[EntityId, EntityRecord]) -> "WorldState":
        """私有构造缝隙：返回**整体替换** entities 后的新 WorldState；self 不变。

        传入的每条记录经 ``model_dump(mode="json")`` 展开后由 ``model_validate``
        重建——调用方持有的记录对象不别名进新状态（§3.5 纪律 2）。重复键的
        显式拒绝在传入前由 ``_build_entities``（entity.py）承担；键与记录身份
        不一致由 ``_check_entities_key_consistency`` 拒绝。
        """
        payload = self.model_dump(mode="json")
        payload["entities"] = {
            str(eid): record.model_dump(mode="json") for eid, record in entities.items()
        }
        return WorldState.model_validate(payload)

    def _with_world_variables(self, world_variables: Mapping[str, JsonValue]) -> "WorldState":
        """私有构造缝隙：返回**整体替换** world_variables 后的新 WorldState；self 不变。

        整体替换是 KBC-4 防线的数据形态：日历时间等结构化事实只能以完整
        payload 进出，不存在可丢失个别键的部分覆写缝隙。
        """
        payload = self.model_dump(mode="json")
        payload["world_variables"] = dict(world_variables)
        return WorldState.model_validate(payload)

    def _with_scenario_state(self, scenario_state: ScenarioState) -> "WorldState":
        """私有构造缝隙：返回替换 scenario_state 后的新 WorldState；self 不变。

        传入信封经 ``model_dump(mode="json")`` 展开后重建，不别名进新状态。
        """
        payload = self.model_dump(mode="json")
        payload["scenario_state"] = scenario_state.model_dump(mode="json")
        return WorldState.model_validate(payload)
