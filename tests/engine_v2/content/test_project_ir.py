"""P5-T02b（W2）单元测试：raw → IR 编译器 + round-trip 面（设计文档 §3.2 / §6.1）。

覆盖 §6.1 ``content/test_project_ir.py`` 用例族（逐条）；全部用例 hermetic
（内存构造 RawProject / ProjectIR，零文件系统、零网络、零 W6 fixture 依赖）：

1. ``__all__`` 6 名台账（逐名逐序，§8.2）+ IRBuildResult frozen / extra=forbid 面;
2. ``build_ir`` 全量 raw → IR 16 字段填充断言（game.yaml 8 键全节 + 8 节文件；
   节文件按 sorted 路径序合并进对应 tuple）;
3. ``build_ir`` 诊断聚合：失败时 ir = None + 诊断集完整——
   extra_forbidden → UNKNOWN_KEY 每键 1 条；其余 ValidationError → SCHEMA 每
   error 1 条按 loc 序；world 多文件 → sorted 首文件 + 每余文件 1 条 SCHEMA
   （refs 逐字，§3.2 L304）；节文件顶层键违例（W2-A2 两族 + 该文件即停）;
   game.yaml 缺失 → FILE_MISSING 双保险（恰好 1 条）;
4. ``flatten_entities`` 序（W2-A3：(id.casefold(), id) 升序 + 重复键后者覆盖）;
5. ``iter_entity_refs`` 全引用类（W2-A4：connection / relationship / inventory
   三类各 ≥1 例 + 精确序断言）;
6. ``ir_to_data`` → ``assert_json_clean`` 通过（K7 钩子实际调用不 raise +
   返回 dict 键面 = ProjectIR 16 字段）;
7. ``canonical_yaml`` 双 dump 字节稳定（同 ir 两次调用字符串相等 + sort_keys
   效应断言 + 数据级 round-trip 恒等，D-P5-14 / 断言 #20 同源）。
"""

from __future__ import annotations

import re
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from src.engine_v2.content import project_ir
from src.engine_v2.content.project_ir import (
    IRBuildResult,
    build_ir,
    canonical_yaml,
    flatten_entities,
    ir_to_data,
    iter_entity_refs,
)
from src.engine_v2.content.schemas import DiagnosticSeverity, ProjectIR, ProjectManifest, RawProject
from src.engine_v2.core.serialization import assert_json_clean

from tests.engine_v2.content.conftest import (
    make_character,
    make_item,
    make_location,
    make_player,
    make_raw_project,
    make_world,
    make_ir,
)

#: 6 导出，设计文档 §8.2 导出台账逐名逐序（用例 1 台账基线）。
EXPECTED_ALL: tuple[str, ...] = (
    "IRBuildResult",
    "build_ir",
    "flatten_entities",
    "iter_entity_refs",
    "ir_to_data",
    "canonical_yaml",
)

#: ProjectIR 16 字段闭集（设计文档 §3.1 字段表）。
EXPECTED_IR_FIELDS: frozenset[str] = frozenset(
    {
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
    }
)

#: canonical_yaml 顶层键行（无缩进 "key:" 行）提取正则。
_TOP_LEVEL_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*:")


# —— 内存 raw 构造（全 hermetic；sorted 路径序合并断言的载体）——


def _valid_game() -> dict[str, Any]:
    """game.yaml 最小合法 v2 顶层（8 键封闭集内必需节齐备）。"""
    return {
        "manifest": {"schema_version": "2", "project_id": "proj_g1", "name": "V2 Project"},
        "scenario": {
            "id": "scenario_main",
            "max_ticks": 20,
            "ticks_per_game_minute": 1.0,
            "game_time": {"hour": 9, "minute": 30},
        },
        "player": {"player_id": "player_1", "name": "Wanderer"},
    }


def _world_file(name: str) -> dict[str, Any]:
    """world 节文件顶层（顶层键必为 world，§3.2 步 3）。"""
    return {"world": {"name": name, "locations": []}}


def _raw_with_game(game: dict[str, Any], extra_files: dict[str, Any] | None = None) -> RawProject:
    """game.yaml + 可选节文件的内存 RawProject。"""
    files: dict[str, Any] = {"game.yaml": game}
    if extra_files:
        files.update(extra_files)
    return make_raw_project(files=files)


def _full_raw() -> RawProject:
    """全量 v2 内存 raw（game.yaml 8 键全节 + 8 个节目录各 ≥1 文件）。

    items 节两个文件：a_items.yaml 按 sorted 序先于 b_items.yaml → IR.items
    tuple 序 = a 文件条目在前（sorted 路径序合并断言载体）。
    """
    game = _valid_game()
    game.update(
        {
            "component_schemas": [
                {"id": "world.location", "fields": [{"name": "x", "type": "number"}]},
            ],
            "authority": [{"id": "auth_sanity", "domain": "attributes.sanity", "owner": "core.sanity"}],
            "gameplay_modes": [{"id": "mode_survival", "mode_type": "survival"}],
            "capabilities": [{"id": "cap_json", "capability": "structured_output"}],
            "plugin_descriptors": [{"id": "plugin_x", "source": "local"}],
        }
    )
    files: dict[str, Any] = {
        "game.yaml": game,
        "world/main_world.yaml": {
            "world": {
                "name": "Stone World",
                "locations": [
                    {"id": "stone_room", "name": "石室", "connections": {"east": "hallway"}},
                    {"id": "hallway", "name": "走廊", "connections": {"west": "stone_room"}},
                ],
            }
        },
        "items/a_items.yaml": {
            "items": [
                {"id": "rope", "name": "绳索"},
                {"id": "torch", "name": "火把"},
            ]
        },
        "items/b_items.yaml": {"items": [{"id": "iron_key", "name": "铁钥匙"}]},
        "characters/villagers.yaml": {
            "characters": [
                {
                    "id": "npc_merchant",
                    "name": "商人",
                    "relationships": {"player_1": 0.7},
                    "starting_inventory": ["potion"],
                }
            ]
        },
        "rules/combat.yaml": {"rules": [{"id": "rule_combat", "description": "战斗规则"}]},
        "actions/verbs.yaml": {"actions": [{"id": "act_open", "name": "打开"}]},
        "prompts/narration.yaml": {
            "prompts": [
                {"id": "prompt_narrate", "scope": "narration", "template_ref": "prompts/narrate.yaml"},
            ]
        },
        "scenarios/chapter2.yaml": {
            "scenarios": [
                {
                    "id": "scenario_c2",
                    "max_ticks": 10,
                    "ticks_per_game_minute": 1.0,
                    "game_time": {"hour": 12, "minute": 0},
                },
            ]
        },
        "modules/core.yaml": {"modules": [{"id": "core.sanity", "version": "1.0.0"}]},
    }
    return make_raw_project(files=files)


# —— 用例族 ——


def test_export_ledger_6_exact_order_and_frozen_result_model() -> None:
    """用例 1：``__all__`` 6 名台账逐名逐序（§8.2）+ IRBuildResult frozen /
    extra="forbid" 面（硬不变量 5）。"""
    assert project_ir.__all__ == list(EXPECTED_ALL)
    assert project_ir.IRBuildResult.model_config["frozen"] is True
    assert project_ir.IRBuildResult.model_config["extra"] == "forbid"
    with pytest.raises(ValidationError):
        IRBuildResult(ir=None, diagnostics=(), unexpected=1)
    result = IRBuildResult(ir=None, diagnostics=())
    with pytest.raises(ValidationError):
        result.diagnostics = ()  # type: ignore[misc]  # frozen：字段再赋值拒绝


def test_build_ir_full_raw_populates_all_16_fields() -> None:
    """用例 2：build_ir 全量 raw → IR 16 字段逐一填充 + 节文件按 sorted 路径序
    合并进对应 tuple（items：a_items 先于 b_items）。"""
    result = build_ir(_full_raw())
    assert result.diagnostics == ()
    ir = result.ir
    assert ir is not None
    # game.yaml 节（单值）
    assert ir.manifest == ProjectManifest(schema_version="2", project_id="proj_g1", name="V2 Project")
    assert ir.scenario.id == "scenario_main"
    assert ir.scenario.max_ticks == 20
    assert ir.scenario.game_time.hour == 9
    assert ir.player.player_id == "player_1"
    assert ir.player.name == "Wanderer"
    # world 节文件（单值）
    assert ir.world is not None
    assert ir.world.name == "Stone World"
    assert [loc.id for loc in ir.world.locations] == ["stone_room", "hallway"]
    assert ir.world.locations[0].connections == {"east": "hallway"}
    # 节文件合并进对应 tuple（sorted 路径序）
    assert [item.id for item in ir.items] == ["rope", "torch", "iron_key"]
    assert [c.id for c in ir.characters] == ["npc_merchant"]
    assert ir.characters[0].relationships == {"player_1": 0.7}
    assert ir.characters[0].starting_inventory == ["potion"]
    assert [cs.id for cs in ir.component_schemas] == ["world.location"]
    assert [a.id for a in ir.actions] == ["act_open"]
    assert [r.id for r in ir.rules] == ["rule_combat"]
    assert [p.id for p in ir.authority] == ["auth_sanity"]
    assert [m.id for m in ir.modules] == ["core.sanity"]
    assert [g.id for g in ir.gameplay_modes] == ["mode_survival"]
    assert [c.id for c in ir.capabilities] == ["cap_json"]
    assert [p.id for p in ir.prompts] == ["prompt_narrate"]
    assert [p.id for p in ir.plugin_descriptors] == ["plugin_x"]
    assert [s.id for s in ir.scenarios] == ["scenario_c2"]


def test_build_ir_unknown_key_one_diagnostic_per_extra_key() -> None:
    """用例 3a：extra_forbidden → LLMSIM_UNKNOWN_KEY 每键 1 条（refs = [键名]，
    按 pydantic 条目序 = 输入键序追加），失败时 ir = None。"""
    game = _valid_game()
    game["player"] = {
        "player_id": "player_1",
        "name": "Wanderer",
        "zz_extra_one": 1,
        "aa_extra_two": "x",
    }
    result = build_ir(_raw_with_game(game))
    assert result.ir is None
    assert len(result.diagnostics) == 2
    assert [(d.code, d.path, d.refs) for d in result.diagnostics] == [
        ("LLMSIM_UNKNOWN_KEY", "game.yaml", ("zz_extra_one",)),
        ("LLMSIM_UNKNOWN_KEY", "game.yaml", ("aa_extra_two",)),
    ]
    assert all(d.severity == DiagnosticSeverity.ERROR for d in result.diagnostics)


def test_build_ir_schema_diagnostics_one_per_error_in_loc_order() -> None:
    """用例 3b：其余 ValidationError → LLMSIM_SCHEMA 每 error 1 条按 loc 序
    （refs = [loc 点分串, type]，按模型字段声明序追加）。"""
    game = _valid_game()
    game["player"] = {"player_id": 99, "name": "", "inventory": [1, 2]}
    result = build_ir(_raw_with_game(game))
    assert result.ir is None
    assert [(d.code, d.path, d.refs) for d in result.diagnostics] == [
        ("LLMSIM_SCHEMA", "game.yaml", ("player_id", "string_type")),
        ("LLMSIM_SCHEMA", "game.yaml", ("name", "string_too_short")),
        ("LLMSIM_SCHEMA", "game.yaml", ("inventory.0", "string_type")),
        ("LLMSIM_SCHEMA", "game.yaml", ("inventory.1", "string_type")),
    ]


def test_build_ir_world_multi_files_sorted_first_plus_one_schema_per_extra() -> None:
    """用例 3c：world 多文件（≥2）→ sorted 路径序首文件为准 + 每余文件 1 条
    LLMSIM_SCHEMA（refs = ["world 节为单值 WorldSpec，多余文件不合并"]，§3.2
    L304 逐字），ir = None，不 raise。"""
    raw = _raw_with_game(
        _valid_game(),
        {
            "world/b_world.yaml": _world_file("B"),
            "world/a_world.yaml": _world_file("A"),
        },
    )
    result = build_ir(raw)
    assert result.ir is None
    assert len(result.diagnostics) == 1
    d = result.diagnostics[0]
    assert d.code == "LLMSIM_SCHEMA"
    assert d.path == "world/b_world.yaml"
    assert d.refs == ("world 节为单值 WorldSpec，多余文件不合并",)


def test_build_ir_world_first_file_inner_validation() -> None:
    """用例 3d：world 恰好 1 文件时该文件做内层校验（首文件内层违例 → SCHEMA
    每 error 1 条按 loc 序）；0 文件 → ir.world = None 合法空（D-P5-05）。"""
    # 首文件内层违例（world.name 缺失）
    raw = _raw_with_game(_valid_game(), {"world/a_world.yaml": {"world": {"locations": []}}})
    result = build_ir(raw)
    assert result.ir is None
    assert [(d.code, d.path, d.refs) for d in result.diagnostics] == [
        ("LLMSIM_SCHEMA", "world/a_world.yaml", ("name", "missing")),
    ]
    # 0 文件 → 合法空（world = None，零诊断）
    result = build_ir(_raw_with_game(_valid_game()))
    assert result.ir is not None
    assert result.diagnostics == ()
    assert result.ir.world is None


def test_build_ir_section_file_top_key_violation_stops_file() -> None:
    """用例 3e：节文件顶层键处置（W2-A2）——期望键缺失 → 1 条 LLMSIM_SCHEMA
    （refs = [期望键名, "missing"]）；实际顶层出现其他键 → 每键 1 条
    LLMSIM_UNKNOWN_KEY（refs = [键名]）；两族可同时出；该文件即停（不再做
    内层校验——内层即使违例也不追加诊断）。"""
    raw = _raw_with_game(
        _valid_game(),
        {"items/only.yaml": {"objects": [{"id": "Bad", "name": "内层也违例"}]}},
    )
    result = build_ir(raw)
    assert result.ir is None
    assert [(d.code, d.path, d.refs) for d in result.diagnostics] == [
        ("LLMSIM_SCHEMA", "items/only.yaml", ("items", "missing")),
        ("LLMSIM_UNKNOWN_KEY", "items/only.yaml", ("objects",)),
    ]
    # 仅多键（期望键在）：每键 1 条 UNKNOWN_KEY，同样即停
    raw = _raw_with_game(
        _valid_game(),
        {"rules/r.yaml": {"rules": [{"id": "Bad", "name": "n"}], "extra_key": 1, "zz_key": 2}},
    )
    result = build_ir(raw)
    assert result.ir is None
    assert [(d.code, d.path, d.refs) for d in result.diagnostics] == [
        ("LLMSIM_UNKNOWN_KEY", "rules/r.yaml", ("extra_key",)),
        ("LLMSIM_UNKNOWN_KEY", "rules/r.yaml", ("zz_key",)),
    ]


def test_build_ir_section_file_non_dict_root_yaml_parse() -> None:
    """用例 3f：节文件解析值根非 dict（内存 RawProject 形态）→ LLMSIM_YAML_PARSE
    （path = 相对路径，refs = ["root-not-dict"]，与 read_yaml_file 同码同 refs
    口径，LLMSIM_YAML_PARSE 码语义 "YAML 解析失败 / 根非 dict"）。"""
    raw = make_raw_project(
        files={"game.yaml": _valid_game(), "rules/x.yaml": ["not", "a", "dict"]}
    )
    result = build_ir(raw)
    assert result.ir is None
    assert [(d.code, d.path, d.refs) for d in result.diagnostics] == [
        ("LLMSIM_YAML_PARSE", "rules/x.yaml", ("root-not-dict",)),
    ]


def test_build_ir_game_yaml_missing_file_missing_double_safety() -> None:
    """用例 3g：game.yaml 缺失（raw.files 无该键）→ FILE_MISSING 双保险恰好
    1 条（path = "game.yaml"），ir = None，不 raise。"""
    raw = make_raw_project(files={"world/a_world.yaml": _world_file("A")})
    result = build_ir(raw)
    assert result.ir is None
    assert len(result.diagnostics) == 1
    d = result.diagnostics[0]
    assert (d.code, d.path, d.refs) == ("LLMSIM_FILE_MISSING", "game.yaml", ())
    assert d.severity == DiagnosticSeverity.ERROR


def test_build_ir_missing_required_section_schema_diagnostic_and_aggregation() -> None:
    """用例 3h：game.yaml 缺必需节 scenario → 恰好 1 条 LLMSIM_SCHEMA
    （refs = ["scenario", "missing"]，path = "game.yaml"）+ 节文件诊断继续
    聚合（全聚合不早退：步 2 失败后步 3 继续校验；诊断序 = 显式步序，
    game.yaml 步 2 在前、节文件按 LAYOUT_OPTIONAL 模板序在后，ERR-P5-13
    D6 裁定钉死全聚合口径）。"""
    game = _valid_game()
    del game["scenario"]
    raw = _raw_with_game(
        game,
        {"items/missing_id.yaml": {"items": [{"name": "no_id_item", "object_type": "tool"}]}},
    )
    result = build_ir(raw)
    # (a) 编译失败
    assert result.ir is None
    # (b) 恰好 1 条必需节缺失 SCHEMA（refs 逐字，path = "game.yaml"）
    schema_missing = [
        d
        for d in result.diagnostics
        if d.code == "LLMSIM_SCHEMA"
        and d.refs == ("scenario", "missing")
        and d.path == "game.yaml"
    ]
    assert len(schema_missing) == 1
    # (c) items 节文件诊断继续聚合（必需节缺失后步 3 继续校验，不早退）
    items_diags = [d for d in result.diagnostics if d.path == "items/missing_id.yaml"]
    assert len(items_diags) >= 1
    assert all(d.code == "LLMSIM_SCHEMA" for d in items_diags)
    # (d) 全诊断集 (code, path, refs) 精确序列（game.yaml 步 2 在前，节文件 LAYOUT_OPTIONAL 序）
    assert [(d.code, d.path, d.refs) for d in result.diagnostics] == [
        ("LLMSIM_SCHEMA", "game.yaml", ("scenario", "missing")),
        ("LLMSIM_SCHEMA", "items/missing_id.yaml", ("0.id", "missing")),
    ]


def test_flatten_entities_merge_order_duplicate_later_wins_and_casefold_key_order() -> None:
    """用例 4：flatten_entities 合并序（locations → items → characters →
    player by player_id，重复键后者覆盖，W2-A3）+ 返回 dict 键序 = 按
    (id.casefold(), id) 升序（id 词法为小写，casefold 为恒等，口径钉死）。"""
    loc_a = make_location(id="alpha_loc")
    loc_z = make_location(id="zeta_loc")
    item_a = make_item(id="alpha_item")
    item_z = make_item(id="zeta_loc")  # 与 location 重复 → items（后者）覆盖
    char_a = make_character(id="alpha_item")  # 与 item 重复 → characters（后者）覆盖
    char_c = make_character(id="char_one")
    player = make_player(player_id="char_one")  # 与 character 重复 → player（后者）覆盖
    ir = make_ir(
        world=make_world(locations=(loc_a, loc_z)),
        items=(item_a, item_z),
        characters=(char_a, char_c),
        player=player,
    )
    flat = flatten_entities(ir)
    assert list(flat) == ["alpha_item", "alpha_loc", "char_one", "zeta_loc"]
    assert list(flat) == sorted(flat, key=lambda key: (key.casefold(), key))
    assert flat["alpha_loc"] is loc_a
    assert flat["zeta_loc"] is item_z
    assert flat["alpha_item"] is char_a
    assert flat["char_one"] is player
    # world = None：locations 缺席，其余池不受影响
    solo_item = make_item(id="solo_item")
    ir_no_world = make_ir(
        items=(solo_item,),
        characters=(),
        player=make_player(player_id="player_solo"),
    )
    flat2 = flatten_entities(ir_no_world)
    assert list(flat2) == ["player_solo", "solo_item"]
    assert flat2["solo_item"] is solo_item
    assert flat2["player_solo"] is ir_no_world.player


def test_iter_entity_refs_all_ref_kinds_and_exact_order() -> None:
    """用例 5：iter_entity_refs 全引用类（connection / relationship / inventory
    三类各 ≥1 例）+ 精确序断言（W2-A4：IR 元组序 locations → characters → player；
    holder 内 connection → relationship → inventory；dict 插入序 / list 序）。"""
    ir = make_ir(
        world=make_world(
            locations=(
                make_location(id="room_a", connections={"east": "room_b", "north": "room_c"}),
                make_location(id="room_b"),
            )
        ),
        characters=(
            make_character(
                id="npc_one",
                relationships={"player_1": 0.5, "npc_two": 0.9},
                starting_inventory=["item_x", "item_y"],
            ),
        ),
        player=make_player(player_id="player_1", inventory=["item_y"]),
    )
    assert list(iter_entity_refs(ir)) == [
        ("room_a", "connection", "room_b"),
        ("room_a", "connection", "room_c"),
        ("npc_one", "relationship", "player_1"),
        ("npc_one", "relationship", "npc_two"),
        ("npc_one", "inventory", "item_x"),
        ("npc_one", "inventory", "item_y"),
        ("player_1", "inventory", "item_y"),
    ]
    assert {kind for _holder, kind, _value in iter_entity_refs(ir)} == {
        "connection",
        "relationship",
        "inventory",
    }
    # world = None 时 locations 引用缺席
    ir_no_world = make_ir(
        player=make_player(player_id="player_1", inventory=["item_z"]),
    )
    assert list(iter_entity_refs(ir_no_world)) == [("player_1", "inventory", "item_z")]


def test_ir_to_data_json_clean_hook_called_and_16_field_key_surface() -> None:
    """用例 6：ir_to_data = model_dump(mode="json") 嵌套展开 + 尾部
    assert_json_clean 机械钩子（K7 / P5-INV-7，实际调用不 raise）+ 返回 dict
    键面 = ProjectIR 16 字段闭集。"""
    result = build_ir(_full_raw())
    ir = result.ir
    assert ir is not None
    data = ir_to_data(ir)
    assert isinstance(data, dict)
    assert set(data) == EXPECTED_IR_FIELDS
    # K7 钩子实际调用不 raise（ir_to_data 尾部已机械调用；此处独立复验）
    assert_json_clean(data)
    # 嵌套展开为 JSON 原生值（枚举/模型 → 字面量）
    assert data["manifest"]["schema_version"] == "2"
    assert data["world"]["name"] == "Stone World"
    assert data["items"][0]["id"] == "rope"
    assert isinstance(data["characters"][0]["relationships"]["player_1"], float)


def test_canonical_yaml_double_dump_byte_stable_and_sorted_keys() -> None:
    """用例 7：canonical_yaml = yaml.safe_dump(sort_keys=True, allow_unicode=True,
    default_flow_style=False, width=100)（D-P5-14）；同 ir 两次调用字符串相等
    （双 dump 字节稳定，纯函数）+ sort_keys 效应（顶层键行字典序）+ 数据级
    round-trip 恒等（load(dump(ir)) == ir，断言 #20 同源）。"""
    result = build_ir(_full_raw())
    ir = result.ir
    assert ir is not None
    first = canonical_yaml(ir)
    second = canonical_yaml(ir)
    assert first == second
    # sort_keys 效应：顶层键行（无缩进）按字典序排列，键集 = 16 字段闭集
    top_keys = [line.split(":")[0] for line in first.splitlines() if _TOP_LEVEL_KEY_RE.match(line)]
    assert top_keys == sorted(top_keys)
    assert set(top_keys) == EXPECTED_IR_FIELDS
    # allow_unicode 效应：中文以 UTF-8 字面量落盘（非 \\uXXXX 转义）
    assert "石室" in first
    # 数据级 round-trip 恒等：ProjectIR.model_validate(safe_load(dump)) == ir
    ir2 = ProjectIR.model_validate(yaml.safe_load(first))
    assert ir2 == ir
    # 断言 #20 字面第二合取：再验证后重 dump 字节相等（ERR-P5-13 D6）
    assert canonical_yaml(ir2) == first
