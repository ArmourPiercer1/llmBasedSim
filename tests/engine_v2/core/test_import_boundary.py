"""P1-T06 收尾验收：import 边界（设计文档 §7.6 B1–B3，扩展骨架 AST 口径）。
P3-T08 扩展：``TestP3Boundary``（任务硬规则 4 的机械验证面）。

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
  LangGraph"的程序化表达）；
- **P3 扩展**（P3-T08 任务硬规则 4，``TestP3Boundary``）：
  - P3 七个行为模块（``P3_SUBMODULES``：clock / event_queue /
    action_registry / action_lifecycle / interrupt / revalidation /
    scheduler）绝对 import 不得触及 ``datetime``/``time``/``random``/
    ``asyncio``——确定性时间域：逻辑时钟是唯一时间源（D-P3-02），墙钟
    与随机数不进调度路径；
  - P3 测试扫描面（``P3_TEST_FILES`` 十个文件：7 个 P3 单元测试 +
    Gate/对抗两文件 + 共享 conftest）适用**全谓词**（§0.3 黑名单 ∪
    上列四个非确定性根）——测试侧同样不接 LLM、不引入时间/随机/异步
    （Spec §47 Phase 1 验收的测试面镜像）。

全部用例无网络、无 LLM、无 API key（Spec §47 Phase 1 验收）。
"""

from __future__ import annotations

import ast
import importlib
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CORE_PKG = "src.engine_v2.core"
CORE_DIR = REPO_ROOT / "src" / "engine_v2" / "core"
TESTS_ENGINE_DIR = REPO_ROOT / "tests" / "engine_v2"

#: core 包 32 个模块（P2 设计规范 §1.1 / D-P2-19：13 个契约模块 +
#: 6 个 P2 行为模块 authority / cascade / conflicts / reducer /
#: transaction_executor / validation；P1 已全数落盘，P2 模块随各任务包
#: 填充行为主体；P3 设计规范 §3.1：7 个 P3 编排层模块 action_lifecycle /
#: action_registry / clock / event_queue / interrupt / revalidation /
#: scheduler；P4 设计规范 §3.1：6 个 P4 模块 behavior_policy /
#: capability / context_provider / gameplay_mode / knowledge / space）。
CORE_SUBMODULES: tuple[str, ...] = (
    "action_lifecycle",
    "action_registry",
    "actions",
    "authority",
    "behavior_policy",
    "capability",
    "cascade",
    "clock",
    "components",
    "conflicts",
    "context_provider",
    "effects",
    "entity",
    "event_queue",
    "events",
    "gameplay_mode",
    "ids",
    "interrupt",
    "knowledge",
    "provenance",
    "reducer",
    "revalidation",
    "revision",
    "scheduler",
    "serialization",
    "snapshot",
    "space",
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

# —— P3 扩展（P3-T08 任务硬规则 4 机械验证面）——

#: P3 七个行为模块（P3 设计文档 §1.1 新增模块集；B1 的 CORE_SUBMODULES
#: 26 元组已含此 7 项，此处单列以承载 P3 专属谓词的扫描面）。
P3_SUBMODULES: tuple[str, ...] = (
    "clock",
    "event_queue",
    "action_registry",
    "action_lifecycle",
    "interrupt",
    "revalidation",
    "scheduler",
)

#: P3 确定性时间域禁入根（硬规则 4）：逻辑时钟（D-P3-02）是调度路径
#: 唯一时间源；墙钟/随机/异步不得进 P3 核心模块与 P3 测试面。
P3_NONDETERMINISM_ROOTS: frozenset[str] = frozenset(
    {"datetime", "time", "random", "asyncio"}
)

#: P3 测试扫描面（10 文件）：7 个 P3 单元测试文件 + Gate/对抗两文件 +
#: 共享 conftest（全位于 ``tests/engine_v2/core/``）。
P3_TEST_FILES: tuple[str, ...] = (
    "test_clock.py",
    "test_event_queue.py",
    "test_action_registry.py",
    "test_action_lifecycle.py",
    "test_interrupt.py",
    "test_revalidation.py",
    "test_scheduler.py",
    "test_p3_gate_scenario.py",
    "test_p3_adversarial.py",
    "conftest.py",
)

# —— P4 扩展（P4 设计规范 §5.5 M1 / §6.4 机械验证面）——

#: P4 六个模块（P4 设计规范 §3.1 文件清单；B1 的 CORE_SUBMODULES
#: 32 元组已含此 6 项，此处单列以承载 P4 专属谓词的扫描面）。
P4_SUBMODULES: tuple[str, ...] = (
    "behavior_policy",
    "capability",
    "context_provider",
    "gameplay_mode",
    "knowledge",
    "space",
)

#: P4 确定性禁入根（M1①，与 P3 同源口径 test_import_boundary.py:159-161）：
#: 六模块绝对 import 不得触及（AST 扫描实现）。
P4_NONDETERMINISM_ROOTS: frozenset[str] = frozenset(
    {"datetime", "time", "random", "asyncio"}
)

#: P4 测试扫描面（10 文件）：6 个 P4 单元测试文件 + Gate/对抗/集成
#: 三文件 + 共享 conftest（全位于 ``tests/engine_v2/core/``）。
P4_TEST_FILES: tuple[str, ...] = (
    "test_capability.py",
    "test_knowledge.py",
    "test_space.py",
    "test_context_provider.py",
    "test_behavior_policy.py",
    "test_gameplay_mode.py",
    "test_p4_gate_scenario.py",
    "test_p4_adversarial.py",
    "test_p4_integration.py",
    "conftest.py",
)

#: M1④ 封闭标识符集（封闭枚举，不得增删；§3.4/§5.5 规范要素一致、依
#: §3.4 引用）：P4 六模块全源文本（含 docstring/注释）casefold 后按词
#: 边界逐词匹配集合成员 → 0 命中（"仍不接实际云模型"的机械像，Plan:556）。
P4_LLM_PROVIDER_BLACKLIST: frozenset[str] = frozenset(
    {
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


def _p3_strict_violation(module_name: str) -> str | None:
    """P3 全谓词（硬规则 4）：§0.3 黑名单（B1 同一谓词）∪ 非确定性根
    （datetime/time/random/asyncio，P3 确定性时间域）。命中返回类别串。"""
    category = _blacklist_category(module_name)
    if category is not None:
        return category
    if module_name.split(".")[0] in P3_NONDETERMINISM_ROOTS:
        return "时间/随机/异步非确定性源（P3 硬规则 4）"
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


class TestP3Boundary:
    """P3（T01–T08）import 边界强化（P3-T08 任务硬规则 4，机械验证）。

    - ``P3_SUBMODULES`` 七个 P3 核心模块：绝对 import 不得触及
      ``datetime``/``time``/``random``/``asyncio``（逻辑时钟是唯一时间
      源，D-P3-02；墙钟与随机数不进调度路径）；
    - ``P3_TEST_FILES`` 十个 P3 测试文件：全谓词（§0.3 黑名单 ∪ 非确定
      性根）——测试侧同样不接 provider/LLM、不引入时间/随机/异步/网络
      （Spec §47 Phase 1 验收的测试面镜像）。
    """

    def test_p3_core_modules_no_nondeterminism_imports(self) -> None:
        """七个 P3 核心模块（src/engine_v2/core/）绝对 import 无
        datetime/time/random/asyncio 命中。"""
        violations: dict[str, list[str]] = {}
        for sub in P3_SUBMODULES:
            path = CORE_DIR / f"{sub}.py"
            assert path.exists(), f"P3 核心模块缺失：{sub}"
            bad = [
                module_name
                for module_name in _collect_absolute_imports(path)
                if module_name.split(".")[0] in P3_NONDETERMINISM_ROOTS
            ]
            if bad:
                violations[f"src/engine_v2/core/{sub}.py"] = bad
        assert not violations, (
            f"P3 核心模块 import 时间/随机/异步非确定性源：{violations}"
        )

    def test_p3_test_files_full_predicate(self) -> None:
        """十个 P3 测试文件适用全谓词（§0.3 黑名单 ∪ 非确定性根）：
        无 provider/LLM/v1/网络/进程 IO import，亦无
        datetime/time/random/asyncio import。"""
        violations: dict[str, list[str]] = {}
        p3_tests_dir = TESTS_ENGINE_DIR / "core"
        for name in P3_TEST_FILES:
            path = p3_tests_dir / name
            assert path.exists(), f"P3 测试扫描面文件缺失：{name}"
            bad = [
                module_name
                for module_name in _collect_absolute_imports(path)
                if _p3_strict_violation(module_name) is not None
            ]
            if bad:
                violations[name] = bad
        assert not violations, f"P3 测试文件命中全谓词：{violations}"


class TestP4Boundary:
    """P4（T01–T06 + T10）import 边界强化（P4 设计规范 §5.5 M1 /
    §6.4，机械验证）。

    - ``P4_SUBMODULES`` 六个 P4 模块：绝对 import 不得触及
      ``datetime``/``time``/``random``/``asyncio``（M1①：确定性纪律
      与 P3 同源；墙钟/随机/异步不进 P4 核心）；
    - M1④：``P4_LLM_PROVIDER_BLACKLIST`` 封闭标识符集对六模块全源文本
      （含 docstring/注释）casefold 词边界匹配 → 0 命中（"形成 Runtime
      世界语义层，但仍不接实际云模型"的机械像，Plan:556）；
    - ``P4_TEST_FILES`` 十个 P4 测试文件：全谓词（§0.3 黑名单 ∪ 非确定
      性根）——测试侧同样不接 provider/LLM、不引入时间/随机/异步/网络
      （Spec §47 Phase 1 验收的测试面镜像）。
    """

    def test_p4_core_modules_no_nondeterminism_imports(self) -> None:
        """六个 P4 核心模块（src/engine_v2/core/）绝对 import 无
        datetime/time/random/asyncio 命中（M1①）；且 M1④ 封闭标识符集
        对全源文本 casefold 词边界匹配 0 命中。"""
        violations: dict[str, list[str]] = {}
        llm_hits: dict[str, list[str]] = {}
        for sub in P4_SUBMODULES:
            path = CORE_DIR / f"{sub}.py"
            assert path.exists(), f"P4 核心模块缺失：{sub}"
            bad = [
                module_name
                for module_name in _collect_absolute_imports(path)
                if module_name.split(".")[0] in P4_NONDETERMINISM_ROOTS
            ]
            if bad:
                violations[f"src/engine_v2/core/{sub}.py"] = bad
            text = path.read_text(encoding="utf-8").casefold()
            hits = [
                word
                for word in sorted(P4_LLM_PROVIDER_BLACKLIST)
                if re.search(rf"\b{re.escape(word)}\b", text)
            ]
            if hits:
                llm_hits[f"src/engine_v2/core/{sub}.py"] = hits
        assert not violations, (
            f"P4 核心模块 import 时间/随机/异步非确定性源：{violations}"
        )
        assert not llm_hits, (
            f"P4 核心模块源文本命中 M1④ 封闭标识符集（§3.4）：{llm_hits}"
        )

    def test_p4_test_files_full_predicate(self) -> None:
        """十个 P4 测试文件适用全谓词（§0.3 黑名单 ∪ 非确定性根）：
        无 provider/LLM/v1/网络/进程 IO import，亦无
        datetime/time/random/asyncio import。"""
        violations: dict[str, list[str]] = {}
        p4_tests_dir = TESTS_ENGINE_DIR / "core"
        for name in P4_TEST_FILES:
            path = p4_tests_dir / name
            assert path.exists(), f"P4 测试扫描面文件缺失：{name}"
            bad = [
                module_name
                for module_name in _collect_absolute_imports(path)
                if _p3_strict_violation(module_name) is not None
            ]
            if bad:
                violations[name] = bad
        assert not violations, f"P4 测试文件命中全谓词：{violations}"
