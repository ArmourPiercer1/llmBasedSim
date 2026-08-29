"""engine_v2 core 层 Actor 决策上下文构建：构建输入、13 字段上下文、
ContextProvider 协议与缺省构建期物化实现（P4-T02，§3.8）。

依据 ``docs/v2/contracts/P4-actor-context-space-mode-design.md``（下称"设计文档"）：

- **§3.8（全量，权威）**：本模块 6 个导出符号，逐字——:class:`ContextBuildInput`
  （7 字段）/ :class:`ActorDecisionContext`（13 字段，K7 全可检查）/
  :class:`ContextProvider`（Protocol）/ :class:`DefaultContextProvider`
  （build 六步次序钉死）/ :class:`ActorUnknownError`（CX-INV-1）/
  :class:`ContextInvariantError`（CX-INV-2/3/6 及 scope 结构非法）；
- **CX-INV-1~7（§3.8 L497-505）**：build 构造期强制，逐条落位——CX-INV-1 actor
  不存在 → :class:`ActorUnknownError`（不产半截 context）；CX-INV-2 visible_entities
  并集口径（超集禁止/缺项禁止 + 两侧断言）；CX-INV-3 local 键 ⊆ visible ∧ 每视图
  revision == base（同刻物化）；CX-INV-4 13 字段全值类型（无 GuardedWorldState/
  token/可调用）；CX-INV-5 prompt 仅 ``__init__`` 存储点（build 路径零引用）；
  CX-INV-6 能力门控填充矩阵；CX-INV-7 candidate_actions casefold 排序元组；
- **§3.8 local 范围语义（D-P4-06 钉死，L507-514）**：scope 四形态（None / radius /
  domain / 双键）+ 未知键拒绝 + actor 无 mapping 域零贡献（不崩溃）+
  ``space_registry is None`` → local 恒空（降级不报错）；
- **§3.3 依赖图（L176）+ L184**：context_provider → reducer（GuardedWorldState
  门面，**仅 TYPE_CHECKING**，house 模式）/ entity / actions / action_registry /
  capability / knowledge / space；**不 import scheduler**（tick 经
  ``ContextBuildInput.tick`` 显式传入）；不 import state / provenance / components /
  authority / conflicts；
- **D-P4-05（认识论边界 = 构建期固化）**：build 只经 GuardedWorldState 只读读取，
  全部结果**复制**进冻结 dataclass（EntityView 拷贝 + JsonValue 纯数据），context
  不持有 GuardedWorldState 或其视图引用（跨 tick 漂移防线）；
- **D-P4-06**：local_scope 四形态 + 两兜底（无 mapping 域零贡献 / registry None
  恒空）；
- **D-P4-09**：Memory = ``{"items": list[JsonValue]}`` 原始列表，**无编解码器**
  （context 侧 memory 字段 = 原始 tuple，不解释）；observations / knowledge 经本域
  ``decode_*``（畸形 → pydantic ValidationError，各随本模块纪律）；
- **§3.6 Memory 无编解码器行 + §8.3 导出账本 context_provider 行（6 导出）**。

Import 面（§3.3 依赖图，除注明外全部运行期）：dataclasses(dataclass) / pydantic
(JsonValue) / entity(EntityView) / ids(EntityId) / revision(Revision) /
actions(ActionTypeId) / action_registry(ActionRegistry) /
capability(Capability, CapabilityTable, check_capability) / knowledge
(ObservationRecord, KnowledgeState, 三组件常量, decode_observations,
decode_knowledge) / space(SpaceRegistry, entity_domain_positions)；reducer 的
GuardedWorldState 仅 ``TYPE_CHECKING``（scheduler.py house 模式同款：``from
__future__ import annotations`` 下注解为字符串，运行时零 import）。§3.4 黑名单
全部适用（无 asyncio / random / datetime / time / uuid / json 直接 import / os /
subprocess / 网络栈）。

**深冻结集成缝（guard 载荷 → pydantic 解码）**：``GuardedWorldState.entity_view``
返回的 EntityView 组件载荷为 ``MappingProxyType`` 深冻结视图，pydantic 解码器
（``decode_observations`` / ``decode_knowledge`` / ``entity_domain_positions`` 内的
``decode_spaces``，其 ``position`` 字段 = ``JsonValue``）不接受 MappingProxyType
（"input was not a valid JSON value"）。故本模块以私有 :func:`_thaw_json` 将载荷
深还原为纯 JSON（MappingProxyType→dict / tuple→list / 标量透传）后再委托解码。
此为 guard 深冻结面与 pydantic 解码面的必要适配（偏离披露见报告 deviations）。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from pydantic import JsonValue

from src.engine_v2.core.action_registry import ActionRegistry
from src.engine_v2.core.actions import ActionTypeId
from src.engine_v2.core.capability import Capability, CapabilityTable, check_capability
from src.engine_v2.core.entity import EntityView
from src.engine_v2.core.ids import EntityId
from src.engine_v2.core.knowledge import (
    KNOWLEDGE_COMPONENT,
    MEMORY_COMPONENT,
    OBSERVATIONS_COMPONENT,
    KnowledgeState,
    ObservationRecord,
    decode_knowledge,
    decode_observations,
)
from src.engine_v2.core.revision import Revision
from src.engine_v2.core.space import (
    SPACES_COMPONENT,
    SpaceRegistry,
    InvalidPositionError,
    entity_domain_positions,
)

if TYPE_CHECKING:  # 仅注解用（house 模式，scheduler.py 同款；运行时零 import）
    from src.engine_v2.core.reducer import GuardedWorldState

__all__ = [
    "ContextBuildInput",
    "ActorDecisionContext",
    "ContextProvider",
    "DefaultContextProvider",
    "ActorUnknownError",
    "ContextInvariantError",
]


# —— 私有助手（guard 深冻结面 ↔ pydantic 解码面适配 + local 物化）——


def _thaw_json(value: Any) -> Any:
    """深冻结视图值 → 纯 JSON（pydantic 可校验 / JSON-native）。

    ``MappingProxyType``（及 dict）→ dict、``tuple``（及 list）→ list、标量透传。
    用于把 :func:`reducer.guard` 深冻结组件载荷还原为 :mod:`pydantic` 解码器可接受
    的纯数据（深冻结集成缝的必要适配）。
    """
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw_json(item) for item in value]
    return value


def _domain_positions(view: EntityView) -> dict[str, JsonValue]:
    """EntityView 的 spaces 组件 → ``{domain_id: position}``（载荷序）。

    经 :func:`entity_domain_positions` 委托（设计文档 §3.8 第 4 步指定）。深冻结
    （guard）视图的 spaces 载荷先 :func:`_thaw_json` 还原为纯 JSON，以同身份字段
    的纯视图承载后委托——组件缺失 → ``{}``（不崩溃）。
    """
    payload = view.get_component(SPACES_COMPONENT)
    if payload is None:
        return {}
    plain = EntityView(
        entity_id=view.entity_id,
        entity_class=view.entity_class,
        tags=view.tags,
        revision=view.revision,
        components={SPACES_COMPONENT: _thaw_json(payload)},
    )
    return entity_domain_positions(plain)


def _parse_local_scope(
    scope: JsonValue | None, space_registry: SpaceRegistry
) -> tuple[tuple[str, ...], int]:
    """解析 world.read.local grant scope → ``(domain_ids, radius)``（D-P4-06 四形态）。

    - scope 为 None → 全部注册域（``space_registry.domain_ids()`` 排序序）、半径 1；
    - ``{"radius": r}``（r 为 int ≥ 1，bool 拒绝；r == 0 显式拒绝）→ 全部注册域、
      半径 r；
    - ``{"domain": d}``（d 必须已注册）→ 仅 d、半径 1；``{"domain": d, "radius": r}``
      → 两者；
    - 未知键 / scope 非 None 且非 dict / domain 未注册 / radius 非 int（含 bool）或
      < 1 → :class:`ContextInvariantError`（可检查不静默，fail-fast）。
    """
    if scope is None:
        return space_registry.domain_ids(), 1
    if not isinstance(scope, Mapping):
        raise ContextInvariantError(
            f"CX-INV-6 违反：world.read.local scope 结构非法——必须为 None 或 dict，"
            f"实际 {type(scope).__name__} {scope!r}（D-P4-06）"
        )
    radius = 1
    domain: str | None = None
    for key, value in scope.items():
        if key == "radius":
            if isinstance(value, bool) or not isinstance(value, int):
                raise ContextInvariantError(
                    f"CX-INV-6 违反：scope.radius 必须为 int（bool 拒绝）：{value!r}"
                )
            if value < 1:
                raise ContextInvariantError(
                    f"CX-INV-6 违反：scope.radius 必须 >= 1（r=0 显式拒绝）：{value!r}"
                )
            radius = value
        elif key == "domain":
            if not isinstance(value, str):
                raise ContextInvariantError(f"CX-INV-6 违反：scope.domain 必须为 str：{value!r}")
            domain = value
        else:
            raise ContextInvariantError(
                f"CX-INV-6 违反：scope 未知键 {key!r}（仅允许 radius/domain，D-P4-06）"
            )
    if domain is not None:
        if domain not in space_registry.domain_ids():
            raise ContextInvariantError(
                f"CX-INV-6 违反：scope.domain 未注册空间域 {domain!r}（D-P4-06）"
            )
        domains = (domain,)
    else:
        domains = space_registry.domain_ids()
    return domains, radius


def _materialize_local(
    input: ContextBuildInput,
    self_view: EntityView,
    base_world_revision: Revision,
) -> dict[EntityId, EntityView]:
    """local 域内邻域视图物化（D-P4-06 四形态 + 两兜底；CX-INV-3 自检）。

    未授权 world.read.local 或 ``space_registry is None`` → ``{}``（降级不报错）。
    授权时：C-INV-1 保证 world.read.local 至多 1 条授权，取其 scope 解析为
    (domains, radius)；逐域（排序序）取 actor 位置，actor 无 mapping 域零贡献（不
    崩溃）；逐实体（state 序）判定 ``validate_position 通过 ∧ distance <= radius``
    纳入（含 actor 自身，距离 0 ≤ 半径）。CX-INV-3 自检：每视图 revision 必须 ==
    base_world_revision（同刻物化，跨刻混入即 KBC-3 同型陷阱），否则
    :class:`ContextInvariantError`。
    """
    actor_id = input.actor_id
    table = input.capability_table
    if not check_capability(table, actor_id, Capability.WORLD_READ_LOCAL):
        return {}
    space_registry = input.space_registry
    if space_registry is None:
        return {}

    local_grant = None
    for grant in table.grants_for(actor_id):
        if grant.capability == Capability.WORLD_READ_LOCAL:
            local_grant = grant
            break
    scope = local_grant.scope if local_grant is not None else None
    domains, radius = _parse_local_scope(scope, space_registry)

    actor_positions = _domain_positions(self_view)
    # 预计算全部实体的域位置（每实体 thaw 一次，确定性；state 序）
    all_positions: dict[EntityId, dict[str, JsonValue]] = {
        eid: _domain_positions(input.state.entity_view(eid)) for eid in input.state.entities
    }

    local_entity_views: dict[EntityId, EntityView] = {}
    for domain in domains:
        actor_pos = actor_positions.get(domain)
        if actor_pos is None:
            continue  # actor 在该域无 mapping → 零贡献（不崩溃）
        backend = space_registry.backend(domain)
        for eid in input.state.entities:
            epos = all_positions[eid].get(domain)
            if epos is None:
                continue
            try:
                backend.validate_position(epos)
            except InvalidPositionError:
                continue
            if backend.distance(actor_pos, epos) <= radius:
                local_entity_views[eid] = input.state.entity_view(eid)

    for view in local_entity_views.values():
        if view.revision != base_world_revision:
            raise ContextInvariantError(
                "CX-INV-3 违反：local_entity_views 存在视图 revision != "
                "base_world_revision（跨刻混入，KBC-3 同型陷阱）"
            )
    return local_entity_views


# —— 错误类型（§3.8 L532-536）——


class ActorUnknownError(LookupError):
    """CX-INV-1：actor 不存在于世界（``entity_view`` 返回 None，不产半截 context）。"""


class ContextInvariantError(ValueError):
    """CX-INV-2/3/6 及 world.read.local scope 结构非法（可检查不静默，fail-fast）。"""


# —— 构建输入 / 决策上下文（§3.8 代码块 L447-495，逐字）——


@dataclass(frozen=True)
class ContextBuildInput:
    """构建输入（当刻快照面；全部值传递，无别名风险）。

    - ``actor_id``：为其构建上下文的 actor——决策主体身份的唯一依据
      （CX-INV-1 查找基；唤醒侧值传递传入，ERR-P4-1）；
    - ``state``：**当刻** ``GuardedWorldState`` guard 视图（reducer.guard 产物，
      reducer.py:1590）——只用于 build 期间读取，**绝不**进入结果（CX-INV-4）；
    - ``tick``：逻辑刻（hook 侧 = ``clock.tick``，scheduler.py:1171-1173 传入）；
    - ``wake_reason``：唤醒原因（= boundary_id，G2 移交 3 双记录口径）或 None。
    """

    actor_id: EntityId
    state: "GuardedWorldState"
    registry: ActionRegistry
    capability_table: CapabilityTable
    space_registry: SpaceRegistry | None
    tick: int
    wake_reason: str | None


@dataclass(frozen=True)
class ActorDecisionContext:
    """Actor 决策上下文——**13 字段**（字段级契约，K7 全可检查）。

    - ``actor_id`` / ``tick`` / ``base_world_revision`` / ``wake_reason``：身份与时序锚
      （base = 构建刻 ``state.world_revision``，reducer 委托面）；
    - ``self_view``：actor 自身 EntityView（深冻结，entity.py:173-196）；
    - ``visible_entities``：可见 id 集（CX-INV-2 的并集口径，见下）；
    - ``local_entity_views``：local 域内邻域视图（授权且空间可达才填充）；
    - ``global_entity_views``：全实体视图（**未授权 world.read.global → None**）；
    - ``observations`` / ``knowledge`` / ``memory``：三组件物化（未授权/缺失 →
      缺省空值：``()`` / ``None`` / ``()``）；
    - ``candidate_actions``：要求能力全部满足的注册 action_id（casefold 排序）；
    - ``granted_capabilities``：本 actor 已授权 capability 集（回显，G4-2 断言面）。
    """

    actor_id: EntityId
    tick: int
    base_world_revision: Revision
    wake_reason: str | None
    self_view: EntityView
    visible_entities: frozenset[EntityId]
    local_entity_views: dict[EntityId, EntityView]
    global_entity_views: dict[EntityId, EntityView] | None
    observations: tuple[ObservationRecord, ...]
    knowledge: KnowledgeState | None
    memory: tuple[JsonValue, ...]
    candidate_actions: tuple[ActionTypeId, ...]
    granted_capabilities: frozenset[Capability]


# —— ContextProvider 协议 + 缺省实现（§3.8 L516-530）——


class ContextProvider(Protocol):
    """上下文提供者协议（Spec:874-878：Policy 经 ContextProvider 获得
    能力限定的数据，不读 entire WorldState Spec:876）。"""

    def build(self, input: ContextBuildInput) -> ActorDecisionContext: ...


class DefaultContextProvider:
    """缺省实现：构建期物化（D-P4-05）。

    ``__init__(self, *, prompt: str | None = None)``——prompt 不透明存储
    （CX-INV-5；K4：Prompt 不定义权限，Spec:295/909）。build 六步次序钉死：
    1. self_view（CX-INV-1）；2. 授权集（granted_capabilities 回显）；
    3. 三组件物化（CX-INV-6 矩阵）；4. local/global 物化（D-P4-06）；
    5. 候选动作（CX-INV-7）；6. 可见集并集（CX-INV-2）+ 一致性自检。
    """

    def __init__(self, *, prompt: str | None = None) -> None:
        # CX-INV-5：prompt 仅不透明存储点（build 路径零引用，连读取都不允许；
        # A2 静态扫描口径：prompt 存储只出现于本 __init__ 的单一赋值）。
        self.prompt = prompt

    def build(self, input: ContextBuildInput) -> ActorDecisionContext:
        # 第 1 步：base_world_revision + self_view（CX-INV-1，不产半截 context）
        base_world_revision = input.state.world_revision
        self_view = input.state.entity_view(input.actor_id)
        if self_view is None:
            raise ActorUnknownError(
                f"CX-INV-1 违反：actor {str(input.actor_id)!r} 不存在于世界"
                "（entity_view 返回 None，不产半截 context）"
            )
        actor_id = input.actor_id
        table = input.capability_table

        # 第 2 步：授权集回显（CX-INV-6）
        granted_capabilities = frozenset(
            grant.capability for grant in table.grants_for(actor_id)
        )

        # 第 3 步：三组件物化（CX-INV-6 矩阵；授权判定 = check_capability）
        if check_capability(table, actor_id, Capability.OBSERVATION_READ):
            obs_payload = self_view.get_component(OBSERVATIONS_COMPONENT)
            observations = (
                () if obs_payload is None else decode_observations(_thaw_json(obs_payload))
            )
        else:
            observations = ()

        if check_capability(table, actor_id, Capability.KNOWLEDGE_READ):
            kn_payload = self_view.get_component(KNOWLEDGE_COMPONENT)
            knowledge = (
                None if kn_payload is None else decode_knowledge(_thaw_json(kn_payload))
            )
        else:
            knowledge = None

        if check_capability(table, actor_id, Capability.MEMORY_READ):
            # D-P4-09：memory 无编解码器——载荷 {"items": [...]} 原始列表透传
            memory_payload = self_view.get_component(MEMORY_COMPONENT)
            if memory_payload is None:
                memory = ()
            elif not isinstance(memory_payload, Mapping):
                raise ContextInvariantError(
                    "CX-INV-6 违反：memory 组件在位但载荷非 Mapping"
                    "（D-P4-09 载荷形状 {\"items\": [...]}）"
                )
            elif "items" not in memory_payload:
                raise ContextInvariantError(
                    "CX-INV-6 违反：memory 载荷缺 items 键"
                    "（D-P4-09 载荷形状 {\"items\": [...]}）"
                )
            else:
                thawed_items = _thaw_json(memory_payload["items"])
                if not isinstance(thawed_items, list):
                    raise ContextInvariantError(
                        "CX-INV-6 违反：memory 载荷 items 非 list（D-P4-09）"
                    )
                memory = tuple(thawed_items)
        else:
            memory = ()

        # 第 4 步：global 物化（CX-INV-6：world.read.global；未授权 → None，非 {}）
        if check_capability(table, actor_id, Capability.WORLD_READ_GLOBAL):
            global_entity_views = {
                eid: input.state.entity_view(eid) for eid in input.state.entities
            }
        else:
            global_entity_views = None

        # 第 4 步：local 物化（D-P4-06；未授权 / registry None → {}）
        local_entity_views = _materialize_local(input, self_view, base_world_revision)

        # 第 5 步：候选动作（CX-INV-7：registry.specs 键集满足者，casefold 排序）
        candidate_actions = tuple(
            sorted(
                (aid for aid in input.registry.specs if table.satisfied(actor_id, aid)),
                key=lambda aid: str(aid).casefold(),
            )
        )

        # 第 6 步：可见集并集（CX-INV-2）——四来源：self / observations /
        # knowledge（∩ 世界实存，str → EntityId）/ local 键集
        observed_ids = frozenset(
            eid for record in observations for eid in record.observed_entity_ids
        )
        if knowledge is not None:
            world_keys = set(input.state.entities.keys())
            knowledge_ids = frozenset(
                EntityId(eid) for eid in knowledge.reference_entity_ids() if eid in world_keys
            )
        else:
            knowledge_ids = frozenset()
        local_ids = frozenset(local_entity_views.keys())
        visible_entities = frozenset({actor_id}) | observed_ids | knowledge_ids | local_ids

        # CX-INV-2 一致性自检：从已物化字段重算并集，与 visible_entities 两侧断言
        # 相等（实现漂移防线）
        recomputed = frozenset({actor_id})
        for record in observations:
            recomputed |= frozenset(record.observed_entity_ids)
        if knowledge is not None:
            world_keys = set(input.state.entities.keys())
            recomputed |= frozenset(
                EntityId(eid) for eid in knowledge.reference_entity_ids() if eid in world_keys
            )
        recomputed |= frozenset(local_entity_views.keys())
        if recomputed != visible_entities:
            raise ContextInvariantError(
                "CX-INV-2 违反：visible_entities 与已物化字段重算并集不等（实现漂移）"
            )

        return ActorDecisionContext(
            actor_id=actor_id,
            tick=input.tick,
            base_world_revision=base_world_revision,
            wake_reason=input.wake_reason,
            self_view=self_view,
            visible_entities=visible_entities,
            local_entity_views=local_entity_views,
            global_entity_views=global_entity_views,
            observations=observations,
            knowledge=knowledge,
            memory=memory,
            candidate_actions=candidate_actions,
            granted_capabilities=granted_capabilities,
        )
