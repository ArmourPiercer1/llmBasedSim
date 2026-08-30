"""P5-T02a（W1）单元测试：P5 项目格式数据 schemas（设计文档 §3.1 / §5.2 / §6.1）。

覆盖 §6.1 ``content/test_schemas.py`` 用例族（恰好 10 用例；「每模型 ≥1 例」
口径在单用例内以逐模型断言实现）；全部用例离线、无网络、无墙钟、无文件系统
访问（TestB3OfflineRunnable 扫描面，import 面 = stdlib + pytest + pydantic +
``src.engine_v2.content``）：

1. ``__all__`` 25 名台账（逐名逐序）+ 25 导出逐一构造（§8.2 台账）；
2. ``DIAGNOSTIC_CODES`` 18 枚闭集核验（集合相等 + 基数 + 逐码可构造）；
3. ``Diagnostic`` 形状与 code 闭集校验（非法 code 构造期拒绝，D-P5-12）；
4. 全部模型 ``frozen=True``（K2 / P5-INV-2）：字段再赋值拒绝；
5. 全部模型 ``extra="forbid"``（D-P5-05）：未知键 → ``ValidationError``（每模型 1 例）；
6. 5 个开放 dict 豁免（D-P5-05）各接受任意 JSON-clean 键（各 ≥1 例）；
7. ``ProjectManifest`` 字段闭集 + ``schema_version`` Literal + ``project_id`` 词法；
8. ``engine_version`` 文法（D-P5-06）+ ``ENGINE_VERSION`` 常量 + ``ModuleGraphNode`` 词法；
9. ``ProjectIR`` 16 字段闭集与默认值面 + ``world`` 单值语义（ERR-P5-7 H-1）；
10. JSON-clean 字段面（K7 / P5-INV-7）：``model_dump(mode="json")`` 全原生 + 往返。
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from src.engine_v2.content import schemas
from src.engine_v2.content.schemas import (
    ActionSpec,
    AttributeSpec,
    AuthorityPolicy,
    CharacterSpec,
    ComponentField,
    ComponentSchema,
    ComponentType,
    DIAGNOSTIC_CODES,
    Diagnostic,
    DiagnosticSeverity,
    EnvironmentSpec,
    GameplayModeSpec,
    InferenceCapabilityProfile,
    LocationSpec,
    ModuleGraphNode,
    ObjectSpec,
    PlayerSpec,
    PositionSpec,
    ProjectIR,
    ProjectManifest,
    PromptPolicy,
    PluginDescriptor,
    RawProject,
    RuleSpec,
    ScenarioSpec,
    ScenarioTime,
    WorldSpec,
)

#: 25 导出，设计文档 §8.2 导出台账逐名逐序（用例 1 台账基线）。
EXPECTED_ALL: tuple[str, ...] = (
    "DIAGNOSTIC_CODES",
    "RawProject",
    "ProjectManifest",
    "ProjectIR",
    "WorldSpec",
    "EnvironmentSpec",
    "LocationSpec",
    "ObjectSpec",
    "PositionSpec",
    "AttributeSpec",
    "PlayerSpec",
    "CharacterSpec",
    "ComponentSchema",
    "ComponentField",
    "ActionSpec",
    "RuleSpec",
    "AuthorityPolicy",
    "ModuleGraphNode",
    "GameplayModeSpec",
    "InferenceCapabilityProfile",
    "PromptPolicy",
    "PluginDescriptor",
    "ScenarioSpec",
    "Diagnostic",
    "DiagnosticSeverity",
)

#: 18 枚诊断码闭集（设计文档 §3.1 诊断码表，逐字；用例 2 基线）。
EXPECTED_CODES: frozenset[str] = frozenset(
    {
        "LLMSIM_FILE_MISSING",
        "LLMSIM_YAML_PARSE",
        "LLMSIM_PROJECT_FORMAT_V1",
        "LLMSIM_SCHEMA",
        "LLMSIM_UNKNOWN_KEY",
        "LLMSIM_DUPLICATE_ID",
        "LLMSIM_UNRESOLVED_REF",
        "LLMSIM_MODULE_REQUIRES_MISSING",
        "LLMSIM_MODULE_VERSION",
        "LLMSIM_MODULE_CYCLE",
        "LLMSIM_MODULE_CONFLICT",
        "LLMSIM_AUTHORITY_CONFLICT",
        "LLMSIM_DEPLOYMENT_FIELD",
        "LLMSIM_DSL_PARSE",
        "LLMSIM_PLUGIN_ENTRY_INVALID",
        "LLMSIM_PLUGIN_NO_PYPROJECT",
        "LLMSIM_ENGINE_VERSION",
        "LLMSIM_PLUGIN_ENTRY_UNRESOLVED",
    }
)

#: 全部 24 个数据模型（23 公开 + 私有 ``ScenarioTime``）的最小合法构造 kwargs
#: （用例 1/4/5 共用；「每模型 1 例」的逐模型基线）。
_MINIMAL_KWARGS: dict[str, dict[str, Any]] = {
    "PositionSpec": {"x": 0.0, "y": 1.0},
    "EnvironmentSpec": {},
    "LocationSpec": {"id": "loc_room", "name": "Room"},
    "WorldSpec": {"name": "World"},
    "ObjectSpec": {"id": "obj_table", "name": "Table"},
    "AttributeSpec": {"name": "health", "value": 50.0, "min": 0.0, "max": 100.0},
    "PlayerSpec": {"player_id": "player_1", "name": "Player"},
    "CharacterSpec": {"id": "char_nia", "name": "Nia"},
    "ComponentField": {"name": "name", "type": "string"},
    "ComponentSchema": {
        "id": "world.location",
        "fields": (ComponentField(name="name", type="string"),),
    },
    "ActionSpec": {"id": "act_open", "name": "Open"},
    "RuleSpec": {"id": "rule_no_swim"},
    "AuthorityPolicy": {"id": "auth_space", "domain": "position", "owner": "world"},
    "ModuleGraphNode": {"id": "content.loader", "version": "1.0"},
    "GameplayModeSpec": {"id": "mode_survival", "mode_type": "survival"},
    "InferenceCapabilityProfile": {"id": "cap_plan", "capability": "planning"},
    "PromptPolicy": {"id": "prompt_narrate", "scope": "narration", "template_ref": "t"},
    "PluginDescriptor": {"id": "plugin_math"},
    "ScenarioTime": {"hour": 9, "minute": 30},
    "ScenarioSpec": {
        "id": "scenario_main",
        "max_ticks": 60,
        "ticks_per_game_minute": 2.0,
        "game_time": ScenarioTime(hour=9, minute=30),
    },
    "RawProject": {
        "root": "/proj",
        "files": {"game.yaml": {}},
        "texts": {"game.yaml": "project: game"},
        "pyproject_present": False,
        "plugins_dir_present": False,
    },
    "ProjectManifest": {"schema_version": "2", "project_id": "proj_g1", "name": "Project"},
    "ProjectIR": {
        "manifest": ProjectManifest(schema_version="2", project_id="proj_g1", name="Project"),
        "scenario": ScenarioSpec(
            id="scenario_main",
            max_ticks=60,
            ticks_per_game_minute=2.0,
            game_time=ScenarioTime(hour=9, minute=30),
        ),
        "player": PlayerSpec(player_id="player_1", name="Player"),
    },
    "Diagnostic": {
        "code": "LLMSIM_SCHEMA",
        "severity": "error",
        "path": "game.yaml",
        "message": "unknown key",
    },
}

#: 5 个开放 dict 豁免（D-P5-05）接受的任意 JSON-clean 键样例（用例 6）。
_ARBITRARY_KEYS: dict[str, Any] = {
    "nested.1": {"a": [1, 2.5, None, True]},
    "中文键": "v",
    "empty": {},
}


def _module_models() -> dict[str, type[BaseModel]]:
    """模块内全部数据模型（24 个：23 公开 + 私有 ``ScenarioTime``），名 → 类。

    与 ``_MINIMAL_KWARGS`` 台账交叉核验，保证「每模型」循环无遗漏、无多余。
    """
    found = {
        name: cls
        for name, cls in vars(schemas).items()
        if isinstance(cls, type)
        and issubclass(cls, BaseModel)
        and cls.__module__ == schemas.__name__
        and not name.startswith("_")
    }
    assert set(found) == set(_MINIMAL_KWARGS)
    return found


def test_export_ledger_25_exact_order_and_constructibility() -> None:
    """用例 1：``__all__`` 25 名台账逐名逐序 + 25 导出逐一构造 + 私有面定位。"""
    assert schemas.__all__ == list(EXPECTED_ALL)
    assert len(schemas.__all__) == 25
    for name in schemas.__all__:
        assert hasattr(schemas, name), f"台账名 {name} 非模块属性"
    # 25 导出逐一构造（DIAGNOSTIC_CODES = 闭集核验，DiagnosticSeverity = 词表核验）
    for name in EXPECTED_ALL:
        export = getattr(schemas, name)
        if name == "DIAGNOSTIC_CODES":
            assert isinstance(export, frozenset)
        elif name == "DiagnosticSeverity":
            assert {member.value for member in export} == {"error", "warning"}
        else:
            export(**_MINIMAL_KWARGS[name])  # 构造成功
    # RawProject 尾 2 字段默认面（loader 产出，pyproject 缺席 → 原文 None）
    raw = RawProject(**_MINIMAL_KWARGS["RawProject"])
    assert raw.pyproject_text is None and raw.plugins_dir_present is False
    # 私有面：存在且不入 ``__all__``（25 台账不含之）
    for private in ("ENGINE_VERSION", "ComponentType", "ScenarioTime"):
        assert hasattr(schemas, private)
        assert private not in schemas.__all__
    assert schemas.ENGINE_VERSION == "0.5.0"
    # 私有 ``ComponentType`` 6 值词表（``ComponentField.type`` 消费）
    assert {member.value for member in ComponentType} == {
        "string",
        "number",
        "boolean",
        "list",
        "map",
        "object",
    }


def test_diagnostic_codes_18_closed_set() -> None:
    """用例 2：``DIAGNOSTIC_CODES`` 18 枚闭集核验（集合相等 + 基数）。"""
    assert isinstance(DIAGNOSTIC_CODES, frozenset)
    assert DIAGNOSTIC_CODES == EXPECTED_CODES
    assert len(DIAGNOSTIC_CODES) == 18
    for code in sorted(EXPECTED_CODES):
        assert code.startswith("LLMSIM_")


def test_diagnostic_shape_and_code_validation() -> None:
    """用例 3：``Diagnostic`` 形状（D-P5-12）——code 闭集构造期拒绝、severity 双形、
    path/message 非空、refs 默认空、18 码逐一可构造。"""
    d = Diagnostic(code="LLMSIM_SCHEMA", severity="error", path="game.yaml", message="unknown key")
    assert d.severity == DiagnosticSeverity.ERROR == "error"
    assert d.refs == ()
    d2 = Diagnostic(
        code="LLMSIM_MODULE_CYCLE",
        severity=DiagnosticSeverity.WARNING,
        path="modules/a.yaml",
        message="cycle",
        refs=("a", "b", "c"),
    )
    assert d2.severity == "warning"
    assert d2.refs == ("a", "b", "c")
    for code in sorted(EXPECTED_CODES):
        Diagnostic(code=code, severity="error", path="p", message="m")
    with pytest.raises(ValidationError):
        Diagnostic(code="LLMSIM_NOT_A_CODE", severity="error", path="p", message="m")
    with pytest.raises(ValidationError):
        Diagnostic(code="LLMSIM_SCHEMA", severity="error", path="", message="m")
    with pytest.raises(ValidationError):
        Diagnostic(code="LLMSIM_SCHEMA", severity="error", path="p", message="")
    with pytest.raises(ValidationError):
        Diagnostic(code="LLMSIM_SCHEMA", severity="critical", path="p", message="m")


def test_all_models_frozen_and_mutation_rejected() -> None:
    """用例 4：全部模型 ``frozen=True``（K2 / P5-INV-2）+ 字段再赋值构造期拒绝。"""
    models = _module_models()
    assert len(models) == 24
    probe = object()
    for name, cls in models.items():
        assert cls.model_config["frozen"] is True, name
        instance = cls(**_MINIMAL_KWARGS[name])
        field_name = next(iter(cls.model_fields))
        with pytest.raises(ValidationError):
            setattr(instance, field_name, probe)


def test_extra_forbid_unknown_key_every_model() -> None:
    """用例 5：全部模型 ``extra="forbid"``（D-P5-05 严格度基线）——未知键
    → ``ValidationError``（error type = ``extra_forbidden``，每模型 1 例）。"""
    models = _module_models()
    for name, cls in models.items():
        assert cls.model_config["extra"] == "forbid", name
        with pytest.raises(ValidationError) as excinfo:
            cls(**{**_MINIMAL_KWARGS[name], "unknown_key_zz": 1})
        assert any(err["type"] == "extra_forbidden" for err in excinfo.value.errors()), name


def test_five_open_dict_exemptions_accept_arbitrary_keys() -> None:
    """用例 6：5 个开放 dict 豁免（D-P5-05）各接受任意 JSON-clean 键。"""
    assert LocationSpec(id="loc_a", name="A", properties=dict(_ARBITRARY_KEYS)).properties == (
        _ARBITRARY_KEYS
    )
    assert ObjectSpec(id="obj_a", name="A", properties=dict(_ARBITRARY_KEYS)).properties == (
        _ARBITRARY_KEYS
    )
    player = PlayerSpec(
        player_id="p1",
        name="P",
        capabilities=dict(_ARBITRARY_KEYS),
        physical_profile=dict(_ARBITRARY_KEYS),
    )
    assert player.capabilities == _ARBITRARY_KEYS
    assert player.physical_profile == _ARBITRARY_KEYS
    assert CharacterSpec(id="ch_a", name="C", personality=dict(_ARBITRARY_KEYS)).personality == (
        _ARBITRARY_KEYS
    )


def test_project_manifest_field_set_literal_and_id_pattern() -> None:
    """用例 7：``ProjectManifest`` 字段闭集与序 + ``schema_version`` Literal["2"]
    （D-P5-04 v1 机械判据）+ ``project_id`` 词法 + name 1..200 边界。"""
    assert list(ProjectManifest.model_fields) == [
        "schema_version",
        "project_id",
        "name",
        "description",
        "engine_version",
    ]
    m = ProjectManifest(schema_version="2", project_id="proj_g1", name="Project")
    assert m.description == ""
    assert m.engine_version == ""
    for bad in ("1", "3", "v2", 2):
        with pytest.raises(ValidationError):
            ProjectManifest(schema_version=bad, project_id="g1", name="G")
    for good in ("g1", "a", "a" + "b" * 63, "a" * 64):
        ProjectManifest(schema_version="2", project_id=good, name="G")
    for bad in ("G1", "1g", "g-1", "_g", "a" * 65, ""):
        with pytest.raises(ValidationError):
            ProjectManifest(schema_version="2", project_id=bad, name="G")
    with pytest.raises(ValidationError):
        ProjectManifest(schema_version="2", project_id="g1", name="")
    assert ProjectManifest(schema_version="2", project_id="g1", name="x" * 200).name == "x" * 200
    with pytest.raises(ValidationError):
        ProjectManifest(schema_version="2", project_id="g1", name="x" * 201)


def test_engine_version_grammar_and_module_node_lexicon() -> None:
    """用例 8：``engine_version`` 文法（D-P5-06：``""`` | V | ``>=V``）+
    ``ENGINE_VERSION`` 单点常量 + ``ModuleGraphNode`` id/version 词法
    （requires 元素文法属 W3 ``parse_requirement`` 面，本面不校验）。"""
    assert schemas.ENGINE_VERSION == "0.5.0"
    base: dict[str, Any] = {"schema_version": "2", "project_id": "g1", "name": "G"}
    for good in ("", "1", "0.5.0", "1.2.3.4.5", "10.20.30", ">=0.5.0", ">=1"):
        assert ProjectManifest(**base, engine_version=good).engine_version == good
    for bad in (">= 0.5.0", "v0.5.0", "0.5.x", "0..5", "<=0.5", "0.5.0 ", " 0.5", "-", ">="):
        with pytest.raises(ValidationError):
            ProjectManifest(**base, engine_version=bad)
    node = ModuleGraphNode(id="content.loader", version="1.0", requires=("content.dsl",))
    assert node.entrypoint is None
    assert node.optional == () and node.conflicts == ()
    assert node.engine_version == "" and node.description == ""
    ModuleGraphNode(id="a.b.c.d", version="0.5.0", entrypoint="content.loader:load")
    for bad in (
        {"id": "Content.loader", "version": "1"},
        {"id": "9content.a", "version": "1"},
        {"id": "content.", "version": "1"},
        {"id": ".content", "version": "1"},
        {"id": "content.loader", "version": ""},
        {"id": "content.loader", "version": "1.2.x"},
        {"id": "content.loader", "version": "v1"},
    ):
        with pytest.raises(ValidationError):
            ModuleGraphNode(**bad)
    with pytest.raises(ValidationError):
        ModuleGraphNode(id="a.b")  # version 必需


def test_project_ir_16_fields_defaults_and_world_none() -> None:
    """用例 9：``ProjectIR`` 16 字段闭集与序 + 默认值面 + ``world`` 单值语义
    （ERR-P5-7 H-1 / D-P5-05：0 文件 → None 合法空；1 文件 → WorldSpec）。"""
    assert list(ProjectIR.model_fields) == [
        "manifest",
        "scenario",
        "world",
        "player",
        "items",
        "characters",
        "component_schemas",
        "actions",
        "rules",
        "authority",
        "modules",
        "gameplay_modes",
        "capabilities",
        "prompts",
        "plugin_descriptors",
        "scenarios",
    ]
    assert ProjectIR.model_fields["world"].default is None
    ir = ProjectIR(**_MINIMAL_KWARGS["ProjectIR"])
    assert ir.world is None
    for field in (
        "items",
        "characters",
        "component_schemas",
        "actions",
        "rules",
        "authority",
        "modules",
        "gameplay_modes",
        "capabilities",
        "prompts",
        "plugin_descriptors",
        "scenarios",
    ):
        assert getattr(ir, field) == ()
    assert ir.manifest.project_id == "proj_g1"
    assert ir.player.player_id == "player_1"
    world = WorldSpec(name="W")
    assert ProjectIR(**{**_MINIMAL_KWARGS["ProjectIR"], "world": world}).world is world
    assert ProjectIR(**{**_MINIMAL_KWARGS["ProjectIR"], "world": None}).world is None
    for required in ("player", "scenario", "manifest"):
        kwargs = {k: v for k, v in _MINIMAL_KWARGS["ProjectIR"].items() if k != required}
        with pytest.raises(ValidationError):
            ProjectIR(**kwargs)


def _fully_populated_ir() -> ProjectIR:
    """16 字段全填充的 ProjectIR（各类模型至少出现一次，用例 10 数据基线）。"""
    return ProjectIR(
        manifest=ProjectManifest(
            schema_version="2",
            project_id="proj_ir_1",
            name="IR 测试项目",
            description="d",
            engine_version=">=0.5.0",
        ),
        scenario=ScenarioSpec(
            id="scenario_main",
            max_ticks=60,
            ticks_per_game_minute=2.0,
            game_time=ScenarioTime(hour=20, minute=5),
            starting_scene_description="夜幕降临",
            narrative_style="calm",
        ),
        world=WorldSpec(
            name="测试世界",
            description="d",
            environment=EnvironmentSpec(time_of_day="night", weather="clear", temperature_c=18.5),
            locations=(
                LocationSpec(
                    id="loc_room",
                    name="Room",
                    connections={"east": "loc_hall"},
                    ambient_light="dim",
                    ambient_sound="wind",
                    properties={"kind": "indoor"},
                ),
            ),
        ),
        player=PlayerSpec(
            player_id="player_1",
            name="Player",
            persona="p",
            position=PositionSpec(x=1.0, y=2.0, z=0.0),
            capabilities={"skill_levels": {"strength": 3}},
            physical_profile={"height_cm": 175.0, "movement_mode": "walk"},
            attributes={
                "health": AttributeSpec(
                    name="health", value=100.0, min=0.0, max=100.0, natural_delta_per_minute=-0.1
                ),
            },
            inventory=["torch"],
            subconscious_rules=["stay calm"],
            subconscious_memory=["met nia"],
            speech_examples=["ok"],
        ),
        items=(
            ObjectSpec(
                id="obj_table",
                object_type="furniture",
                name="Table",
                description="d",
                position=PositionSpec(x=3.0, y=4.0),
                state="closed",
                properties={"wood": True},
            ),
        ),
        characters=(
            CharacterSpec(
                id="char_nia",
                name="Nia",
                personality={"traits": ["calm"], "speech_style": "brief"},
                position=PositionSpec(x=5.0, y=6.0, z=1.0),
                starting_inventory=["key"],
                relationships={"player_1": 0.8},
                speech_examples=["嗯。"],
                attributes={
                    "mood": AttributeSpec(name="mood", value=0.5, min=0.0, max=1.0),
                },
            ),
        ),
        component_schemas=(
            ComponentSchema(
                id="world.location",
                description="d",
                fields=(
                    ComponentField(name="name", type="string", required=True),
                    ComponentField(name="tags", type="list", default=[]),
                    ComponentField(name="solid", type="boolean"),
                ),
            ),
        ),
        actions=(
            ActionSpec(
                id="act_open",
                name="Open",
                verb="open",
                requires_components=("world.door",),
                condition="target.state == 'locked'",
                success_probability=0.9,
                description="d",
            ),
        ),
        rules=(
            RuleSpec(id="rule_no_swim", description="d", match="swim", feasibility="blocked"),
            RuleSpec(
                id="rule_fatigue",
                description="d",
                feasibility="uncertain",
                probability=0.25,
                priority=50,
            ),
        ),
        authority=(
            AuthorityPolicy(
                id="auth_space",
                domain="position",
                owner="world",
                exclusive=True,
                description="d",
            ),
        ),
        modules=(
            ModuleGraphNode(
                id="content.loader",
                version="1.0",
                entrypoint="content.loader:load_project",
                requires=("content.schemas",),
                optional=("content.plugins",),
                conflicts=("content.legacy",),
                engine_version=">=0.5.0",
                description="d",
            ),
        ),
        gameplay_modes=(
            GameplayModeSpec(
                id="mode_survival",
                mode_type="survival",
                params={"difficulty": 1},
                description="d",
            ),
        ),
        capabilities=(
            InferenceCapabilityProfile(
                id="cap_plan", capability="planning", min_tier=2, ideal_tier=3, notes="d"
            ),
        ),
        prompts=(
            PromptPolicy(
                id="prompt_narrate",
                scope="narration",
                template_ref="prompts/narrate",
                variables=("scene",),
            ),
        ),
        plugin_descriptors=(
            PluginDescriptor(id="plugin_math", source="local", description="d"),
            PluginDescriptor(
                id="plugin_custom",
                source="entrypoint",
                entrypoint="math_ext:MathPlugin",
            ),
        ),
        scenarios=(
            ScenarioSpec(
                id="scenario_alt",
                max_ticks=10,
                ticks_per_game_minute=1.0,
                game_time=ScenarioTime(hour=0, minute=0),
            ),
        ),
    )


def test_json_clean_field_surface() -> None:
    """用例 10：JSON-clean 字段面（K7 / P5-INV-7）——全填充 IR 的
    ``model_dump(mode="json")`` 全原生（json.dumps 成功即证）、枚举 → str、
    元组 → list、JSON 往返相等；Diagnostic 同面。"""
    ir = _fully_populated_ir()
    data = ir.model_dump(mode="json")
    assert list(data) == list(ProjectIR.model_fields)
    text = json.dumps(data, ensure_ascii=False)
    assert json.loads(text) == data
    assert data["manifest"]["engine_version"] == ">=0.5.0"
    assert data["scenario"]["game_time"] == {"hour": 20, "minute": 5}
    assert data["world"]["environment"]["temperature_c"] == 18.5
    assert data["world"]["locations"][0]["connections"] == {"east": "loc_hall"}
    assert data["world"]["locations"][0]["properties"] == {"kind": "indoor"}
    assert data["player"]["position"] == {"x": 1.0, "y": 2.0, "z": 0.0}
    assert data["player"]["attributes"]["health"]["value"] == 100.0
    assert data["items"][0]["state"] == "closed"
    assert data["characters"][0]["relationships"] == {"player_1": 0.8}
    assert data["component_schemas"][0]["fields"][0]["type"] == "string"
    assert ComponentType("string") is ComponentType.STRING
    assert data["component_schemas"][0]["fields"][1]["default"] == []
    assert data["actions"][0]["requires_components"] == ["world.door"]
    assert data["rules"][1]["probability"] == 0.25
    assert data["modules"][0]["requires"] == ["content.schemas"]
    assert data["capabilities"][0]["ideal_tier"] == 3
    assert data["prompts"][0]["variables"] == ["scene"]
    assert data["plugin_descriptors"][1]["entrypoint"] == "math_ext:MathPlugin"
    assert data["scenarios"][0]["game_time"] == {"hour": 0, "minute": 0}
    d = Diagnostic(
        code="LLMSIM_DUPLICATE_ID",
        severity=DiagnosticSeverity.WARNING,
        path="game.yaml",
        message="duplicate id",
        refs=("loc_a", "loc_b"),
    )
    dumped = d.model_dump(mode="json")
    assert json.loads(json.dumps(dumped, ensure_ascii=False)) == dumped
    assert dumped["severity"] == "warning"
    assert dumped["refs"] == ["loc_a", "loc_b"]
