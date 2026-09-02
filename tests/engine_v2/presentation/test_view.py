"""P10 T01 SceneView 派生平铺测试（SOT §6.1 t1–t7；7 函数）。

A 判据映射（§5.3）：A5 → t1 / A6 → t2（辅 t7）/ A7 → t6（辅 t4）；
t3 = P10-INV-1 零反作用辅面，t5 = D-P10-12 scene_id 稳定辅面。
零 wall-clock / 零随机（D6/K8）；世界 / 事件 / 脚本消费
``tests.engine_v2.presentation.conftest`` 冻结 fixture。
"""

from __future__ import annotations

import json

import pytest

from src.engine_v2.core.revision import Revision, is_stale
from src.engine_v2.modules.narration import NarrativeView
from src.engine_v2.presentation.view import (
    PresentationError,
    VIEW_SCHEMA_VERSION,
    derive_scene_view,
    scene_id_of,
)
from tests.engine_v2.presentation.conftest import (
    _NPC_ID,
    _PLAYER_ID,
    make_fixture_runtime,
    make_p10_world,
    world_hash,
)


def test_view_t1_deterministic_derive(fixture_world) -> None:
    """A5：同 world 双跑 → SceneView ``json.dumps`` 字符串相等。"""
    view_a = derive_scene_view(fixture_world)
    view_b = derive_scene_view(fixture_world)
    assert json.dumps(view_a) == json.dumps(view_b)
    assert json.dumps(view_a, ensure_ascii=False) == json.dumps(
        view_b, ensure_ascii=False
    )


def test_view_t2_view_revision_projection(fixture_world, known_event_sequence) -> None:
    """A6：view.view_revision == world.world_revision；tick 推进严格递增。"""
    view = derive_scene_view(fixture_world)
    assert view["view_revision"] == int(fixture_world.world_revision)
    assert view["tick"] == 0

    # 3 commit 驱动世界（revision 3）→ view_revision 同步投影
    sequence_world = known_event_sequence.world
    assert derive_scene_view(sequence_world)["view_revision"] == 3
    assert int(sequence_world.world_revision) == 3

    # tick 推进严格递增（宿主侧世界事实投影缝隙；P1 D-6 口径）
    view_base = derive_scene_view(fixture_world)
    ticked_2 = fixture_world._with_world_variables(
        {**fixture_world.world_variables, "logical_tick": 2}
    )
    ticked_5 = fixture_world._with_world_variables(
        {**fixture_world.world_variables, "logical_tick": 5}
    )
    view_2 = derive_scene_view(ticked_2)
    view_5 = derive_scene_view(ticked_5)
    assert view_2["tick"] == 2 > view_base["tick"]
    assert view_5["tick"] == 5 > view_2["tick"]
    # tick 推进不推进 world_revision（P1 D-5 / D-P2-18 同源）
    assert view_5["view_revision"] == view_base["view_revision"]


def test_view_t3_zero_reverse_action(fixture_world) -> None:
    """P10-INV-1：改 view（含嵌套 dict）→ 世界哈希不变（零反作用）。"""
    runtime = make_fixture_runtime()
    before = world_hash(fixture_world, runtime)
    view = derive_scene_view(fixture_world)
    view["schema"] = 99
    view["narrative"]["scene_text"] = "篡改"
    view["narrative"]["frames"].append({"tick": 1, "speaker_id": "x", "text": "y"})
    view["narrative"]["clock"]["tick"] = 999
    view["actors"][0]["mood"] = "篡改"
    view["actors"][0]["position"]["hex"] = "hex_2_2"
    view["actors"][0]["tags"].append("注入")
    view["environment"]["weather"] = "篡改"
    view["image_slot"] = {"artifact_id": "art_tamper"}
    view["clock"]["logical_tick"] = 999
    view["clock"]["game_time"]["day"] = 99
    after = world_hash(fixture_world, runtime)
    assert before == after


def test_view_t4_json_clean(scene_view) -> None:
    """A7 辅面：10 键齐全 + ``json.dumps`` 零失败（P10-INV-10）。"""
    expected_keys = {
        "schema",
        "view_revision",
        "scene_id",
        "tick",
        "narrative",
        "actors",
        "environment",
        "tactical_overlay",
        "image_slot",
        "clock",
    }
    assert set(scene_view) == expected_keys
    assert scene_view["schema"] == VIEW_SCHEMA_VERSION
    assert scene_view["image_slot"] is None
    assert scene_view["tactical_overlay"] is None
    json.dumps(scene_view)
    json.dumps(scene_view, ensure_ascii=False)


def test_view_t5_scene_id_stability(fixture_world) -> None:
    """D-P10-12：同 location 同 actor 集 → 同 scene_id；actor 集变化 /
    location 变化 → 异 id；actor 集序变（插入序不同）→ 仍同 id（排序
    元组归一）；空 scene_key → PresentationError(code=
    "scene_key_invalid")。"""
    base = derive_scene_view(fixture_world)
    same = derive_scene_view(make_p10_world())
    assert same["scene_id"] == base["scene_id"]

    reordered = derive_scene_view(make_p10_world(actor_ids=(_NPC_ID, _PLAYER_ID)))
    assert reordered["scene_id"] == base["scene_id"]

    assert derive_scene_view(make_p10_world(actor_ids=(_PLAYER_ID,)))["scene_id"] != (
        base["scene_id"]
    )
    assert derive_scene_view(
        make_p10_world(location_id="ent_authoring_warehouse")
    )["scene_id"] != base["scene_id"]

    with pytest.raises(PresentationError) as excinfo:
        scene_id_of(())
    assert excinfo.value.code == "scene_key_invalid"


def test_view_t6_narrative_surface_compat(scene_view) -> None:
    """A7：view.narrative 键集 == P9 NarrativeView 5 键逐字
    （tick / scene_text / frames / actors_visible / clock）。"""
    narrative = scene_view["narrative"]
    assert set(narrative) == {"tick", "scene_text", "frames", "actors_visible", "clock"}
    assert set(narrative) == set(NarrativeView.__annotations__)


def test_view_t7_stale_projection() -> None:
    """A6 辅面：core 冻结 ``is_stale`` 投影判据（base < current → True；
    同刻 False；current < base 倒序 False——Revision 单调序）。"""
    assert is_stale(Revision(83), Revision(87)) is True
    assert is_stale(Revision(87), Revision(87)) is False
    assert is_stale(Revision(87), Revision(83)) is False
