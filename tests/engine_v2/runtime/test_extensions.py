"""runtime.extensions T3 gate 测试（contract §3；计划 T3 安全 Gate 全覆盖）。

跑法（targeted，禁全量）：

    PYTHONPATH=. .venv/bin/python -m pytest tests/engine_v2/runtime/test_extensions.py -q -p no:cacheprovider

Gate 映射：
1. ``test_undeclared_rogue_py_never_imported``——项目根 rogue.py 未声明 →
   零 import + 零 marker（trust False / True 双路）；
2. ``test_trust_false_zero_import_with_diagnostics``——trust_python=False +
   有效 plugin.yaml + 有效模块 → 零 import + RUNTIME_PYTHON_NOT_TRUSTED 类
   语义诊断 + bundles=()；
3. ``test_trust_true_valid_bundle_fields_one_to_one``——有效 entrypoint →
   bundles 恰 1 + 字段逐一对（对象 identity）；
4. ``test_entrypoint_returns_wrong_type``——entrypoint 返回 dict → 显式
   诊断 + bundles=() + 不抛未捕获异常；
5. ``test_entrypoint_grammar_invalid_descriptor``——entrypoint 文法非法
   （"nodots:"）→ parse 层诊断。

另补：dual-source 同 id（plugin.yaml 优先 + warning）、descriptor-only
source、import 失败 / 非 callable / arity 违例 / 字段类型违例 / build 抛
异常 / 零声明空面。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from src.engine_v2.content.schemas import (
    PluginDescriptor,
    PlayerSpec,
    ProjectIR,
    ProjectManifest,
    ScenarioSpec,
)
from src.engine_v2.runtime.extensions import (
    ExtensionLoadResult,
    ProducerGrant,
    load_extensions,
)

# —— 项目树构造面 ——


def _plugin_yaml(plugin_id: str, module_name: str) -> str:
    """有效 plugin.yaml（id/version/entrypoint 三必填面）。"""
    return (
        f"id: {plugin_id}\n"
        f'version: "1.0"\n'
        f'entrypoint: "{module_name}:build_extension"\n'
    )


def _valid_module_body(grant_id: str) -> str:
    """有效插件模块体：build_extension 返回 4 字段齐的 ExtensionBundle，
    并把产物暴露为模块级 LAST_BUNDLE（字段逐一对 identity 断言面）。"""
    return (
        'from src.engine_v2.runtime.extensions import (\n'
        "    ExtensionBundle,\n"
        "    ExtensionContext,\n"
        "    ProducerGrant,\n"
        ")\n"
        "\n"
        "LAST_BUNDLE = None\n"
        "\n"
        "\n"
        "class StubExecutor:\n"
        "    def execute(self, proposal, world, tick):\n"
        '        raise AssertionError("stub executor must not execute at load time")\n'
        "\n"
        "\n"
        "class StubBackend:\n"
        "    def metadata(self):\n"
        '        raise AssertionError("stub backend must not simulate at load time")\n'
        "\n"
        "    def simulate(self, snapshot, stimuli, context):\n"
        '        raise AssertionError("stub backend must not simulate at load time")\n'
        "\n"
        "\n"
        "class StubPolicy:\n"
        "    def decide(self, context):\n"
        "        return None\n"
        "\n"
        "\n"
        "def build_extension(context):\n"
        "    global LAST_BUNDLE\n"
        '    assert isinstance(context, ExtensionContext), f"context type: {type(context)}"\n'
        "    bundle = ExtensionBundle(\n"
        '        action_executors={"move": StubExecutor()},\n'
        "        dynamics_backends=(StubBackend(),),\n"
        '        policies={"npc": StubPolicy()},\n'
        f'        producer_grants=(ProducerGrant("{grant_id}", ("hp", "stamina"), 42),),\n'
        "    )\n"
        "    LAST_BUNDLE = bundle\n"
        "    return bundle\n"
    )


def _write_plugin(root: Path, plugin_id: str, module_name: str, body: str) -> None:
    """写 plugins/<plugin_id>/plugin.yaml + 根模块 <module_name>.py。"""
    plugin_dir = root / "plugins" / plugin_id
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.yaml").write_text(
        _plugin_yaml(plugin_id, module_name), encoding="utf-8"
    )
    (root / f"{module_name}.py").write_text(body, encoding="utf-8")


def _write_rogue(root: Path) -> None:
    """项目根未声明 rogue.py：模块级 sentinel 写 marker 文件。"""
    (root / "rogue.py").write_text(
        "from pathlib import Path\n"
        'Path(__file__).with_name("rogue_marker.txt").write_text("pwned", encoding="utf-8")\n',
        encoding="utf-8",
    )


def _make_ir(plugin_descriptors=()) -> ProjectIR:
    """最小合法 ProjectIR（plugin_descriptors 可注入）。"""
    return ProjectIR(
        manifest=ProjectManifest(
            schema_version="2",
            project_id="proj_t3",
            name="T3 Test",
        ),
        scenario=ScenarioSpec(
            id="s1",
            max_ticks=1,
            ticks_per_game_minute=1.0,
            game_time={"hour": 0, "minute": 0},
        ),
        player=PlayerSpec(player_id="p1", name="Player"),
        plugin_descriptors=tuple(plugin_descriptors),
    )


# —— 隔离面：插件模块只经本测试 import 进 sys.modules，teardown 必清；
# —— sys.path 任何残留 = 实现违约（load_extensions finally 精确还原）。
@pytest.fixture(autouse=True)
def _isolate_sys_state():
    modules_before = set(sys.modules)
    path_before = list(sys.path)
    yield
    for name in set(sys.modules) - modules_before:
        if name == "rogue" or name.startswith("extmod_"):
            del sys.modules[name]
    assert sys.path == path_before, "load_extensions 必须精确还原 sys.path"


# —— Gate 1：未声明 .py 零 import ——


def test_undeclared_rogue_py_never_imported(tmp_path):
    _write_rogue(tmp_path)
    _write_plugin(tmp_path, "sim", "extmod_g1", _valid_module_body("ext.g1"))
    ir = _make_ir()

    # trust_python=False（默认）：零 import 设计。
    result_off = load_extensions(tmp_path, ir)
    assert "rogue" not in sys.modules
    assert not (tmp_path / "rogue_marker.txt").exists()
    assert result_off.bundles == ()

    # trust_python=True：只 import 声明的模块，rogue 绝不被触碰。
    result_on = load_extensions(tmp_path, ir, trust_python=True)
    assert "rogue" not in sys.modules
    assert not (tmp_path / "rogue_marker.txt").exists()
    assert "extmod_g1" in sys.modules
    assert len(result_on.bundles) == 1
    assert result_on.diagnostics == ()


# —— Gate 2：trust_python=False 零 import + 显式诊断 ——


def test_trust_false_zero_import_with_diagnostics(tmp_path):
    _write_plugin(tmp_path, "sim", "extmod_g2", _valid_module_body("ext.g2"))
    ir = _make_ir()

    result = load_extensions(tmp_path, ir)  # trust_python 默认 False

    assert "extmod_g2" not in sys.modules, "trust_python=False 必须零 import"
    assert result.bundles == ()
    assert len(result.diagnostics) == 1
    diag = result.diagnostics[0]
    assert diag.code == "LLMSIM_PLUGIN_ENTRY_UNRESOLVED"
    assert diag.severity == "error"
    assert diag.path == "sim"
    assert "trust_python=True" in diag.message


# —— Gate 3：trust_python=True 有效 entrypoint → bundles 恰 1 + 字段逐一对 ——


def test_trust_true_valid_bundle_fields_one_to_one(tmp_path):
    _write_plugin(tmp_path, "sim", "extmod_g3", _valid_module_body("ext.g3"))
    ir = _make_ir()

    result = load_extensions(tmp_path, ir, trust_python=True)

    assert isinstance(result, ExtensionLoadResult)
    assert result.diagnostics == ()
    assert len(result.bundles) == 1
    bundle = result.bundles[0]
    expected = sys.modules["extmod_g3"].LAST_BUNDLE

    # 字段逐一对（对象 identity，非仅同形）。
    assert bundle.action_executors["move"] is expected.action_executors["move"]
    assert bundle.dynamics_backends[0] is expected.dynamics_backends[0]
    assert bundle.policies["npc"] is expected.policies["npc"]
    assert bundle.producer_grants == expected.producer_grants
    assert bundle.producer_grants[0].producer_id == "ext.g3"
    assert bundle.producer_grants[0].component_types == ("hp", "stamina")
    assert bundle.producer_grants[0].priority == 42

    # 冻结 API 面：ProducerGrant.priority 默认 50。
    assert ProducerGrant("x", ()).priority == 50


# —— Gate 4：entrypoint 返回错误类型 → 显式诊断 + 不抛未捕获异常 ——


def test_entrypoint_returns_wrong_type(tmp_path):
    plugin_dir = tmp_path / "plugins" / "sim"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.yaml").write_text(
        _plugin_yaml("sim", "extmod_g4"), encoding="utf-8"
    )
    (tmp_path / "extmod_g4.py").write_text(
        "def build_extension(context):\n"
        '    return {"action_executors": {}}\n',
        encoding="utf-8",
    )
    ir = _make_ir()

    result = load_extensions(tmp_path, ir, trust_python=True)  # 不抛 = 通过

    assert result.bundles == ()
    assert len(result.diagnostics) == 1
    diag = result.diagnostics[0]
    assert diag.code == "LLMSIM_SCHEMA"
    assert diag.severity == "error"
    assert diag.path == "sim"
    assert "ExtensionBundle" in diag.message
    assert "dict" in diag.message


# —— Gate 5：entrypoint 文法非法（"nodots:"）→ parse 层诊断 ——


def test_entrypoint_grammar_invalid_descriptor(tmp_path):
    ir = _make_ir(
        [PluginDescriptor(id="g5", source="local", entrypoint="nodots:")]
    )

    result = load_extensions(tmp_path, ir, trust_python=True)

    assert result.bundles == ()
    assert len(result.diagnostics) == 1
    diag = result.diagnostics[0]
    assert diag.code == "LLMSIM_PLUGIN_ENTRY_INVALID"
    assert diag.severity == "error"
    assert diag.path == "nodots:"


# —— 双 source 同 id：plugin.yaml 侧优先 + 恰 1 条 warning ——


def test_dual_source_same_id_yaml_side_wins(tmp_path):
    _write_plugin(tmp_path, "sim", "extmod_dual_a", _valid_module_body("ext.a"))
    (tmp_path / "extmod_dual_b.py").write_text(
        _valid_module_body("ext.b"), encoding="utf-8"
    )
    ir = _make_ir(
        [
            PluginDescriptor(
                id="sim", source="local", entrypoint="extmod_dual_b:build_extension"
            )
        ]
    )

    result = load_extensions(tmp_path, ir, trust_python=True)

    assert len(result.bundles) == 1
    assert result.bundles[0].producer_grants[0].producer_id == "ext.a"
    assert "extmod_dual_b" not in sys.modules, "非优先侧不得被 import"
    warnings = [d for d in result.diagnostics if d.severity == "warning"]
    assert len(warnings) == 1
    assert warnings[0].code == "LLMSIM_DUPLICATE_ID"
    assert warnings[0].path == "sim"


# —— source 2 单独面：descriptor-only（无 plugins/ 目录）——


def test_descriptor_only_source(tmp_path):
    (tmp_path / "extmod_desc.py").write_text(
        _valid_module_body("ext.desc"), encoding="utf-8"
    )
    ir = _make_ir(
        [
            PluginDescriptor(
                id="onlyd", source="local", entrypoint="extmod_desc:build_extension"
            )
        ]
    )

    result = load_extensions(tmp_path, ir, trust_python=True)

    assert result.diagnostics == ()
    assert len(result.bundles) == 1
    assert result.bundles[0].producer_grants[0].producer_id == "ext.desc"


# —— entrypoint 定位失败：模块不存在 → 显式诊断 + 不抛 ——


def test_import_failure_module_missing(tmp_path):
    plugin_dir = tmp_path / "plugins" / "sim"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.yaml").write_text(
        _plugin_yaml("sim", "extmod_missing_xyz"), encoding="utf-8"
    )
    ir = _make_ir()

    result = load_extensions(tmp_path, ir, trust_python=True)  # 不抛 = 通过

    assert result.bundles == ()
    assert "extmod_missing_xyz" not in sys.modules
    assert len(result.diagnostics) == 1
    diag = result.diagnostics[0]
    assert diag.code == "LLMSIM_PLUGIN_ENTRY_INVALID"
    assert diag.path == "sim"
    assert "import" in diag.message
    assert "extmod_missing_xyz" in diag.refs


# —— entrypoint 对象验证：非 callable ——


def test_entrypoint_not_callable(tmp_path):
    _write_plugin(tmp_path, "sim", "extmod_g9", "build_extension = 42\n")
    ir = _make_ir()

    result = load_extensions(tmp_path, ir, trust_python=True)

    assert result.bundles == ()
    assert len(result.diagnostics) == 1
    diag = result.diagnostics[0]
    assert diag.code == "LLMSIM_PLUGIN_ENTRY_INVALID"
    assert diag.path == "sim"
    assert "callable" in diag.message


# —— entrypoint 对象验证：arity 违例（2 个位置参数）——


def test_entrypoint_wrong_arity(tmp_path):
    _write_plugin(
        tmp_path,
        "sim",
        "extmod_g10",
        "def build_extension(a, b):\n"
        '    raise AssertionError("must not run")\n',
    )
    ir = _make_ir()

    result = load_extensions(tmp_path, ir, trust_python=True)

    assert result.bundles == ()
    assert len(result.diagnostics) == 1
    diag = result.diagnostics[0]
    assert diag.code == "LLMSIM_PLUGIN_ENTRY_INVALID"
    assert "位置参数" in diag.message


# —— ExtensionBundle 字段类型违例（action_executors = list）——


def test_bundle_field_type_violation(tmp_path):
    _write_plugin(
        tmp_path,
        "sim",
        "extmod_g11",
        "from src.engine_v2.runtime.extensions import ExtensionBundle\n"
        "\n"
        "\n"
        "def build_extension(context):\n"
        '    return ExtensionBundle(action_executors=["not-a-mapping"])\n',
    )
    ir = _make_ir()

    result = load_extensions(tmp_path, ir, trust_python=True)

    assert result.bundles == ()
    assert len(result.diagnostics) == 1
    diag = result.diagnostics[0]
    assert diag.code == "LLMSIM_SCHEMA"
    assert diag.path == "sim"
    assert "action_executors" in diag.message


# —— build_extension 执行抛异常 → 显式诊断 + 不牵连其余插件 ——


def test_build_extension_raises_and_rest_survive(tmp_path):
    _write_plugin(
        tmp_path,
        "bad",
        "extmod_g12_bad",
        "def build_extension(context):\n"
        '    raise ValueError("boom")\n',
    )
    _write_plugin(
        tmp_path, "good", "extmod_g12_good", _valid_module_body("ext.good")
    )
    ir = _make_ir()

    result = load_extensions(tmp_path, ir, trust_python=True)

    assert len(result.bundles) == 1
    assert result.bundles[0].producer_grants[0].producer_id == "ext.good"
    errors = [d for d in result.diagnostics if d.severity == "error"]
    assert len(errors) == 1
    assert errors[0].code == "LLMSIM_SCHEMA"
    assert errors[0].path == "bad"
    assert "ValueError" in errors[0].message


# —— 空面：零声明 → 零 bundles + 零诊断（双 trust 面）——


def test_no_declarations_zero_diagnostics(tmp_path):
    ir = _make_ir()

    result_off = load_extensions(tmp_path, ir)
    assert result_off.bundles == ()
    assert result_off.diagnostics == ()

    result_on = load_extensions(tmp_path, ir, trust_python=True)
    assert result_on.bundles == ()
    assert result_on.diagnostics == ()


# —— descriptor entrypoint=None = 非可执行声明（静默，无 trust 诊断）——


def test_descriptor_without_entrypoint_is_not_declared(tmp_path):
    ir = _make_ir([PluginDescriptor(id="nop", source="local", entrypoint=None)])

    result = load_extensions(tmp_path, ir)  # trust_python=False

    assert result.bundles == ()
    assert result.diagnostics == ()
