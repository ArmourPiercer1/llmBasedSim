"""P0-T05：``src/engine_v2`` 骨架验收测试（G0 门禁：新 v2 目录可 import，但未替换 v1）。

检查项：
1. ``src.engine_v2`` 及各子包可成功 import，且均为包；
2. 各子包 ``__init__.py`` 仅含模块 docstring（占位纪律，无任何 import / 语句）；
3. engine_v2 全树不得 import LangGraph / OpenAI 系依赖
   （静态 AST 扫描 + import 前后 sys.modules 增量检查双保险）；
4. v1 代码（``src/`` 下 engine_v2 之外的 .py）不得引用 ``engine_v2``；
5. ``src/engine_v2/README.md`` 存在且含「v2 冻结规则」章节。

纯静态 / import 冒烟检查：无网络、无 LLM、不触碰 v1 行为。
"""

from __future__ import annotations

import ast
import importlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ENGINE_PKG = "src.engine_v2"
ENGINE_DIR = REPO_ROOT / "src" / "engine_v2"

SUBPACKAGES = [
    "core",
    "runtime",
    "persistence",
    "plugins",
    "context",
    "modules",
    "dynamics",
    "llm",
    "prompts",
    "content",
    "devtools",
    "adapters",
    "presentation",
]

# G1 门禁：Core import 不需要 LangGraph / OpenAI；骨架期整树禁止引入。
FORBIDDEN_MODULE_PREFIXES = (
    "langgraph",
    "langchain_openai",
    "langchain_core",
    "langchain",
    "openai",
)


def _all_engine_module_names() -> list[str]:
    return [ENGINE_PKG] + [f"{ENGINE_PKG}.{sub}" for sub in SUBPACKAGES]


def _engine_python_files() -> list[Path]:
    assert ENGINE_DIR.is_dir(), "src/engine_v2/ 目录不存在"
    return sorted(ENGINE_DIR.rglob("*.py"))


def _collect_static_import_roots(path: Path) -> set[str]:
    """静态收集一个 .py 文件中所有绝对 import 的顶层模块名。"""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            # 相对 import（level > 0）不会逃出 engine_v2 包，无需检查。
            if node.level == 0 and node.module:
                roots.add(node.module.split(".")[0])
    return roots


def _is_forbidden(module_name: str) -> bool:
    return any(
        module_name == prefix or module_name.startswith(prefix + ".")
        for prefix in FORBIDDEN_MODULE_PREFIXES
    )


def _freshly_import_engine() -> set[str]:
    """清掉已缓存的 engine_v2 模块后重新 import，返回本次 import 新增的 sys.modules 键。"""
    for name in [n for n in sys.modules if n == ENGINE_PKG or n.startswith(ENGINE_PKG + ".")]:
        del sys.modules[name]
    before = set(sys.modules)
    for name in _all_engine_module_names():
        importlib.import_module(name)
    return set(sys.modules) - before


def test_engine_v2_and_subpackages_import():
    """G0：新 v2 目录可以 import。"""
    for name in _all_engine_module_names():
        module = importlib.import_module(name)
        assert hasattr(module, "__path__"), f"{name} 不是包（缺少 __path__）"


def test_engine_v2_init_files_are_docstring_only():
    """骨架纪律：每个 __init__.py 仅含模块 docstring，无 import / 赋值 / 定义。"""
    init_files = sorted(ENGINE_DIR.rglob("__init__.py"))
    assert len(init_files) == len(SUBPACKAGES) + 1, "子包数量与任务包清单不符（应为 13 子包 + 根包）"
    for init_path in init_files:
        tree = ast.parse(init_path.read_text(encoding="utf-8"), filename=str(init_path))
        for node in tree.body:
            is_docstring = (
                isinstance(node, ast.Expr)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
            )
            rel = init_path.relative_to(REPO_ROOT)
            assert is_docstring, (
                f"{rel} 骨架 __init__.py 应仅含模块 docstring，发现非 docstring 语句"
            )


def test_engine_v2_static_scan_has_no_forbidden_imports():
    """b)（静态扫描）engine_v2 全树源码不得 import langgraph / langchain_openai / openai。"""
    violations: dict[str, set[str]] = {}
    for path in _engine_python_files():
        for root in _collect_static_import_roots(path):
            if _is_forbidden(root):
                violations.setdefault(str(path.relative_to(REPO_ROOT)), set()).add(root)
    assert not violations, f"engine_v2 不得 import LangGraph / OpenAI 系依赖：{violations}"


def test_engine_v2_import_pulls_in_no_forbidden_modules_sysmodules():
    """b)（sys.modules 检查）fresh import engine_v2 全树不得新载入 LangGraph / OpenAI 系模块。"""
    pulled = _freshly_import_engine()
    bad = sorted(name for name in pulled if _is_forbidden(name))
    assert not bad, f"import engine_v2 过程中新载入了禁止依赖：{bad}"


def test_v1_code_does_not_reference_engine_v2():
    """c) src/ 下除 engine_v2 外，v1 代码（.py）不得引用 engine_v2。"""
    offenders: list[str] = []
    for path in sorted((REPO_ROOT / "src").rglob("*.py")):
        try:
            path.relative_to(ENGINE_DIR)
        except ValueError:
            pass
        else:
            continue  # engine_v2 自身文件不在检查范围
        if "engine_v2" in path.read_text(encoding="utf-8"):
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, f"v1 代码引用了 engine_v2（G0：新目录可 import，但未替换 v1）：{offenders}"


def test_engine_v2_readme_documents_freeze_rules():
    """README 存在且包含「v2 冻结规则」与目录布局。"""
    readme = ENGINE_DIR / "README.md"
    assert readme.is_file(), "缺少 src/engine_v2/README.md"
    text = readme.read_text(encoding="utf-8")
    assert "v2 冻结规则" in text, "README 缺少「v2 冻结规则」章节"
    assert "目录布局" in text, "README 缺少「目录布局」章节"
