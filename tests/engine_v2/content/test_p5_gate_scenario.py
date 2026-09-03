"""P5 门场景测试：SOT §5.2 断言表 20 行 1:1 映射 test_assert_01..test_assert_20。

- SOT 锚：``docs/v2/contracts/P5-project-format-module-plugin-dsl-design.md``
  §5.1 S0–S9 步表（L680-694）+ §5.2 断言表（L696-731）；
- A7 纪律：恰好 20 个扁平测试函数，零测试类，零 subprocess（subprocess 三态
  在 ``test_p5_integration``，A8）；
- S0–S9 以本文件私有 helper + conftest fixture（``zero_python_project`` /
  ``broken_project`` / ``plugin_project`` / ``make_*`` 构造器）承载；
- K8 自扫描纪律：12 名探针常量全部字符串拼接构造（断言 #19 消费）。
"""

from __future__ import annotations

import ast
import importlib
import inspect
import json
import sys
from collections.abc import Iterator
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

import yaml
from pydantic import BaseModel

import tests.engine_v2.content.test_rule_dsl_parity as parity_module
from src.engine_v2.content.cli import main
from src.engine_v2.content.loader import load_project
from src.engine_v2.content.module_graph import build_module_graph, topological_order
from src.engine_v2.content.project_ir import build_ir, canonical_yaml
from src.engine_v2.content.rule_module import DSL_NODE_KINDS, parse_dsl
from src.engine_v2.content.schemas import (
    DIAGNOSTIC_CODES,
    InferenceCapabilityProfile,
    ProjectIR,
    PromptPolicy,
)
from src.engine_v2.content.validator import (
    check_deployment_leakage,
    validate_project,
)
from src.engine_v2.plugins.registry import (
    PluginSourceKind,
    discover_entry_point_plugins,
    discover_local_plugins,
)
from tests.engine_v2.content.conftest import (
    make_ir,
    make_module_node,
    make_raw_project,
)
from tests.engine_v2.plugins.conftest import FakeDistribution, FakeEntryPoint

_REPO_ROOT = Path(__file__).resolve().parents[3]

# K8 探针名（拼接构造，避免本文件自身命中 12 名扫描面）。
_API_KEY = "api_" + "key"
_PROVIDER = "prov" + "ider"
_BASE_URL = "base_" + "url"
_OPEN_AI = "open" + "ai"

# 插件族诊断码（断言 #3 / #7 消费）。
_PLUGIN_FAMILY_CODES = frozenset(
    {
        "LLMSIM_PLUGIN_ENTRY_INVALID",
        "LLMSIM_PLUGIN_NO_PYPROJECT",
        "LLMSIM_PLUGIN_ENTRY_UNRESOLVED",
    }
)

# 断言 #7 用最小合法 v2 项目面（manifest/scenario/player 三必需节齐）。
_MINIMAL_GAME_YAML = (
    "manifest:\n"
    "  schema_version: \"2\"\n"
    "  project_id: gate_probe\n"
    "  name: Gate Probe\n"
    "  engine_version: \">=0.5.0\"\n"
    "scenario:\n"
    "  id: scenario_main\n"
    "  max_ticks: 10\n"
    "  ticks_per_game_minute: 1\n"
    "  game_time:\n"
    "    hour: 9\n"
    "    minute: 0\n"
    "  starting_scene_description: a quiet room\n"
    "  narrative_style: second person\n"
    "player:\n"
    "  player_id: player_1\n"
    "  name: Gate\n"
    "  persona: probe persona\n"
    "  position: {x: 0, y: 0, z: 0}\n"
    "  capabilities: {}\n"
    "  physical_profile: {}\n"
    "  attributes: {}\n"
    "  inventory: []\n"
)

_CLEAN_PYPROJECT = '[project]\nname = "gate-probe"\nversion = "0.1.0"\ndependencies = []\n'

# 断言 #12 合法语料（文法：if(条件, outcome; ...; trailing)，trailing 必需）。
_LEGAL_DSL_CORPUS = (
    "if(a < 1, blocked; allowed)",
    "if(a = 1, allowed; blocked)",
    "if(rand() < 0.5, allowed; blocked)",
    "if(x in y, allowed; blocked)",
    "if(a not in y, blocked; allowed)",
    "if(len(items) > max(a, b), allowed; blocked)",
    "if(not a and b >= min(c, 2), uncertain : 0.5; blocked)",
    "if(player.strength >= target.weight * 1.5, allowed; blocked)",
    "if(a contains b or c disjoint d, allowed; blocked)",
)

# 断言 #12 对抗语料（闭文法外：循环 / 函数定义 / lambda）。
_ADVERSARIAL_DSL = (
    "while (x) {",
    "def f(): pass",
    "lambda x: x",
)


def _run_main(argv: list[str]) -> tuple[int, str, str]:
    """main() 包 stdout/stderr 捕获（A7：进程内调用，零 subprocess）。"""
    out = StringIO()
    err = StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


def _full_chain(root: Path) -> tuple[object, object, object]:
    """load_project → build_ir → validate_project 三段链（raw/ir 非 None 断言内置）。"""
    loaded = load_project(root)
    assert loaded.raw is not None, f"raw is None: {loaded.diagnostics}"
    built = build_ir(loaded.raw)
    assert built.ir is not None, f"ir is None: {built.diagnostics}"
    result = validate_project(built.ir, loaded.raw)
    return loaded, built, result


def _iter_nested_nodes(value: object) -> Iterator[BaseModel]:
    """递归展开 DSL AST 嵌套字段（tuple/list 内层节点）。"""
    if isinstance(value, BaseModel) and hasattr(value, "kind"):
        yield value
    elif isinstance(value, (tuple, list)):
        for item in value:
            yield from _iter_nested_nodes(item)


def _walk_node_kinds(node: BaseModel) -> Iterator[str]:
    """深度遍历 DSL AST，逐节点产 kind（断言 #12 闭文法面）。"""
    yield node.kind
    for value in node.__dict__.values():
        for child in _iter_nested_nodes(value):
            yield from _walk_node_kinds(child)


# ── 断言 #1–#3：S1 零-Python 项目（S0/S1/G5-1）─────────────────────────────


def test_assert_01(zero_python_project: Path) -> None:
    """§5.2 #1：load_project 5 文件全部命中模板，FILE_MISSING 零条。"""
    loaded = load_project(zero_python_project)
    assert loaded.raw is not None
    assert loaded.diagnostics == ()
    assert set(loaded.raw.files) == {
        "game.yaml",
        "world/main_world.yaml",
        "characters/npc01.yaml",
        "rules/basics.yaml",
        "actions/move.yaml",
    }


def test_assert_02(zero_python_project: Path) -> None:
    """§5.2 #2：全链零诊断；CLI validate 退出码 0，摘要行尾。"""
    _loaded, _built, result = _full_chain(zero_python_project)
    assert result.diagnostics == ()
    code, out, err = _run_main(["validate", str(zero_python_project)])
    assert code == 0
    assert err == ""
    assert out.endswith("llmsim validate: 0 error(s), 0 warning(s)\n")


def test_assert_03(zero_python_project: Path) -> None:
    """§5.2 #3：零-Python 前提（无插件目录/无 pyproject）→ 插件族诊断零条。"""
    loaded, _built, result = _full_chain(zero_python_project)
    assert loaded.raw is not None
    assert loaded.raw.plugins_dir_present is False
    assert loaded.raw.pyproject_present is False
    assert [d for d in result.diagnostics if d.code in _PLUGIN_FAMILY_CODES] == []


# ── 断言 #4–#5：S3 插件双路发现（G5-2）─────────────────────────────────────


def test_assert_04(plugin_project: Path) -> None:
    """§5.2 #4：plugins/<id>/plugin.yaml → 本地注册；无 manifest 目录静默零。"""
    loaded, _built, _result = _full_chain(plugin_project)
    registry, diags = discover_local_plugins(loaded.raw)
    assert diags == ()
    assert set(registry.plugins) == {"infection"}
    entry = registry.plugins["infection"]
    assert entry.source is PluginSourceKind.LOCAL_MANIFEST
    assert entry.origin == "plugins/infection/plugin.yaml"

    bare = make_raw_project(files={}, plugins_dir_present=True)
    registry2, diags2 = discover_local_plugins(bare)
    assert registry2.plugins == {}
    assert diags2 == ()


def test_assert_05(monkeypatch) -> None:
    """§5.2 #5：entry-point 路 metadata-only（零 import）；值文法违例 → 诊断。"""
    monkeypatch.setattr(
        "importlib.metadata.entry_points",
        lambda group=None, **_kw: [
            FakeEntryPoint(
                name="infection",
                value="infection_plugin.system:InfectionSystem",
                distribution=FakeDistribution("infection-plugin", "1.0.0"),
            )
        ],
    )
    registry, diags = discover_entry_point_plugins()
    assert diags == ()
    entry = registry.plugins["infection"]
    assert entry.source is PluginSourceKind.ENTRY_POINT
    assert entry.origin == "infection-plugin"
    assert entry.manifest.version == "1.0.0"
    # metadata-only：EP 指向的模块零 import。
    assert "infection_plugin" not in sys.modules
    assert "infection_plugin.system" not in sys.modules

    monkeypatch.setattr(
        "importlib.metadata.entry_points",
        lambda group=None, **_kw: [
            FakeEntryPoint(
                name="bad_ep",
                value="no-colon-here",
                distribution=FakeDistribution("bad-dist", "0.1.0"),
            )
        ],
    )
    registry2, diags2 = discover_entry_point_plugins()
    assert registry2.plugins == {}
    assert len(diags2) == 1
    bad = diags2[0]
    assert bad.code == "LLMSIM_PLUGIN_ENTRY_INVALID"
    assert bad.path == "no-colon-here"
    assert bad.refs == ("bad-dist",)
    assert bad.severity == "error"


# ── 断言 #6–#7：G5-3 零动态加载（静态 + 动态面）────────────────────────────


def test_assert_06() -> None:
    """§5.2 #6：AST 扫描 src/engine_v2 全量 .py → 动态 import 调用位点零命中。

    12h runtime closure（2026-09-04 Leader 裁决）：``src/engine_v2/runtime/`` 为
    计划授权的唯一动态加载面（Gates C2/C3：trust_python=True 时仅 import
    已声明插件 entrypoint）；该层降级为单点纪律，见 test_assert_06b。
    """
    banned_calls = {"import_module", "__import__", "spec_from_file_location", "module_from_spec"}
    violations: list[str] = []
    entry_load_sites: list[str] = []
    py_files = sorted(_REPO_ROOT.joinpath("src", "engine_v2").rglob("*.py"))
    assert len(py_files) > 0
    covered = {p.name for p in py_files}
    assert "loader.py" in covered
    assert "registry.py" in covered
    for py in py_files:
        if "runtime" in py.parts:  # 见 docstring：runtime 单点纪律 → test_assert_06b
            continue
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Attribute):
                if func.attr in banned_calls:
                    violations.append(f"{py.name}:{node.lineno} call {func.attr}()")
                if func.attr == "load":
                    base = func.value
                    is_entry = (
                        (isinstance(base, ast.Name) and base.id == "entry")
                        or (isinstance(base, ast.Attribute) and base.attr == "entry")
                    )
                    if is_entry:
                        entry_load_sites.append(f"{py.name}:{node.lineno} entry.load()")
            elif isinstance(func, ast.Name) and func.id in banned_calls:
                violations.append(f"{py.name}:{node.lineno} call {func.id}()")
    assert violations == []
    assert entry_load_sites == []


def test_assert_06b() -> None:
    """§5.2 #6b（12h runtime closure，2026-09-04 Leader 裁决）：
    ``src/engine_v2/runtime/`` 动态 import 单点纪律 —— 动态加载调用位点
    仅限 extensions.py（trusted Python 加载器）单处 import_module()；
    其余文件 / 其余位点 / 其余四元组调用 = 违规。"""
    runtime_dir = _REPO_ROOT.joinpath("src", "engine_v2", "runtime")
    py_files = sorted(runtime_dir.rglob("*.py"))
    assert py_files, "runtime/ 不得为空"
    banned_calls = {"import_module", "__import__", "spec_from_file_location", "module_from_spec"}
    sites: list[str] = []
    for py in py_files:
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr in banned_calls:
                    sites.append(f"{py.name}:{node.lineno} {node.func.attr}()")
    assert len(sites) == 1, f"runtime 动态 import 必须恰 1 位点：{sites}"
    assert sites[0].startswith("extensions.py:"), sites
    assert sites[0].endswith(" import_module()"), sites


def test_assert_07(tmp_path: Path) -> None:
    """§5.2 #7：plugins/<x>/ 流氓 .py（无 manifest）→ 插件诊断零条且零 import。"""
    root = tmp_path / "rogue_probe"
    (root / "plugins" / "rogue").mkdir(parents=True)
    (root / "game.yaml").write_text(_MINIMAL_GAME_YAML, encoding="utf-8")
    (root / "pyproject.toml").write_text(_CLEAN_PYPROJECT, encoding="utf-8")
    (root / "plugins" / "rogue" / "plugin_impl.py").write_text("X = 1\n", encoding="utf-8")
    loaded = load_project(root)
    assert loaded.raw is not None
    assert loaded.raw.plugins_dir_present is True
    assert loaded.raw.pyproject_present is True
    built = build_ir(loaded.raw)
    assert built.ir is not None
    result = validate_project(built.ir, loaded.raw)
    assert [d for d in result.diagnostics if d.code in _PLUGIN_FAMILY_CODES] == []
    assert result.diagnostics == ()
    assert "rogue" not in sys.modules
    assert "plugin_impl" not in sys.modules


# ── 断言 #8–#10：S4/S5 模块图与插件校验面（G5-2/G5-4）──────────────────────


def test_assert_08() -> None:
    """§5.2 #8：plugins/ 目录在而 pyproject.toml 缺 → 恰 1 条 PLUGIN_NO_PYPROJECT。"""
    raw = make_raw_project(files={}, plugins_dir_present=True)
    result = validate_project(make_ir(), raw)
    assert len(result.diagnostics) == 1
    diag = result.diagnostics[0]
    assert diag.code == "LLMSIM_PLUGIN_NO_PYPROJECT"
    assert diag.path == "pyproject.toml"
    assert diag.severity == "error"


def test_assert_09() -> None:
    """§5.2 #9：a→b→c→a 环 → topological_order []；恰 1 条 MODULE_CYCLE。"""
    ir = make_ir(
        modules=(
            make_module_node(id="a", requires=("b",)),
            make_module_node(id="b", requires=("c",)),
            make_module_node(id="c", requires=("a",)),
        )
    )
    graph = build_module_graph(ir)
    assert topological_order(graph) == []
    result = validate_project(ir)
    assert len(result.diagnostics) == 1
    diag = result.diagnostics[0]
    assert diag.code == "LLMSIM_MODULE_CYCLE"
    assert diag.refs == ("a", "b", "c")
    assert diag.path == "a"


def test_assert_10() -> None:
    """§5.2 #10：菱形 a→{b,c}→d → Kahn 确定序 [a, b, c, d]。"""
    ir = make_ir(
        modules=(
            make_module_node(id="mod.a", requires=("mod.b", "mod.c")),
            make_module_node(id="mod.b", requires=("mod.d",)),
            make_module_node(id="mod.c", requires=("mod.d",)),
            make_module_node(id="mod.d"),
        )
    )
    graph = build_module_graph(ir)
    assert topological_order(graph) == ["mod.a", "mod.b", "mod.c", "mod.d"]


# ── 断言 #11–#12：S6 DSL 等价与闭文法（G5-5）──────────────────────────────


def test_assert_11(request) -> None:
    """§5.2 #11：66 条 parity 测试逐函数重跑，零新增、零缺失、零失败。"""
    names = sorted(n for n in dir(parity_module) if n.startswith("test_"))
    assert len(names) == 66
    for name in names:
        fn = getattr(parity_module, name)
        params = list(inspect.signature(fn).parameters)
        kwargs = {p: request.getfixturevalue(p) for p in params}
        fn(**kwargs)


def test_assert_12() -> None:
    """§5.2 #12：合法语料逐节点 kind ∈ 闭集合；def/while/lambda → DSL_PARSE。"""
    assert len(DSL_NODE_KINDS) == 23
    assert not ({"while", "loop", "def", "lambda"} & DSL_NODE_KINDS)
    for expression in _LEGAL_DSL_CORPUS:
        parsed = parse_dsl(expression, "gate")
        assert parsed.diagnostics == (), expression
        assert parsed.ast is not None, expression
        kinds = list(_walk_node_kinds(parsed.ast))
        assert kinds, expression
        for kind in kinds:
            assert kind in DSL_NODE_KINDS, (expression, kind)
    for expression in _ADVERSARIAL_DSL:
        parsed = parse_dsl(expression, "gate")
        assert parsed.ast is None, expression
        assert len(parsed.diagnostics) == 1, expression
        assert parsed.diagnostics[0].code == "LLMSIM_DSL_PARSE", expression


# ── 断言 #13–#15：S7 CLI 三态与 --json（G5-6）─────────────────────────────


def test_assert_13(broken_project: Path) -> None:
    """§5.2 #13：broken --json → 退出码 1；stdout 纯 JSON，4 键闭合。"""
    code, out, _err = _run_main(["validate", str(broken_project), "--json"])
    assert code == 1
    data = json.loads(out)
    assert set(data) == {"ok", "project", "diagnostics", "exit_code"}
    assert data["ok"] is False
    assert data["exit_code"] == 1
    assert data["project"] == str(broken_project)


def test_assert_14(broken_project: Path) -> None:
    """§5.2 #14：--json 双跑 stdout 字节相等；诊断三元组 (code, path, message) 有序。"""
    code1, out1, err1 = _run_main(["validate", str(broken_project), "--json"])
    code2, out2, err2 = _run_main(["validate", str(broken_project), "--json"])
    assert code1 == code2 == 1
    assert out1 == out2
    assert err1 == err2 == ""
    data = json.loads(out1)
    triples = [(d["code"], d["path"], d["message"]) for d in data["diagnostics"]]
    assert triples == sorted(triples)


def test_assert_15(zero_python_project: Path, broken_project: Path) -> None:
    """§5.2 #15：CLI 三态退出码 0（净）/ 1（坏）/ 2（用法错）。"""
    assert _run_main(["validate", str(zero_python_project)])[0] == 0
    assert _run_main(["validate", str(broken_project)])[0] == 1
    assert _run_main([])[0] == 2
    assert _run_main(["frobnicate"])[0] == 2


# ── 断言 #16–#18：S8 v1 拒绝 + S4 诊断面 + S5 缺依赖（G5-1/G5-4）───────────


def test_assert_16(tmp_path: Path) -> None:
    """§5.2 #16：v1 形状 game.yaml → 恰 1 条 PROJECT_FORMAT_V1，raw = None。"""
    v1_source = _REPO_ROOT / "public_start" / "test_empty.yaml"
    root = tmp_path / "legacy"
    root.mkdir()
    (root / "game.yaml").write_bytes(v1_source.read_bytes())
    loaded = load_project(root)
    assert loaded.raw is None
    codes = [d.code for d in loaded.diagnostics]
    assert codes.count("LLMSIM_PROJECT_FORMAT_V1") == 1
    assert all(c == "LLMSIM_PROJECT_FORMAT_V1" for c in codes)


def test_assert_17(broken_project: Path) -> None:
    """§5.2 #17：broken 全链每条诊断字段面良构；10 模块 116 导出名全局唯一。

    （116 名唯一性内置于本函数 = D-04 偏差记录位：A7 钉死 20 函数，SOT
    「内置于 test_p5_gate_scenario」以单函数承载。）
    """
    _loaded, _built, result = _full_chain(broken_project)
    assert result.diagnostics
    for diag in result.diagnostics:
        assert diag.code in DIAGNOSTIC_CODES
        assert diag.severity in ("error", "warning")
        assert diag.path
        assert diag.message
    module_paths = (
        "src.engine_v2.content.schemas",
        "src.engine_v2.content.project_ir",
        "src.engine_v2.content.loader",
        "src.engine_v2.content.module_graph",
        "src.engine_v2.content.rule_module",
        "src.engine_v2.content.validator",
        "src.engine_v2.content.cli",
        "src.engine_v2.plugins.manifest",
        "src.engine_v2.plugins.api",
        "src.engine_v2.plugins.registry",
    )
    all_names = [
        name
        for module_path in module_paths
        for name in importlib.import_module(module_path).__all__
    ]
    assert len(all_names) == 116
    assert len(set(all_names)) == 116


def test_assert_18() -> None:
    """§5.2 #18：B requires A 而 A 未声明 → 恰 1 条 MODULE_REQUIRES_MISSING。"""
    ir = make_ir(modules=(make_module_node(id="mod.b", requires=("mod.a",)),))
    result = validate_project(ir)
    assert len(result.diagnostics) == 1
    diag = result.diagnostics[0]
    assert diag.code == "LLMSIM_MODULE_REQUIRES_MISSING"
    assert diag.path == "mod.b"
    assert diag.refs == ("mod.a",)


# ── 断言 #19–#20：K8 探针表 + K7 规范化往返（D-P5-11 / D-P5-13）────────────


def test_assert_19(broken_project: Path) -> None:
    """§5.2 #19：K8 探针表 P1–P4 全命中、N1–N3 零误报；推断/策略字段无部署名。

    - P1/P2/P3：broken fixture game.yaml 携带三个部署字段名（含值面词）；
    - P4：单元级 raw 构造，pyproject.toml 依赖行 → 直调 check_deployment_leakage；
    - N1–N3：model / 下划线延申键名 / 本仓库名 → 零命中；
    - 字段面：InferenceCapabilityProfile / PromptPolicy 字段集无部署字段名。
    """
    _loaded, _built, result = _full_chain(broken_project)
    dep = [d for d in result.diagnostics if d.code == "LLMSIM_DEPLOYMENT_FIELD"]
    ref_names = {ref for d in dep for ref in d.refs}
    assert _API_KEY in ref_names
    assert _PROVIDER in ref_names
    assert _BASE_URL in ref_names
    assert _OPEN_AI in ref_names

    raw_dep = make_raw_project(
        files={},
        pyproject_present=True,
        pyproject_text='[project]\ndependencies = ["' + _OPEN_AI + '-sdk == 1.0.0"]\n',
    )
    leak = check_deployment_leakage(raw_dep)
    assert len(leak) == 1
    assert leak[0].path == "pyproject.toml"
    assert leak[0].refs == (_OPEN_AI,)

    clean_text = "model: something\n" + _API_KEY + "_env: X\nllmsim: y\n"
    raw_clean = make_raw_project(
        files={"game.yaml": {}}, texts={"game.yaml": clean_text}
    )
    assert check_deployment_leakage(raw_clean) == []

    cap_fields = set(InferenceCapabilityProfile.model_fields)
    pol_fields = set(PromptPolicy.model_fields)
    banned = {_PROVIDER, "model", _BASE_URL, _API_KEY}
    assert not (banned & (cap_fields | pol_fields))


def test_assert_20(zero_python_project: Path, plugin_project: Path) -> None:
    """§5.2 #20：canonical_yaml → safe_load → model_validate == ir；双 dump 字节稳。"""
    for root in (zero_python_project, plugin_project):
        _loaded, built, _result = _full_chain(root)
        ir = built.ir
        text1 = canonical_yaml(ir)
        ir2 = ProjectIR.model_validate(yaml.safe_load(text1))
        assert ir2 == ir
        assert canonical_yaml(ir2) == text1
