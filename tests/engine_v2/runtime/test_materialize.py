"""Runtime T1 materialize 测试（contract §0/§5 T1 行）。

Gate 覆盖：

1. 两个既有 P9 fixture（``tests/fixtures/v2_project_galgame`` /
   ``v2_project_tactical``）可 materialize——经 ``content.loader.load_project``
   + ``content.project_ir.build_ir`` 得 ProjectIR（fixture 只读，零修改）；
   tactical 另覆盖显式 backend 路径（hex GraphSpace，P9 宿主同构造口径）；
2. 无 tests.* import（src 侧机械守卫）；
3. 同 IR 双构造 world 序列化一致（core.serialization.dump_json 两次输出
   相等）。

另覆盖语义面：spaces 组件投影 / world_variables 环境+时钟投影 /
character_profile 只读组件 / component_registry 注册 / RuntimeState 零
初始 / 失败语义（world 节缺失 / player 硬缺 / 位置未解析 / 实体 id 重复 /
组件 schema 重复）。
"""

from __future__ import annotations

import json
from dataclasses import fields, is_dataclass
from pathlib import Path

import pytest

from src.engine_v2.content.loader import load_project
from src.engine_v2.content.project_ir import build_ir
from src.engine_v2.content.schemas import (
    ComponentField,
    ComponentType,
    Diagnostic,
    DiagnosticSeverity,
    PlayerSpec,
    ProjectIR,
    ProjectManifest,
    ScenarioSpec,
    ScenarioTime,
)
from src.engine_v2.content.schemas import ComponentSchema as ContentComponentSchema
from src.engine_v2.core.components import ComponentTypeId
from src.engine_v2.core.ids import EntityId
from src.engine_v2.core.serialization import dump_json
from src.engine_v2.core.space import (
    SPACES_COMPONENT,
    GraphSpace,
    GridSpace,
    decode_spaces,
)
from src.engine_v2.core.state import RuntimeLifecycle
from src.engine_v2.modules.space import HexGrid, hex_adjacency
from src.engine_v2.runtime.materialize import (
    CHARACTER_PROFILE_COMPONENT,
    WorldMaterialization,
    materialize_world,
)

FIXTURES_ROOT = Path(__file__).resolve().parents[2] / "fixtures"
GALGAME_ROOT = FIXTURES_ROOT / "v2_project_galgame"
TACTICAL_ROOT = FIXTURES_ROOT / "v2_project_tactical"


# —— 助手（确定性；fixture 只读）——


def _load_ir(project: Path) -> ProjectIR:
    """load_project + build_ir → ProjectIR（P9 宿主同源流程，零诊断断言）。"""
    loaded = load_project(str(project))
    assert loaded.raw is not None, f"load_project 失败：{loaded.diagnostics}"
    assert not loaded.diagnostics, loaded.diagnostics
    built = build_ir(loaded.raw)
    assert built.ir is not None, f"build_ir 失败：{built.diagnostics}"
    assert not built.diagnostics, built.diagnostics
    return built.ir


def _error_diagnostics(mat: WorldMaterialization) -> list[Diagnostic]:
    return [d for d in mat.diagnostics if d.severity is DiagnosticSeverity.ERROR]


def _domain_position(world, entity_id: str, domain: str = "world"):
    """域内位置（P9 宿主 world_positions 同口径：读 EntityRecord 组件载荷
    经 decode_spaces 投影——EntityView 深冻结面 MappingProxyType 不直接
    过 pydantic JsonValue 校验）。"""
    record = world.entities.get(EntityId(entity_id))
    assert record is not None, f"实体缺席：{entity_id}"
    payload = record.components.get(SPACES_COMPONENT)
    assert payload is not None, f"spaces 组件缺席：{entity_id}"
    positions = {m.domain_id: m.position for m in decode_spaces(payload)}
    assert domain in positions, f"域 {domain} 无映射：{entity_id}"
    return positions[domain]


def _mini_ir(**overrides) -> ProjectIR:
    """最小合法 ProjectIR 工厂（world=None 缺省；硬缺语义面用）。"""
    base = dict(
        manifest=ProjectManifest(schema_version="2", project_id="mini", name="mini"),
        scenario=ScenarioSpec(
            id="mini",
            max_ticks=1,
            ticks_per_game_minute=1.0,
            game_time=ScenarioTime(hour=8, minute=0),
        ),
        player=PlayerSpec(player_id="p", name="p"),
    )
    base.update(overrides)
    return ProjectIR(**base)


@pytest.fixture(scope="module")
def galgame_ir() -> ProjectIR:
    return _load_ir(GALGAME_ROOT)


@pytest.fixture(scope="module")
def tactical_ir() -> ProjectIR:
    return _load_ir(TACTICAL_ROOT)


# —— Gate 2：src 侧零 tests.* import（机械守卫；只读自身模块源文件）——


def test_src_module_has_no_tests_import() -> None:
    import src.engine_v2.runtime.materialize as mod

    text = Path(mod.__file__).read_text(encoding="utf-8")
    assert "import tests" not in text
    assert "from tests" not in text


# —— WorldMaterialization 形状面（contract §1 字段冻结）——


def test_world_materialization_shape() -> None:
    assert is_dataclass(WorldMaterialization)
    assert WorldMaterialization.__dataclass_params__.frozen
    assert tuple(f.name for f in fields(WorldMaterialization)) == (
        "world",
        "runtime",
        "spaces",
        "component_registry",
        "diagnostics",
    )


# —— Gate 1a：galgame fixture（缺省 grid 推导路径）——


class TestGalgame:
    def test_materializes_default_grid(self, galgame_ir: ProjectIR) -> None:
        mat = materialize_world(galgame_ir, world_instance_id="t1_galgame", space_backend=None)
        assert _error_diagnostics(mat) == []

        # 实体面：locations → characters → player → items（规范型 id）
        assert set(mat.world.entities) == {
            EntityId("ent_authoring_classroom"),
            EntityId("ent_authoring_lena"),
            EntityId("ent_authoring_yuki"),
            EntityId("ent_authoring_player_1"),
            EntityId("ent_authoring_letter"),
        }
        assert mat.world.entities[EntityId("ent_authoring_lena")].entity_class == "character"
        assert mat.world.entities[EntityId("ent_authoring_player_1")].entity_class == "player"
        assert mat.world.entities[EntityId("ent_authoring_letter")].entity_class == "item"
        assert mat.world.entities[EntityId("ent_authoring_classroom")].entity_class == "location"
        for record in mat.world.entities.values():
            assert record.created_revision == 0
            assert record.tags == []

        # spaces 面：域注册 + 缺省 grid（声明坐标 max (3,2) → 4×3 = 12 格）
        assert mat.spaces.domain_ids() == ("world",)
        backend = mat.spaces.backend("world")
        assert isinstance(backend, GridSpace)
        assert len(backend.positions()) == 12

        # spaces 组件投影（P9 宿主同款口径：int x/y）
        assert _domain_position(mat.world, "ent_authoring_player_1") == {"x": 1, "y": 1}
        assert _domain_position(mat.world, "ent_authoring_lena") == {"x": 0, "y": 2}
        assert _domain_position(mat.world, "ent_authoring_yuki") == {"x": 2, "y": 1}
        assert _domain_position(mat.world, "ent_authoring_letter") == {"x": 3, "y": 2}
        # location 实体无 position 声明 → 不挂 spaces 组件
        classroom = mat.world.entities[EntityId("ent_authoring_classroom")]
        assert SPACES_COMPONENT not in classroom.components

    def test_world_variables_environment_and_clock(self, galgame_ir: ProjectIR) -> None:
        mat = materialize_world(galgame_ir, world_instance_id="t1_galgame_wv")
        assert mat.world.world_variables == {
            "location": "classroom",
            "description": "午后铃声后的教室，阳光从窗斜进。",
            "time_of_day": "afternoon",
            "weather": "clear",
            "temperature_c": 24.0,
            "game_time": {"hour": 14, "minute": 30},
        }

    def test_runtime_zero_initial(self, galgame_ir: ProjectIR) -> None:
        mat = materialize_world(galgame_ir, world_instance_id="t1_galgame_rt")
        assert mat.runtime.logical_tick == 0
        assert mat.runtime.lifecycle is RuntimeLifecycle.CREATED
        assert mat.runtime.scheduler_queue == []
        assert mat.runtime.active_actions == {}
        assert mat.runtime.actor_wakeups == []
        assert mat.runtime.active_modes == []
        assert mat.runtime.mode_context == {}
        assert mat.runtime.rng_state is None
        assert mat.runtime.pending_proposals == []
        assert mat.runtime.backend_refs == {}

    def test_character_profile_read_only_component(self, galgame_ir: ProjectIR) -> None:
        mat = materialize_world(galgame_ir, world_instance_id="t1_galgame_profile")
        lena = mat.world.entities[EntityId("ent_authoring_lena")]
        payload = lena.components[CHARACTER_PROFILE_COMPONENT]
        assert payload["name"] == "莉娜·索蕾尔"
        assert payload["personality"]["traits"] == ["lively", "sociable"]
        assert payload["personality"]["speech_style"] == "活泼，爱用反问句。"
        assert payload["speech_examples"] == ["上个月的祭典你喜欢吗？"]
        # 组件数据 JSON-clean（json round-trip 逐字稳定，无 MappingProxy 等
        # 非 JSON 容器）
        assert json.loads(json.dumps(payload)) == payload

        # 只读：零 authority 授予 + 零 payload 校验钩子（D-8 不透明）
        schema = mat.component_registry.get(CHARACTER_PROFILE_COMPONENT)
        assert schema is not None
        assert schema.authority_domain is None
        assert schema.payload_model is None

        # player 无 profile 组件（T1 只投影 CharacterSpec）
        player = mat.world.entities[EntityId("ent_authoring_player_1")]
        assert CHARACTER_PROFILE_COMPONENT not in player.components
        assert SPACES_COMPONENT in player.components

    def test_diagnostics_disclosure_no_errors(self, galgame_ir: ProjectIR) -> None:
        mat = materialize_world(galgame_ir, world_instance_id="t1_galgame_diag")
        assert _error_diagnostics(mat) == []
        warnings = [d for d in mat.diagnostics if d.severity is DiagnosticSeverity.WARNING]
        # 缺省 grid assumption（WorldSpec 无 backend kind 声明字段）
        assert any(
            d.path == "world" and "grid" in d.message and "assumption" in d.refs for d in warnings
        )
        # character_profile 投影披露（refs = 角色 slug 序）
        profile_diags = [d for d in warnings if d.path == "character_profile"]
        assert len(profile_diags) == 1
        assert profile_diags[0].refs == ("lena", "yuki")


# —— Gate 1b：tactical fixture（缺省 grid + 显式 hex backend 双路径）——


class TestTactical:
    def test_materializes_default_grid(self, tactical_ir: ProjectIR) -> None:
        mat = materialize_world(tactical_ir, world_instance_id="t1_tactical")
        assert _error_diagnostics(mat) == []
        assert set(mat.world.entities) == {
            EntityId("ent_authoring_arena"),
            EntityId("ent_authoring_soldier_a"),
            EntityId("ent_authoring_soldier_b"),
            EntityId("ent_authoring_player_1"),
        }
        backend = mat.spaces.backend("world")
        assert isinstance(backend, GridSpace)
        # 声明坐标 max (1,1) → 2×2
        assert len(backend.positions()) == 4
        assert _domain_position(mat.world, "ent_authoring_soldier_a") == {"x": 0, "y": 0}
        assert _domain_position(mat.world, "ent_authoring_soldier_b") == {"x": 1, "y": 0}
        assert _domain_position(mat.world, "ent_authoring_player_1") == {"x": 1, "y": 1}
        assert mat.world.world_variables["location"] == "arena"
        assert mat.world.world_variables["weather"] == "overcast"
        assert mat.world.world_variables["time_of_day"] == "morning"
        assert mat.world.world_variables["game_time"] == {"hour": 9, "minute": 0}

    def test_materializes_explicit_hex_backend(self, tactical_ir: ProjectIR) -> None:
        grid = HexGrid(cols=3, rows=3)
        nodes = [f"hex_{c}_{r}" for c in range(3) for r in range(3)]
        # 有向边表 → 去重无向集（G-INV 面；P9 A12 宿主同口径）
        directed = hex_adjacency(grid)
        deduped = sorted({(min(a, b), max(a, b)) for a, b in directed})
        backend = GraphSpace(nodes=nodes, edges=deduped)
        mat = materialize_world(
            tactical_ir,
            world_instance_id="t1_tactical_hex",
            space_backend=backend,
        )
        assert _error_diagnostics(mat) == []
        # 显式 backend 注册入 domain_id（同一对象）
        assert mat.spaces.backend("world") is backend
        assert isinstance(backend, GraphSpace)
        # graph 投影口径：hex_<x>_<y> 节点串
        assert _domain_position(mat.world, "ent_authoring_soldier_a") == "hex_0_0"
        assert _domain_position(mat.world, "ent_authoring_soldier_b") == "hex_1_0"
        assert _domain_position(mat.world, "ent_authoring_player_1") == "hex_1_1"
        # 显式 backend → 无缺省 grid assumption（world 节 warning 零条）
        assert not [d for d in mat.diagnostics if d.path == "world"]


# —— Gate 3：同 IR 双构造 world 序列化一致——


@pytest.mark.parametrize("project", ["v2_project_galgame", "v2_project_tactical"], ids=lambda s: s)
def test_same_ir_double_construction_world_serialization_equal(project: str) -> None:
    ir = _load_ir(FIXTURES_ROOT / project)
    mat_a = materialize_world(ir, world_instance_id="t1_dup_a")
    mat_b = materialize_world(ir, world_instance_id="t1_dup_b")
    assert dump_json(mat_a.world) == dump_json(mat_b.world)
    assert dump_json(mat_a.runtime) == dump_json(mat_b.runtime)
    # 双构造诊断逐字一致（确定性文本面）
    assert [(d.code, d.severity.value, d.path, d.message, d.refs) for d in mat_a.diagnostics] == [
        (d.code, d.severity.value, d.path, d.message, d.refs) for d in mat_b.diagnostics
    ]


# —— 失败语义（显式诊断不静默；能 materialize 的部分仍产出）——


class TestFailureSemantics:
    def test_missing_world_section_diagnostic_still_materializes(self) -> None:
        ir = _mini_ir(world=None)
        mat = materialize_world(ir, world_instance_id="t1_noworld")
        # world 节缺失 = 合法空（D-P5-05）→ warning，非 error
        assert _error_diagnostics(mat) == []
        assert any(
            d.path == "world" and d.severity is DiagnosticSeverity.WARNING for d in mat.diagnostics
        )
        # 无环境投影；时钟初始值仍产出
        assert mat.world.world_variables == {"game_time": {"hour": 8, "minute": 0}}
        # 无声明坐标 → 1×1 缺省 grid + assumption
        assert len(mat.spaces.backend("world").positions()) == 1
        # player 仍产出
        assert EntityId("ent_authoring_p") in mat.world.entities

    def test_missing_player_hard_diagnostic_not_silent(self, galgame_ir: ProjectIR) -> None:
        broken = galgame_ir.model_copy(update={"player": None})
        mat = materialize_world(broken, world_instance_id="t1_noplayer")
        hard = [d for d in _error_diagnostics(mat) if d.refs == ("player", "missing")]
        assert len(hard) == 1
        assert hard[0].code == "LLMSIM_SCHEMA"
        # player 不产出；余部仍 materialize
        assert EntityId("ent_authoring_player_1") not in mat.world.entities
        assert EntityId("ent_authoring_lena") in mat.world.entities
        assert EntityId("ent_authoring_letter") in mat.world.entities

    def test_unresolvable_position_diagnostic_entity_still_materialized(
        self, galgame_ir: ProjectIR
    ) -> None:
        # 显式 2×2 grid：lena(0,2) / yuki(2,1) / letter(3,2) 越界；
        # player(1,1) 合法
        backend = GridSpace(width=2, height=2)
        mat = materialize_world(
            galgame_ir,
            world_instance_id="t1_small_grid",
            space_backend=backend,
        )
        bad = {d.path for d in _error_diagnostics(mat) if d.code == "LLMSIM_UNRESOLVED_REF"}
        assert bad == {
            "ent_authoring_lena",
            "ent_authoring_yuki",
            "ent_authoring_letter",
        }
        # 实体仍产出，仅不挂 spaces 组件
        for slug in ("lena", "yuki", "letter"):
            record = mat.world.entities[EntityId(f"ent_authoring_{slug}")]
            assert record is not None
            assert SPACES_COMPONENT not in record.components
        assert _domain_position(mat.world, "ent_authoring_player_1") == {"x": 1, "y": 1}

    def test_duplicate_entity_id_explicit_first_wins(self, galgame_ir: ProjectIR) -> None:
        # 角色 lena 改 id=letter → 与物品 letter 规范 id 冲突；装配序角色先
        specs = tuple(
            c.model_copy(update={"id": "letter"}) if c.id == "lena" else c
            for c in galgame_ir.characters
        )
        ir2 = galgame_ir.model_copy(update={"characters": specs})
        mat = materialize_world(ir2, world_instance_id="t1_dup_id")
        dups = [d for d in _error_diagnostics(mat) if d.code == "LLMSIM_DUPLICATE_ID"]
        assert len(dups) == 1
        assert dups[0].path == "ent_authoring_letter"
        assert dups[0].refs == ("letter", "letter")
        # 首个来源（character）保留
        record = mat.world.entities[EntityId("ent_authoring_letter")]
        assert record.entity_class == "character"

    def test_duplicate_component_schema_diagnostic_not_raised(self) -> None:
        ir = _mini_ir(
            component_schemas=(
                ContentComponentSchema(
                    id="dual",
                    fields=(ComponentField(name="a", type=ComponentType.STRING),),
                    description="first",
                ),
                ContentComponentSchema(
                    id="dual",
                    fields=(ComponentField(name="b", type=ComponentType.STRING),),
                    description="second",
                ),
            )
        )
        mat = materialize_world(ir, world_instance_id="t1_dup_schema")
        dups = [d for d in _error_diagnostics(mat) if d.code == "LLMSIM_DUPLICATE_ID"]
        assert len(dups) == 1
        assert dups[0].path == "dual"
        # 首条保留
        assert mat.component_registry.get(ComponentTypeId("dual")).description == "first"


# —— component_registry：IR ComponentSchema 注册面——


def test_registers_ir_component_schemas() -> None:
    ir = _mini_ir(
        component_schemas=(
            ContentComponentSchema(
                id="world.location",
                fields=(ComponentField(name="name", type=ComponentType.STRING),),
                description="location 组件",
            ),
        )
    )
    mat = materialize_world(ir, world_instance_id="t1_schemas")
    assert _error_diagnostics(mat) == []
    schema = mat.component_registry.get(ComponentTypeId("world.location"))
    assert schema is not None
    assert schema.description == "location 组件"
    # D-8：未注册组件类型 ≠ 错误
    assert mat.component_registry.get(ComponentTypeId("unknown.type")) is None
    # character_profile 恒注册
    assert mat.component_registry.get(CHARACTER_PROFILE_COMPONENT) is not None


# —— 显式 backend 守卫面（文法/种类一致：编程错误显式抛出，不静默）——


def test_invalid_domain_id_raises_explicitly(galgame_ir: ProjectIR) -> None:
    with pytest.raises(ValueError):
        materialize_world(
            galgame_ir,
            world_instance_id="t1_bad_domain",
            domain_id="World",  # S-INV-1 文法违例
        )


def test_explicit_grid_backend_registered_identity(galgame_ir: ProjectIR) -> None:
    # 显式 GridSpace → 注册入 domain_id（同一对象；S-INV-5 种类一致）
    backend = GridSpace(width=4, height=3)
    mat = materialize_world(
        galgame_ir,
        world_instance_id="t1_grid_backend",
        space_backend=backend,
    )
    assert _error_diagnostics(mat) == []
    assert mat.spaces.backend("world") is backend
