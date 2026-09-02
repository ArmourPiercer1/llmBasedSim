"""P10 面测试（SOT §6.1 test_p10_face t1–t6 逐字面；白名单行 35 A）。

- t1 = src 树闭集：presentation/ + adapters/web/ 文件集 == 白名单行
  1–19（19 项；既有占位二件套属冻结面，边界 m6 哈希钉，不计）；
- t2 = 49 名导出台账逐字（§8.2 逐模块 ``__all__`` 名 + 序，12 模块
  49 名）；
- t3 = 19 src 文件字符串字面量（含 docstring）× 12 名黑名单零命中，
  唯一允许命中 = narrator.py TEXT_SOURCES 钉元组（ERR-P10-10）；
- t4 = import 闭集 AST（19 src 文件根闭集 ⊆ SOT §3.0：stdlib /
  pydantic / core / llm.adapter / persistence.snapshot /
  devtools.trace_query / presentation.* / adapters.web；http.server
  仅 server.py；jinja2 / 图像库 / v1 src.* 零；random-time-datetime-
  timeit 零（ERR-P10-07）；text/ ↔ image/ 零互 import；inspector /
  workbench 零 core.entity / core.components 直读（INV-5 特例钉）；
  engine_v2 全树零 langgraph/langchain）；
- t5 = 19 src 文件零裸 0x5C 0x62 字节（D3）；
- t6 = 零前端构建产物：src/ 全树零 package.json 三件 / vite.config.*
  / webpack*；static == 3 文件闭集；app.js 零 import / require /
  document.write。

纪律：全部判定 = 磁盘 AST / 字节面（零运行时 import 业务模块——t2
台账核对为唯一 importlib 面）；词边界转义经 ``chr(92) + "b"`` 运行
时构造（零裸 0x5C 0x62，D3 同源纪律）；行宽 ≤ 100（D2）。
"""

from __future__ import annotations

import ast
import importlib
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]

#: 词边界转义（零裸 0x5C 0x62 纪律，锚文件同源）。
_WB = chr(92) + "b"

#: 白名单行 1–19（19 项；presentation 9 + adapters/web 7 + static 3）。
_P10_SRC_FILES: tuple[str, ...] = (
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
    "src/engine_v2/adapters/web/static/index.html",
    "src/engine_v2/adapters/web/static/app.js",
    "src/engine_v2/adapters/web/static/styles.css",
)

#: 12 模块 49 名导出台账（§8.2 逐字；__all__ 名 + 序钉）。
_EXPORT_LEDGER: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "src.engine_v2.presentation.view",
        (
            "PresentationError",
            "VIEW_SCHEMA_VERSION",
            "SceneView",
            "scene_id_of",
            "derive_scene_view",
        ),
    ),
    (
        "src.engine_v2.presentation.text.narrator",
        (
            "NARRATOR_LOGICAL_ROLE",
            "TEXT_SOURCES",
            "TextArtifact",
            "NarratorPresentationBackend",
            "narrate_scene",
        ),
    ),
    (
        "src.engine_v2.presentation.image.contract",
        (
            "RENDER_INTENT_SCHEMA_VERSION",
            "ImageStalePolicy",
            "RenderIntent",
            "ImageArtifact",
            "ImageSlot",
            "apply_image_result",
        ),
    ),
    (
        "src.engine_v2.presentation.image.director",
        (
            "VISUAL_DIRECTOR_LOGICAL_ROLE",
            "VisualDirector",
            "derive_render_intent",
        ),
    ),
    (
        "src.engine_v2.presentation.image.backend",
        (
            "IMAGE_BACKEND_KINDS",
            "ImageBackend",
            "DeterministicImageBackend",
            "FakeImageBackend",
            "render_intent_to_ppm",
        ),
    ),
    (
        "src.engine_v2.presentation.tactical.layout",
        (
            "TACTICAL_LAYOUT_SCHEMA_VERSION",
            "TacticalLayout",
            "build_tactical_layout",
        ),
    ),
    (
        "src.engine_v2.adapters.web.session",
        (
            "SESSION_COMMANDS",
            "TickDriver",
            "TemplatePlayerPolicy",
            "WebSession",
            "SessionManager",
            "SessionNotFoundError",
        ),
    ),
    (
        "src.engine_v2.adapters.web.api",
        (
            "WEB_ROUTES",
            "WebApiError",
            "WebResponse",
            "handle_web_request",
            "resolve_static_name",
        ),
    ),
    (
        "src.engine_v2.adapters.web.inspector",
        ("INSPECTOR_SECTIONS", "build_inspector_view", "inspect_event"),
    ),
    (
        "src.engine_v2.adapters.web.workbench",
        ("WORKBENCH_SECTIONS", "build_workbench_view", "prompt_history"),
    ),
    (
        "src.engine_v2.adapters.web.views",
        ("PAGE_NAMES", "PAGE_TEMPLATES", "render_page"),
    ),
    (
        "src.engine_v2.adapters.web.server",
        ("create_web_server", "run_web_server"),
    ),
)

#: 12 名闭集（P4_LLM_PROVIDER_BLACKLIST 同值；边界 m3 同源口径）。
_K8_BLACKLIST: tuple[str, ...] = (
    "openai",
    "anthropic",
    "langchain",
    "litellm",
    "ollama",
    "gemini",
    "gpt",
    "claude",
    "llm",
    "provider",
    "api_key",
    "base_url",
)

#: t3 唯一允许命中（ERR-P10-10：narrator.py TEXT_SOURCES 钉元组的
#: 第 2 名 "llm" 字符串字面量；(rel, 词, 字面量) 三元组钉）。
_K8_ALLOWED_HIT = (
    "src/engine_v2/presentation/text/narrator.py",
    "llm",
    "llm",
)

#: pydantic 允许文件集（§3.0 逐行：text/* / image/* / adapters/web/*；
#: view.py / tactical/* / 占位 __init__ 行不含 pydantic）。
_PYDANTIC_ALLOWED: tuple[str, ...] = (
    "src/engine_v2/presentation/text/narrator.py",
    "src/engine_v2/presentation/image/contract.py",
    "src/engine_v2/presentation/image/director.py",
    "src/engine_v2/presentation/image/backend.py",
    "src/engine_v2/adapters/web/session.py",
    "src/engine_v2/adapters/web/api.py",
    "src/engine_v2/adapters/web/inspector.py",
    "src/engine_v2/adapters/web/workbench.py",
    "src/engine_v2/adapters/web/views.py",
    "src/engine_v2/adapters/web/server.py",
)

#: D6 确定性禁入根（ERR-P10-07：19 src 文件 import 面零命中）。
_NONDETERMINISM_ROOTS: frozenset[str] = frozenset(
    {"random", "time", "datetime", "timeit"}
)


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


def _allowed_presentation_module(rel: str, module: str) -> bool:
    """presentation.* 子闭集（§3.0 逐行 + text/ ↔ image/ 零互钉）。"""
    if rel.endswith("presentation/view.py"):
        return module == "src.engine_v2.presentation.tactical.layout"
    if "/text/" in rel:
        return module == "src.engine_v2.presentation.view"
    if "/image/" in rel:
        return module == "src.engine_v2.presentation.view" or module.startswith(
            "src.engine_v2.presentation.image"
        )
    if "/tactical/" in rel:
        return module.startswith("src.engine_v2.presentation.tactical")
    return module.startswith("src.engine_v2.presentation")


def _check_import_closure(rel: str, modules: list[str]) -> None:
    """单文件 import 根闭集核对（§3.0 + 特例钉）。"""
    inspector_workbench = rel.endswith(("inspector.py", "workbench.py"))
    for module in modules:
        top = module.split(".")[0]
        if top in sys.stdlib_module_names:
            assert top not in _NONDETERMINISM_ROOTS, (rel, module)
            if module == "http.server":
                assert rel.endswith("server.py"), (rel, module)
            continue
        if top == "pydantic":
            assert rel in _PYDANTIC_ALLOWED, (rel, module)
            continue
        assert top == "src", (rel, module)
        parts = module.split(".")
        assert len(parts) > 2 and parts[1] == "engine_v2", (rel, module)
        sub = parts[2]
        if sub == "core":
            if inspector_workbench:
                assert module not in (
                    "src.engine_v2.core.entity",
                    "src.engine_v2.core.components",
                ), (rel, module)
            continue
        if sub == "llm":
            assert module == "src.engine_v2.llm.adapter", (rel, module)
            continue
        if sub == "persistence":
            assert module == "src.engine_v2.persistence.snapshot", (rel, module)
            continue
        if sub == "devtools":
            assert module == "src.engine_v2.devtools.trace_query", (rel, module)
            continue
        if sub == "presentation":
            assert _allowed_presentation_module(rel, module), (rel, module)
            continue
        if sub == "adapters":
            assert module.startswith("src.engine_v2.adapters.web"), (rel, module)
            continue
        assert False, (rel, module)


def test_p10_face_t1_src_tree_closed() -> None:
    """t1：P10 src 树 == 白名单行 1–19（19 项闭集）。"""
    actual: set[str] = set()
    for sub in (
        "src/engine_v2/presentation",
        "src/engine_v2/adapters/web",
    ):
        for path in (REPO_ROOT / sub).rglob("*"):
            if (
                path.is_file()
                and path.suffix != ".pyc"
                and "__pycache__" not in path.parts
            ):
                actual.add(path.relative_to(REPO_ROOT).as_posix())
    # 既有占位二件套属冻结面（边界 m6 哈希钉），不计 19 项。
    actual.discard("src/engine_v2/presentation/__init__.py")
    assert actual == set(_P10_SRC_FILES)
    assert len(actual) == 19


def test_p10_face_t2_export_ledger() -> None:
    """t2：12 模块 49 名导出台账逐字（§8.2 名 + 序钉）。"""
    for module_name, expected in _EXPORT_LEDGER:
        module = importlib.import_module(module_name)
        assert tuple(module.__all__) == expected, module_name
    total = sum(len(expected) for _, expected in _EXPORT_LEDGER)
    assert total == 49


def test_p10_face_t3_k8_literals() -> None:
    """t3：19 src 文件字符串字面量 × 12 名零命中（唯一允许命中 =
    narrator.py TEXT_SOURCES 钉元组，ERR-P10-10）。"""
    hits: set[tuple[str, str, str]] = set()

    def scan(rel: str, text: str) -> None:
        folded = text.casefold()
        for name in _K8_BLACKLIST:
            if re.search(_WB + re.escape(name) + _WB, folded):
                hits.add((rel, name, text))

    for rel in _P10_SRC_FILES:
        path = REPO_ROOT / rel
        if rel.endswith(".py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    scan(rel, node.value)
        else:
            scan(rel, path.read_text(encoding="utf-8"))
    assert hits == {_K8_ALLOWED_HIT}


def test_p10_face_t4_import_closure() -> None:
    """t4：import 闭集 AST（§3.0 + 特例钉 + engine_v2 全树
    langgraph/langchain 零）。"""
    for rel in _P10_SRC_FILES:
        if not rel.endswith(".py"):
            continue
        _check_import_closure(rel, _imported_modules(REPO_ROOT / rel))
    # engine_v2 全树零 langgraph/langchain（G9-16 延续，P10 域重钉）。
    for path in sorted((REPO_ROOT / "src" / "engine_v2").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        for module in _imported_modules(path):
            top = module.split(".")[0]
            assert top not in ("langgraph", "langchain"), (path, module)


def test_p10_face_t5_no_control_bytes() -> None:
    """t5：19 src 文件零裸 0x5C 0x62 字节（D3）。"""
    forbidden = bytes([0x5C, 0x62])
    for rel in _P10_SRC_FILES:
        data = (REPO_ROOT / rel).read_bytes()
        assert forbidden not in data, rel


def test_p10_face_t6_no_frontend_build_artifacts() -> None:
    """t6：零前端构建产物（src/ 全树）+ static 3 文件闭集 + app.js
    零 import / require / document.write。"""
    for path in sorted((REPO_ROOT / "src").rglob("*")):
        if not path.is_file():
            continue
        name = path.name
        assert name not in (
            "package.json",
            "package-lock.json",
            "bun.lockb",
        ), path
        assert not name.startswith("vite.config."), path
        assert not name.startswith("webpack"), path
    static_dir = REPO_ROOT / "src/engine_v2/adapters/web/static"
    actual = {p.name for p in static_dir.iterdir() if p.is_file()}
    assert actual == {"index.html", "app.js", "styles.css"}
    app_js = (static_dir / "app.js").read_text(encoding="utf-8")
    for token in ("import", "require(", "document.write"):
        assert token not in app_js, token
