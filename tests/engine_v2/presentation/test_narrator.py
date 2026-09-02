"""P10 T02 Narrator presentation backend 平铺测试（SOT §6.1 t1–t5；5
函数）。

A 判据映射（§5.3）：A8 → t2（辅助 t1）；t3 = Spec §32.3 必带标签纪律
text 侧钉；t4 = D6 双跑钉；t5 = A2 单元面（AST：text/ 文件 import
零 ``presentation.image.*``）。零 wall-clock / 零随机（D6/K8）；世界 /
事件 / 脚本消费 ``tests.engine_v2.presentation.conftest`` 冻结 fixture
（跨波不改，SOT §6.4）；额外脚本键只可在测试函数内局部构造
FakeInferenceBackend（零 conftest 修改，SOT §6.4 纪律）；显式 id，零
uuid4 默认路径（DEV-P10-05 精神）。
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

from src.engine_v2.core.revision import Revision
from src.engine_v2.llm.adapter import FakeInferenceBackend
from src.engine_v2.presentation.text.narrator import (
    NARRATOR_LOGICAL_ROLE,
    TEXT_SOURCES,
    narrate_scene,
)
from src.engine_v2.presentation.view import derive_scene_view
from tests.engine_v2.presentation.conftest import _NARRATOR_SCRIPT_TEXT

_REPO_ROOT = Path(__file__).resolve().parents[3]
_TEXT_PACKAGE_DIR = _REPO_ROOT / "src" / "engine_v2" / "presentation" / "text"
_TEXT_PACKAGE_FILES: tuple[str, ...] = ("__init__.py", "narrator.py")

#: t1 探针脚本文本（K8-safe 面值；「会命中但未被调用」钉面消费）。
_T1_PROBE_TEXT = "探针脚本命中文本"


def _import_module_names(tree: ast.AST, file_package: str) -> list[str]:
    """文件全部 import 模块名（绝对形式；相对 import 按文件包解析）。"""
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                modules.append(node.module or "")
            else:
                parts = file_package.split(".")
                base = ".".join(parts[: len(parts) - (node.level - 1)])
                modules.append(f"{base}.{node.module}" if node.module else base)
    return modules


def test_narrator_t1_template_zero_backend(scene_view) -> None:
    """A8 辅助 / K5：template 路径零推理调用——backend=None（§3.2
    路径选择）；探针 FakeInferenceBackend（脚本预置当前 view revision +
    seq 1 会命中键、未注入）calls == ()；source == template；
    text = 确定性模板（零帧 → 纯 scene_text）。"""
    fake = FakeInferenceBackend(
        script={
            (
                NARRATOR_LOGICAL_ROLE,
                Revision(int(scene_view["view_revision"])),
                1,
            ): _T1_PROBE_TEXT
        }
    )
    artifact = narrate_scene(scene_view)
    assert fake.calls == ()
    assert artifact.source == TEXT_SOURCES[0]
    assert artifact.text == scene_view["narrative"]["scene_text"]


def test_narrator_t2_scripted_llm_path(known_event_sequence, script_backend) -> None:
    """A8：脚本 (narrator, Revision(2), 1) 命中 → text 含命中文本 +
    source == "llm"（TEXT_SOURCES[1]）；调用面钉（logical_role /
    base_revision，P6 冻结面 FakeInferenceBackend 脚本键同址）。"""
    view = derive_scene_view(known_event_sequence.worlds[1])
    assert view["view_revision"] == 2
    artifact = narrate_scene(view, backend=script_backend)
    assert artifact.source == TEXT_SOURCES[1]
    assert _NARRATOR_SCRIPT_TEXT in artifact.text
    calls = script_backend.calls
    assert len(calls) == 1
    assert calls[0].logical_role == NARRATOR_LOGICAL_ROLE
    assert calls[0].base_revision == Revision(2)


def test_narrator_t3_artifact_tagged(scene_view) -> None:
    """artifact.view_revision / scene_id == view 面值（Spec §32.3 必带
    标签纪律 text 侧）；source ∈ TEXT_SOURCES；to_dict JSON-clean
    （新建容器，零别名）。"""
    artifact = narrate_scene(scene_view)
    assert artifact.view_revision == scene_view["view_revision"]
    assert artifact.scene_id == scene_view["scene_id"]
    assert artifact.source in TEXT_SOURCES
    payload = artifact.to_dict()
    json.dumps(payload)
    json.dumps(payload, ensure_ascii=False)
    payload["frames"].append({"injected": 1})
    payload["text"] = "篡改"
    assert artifact.frames == ()
    assert artifact.text == scene_view["narrative"]["scene_text"]


def test_narrator_t4_determinism_rerun(scene_view) -> None:
    """D6：同 view 双跑 → TextArtifact 字段相等 + json.dumps 相等
    （template 路径，零推理调用双跑）。"""
    artifact_a = narrate_scene(scene_view)
    artifact_b = narrate_scene(scene_view)
    assert artifact_a == artifact_b
    assert json.dumps(artifact_a.to_dict()) == json.dumps(artifact_b.to_dict())


def test_narrator_t5_no_image_import() -> None:
    """A2 单元面：AST——text/ 文件 import 零 ``presentation.image.*``
    （绝对 + 相对 import 双面，SOT §3.0 特例钉）。"""
    for name in _TEXT_PACKAGE_FILES:
        path = _TEXT_PACKAGE_DIR / name
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        modules = _import_module_names(tree, "src.engine_v2.presentation.text")
        offenders = [
            module
            for module in modules
            if module.startswith("src.engine_v2.presentation.image")
        ]
        assert not offenders, f"{name} import presentation.image/*：{offenders}"
