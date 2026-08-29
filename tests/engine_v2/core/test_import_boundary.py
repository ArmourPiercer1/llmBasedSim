"""P1-T06 收尾验收：import 边界（设计文档 §7.6 B1–B3，扩展骨架 AST 口径）。

对 T01–T05 落盘的整体 core 包做 §0.3 import 边界的包级验收（各模块的
白名单口径已在 T01–T05 各自测试中逐模块固化，本文件是 **包级黑名单**
验收，与设计文档 §7.6 口径一致）：

- **B1 静态扫描**：``src/engine_v2/core/`` 全部 ``.py``（13 个契约模块 +
  re-export 后的 ``__init__.py``）无 §0.3 黑名单 import。黑名单 = 骨架
  ``tests/test_engine_v2_skeleton.py`` 的 provider 前缀口径**扩展**为
  §0.3 全表：provider/LLM SDK、一切 v1 包（``src.`` 命名空间下
  engine_v2 之外的任何包，以及 §0.3 列举的 v1 包根名裸 import）、网络/
  进程 IO 库（``requests``/``httpx``/``socket``/``subprocess`` 等）。
  AST 口径扩展：骨架只取 import 的顶层根名，本测试保留**完整点分模块名**
  （才能区分 ``src.engine_v2``（同包，合法）与 ``src.game`` 等 v1 包）；
- **B2 运行时扫描**：fresh import ``src.engine_v2.core`` 全部模块（含
  re-export 后的 ``__init__.py``），``sys.modules`` 增量不含任何黑名单
  模块（与 B1 同一谓词）；
- **B3 无网络可运行**：T06 全套用例（``tests/engine_v2/`` 全部测试）在
  断网环境（不设置任何 API key 环境变量）通过的机械保证——静态扫描测试
  树无任何网络/进程 IO/provider/v1 import（配合 B1/B2 双保险，即设计
  文档 §7 引注"全部用例必须无网络、无 API key、无 provider、无
  LangGraph"的程序化表达）。

全部用例无网络、无 LLM、无 API key（Spec §47 Phase 1 验收）。
"""

from __future__ import annotations

import ast
import importlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CORE_PKG = "src.engine_v2.core"
CORE_DIR = REPO_ROOT / "src" / "engine_v2" / "core"
TESTS_ENGINE_DIR = REPO_ROOT / "tests" / "engine_v2"

#: core 包 19 个模块（P2 设计规范 §1.1 / D-P2-19：13 个契约模块 +
#: 6 个 P2 行为模块 authority / cascade / conflicts / reducer /
#: transaction_executor / validation；P1 已全数落盘，P2 模块随各任务包
#: 填充行为主体）。
CORE_SUBMODULES: tuple[str, ...] = (
    "action_lifecycle",
    "action_registry",
    "actions",
    "authority",
    "cascade",
    "clock",
    "components",
    "conflicts",
    "effects",
    "entity",
    "event_queue",
    "events",
    "ids",
    "interrupt",
    "provenance",
    "reducer",
    "revision",
    "scheduler",
    "serialization",
    "snapshot",
    "state",
    "trace",
    "transaction",
    "transaction_executor",
    "validation",
)

# —— §0.3 黑名单（骨架 FORBIDDEN_MODULE_PREFIXES 的扩展口径）——

#: provider / LLM SDK（§0.3："langgraph、langchain、langchain_core、
#: langchain_openai、openai 及任何 provider SDK"；Spec §47 Phase 1
#: "此阶段完全不接 LLM"）。机械集合在骨架 5 项之外补入常见 provider 根名。
PROVIDER_ROOTS: frozenset[str] = frozenset(
    {
        "langgraph",
        "langchain",
        "langchain_core",
        "langchain_openai",
        "langchain_community",
        "openai",
        "anthropic",
        "google",
        "azure",
        "boto3",
    }
)

#: v1 包根名（§0.3："一切 v1 包：src.graph、src.game、src.agents、src.web、
#: src.llm、src.prompts、src.config、src.models、src.ui"）。本仓 v1 包位于
#: ``src/`` 命名空间下，import 形态为 ``src.<包名>...``；根名表用于拦截
#: 裸名 import 形态（std lib 与白名单第三方中不存在这些顶层名，无误报）。
V1_PKG_ROOTS: frozenset[str] = frozenset(
    {"graph", "game", "agents", "web", "llm", "prompts", "config", "models", "ui"}
)

#: 网络 / 进程 IO 库（§0.3："requests、httpx、socket、subprocess 等——
#: Kernel 必须在无网络环境单测"）。std lib 网络/进程 IO + 常见第三方
#: 网络/RPC 库的顶层根名。
NETWORK_IO_ROOTS: frozenset[str] = frozenset(
    {
        # std lib 网络 IO
        "socket",
        "socketserver",
        "urllib",
        "http",
        "ssl",
        "ftplib",
        "smtplib",
        "poplib",
        "imaplib",
        "telnetlib",
        "xmlrpc",
        # std lib 进程
        "subprocess",
        "multiprocessing",
        # 第三方网络 / RPC
        "requests",
        "httpx",
        "aiohttp",
        "httpcore",
        "anyio",
        "websockets",
        "grpcio",
        "twisted",
    }
)


# —— 扫描工具（扩展骨架 AST 口径：保留完整点分模块名）——


def _collect_absolute_imports(path: Path) -> list[str]:
    """静态收集一个 .py 文件中所有**绝对** import 的完整点分模块名。

    相对 import（level > 0）不可能逃出所在包（core 内相对 import 只能到
    达 core 自身），按骨架口径不检查；``level == 0`` 的 ``from x import``
    取 ``node.module``，``import x.y`` 取 ``alias.name``。
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.append(node.module)
    return modules


def _blacklist_category(module_name: str) -> str | None:
    """判定一个完整点分模块名是否命中 §0.3 黑名单；命中返回类别，否则 None。

    判定顺序：

    1. ``src`` 命名空间：裸 ``src`` 是**命名空间包本身**（无代码，加载它
       不载入任何 v1 模块）——合法；``src.engine_v2`` / ``src.engine_v2.*``
       为同包 import（§0.3 白名单"同包 src.engine_v2"）——合法；其余
       ``src.*`` 即 v1 包（无论包名，命名空间内 engine_v2 之外全是 v1）；
    2. 顶层根名命中 v1 包根名表（裸名形态）；
    3. 顶层根名命中 provider/LLM SDK 表；
    4. 顶层根名命中网络/进程 IO 表。
    """
    if module_name == "src":
        return None
    if module_name.startswith("src."):
        if module_name == "src.engine_v2" or module_name.startswith("src.engine_v2."):
            return None
        return "v1 包（src 命名空间）"
    root = module_name.split(".")[0]
    if root in V1_PKG_ROOTS:
        return "v1 包（裸名）"
    if root in PROVIDER_ROOTS:
        return "provider/LLM SDK"
    if root in NETWORK_IO_ROOTS:
        return "网络/进程 IO"
    return None


def _scan_violations(directory: Path, pattern: str) -> dict[str, dict[str, str]]:
    """对目录下匹配的 .py 做 B1 黑名单扫描，返回 {文件: {模块名: 类别}}。"""
    violations: dict[str, dict[str, str]] = {}
    for path in sorted(directory.glob(pattern)):
        for module_name in _collect_absolute_imports(path):
            category = _blacklist_category(module_name)
            if category is not None:
                violations.setdefault(str(path.relative_to(REPO_ROOT)), {})[module_name] = (
                    category
                )
    return violations


class TestB1StaticScan:
    """B1：src/engine_v2/core/ 全部 .py 无 §0.3 黑名单 import（AST 静态扫描）。"""

    def test_core_dir_file_set_matches_design_table(self) -> None:
        """扫描面 = 设计文档 §1.1 文件清单（13 模块）+ re-export 的 __init__.py。"""
        stems = sorted(p.stem for p in CORE_DIR.glob("*.py"))
        assert stems == sorted(set(CORE_SUBMODULES) | {"__init__"}), (
            f"core/ 文件集合与设计文档 §1.1 不符：{stems}"
        )

    def test_no_blacklisted_imports_anywhere_in_core(self) -> None:
        """B1 主断言：core/ 全部 .py（含 __init__.py）的绝对 import 无黑名单命中。"""
        violations = _scan_violations(CORE_DIR, "*.py")
        assert not violations, f"core/ 出现 §0.3 黑名单 import：{violations}"

    def test_whitelisted_families_only(self) -> None:
        """正向核对：core/ 的每个绝对 import 都落在白名单族
        （标准库 / pydantic / 同包 src.engine_v2）。黑名单谓词之外，
        额外断言 src. 命名空间下同包 import 全部指向 src.engine_v2 之内。"""
        for path in sorted(CORE_DIR.glob("*.py")):
            for module_name in _collect_absolute_imports(path):
                if module_name == "src" or module_name.startswith("src."):
                    assert module_name == "src.engine_v2" or module_name.startswith(
                        "src.engine_v2."
                    ), f"{path.name} 的 src 命名空间 import 越出同包：{module_name}"


class TestB2RuntimeScan:
    """B2：fresh import src.engine_v2.core 全部模块，sys.modules 增量无黑名单。"""

    def test_fresh_import_pulls_no_blacklisted_modules(self) -> None:
        # 清掉 core 包与全部子模块缓存，重新 import（骨架同款手法，
        # 范围收窄到 core 包；父包 src / src.engine_v2 保持已加载）。
        # 测试结束后恢复原模块实例：fresh import 产生的新模块对象不得
        # 泄漏进全局 sys.modules（套件内其余测试对 core 类对象的身份
        # 一致性敏感——ContractModel/typed ID 等跨模块共享定义）。
        saved = {
            name: module
            for name, module in sys.modules.items()
            if name == CORE_PKG or name.startswith(CORE_PKG + ".")
        }
        try:
            for name in saved:
                del sys.modules[name]
            before = set(sys.modules)
            importlib.import_module(CORE_PKG)
            for sub in CORE_SUBMODULES:
                importlib.import_module(f"{CORE_PKG}.{sub}")
            pulled = set(sys.modules) - before
            bad = {
                name: _blacklist_category(name) for name in pulled if _blacklist_category(name)
            }
            assert not bad, f"import core 过程中新载入了 §0.3 黑名单模块：{bad}"
            # 有效性自检：fresh import 确实重建了 core 包与全部 13 个子模块
            assert CORE_PKG in pulled, "fresh import 未重新加载 core 包"
            for sub in CORE_SUBMODULES:
                assert f"{CORE_PKG}.{sub}" in pulled, f"fresh import 未重新加载 {sub}"
        finally:
            for name in [
                n for n in sys.modules if n == CORE_PKG or n.startswith(CORE_PKG + ".")
            ]:
                del sys.modules[name]
            sys.modules.update(saved)


class TestB3OfflineRunnable:
    """B3：T06 全套用例无网络可运行（机械保证：测试树无网络/进程/provider import）。

    设计文档 §7 引注：全部用例必须无网络、无 API key、无 provider、无
    LangGraph（Plan §22.2、Spec §47 Phase 1 验收）。API key 环境变量在
    测试全程未被读取（无 provider import ⇒ 无 SDK 配置路径）；断网能力
    由本静态扫描 + B1/B2 双保险表达。
    """

    def test_t06_test_tree_has_no_network_provider_or_v1_imports(self) -> None:
        violations = _scan_violations(TESTS_ENGINE_DIR, "**/*.py")
        assert not violations, f"tests/engine_v2/ 出现 §0.3 黑名单 import：{violations}"
