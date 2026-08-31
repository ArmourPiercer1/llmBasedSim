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
                        if re.search(rf"{re.escape(word)}", text)
                    )
            if matched:
                hits[str(path.relative_to(REPO_ROOT))] = sorted(matched)
        assert not hits, (
            f"P7 文件命中 12 名黑名单字符串字面量域（SOT §3.9 方法 3）：{hits}"
        )
        probe = re.compile(r"(?:" + "|".join(joined) + r")")
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
