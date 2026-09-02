"""P10 T04 image backend 平铺测试（SOT §6.1 t1–t8；8 函数）。

A 判据映射（§5.3）：A10 → t2（辅 t1/t3）；A1 单元面 = t6/t7（辅
t8）；t5 = 新鲜槽面；t4 = fake 回显 + intents 序钉；t1 含 AD-P10-2
对抗扩展断言（§6.3 并入），t6 含 AD-P10-3 stale 连发扩展循环（§6.3
并入）。零 wall-clock / 零随机（D6/K8）；世界 / 事件 / 脚本消费
``tests.engine_v2.presentation.conftest`` 冻结 fixture（跨波不改，
SOT §6.4）；stale 单元面 = 直接对 ImageSlot dict 调
``apply_image_result``（W2 落码 contract 面；不依赖 session 层
——session = W4）。
"""

from __future__ import annotations

import dataclasses
import json

import pytest

from src.engine_v2.core.revision import Revision
from src.engine_v2.presentation.image.backend import (
    DeterministicImageBackend,
    FakeImageBackend,
    render_intent_to_ppm,
)
from src.engine_v2.presentation.image.contract import (
    ImageArtifact,
    ImageSlot,
    ImageStalePolicy,
    apply_image_result,
)
from src.engine_v2.presentation.image.director import derive_render_intent
from src.engine_v2.presentation.view import SceneView, derive_scene_view


def _view_at_revision(fixture_world, revision: int) -> SceneView:
    """当前刻 = ``revision`` 的 SceneView 投影（私有构造缝隙，测试专用，
    state.py:333 口径；scene_key 面不随 revision 变 → scene_id 恒定）。"""
    world = fixture_world._with_world_revision(Revision(revision))
    return derive_scene_view(world)


def _artifact_at(revision: int, scene_id: str) -> ImageArtifact:
    """字面量 artifact 构造器（stale 单元面；零 uuid4）。"""
    return ImageArtifact(
        artifact_id=f"art_rev_{revision:03d}",
        scene_id=scene_id,
        view_revision=revision,
        media_type="image/x-ppm",
        payload=b"stale-payload",
        continuity_refs=(),
        style_refs=(),
    )


def _parse_ppm(payload: bytes) -> tuple[str, list[int]]:
    """PPM P3 解析（头部 + 分量面；非法 → AssertionError）。"""
    text = payload.decode("ascii")
    lines = text.split("\n")
    assert lines[0] == "P3"
    assert lines[2] == "255"
    width, height = (int(part) for part in lines[1].split(" "))
    components = [int(part) for part in text.split("\n", 3)[3].split()]
    assert len(components) == width * height * 3
    assert all(0 <= channel <= 255 for channel in components)
    return lines[1], components


def test_image_backend_t1_ppm_header_pin(scene_view) -> None:
    """A10 辅助：缺省 64×32 字节起首 ``"P3\\n64 32\\n255\\n"`` + 分量
    计数 == 64*32*3；width/height ≤ 0 → ValueError（SOT §3.5 钉）。
    AD-P10-2 并入扩展断言（§6.3）：空 subjects / 超长 unicode mood /
    异常 camera（非 JSON-clean 嵌套值）→ 合法 PPM（头部 + 分量可
    解析），零异常逃逸。"""
    intent = derive_render_intent(scene_view)
    payload = render_intent_to_ppm(intent)
    assert payload.startswith(b"P3\n64 32\n255\n")
    header, components = _parse_ppm(payload)
    assert header == "64 32"
    assert len(components) == 64 * 32 * 3

    # AD-P10-2 扩展断言（§6.3 并入 t1）
    empty_subjects = dataclasses.replace(intent, subjects=())
    payload_empty = render_intent_to_ppm(empty_subjects)
    assert payload_empty.startswith(b"P3\n64 32\n255\n")
    assert len(_parse_ppm(payload_empty)[1]) == 64 * 32 * 3

    long_mood = dataclasses.replace(intent, mood="紧张" * 200)
    payload_mood = render_intent_to_ppm(long_mood)
    assert payload_mood.startswith(b"P3\n64 32\n255\n")
    assert len(_parse_ppm(payload_mood)[1]) == 64 * 32 * 3

    weird_camera = dataclasses.replace(
        intent, camera={"nested": {"deep": object()}}
    )
    payload_camera = render_intent_to_ppm(weird_camera)
    assert payload_camera.startswith(b"P3\n64 32\n255\n")
    assert len(_parse_ppm(payload_camera)[1]) == 64 * 32 * 3

    # width/height ≤ 0 → ValueError（SOT §3.5 钉：纯函数面 + 构造面）
    with pytest.raises(ValueError):
        render_intent_to_ppm(intent, width=0, height=32)
    with pytest.raises(ValueError):
        render_intent_to_ppm(intent, width=64, height=-1)
    with pytest.raises(ValueError):
        DeterministicImageBackend(width=0)
    with pytest.raises(ValueError):
        DeterministicImageBackend(height=-32)


def test_image_backend_t2_determinism_rerun(scene_view) -> None:
    """A10：同 intent 双跑 bytes 相等（backend 面 + 纯函数面双钉；
    artifact 标签相等——artifact_id = 载荷哈希派生，零 uuid4）。"""
    intent = derive_render_intent(scene_view)
    backend = DeterministicImageBackend()
    artifact_a = backend.render(intent)
    artifact_b = backend.render(intent)
    assert artifact_a.payload == artifact_b.payload
    assert artifact_a.artifact_id == artifact_b.artifact_id
    assert artifact_a.scene_id == intent.scene_id
    assert artifact_a.view_revision == intent.view_revision
    assert artifact_a.media_type == "image/x-ppm"
    direct_a = render_intent_to_ppm(intent)
    direct_b = render_intent_to_ppm(intent)
    assert direct_a == direct_b
    assert artifact_a.payload == direct_a


def test_image_backend_t3_scene_sensitivity(scene_view) -> None:
    """T08 错场敏感面：同 intent 异 scene_id → bytes 异（scene_id
    参与全部颜色派生，SOT §3.5；backend 面 + 纯函数面双钉）。"""
    intent = derive_render_intent(scene_view)
    other = dataclasses.replace(intent, scene_id="scene:diffscene0000")
    assert render_intent_to_ppm(intent) != render_intent_to_ppm(other)
    backend = DeterministicImageBackend()
    assert backend.render(intent).payload != backend.render(other).payload


def test_image_backend_t4_fake_echo(scene_view) -> None:
    """fake 回显钉：payload = scene_id + 0x00 + view_revision；intents
    调用史 == 提交序（零像素逻辑）；artifact 标签 = intent 面值。"""
    intent = derive_render_intent(scene_view)
    fake = FakeImageBackend()
    assert fake.intents == ()
    artifact = fake.render(intent)
    assert artifact.payload == (
        intent.scene_id.encode("utf-8")
        + b"\x00"
        + str(intent.view_revision).encode("ascii")
    )
    assert artifact.scene_id == intent.scene_id
    assert artifact.view_revision == intent.view_revision
    assert artifact.continuity_refs == intent.continuity_refs
    assert artifact.style_refs == intent.style_refs
    assert artifact.media_type == "image/x-ppm"
    other = dataclasses.replace(intent, view_revision=intent.view_revision + 1)
    fake.render(other)
    assert fake.intents == (intent, other)


def test_image_backend_t5_fresh_slot(fixture_world) -> None:
    """新鲜 artifact（revision + scene_id == 当前 view）→ 槽
    stale==False / archived==False / view_revision==当前（W2 落码
    contract 面直接消费；零 session 依赖）。"""
    view = derive_scene_view(fixture_world)
    intent = derive_render_intent(view)
    artifact = DeterministicImageBackend().render(intent)
    slot = apply_image_result(None, artifact, view)
    assert slot is not None
    assert slot["stale"] is False
    assert slot["archived"] is False
    assert slot["view_revision"] == view["view_revision"]
    assert slot["scene_id"] == view["scene_id"]
    assert slot["artifact_id"] == artifact.artifact_id
    assert slot["media_type"] == "image/x-ppm"
    assert slot["byte_length"] == len(artifact.payload)
    json.dumps(slot)


def test_image_backend_t6_stale_discard_no_overwrite(fixture_world) -> None:
    """A1 单元面：83→87 DISCARD（默认）：无槽 → None；有槽 → 原槽
    逐键不变（零覆盖）。AD-P10-3 并入扩展循环（§6.3）：当前 87→88→
    89 推进中重复提交 revision 83 artifact → 恒 None / 恒原样（INV-2
    连续钉）。"""
    current = _view_at_revision(fixture_world, 87)
    stale = _artifact_at(83, current["scene_id"])
    assert apply_image_result(None, stale, current) is None

    existing: ImageSlot = {
        "artifact_id": "art_fresh_87",
        "scene_id": current["scene_id"],
        "view_revision": 87,
        "stale": False,
        "archived": False,
        "media_type": "image/x-ppm",
        "byte_length": 100,
    }
    untouched = apply_image_result(dict(existing), stale, current)
    assert untouched == existing

    # AD-P10-3：stale 连发（当前 87→88→89 推进，DISCARD 默认）
    none_slot = None
    for revision in (87, 88, 89):
        view = _view_at_revision(fixture_world, revision)
        none_slot = apply_image_result(
            none_slot, _artifact_at(83, view["scene_id"]), view
        )
    assert none_slot is None
    held = dict(existing)
    for revision in (87, 88, 89):
        view = _view_at_revision(fixture_world, revision)
        held = apply_image_result(held, _artifact_at(83, view["scene_id"]), view)
    assert held == existing  # 恒原样（零覆盖，INV-2）


def test_image_backend_t7_stale_display_flagged(fixture_world) -> None:
    """A1 单元面：83→87 DISPLAY：槽 view_revision==87（当前值，绝不
    以 83 覆盖）+ stale==True + archived==False；有槽面 → 新槽（槽
    恒随当前 view）。"""
    current = _view_at_revision(fixture_world, 87)
    stale = _artifact_at(83, current["scene_id"])
    slot = apply_image_result(None, stale, current, policy=ImageStalePolicy.DISPLAY)
    assert slot is not None
    assert slot["stale"] is True
    assert slot["archived"] is False
    assert slot["view_revision"] == 87
    assert slot["scene_id"] == stale.scene_id
    assert slot["artifact_id"] == stale.artifact_id
    assert slot["byte_length"] == len(stale.payload)

    existing: ImageSlot = {
        "artifact_id": "art_fresh_87",
        "scene_id": current["scene_id"],
        "view_revision": 87,
        "stale": False,
        "archived": False,
        "media_type": "image/x-ppm",
        "byte_length": 100,
    }
    flagged = apply_image_result(
        dict(existing), stale, current, policy=ImageStalePolicy.DISPLAY
    )
    assert flagged["stale"] is True
    assert flagged["archived"] is False
    assert flagged["view_revision"] == 87


def test_image_backend_t8_stale_archive(fixture_world) -> None:
    """A1 单元面 / INV-2：83→87 ARCHIVE：stale==True + archived==True
    + view_revision==87（当前值，零以过期刻覆盖）。"""
    current = _view_at_revision(fixture_world, 87)
    stale = _artifact_at(83, current["scene_id"])
    slot = apply_image_result(None, stale, current, policy=ImageStalePolicy.ARCHIVE)
    assert slot is not None
    assert slot["stale"] is True
    assert slot["archived"] is True
    assert slot["view_revision"] == 87
