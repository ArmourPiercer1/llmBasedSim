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

# —— P5 扩展（P5 设计规范 §3.11 锚点同步表 / §6.4 机械验证面）——

#: P5 十个模块（§3.11：10 茎 = content 7 模块 schemas/project_ir/loader/
#: module_graph/rule_module/validator/cli + plugins 3 模块 manifest/api/
#: registry；D-P5-01：P5 不入 core，CORE_SUBMODULES 不含此 10 项，此处
#: 单列以承载 P5 专属谓词的扫描面）。
P5_SUBMODULES: tuple[str, ...] = (
    "schemas",
    "project_ir",
    "loader",
    "module_graph",
    "rule_module",
    "validator",
    "cli",
    "manifest",
    "api",
    "registry",
)

#: P5 测试扫描面（15 文件；白名单 #13-24 / #26-28：11 个 content 测试
#: 文件 + 2 个 plugins 测试文件 + 2 个共享 conftest；不含 __init__.py，
#: P4_TEST_FILES 同款基名口径）。``conftest.py`` 基名在 content/ 与
#: plugins/ 两目录各一（#13/#26），故元组内以重复项计数 15；解析见
#: ``_p5_test_paths``（去重后恰好 15 个不同路径）。
P5_TEST_FILES: tuple[str, ...] = (
    "test_schemas.py",
    "test_project_ir.py",
    "test_loader.py",
    "test_module_graph.py",
    "test_rule_dsl_parity.py",
    "test_rule_module.py",
    "test_validator.py",
    "test_cli.py",
    "test_p5_gate_scenario.py",
    "test_p5_adversarial.py",
    "test_p5_integration.py",
    "test_manifest.py",
    "test_registry.py",
    "conftest.py",
    "conftest.py",
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
        # P5 例外（SOT §6.5 字面要求；Leader 裁定，ERR-P5-16 记录）：
        # test_p5_integration.py 的子进程冒烟 = 本地解释器 python -m 三态
        # （无网络、无 API key、无 provider），仅豁免该文件「网络/进程 IO」
        # 类别命中（subprocess）；provider / v1 类别对该文件仍零容忍。
        # 本方法体是 §3.11 纯追加纪律的受控偏离（既有行变更：第一处，
        # 第二处 = 下方 P6 例外，ERR-P6-6 记录）。
        p5_smoke = "tests/engine_v2/content/test_p5_integration.py"
        if p5_smoke in violations:
            rest = {
                module_name: category
                for module_name, category in violations[p5_smoke].items()
                if category != "网络/进程 IO"
            }
            if rest:
                violations[p5_smoke] = rest
            else:
                del violations[p5_smoke]
        # P6 例外（SOT §5.1 S0 L751 + §6.1 L811 字面要求：W3 test_adapter.py
        # 仅用 httpx.MockTransport / ConnectError 进程内面，零真实网络；
        # Leader 裁定，ERR-P6-6 记录，W3 提前落地）：仅豁免该文件「网络/
        # 进程 IO」类别命中（httpx）；provider / v1 类别对该文件仍零容忍。
        p6_adapter = "tests/engine_v2/llm/test_adapter.py"
        if p6_adapter in violations:
            rest = {
                module_name: category
                for module_name, category in violations[p6_adapter].items()
                if category != "网络/进程 IO"
            }
            if rest:
                violations[p6_adapter] = rest
            else:
                del violations[p6_adapter]
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


# —— P5 扫描面解析（§3.11：既有行零改动，纯追加；辅助函数供 TestP5Boundary
# 五方法复用，P5 专属常量仍仅 P5_SUBMODULES / P5_TEST_FILES 两个）——


def _p5_src_path(stem: str) -> Path:
    """P5 模块茎 → src 实际路径（content/ 与 plugins/ 两目录二选一）。"""
    for sub in ("content", "plugins"):
        path = REPO_ROOT / "src" / "engine_v2" / sub / f"{stem}.py"
        if path.exists():
            return path
    raise AssertionError(f"P5 模块缺失：{stem}")


def _p5_test_paths() -> list[Path]:
    """P5 测试扫描面 15 文件 → 实际路径（content/ 与 plugins/ 两目录解析）。

    ``conftest.py`` 基名在两目录各一（白名单 #13/#26），元组内重复计数，
    去重后恰好 15 个不同路径。
    """
    dirs = (TESTS_ENGINE_DIR / "content", TESTS_ENGINE_DIR / "plugins")
    paths: list[Path] = []
    for name in P5_TEST_FILES:
        matches = [d / name for d in dirs if (d / name).exists()]
        assert matches, f"P5 测试扫描面文件缺失：{name}"
        paths.extend(matches)
    deduped = list(dict.fromkeys(paths))
    assert len(deduped) == 15, f"P5 测试扫描面应为 15 文件：{len(deduped)}"
    return deduped


def _p5_ast_face() -> list[Path]:
    """P5 AST/import 扫描面（27 文件）：10 模块 + 15 测试文件 + 测试侧 2
    个包 ``__init__.py``（§6.4 扫描面声明；2 个 src 侧 ``__init__.py``
    docstring-only（骨架已钉死），不入 AST/import 扫描面）。"""
    return (
        [_p5_src_path(stem) for stem in P5_SUBMODULES]
        + _p5_test_paths()
        + [
            TESTS_ENGINE_DIR / "content" / "__init__.py",
            TESTS_ENGINE_DIR / "plugins" / "__init__.py",
        ]
    )


def _p5_all_files() -> list[Path]:
    """P5 全文件文本扫描面（29 文件）：AST/import 扫描面 + src 侧 2 个包
    ``__init__.py``（§6.4 行 2「全部 P5 src+test 文件」口径）。"""
    return _p5_ast_face() + [
        REPO_ROOT / "src" / "engine_v2" / "content" / "__init__.py",
        REPO_ROOT / "src" / "engine_v2" / "plugins" / "__init__.py",
    ]


class TestP5Boundary:
    """P5 import 边界强化（P5 设计规范 §3.11 / §6.4，机械验证）。

    - ``P5_SUBMODULES`` 十个模块（content 7 + plugins 3）：绝对 import
      不得触及 ``datetime``/``time``/``random``/``asyncio``（复用 P4 同
      源常量 ``P4_NONDETERMINISM_ROOTS``）；
    - 12 名 casefold 词边界扫描全部 P5 src+test 文件 → 0 命中（常量以
      串拼接构造自豁免——P5 扫描面扩至 src+test，非 P4 明文常量仅 src
      六模块的同型先例；拼接集与 ``P4_LLM_PROVIDER_BLACKLIST`` 断言相
      等，复用既有常量作语义锚）；
    - 绝对 import 扫描：provider 根集 ∪ 网络库根 → 0 命中（网络库根 =
      ``NETWORK_IO_ROOTS`` 的网络部分，「httpx/requests/socket/urllib
      族」；std lib 进程根 subprocess/multiprocessing 不在本行字面范
      围——进程面由 T06 全树扫描兜底，唯一文档化例外 = SOT §6.5 要求
      的 test_p5_integration.py 子进程冒烟）；
    - ``content/loader.py`` + ``plugins/registry.py`` 封闭模式
      （import_module/__import__/spec_from_file_location/
      module_from_spec/entry.load()）→ 0 命中（断言 #6 的测试内实
      现；``importlib.metadata`` 静态元数据查询不在封闭模式——P5 零动
      态模块加载，W5 交付件 registry.py 既有先例）；
    - ``src.game.*``/``src.config.*``/``src.agents.*`` 绝对 import → 0
      命中（复用 V1 根集 + src 命名空间谓词，``_blacklist_category``
      既有辅助；§3.11 锚点同步）。

    扫描面 = §6.4 声明：10 模块 ∪ 15 测试文件 ∪ 测试侧 2 个包
    ``__init__.py``；2 个 src 侧 ``__init__.py`` 不入 AST/import 扫描
    面，只计入 ``test_p5_file_set`` 文件集断言。P5 专属常量仅 2 个
    （§3.11）。
    """

    def test_p5_file_set(self) -> None:
        """实际文件集（路径扫描）== ``P5_SUBMODULES``∪{__init__}×2 ∪
        ``P5_TEST_FILES`` ∪ {测试侧 2 个包 ``__init__.py``}（§6.4 行 1；
        §3.12 白名单代码面的测试内镜像，TestB1 文件集断言同型）。"""
        content_dir = REPO_ROOT / "src" / "engine_v2" / "content"
        plugins_dir = REPO_ROOT / "src" / "engine_v2" / "plugins"
        actual_stems = sorted(
            {p.stem for p in content_dir.glob("*.py")}
            | {p.stem for p in plugins_dir.glob("*.py")}
        )
        assert actual_stems == sorted(set(P5_SUBMODULES) | {"__init__"}), (
            f"P5 src 文件集与设计文档 §3.11 10 茎不符：{actual_stems}"
        )
        assert (content_dir / "__init__.py").exists(), "src content/__init__ 缺失"
        assert (plugins_dir / "__init__.py").exists(), "src plugins/__init__ 缺失"
        for path in _p5_test_paths():
            assert path.exists(), f"P5 测试文件缺失：{path}"
        assert (TESTS_ENGINE_DIR / "content" / "__init__.py").exists()
        assert (TESTS_ENGINE_DIR / "plugins" / "__init__.py").exists()

    def test_p5_12_name_blacklist(self) -> None:
        """12 名 casefold ``\\b`` 词边界扫描全部 P5 src+test 文件 → 0
        命中（§6.4 行 2）。

        常量以串拼接构造自豁免（P5 扫描面扩至 src+test，非 P4 先例）；
        拼接集与 ``P4_LLM_PROVIDER_BLACKLIST``（既有 12 明文常量）断言
        相等。负例锚：``llmsim``/``api_key_env`` 不命中（``\\w`` 边界
        语义钉死）。
        """
        joined = [
            "open" + "ai",
            "anthr" + "opic",
            "lang" + "chain",
            "lite" + "llm",
            "oll" + "ama",
            "gem" + "ini",
            "g" + "pt",
            "cla" + "ude",
            "l" + "lm",
            "prov" + "ider",
            "api_" + "key",
            "base_" + "url",
        ]
        assert set(joined) == P4_LLM_PROVIDER_BLACKLIST, "拼接集与 12 名常量不等"
        hits: dict[str, list[str]] = {}
        for path in _p5_all_files():
            text = path.read_text(encoding="utf-8").casefold()
            matched = [
                word
                for word in joined
                if re.search(rf"\b{re.escape(word)}\b", text)
            ]
            if matched:
                hits[str(path.relative_to(REPO_ROOT))] = matched
        assert not hits, f"P5 文件命中 12 名黑名单（§6.4）：{hits}"
        probe = re.compile(r"\b(?:" + "|".join(joined) + r")\b")
        assert not probe.search("llmsim"), "负例锚失守：llmsim 不应命中"
        assert not probe.search("api_key_env"), "负例锚失守：api_key_env 不应命中"

    def test_p5_forbidden_roots(self) -> None:
        """绝对 import 扫描：provider 根集 ∪ 网络库根 → 0 命中（§6.4
        行 3）。

        网络库根 = ``NETWORK_IO_ROOTS`` 的网络部分（「httpx/requests/
        socket/urllib 族」）；std lib 进程根 subprocess/multiprocessing
        不在本行字面范围——进程面由 T06 全树扫描兜底，唯一文档化例外
        = SOT §6.5 要求的 test_p5_integration.py 子进程冒烟。
        """
        forbidden = PROVIDER_ROOTS | (
            NETWORK_IO_ROOTS - {"subprocess", "multiprocessing"}
        )
        violations: dict[str, list[str]] = {}
        for path in _p5_ast_face():
            bad = [
                module_name
                for module_name in _collect_absolute_imports(path)
                if module_name.split(".")[0] in forbidden
            ]
            if bad:
                violations[str(path.relative_to(REPO_ROOT))] = bad
        assert not violations, f"P5 文件命中 provider/网络库根（§6.4）：{violations}"

    def test_p5_ast_nondeterminism(self) -> None:
        """AST 扫描 10 个 src 模块：time/random/datetime/asyncio import
        或属性调用 → 0 命中；content/loader.py + plugins/registry.py
        封闭模式（import_module/__import__/spec_from_file_location/
        module_from_spec/entry.load()）→ 0 命中（§6.4 行 4；断言 #6
        的测试内实现）。

        ``importlib.metadata`` 静态元数据查询（registry.py 的
        ``entry_points`` 面，W5 交付件既有先例）不在封闭模式——P5 零
        动态模块加载，允许静态元数据读取。
        """
        hits: list[str] = []
        for stem in P5_SUBMODULES:
            path = _p5_src_path(stem)
            for module_name in _collect_absolute_imports(path):
                if module_name.split(".")[0] in P4_NONDETERMINISM_ROOTS:
                    hits.append(f"{path.name}: import {module_name}")
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Name) and node.id in P4_NONDETERMINISM_ROOTS:
                    hits.append(f"{path.name}:L{node.lineno}: 使用 {node.id}")
                elif (
                    isinstance(node, ast.Attribute)
                    and node.attr in P4_NONDETERMINISM_ROOTS
                ):
                    hits.append(f"{path.name}:L{node.lineno}: 属性 {node.attr}")
        closed = {
            "import_module",
            "__import__",
            "spec_from_file_location",
            "module_from_spec",
        }
        for path in (_p5_src_path("loader"), _p5_src_path("registry")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and any(
                    alias.name in closed for alias in node.names
                ):
                    hits.append(f"{path.name}:L{node.lineno}: from-import 封闭模式")
                elif isinstance(node, ast.Name) and node.id in closed:
                    hits.append(f"{path.name}:L{node.lineno}: {node.id}")
                elif isinstance(node, ast.Attribute) and node.attr in closed:
                    hits.append(f"{path.name}:L{node.lineno}: {node.attr}")
                elif (
                    isinstance(node, ast.Attribute)
                    and node.attr == "load"
                    and isinstance(node.value, ast.Name)
                    and node.value.id == "entry"
                ):
                    hits.append(f"{path.name}:L{node.lineno}: entry.load()")
        assert not hits, (
            f"P5 模块命中非确定性根或动态加载封闭模式（§6.4）：{hits}"
        )

    def test_p5_no_v1_imports(self) -> None:
        """src.game.*/src.config.*/src.agents.* 绝对 import → 0 命中
        （§6.4 行 5；复用 V1 根集 + src 命名空间谓词，
        ``_blacklist_category`` 既有辅助；§3.11 锚点同步）。"""
        violations: dict[str, list[str]] = {}
        for path in _p5_ast_face():
            bad = [
                module_name
                for module_name in _collect_absolute_imports(path)
                if _blacklist_category(module_name)
                in ("v1 包（src 命名空间）", "v1 包（裸名）")
            ]
            if bad:
                violations[str(path.relative_to(REPO_ROOT))] = bad
        assert not violations, f"P5 文件命中 v1 包 import（§6.4）：{violations}"


# —— P6 扩展（P6 设计规范 §3.12 边界同步面，纯追加 Leader hunk，P5 块同构）——

#: P6 11 模块茎（封闭）：前 8 = llm/，后 3 = prompts/（§3.12）。
P6_SUBMODULES: tuple[str, ...] = (
    "profiles",
    "deployment",
    "router",
    "adapter",
    "structured",
    "policy",
    "staleness",
    "critic",
    "registry",
    "assembler",
    "diagnostic",
)

#: P6 测试扫描面（15 文件，封闭，不含 ``__init__.py``）：llm/ 10 测试文件 +
#: llm/ conftest + prompts/ 2 测试文件 + 边界文件自身 + scripts/llm_smoke.py
#: （smoke 同入边界扫描域，Leader-A10；§3.12）。边界文件自身 = 白名单 #37
#: 纯追加块宿主：方法 2 字符串字面量面排除，方法 1/3/4/5/6 import/文件集
#: 面保留（既有冻结内容含 12 名明文常量，不可移除）。
P6_TEST_FILES: tuple[str, ...] = (
    "test_profiles.py",
    "test_deployment.py",
    "test_router.py",
    "test_adapter.py",
    "test_structured.py",
    "test_policy.py",
    "test_staleness.py",
    "test_critic.py",
    "test_p6_gate_scenario.py",
    "test_p6_adversarial.py",
    "conftest.py",
    "test_registry.py",
    "test_assembler.py",
    "test_import_boundary.py",
    "llm_smoke.py",
)

#: P6 白名单 37 文件（封闭，§3.13 表波次序 #1-37；gate ③ 的 pytest 内镜像）。
_P6_WHITELIST_37: tuple[str, ...] = (
    "src/engine_v2/llm/profiles.py",
    "src/engine_v2/llm/deployment.py",
    "src/engine_v2/prompts/diagnostic.py",
    "tests/engine_v2/llm/test_profiles.py",
    "tests/engine_v2/llm/test_deployment.py",
    "src/engine_v2/llm/router.py",
    "tests/engine_v2/llm/test_router.py",
    "src/engine_v2/llm/adapter.py",
    "tests/engine_v2/llm/__init__.py",
    "tests/engine_v2/llm/test_adapter.py",
    "src/engine_v2/llm/structured.py",
    "src/engine_v2/prompts/registry.py",
    "src/engine_v2/prompts/assembler.py",
    "tests/engine_v2/llm/test_structured.py",
    "tests/engine_v2/prompts/__init__.py",
    "tests/engine_v2/prompts/test_registry.py",
    "tests/engine_v2/prompts/test_assembler.py",
    "src/engine_v2/llm/policy.py",
    "src/engine_v2/llm/staleness.py",
    "tests/engine_v2/llm/conftest.py",
    "tests/engine_v2/llm/test_policy.py",
    "tests/engine_v2/llm/test_staleness.py",
    "src/engine_v2/llm/critic.py",
    "pyproject.toml",
    "tests/engine_v2/llm/test_critic.py",
    "tests/engine_v2/llm/test_p6_gate_scenario.py",
    "tests/engine_v2/llm/test_p6_adversarial.py",
    "tests/fixtures/v2_project_llm/game.yaml",
    "tests/fixtures/v2_project_llm/characters/alice.yaml",
    "tests/fixtures/v2_project_llm/prompts/game_policy.yaml",
    "tests/fixtures/v2_project_llm/prompts/character_alice.yaml",
    "tests/fixtures/v2_project_llm/prompts/game_policy.md",
    "tests/fixtures/v2_project_llm/prompts/character_alice.md",
    "tests/fixtures/v2_deployment/deployment.yaml",
    "tests/fixtures/v2_deployment/deployment_alt.yaml",
    "scripts/llm_smoke.py",
    "tests/engine_v2/core/test_import_boundary.py",
)


def _p6_src_path(stem: str) -> Path:
    """P6 模块茎 → src 实际路径（llm/ 与 prompts/ 两目录二选一）。"""
    for sub in ("llm", "prompts"):
        path = REPO_ROOT / "src" / "engine_v2" / sub / f"{stem}.py"
        if path.exists():
            return path
    raise AssertionError(f"P6 模块缺失：{stem}")


def _p6_test_path(name: str) -> Path:
    """P6 测试扫描面基名 → 实际路径（封闭映射，4 个解析目标：tests llm/ ·
    prompts/ · core/ 与 scripts/）。

    ``conftest.py`` 基名在 llm/ 与 core/ 两目录各一（core/ 侧 = P4/P5 世界
    夹具，非 P6 面），故不做目录探测，映射封闭钉死（实现面裁定，SOT 未钉
    解析目录）。
    """
    if name == "llm_smoke.py":
        path = REPO_ROOT / "scripts" / name
    elif name == "test_import_boundary.py":
        path = TESTS_ENGINE_DIR / "core" / name
    elif name in ("test_registry.py", "test_assembler.py"):
        path = TESTS_ENGINE_DIR / "prompts" / name
    else:
        path = TESTS_ENGINE_DIR / "llm" / name
    assert path.exists(), f"P6 测试扫描面文件缺失：{name}"
    return path


def _p6_test_paths() -> list[Path]:
    """P6 测试扫描面 15 文件 → 实际路径（P6_TEST_FILES 逐一封闭映射）。"""
    paths = [_p6_test_path(name) for name in P6_TEST_FILES]
    assert len(paths) == 15, f"P6 测试扫描面应为 15 文件：{len(paths)}"
    return paths


def _p6_ast_face() -> list[Path]:
    """P6 AST/import 扫描面（28 文件）：11 模块 + 15 测试扫描面文件 + 测试
    侧 2 个包 ``__init__.py``（§3.12 方法 1/3/4/5/6 import/文件集面域；
    边界文件自身在此保留；2 个既有骨架 src ``__init__.py`` P0 冻结、
    不在白名单、不入本面）。"""
    return (
        [_p6_src_path(stem) for stem in P6_SUBMODULES]
        + _p6_test_paths()
        + [
            TESTS_ENGINE_DIR / "llm" / "__init__.py",
            TESTS_ENGINE_DIR / "prompts" / "__init__.py",
        ]
    )


def _p6_string_literal_face() -> list[Path]:
    """P6 方法 2 字符串字面量扫描面（27 文件）：AST/import 扫描面扣减边界
    文件自身（SOT §3.12 方法 2；其既有冻结内容含 12 名明文常量）。本块
    追加内容同样以拼接构造自豁免，不做单独块级扫描（与 P5 完全同构）。"""
    boundary = TESTS_ENGINE_DIR / "core" / "test_import_boundary.py"
    return [p for p in _p6_ast_face() if p != boundary]


class TestP6Boundary:
    """P6 import 边界强化（P6 设计规范 §3.12 / §6.4，机械验证；纯追加
    Leader hunk，TestP5Boundary 同构）。

    - ``P6_SUBMODULES`` 11 模块（llm 8 + prompts 3）：asyncio 零出现
      （方法 4）；random/datetime = 0 命中；``time`` 与 httpx import 仅
      llm/adapter.py + test_adapter.py MockTransport 面（D-P6-13 两处
      文档化例外 + B3 受控偏离 ERR-P6-6；ERR-P6-12）；socket/urllib/
      requests/http.client = 0；动态加载面 = 0（边界文件自身 P4 冻结
      harness 自豁免，ERR-P6-12；方法 5）；v1 根集绝对 import（含
      src.llm.*/src.prompts.*）= 0（方法 3）；
    - 12 名 casefold 词边界扫描 AST 字符串字面量面 → 0 命中（方法 2；较
      P5 全文口径收紧为 ``ast.Constant`` str 域（含 docstring）；27 文件
      域 = 11 新建 src 模块 + 15 测试扫描面文件 − 边界文件自身 + 2 测试
      侧包 ``__init__.py``；探针串拼接构造，拼接集与
      ``P4_LLM_PROVIDER_BLACKLIST`` 断言相等；负例锚 ``llmsim``/
      ``api_key_env``）；
    - ``policy.py`` 模块 import ∩ {httpx, time, random, asyncio, datetime,
      socket, urllib, requests} = ∅；``LLMPolicy`` 类体零具体后端类名
      （B-CON-4 AST 面，方法 6）；
    - 白名单 37 文件闭集断言（方法 1，gate ③ 的 pytest 内镜像）。
    """

    def test_p6_file_set_closed(self) -> None:
        """白名单 37 文件闭集断言（gate ③ 的 pytest 内镜像；§3.13 表）。

        目录封闭面：src llm/ = 8 新建 + 骨架 __init__（9 .py）；src
        prompts/ = 3 新建 + 骨架 __init__（4 .py）；tests llm/ = 10 测试
        + conftest + __init__（12 .py）；tests prompts/ = 2 测试 +
        __init__（3 .py）；fixture 树 = 8 文件；pyproject.toml 与本文件
        修改面在位。
        """
        for rel in _P6_WHITELIST_37:
            assert (REPO_ROOT / rel).exists(), f"白名单文件缺失：{rel}"
        llm_src = sorted(
            p.name for p in (REPO_ROOT / "src" / "engine_v2" / "llm").glob("*.py")
        )
        assert llm_src == sorted(
            [f"{s}.py" for s in P6_SUBMODULES[:8]] + ["__init__.py"]
        ), f"src llm/ 文件集非封闭：{llm_src}"
        prompts_src = sorted(
            p.name for p in (REPO_ROOT / "src" / "engine_v2" / "prompts").glob("*.py")
        )
        assert prompts_src == sorted(
            [f"{s}.py" for s in P6_SUBMODULES[8:]] + ["__init__.py"]
        ), f"src prompts/ 文件集非封闭：{prompts_src}"
        llm_tests = sorted(p.name for p in (TESTS_ENGINE_DIR / "llm").glob("*.py"))
        assert llm_tests == sorted(
            [
                "test_profiles.py",
                "test_deployment.py",
                "test_router.py",
                "test_adapter.py",
                "test_structured.py",
                "test_policy.py",
                "test_staleness.py",
                "test_critic.py",
                "test_p6_gate_scenario.py",
                "test_p6_adversarial.py",
                "conftest.py",
                "__init__.py",
            ]
        ), f"tests llm/ 文件集非封闭：{llm_tests}"
        prompts_tests = sorted(
            p.name for p in (TESTS_ENGINE_DIR / "prompts").glob("*.py")
        )
        assert prompts_tests == sorted(
            ["test_registry.py", "test_assembler.py", "__init__.py"]
        ), f"tests prompts/ 文件集非封闭：{prompts_tests}"
        fixtures = sorted(
            str(p.relative_to(REPO_ROOT))
            for d in (
                "tests/fixtures/v2_project_llm",
                "tests/fixtures/v2_deployment",
            )
            for p in (REPO_ROOT / d).rglob("*")
            if p.is_file()
        )
        assert fixtures == sorted(
            [
                "tests/fixtures/v2_project_llm/game.yaml",
                "tests/fixtures/v2_project_llm/characters/alice.yaml",
                "tests/fixtures/v2_project_llm/prompts/game_policy.yaml",
                "tests/fixtures/v2_project_llm/prompts/character_alice.yaml",
                "tests/fixtures/v2_project_llm/prompts/game_policy.md",
                "tests/fixtures/v2_project_llm/prompts/character_alice.md",
                "tests/fixtures/v2_deployment/deployment.yaml",
                "tests/fixtures/v2_deployment/deployment_alt.yaml",
            ]
        ), f"fixture 树文件集非封闭：{fixtures}"

    def test_p6_no_12_name_in_string_literals(self) -> None:
        """AST 字符串字面量域 12 名 casefold 词边界扫描 → 0 命中（§3.12
        方法 2）。

        较 P5 全文口径收紧为 ``ast.Constant`` str 节点值域（含 docstring）；
        27 文件域见 ``_p6_string_literal_face``。常量以串拼接构造自豁免
        （本文件不在方法 2 扫描面；本追加块自身同以拼接构造自豁免——与
        P5 完全同构）；拼接集与 ``P4_LLM_PROVIDER_BLACKLIST``（既有 12
        明文常量）断言相等。负例锚：``llmsim``/``api_key_env`` 不命中
        （``\\w`` 边界语义钉死）。
        """
        joined = [
            "open" + "ai",
            "anthr" + "opic",
            "lang" + "chain",
            "lite" + "llm",
            "oll" + "ama",
            "gem" + "ini",
            "g" + "pt",
            "cla" + "ude",
            "l" + "lm",
            "prov" + "ider",
            "api_" + "key",
            "base_" + "url",
        ]
        assert set(joined) == P4_LLM_PROVIDER_BLACKLIST, "拼接集与 12 名常量不等"
        hits: dict[str, list[str]] = {}
        for path in _p6_string_literal_face():
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            matched: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    text = node.value.casefold()
                    matched.update(
                        word
                        for word in joined
                        if re.search(rf"\b{re.escape(word)}\b", text)
                    )
            if matched:
                hits[str(path.relative_to(REPO_ROOT))] = sorted(matched)
        assert not hits, f"P6 文件命中 12 名黑名单字符串字面量域（§3.12 方法 2）：{hits}"
        probe = re.compile(r"\b(?:" + "|".join(joined) + r")\b")
        assert not probe.search("llmsim"), "负例锚失守：llmsim 不应命中"
        assert not probe.search("api_key_env"), "负例锚失守：api_key_env 不应命中"

    def test_p6_no_v1_absolute_imports(self) -> None:
        """v1 根集绝对 import = 0（§3.12 方法 3；D-P6-13 禁止面：
        src.game.* / src.config.* / src.agents.* / src.llm.* /
        src.prompts.*；扫描面 = 28 文件 import 面，边界文件自身保留）。"""
        forbidden = {
            "src.game",
            "src.config",
            "src.agents",
            "src.llm",
            "src.prompts",
        }
        violations: dict[str, list[str]] = {}
        for path in _p6_ast_face():
            bad = [
                module_name
                for module_name in _collect_absolute_imports(path)
                if module_name in forbidden
                or any(module_name.startswith(root + ".") for root in forbidden)
            ]
            if bad:
                violations[str(path.relative_to(REPO_ROOT))] = bad
        assert not violations, f"P6 文件命中 v1 根 import（§3.12 方法 3）：{violations}"

    def test_p6_zero_asyncio(self) -> None:
        """asyncio import = 0 且 ``ast.AsyncFunctionDef`` = 0（§3.12 方法
        4；P6 同步面零 asyncio，扫描面 = 28 文件）。"""
        hits: list[str] = []
        for path in _p6_ast_face():
            for module_name in _collect_absolute_imports(path):
                if module_name.split(".")[0] == "asyncio":
                    hits.append(f"{path.name}: import {module_name}")
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.AsyncFunctionDef):
                    hits.append(f"{path.name}:L{node.lineno}: async def {node.name}")
        assert not hits, f"P6 文件命中 asyncio 面（§3.12 方法 4）：{hits}"

    def test_p6_nondeterminism_and_io_surface(self) -> None:
        """random/datetime = 0 命中；``time`` 与 httpx import 仅
        llm/adapter.py（+ test_adapter.py MockTransport 进程内面 = B3
        受控偏离 ERR-P6-6，唯一文档化测试侧 httpx import）；socket/
        urllib/requests/http.client = 0；动态加载面（importlib/
        __import__）= 0（§3.12 方法 5；D-P6-13 两处文档化例外 ①httpx
        ②time 均限定 adapter）。

        边界文件自身 P4 冻结可导入性探针 harness（importlib.import_module）
        自豁免（同方法 2 排除同型，ERR-P6-12）；经冻结 adapter 模块
        命名空间取用 in-process 传输替身的属性面（W6 gate 测试面）非
        import 面——本方法仅扫 AST import 节点。
        """
        adapter = _p6_src_path("adapter")
        mock_transport_test = TESTS_ENGINE_DIR / "llm" / "test_adapter.py"
        boundary = TESTS_ENGINE_DIR / "core" / "test_import_boundary.py"
        hits: list[str] = []
        for path in _p6_ast_face():
            for module_name in _collect_absolute_imports(path):
                root = module_name.split(".")[0]
                if root in ("random", "datetime"):
                    hits.append(f"{path.name}: import {module_name}")
                elif root in ("time", "httpx") and path not in (
                    adapter,
                    mock_transport_test,
                ):
                    hits.append(
                        f"{path.name}: import {module_name}（仅 llm/adapter.py"
                        " + test_adapter.py MockTransport 面允许）"
                    )
                elif (
                    module_name in ("socket", "urllib", "requests", "http.client")
                    or module_name.startswith(
                        ("socket.", "urllib.", "requests.", "http.client.")
                    )
                ):
                    hits.append(f"{path.name}: import {module_name}")
                elif root == "importlib" and path != boundary:
                    hits.append(f"{path.name}: import {module_name}（动态加载面）")
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if (
                    path != boundary
                    and (
                        (isinstance(node, ast.Name) and node.id == "__import__")
                        or (isinstance(node, ast.Attribute) and node.attr == "__import__")
                    )
                ):
                    hits.append(f"{path.name}:L{node.lineno}: __import__（动态加载面）")
        assert not hits, f"P6 文件命中非确定性/IO 面（§3.12 方法 5）：{hits}"

    def test_p6_policy_strict_face(self) -> None:
        """policy.py 模块 import ∩ {httpx, time, random, asyncio, datetime,
        socket, urllib, requests} = ∅；``LLMPolicy`` 类体（含方法体）零
        具体后端/时钟类名与零网络对象（B-CON-4 AST 面，§3.12 方法 6；
        协议 Protocol 面 InferenceBackend/MonotonicClock 注解 = 允许面）。
        """
        policy = _p6_src_path("policy")
        forbidden_roots = {
            "httpx",
            "time",
            "random",
            "asyncio",
            "datetime",
            "socket",
            "urllib",
            "requests",
        }
        bad_imports = [
            module_name
            for module_name in _collect_absolute_imports(policy)
            if module_name.split(".")[0] in forbidden_roots
        ]
        assert not bad_imports, (
            f"policy.py 命中禁止 import 根（§3.12 方法 6）：{bad_imports}"
        )
        forbidden_names = {
            "HttpxInferenceBackend",
            "FakeInferenceBackend",
            "SystemMonotonicClock",
            "FixedMonotonicClock",
            "random",
            "httpx",
            "socket",
            "urllib",
            "requests",
        }
        tree = ast.parse(policy.read_text(encoding="utf-8"), filename=str(policy))
        class_body_hits: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "LLMPolicy":
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Name) and sub.id in forbidden_names:
                        class_body_hits.append(f"L{sub.lineno}: Name {sub.id}")
                    elif isinstance(sub, ast.Attribute) and sub.attr in forbidden_names:
                        class_body_hits.append(f"L{sub.lineno}: Attribute {sub.attr}")
        assert not class_body_hits, (
            f"LLMPolicy 类体命中具体后端/时钟/网络面（B-CON-4，§3.12 方法 6）："
            f"{class_body_hits}"
        )

# —— P7 扩展（P7 SOT §3.9 TestP7Boundary 6 法 / §3.10 白名单 23 文件 / §8.2
# 导出账本 35 名；纯追加 Leader hunk，TestP6Boundary 同构；本文件进程无操作
# 纪律：全部 6 法零 subprocess）——

#: P7 src 8 模块（§3.10 白名单 #1-#3/#11/#13/#15-#17；skeleton
#: ``dynamics/__init__.py`` 占位不在此列，基线 e816a64 已存在，gate ③
#: ``git diff --stat`` 零）。
P7_SRC_SUBMODULES: tuple[str, ...] = (
    "backend",
    "diagnostic",
    "rule",
    "toy_rigid",
    "llm_world",
    "composite",
    "authority",
    "host",
)

#: P7 测试扫描面（12 文件，封闭，含 ``__init__.py`` + conftest；SOT
#: §3.9 方法 2 / E2 的 12 测试面）。
P7_TEST_FILES: tuple[str, ...] = (
    "__init__.py",
    "conftest.py",
    "test_backend_metadata.py",
    "test_toy_rigid.py",
    "test_diagnostic.py",
    "test_rule_dynamics.py",
    "test_llm_world.py",
    "test_composite.py",
    "test_authority_host.py",
    "test_host_driver.py",
    "test_g7_scenarios.py",
    "test_p7_adversarial.py",
)

#: P7 白名单 23 文件（封闭，§3.10 表波次序 #1-23；gate ③ 的 pytest 内
#: 闭集镜像，方法 5；docs/ 依设计不入白名单）。
_P7_WHITELIST_23: tuple[str, ...] = (
    "src/engine_v2/dynamics/backend.py",
    "src/engine_v2/dynamics/diagnostic.py",
    "src/engine_v2/dynamics/toy_rigid.py",
    "tests/engine_v2/dynamics/__init__.py",
    "tests/engine_v2/dynamics/conftest.py",
    "tests/engine_v2/dynamics/test_backend_metadata.py",
    "tests/engine_v2/dynamics/test_toy_rigid.py",
    "tests/engine_v2/dynamics/test_diagnostic.py",
    "tests/fixtures/v2_deployment_p7/deployment.yaml",
    "tests/fixtures/v2_project_p7/game.yaml",
    "src/engine_v2/dynamics/rule.py",
    "tests/engine_v2/dynamics/test_rule_dynamics.py",
    "src/engine_v2/dynamics/llm_world.py",
    "tests/engine_v2/dynamics/test_llm_world.py",
    "src/engine_v2/dynamics/composite.py",
    "src/engine_v2/dynamics/authority.py",
    "src/engine_v2/dynamics/host.py",
    "tests/engine_v2/dynamics/test_composite.py",
    "tests/engine_v2/dynamics/test_authority_host.py",
    "tests/engine_v2/dynamics/test_host_driver.py",
    "tests/engine_v2/dynamics/test_g7_scenarios.py",
    "tests/engine_v2/dynamics/test_p7_adversarial.py",
    "tests/engine_v2/core/test_import_boundary.py",
)

#: P7 导出账本（§8.2 序钉死；边界方法 6 集合 + 序双等机械核；总 35 名）。
P7_EXPORT_LEDGER: dict[str, tuple[str, ...]] = {
    "backend": (
        "WorldSnapshot",
        "Stimulus",
        "STIMULUS_KINDS",
        "DynamicsContext",
        "InferenceBudget",
        "BackendMetadata",
        "DETERMINISM_CLASSES",
        "IMPLEMENTATION_TYPES",
        "FIDELITY_PATTERN",
        "WorldDynamicsBackend",
        "new_deterministic_effect_id",
        "DynamicsError",
    ),
    "diagnostic": ("DynamicsDiagnostic", "P7_DYNAMICS_DIAGNOSTIC_CODES"),
    "rule": ("WorldRule", "RuleDynamics", "RULE_CONDITION_OPERATORS"),
    "toy_rigid": ("ToyRigidDynamics", "RIGID_COMPONENT", "TOY_CHECKPOINT_VERSION"),
    "llm_world": (
        "LLMWorldDynamics",
        "LLMWorldDynamicsConfig",
        "DynamicsProposalWire",
        "DynamicsEffectWire",
    ),
    "composite": ("CompositeDynamics", "determinism_join"),
    "authority": (
        "P7_PRODUCER_IDS",
        "RULE_DYNAMICS_PRODUCER",
        "LLM_WORLD_DYNAMICS_PRODUCER",
        "RIGID_BODY_PRODUCER",
        "COMPOSITE_DYNAMICS_PRODUCER",
        "build_dynamics_producers",
        "default_dynamics_policy",
    ),
    "host": ("run_dynamics_turn", "DynamicsTurn"),
}


def _p7_ast_face() -> list[Path]:
    """P7 方法 1 AST import 扫描面（21 文件 = 8 src + 12 tests + 1 锚点；
    SOT §3.9 方法 1 / E6）。"""
    src = [
        REPO_ROOT / "src" / "engine_v2" / "dynamics" / f"{stem}.py"
        for stem in P7_SRC_SUBMODULES
    ]
    tests = [TESTS_ENGINE_DIR / "dynamics" / name for name in P7_TEST_FILES]
    anchor = TESTS_ENGINE_DIR / "core" / "test_import_boundary.py"
    return src + tests + [anchor]


def _p7_string_literal_face() -> list[Path]:
    """P7 方法 3 字符串字面量扫描面（20 文件 = 21 − 锚点自身；SOT §3.9
    方法 3 / E6：锚点含 12 名黑名单字面量本体（P4_LLM_PROVIDER_BLACKLIST），
    P6 同款口径排除）。"""
    anchor = TESTS_ENGINE_DIR / "core" / "test_import_boundary.py"
    return [path for path in _p7_ast_face() if path != anchor]


class TestP7Boundary:
    """P7 import 边界强化（P7 SOT §3.9 6 法，机械验证；纯追加 Leader
    hunk，TestP5Boundary/TestP6Boundary 同构；本文件零 subprocess 纪律）。

    - 方法 1（``test_p7_import_whitelist``）：AST import 面 21 文件（8 src
      + 12 tests + 1 锚点）全部绝对 import ∈ SOT §3.0 闭集白名单（模块根
      面）；黑名单（asyncio/httpx/random/datetime/socket/urllib/requests/
      subprocess + v1 五根 src.game/src.config/src.agents/src.llm/
      src.prompts）零命中；零相对 import（模块面封闭）；
    - 方法 2（``test_p7_test_files_closed``）：测试扫描面 == 12 文件（含
      conftest + __init__），与磁盘目录双向相等；
    - 方法 3（``test_p7_k8_string_literals``）：字符串字面量面 20 文件（锚
      点除外）12 名闭集 casefold + 词边界零命中（``ast.Constant`` str 域
      含 docstring，K8 口径）；探针串拼接构造自豁免，拼接集与
      ``P4_LLM_PROVIDER_BLACKLIST`` 断言相等；负例锚 ``llmsim``/
      ``api_key_env`` 不命中；
    - 方法 4（``test_p7_kernel_agnostic_and_sync``）：(a) kernel 无感——
      core/** 全量文件零命中 ``engine_v2.dynamics`` 包路径 / if-elif
      字面 / 35 P7 export 名（35 名运行时自 8 模块 ``__all__`` 派生，与
      §8.2 自动同步；已知合法面：core/state.py docstring 裸词
      "dynamics"（backend_kind 词表说明）不在 token 集）；(b) P7 src 8
      文件零 ``async def`` / ``await``（D-P7-01 同步面）；
    - 方法 5（``test_p7_whitelist_diff``）：白名单 23 文件闭集断言
      （gate ③ 的 pytest 内镜像，P6 方法 1 file_set_closed 口径：23 文件
      全存在 + src dynamics/ 目录封闭 8 + 骨架 __init__ + tests
      dynamics/ 封闭 12 + fixtures 2 文件；字面
      ``git diff --name-only e816a64..HEAD -- src tests scripts == 23``
      由 G7 gate ③ Leader bash 执行，§3.10 步 3——边界文件零 subprocess
      先例下 pytest 侧以目录封闭镜像承载）；
    - 方法 6（``test_p7_export_ledger``）：8 模块 ``__all__`` == §8.2
      账本（集合 + 序双等）；总 35 名。
    """

    def test_p7_import_whitelist(self) -> None:
        """方法 1：AST import 面 21 文件——绝对 import ∈ SOT §3.0 闭集
        白名单（模块根面）；黑名单零命中；零相对 import。"""
        allowed_roots = (
            "__future__",
            "ast",
            "collections",
            "dataclasses",
            "hashlib",
            "importlib",
            "json",
            "pathlib",
            "re",
            "sys",
            "typing",
            "pydantic",
            "pytest",
            "src.engine_v2.core",
            "src.engine_v2.content.loader",
            "src.engine_v2.content.schemas",
            "src.engine_v2.dynamics",
            "src.engine_v2.llm.adapter",
            "src.engine_v2.llm.deployment",
            "src.engine_v2.llm.profiles",
            "src.engine_v2.llm.structured",
            "src.engine_v2.prompts.diagnostic",
            "tests.engine_v2.core.test_import_boundary",
            "tests.engine_v2.dynamics.conftest",
        )
        forbidden = (
            "asyncio",
            "httpx",
            "random",
            "datetime",
            "socket",
            "urllib",
            "requests",
            "subprocess",
            "src.game",
            "src.config",
            "src.agents",
            "src.llm",
            "src.prompts",
        )

        def _check(module_name: str) -> str | None:
            if any(
                module_name == root or module_name.startswith(root + ".")
                for root in forbidden
            ):
                return f"黑名单命中：{module_name}"
            if not any(
                module_name == root or module_name.startswith(root + ".")
                for root in allowed_roots
            ):
                return f"不在闭集白名单：{module_name}"
            return None

        violations: dict[str, list[str]] = {}
        for path in _p7_ast_face():
            rel = str(path.relative_to(REPO_ROOT))
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                modules: list[str] = []
                if isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    if node.level != 0:
                        violations.setdefault(rel, []).append(
                            f"L{node.lineno}: 相对 import（模块面封闭，零相对 import）"
                        )
                        continue
                    modules = [node.module or ""]
                for module_name in modules:
                    problem = _check(module_name)
                    if problem is not None:
                        violations.setdefault(rel, []).append(
                            f"L{node.lineno}: {problem}"
                        )
        assert not violations, f"P7 import 面违规（SOT §3.9 方法 1）：{violations}"

    def test_p7_test_files_closed(self) -> None:
        """方法 2：测试扫描面 == 12 文件（含 conftest + __init__），与磁盘
        目录双向相等（SOT §3.9 方法 2）。"""
        disk = sorted(p.name for p in (TESTS_ENGINE_DIR / "dynamics").glob("*.py"))
        assert disk == sorted(P7_TEST_FILES), (
            f"tests/engine_v2/dynamics/ 目录非封闭（P7_TEST_FILES 12 文件）："
            f"{disk}"
        )

    def test_p7_k8_string_literals(self) -> None:
        """方法 3：字符串字面量面 20 文件（8 src + 12 tests，锚点除外）
        12 名闭集零命中（K8；``ast.Constant`` str 域含 docstring；casefold
        + 词边界）。探针串拼接构造自豁免（本文件不在方法 3 扫描面；本追加
        块同以拼接构造自豁免——与 P5/P6 完全同构）；拼接集与
        ``P4_LLM_PROVIDER_BLACKLIST`` 断言相等。负例锚：``llmsim``/
        ``api_key_env`` 不命中（``\\w`` 边界语义钉死）。"""
        joined = [
            "open" + "ai",
            "anthr" + "opic",
            "lang" + "chain",
            "lite" + "llm",
            "oll" + "ama",
            "gem" + "ini",
            "g" + "pt",
            "cla" + "ude",
            "l" + "lm",
            "prov" + "ider",
            "api_" + "key",
            "base_" + "url",
        ]
        assert set(joined) == P4_LLM_PROVIDER_BLACKLIST, "拼接集与 12 名常量不等"

        # ERR-P7-14 自检：词边界模式必须命中空格分隔形（W5 R1 0x08 控制字节腐蚀教训；
        # 若转义再退化为控制字节，此处响亮失败而非恒绿）
        for word in joined:
            _pat = re.compile(rf"\b{re.escape(word)}\b")
            assert _pat.search(f" {word} "), f"K8 自检失守: {word!r}"
        hits: dict[str, list[str]] = {}
        for path in _p7_string_literal_face():
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            matched: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    text = node.value.casefold()
                    matched.update(
                        word
                        for word in joined
                        if re.search(rf"\b{re.escape(word)}\b", text)
                    )
            if matched:
                hits[str(path.relative_to(REPO_ROOT))] = sorted(matched)
        assert not hits, (
            f"P7 文件命中 12 名黑名单字符串字面量域（SOT §3.9 方法 3）：{hits}"
        )
        probe = re.compile(r"\b(?:" + "|".join(joined) + r")\b")
        assert not probe.search("llmsim"), "负例锚失守：llmsim 不应命中"
        assert not probe.search("api_key_env"), "负例锚失守：api_key_env 不应命中"

    def test_p7_kernel_agnostic_and_sync(self) -> None:
        """方法 4：(a) core/** 全量零命中 ``engine_v2.dynamics`` 包路径 /
        if-elif 字面 / 35 P7 export 名（运行时自 8 模块 ``__all__`` 派生；
        已知合法面 core/state.py docstring 裸词 "dynamics" 不在 token
        集）；(b) P7 src 8 文件零 ``async def`` / ``await``。"""
        import src.engine_v2.dynamics.authority as _p7_authority
        import src.engine_v2.dynamics.backend as _p7_backend
        import src.engine_v2.dynamics.composite as _p7_composite
        import src.engine_v2.dynamics.diagnostic as _p7_diagnostic
        import src.engine_v2.dynamics.host as _p7_host
        import src.engine_v2.dynamics.llm_world as _p7_llm_world
        import src.engine_v2.dynamics.rule as _p7_rule
        import src.engine_v2.dynamics.toy_rigid as _p7_toy_rigid

        p7_exports = tuple(
            name
            for module in (
                _p7_backend,
                _p7_diagnostic,
                _p7_rule,
                _p7_toy_rigid,
                _p7_llm_world,
                _p7_composite,
                _p7_authority,
                _p7_host,
            )
            for name in module.__all__
        )
        assert len(p7_exports) == 35, f"P7 导出账本应为 35 名：{len(p7_exports)}"
        tokens = (
            "engine_v2.dynamics",
            "if backend is",
            "elif backend is",
            *p7_exports,
        )
        core_hits: dict[str, list[str]] = {}
        for path in sorted(CORE_DIR.rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            matched = [token for token in tokens if token in text]
            if matched:
                core_hits[str(path.relative_to(REPO_ROOT))] = matched
        assert not core_hits, (
            f"kernel（core/）引用 P7 类型名/包路径（SOT §3.9 方法 4 (a)）："
            f"{core_hits}"
        )
        async_hits: dict[str, int] = {}
        for stem in P7_SRC_SUBMODULES:
            path = REPO_ROOT / "src" / "engine_v2" / "dynamics" / f"{stem}.py"
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            count = sum(
                1
                for node in ast.walk(tree)
                if isinstance(node, (ast.AsyncFunctionDef, ast.Await))
            )
            if count:
                async_hits[path.name] = count
        assert not async_hits, f"P7 src 零 async def / await（方法 4 (b)）：{async_hits}"

    def test_p7_whitelist_diff(self) -> None:
        """方法 5：白名单 23 文件闭集断言——gate ③ 的 pytest 内镜像（P6
        方法 1 file_set_closed 口径）：23 文件全存在；src dynamics/ 目录
        封闭（8 新建 + 骨架 __init__ 占位，占位字节不变由 gate ③
        ``git diff --stat`` 零核验）；tests dynamics/ 封闭（12）；P7
        fixture 树 = 2 文件。字面 ``git diff --name-only e816a64..HEAD --
        src tests scripts == 23`` 由 G7 gate ③ Leader bash 执行（§3.10
        步 3）——边界文件零 subprocess 纪律下 pytest 侧以目录封闭镜像
        承载。"""
        for rel in _P7_WHITELIST_23:
            assert (REPO_ROOT / rel).exists(), f"白名单文件缺失：{rel}"
        dynamics_src = sorted(
            p.name for p in (REPO_ROOT / "src" / "engine_v2" / "dynamics").glob("*.py")
        )
        assert dynamics_src == sorted(
            [f"{stem}.py" for stem in P7_SRC_SUBMODULES] + ["__init__.py"]
        ), f"src dynamics/ 文件集非封闭（8 + 骨架 __init__）：{dynamics_src}"
        dynamics_tests = sorted(p.name for p in (TESTS_ENGINE_DIR / "dynamics").glob("*.py"))
        assert dynamics_tests == sorted(P7_TEST_FILES), (
            f"tests dynamics/ 文件集非封闭（12 文件）：{dynamics_tests}"
        )
        fixtures = sorted(
            str(p.relative_to(REPO_ROOT))
            for d in ("tests/fixtures/v2_deployment_p7", "tests/fixtures/v2_project_p7")
            for p in (REPO_ROOT / d).rglob("*")
            if p.is_file()
        )
        assert fixtures == [
            "tests/fixtures/v2_deployment_p7/deployment.yaml",
            "tests/fixtures/v2_project_p7/game.yaml",
        ], f"P7 fixture 树非封闭（2 文件）：{fixtures}"

    def test_p7_export_ledger(self) -> None:
        """方法 6：8 模块 ``__all__`` == §8.2 账本（集合 + 序双等）；总 35
        名（SOT §3.9 方法 6 / E4 机械核）。"""
        total = 0
        for stem in P7_SRC_SUBMODULES:
            module = importlib.import_module(f"src.engine_v2.dynamics.{stem}")
            actual = tuple(module.__all__)
            expected = P7_EXPORT_LEDGER[stem]
            assert actual == expected, (
                f"{stem}.py __all__ 与 §8.2 账本不等（集合 + 序双等）：{actual}"
            )
            total += len(actual)
        assert total == 35, f"导出账本总数应为 35：{total}"


# —— P8 扩展（P8 SOT §3.10.3 TestP8Boundary 6 法 / §3.10.2 白名单 25 文件 /
# §8.2 导出账本 44 名；W5 纯追加 Leader hunk，TestP7Boundary 同构；本文件
# 进程无操作纪律：全部 6 法零 subprocess）——

#: P8 src 9 模块（§3.10.2 白名单 #1-#9；dotted 名；占位 ``__init__.py``
#: 字节冻结不入账本，P8-INV-8）。
P8_SRC_SUBMODULES: tuple[str, ...] = (
    "persistence.base",
    "persistence.snapshot",
    "persistence.filesystem",
    "persistence.replay",
    "persistence.checkpoint",
    "persistence.branch",
    "devtools.intervention",
    "devtools.trace_query",
    "devtools.cli",
)

#: P8 测试扫描面（2 目录 14 文件，封闭，含 ``__init__.py`` + conftest；
#: SOT §3.10.3 方法 2）。
P8_TEST_FILES: dict[str, tuple[str, ...]] = {
    "persistence": (
        "__init__.py",
        "conftest.py",
        "test_snapshot_format.py",
        "test_filesystem_backend.py",
        "test_replay.py",
        "test_checkpoint_registry.py",
        "test_branch.py",
        "test_p8_adversarial.py",
    ),
    "devtools": (
        "__init__.py",
        "conftest.py",
        "test_intervention.py",
        "test_trace_query.py",
        "test_cli.py",
        "test_g8_scenarios.py",
    ),
}

#: P8 白名单 25 文件（封闭，§3.10.2 表波次序 #1-25；gate ③/⑥ 字面
#: ``git diff --name-only 84a5d4f..HEAD -- src tests scripts == 25`` 由
#: Leader bash 执行（§3.10.4 步 6），pytest 侧以目录封闭镜像承载（方法
#: 5）；docs/ 依设计不入白名单；2 占位 ``__init__.py`` 不在白名单
#: （P8-INV-8 字节不变）。
P8_WHITELIST: tuple[str, ...] = (
    "src/engine_v2/persistence/base.py",
    "src/engine_v2/persistence/snapshot.py",
    "src/engine_v2/persistence/filesystem.py",
    "src/engine_v2/persistence/replay.py",
    "src/engine_v2/persistence/checkpoint.py",
    "src/engine_v2/persistence/branch.py",
    "src/engine_v2/devtools/intervention.py",
    "src/engine_v2/devtools/trace_query.py",
    "src/engine_v2/devtools/cli.py",
    "scripts/v2_devcontrol.py",
    "tests/engine_v2/persistence/__init__.py",
    "tests/engine_v2/persistence/conftest.py",
    "tests/engine_v2/persistence/test_snapshot_format.py",
    "tests/engine_v2/persistence/test_filesystem_backend.py",
    "tests/engine_v2/persistence/test_replay.py",
    "tests/engine_v2/persistence/test_checkpoint_registry.py",
    "tests/engine_v2/persistence/test_branch.py",
    "tests/engine_v2/persistence/test_p8_adversarial.py",
    "tests/engine_v2/devtools/__init__.py",
    "tests/engine_v2/devtools/conftest.py",
    "tests/engine_v2/devtools/test_intervention.py",
    "tests/engine_v2/devtools/test_trace_query.py",
    "tests/engine_v2/devtools/test_cli.py",
    "tests/engine_v2/devtools/test_g8_scenarios.py",
    "tests/engine_v2/core/test_import_boundary.py",
)

#: P8 导出账本（9 模块 44 名，§8.2 逐字；边界方法 6 集合 + 序双等锚）。
P8_EXPORT_LEDGER: dict[str, tuple[str, ...]] = {
    "persistence.base": (
        "PERSISTENCE_FORMAT_VERSION",
        "PERSISTENCE_SAVE_FILES",
        "SAVE_ID_PATTERN",
        "P8_ERROR_CODES",
        "PersistenceError",
        "PersistenceBackend",
        "SaveBundle",
    ),
    "persistence.snapshot": (
        "PersistenceSnapshot",
        "to_persistence_snapshot",
        "dump_persistence_snapshot",
        "load_persistence_snapshot",
        "check_persistence_versions",
    ),
    "persistence.filesystem": (
        "FilesystemPersistenceBackend",
        "read_trace_records",
    ),
    "persistence.replay": ("ReplayResult", "ReplayError", "replay_committed"),
    "persistence.checkpoint": (
        "CheckpointError",
        "CheckpointSnapshot",
        "BackendCheckpointRegistry",
    ),
    "persistence.branch": (
        "BRANCH_CHECKS",
        "BranchError",
        "WorldInstanceHandle",
        "BranchResult",
        "branch_world",
    ),
    "devtools.intervention": (
        "DEVTOOLS_DEVELOPER_PRODUCER",
        "DEVELOPMENT_COMMAND_KINDS",
        "WORLD_MUTATING_KINDS",
        "RUNTIME_CONTROL_KINDS",
        "INSTANCE_LEVEL_KINDS",
        "DevelopmentCommand",
        "ExternalInterventionEffect",
        "InterventionResult",
        "InterventionError",
        "to_intervention_effects",
        "apply_development_command",
    ),
    "devtools.trace_query": ("TraceQuery", "CausalChain", "TraceQueryError"),
    "devtools.cli": (
        "CLI_TOOL_NAME",
        "DEVCONTROL_CLI_SCHEMA_VERSION",
        "CLI_COMMANDS",
        "build_cli_envelope",
        "run_devcontrol_cli",
    ),
}


def _p8_ast_face() -> list[Path]:
    """P8 src 9 模块 + 薄脚本（10 文件；方法 1 import 面 / 方法 3 字符串
    字面量面 / 方法 4 (b) async 面）。锚文件自身不在扫描面——自豁免
    （P5/P6/P7 同构；探针串拼接构造）。"""
    paths = [
        REPO_ROOT / "src" / "engine_v2" / f"{dotted.replace('.', '/')}.py"
        for dotted in P8_SRC_SUBMODULES
    ]
    paths.append(REPO_ROOT / "scripts" / "v2_devcontrol.py")
    return paths


class TestP8Boundary:
    """P8 边界 6 法（SOT §3.10.3；TestP7Boundary 同构；锚文件 EOF 纯追加）。

    - 方法 1（``test_p8_src_import_whitelist``）：9 src 模块 + 薄脚本
      import 面 ∈ §3.0 闭集（模块根级闭集 + 3 项名级窄例外：pydantic 3
      名 / core.snapshot 仅 snapshot 函数 / dynamics.backend 仅
      BackendMetadata——DEV-W5-5）；黑名单零命中；零相对 import；
    - 方法 2（``test_p8_test_files_closed``）：tests/engine_v2/persistence
      （8 文件）+ tests/engine_v2/devtools（6 文件）目录枚举 == 闭集；
    - 方法 3（``test_p8_k8_string_scan``）：10 文件字符串字面量面 12 名
      casefold 词边界扫描（两侧词边界转义）零命中 + 负探针
      ``llmsim``/``api_key_env`` 不命中（ERR-P7-14 自检防 0x08 控制字节
      腐蚀致转义退化恒绿）；
    - 方法 4（``test_p8_kernel_agnostic_zero_async``）：(a) core/** 全量
      零引用 ``engine_v2.persistence``/``engine_v2.devtools`` 包路径 / 44
      P8 导出名（运行时自 9 模块 ``__all__`` 派生）；(b) P8 src 9 文件零
      ``async def`` / ``await`` + 导入面 6 禁名零命中；
    - 方法 5（``test_p8_whitelist_diff_mirror``）：25 白名单文件全存在 +
      src/tests 4 目录封闭 + 2 占位 ``__init__.py`` 不在白名单（diff 右值
      == 白名单 ⇒ 不在 diff）；
    - 方法 6（``test_p8_export_ledger_dual_equality``）：9 模块 ``__all__``
      == §8.2 账本（集合 + 序双等）+ 每名模块级定义；总 44 名。
    """

    def test_p8_src_import_whitelist(self) -> None:
        """方法 1：AST import 面 10 文件——绝对 import ∈ SOT §3.0 闭集
        白名单（根级闭集 + 名级窄例外）；黑名单零命中；零相对 import
        （同构 P7 L1388）。"""
        allowed_roots = (
            "__future__",
            "argparse",
            "collections",
            "dataclasses",
            "functools",
            "json",
            "os",
            "pathlib",
            "re",
            "sys",
            "typing",
            "pydantic",
            "src.engine_v2.core",
            "src.engine_v2.dynamics",
            "src.engine_v2.persistence",
            "src.engine_v2.devtools",
        )
        forbidden = (
            "asyncio",
            "httpx",
            "requests",
            "socket",
            "urllib",
            "random",
            "datetime",
            "time",
            "uuid",
            "subprocess",
            "threading",
            "src.game",
            "src.config",
            "src.agents",
            "src.llm",
            "src.prompts",
        )
        narrow_exceptions = {
            "pydantic": ("Field", "model_validator", "ValidationError"),
            "src.engine_v2.core.snapshot": ("snapshot",),
            "src.engine_v2.dynamics.backend": ("BackendMetadata",),
        }

        def _check(module_name: str) -> str | None:
            if any(
                module_name == root or module_name.startswith(root + ".")
                for root in forbidden
            ):
                return f"黑名单命中：{module_name}"
            if not any(
                module_name == root or module_name.startswith(root + ".")
                for root in allowed_roots
            ):
                return f"不在闭集白名单：{module_name}"
            return None

        violations: dict[str, list[str]] = {}
        for path in _p8_ast_face():
            rel = str(path.relative_to(REPO_ROOT))
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                modules: list[str] = []
                if isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    if node.level != 0:
                        violations.setdefault(rel, []).append(
                            f"L{node.lineno}: 相对 import（模块面封闭，零相对 import）"
                        )
                        continue
                    modules = [node.module or ""]
                for module_name in modules:
                    problem = _check(module_name)
                    if problem is not None:
                        violations.setdefault(rel, []).append(f"L{node.lineno}: {problem}")
                if isinstance(node, ast.ImportFrom) and node.module in narrow_exceptions:
                    for alias in node.names:
                        if alias.name not in narrow_exceptions[node.module]:
                            violations.setdefault(rel, []).append(
                                f"L{node.lineno}: 名级窄例外越界（{node.module}.{alias.name}）"
                            )
        assert not violations, f"P8 import 面违规（SOT §3.10.3 方法 1）：{violations}"

    def test_p8_test_files_closed(self) -> None:
        """方法 2：测试扫描面 2 目录 14 文件（persistence 8 + devtools 6，
        含 conftest + __init__），与磁盘目录双向相等（SOT §3.10.3 方法 2；
        同构 P7 L1469 / P7_TEST_FILES 模式）。"""
        for dirname, expected in P8_TEST_FILES.items():
            disk = sorted(p.name for p in (TESTS_ENGINE_DIR / dirname).glob("*.py"))
            assert disk == sorted(expected), (
                f"tests/engine_v2/{dirname}/ 目录非封闭"
                f"（P8_TEST_FILES {len(expected)} 文件）：{disk}"
            )

    def test_p8_k8_string_scan(self) -> None:
        """方法 3：字符串字面量面 10 文件（9 src + 脚本）12 名闭集零命中
        （K8；``ast.Constant`` str 域含 docstring；casefold + 词边界）。
        探针串拼接构造自豁免（本文件不在方法 3 扫描面；本追加块自身同以
        拼接构造自豁免——与 P5/P6/P7 完全同构）；拼接集与
        ``P4_LLM_PROVIDER_BLACKLIST``（既有 12 明文常量）断言相等。负例
        锚：``llmsim``/``api_key_env`` 不命中（词边界转义语义钉死；
        ERR-P7-14 自检防 0x08 控制字节腐蚀致转义退化恒绿）。"""
        joined = [
            "open" + "ai",
            "anthr" + "opic",
            "lang" + "chain",
            "lite" + "llm",
            "oll" + "ama",
            "gem" + "ini",
            "g" + "pt",
            "cla" + "ude",
            "l" + "lm",
            "prov" + "ider",
            "api_" + "key",
            "base_" + "url",
        ]
        assert set(joined) == P4_LLM_PROVIDER_BLACKLIST, "拼接集与 12 名常量不等"

        # ERR-P7-14 自检：词边界模式必须命中空格分隔形（W5 R1 0x08 控制字节腐蚀教训；
        # 若转义再退化为控制字节，此处响亮失败而非恒绿）
        for word in joined:
            _pat = re.compile(rf"\b{re.escape(word)}\b")
            assert _pat.search(f" {word} "), f"K8 自检失守: {word!r}"
        hits: dict[str, list[str]] = {}
        for path in _p8_ast_face():
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            matched: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    text = node.value.casefold()
                    matched.update(
                        word
                        for word in joined
                        if re.search(rf"\b{re.escape(word)}\b", text)
                    )
            if matched:
                hits[str(path.relative_to(REPO_ROOT))] = sorted(matched)
        assert not hits, (
            f"P8 文件命中 12 名黑名单字符串字面量域（SOT §3.10.3 方法 3）：{hits}"
        )
        probe = re.compile(r"\b(?:" + "|".join(joined) + r")\b")
        assert not probe.search("llmsim"), "负例锚失守：llmsim 不应命中"
        assert not probe.search("api_key_env"), "负例锚失守：api_key_env 不应命中"

    def test_p8_kernel_agnostic_zero_async(self) -> None:
        """方法 4：(a) core/** 全量（32 子模块 + __init__）零引用
        ``engine_v2.persistence`` / ``engine_v2.devtools`` 包路径 / 43 P8
        导出名（运行时自 9 模块 ``__all__`` 派生 44 名，剔除 ``
        PersistenceBackend``——已知合法面：冻结 core 3 文件 docstring 设计
        概念裸词，P7 方法 4 "core/state.py docstring 裸词" 先例同族；
        DEV-W5-7）；(b) P8 src 9 文件零 ``async def`` / ``await`` + 导入面
        6 禁名（asyncio/socket/random/datetime/time/uuid）零命中（SOT
        §3.10.3 方法 4；同构 P7 L1527）。
        """
        p8_exports = tuple(
            name
            for dotted in P8_SRC_SUBMODULES
            for name in importlib.import_module(f"src.engine_v2.{dotted}").__all__
        )
        assert len(p8_exports) == 44, f"P8 导出账本应为 44 名：{len(p8_exports)}"
        # 已知合法面（DEV-W5-7）：``PersistenceBackend`` 为冻结 core docstring
        # 的设计概念裸词（snapshot.py/state.py/trace.py 各 1–3 处，P8-INV 字节
        # 冻结不可改）——P7 方法 4 "dynamics" 裸词先例同族，从 token 集剔除。
        scan_exports = tuple(name for name in p8_exports if name != "PersistenceBackend")
        tokens = (
            "engine_v2.persistence",
            "engine_v2.devtools",
            *scan_exports,
        )
        core_hits: dict[str, list[str]] = {}
        for path in sorted(CORE_DIR.rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            matched = [token for token in tokens if token in text]
            if matched:
                core_hits[str(path.relative_to(REPO_ROOT))] = matched
        assert not core_hits, (
            f"kernel（core/）引用 P8 类型名/包路径（SOT §3.10.3 方法 4 (a)）："
            f"{core_hits}"
        )
        forbidden_modules = ("asyncio", "socket", "random", "datetime", "time", "uuid")
        async_hits: dict[str, int] = {}
        import_hits: dict[str, list[str]] = {}
        for dotted in P8_SRC_SUBMODULES:
            path = REPO_ROOT / "src" / "engine_v2" / f"{dotted.replace('.', '/')}.py"
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            count = sum(
                1
                for node in ast.walk(tree)
                if isinstance(node, (ast.AsyncFunctionDef, ast.Await))
            )
            if count:
                async_hits[path.name] = count
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                else:
                    continue
                for name in names:
                    if any(
                        name == module_name or name.startswith(module_name + ".")
                        for module_name in forbidden_modules
                    ):
                        import_hits.setdefault(dotted, []).append(
                            f"L{node.lineno}: {name}"
                        )
        assert not async_hits, f"P8 src 零 async def / await（方法 4 (b)）：{async_hits}"
        assert not import_hits, (
            f"P8 src 导入面 6 禁名零命中（方法 4 (b)）：{import_hits}"
        )

    def test_p8_whitelist_diff_mirror(self) -> None:
        """方法 5：白名单 25 文件闭集断言——gate ③/⑥ 的 pytest 内镜像（P6
        方法 1 file_set_closed 口径）：25 文件全存在；2 占位
        ``__init__.py`` 不在白名单（diff 右值 == 白名单 ⇒ 不在 diff；占位
        字节不变由 gate ``git diff --stat`` 零核验）；src persistence/ 封闭
        （6 新建 + 占位 __init__）；src devtools/ 封闭（3 新建 + 占位
        __init__）；tests persistence/ 封闭（8）；tests devtools/ 封闭
        （6）。字面 ``git diff --name-only 84a5d4f..HEAD -- src tests
        scripts == 25`` 由 gate ③/⑥ Leader bash 执行（§3.10.4 步 6）——
        边界文件零 subprocess 纪律下 pytest 侧以目录封闭镜像承载。"""
        for rel in P8_WHITELIST:
            assert (REPO_ROOT / rel).exists(), f"白名单文件缺失：{rel}"
        assert "src/engine_v2/persistence/__init__.py" not in P8_WHITELIST, (
            "占位 persistence/__init__.py 不应在白名单（P8-INV-8）"
        )
        assert "src/engine_v2/devtools/__init__.py" not in P8_WHITELIST, (
            "占位 devtools/__init__.py 不应在白名单（P8-INV-8）"
        )
        persistence_stems = ("base", "snapshot", "filesystem", "replay", "checkpoint", "branch")
        devtools_stems = ("intervention", "trace_query", "cli")
        persistence_src = sorted(
            p.name for p in (REPO_ROOT / "src" / "engine_v2" / "persistence").glob("*.py")
        )
        assert persistence_src == sorted(
            [f"{stem}.py" for stem in persistence_stems] + ["__init__.py"]
        ), f"src persistence/ 文件集非封闭（6 + 占位 __init__）：{persistence_src}"
        devtools_src = sorted(
            p.name for p in (REPO_ROOT / "src" / "engine_v2" / "devtools").glob("*.py")
        )
        assert devtools_src == sorted(
            [f"{stem}.py" for stem in devtools_stems] + ["__init__.py"]
        ), f"src devtools/ 文件集非封闭（3 + 占位 __init__）：{devtools_src}"
        for dirname, expected in P8_TEST_FILES.items():
            disk = sorted(p.name for p in (TESTS_ENGINE_DIR / dirname).glob("*.py"))
            assert disk == sorted(expected), (
                f"tests/engine_v2/{dirname}/ 文件集非封闭（{len(expected)} 文件）："
                f"{disk}"
            )

    def test_p8_export_ledger_dual_equality(self) -> None:
        """方法 6：9 模块 ``__all__`` == §8.2 账本（集合 + 序双等）+ 每名
        模块级定义；总 44 名（SOT §3.10.3 方法 6；同构 P7 L1617）。"""
        total = 0
        for dotted in P8_SRC_SUBMODULES:
            module = importlib.import_module(f"src.engine_v2.{dotted}")
            actual = tuple(module.__all__)
            expected = P8_EXPORT_LEDGER[dotted]
            assert actual == expected, (
                f"{dotted}.py __all__ 与 §8.2 账本不等（集合 + 序双等）：{actual}"
            )
            for name in expected:
                assert hasattr(module, name), (
                    f"{dotted}.py 账本名非模块级定义：{name!r}"
                )
            total += len(actual)
        assert total == 44, f"导出账本总数应为 44：{total}"
import hashlib
import importlib


class TestP9Boundary:
    """P9 W7 边界六方法块（SOT §3.20；锚文件 EOF 纯追加，L1–L2071 字节
    冻结）。

    方法 5/6 嵌入清单 = W7 落盘时自 W7 工作树一次性计算的 sha256
    字面量（81 条 v1 既有路径 == aab029c 逐条一致；15 条 = W6/W7 新
    fixture 路径，无 aab029c 对应；非运行时 git 调用——测试环境无 git
    依赖假设）。词边界
    转义经 ``chr(92) + "b"`` 运行时构造（本追加段零裸 0x5C 0x62，D3 同
    源纪律）；12 名黑名单复用既有 ``P4_LLM_PROVIDER_BLACKLIST``（:225–
    240）。锚文件自身在方法 6(c) 子树哈希中特判 = 前 2071 行 sha256。
    """

    _WB = chr(92) + "b"  # 词边界转义（零裸 0x5C 0x62 纪律）
    _ANCHOR_REL = "tests/engine_v2/core/test_import_boundary.py"
    _ANCHOR_HEAD_LINES = 2071
    _ANCHOR_HEAD_SHA = (
        "26fc0528459e658f126c9b13bbc284344e553b2918eeee85e8b08dbf3dbc9202"
    )
    _PYPROJECT_SHA = (
        "0faaee7b72bf13e5d28c638f941405dcbcc69d33688313ba5d3d1d20bdd3a17a"
    )

    _P9_MODULE_STEMS: tuple[str, ...] = (
        "base", "attributes", "inventory", "relationships", "character",
        "perception", "knowledge", "scenario", "actions", "dialogue",
        "space", "tactical", "dynamics", "narration", "v1_migration",
    )
    _P9_TEST_FILES: tuple[str, ...] = (
        "__init__.py", "conftest.py", "test_attributes.py",
        "test_inventory.py", "test_relationships.py", "test_character.py",
        "test_perception_knowledge.py", "test_scenario_trigger.py",
        "test_action_executors.py", "test_v1_migration.py",
        "test_g9_galgame.py", "test_g9_sandbox.py", "test_g9_tactical.py",
        "test_p9_differential.py", "test_module_face.py",
    )
    _P9_FIXTURE_FILES: dict[str, tuple[str, ...]] = {
        "v2_project_galgame": (
            "game.yaml", "world/galgame_world.yaml", "characters/yuki.yaml",
            "characters/lena.yaml", "items/letter.yaml",
        ),
        "v2_project_sandbox": (
            "game.yaml", "world/sandbox_world.yaml", "characters/wanderer.yaml",
            "characters/merchant.yaml", "rules/sandbox_rules.yaml",
        ),
        "v2_project_tactical": (
            "game.yaml", "world/arena.yaml", "characters/soldier_a.yaml",
            "characters/soldier_b.yaml", "actions/tactical_actions.yaml",
        ),
    }
    # — 方法 5：v1 路径集 sha256 清单（relpath → sha256；96 项）—
    _V1_FROZEN_MANIFEST: dict[str, str] = {
        "config/simulation.yaml":
            "26d164153d3db94187a26169f4012e1f78995aad7ccc8713fbae0b0af31323dd",
        "public_start/murder.yaml":
            "e08172bfff7ccf87c33b775b331087cda301d7dffe27193d30fae3299a92299d",
        "public_start/test_empty.yaml":
            "16e2f4cb870ef4eb269336c0ac8437267ed6996b917cf4293c4804dcd1b82c2b",
        "public_start/whisperheads.yaml":
            "5553c48be5676aea87e5ffc4e88e1480f24a533e863ba92c74c2584ff5ffa58e",
        "pyproject.toml":
            "0faaee7b72bf13e5d28c638f941405dcbcc69d33688313ba5d3d1d20bdd3a17a",
        "src/__init__.py":
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "src/agents/__init__.py":
            "234f4f3863e422eae99295877fe236edec27745375472e5410a2eee7d2510ce8",
        "src/agents/init.py":
            "93339de86b2fab1552fdfefb1c2599ecc49ee884de928345b3a1b06af480012d",
        "src/config/__init__.py":
            "cd2d7d5c67c70d8258c342977630924429909c90671872579fddeb631618e560",
        "src/config/loader.py":
            "2eec3259d393fcaab6d38caa17588775f1c3c4351c34bad721fdf3d991d6a175",
        "src/game/__init__.py":
            "443e5f29945baf9fcfcabed9517ddbf9f73b69bb83677ac92cb4e54c292377d2",
        "src/game/attributes.py":
            "f9297de0b76dd9e134df73742d1063ea791cc3eb375b6d6f9fb48d6e9e1c4921",
        "src/game/condition_eval.py":
            "f647c6d4bf543a6e2c8be8403881b30eaee8681f6359d195494e107854dca6a8",
        "src/game/deterministic_rules.py":
            "b3106181de3122b062dedb8a1e13408ad9707e091972c9d3b488def4b90cd810",
        "src/game/rules.py":
            "aea10d493718ac7bc1e7685495fecc4000fc3d17ab7b595e217648c05eead635",
        "src/game/state_apply.py":
            "cb25bc3ce7c32e85a0eeb3534b804f2fae95c13835a585d4305ccff59761067f",
        "src/game/tick_eval.py":
            "f828ce2125a54ba2d64b8600da78f5aa5e9a7f4b09b3d168ea58b799c8f621b4",
        "src/graph/__init__.py":
            "79d8fd91120ee90d9fc5ba4194ebf1d5732178882603e362dfe5514467e330cd",
        "src/graph/game_graph.py":
            "bff34ee1e156f10979059104c63848f8772d34def9a2d4a2117c26a10f46559a",
        "src/graph/game_state.py":
            "e8d2e7d2c3b4e2f353d997bce7fb46acfa8be9f8e5804b99fbe787be46f3c2bf",
        "src/llm/__init__.py":
            "a4d675113995075c5e3719c7f022b0b5043b6e94f7447c522d73f05873b2f47a",
        "src/llm/parser.py":
            "d8c2b65893ee962db3a7ee0faaf8f3371f4502c7c27c3c6099569bd8e835ad61",
        "src/main.py":
            "2d3df1438240b8cae12c59654faf48e1679fd34102fae02d2d61ed1c9e6508ef",
        "src/models/__init__.py":
            "5c66db8931dee126952cf20af03d1261c02ad94e858f667121904e80d695e254",
        "src/models/character.py":
            "5b887b77cd7380c5803e8f5ef17a2b2e3dd871030453afdc70346fb04bd593ba",
        "src/models/common.py":
            "7b4f9852632360dda1f734dff88308756cc5b4bb526f340d41fc8a983f578e4a",
        "src/models/config.py":
            "e0eb3e6a9d82eaa0ca5d46a9a6635bef9bc02de46b1f4e44e105bc3ec4814f7d",
        "src/models/events.py":
            "93ab5754fbfba1f55398e927d03e0cba66b053dd6f0ab5e1729708e06e59d00e",
        "src/models/player.py":
            "bd8ab98eb5212da1f89012cfe5926952336f19040bf1c5603ecf88771df46279",
        "src/models/world.py":
            "b4bd150086946e4184398873da56aada348ad2d5509454de8a377eb86fc668b5",
        "src/prompts/__init__.py":
            "b43fe8dbd9e888c12c96b537ed5bc486192cd692bb74733007d1cfd14f7c1a1e",
        "src/prompts/loader.py":
            "93e94827d91c94f36c21312e21a8b521e8912aeecc60d928f9374b7c44fd3ad8",
        "src/ui/__init__.py":
            "0d6b46c722e1ece3fa2fe5b81bbfbb1c9c497d07391a2c3153fb1b3656650427",
        "src/ui/cli.py":
            "9df23a8f6cce9b4183083b8e04edb1b036c5131c3143702d6be74ecd7de2041e",
        "src/ui/renderer.py":
            "7546494ecec99abf51bd1738eeab064b3bb96951e05300493c0f302f3757349b",
        "src/ui/status.py":
            "e107f91731b76c0eb2ecf12084d05ec798e38795d5cec7266caae7548519ca8c",
        "src/web/__init__.py":
            "c16c377ecd2c2eea16498f29f826b4ba808768cc8df623929ebfda3a202a52c1",
        "src/web/app.py":
            "9d154e6b091414aaf46ad3e9afd7c2b495f8aab69d44bbe676d0fceebadc63be",
        "src/web/main.py":
            "58e13f75e674f8dbc15ea45aafacf9a5b33778b5a134680693ee1b8638d40824",
        "tests/__init__.py":
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "tests/char_helpers.py":
            "55d8a56086106ba5910c864d16325543148f9becf7dae4e2fb5bb5bfc40e0b2b",
        "tests/fixtures/v2_deployment/deployment.yaml":
            "19eb036a303fe1b84ecb8995d1a9d2ce5ccb9dbba377a920f8d6337656b63c04",
        "tests/fixtures/v2_deployment/deployment_alt.yaml":
            "4701b86a000805720358033efeba62590739be34908742b61ef85decb047ff31",
        "tests/fixtures/v2_deployment_p7/deployment.yaml":
            "24160f5423f5ee6702fd3c9b4396c217682abc1fe437acaaf341ff3c3cf03664",
        "tests/fixtures/v2_plugin_local/game.yaml":
            "ecd9742a2b9ff5428ae969befffc90b14f78c3bdccbabf2e2d17d7686b33c474",
        "tests/fixtures/v2_plugin_local/plugins/infection/plugin.yaml":
            "337cca2ad0ca697d0ba4cf23f25143a47d8d69ebc832180b092fbc1d978e8b52",
        "tests/fixtures/v2_plugin_local/pyproject.toml":
            "ce650fa38638b7c62f46550e391fb318080049b126e12389bda004ba2fc4c6de",
        "tests/fixtures/v2_project_broken/game.yaml":
            "d7fc022d7c385c354329a48ce6bfeee6ecb8141f215b1584bf7a0974329129ad",
        "tests/fixtures/v2_project_broken/world/dup_world.yaml":
            "5747fae96ba621eebbbc857369ac3671c37ef32f16d7290d11a09a9b35c97ad3",
        "tests/fixtures/v2_project_galgame/characters/lena.yaml":
            "f6de04e0158c9014d2658f17d69cc5c066642c1db4de0d8e7b67ed188a893cd3",
        "tests/fixtures/v2_project_galgame/characters/yuki.yaml":
            "1f1566f11898c82759635613573dc3fc5a2fe43619702a869463a5e7180e32c6",
        "tests/fixtures/v2_project_galgame/game.yaml":
            "f2b656b74bbd9e4cfb4df8a180313f8770731fce1661fb30febf14ef3c8d00a1",
        "tests/fixtures/v2_project_galgame/items/letter.yaml":
            "66442cbc232cf109060a054b99ed2219cc6b4d7ed48668bd29027b89e217fcf3",
        "tests/fixtures/v2_project_galgame/world/galgame_world.yaml":
            "1a057771935756a93c33e0c210f9121b382624c27154c7be361f09104017502b",
        "tests/fixtures/v2_project_llm/characters/alice.yaml":
            "33f31c682d58f69a5cdd40368fbf52fd885df27446f00a4e693652d4ccc998c5",
        "tests/fixtures/v2_project_llm/game.yaml":
            "47417cae1709a8419a1b711315aee3f982e638e1d8b7e197254bd29a6bd97c25",
        "tests/fixtures/v2_project_llm/prompts/character_alice.md":
            "5b5a01318a6b52e3b6e2ebd75f95a73b365cc49786008831a849380748294ee5",
        "tests/fixtures/v2_project_llm/prompts/character_alice.yaml":
            "31aa125517094862cc978190d1ff189e87e74636f53afbbb8836bfaae368cbf7",
        "tests/fixtures/v2_project_llm/prompts/game_policy.md":
            "ca6f47383daed39c9fdb01ccdf0d2bb8bde1f340456f59c9a09928b28a1631ff",
        "tests/fixtures/v2_project_llm/prompts/game_policy.yaml":
            "b22fd9871e0f1cfca2986bc0899720122d966c7a4409b9a124bad59a67c55654",
        "tests/fixtures/v2_project_p7/game.yaml":
            "16a25a6573703d3a1b36149bfd657744fae3a26d4368da0c194cf0784fdf9052",
        "tests/fixtures/v2_project_sandbox/characters/merchant.yaml":
            "51db87ab82b1f7a9c756cb9a5b068f816e59b5dc917b17d5813b715049d93c32",
        "tests/fixtures/v2_project_sandbox/characters/wanderer.yaml":
            "922e52745b070455d53cf7dc8fcce15cf5c543a990f6878db9ff5e9ddb87ab09",
        "tests/fixtures/v2_project_sandbox/game.yaml":
            "acad80c627ba7f428bd54062e7c3d2122cddc1a2f45b6a41fb46b44c52abc494",
        "tests/fixtures/v2_project_sandbox/rules/sandbox_rules.yaml":
            "cf53e6dd2fbf23e15b85b1056dd45d03d61153069bad394dd85c3e8c2883e7e9",
        "tests/fixtures/v2_project_sandbox/world/sandbox_world.yaml":
            "5698e4363d512f53b5ef03862edc3b2cebcd3769a7330790410c2a7c02e3aaf9",
        "tests/fixtures/v2_project_tactical/actions/tactical_actions.yaml":
            "5a06102f7ac7f559e739d6336a8570c5cc93a0f52236fd55998b00ad910de4e6",
        "tests/fixtures/v2_project_tactical/characters/soldier_a.yaml":
            "b87646f54820ca4f5bd9b2b310f66b193adfb48f5336cfb3b6f14fc57fc29353",
        "tests/fixtures/v2_project_tactical/characters/soldier_b.yaml":
            "7a5b0f023ec6e583607467cc269f8506983539c4ab52ee0a8010d0d773ad3290",
        "tests/fixtures/v2_project_tactical/game.yaml":
            "74f20ddfd3150b6b4acb6c47b4127d628a3755c1d3eb5b532e4a381fd6f7f215",
        "tests/fixtures/v2_project_tactical/world/arena.yaml":
            "34609cb5cbd564038f2847f11d02adc6a7c44a2e8b14c4e45b8d38982c886dc3",
        "tests/fixtures/v2_project_zero_python/actions/move.yaml":
            "d2bba73b895d695e6b79748e7b0b62347bc03eff03f28d8801b1046ea260cdb7",
        "tests/fixtures/v2_project_zero_python/characters/npc01.yaml":
            "0289d86835dd366509e53601d6e489fc5d4fa2a215c82274c81ed44e4b984938",
        "tests/fixtures/v2_project_zero_python/game.yaml":
            "42d6098b44f23433435b75ab5a83e74ecb010789515c6889e65e8e074465a5f6",
        "tests/fixtures/v2_project_zero_python/rules/basics.yaml":
            "3d944f10d130ee26e430e09c5f4da6104c0f863efc977e75a97d94d8beef16e8",
        "tests/fixtures/v2_project_zero_python/world/main_world.yaml":
            "06451f6a070f4057a787bf46817b2161acb6bc95c4b4c6941b8fc5618a2c2e4b",
        "tests/test_attributes.py":
            "1a6f21f35d75b6ba53d0310dd69fabc2e03a18cccb3c7efdeb58b60edee6608c",
        "tests/test_char_graph.py":
            "ca93962897b4d075c95dc0fca45a721ab315fecbf27c4dc3815984f9506b1e88",
        "tests/test_char_nodes.py":
            "cb765b1948e2bf4fda4eff8581fa931ccdd93a086220fa1e72d1c96d4415e8c6",
        "tests/test_complications.py":
            "d110ba358b3459a223917f7c5a526381da2175fb0c8ca0db6839ce7f92ff9350",
        "tests/test_condition_eval.py":
            "4e748d4a5a0b6fba314b3487a220f823b2ed2f5e83dc1199d3296efc1aa536b3",
        "tests/test_config_loader.py":
            "8e50b9c9f0b93a84a3a4f24a5b814772122abe530e5e0beeecb8a74899c7232c",
        "tests/test_engine_v2_skeleton.py":
            "f68ed96ed8b419d6103fbdfd07923f63d180a7a29fc113dfea9a874c7e97bb05",
        "tests/test_init_and_state.py":
            "9d8fae04150733c06458a92feeb32312e9b4305ca8871ee83393d5d305d83d2f",
        "tests/test_init_extra.py":
            "4e735639f651baa17a5236efbebf5feeff0126e3b9a07f2abe2538d63efe5a1d",
        "tests/test_long_task.py":
            "35aa0352a18926590a08232b563728852882c02aa4e88065e600b4d529ba9a51",
        "tests/test_models.py":
            "9b9e2e0633ef495e63f0e958636e2eb261c525bc2c825516a569e11c63b5e4d1",
        "tests/test_parser.py":
            "2f670a4e12a473722cb72a46c757eb83e80ed94dae5e2ea4759669468f4d4ea9",
        "tests/test_phase4.py":
            "939818981e8e1ababe44a9c54088e20378be4df68873cc40fd1134d1819e820a",
        "tests/test_prompts.py":
            "a6c54113240c99363141bc1eba3be6a945208f051aec994b073ad4bd1b354e8e",
        "tests/test_renderer.py":
            "a2ee2d26263a4a2432fe6c325e8d0c38b34d61f55f8bf3096cbbe75ad3eb4b7b",
        "tests/test_rules.py":
            "a3766857aea7dc651a28219f998e57510ebc3927de6cf4718f6c8e90ca47d0e1",
        "tests/test_state_apply.py":
            "1c4fbc05c5c4c95c58908cea9cb56f31a4916c8efad585e9ee49cecfda1c599f",
        "tests/test_tick_eval.py":
            "d966c7d04aac5c69df8fd152ba6666ea9b0f563ce67bf216b02052a5a3d8a822",
        "tests/test_tick_speed.py":
            "754f0e48ad9b6f7a81e5f8e8b2a733a3ad5e948c4d7b7ea1399d46a429673583",
        "tests/test_webui.py":
            "46df401465c06234d48cf8546f109ac9a99cc026c06e380727f49a8b687c9564",
    }

    _PLACEHOLDER_MANIFEST: dict[str, str] = {
        "src/engine_v2/modules/__init__.py":
            "4f712c2e4291f6cc593ca374bfad9e5c570ab2760afc88fe5bb2b3b864dc70cc",
        "src/engine_v2/presentation/__init__.py":
            "b6b04ab2b2318ca7e74774d7c520b85df7981fb70182d191b365b652c34d1c07",
        "src/engine_v2/context/__init__.py":
            "2fa9bc9febe0edd25649417cf46c237bcac70d769376ced0956980a7c3a5e009",
        "src/engine_v2/adapters/__init__.py":
            "bf15ab529dea18a1160ab7d2c1bd6242f1268e0911e2918652129f4d26389dd5",
        "src/engine_v2/runtime/__init__.py":
            "05347655e4ac45a5d2025291f44fe5f8f7bf78357278134f429023d49897f348",
    }
    _SUBTREE_MANIFEST: dict[str, str] = {
        "src/engine_v2/core":
            "ca3ce91983bf052e4ed92c7106665bdbbdfe8dc9e7e6714197c7397a926e21bc",
        "tests/engine_v2/core":
            "42d513e5e68667c9bc43661b7a9d5230912c6399b74f56b7182852be5cef3aa6",
        "src/engine_v2/content":
            "0577125f0881733f0aa486e2bd28e82dd7845f81dfd36b9380079d059612eb28",
        "tests/engine_v2/content":
            "d5bc24dfbdb6e9a0e65a666acfe37c132ee27a2b5ecbdf00b4a9ed4fa5e349d8",
        "src/engine_v2/llm":
            "c21ea42db68d735576784432ea5099cd29c77b65319194881c65d07d1a7ea3d0",
        "tests/engine_v2/llm":
            "2bfe397e913168c24d9ee56fd23d30e2713dde6398628400f12fb00f97768a4c",
        "src/engine_v2/prompts":
            "9d6c6bc252ec92369efd419395eb530f20f2b4ec942fe9bca7806561a31a9f30",
        "tests/engine_v2/prompts":
            "6f9ddabd276ccbf73a6caeefb0f5f88c38a3fb5b5ec323eb098855061c99dbbb",
        "src/engine_v2/dynamics":
            "80599cfddcaa6dfc731076e217bf5bd142c0f2bc5ac36f4f9deb683a301cb1ea",
        "tests/engine_v2/dynamics":
            "3f21a18872e0b4d38b6dbae2e3dec3e5b2f535c6deb93d1ceca5d2c45be4a3a5",
        "src/engine_v2/persistence":
            "1b66b895f9187953c5a3fea9cd034db39d672d195208c9ece9a4912a1773a5e8",
        "tests/engine_v2/persistence":
            "82912faf6f1887ab033ea1d4d4e70d375f09c93ba7be3b808c9dbd7f3198a32b",
        "src/engine_v2/plugins":
            "c3af0eaa340c9f175ec95b8a45961d26fcc77319366fb989f9b25505e926855a",
        "tests/engine_v2/plugins":
            "8ec6694a2f0951c265091e9a6bbf745464c4973828811a6c1862da8a5d996705",
    }
    _FIXTURE_MANIFEST: dict[str, str] = {
        "v2_deployment":
            "58d9b531ccd0b9dbaedbb38833c476d9d9f5d10ce3d4651d01fc780c5e681fd0",
        "v2_deployment_p7":
            "d12ccec56d86799d9e44c4f759804d4a979297b4f5ccaae9a51032f07e0a0b17",
        "v2_plugin_local":
            "d430e84101e436521f92b0c5c441c24ebcf426fe23cf458a13f1f4aa37d87fd5",
        "v2_project_broken":
            "69b5c28705e3149355bc26923207daa78d94491fbffb03277c3157f0e6e1e6d1",
        "v2_project_llm":
            "fc7eef49ba6e5a429678de374dfc513fc0ab777874c2601b65c55b51e514923c",
        "v2_project_p7":
            "dfc6bfe31f0387c536183d5c433e0d2b7f9957c481a120f230f0b71c6430e1b1",
        "v2_project_zero_python":
            "439e166e01c4bf879c323a7f448d49483321f22a4b9271beeef90a3e038e341d",
    }

    @staticmethod
    def _sha(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    @classmethod
    def _walk_files(cls, root: Path) -> list[Path]:
        out = []
        for p in sorted(root.rglob("*")):
            if p.is_file() and p.suffix != ".pyc" and "__pycache__" not in p.parts:
                out.append(p)
        return out

    @classmethod
    def _anchor_head_sha(cls) -> str:
        path = REPO_ROOT / cls._ANCHOR_REL
        head = path.read_bytes().splitlines(keepends=True)[: cls._ANCHOR_HEAD_LINES]
        return hashlib.sha256(b"".join(head)).hexdigest()

    @classmethod
    def _subtree_digest(cls, sub: str) -> str:
        base = REPO_ROOT / sub
        lines = []
        for p in cls._walk_files(base):
            r = p.relative_to(REPO_ROOT).as_posix()
            if r == cls._ANCHOR_REL:
                head = p.read_bytes().splitlines(keepends=True)[: cls._ANCHOR_HEAD_LINES]
                h = hashlib.sha256(b"".join(head)).hexdigest()
            else:
                h = cls._sha(p)
            lines.append(f"{r} {h}")
        lines.sort()
        return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()

    @classmethod
    def _v1_manifest(cls) -> dict[str, str]:
        out: dict[str, str] = {}

        def add(p: Path) -> None:
            out[p.relative_to(REPO_ROOT).as_posix()] = cls._sha(p)

        for p in cls._walk_files(REPO_ROOT / "src"):
            if "engine_v2" not in p.parts:
                add(p)
        for p in cls._walk_files(REPO_ROOT / "public_start"):
            add(p)
        for p in cls._walk_files(REPO_ROOT / "config"):
            add(p)
        for p in cls._walk_files(REPO_ROOT / "tests"):
            if "engine_v2" not in p.parts:
                add(p)
        add(REPO_ROOT / "pyproject.toml")
        return out

    @classmethod
    def _import_modules(cls, path: Path) -> list[str]:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        mods: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                mods.append(node.module)
            elif isinstance(node, ast.Import):
                mods.extend(alias.name for alias in node.names)
        return mods

    def test_p9_src_tree_closed(self) -> None:
        """方法 1：src/engine_v2/modules/ 文件集 == 白名单行 1–15 + 占位
        __init__.py（16 项）；scripts/v2_migrate_v1.py 存在。"""
        mod_dir = REPO_ROOT / "src" / "engine_v2" / "modules"
        actual = {p.name for p in mod_dir.iterdir() if p.is_file()}
        expected = {"__init__.py"} | {s + ".py" for s in self._P9_MODULE_STEMS}
        assert actual == expected, (
            f"src modules/ 文件集越白（应 16 项）：差集 {actual ^ expected}"
        )
        assert len(actual) == 16
        assert (REPO_ROOT / "scripts" / "v2_migrate_v1.py").is_file(), (
            "scripts/v2_migrate_v1.py 缺失（白名单行 46）"
        )

    def test_p9_test_tree_closed(self) -> None:
        """方法 2：tests/engine_v2/modules/ 文件集 == 白名单行 16–30（15
        项）；tests/fixtures/v2_project_{galgame,sandbox,tactical}/ 文件集
        == 行 31–45（各 5 项）。"""
        test_dir = REPO_ROOT / "tests" / "engine_v2" / "modules"
        actual = {p.name for p in test_dir.iterdir() if p.is_file()}
        expected = set(self._P9_TEST_FILES)
        assert actual == expected, (
            f"tests modules/ 文件集越白（应 15 项）：差集 {actual ^ expected}"
        )
        assert len(actual) == 15
        for dirname, files in self._P9_FIXTURE_FILES.items():
            base = REPO_ROOT / "tests" / "fixtures" / dirname
            disk = {
                p.relative_to(base).as_posix()
                for p in base.rglob("*")
                if p.is_file()
            }
            assert disk == set(files), (
                f"fixture {dirname}/ 文件集越白（应 5 项）：差集 {disk ^ set(files)}"
            )
            assert len(disk) == 5

    def test_p9_string_literal_k8(self) -> None:
        """方法 3：AST 遍历 P9 src 15 文件全部字符串字面量（含 docstring）
        × 12 名黑名单（复用 P4_LLM_PROVIDER_BLACKLIST）零命中（casefold +
        词边界）；探针拼接构造自豁免 + 负例锚。"""
        assert len(P4_LLM_PROVIDER_BLACKLIST) == 12
        joined = sorted(P4_LLM_PROVIDER_BLACKLIST)
        probe = re.compile(
            self._WB + "(?:" + "|".join(re.escape(w) for w in joined) + ")" + self._WB
        )
        assert not probe.search("llmsim"), "负例锚失守：llmsim 不应命中"
        assert not probe.search("api_key_env"), "负例锚失守：api_key_env 不应命中"
        hits: dict[str, list[str]] = {}
        for stem in self._P9_MODULE_STEMS:
            path = REPO_ROOT / "src" / "engine_v2" / "modules" / f"{stem}.py"
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            matched: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    text = node.value.casefold()
                    matched.update(
                        w for w in joined
                        if re.search(self._WB + re.escape(w) + self._WB, text)
                    )
            if matched:
                hits[stem] = sorted(matched)
        assert not hits, (
            f"P9 src 命中 12 名黑名单字符串字面量域（SOT §3.20 方法 3）：{hits}"
        )

    def test_p9_import_closure(self) -> None:
        """方法 4：(a) P9 src 15 文件 import 根闭集 = stdlib + 既有第三方
        （pydantic / PyYAML，均 pyproject.toml 预声明，零新依赖 P9-INV-10）
        + engine_v2.{core,content,llm,prompts,dynamics,modules}（§3.0）；
        v1 包根（src.game 等）与 langgraph / langchain 禁止。(b)
        engine_v2 全树（P1–P8 冻结面 + P9 面）import 零 langgraph /
        langchain（G9 条款②，G9-16）。

        注（DEV-W7-5）：§3.0 闭集块字面仅列 "stdlib + pydantic +
        engine_v2.*" 且禁 "任何其它路径"，但 v1_migration.py（白名单行
        15）必需 import PyYAML（``yaml``）；PyYAML 为既有项目依赖
        （pyproject.toml:11 预声明），且已被冻结 v1（src/config/loader.py、
        src/agents/init.py）与冻结 P1–P8 面（content/loader.py、
        content/project_ir.py、llm/deployment.py）import。故边界测试将
        ``yaml`` 列为既有第三方根（非新依赖）——§3.0 闭集块 errata。
        """
        allowed_subs = {"core", "content", "llm", "prompts", "dynamics", "modules"}
        existing_third_party = {"pydantic", "yaml"}
        closure_hits: dict[str, list[str]] = {}
        for stem in self._P9_MODULE_STEMS:
            path = REPO_ROOT / "src" / "engine_v2" / "modules" / f"{stem}.py"
            bad: list[str] = []
            for mod in self._import_modules(path):
                top = mod.split(".")[0]
                if mod.startswith("src.engine_v2."):
                    sub = mod.split(".", 3)[2]
                    if sub not in allowed_subs:
                        bad.append(mod)
                elif mod == "src" or mod.startswith("src."):
                    bad.append(mod)  # v1 树（src.game / src.config / ...）
                elif top in existing_third_party or top in sys.stdlib_module_names:
                    continue
                else:
                    bad.append(mod)
            if bad:
                closure_hits[stem] = sorted(set(bad))
        assert not closure_hits, (
            f"P9 src import 根越界（§3.0 闭集 + DEV-W7-5）：{closure_hits}"
        )
        # (a2) per-module requires 级（SOT §3.0「modules.<name> 仅
        # <name> ∈ 本模块 MODULE_REQUIRES」；R1 S-3 补充钉）：13 官方
        # 模块的 modules.* import 面 ⊆ {base} ∪ IDENTITY.requires 对应
        # stem 集（base = 13 模块公共面，∉ 任何 requires——§3.0 字面
        # 自相矛盾，errata 候补）；base / v1_migration = 包基础设施
        # （无 IDENTITY，A18 13 闭集之外），不在 requires 图内。
        requires_violations: dict[str, list[str]] = {}
        for stem in self._P9_MODULE_STEMS:
            if stem in ("base", "v1_migration"):
                continue
            path = REPO_ROOT / "src" / "engine_v2" / "modules" / f"{stem}.py"
            module = importlib.import_module(f"src.engine_v2.modules.{stem}")
            allowed = {
                "base"
            } | {
                mid.removeprefix("llmsim-standard-")
                for mid in module.IDENTITY.requires
            }
            imported = set()
            for mod in self._import_modules(path):
                if mod.startswith("src.engine_v2.modules."):
                    imported.add(mod.split(".")[-1])
            bad = sorted(imported - allowed)
            if bad:
                requires_violations[stem] = bad
        assert not requires_violations, (
            "P9 src 模块越权 import（modules.<name> ∉ 本模块 requires）"
            f"（§3.0 per-module 闭集 + R1 S-3）：{requires_violations}"
        )
        banned = {"langgraph", "langchain"}
        lg_hits: dict[str, list[str]] = {}
        for path in self._walk_files(REPO_ROOT / "src" / "engine_v2"):
            if path.suffix != ".py":
                continue
            bad = [
                m for m in self._import_modules(path)
                if m.split(".")[0] in banned
            ]
            if bad:
                lg_hits[path.relative_to(REPO_ROOT).as_posix()] = sorted(set(bad))
        assert not lg_hits, (
            f"engine_v2 全树 import 命中 langgraph / langchain（G9-16）：{lg_hits}"
        )

    def test_v1_frozen_hashes(self) -> None:
        """方法 5：v1 路径集（§0.3 定义）sha256 == 嵌入清单（W7 落盘时
        自 W7 工作树计算：81 条 v1 既有路径 == aab029c 逐条一致 +
        15 条 W6/W7 新 fixture 路径；dict 双等，P9-INV-1）。"""
        recomputed = self._v1_manifest()
        assert recomputed == self._V1_FROZEN_MANIFEST, (
            "v1 冻结面 sha256 漂移（P9-INV-1）："
            f"差集 {set(recomputed.items()) ^ set(self._V1_FROZEN_MANIFEST.items())}"
        )

    def test_p9_frozen_surfaces_untouched(self) -> None:
        """方法 6：(a) pyproject.toml sha256 不变（P9-INV-10）；(b) 占位
        五件套 sha256 不变（§2.9）；(c) engine_v2 14 子树哈希不变（锚文件
        特判前 2071 行）；(d) 既有 7 fixture 项目目录哈希不变。"""
        assert self._sha(REPO_ROOT / "pyproject.toml") == self._PYPROJECT_SHA, (
            "pyproject.toml sha256 漂移（P9-INV-10）"
        )
        for rel_path, expected in self._PLACEHOLDER_MANIFEST.items():
            assert self._sha(REPO_ROOT / rel_path) == expected, (
                f"占位 {rel_path} sha256 漂移（§2.9）"
            )
        assert self._anchor_head_sha() == self._ANCHOR_HEAD_SHA, (
            "锚文件前 2071 行 sha256 漂移（纯追加纪律破坏）"
        )
        for sub, expected in self._SUBTREE_MANIFEST.items():
            assert self._subtree_digest(sub) == expected, (
                f"engine_v2 子树 {sub} 哈希漂移（P9-INV-2）"
            )
        for dirname, expected in self._FIXTURE_MANIFEST.items():
            assert self._subtree_digest(f"tests/fixtures/{dirname}") == expected, (
                f"既有 fixture 目录 {dirname} 哈希漂移（P9-INV-2）"
            )


# ── P10 块（行 36 M 模式：L1–2625 逐字节不变；ERR-P10-09/10）──────────
# ERR-P10-09：skeleton test 计数面扩展（白名单行 37 M；W2 +2 子包条目）
# → v1 冻结哈希清单刷新（P9 块 L2127–2625 字面量零修改；最后赋值生效；
# W3/W4 各续一行同形语句）。
TestP9Boundary._V1_FROZEN_MANIFEST["tests/test_engine_v2_skeleton.py"] = (
    "9c6a6f820336c8f71e97c4fb4bcb42194afbcb89ad3a7980624a08fa5e8ed580"
)
# W3 续（ERR-P10-09）：skeleton +1 "presentation.tactical" + 计数文案 15→16
# → v1 冻结哈希清单刷新（P9 块字面量零修改；最后赋值生效；W4 续同形语句）。
TestP9Boundary._V1_FROZEN_MANIFEST["tests/test_engine_v2_skeleton.py"] = (
    "59c0a8c0be6020ed7d60889fa7456a5f1454bb3a9d22e43423a93e0770065fa7"
)
# W4 续（ERR-P10-09）：skeleton +1 "adapters.web" + 计数文案 16→17
# → v1 冻结哈希清单刷新（P9 块字面量零修改；最后赋值生效）。
TestP9Boundary._V1_FROZEN_MANIFEST["tests/test_engine_v2_skeleton.py"] = (
    "f6017411b1a8d9f0997504ad76ad0029c57758f491c5c4b193f9839b4e772569"
)

# ── P10 W5 续（行 36 M 模式：TestP10Boundary 6 方法 EOF 纯追加；P10 块
#    续段——L1–2625 + W2–W4 P10 块逐字节不变）────────────
# m5/m6 嵌入清单 = sha256 字面量（W5 实现者自 G9 收口 commit 9945565
# 一次性计算：``git show 9945565:<path> | sha256sum`` 构建期计算；测试
# 运行时零 git/subprocess 调用；P9 §3.20 同先例）。m5 skeleton test =
# v1 路径集成员，其值 = P10 块逐波刷新语句后值（ERR-P10-09，最后赋值
# 生效）——m5 面自 P9 清单取刷新后值（双钉）；m6 锚文件特判 = 前 2625
# 行 sha256（G9 收口点行；P10 纯追加段剔除）。词边界转义经
# ``chr(92) + "b"`` 运行时构造（本追加段零裸 0x5C 0x62，D3 同源纪律）。


class TestP10Boundary:
    """P10 W5 边界六方法块（SOT §7；锚文件 EOF 纯追加，L1–2625 字节
    冻结）。

    - 方法 1：P10 src 树闭集（白名单行 1–19；19 项；占位二件套属
      冻结面，方法 6 哈希钉，不计）；
    - 方法 2：P10 test 树闭集（白名单行 20–35；presentation 7 +
      adapters 9）；
    - 方法 3：19 src 文件字符串字面量（含 docstring）× 12 名零命中，
      唯一允许命中 = narrator.py TEXT_SOURCES 钉元组（ERR-P10-10；
      复用既有 ``P4_LLM_PROVIDER_BLACKLIST`` :225–240）；
    - 方法 4：19 src 文件 import 根闭集 ⊆ §3.0（含 http.server
      server.py 仅 / jinja2 零 / 图像库零 / v1 src.* 零 /
      random-time-datetime-timeit 零（ERR-P10-07）/ text/ ↔ image/
      零互 import / inspector-workbench 零 core.entity-core.
      components 直读（INV-5 特例钉）/ engine_v2 全树
      langgraph-langchain 零）；
    - 方法 5：v1 路径集（P9-INV-1 口径）sha256 == 嵌入清单（G9
      收口 9945565 面；skeleton = P10 块刷新后值——ERR-P10-09
      双钉）；
    - 方法 6：(a) pyproject.toml sha；(b) 占位二件套 sha（§2.6）；
      (c) 17 冻结子树哈希（src 9 + tests 8；锚文件特判 = 前 2625
      行 sha256，G9 收口点行）+ 前 2071 行 sha（P9 既有常量复用，
      零重复定义）；(d) 既有 7 + P9 3 样例目录哈希。
    """

    _WB = chr(92) + "b"  # 词边界转义（零裸 0x5C 0x62 纪律）
    _ANCHOR_P10_HEAD_LINES = 2625
    _ANCHOR_P10_HEAD_SHA = (
        "76e8cfc95f5cca49681544c984930e4729cc9b8187dcc82b06603982e047e741"
    )
    _PYPROJECT_SHA = (
        "0faaee7b72bf13e5d28c638f941405dcbcc69d33688313ba5d3d1d20bdd3a17a"
    )
    _PLACEHOLDER_MANIFEST: dict[str, str] = {
        "src/engine_v2/presentation/__init__.py":
            "b6b04ab2b2318ca7e74774d7c520b85df7981fb70182d191b365b652c34d1c07",
        "src/engine_v2/adapters/__init__.py":
            "bf15ab529dea18a1160ab7d2c1bd6242f1268e0911e2918652129f4d26389dd5",
    }
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
    _P10_TEST_PRESENTATION: tuple[str, ...] = (
        "tests/engine_v2/presentation/__init__.py",
        "tests/engine_v2/presentation/conftest.py",
        "tests/engine_v2/presentation/test_view.py",
        "tests/engine_v2/presentation/test_narrator.py",
        "tests/engine_v2/presentation/test_render_intent.py",
        "tests/engine_v2/presentation/test_image_backend.py",
        "tests/engine_v2/presentation/test_tactical_layout.py",
    )
    _P10_TEST_ADAPTERS: tuple[str, ...] = (
        "tests/engine_v2/adapters/__init__.py",
        "tests/engine_v2/adapters/web/__init__.py",
        "tests/engine_v2/adapters/web/conftest.py",
        "tests/engine_v2/adapters/web/test_session_manager.py",
        "tests/engine_v2/adapters/web/test_web_api.py",
        "tests/engine_v2/adapters/web/test_inspector.py",
        "tests/engine_v2/adapters/web/test_workbench.py",
        "tests/engine_v2/adapters/web/test_g10_gate.py",
        "tests/engine_v2/adapters/web/test_p10_face.py",
    )
    _K8_ALLOWED_HIT = (
        "src/engine_v2/presentation/text/narrator.py",
        "llm",
        "llm",
    )
    _SKELETON_REL = "tests/test_engine_v2_skeleton.py"
    _P10_NONDETERMINISM_ROOTS: frozenset[str] = frozenset(
        {"random", "time", "datetime", "timeit"}
    )
    _P10_PYDANTIC_ALLOWED: tuple[str, ...] = (
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
    # — 方法 5：v1 路径集 sha256 清单（relpath → sha256；96 项；
    #   全部 = G9 收口 9945565 面；skeleton 项测试时自 P9 刷新清单
    #   取后值，ERR-P10-09 双钉）—
    _V1_P10_MANIFEST: dict[str, str] = {
        "config/simulation.yaml":
            "26d164153d3db94187a26169f4012e1f78995aad7ccc8713fbae0b0af31323dd",
        "public_start/murder.yaml":
            "e08172bfff7ccf87c33b775b331087cda301d7dffe27193d30fae3299a92299d",
        "public_start/test_empty.yaml":
            "16e2f4cb870ef4eb269336c0ac8437267ed6996b917cf4293c4804dcd1b82c2b",
        "public_start/whisperheads.yaml":
            "5553c48be5676aea87e5ffc4e88e1480f24a533e863ba92c74c2584ff5ffa58e",
        "pyproject.toml":
            "0faaee7b72bf13e5d28c638f941405dcbcc69d33688313ba5d3d1d20bdd3a17a",
        "src/__init__.py":
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "src/agents/__init__.py":
            "234f4f3863e422eae99295877fe236edec27745375472e5410a2eee7d2510ce8",
        "src/agents/init.py":
            "93339de86b2fab1552fdfefb1c2599ecc49ee884de928345b3a1b06af480012d",
        "src/config/__init__.py":
            "cd2d7d5c67c70d8258c342977630924429909c90671872579fddeb631618e560",
        "src/config/loader.py":
            "2eec3259d393fcaab6d38caa17588775f1c3c4351c34bad721fdf3d991d6a175",
        "src/game/__init__.py":
            "443e5f29945baf9fcfcabed9517ddbf9f73b69bb83677ac92cb4e54c292377d2",
        "src/game/attributes.py":
            "f9297de0b76dd9e134df73742d1063ea791cc3eb375b6d6f9fb48d6e9e1c4921",
        "src/game/condition_eval.py":
            "f647c6d4bf543a6e2c8be8403881b30eaee8681f6359d195494e107854dca6a8",
        "src/game/deterministic_rules.py":
            "b3106181de3122b062dedb8a1e13408ad9707e091972c9d3b488def4b90cd810",
        "src/game/rules.py":
            "aea10d493718ac7bc1e7685495fecc4000fc3d17ab7b595e217648c05eead635",
        "src/game/state_apply.py":
            "cb25bc3ce7c32e85a0eeb3534b804f2fae95c13835a585d4305ccff59761067f",
        "src/game/tick_eval.py":
            "f828ce2125a54ba2d64b8600da78f5aa5e9a7f4b09b3d168ea58b799c8f621b4",
        "src/graph/__init__.py":
            "79d8fd91120ee90d9fc5ba4194ebf1d5732178882603e362dfe5514467e330cd",
        "src/graph/game_graph.py":
            "bff34ee1e156f10979059104c63848f8772d34def9a2d4a2117c26a10f46559a",
        "src/graph/game_state.py":
            "e8d2e7d2c3b4e2f353d997bce7fb46acfa8be9f8e5804b99fbe787be46f3c2bf",
        "src/llm/__init__.py":
            "a4d675113995075c5e3719c7f022b0b5043b6e94f7447c522d73f05873b2f47a",
        "src/llm/parser.py":
            "d8c2b65893ee962db3a7ee0faaf8f3371f4502c7c27c3c6099569bd8e835ad61",
        "src/main.py":
            "2d3df1438240b8cae12c59654faf48e1679fd34102fae02d2d61ed1c9e6508ef",
        "src/models/__init__.py":
            "5c66db8931dee126952cf20af03d1261c02ad94e858f667121904e80d695e254",
        "src/models/character.py":
            "5b887b77cd7380c5803e8f5ef17a2b2e3dd871030453afdc70346fb04bd593ba",
        "src/models/common.py":
            "7b4f9852632360dda1f734dff88308756cc5b4bb526f340d41fc8a983f578e4a",
        "src/models/config.py":
            "e0eb3e6a9d82eaa0ca5d46a9a6635bef9bc02de46b1f4e44e105bc3ec4814f7d",
        "src/models/events.py":
            "93ab5754fbfba1f55398e927d03e0cba66b053dd6f0ab5e1729708e06e59d00e",
        "src/models/player.py":
            "bd8ab98eb5212da1f89012cfe5926952336f19040bf1c5603ecf88771df46279",
        "src/models/world.py":
            "b4bd150086946e4184398873da56aada348ad2d5509454de8a377eb86fc668b5",
        "src/prompts/__init__.py":
            "b43fe8dbd9e888c12c96b537ed5bc486192cd692bb74733007d1cfd14f7c1a1e",
        "src/prompts/loader.py":
            "93e94827d91c94f36c21312e21a8b521e8912aeecc60d928f9374b7c44fd3ad8",
        "src/ui/__init__.py":
            "0d6b46c722e1ece3fa2fe5b81bbfbb1c9c497d07391a2c3153fb1b3656650427",
        "src/ui/cli.py":
            "9df23a8f6cce9b4183083b8e04edb1b036c5131c3143702d6be74ecd7de2041e",
        "src/ui/renderer.py":
            "7546494ecec99abf51bd1738eeab064b3bb96951e05300493c0f302f3757349b",
        "src/ui/status.py":
            "e107f91731b76c0eb2ecf12084d05ec798e38795d5cec7266caae7548519ca8c",
        "src/web/__init__.py":
            "c16c377ecd2c2eea16498f29f826b4ba808768cc8df623929ebfda3a202a52c1",
        "src/web/app.py":
            "9d154e6b091414aaf46ad3e9afd7c2b495f8aab69d44bbe676d0fceebadc63be",
        "src/web/main.py":
            "58e13f75e674f8dbc15ea45aafacf9a5b33778b5a134680693ee1b8638d40824",
        "tests/__init__.py":
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "tests/char_helpers.py":
            "55d8a56086106ba5910c864d16325543148f9becf7dae4e2fb5bb5bfc40e0b2b",
        "tests/fixtures/v2_deployment/deployment.yaml":
            "19eb036a303fe1b84ecb8995d1a9d2ce5ccb9dbba377a920f8d6337656b63c04",
        "tests/fixtures/v2_deployment/deployment_alt.yaml":
            "4701b86a000805720358033efeba62590739be34908742b61ef85decb047ff31",
        "tests/fixtures/v2_deployment_p7/deployment.yaml":
            "24160f5423f5ee6702fd3c9b4396c217682abc1fe437acaaf341ff3c3cf03664",
        "tests/fixtures/v2_plugin_local/game.yaml":
            "ecd9742a2b9ff5428ae969befffc90b14f78c3bdccbabf2e2d17d7686b33c474",
        "tests/fixtures/v2_plugin_local/plugins/infection/plugin.yaml":
            "337cca2ad0ca697d0ba4cf23f25143a47d8d69ebc832180b092fbc1d978e8b52",
        "tests/fixtures/v2_plugin_local/pyproject.toml":
            "ce650fa38638b7c62f46550e391fb318080049b126e12389bda004ba2fc4c6de",
        "tests/fixtures/v2_project_broken/game.yaml":
            "d7fc022d7c385c354329a48ce6bfeee6ecb8141f215b1584bf7a0974329129ad",
        "tests/fixtures/v2_project_broken/world/dup_world.yaml":
            "5747fae96ba621eebbbc857369ac3671c37ef32f16d7290d11a09a9b35c97ad3",
        "tests/fixtures/v2_project_galgame/characters/lena.yaml":
            "f6de04e0158c9014d2658f17d69cc5c066642c1db4de0d8e7b67ed188a893cd3",
        "tests/fixtures/v2_project_galgame/characters/yuki.yaml":
            "1f1566f11898c82759635613573dc3fc5a2fe43619702a869463a5e7180e32c6",
        "tests/fixtures/v2_project_galgame/game.yaml":
            "f2b656b74bbd9e4cfb4df8a180313f8770731fce1661fb30febf14ef3c8d00a1",
        "tests/fixtures/v2_project_galgame/items/letter.yaml":
            "66442cbc232cf109060a054b99ed2219cc6b4d7ed48668bd29027b89e217fcf3",
        "tests/fixtures/v2_project_galgame/world/galgame_world.yaml":
            "1a057771935756a93c33e0c210f9121b382624c27154c7be361f09104017502b",
        "tests/fixtures/v2_project_llm/characters/alice.yaml":
            "33f31c682d58f69a5cdd40368fbf52fd885df27446f00a4e693652d4ccc998c5",
        "tests/fixtures/v2_project_llm/game.yaml":
            "47417cae1709a8419a1b711315aee3f982e638e1d8b7e197254bd29a6bd97c25",
        "tests/fixtures/v2_project_llm/prompts/character_alice.md":
            "5b5a01318a6b52e3b6e2ebd75f95a73b365cc49786008831a849380748294ee5",
        "tests/fixtures/v2_project_llm/prompts/character_alice.yaml":
            "31aa125517094862cc978190d1ff189e87e74636f53afbbb8836bfaae368cbf7",
        "tests/fixtures/v2_project_llm/prompts/game_policy.md":
            "ca6f47383daed39c9fdb01ccdf0d2bb8bde1f340456f59c9a09928b28a1631ff",
        "tests/fixtures/v2_project_llm/prompts/game_policy.yaml":
            "b22fd9871e0f1cfca2986bc0899720122d966c7a4409b9a124bad59a67c55654",
        "tests/fixtures/v2_project_p7/game.yaml":
            "16a25a6573703d3a1b36149bfd657744fae3a26d4368da0c194cf0784fdf9052",
        "tests/fixtures/v2_project_sandbox/characters/merchant.yaml":
            "51db87ab82b1f7a9c756cb9a5b068f816e59b5dc917b17d5813b715049d93c32",
        "tests/fixtures/v2_project_sandbox/characters/wanderer.yaml":
            "922e52745b070455d53cf7dc8fcce15cf5c543a990f6878db9ff5e9ddb87ab09",
        "tests/fixtures/v2_project_sandbox/game.yaml":
            "acad80c627ba7f428bd54062e7c3d2122cddc1a2f45b6a41fb46b44c52abc494",
        "tests/fixtures/v2_project_sandbox/rules/sandbox_rules.yaml":
            "cf53e6dd2fbf23e15b85b1056dd45d03d61153069bad394dd85c3e8c2883e7e9",
        "tests/fixtures/v2_project_sandbox/world/sandbox_world.yaml":
            "5698e4363d512f53b5ef03862edc3b2cebcd3769a7330790410c2a7c02e3aaf9",
        "tests/fixtures/v2_project_tactical/actions/tactical_actions.yaml":
            "5a06102f7ac7f559e739d6336a8570c5cc93a0f52236fd55998b00ad910de4e6",
        "tests/fixtures/v2_project_tactical/characters/soldier_a.yaml":
            "b87646f54820ca4f5bd9b2b310f66b193adfb48f5336cfb3b6f14fc57fc29353",
        "tests/fixtures/v2_project_tactical/characters/soldier_b.yaml":
            "7a5b0f023ec6e583607467cc269f8506983539c4ab52ee0a8010d0d773ad3290",
        "tests/fixtures/v2_project_tactical/game.yaml":
            "74f20ddfd3150b6b4acb6c47b4127d628a3755c1d3eb5b532e4a381fd6f7f215",
        "tests/fixtures/v2_project_tactical/world/arena.yaml":
            "34609cb5cbd564038f2847f11d02adc6a7c44a2e8b14c4e45b8d38982c886dc3",
        "tests/fixtures/v2_project_zero_python/actions/move.yaml":
            "d2bba73b895d695e6b79748e7b0b62347bc03eff03f28d8801b1046ea260cdb7",
        "tests/fixtures/v2_project_zero_python/characters/npc01.yaml":
            "0289d86835dd366509e53601d6e489fc5d4fa2a215c82274c81ed44e4b984938",
        "tests/fixtures/v2_project_zero_python/game.yaml":
            "42d6098b44f23433435b75ab5a83e74ecb010789515c6889e65e8e074465a5f6",
        "tests/fixtures/v2_project_zero_python/rules/basics.yaml":
            "3d944f10d130ee26e430e09c5f4da6104c0f863efc977e75a97d94d8beef16e8",
        "tests/fixtures/v2_project_zero_python/world/main_world.yaml":
            "06451f6a070f4057a787bf46817b2161acb6bc95c4b4c6941b8fc5618a2c2e4b",
        "tests/test_attributes.py":
            "1a6f21f35d75b6ba53d0310dd69fabc2e03a18cccb3c7efdeb58b60edee6608c",
        "tests/test_char_graph.py":
            "ca93962897b4d075c95dc0fca45a721ab315fecbf27c4dc3815984f9506b1e88",
        "tests/test_char_nodes.py":
            "cb765b1948e2bf4fda4eff8581fa931ccdd93a086220fa1e72d1c96d4415e8c6",
        "tests/test_complications.py":
            "d110ba358b3459a223917f7c5a526381da2175fb0c8ca0db6839ce7f92ff9350",
        "tests/test_condition_eval.py":
            "4e748d4a5a0b6fba314b3487a220f823b2ed2f5e83dc1199d3296efc1aa536b3",
        "tests/test_config_loader.py":
            "8e50b9c9f0b93a84a3a4f24a5b814772122abe530e5e0beeecb8a74899c7232c",
        "tests/test_engine_v2_skeleton.py":
            "f68ed96ed8b419d6103fbdfd07923f63d180a7a29fc113dfea9a874c7e97bb05",
        "tests/test_init_and_state.py":
            "9d8fae04150733c06458a92feeb32312e9b4305ca8871ee83393d5d305d83d2f",
        "tests/test_init_extra.py":
            "4e735639f651baa17a5236efbebf5feeff0126e3b9a07f2abe2538d63efe5a1d",
        "tests/test_long_task.py":
            "35aa0352a18926590a08232b563728852882c02aa4e88065e600b4d529ba9a51",
        "tests/test_models.py":
            "9b9e2e0633ef495e63f0e958636e2eb261c525bc2c825516a569e11c63b5e4d1",
        "tests/test_parser.py":
            "2f670a4e12a473722cb72a46c757eb83e80ed94dae5e2ea4759669468f4d4ea9",
        "tests/test_phase4.py":
            "939818981e8e1ababe44a9c54088e20378be4df68873cc40fd1134d1819e820a",
        "tests/test_prompts.py":
            "a6c54113240c99363141bc1eba3be6a945208f051aec994b073ad4bd1b354e8e",
        "tests/test_renderer.py":
            "a2ee2d26263a4a2432fe6c325e8d0c38b34d61f55f8bf3096cbbe75ad3eb4b7b",
        "tests/test_rules.py":
            "a3766857aea7dc651a28219f998e57510ebc3927de6cf4718f6c8e90ca47d0e1",
        "tests/test_state_apply.py":
            "1c4fbc05c5c4c95c58908cea9cb56f31a4916c8efad585e9ee49cecfda1c599f",
        "tests/test_tick_eval.py":
            "d966c7d04aac5c69df8fd152ba6666ea9b0f563ce67bf216b02052a5a3d8a822",
        "tests/test_tick_speed.py":
            "754f0e48ad9b6f7a81e5f8e8b2a733a3ad5e948c4d7b7ea1399d46a429673583",
        "tests/test_webui.py":
            "46df401465c06234d48cf8546f109ac9a99cc026c06e380727f49a8b687c9564",
    }
    # — 方法 6(c)：17 冻结子树哈希（G9 收口 9945565 面；锚文件特判
    #   = 前 2625 行 sha256）—
    _SUBTREE_MANIFEST: dict[str, str] = {
        "src/engine_v2/content":
            "0577125f0881733f0aa486e2bd28e82dd7845f81dfd36b9380079d059612eb28",
        "src/engine_v2/core":
            "ca3ce91983bf052e4ed92c7106665bdbbdfe8dc9e7e6714197c7397a926e21bc",
        "src/engine_v2/devtools":
            "0af2037fb12993bad937963f34f1129c9518b3e94ba926f8f05b045d0f5418a4",
        "src/engine_v2/dynamics":
            "80599cfddcaa6dfc731076e217bf5bd142c0f2bc5ac36f4f9deb683a301cb1ea",
        "src/engine_v2/llm":
            "c21ea42db68d735576784432ea5099cd29c77b65319194881c65d07d1a7ea3d0",
        "src/engine_v2/modules":
            "c8f26b136c623225335b8279b4105bfcfc0b52b0494c99e982991bc106bfbd2c",
        "src/engine_v2/persistence":
            "1b66b895f9187953c5a3fea9cd034db39d672d195208c9ece9a4912a1773a5e8",
        "src/engine_v2/plugins":
            "c3af0eaa340c9f175ec95b8a45961d26fcc77319366fb989f9b25505e926855a",
        "src/engine_v2/prompts":
            "9d6c6bc252ec92369efd419395eb530f20f2b4ec942fe9bca7806561a31a9f30",
        "tests/engine_v2/content":
            "d5bc24dfbdb6e9a0e65a666acfe37c132ee27a2b5ecbdf00b4a9ed4fa5e349d8",
        "tests/engine_v2/core":
            "9f2147030f28a5f3faeaca02884427b3ec29806c8e923262d17b0d975048503b",
        "tests/engine_v2/dynamics":
            "3f21a18872e0b4d38b6dbae2e3dec3e5b2f535c6deb93d1ceca5d2c45be4a3a5",
        "tests/engine_v2/llm":
            "2bfe397e913168c24d9ee56fd23d30e2713dde6398628400f12fb00f97768a4c",
        "tests/engine_v2/modules":
            "f8af45fec5ed8e4d6fe15a4f90a40727d9cfb186536de7ef92795716d7909160",
        "tests/engine_v2/persistence":
            "82912faf6f1887ab033ea1d4d4e70d375f09c93ba7be3b808c9dbd7f3198a32b",
        "tests/engine_v2/plugins":
            "8ec6694a2f0951c265091e9a6bbf745464c4973828811a6c1862da8a5d996705",
        "tests/engine_v2/prompts":
            "6f9ddabd276ccbf73a6caeefb0f5f88c38a3fb5b5ec323eb098855061c99dbbb",
    }
    # — 方法 6(d)：既有 7 + P9 3 样例目录哈希（G9 收口 9945565 面）—
    _FIXTURE_MANIFEST: dict[str, str] = {
        "tests/fixtures/v2_deployment":
            "58d9b531ccd0b9dbaedbb38833c476d9d9f5d10ce3d4651d01fc780c5e681fd0",
        "tests/fixtures/v2_deployment_p7":
            "d12ccec56d86799d9e44c4f759804d4a979297b4f5ccaae9a51032f07e0a0b17",
        "tests/fixtures/v2_plugin_local":
            "d430e84101e436521f92b0c5c441c24ebcf426fe23cf458a13f1f4aa37d87fd5",
        "tests/fixtures/v2_project_broken":
            "69b5c28705e3149355bc26923207daa78d94491fbffb03277c3157f0e6e1e6d1",
        "tests/fixtures/v2_project_galgame":
            "a3149a04eb708c9fa1b9329d9ac38a951b928bf2812d017770d6253e3c314572",
        "tests/fixtures/v2_project_llm":
            "fc7eef49ba6e5a429678de374dfc513fc0ab777874c2601b65c55b51e514923c",
        "tests/fixtures/v2_project_p7":
            "dfc6bfe31f0387c536183d5c433e0d2b7f9957c481a120f230f0b71c6430e1b1",
        "tests/fixtures/v2_project_sandbox":
            "6599ae08d542a37f4679d86e5a11e46e16c05c4cdbbde5b2c501ae5c58206a5d",
        "tests/fixtures/v2_project_tactical":
            "a0edf5a4f0ceb53402fa3db7f98d9f8e086b589ae10f6de7bfb3c9704a980dc9",
        "tests/fixtures/v2_project_zero_python":
            "439e166e01c4bf879c323a7f448d49483321f22a4b9271beeef90a3e038e341d",
    }

    @classmethod
    def _p10_subtree_digest(cls, sub: str) -> str:
        """子树摘要（P9 同源口径；锚文件特判 = 前 2625 行 sha256）。"""
        base = REPO_ROOT / sub
        lines = []
        for p in TestP9Boundary._walk_files(base):
            r = p.relative_to(REPO_ROOT).as_posix()
            if r == TestP9Boundary._ANCHOR_REL:
                head = p.read_bytes().splitlines(keepends=True)[: cls._ANCHOR_P10_HEAD_LINES]
                h = hashlib.sha256(b"".join(head)).hexdigest()
            else:
                h = TestP9Boundary._sha(p)
            lines.append(f"{r} {h}")
        lines.sort()
        return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()

    @classmethod
    def _p10_imported_modules(cls, path: Path) -> list[str]:
        """AST 收集完整点分 import 模块名（锚文件同源口径）。"""
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        mods: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                mods.append(node.module)
            elif isinstance(node, ast.Import):
                mods.extend(alias.name for alias in node.names)
        return mods

    @staticmethod
    def _p10_allowed_presentation_module(rel: str, module: str) -> bool:
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

    @classmethod
    def _p10_check_import_closure(cls, rel: str, modules: list[str]) -> None:
        """单文件 import 根闭集核对（§3.0 + 特例钉）。"""
        inspector_workbench = rel.endswith(("inspector.py", "workbench.py"))
        for module in modules:
            top = module.split(".")[0]
            if top in sys.stdlib_module_names:
                assert top not in cls._P10_NONDETERMINISM_ROOTS, (rel, module)
                if module == "http.server":
                    assert rel.endswith("server.py"), (rel, module)
                continue
            if top == "pydantic":
                assert rel in cls._P10_PYDANTIC_ALLOWED, (rel, module)
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
                assert cls._p10_allowed_presentation_module(rel, module), (
                    rel,
                    module,
                )
                continue
            if sub == "adapters":
                assert module.startswith("src.engine_v2.adapters.web"), (rel, module)
                continue
            assert False, (rel, module)

    def test_p10_src_tree_closed(self) -> None:
        """方法 1：P10 src 树 == 白名单行 1–19（19 项闭集；占位二件
        套属冻结面，不计）。"""
        actual: set[str] = set()
        for sub in (
            "src/engine_v2/presentation",
            "src/engine_v2/adapters/web",
        ):
            for p in TestP9Boundary._walk_files(REPO_ROOT / sub):
                actual.add(p.relative_to(REPO_ROOT).as_posix())
        actual.discard("src/engine_v2/presentation/__init__.py")
        assert actual == set(self._P10_SRC_FILES)
        assert len(actual) == 19

    def test_p10_test_tree_closed(self) -> None:
        """方法 2：P10 test 树 == 白名单行 20–35（presentation 7 +
        adapters 9）。"""
        presentation = {
            p.relative_to(REPO_ROOT).as_posix()
            for p in TestP9Boundary._walk_files(
                REPO_ROOT / "tests/engine_v2/presentation"
            )
        }
        assert presentation == set(self._P10_TEST_PRESENTATION)
        assert len(presentation) == 7
        adapters = {
            p.relative_to(REPO_ROOT).as_posix()
            for p in TestP9Boundary._walk_files(
                REPO_ROOT / "tests/engine_v2/adapters"
            )
        }
        assert adapters == set(self._P10_TEST_ADAPTERS)
        assert len(adapters) == 9

    def test_p10_string_literal_k8(self) -> None:
        """方法 3：19 src 文件字符串字面量 × 12 名零命中（唯一允许
        命中 = narrator.py TEXT_SOURCES 钉元组，ERR-P10-10）。"""
        hits: set[tuple[str, str, str]] = set()

        def scan(rel: str, text: str) -> None:
            folded = text.casefold()
            for name in P4_LLM_PROVIDER_BLACKLIST:
                if re.search(self._WB + re.escape(name) + self._WB, folded):
                    hits.add((rel, name, text))

        for rel in self._P10_SRC_FILES:
            path = REPO_ROOT / rel
            if rel.endswith(".py"):
                tree = ast.parse(path.read_text(encoding="utf-8"))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Constant) and isinstance(node.value, str):
                        scan(rel, node.value)
            else:
                scan(rel, path.read_text(encoding="utf-8"))
        assert hits == {self._K8_ALLOWED_HIT}

    def test_p10_import_closure(self) -> None:
        """方法 4：19 src 文件 import 根闭集 ⊆ §3.0（特例钉全核）+
        engine_v2 全树 langgraph/langchain 零。"""
        for rel in self._P10_SRC_FILES:
            if not rel.endswith(".py"):
                continue
            self._p10_check_import_closure(
                rel, self._p10_imported_modules(REPO_ROOT / rel)
            )
        for p in sorted((REPO_ROOT / "src" / "engine_v2").rglob("*.py")):
            if "__pycache__" in p.parts:
                continue
            for module in self._p10_imported_modules(p):
                top = module.split(".")[0]
                assert top not in ("langgraph", "langchain"), (p, module)

    def test_v1_p10_frozen_hashes(self) -> None:
        """方法 5：v1 路径集（P9-INV-1 口径）sha256 == 嵌入清单（G9
        收口 9945565 面；skeleton = P10 块刷新后值——ERR-P10-09
        双钉：P9 清单 + P10 块逐波刷新语句，最后赋值生效；本波
        零新增刷新行——skeleton 未变）。"""
        recomputed = TestP9Boundary._v1_manifest()
        expected = dict(self._V1_P10_MANIFEST)
        expected[self._SKELETON_REL] = TestP9Boundary._V1_FROZEN_MANIFEST[
            self._SKELETON_REL
        ]
        assert recomputed == expected, (
            "v1 冻结面 sha256 漂移（P10-INV-9）："
            f"差集 {set(recomputed.items()) ^ set(expected.items())}"
        )

    def test_p10_frozen_surfaces_untouched(self) -> None:
        """方法 6：(a) pyproject sha（P10-INV-10 域）；(b) 占位二件
        套 sha（§2.6）；(c) 锚文件前 2071 行 sha（P9 常量复用）+
        前 2625 行 sha（G9 收口点行）+ 17 冻结子树哈希（锚文件特判）
        ；(d) 既有 7 + P9 3 样例目录哈希。"""
        assert TestP9Boundary._sha(REPO_ROOT / "pyproject.toml") == self._PYPROJECT_SHA, (
            "pyproject.toml sha256 漂移（P10-INV-10 域）"
        )
        for rel_path, expected in self._PLACEHOLDER_MANIFEST.items():
            assert TestP9Boundary._sha(REPO_ROOT / rel_path) == expected, (
                f"占位 {rel_path} sha256 漂移（§2.6）"
            )
        anchor_path = REPO_ROOT / TestP9Boundary._ANCHOR_REL
        head_p9 = anchor_path.read_bytes().splitlines(
            keepends=True
        )[: TestP9Boundary._ANCHOR_HEAD_LINES]
        assert hashlib.sha256(b"".join(head_p9)).hexdigest() == (
            TestP9Boundary._ANCHOR_HEAD_SHA
        ), "锚文件前 2071 行 sha256 漂移（纯追加纪律破坏）"
        head_p10 = anchor_path.read_bytes().splitlines(
            keepends=True
        )[: self._ANCHOR_P10_HEAD_LINES]
        assert hashlib.sha256(b"".join(head_p10)).hexdigest() == (
            self._ANCHOR_P10_HEAD_SHA
        ), "锚文件前 2625 行 sha256 漂移（G9 收口点行漂移）"
        for sub, expected in self._SUBTREE_MANIFEST.items():
            assert self._p10_subtree_digest(sub) == expected, (
                f"engine_v2 子树 {sub} 哈希漂移（P10-INV-9 域）"
            )
        for dirname, expected in self._FIXTURE_MANIFEST.items():
            assert self._p10_subtree_digest(dirname) == expected, (
                f"fixture 目录 {dirname} 哈希漂移（P10-INV-9 域）"
            )
