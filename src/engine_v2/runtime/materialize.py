"""Runtime T1：ProjectIR → World materialization（runtime closure 冻结契约
§0/§5 表 T1 行；contract ``docs/plans/runtime_closure_contract.md``）。

入口 API（冻结，契约逐字）::

    materialize_world(
        ir: ProjectIR, *, world_instance_id: str,
        domain_id: str = "world", space_backend: SpaceBackend | None = None,
    ) -> WorldMaterialization

职责边界（contract §1）：T1 只产 ``WorldMaterialization``（world / runtime /
spaces / component_registry + 诊断）；executor / policy / dynamics /
authority / producer / trace 由 T9 注入，本模块不触碰。

语义要点（全确定性：零随机 / 零 wall-clock / 零 dict 序外溢）：

- **entities**：locations（仅 WorldSpec 声明时，sorted id）→ characters
  （sorted id）→ player → items（sorted id）。实体键 = 规范型
  ``ent_authoring_<slug>``（core ids.py 内容侧确定性命名约定；L1
  ``bad_id_kind`` 校验面——无前缀 slug 无法通过 K2 管道复检）。每实体 =
  ``EntityRecord(entity_id, entity_class, tags=[], created_revision=
  INITIAL_WORLD_REVISION, components)``。有 position 声明的实体挂 spaces
  组件（SpaceMapping via ``encode_spaces``，domain = domain_id，
  entered_tick=0）。位置投影 = P9 宿主同款口径（移植语义，不引 tests.*
  helper）：grid = 恰含 x/y 两键 int 坐标字典；graph = ``hex_<x>_<y>`` 节点
  串（int 截断）。投影后位置非法（grid 越界 / graph 未声明节点）= 显式
  ``LLMSIM_UNRESOLVED_REF`` 诊断（error，不静默），实体**仍**materialize
  （不挂 spaces 组件）——「能 materialize 的部分仍产出 + 诊断」。
- **NPC authoring 投影**（计划 T1 额外最小要求）：每 CharacterSpec 投影一个
  **read-only** ``character_profile`` 组件（name / personality /
  speech_examples），使 P6 LLMPolicy 的 self_view 可见角色信息。无 mutation
  flow：``authority_domain=None``（不进 authority 授予）+ ``payload_model=
  None``（D-8 不透明存储，零校验钩子）。注册入 component_registry，诊断中
  披露（warning 汇总条）。
- **world_variables**：environment 投影（location = sorted 首 location id、
  无 locations 时 = WorldSpec.name；description / time_of_day / weather /
  temperature_c[声明时]）+ 时钟初始值 ``game_time = {"hour", "minute"}``
  （``ScenarioSpec.game_time``；键名 = presentation view.py / v1 同面）。
  WorldSpec 缺席 = 合法空（D-P5-05）：显式 warning 诊断，时钟仍产出。
- **spaces**：``space_backend`` 给定 → 注册入 ``domain_id``（GraphSpace /
  GridSpace 经 modules.space ``register_standard_space`` 语义面：文法核验 +
  种类一致 + 幂等写入；其余 SpaceBackend 实现 → ``SpatialDomain(
  backend_kind="custom")`` 直接条目——reserved kind 词表内，S-INV-5 不核
  isinstance）。None → WorldSpec 无空间 backend 声明字段（P5 字段封闭集
  事实）→ **缺省 grid** + assumption 诊断（warning，code 闭集内取
  ``LLMSIM_SCHEMA``）；grid 尺寸 = 声明坐标（int 截断）max+1 推导，无声明
  坐标 = 1×1。
- **component_registry**：注册 IR 全部 ComponentSchema（content schema →
  core ``ComponentSchema(component_type, version=1, description,
  payload_model=None)``——字段表不动态建 pydantic 模型，D-8 不透明存储）；
  同 id 重复声明 = 显式 ``LLMSIM_DUPLICATE_ID``（保留首条、跳过、不 raise）。
- **runtime**：``RuntimeState()`` 零初始（logical_tick=0、lifecycle=
  CREATED、其余字段空）。
- **``world_instance_id``**：按契约签名接收，**不写入任何状态字段**（D-9：
  instance 身份记录在 Snapshot 信封 / WorldInstance 容器，非 WorldState
  本体），留待 T9 ``assemble_project`` 组装 ``WorldInstance`` 时消费。

Import 边界（§0.3 白名单同纪律）：stdlib + pydantic + ``src.engine_v2``
（content.schemas / core.* / modules.space）；零 LLM / plugin / tick /
CascadeExecutor / persistence / Web；零 tests.* import。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from pydantic import JsonValue, TypeAdapter

from src.engine_v2.content.schemas import (
    CharacterSpec,
    Diagnostic,
    DiagnosticSeverity,
    PositionSpec,
    ProjectIR,
)
from src.engine_v2.core.components import (
    ComponentRegistry,
    ComponentSchema,
    ComponentTypeId,
    parse_component_type_id,
)
from src.engine_v2.core.entity import EntityRecord
from src.engine_v2.core.ids import EntityId
from src.engine_v2.core.revision import INITIAL_WORLD_REVISION
from src.engine_v2.core.space import (
    SPACES_COMPONENT,
    GraphSpace,
    GridSpace,
    InvalidPositionError,
    SpaceBackend,
    SpaceMapping,
    SpaceRegistry,
    SpatialDomain,
    encode_spaces,
)
from src.engine_v2.core.state import RuntimeState, WorldState
from src.engine_v2.modules.space import register_standard_space

__all__ = [
    "CHARACTER_PROFILE_COMPONENT",
    "WorldMaterialization",
    "materialize_world",
]

#: NPC read-only authoring/profile 组件类型（T1 投影面；P6 self_view 消费）。
#: 无 mutation flow：注册时 ``authority_domain=None`` + ``payload_model=None``。
CHARACTER_PROFILE_COMPONENT: Final[ComponentTypeId] = ComponentTypeId("character_profile")

#: 内容侧确定性命名前缀（core ids.py:68-69 ``ent_authoring_<slug>`` 约定）。
_CANONICAL_PREFIX: Final[str] = "ent_authoring_"


@dataclass(frozen=True)
class WorldMaterialization:
    """T1 产物（contract §1：T9 组装 ``WorldInstance`` 的输入面）。

    - ``world``：权威世界事实（entities + world_variables；D-9 不内嵌
      world_instance_id）；
    - ``runtime``：零初始 RuntimeState（logical_tick=0、CREATED）；
    - ``spaces``：空间域注册表（本 T1 至多注册 ``domain_id`` 一个域；
      多域由 T9/调用方后续经新注册表扩展——SpaceRegistry 零 mutator）；
    - ``component_registry``：IR ComponentSchema + character_profile 注册
      面；
    - ``diagnostics``：显式诊断闭集（assumption / 硬缺 / 未解析引用；
      全部确定性文本，D-P5-15 同纪律）。
    """

    world: WorldState
    runtime: RuntimeState
    spaces: SpaceRegistry
    component_registry: ComponentRegistry
    diagnostics: tuple[Diagnostic, ...]


# —— 私有纯函数助手（确定性；零状态）——


def _canonical(slug: str) -> str:
    """slug → 规范实体 id（core ids.py 内容侧确定性命名约定，逐字移植
    P9 宿主语义）。"""
    return f"{_CANONICAL_PREFIX}{slug}"


def _project_position(backend: SpaceBackend, x: float, y: float) -> object:
    """spec 坐标 → 域内位置（P9 宿主投影口径移植，conftest L248-254 语义）：
    grid = 恰含 x/y 两键 int 坐标字典（core D-P4-10）；graph =
    ``hex_<x>_<y>`` 节点串（int 截断）。"""
    if isinstance(backend, GridSpace):
        return {"x": int(x), "y": int(y)}
    return f"hex_{int(x)}_{int(y)}"


def _declared_positions(ir: ProjectIR) -> tuple[tuple[float, float], ...]:
    """全部声明坐标（player + characters + items；locations 无 position
    字段），确定性序（characters sorted → player → items sorted）。"""
    out: list[tuple[float, float]] = []
    for character in sorted(ir.characters, key=lambda c: c.id):
        if character.position is not None:
            out.append((float(character.position.x), float(character.position.y)))
    if ir.player is not None and ir.player.position is not None:
        out.append((float(ir.player.position.x), float(ir.player.position.y)))
    for item in sorted(ir.items, key=lambda o: o.id):
        if item.position is not None:
            out.append((float(item.position.x), float(item.position.y)))
    return tuple(out)


def _derive_grid_dimensions(
    positions: tuple[tuple[float, float], ...],
) -> tuple[int, int]:
    """缺省 grid 尺寸推导：声明坐标（int 截断）max+1；无声明坐标 = 1×1。"""
    if not positions:
        return 1, 1
    width = max(int(x) for x, _ in positions) + 1
    height = max(int(y) for _, y in positions) + 1
    return max(1, width), max(1, height)


def _register_domain(
    entries: dict[str, tuple[SpatialDomain, SpaceBackend]],
    domain_id: str,
    backend: SpaceBackend,
) -> None:
    """后端注册入宿主条目映射（modules.space register_standard_space 语义
    面；DEV-W6-8 同披露：SpaceRegistry 零 mutator，宿主经条目映射构造）。

    GraphSpace / GridSpace → ``register_standard_space``（文法核验 +
    种类一致 + 幂等写入）；其余 SpaceBackend 实现（协议可替换面，Spec
    :1345）→ ``backend_kind="custom"``（SPATIAL_BACKEND_KINDS reserved
    词表内；S-INV-5 对 reserved kind 不核对 isinstance）直接条目。
    """
    if isinstance(backend, (GraphSpace, GridSpace)):
        register_standard_space(entries, domain_id, backend)
        return
    entries[domain_id] = (
        SpatialDomain(domain_id=domain_id, backend_kind="custom"),
        backend,
    )


def _profile_payload(spec: CharacterSpec) -> dict[str, Any]:
    """CharacterSpec → character_profile 组件载荷（JSON-clean 封闭 3 键）。

    pydantic 模型取出的 dict（``spec.personality``）经
    ``TypeAdapter(dict[str, JsonValue])`` 校验重建 = JSON-clean 深拷贝
    （容器重建零别名；非 JSON 值构造期显式拒绝，不静默入世界组件数据）。
    """
    payload = {
        "name": spec.name,
        "personality": spec.personality,
        "speech_examples": list(spec.speech_examples),
    }
    return _PROFILE_ADAPTER.validate_python(payload)


#: profile 载荷 JSON-clean 深拷贝校验器（pydantic JsonValue 封闭类型集）。
_PROFILE_ADAPTER: Final[TypeAdapter[dict[str, JsonValue]]] = TypeAdapter(dict[str, JsonValue])


def _build_component_registry(ir: ProjectIR, diagnostics: list[Diagnostic]) -> ComponentRegistry:
    """IR 全部 ComponentSchema + character_profile 注册（确定性序：profile
    先、IR 声明序；同 id 重复 = LLMSIM_DUPLICATE_ID 显式、不 raise）。"""
    registry = ComponentRegistry()
    registry.register(
        ComponentSchema(
            component_type=CHARACTER_PROFILE_COMPONENT,
            version=1,
            description="NPC read-only authoring/profile 投影（T1）；无 mutation flow",
            payload_model=None,
            authority_domain=None,
        )
    )
    for schema in ir.component_schemas:
        ct = parse_component_type_id(schema.id)
        if registry.get(ct) is not None:
            diagnostics.append(
                Diagnostic(
                    code="LLMSIM_DUPLICATE_ID",
                    severity=DiagnosticSeverity.ERROR,
                    path=schema.id,
                    message=(f"组件 schema {schema.id!r} 重复声明：保留首条，跳过本条"),
                    refs=(schema.id,),
                )
            )
            continue
        registry.register(
            ComponentSchema(
                component_type=ct,
                version=1,
                description=schema.description,
                payload_model=None,
                authority_domain=None,
            )
        )
    return registry


# —— 公开面 ——


def materialize_world(
    ir: ProjectIR,
    *,
    world_instance_id: str,
    domain_id: str = "world",
    space_backend: SpaceBackend | None = None,
) -> WorldMaterialization:
    """ProjectIR → World materialization（contract §0 冻结签名）。

    Args:
        ir: P5 编译产物（``content.project_ir.build_ir``）；player 为
            ProjectIR 必需字段——若经非常规构造缺失（``None``）= 硬缺，
            显式 error 诊断，player 实体不产出，余部仍 materialize。
        world_instance_id: 契约签名必填；**不写入状态**（D-9），留待 T9
            组装 ``WorldInstance`` 消费。
        domain_id: 本 T1 注册的空间域名（缺省 ``"world"``；文法违例经
            SpatialDomain / register_standard_space 构造期显式拒绝）。
        space_backend: 给定 → 注册入 ``domain_id``；None → 缺省 grid
            （尺寸自声明坐标推导）+ assumption 诊断。

    Returns:
        :class:`WorldMaterialization`（world / runtime / spaces /
        component_registry / diagnostics）。

    失败语义（不静默）：硬缺（player / world 节）与软失败（位置未解析 /
    重复 id / schema 重复声明）全部成显式诊断；能 materialize 的部分仍
    产出。本函数不 raise 内容级异常（K2 / P5-INV-2 同纪律）；仅构造期
    编程错误（domain 文法 / backend 种类不一致）经 core 具名异常显式抛出。
    """
    del world_instance_id  # D-9：留待 T9 WorldInstance 组装消费，不入状态

    diagnostics: list[Diagnostic] = []

    # —— 1. spaces（backend 决定实体投影面，先于 entities）——
    if space_backend is not None:
        backend: SpaceBackend = space_backend
    else:
        width, height = _derive_grid_dimensions(_declared_positions(ir))
        backend = GridSpace(width=width, height=height)
        diagnostics.append(
            Diagnostic(
                code="LLMSIM_SCHEMA",
                severity=DiagnosticSeverity.WARNING,
                path="world",
                message=(
                    "world 节未声明空间 backend kind；缺省 grid 后端"
                    f"（width={width}, height={height}，声明坐标 max+1 推导"
                    "或 1×1）"
                ),
                refs=("assumption", "grid"),
            )
        )
    entries: dict[str, tuple[SpatialDomain, SpaceBackend]] = {}
    _register_domain(entries, domain_id, backend)
    spaces = SpaceRegistry(entries)

    # —— 2. world_variables（environment 投影 + 时钟初始值）——
    world_variables: dict[str, Any] = {}
    if ir.world is not None:
        locations = sorted(ir.world.locations, key=lambda loc: loc.id)
        world_variables["location"] = locations[0].id if locations else ir.world.name
        world_variables["description"] = ir.world.description
        world_variables["time_of_day"] = ir.world.environment.time_of_day
        world_variables["weather"] = ir.world.environment.weather
        if ir.world.environment.temperature_c is not None:
            world_variables["temperature_c"] = ir.world.environment.temperature_c
    else:
        diagnostics.append(
            Diagnostic(
                code="LLMSIM_SCHEMA",
                severity=DiagnosticSeverity.WARNING,
                path="world",
                message="world 节缺失（0 文件）；无 environment/location 投影（合法空）",
                refs=("world",),
            )
        )
    world_variables["game_time"] = {
        "hour": ir.scenario.game_time.hour,
        "minute": ir.scenario.game_time.minute,
    }

    # —— 3. entities（确定性装配序：locations → characters → player → items）——
    records: list[EntityRecord] = []
    first_source: dict[str, str] = {}

    def _add(slug: str, entity_class: str, components: dict) -> None:
        entity_id = EntityId(_canonical(slug))
        if str(entity_id) in first_source:
            diagnostics.append(
                Diagnostic(
                    code="LLMSIM_DUPLICATE_ID",
                    severity=DiagnosticSeverity.ERROR,
                    path=str(entity_id),
                    message=(
                        f"重复实体 id {str(entity_id)!r}"
                        f"（{slug!r}）：保留首个来源 {first_source[str(entity_id)]!r}，"
                        "跳过本条"
                    ),
                    refs=(first_source[str(entity_id)], slug),
                )
            )
            return
        first_source[str(entity_id)] = slug
        records.append(
            EntityRecord(
                entity_id=entity_id,
                entity_class=entity_class,
                tags=[],
                created_revision=INITIAL_WORLD_REVISION,
                components=components,
            )
        )

    def _attach_spaces(slug: str, components: dict, position: PositionSpec | None) -> None:
        if position is None:
            return
        projected = _project_position(backend, float(position.x), float(position.y))
        try:
            backend.validate_position(projected)
        except InvalidPositionError as exc:
            diagnostics.append(
                Diagnostic(
                    code="LLMSIM_UNRESOLVED_REF",
                    severity=DiagnosticSeverity.ERROR,
                    path=_canonical(slug),
                    message=(
                        f"位置声明在域 {domain_id!r} 内未解析："
                        f"投影位置 {projected!r}（实体仍产出，不挂 spaces 组件）"
                    ),
                    refs=(str(exc),),
                )
            )
            return
        components[SPACES_COMPONENT] = encode_spaces(
            (SpaceMapping(domain_id=domain_id, position=projected, entered_tick=0),)
        )

    if ir.world is not None:
        for location in sorted(ir.world.locations, key=lambda loc: loc.id):
            _add(location.id, "location", {})

    profiled: list[str] = []
    for character in sorted(ir.characters, key=lambda c: c.id):
        components: dict = {}
        _attach_spaces(character.id, components, character.position)
        components[CHARACTER_PROFILE_COMPONENT] = _profile_payload(character)
        _add(character.id, "character", components)
        profiled.append(character.id)

    if ir.player is not None:
        components = {}
        _attach_spaces(ir.player.player_id, components, ir.player.position)
        _add(ir.player.player_id, "player", components)
    else:
        diagnostics.append(
            Diagnostic(
                code="LLMSIM_SCHEMA",
                severity=DiagnosticSeverity.ERROR,
                path="game.yaml",
                message="player 缺失（硬缺）；player 实体不产出",
                refs=("player", "missing"),
            )
        )

    for item in sorted(ir.items, key=lambda o: o.id):
        components = {}
        _attach_spaces(item.id, components, item.position)
        _add(item.id, "item", components)

    # —— 4. component_registry（IR schemas + character_profile）——
    component_registry = _build_component_registry(ir, diagnostics)
    if profiled:
        diagnostics.append(
            Diagnostic(
                code="LLMSIM_SCHEMA",
                severity=DiagnosticSeverity.WARNING,
                path="character_profile",
                message=(
                    "已投影 read-only 组件 character_profile（无 mutation flow）："
                    f"{len(profiled)} 角色"
                ),
                refs=tuple(sorted(profiled)),
            )
        )

    # —— 5. world / runtime（零初始）——
    world = WorldState(
        entities={record.entity_id: record for record in records},
        world_variables=world_variables,
    )
    runtime = RuntimeState()

    return WorldMaterialization(
        world=world,
        runtime=runtime,
        spaces=spaces,
        component_registry=component_registry,
        diagnostics=tuple(diagnostics),
    )
