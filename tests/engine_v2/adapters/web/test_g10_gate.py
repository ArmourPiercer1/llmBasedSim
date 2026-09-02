"""P10 G10 门自动 4 面 1:1 平铺函数（SOT §5.2 A1–A4；§6.1
test_g10_gate t1–t4 逐字面；每面恰 1 函数）。

- t1 (G10-1/A1) = 过期图像双面：DISCARD 零覆盖 + DISPLAY stale 标记
  且槽 revision 钉（纯函数面 apply_image_result，SOT §3.3）；
- t2 (G10-2/A2) = 同 SceneView → narrate_scene + derive_render_intent
  独立（双 backend 消费结构化 View 而非 prose）+ text/ ↔ image/ 零
  互 import（整文件面 AST）；
- t3 (G10-3/A3) = 零模块单例：16 py 文件 AST 零模块级 WorldState /
  SessionManager / WebSession / Scheduler / LogicalClock 实例化 + 零
  模块级 session / world 全局绑定（SC-P10-1 反钉）+ static 3 文件
  零构造器名字面量；
- t4 (G10-4/A4) = inspector 链定位器：inspect_event 端到端（event →
  transaction → effect → producer；链全经 TraceQuery，INV-5）。

纪律：全部面值 = 字面量或 fixture 面（零随机、零墙钟，D6）；t4 数据
源 = known_event_sequence 世界 + 五面 trace 注入会话（测试函数内
局部构造 = 合法面：W4 web conftest trace_manager_session 同构；
conftest 跨树 fixture 引用面不解析——零 conftest 修改）；事件 id =
P1 核心 uuid4 身份标签（既有 core 面）→ 经公开快照面取，零字面量
钉；行宽 ≤ 100（D2）。
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

from src.engine_v2.adapters.web.inspector import inspect_event
from src.engine_v2.adapters.web.session import SessionManager
from src.engine_v2.presentation.image.backend import DeterministicImageBackend
from src.engine_v2.presentation.image.contract import (
    ImageArtifact,
    ImageStalePolicy,
    apply_image_result,
)
from src.engine_v2.presentation.image.director import derive_render_intent
from src.engine_v2.presentation.text.narrator import narrate_scene
from src.engine_v2.presentation.view import derive_scene_view
from tests.engine_v2.adapters.web.conftest import HostTickDriver
from tests.engine_v2.presentation.conftest import (
    _run_known_sequence,
    make_p10_world,
)

REPO_ROOT = Path(__file__).resolve().parents[4]

#: G10-3 检查域 = v2 web/presentation 树 16 py 文件（D-P10-08；v1 树
#: 冻结反例锚不属检查域）。
_P10_PY_FILES: tuple[str, ...] = (
    "src/engine_v2/presentation/view.py",
    "src/engine_v2/presentation/text/__init__.py",
    "src/engine_v2/presentation/text/narrator.py",
    "src/engine_v2/presentation/image/__init__.py",
    "src/engine_v2/presentation/image/contract.py",
    "src/engine_v2/presentation/image/director.py",
    "src/engine_v2/presentation/image/backend.py",
    "src/engine_v2/presentation/tactical/__init__.py",
    "src/engine_v2/presentation/tactical/layout.py",
    "src/engine_v2/adapters/web/__init__.py",
    "src/engine_v2/adapters/web/session.py",
    "src/engine_v2/adapters/web/api.py",
    "src/engine_v2/adapters/web/inspector.py",
    "src/engine_v2/adapters/web/workbench.py",
    "src/engine_v2/adapters/web/views.py",
    "src/engine_v2/adapters/web/server.py",
)
_STATIC_FILES: tuple[str, ...] = (
    "src/engine_v2/adapters/web/static/index.html",
    "src/engine_v2/adapters/web/static/app.js",
    "src/engine_v2/adapters/web/static/styles.css",
)

#: 模块级单例构造器禁名单（G10-3 判据字面）。
_SINGLETON_CONSTRUCTORS: tuple[str, ...] = (
    "WorldState",
    "SessionManager",
    "WebSession",
    "Scheduler",
    "LogicalClock",
)

#: 模块级 session 全局绑定禁名（SC-P10-1 反钉：``session =
#: SessionManager()`` / ``world = WorldState(...)``）。
_GLOBAL_SESSION_BINDINGS: tuple[str, ...] = ("session", "world")


def _imported_modules(path: Path) -> list[str]:
    """AST 收集完整点分 import 模块名（锚文件同源口径）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
        elif isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
    return modules


def test_g10_gate_t1_stale_image_no_overwrite() -> None:
    """t1（G10-1/A1）：stale 双面——DISCARD 零覆盖（无槽 → None /
    有槽 → 逐键不变）+ DISPLAY stale 标记且槽 revision = 当前（绝不
    等于 artifact 旧值）。"""
    current_view = {"scene_id": "scene:stale_g10", "view_revision": 87}
    stale_artifact = ImageArtifact(
        artifact_id="art_g10_stale",
        scene_id="scene:stale_g10",
        view_revision=83,
        media_type="image/x-ppm",
        payload=b"P1\n1 1\n0 0 0\n",
        continuity_refs=(),
        style_refs=(),
    )
    # DISCARD（缺省）双面：
    assert apply_image_result(None, stale_artifact, current_view) is None
    current_slot = apply_image_result(
        None,
        ImageArtifact(
            artifact_id="art_g10_current",
            scene_id="scene:stale_g10",
            view_revision=87,
            media_type="image/x-ppm",
            payload=b"P1\n1 1\n1 1 1\n",
            continuity_refs=(),
            style_refs=(),
        ),
        current_view,
    )
    assert current_slot is not None
    assert current_slot["stale"] is False
    discarded = apply_image_result(current_slot, stale_artifact, current_view)
    assert discarded == current_slot  # 零覆盖：逐键不变
    # DISPLAY 面：stale 标记 + 槽 revision = 当前（钉）：
    displayed = apply_image_result(
        current_slot, stale_artifact, current_view, policy=ImageStalePolicy.DISPLAY
    )
    assert displayed is not None
    assert displayed["stale"] is True
    assert displayed["view_revision"] == 87
    assert displayed["artifact_id"] == "art_g10_stale"


def test_g10_gate_t2_dual_backend_structured_view() -> None:
    """t2（G10-2/A2）：同 SceneView → narrate_scene +
    derive_render_intent 独立产出 + JSON-clean + text/ ↔ image/ 零
    互 import（整文件面 AST）。"""
    view = derive_scene_view(make_p10_world())
    text_artifact = narrate_scene(view)
    intent = derive_render_intent(view)
    assert text_artifact.source == "template"
    assert text_artifact.view_revision == view["view_revision"]
    assert intent.scene_id == view["scene_id"]
    assert intent.view_revision == view["view_revision"]
    json.dumps(text_artifact.to_dict(), ensure_ascii=False)
    json.dumps(intent.to_dict(), ensure_ascii=False)
    # A2 特例钉：presentation/text/ ↔ presentation/image/ 零互 import。
    for rel in (
        "src/engine_v2/presentation/text/__init__.py",
        "src/engine_v2/presentation/text/narrator.py",
    ):
        for module in _imported_modules(REPO_ROOT / rel):
            assert not module.startswith("src.engine_v2.presentation.image"), (
                rel,
                module,
            )
    for rel in (
        "src/engine_v2/presentation/image/__init__.py",
        "src/engine_v2/presentation/image/contract.py",
        "src/engine_v2/presentation/image/director.py",
        "src/engine_v2/presentation/image/backend.py",
    ):
        for module in _imported_modules(REPO_ROOT / rel):
            assert not module.startswith("src.engine_v2.presentation.text"), (
                rel,
                module,
            )


def test_g10_gate_t3_no_module_singleton_world() -> None:
    """t3（G10-3/A3）：零模块单例 World——16 py 文件 AST 零模块级
    构造器实例化 + 零模块级 session / world 全局绑定；static 3 文件
    零构造器名字面量。"""
    for rel in _P10_PY_FILES:
        path = REPO_ROOT / rel
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:  # 模块级 only（嵌套 = 函数/类内，合法）
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                func = node.value.func
                name = func.id if isinstance(func, ast.Name) else None
                assert name not in _SINGLETON_CONSTRUCTORS, (rel, name)
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                value = node.value
                if isinstance(value, ast.Call):
                    func = value.func
                    name = func.id if isinstance(func, ast.Name) else None
                    assert name not in _SINGLETON_CONSTRUCTORS, (rel, name)
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    if isinstance(target, ast.Name):
                        assert target.id not in _GLOBAL_SESSION_BINDINGS, (
                            rel,
                            target.id,
                        )
    for rel in _STATIC_FILES:
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        for ctor in _SINGLETON_CONSTRUCTORS:
            assert ctor not in text, (rel, ctor)


def _trace_session():
    """known_event_sequence 世界 + trace_records 注入会话（SOT §6.2
    同构面；测试函数内局部构造 = 合法面；显式 session_id，
    DEV-P10-05）。"""
    sequence = _run_known_sequence(make_p10_world())
    manager = SessionManager(
        driver_factory=lambda: HostTickDriver(),
        image_backend_factory=lambda: DeterministicImageBackend(),
    )
    session_id = manager.create_session(
        sequence.world,
        session_id="sess_w5_g10_t4",
        driver=HostTickDriver(sequence.world),
        trace_records=sequence.trace_records,
    )
    return manager.get(session_id)


def test_g10_gate_t4_inspector_chain_locator() -> None:
    """t4（G10-4/A4）：inspector 能定位 event → transaction → effect
    → producer（链全经 TraceQuery，INV-5 合规）。"""
    session = _trace_session()
    recent_events = session.state_snapshot()["recent_events"]
    assert len(recent_events) >= 1
    event_id = recent_events[-1]["event_id"]
    chain = inspect_event(session, event_id)
    assert chain["event"]["event_id"] == event_id
    assert chain["transaction"] is not None
    assert len(chain["effects"]) >= 1
    assert len(chain["producers"]) >= 1
    assert len(chain["action_refs"]) >= 1
