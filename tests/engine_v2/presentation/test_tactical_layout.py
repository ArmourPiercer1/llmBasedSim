"""P10 T04 波 tactical 布局平铺测试（SOT §6.1 t1–t3；3 函数）。

A 判据映射（§5.3）：A11 → t1（辅 t2/t3）；t3 = P10-INV-1 零反作用
辅面。零 wall-clock / 零随机（D6/K8）；世界 / 事件 / 脚本消费
``tests.engine_v2.presentation.conftest`` 冻结 fixture（跨波不改，
SOT §6.4）；几何事实宿主镜像 = 测试函数内局部经
``_with_world_variables`` 构造（conftest 冻结零修改，SOT §6.4 纪律
同形）；hex 域 3×3 = GraphSpace（P9 A12 钉值 16 无向边参照），grid
域 = GridSpace(3,3) 对照（conftest 世界构建面同值）。
"""

from __future__ import annotations

import json

import pytest

from src.engine_v2.modules.space import HexGrid, hex_adjacency
from src.engine_v2.presentation.tactical.layout import (
    TACTICAL_LAYOUT_SCHEMA_VERSION,
    _SPACES_FACT_KEY,
    _TacticalLayoutError,
    build_tactical_layout,
)
from tests.engine_v2.presentation.conftest import (
    _GRID_DOMAIN,
    _HEX_DOMAIN,
    make_fixture_runtime,
    world_hash,
)


def _hex_fact() -> dict[str, object]:
    """hex 3×3 几何事实（P9 A12 钉值参照：16 无向边；节点
    ``hex_<c>_<r>`` 0 基，conftest 世界构建面同序）。"""
    directed = hex_adjacency(HexGrid(cols=3, rows=3))
    undirected = sorted({(min(a, b), max(a, b)) for a, b in directed})
    assert len(undirected) == 16
    return {
        "kind": "graph",
        "nodes": [f"hex_{c}_{r}" for c in range(3) for r in range(3)],
        "edges": [list(edge) for edge in undirected],
    }


def _grid_fact() -> dict[str, object]:
    """grid 3×3 几何事实（conftest GridSpace(3,3) 对照域同值）。"""
    return {"kind": "grid", "cols": 3, "rows": 3}


def _world_with_facts(fixture_world, facts: dict[str, dict[str, object]]):
    """几何事实宿主镜像世界（测试函数内局部构造；conftest 冻结零
    修改，SOT §6.4 纪律同形）。"""
    return fixture_world._with_world_variables(
        {**fixture_world.world_variables, _SPACES_FACT_KEY: facts}
    )


def test_tactical_layout_t1_hex_layout(fixture_world) -> None:
    """A11：hex GraphSpace 3×3 域 → grid.nodes/edges 摘要（16 无向
    边，P9 A12 钉值参照）+ cells + actors 钉 + JSON-clean；域缺席
    （fixture 世界无几何事实且 "default" 域无位置映射）→ 错误族
    （code="scene_key_invalid"，§3.6 钉面）。"""
    world = _world_with_facts(fixture_world, {_HEX_DOMAIN: _hex_fact()})
    layout = build_tactical_layout(world, domain_id=_HEX_DOMAIN)
    assert layout["schema"] == TACTICAL_LAYOUT_SCHEMA_VERSION
    assert layout["view_revision"] == int(fixture_world.world_revision)
    assert layout["domain_id"] == _HEX_DOMAIN
    assert layout["grid"] == {
        "nodes": sorted(f"hex_{c}_{r}" for c in range(3) for r in range(3)),
        "edges": _hex_fact()["edges"],
    }
    # cells = 占据单元格（actor id 排序序：npc → player）
    assert layout["cells"] == [{"node": "hex_0_1"}, {"node": "hex_1_1"}]
    # actors = 域内 actor 位置面（{"id","position"}）
    assert layout["actors"] == [
        {"id": "ent_authoring_npc", "position": "hex_0_1"},
        {"id": "ent_authoring_player", "position": "hex_1_1"},
    ]
    assert layout["mode"] is None
    json.dumps(layout)
    json.dumps(layout, ensure_ascii=False)

    # 域缺席（§3.6 钉面：code="scene_key_invalid"；缺省域 + 显式缺席域）
    with pytest.raises(_TacticalLayoutError) as excinfo:
        build_tactical_layout(fixture_world)
    assert excinfo.value.code == "scene_key_invalid"
    with pytest.raises(_TacticalLayoutError) as other:
        build_tactical_layout(fixture_world, domain_id="nowhere")
    assert other.value.code == "scene_key_invalid"


def test_tactical_layout_t2_grid_layout(fixture_world) -> None:
    """A11 辅助：GridSpace 域 → grid = {"cols","rows"} + 位置钉
    （actor id 排序：npc → player）。"""
    world = _world_with_facts(fixture_world, {_GRID_DOMAIN: _grid_fact()})
    layout = build_tactical_layout(world, domain_id=_GRID_DOMAIN)
    assert layout["domain_id"] == _GRID_DOMAIN
    assert layout["grid"] == {"cols": 3, "rows": 3}
    assert layout["cells"] == [{"x": 0, "y": 1}, {"x": 1, "y": 1}]
    assert layout["actors"] == [
        {"id": "ent_authoring_npc", "position": {"x": 0, "y": 1}},
        {"id": "ent_authoring_player", "position": {"x": 1, "y": 1}},
    ]
    json.dumps(layout)


def test_tactical_layout_t3_zero_reverse_action(fixture_world) -> None:
    """A11 辅助 / P10-INV-1：修改 layout（含嵌套 dict）→ 世界哈希
    不变（零反作用；返回容器与 WorldState 零别名）。"""
    world = _world_with_facts(fixture_world, {_HEX_DOMAIN: _hex_fact()})
    runtime = make_fixture_runtime()
    before = world_hash(world, runtime)
    layout = build_tactical_layout(world, domain_id=_HEX_DOMAIN)
    layout["schema"] = 99
    layout["view_revision"] = 999
    layout["domain_id"] = "篡改"
    layout["grid"]["nodes"].append("hex_9_9")
    layout["grid"]["edges"].append(["hex_9_9", "hex_0_0"])
    layout["cells"].append({"node": "hex_9_9"})
    layout["actors"][0]["position"] = "hex_9_9"
    layout["mode"] = {"active_modes": ["injected"]}
    after = world_hash(world, runtime)
    assert before == after
