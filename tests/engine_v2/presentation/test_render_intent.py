"""P10 T03 RenderIntent 契约平铺测试（SOT §6.1 t1–t5；5 函数）。

A 判据映射（§5.3）：A9 → t1（辅助 t5）；t2 = D6 双跑钉；t3 = 脚本命中
8 字段落位 + 坏 JSON 错误族钉（SOT §3.4 8 字段校验违例面）；t4 = T08
continuity_refs 尾 3 窗口钉（SOT §3.4「尾 ≤3 条」语义面）。零
wall-clock / 零随机（D6/K8）；世界 / 事件 / 脚本消费
``tests.engine_v2.presentation.conftest`` 冻结 fixture（跨波不改，SOT
§6.4）；额外脚本键只可在测试函数内局部构造 FakeInferenceBackend（零
conftest 修改，SOT §6.4 纪律）；显式 id，零 uuid4 默认路径
（DEV-P10-05 精神）。
"""

from __future__ import annotations

import dataclasses
import json

import pytest

from src.engine_v2.core.revision import Revision
from src.engine_v2.llm.adapter import FakeInferenceBackend
from src.engine_v2.presentation.image.contract import RenderIntent
from src.engine_v2.presentation.image.director import (
    VISUAL_DIRECTOR_LOGICAL_ROLE,
    derive_render_intent,
)
from src.engine_v2.presentation.view import PresentationError, derive_scene_view
from tests.engine_v2.presentation.conftest import _DIRECTOR_SCRIPT_INTENT


def _history_intent(index: int) -> RenderIntent:
    """t4 历史意图构造器（字面量 scene_id，零 uuid4）。"""
    return RenderIntent(
        scene_id=f"scene:hist{index:08d}",
        view_revision=index,
        subjects=(),
        environment={},
        camera={},
        mood="calm",
        continuity_refs=(),
        style_refs=(),
    )


def test_render_intent_t1_eight_fields_spec() -> None:
    """A9：8 字段 == Spec §32.2（L1698–1713）逐字序（名 + 形）。"""
    names = [field.name for field in dataclasses.fields(RenderIntent)]
    assert names == [
        "scene_id",
        "view_revision",
        "subjects",
        "environment",
        "camera",
        "mood",
        "continuity_refs",
        "style_refs",
    ]
    intent = RenderIntent(
        scene_id="scene:spec00000000",
        view_revision=7,
        subjects=(),
        environment={},
        camera={},
        mood="calm",
        continuity_refs=(),
        style_refs=(),
    )
    assert isinstance(intent.scene_id, str)
    assert isinstance(intent.view_revision, int)
    assert isinstance(intent.subjects, tuple)
    assert isinstance(intent.environment, dict)
    assert isinstance(intent.camera, dict)
    assert isinstance(intent.mood, str)
    assert isinstance(intent.continuity_refs, tuple)
    assert isinstance(intent.style_refs, tuple)


def test_render_intent_t2_determinism_rerun(scene_view) -> None:
    """D6：同 view 双跑 → intent 相等（template 路径，零推理调用）。"""
    intent_a = derive_render_intent(scene_view)
    intent_b = derive_render_intent(scene_view)
    assert intent_a == intent_b
    assert json.dumps(intent_a.to_dict()) == json.dumps(intent_b.to_dict())


def test_render_intent_t3_scripted_llm_path(known_event_sequence, script_backend) -> None:
    """脚本 JSON 命中 → 8 字段落位（逐值 == conftest 脚本钉，SOT §6.4）；
    坏 JSON / 键面违例 → PresentationError（code="intent_schema_invalid"，
    SOT §3.4；额外脚本键 = 测试函数内局部 FakeInferenceBackend，零
    conftest 修改）。"""
    view = derive_scene_view(known_event_sequence.worlds[1])
    intent = derive_render_intent(view, backend=script_backend)
    script = _DIRECTOR_SCRIPT_INTENT
    assert intent.scene_id == script["scene_id"]
    assert intent.view_revision == int(script["view_revision"])
    assert [dict(subject) for subject in intent.subjects] == script["subjects"]
    assert intent.environment == script["environment"]
    assert intent.camera == script["camera"]
    assert intent.mood == script["mood"]
    assert intent.continuity_refs == tuple(script["continuity_refs"])
    assert intent.style_refs == tuple(script["style_refs"])
    # 调用面钉：恰 1 次调用，脚本键 (visual_director, Revision(2), seq 1)
    calls = script_backend.calls
    assert len(calls) == 1
    assert calls[0].logical_role == VISUAL_DIRECTOR_LOGICAL_ROLE
    assert calls[0].base_revision == Revision(2)
    # 坏 JSON → 错误族
    bad_backend = FakeInferenceBackend(
        script={(VISUAL_DIRECTOR_LOGICAL_ROLE, Revision(2), 1): "not a json object"}
    )
    with pytest.raises(PresentationError) as excinfo:
        derive_render_intent(view, backend=bad_backend)
    assert excinfo.value.code == "intent_schema_invalid"
    # 键面违例（缺键/多键）→ 同错误族（SOT §3.4 8 字段校验面）
    shape_backend = FakeInferenceBackend(
        script={
            (VISUAL_DIRECTOR_LOGICAL_ROLE, Revision(2), 1): (
                '{"scene_id": "scene:only_one_field"}'
            )
        }
    )
    with pytest.raises(PresentationError) as shape_excinfo:
        derive_render_intent(view, backend=shape_backend)
    assert shape_excinfo.value.code == "intent_schema_invalid"


def test_render_intent_t4_continuity_refs(scene_view) -> None:
    """T08：传 3 条历史 intent → continuity_refs == 尾 3 scene_id 序；
    超 3 条 → 尾 3 窗口（SOT §3.4「尾 ≤3 条」语义面）；其余字段保持
    template 投影面（continuity 只影响 refs）。"""
    history = tuple(_history_intent(index) for index in (1, 2, 3))
    intent = derive_render_intent(scene_view, continuity=history)
    assert intent.continuity_refs == (
        "scene:hist00000001",
        "scene:hist00000002",
        "scene:hist00000003",
    )
    assert intent.scene_id == scene_view["scene_id"]
    assert intent.view_revision == scene_view["view_revision"]
    window = tuple(_history_intent(index) for index in (1, 2, 3, 4, 5))
    assert (
        derive_render_intent(scene_view, continuity=window).continuity_refs
        == (
            "scene:hist00000003",
            "scene:hist00000004",
            "scene:hist00000005",
        )
    )


def test_render_intent_t5_json_clean(scene_view) -> None:
    """A9 辅助：to_dict 8 键在位 + json.dumps 零失败（P10-INV-10；
    fixture 环境面含 CJK 值，ensure_ascii=False 双面钉）。"""
    intent = derive_render_intent(scene_view)
    payload = intent.to_dict()
    assert set(payload) == {
        "scene_id",
        "view_revision",
        "subjects",
        "environment",
        "camera",
        "mood",
        "continuity_refs",
        "style_refs",
    }
    json.dumps(payload)
    json.dumps(payload, ensure_ascii=False)
