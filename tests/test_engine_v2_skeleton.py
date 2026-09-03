"""P0-T05：``src/engine_v2`` 骨架验收测试（G0 门禁：新 v2 目录可 import，但未替换 v1）。

检查项：
1. ``src.engine_v2`` 及各子包可成功 import，且均为包；
2. 各子包 ``__init__.py`` 仅含模块 docstring（占位纪律，无任何 import / 语句）；
   P1 收尾豁免（设计文档 §0.4 预告）：仅 ``core/__init__.py`` 额外允许
   re-export 语句（从同包 core 子模块导入契约类型）与 ``__all__`` 清单；
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
    # P10（SOT §11 行 2/4/8/10；ERR-P10-09 计数面机械追加）：
    "presentation.text",
    "presentation.image",
    "presentation.tactical",
    "adapters.web",
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


def _is_docstring_node(node: ast.stmt) -> bool:
    """模块体顶层的模块 docstring（str Constant 的 Expr 包装）。"""
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )


def _is_reexport_node(node: ast.stmt, prefix: str) -> bool:
    """re-export 豁免的通用检查（包前缀 ``prefix`` 口径）。

    - re-export import：仅允许从同包子模块拉取名称——绝对
      ``<prefix>.<模块>`` 或包内相对 import（``from .<模块>``，level 恰
      为 1，不得相对穿出本包）；
    - ``__all__ = [...]``：单个 Name 目标为 ``__all__``、值为字符串常量
      列表/元组的单一赋值（导出清单）；
    - 其余一切语句（函数/类定义、其他赋值、表达式、指向包外的 import）
      仍属违规。
    """
    if isinstance(node, ast.ImportFrom):
        if node.level == 1 and node.module:
            return True  # 包内相对 import（from .<模块> import ...）
        return node.level == 0 and node.module is not None and node.module.startswith(
            prefix
        )
    if isinstance(node, ast.Import):
        return all(alias.name.startswith(prefix) for alias in node.names)
    if isinstance(node, ast.Assign):
        return (
            len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "__all__"
            and isinstance(node.value, (ast.List, ast.Tuple))
            and all(
                isinstance(el, ast.Constant) and isinstance(el.value, str)
                for el in node.value.elts
            )
        )
    return False


def _is_core_reexport_node(node: ast.stmt) -> bool:
    """P1 收尾豁免（设计文档 §0.4）：仅 ``core/__init__.py`` 适用的放宽口径。

    只放宽 **re-export 语句** 与 ``__all__`` 导出清单，其余纪律不放宽
    （通用检查见 :func:`_is_reexport_node`，prefix = ``src.engine_v2.core``）。
    """
    return _is_reexport_node(node, "src.engine_v2.core")


def test_engine_v2_init_files_are_docstring_only():
    """骨架纪律：每个 __init__.py 仅含模块 docstring，无 import / 赋值 / 定义。

    P1 收尾豁免（设计文档 §0.4，骨架纪律的自然收尾）：``core/__init__.py``
    额外允许 re-export 语句（从同包 core 子模块导入契约类型）与 ``__all__``
    清单语句；ERR-C-01（12h closure，同先例同口径）：``runtime/__init__.py``
    额外允许 re-export 语句（从同包 runtime 子模块导入装配/运行面公开名）
    与 ``__all__`` 清单语句；其余 17 个子包（含 P10 嵌套子包，ERR-P10-09）
    + 根包保持 "仅 docstring" 纪律不变。
    """
    init_files = sorted(ENGINE_DIR.rglob("__init__.py"))
    assert len(init_files) == len(SUBPACKAGES) + 1, "子包数量与任务包清单不符（应为 17 子包（含嵌套）+ 根包）"
    reexport_exempt = {
        ENGINE_DIR / "core" / "__init__.py": "src.engine_v2.core",
        ENGINE_DIR / "runtime" / "__init__.py": "src.engine_v2.runtime",
    }
    for init_path in init_files:
        tree = ast.parse(init_path.read_text(encoding="utf-8"), filename=str(init_path))
        rel = init_path.relative_to(REPO_ROOT)
        for node in tree.body:
            allowed = _is_docstring_node(node) or (
                init_path in reexport_exempt
                and _is_reexport_node(node, reexport_exempt[init_path])
            )
            assert allowed, (
                f"{rel} 骨架 __init__.py 应仅含模块 docstring"
                "（core/__init__.py 与 runtime/__init__.py 额外允许 re-export "
                "语句与 __all__ 清单），"
                f"发现违规语句：{ast.dump(node)[:120]}"
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
