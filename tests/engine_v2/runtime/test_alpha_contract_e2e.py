"""0.1.0-alpha.1 M4——production-only 中性 contract E2E。

数据面 = ``tests/fixtures/alpha_contract``（中性「测量实验室」项目，零玩法
语义）+ ``alpha_contract`` 扩展（M3.5 通用 contract 验证扩展）。装配入口
**只有** production 链：``assemble_project(root, trust_python=True)``
（零 test-only assembly、零 tests import——K13 面由 a13 机械断言）。

M4.3 十四能力面 → 测试映射：

1.  tick-0 完整 WorldState              → a1
2.  attributes 无首访自举               → a1
3.  inventory 无首访自举 + authoritative ID → a2
4.  item state/properties 无首访自举    → a3
5.  item 引用 = authoritative entity ID → a2
6.  自定义 ActionExecutor production 绑定 → a4
7.  自定义 solver 可被 executor 调用    → a4（scale_max 来自 tick-0 item 组件）
8.  一次动作 → 多 ProposedEffect        → a5
9.  自定义 DynamicsBackend production 绑定 → a7
10. 组件 grant 生效                     → a4 / a7（授权 producer 提交成功）
11. Kernel state-domain grant 生效      → a8（dynamics 写 world_variables）
12. 世界变量经正式 authority 管道修改    → a8 / a9（动作侧 + 后端侧）
13. 世界时间增量依赖当前 WorldState     → a9
14. 无直写面                            → a14
15. failure/deny 路径零状态变更         → a6 / a11
16. deterministic replay-by-input ≥1 E2E → a12
17. production E2E 不依赖 tests         → a13
（clean install / version / README / tag = M5 发布面，非本文件。）
"""

from __future__ import annotations

import ast
import dataclasses
import sys
from pathlib import Path

import pytest

from src.engine_v2.content.schemas import DiagnosticSeverity
from src.engine_v2.core.components import ComponentTypeId
from src.engine_v2.core.ids import EntityId
from src.engine_v2.core.serialization import dump_json
from src.engine_v2.modules.actions import ExecutorResult
from src.engine_v2.dynamics.backend import WorldSnapshot
from src.engine_v2.runtime import assemble_project

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "alpha_contract"
RUNTIME_DIR = REPO_ROOT / "src" / "engine_v2" / "runtime"
RUNNER_SCRIPT = REPO_ROOT / "scripts" / "v2_alpha_run.py"

OPERATOR = EntityId("ent_authoring_operator")
RESPONDER = EntityId("ent_authoring_responder")
GAUGE = EntityId("ent_authoring_gauge")
KIT = EntityId("ent_authoring_kit")

GAUGE_READING = ComponentTypeId("gauge_reading")
ATTRIBUTES = ComponentTypeId("attributes")
ITEM = ComponentTypeId("item")
INVENTORY = ComponentTypeId("inventory")


# —— 公共面（每测试全新装配：零跨测试世界共享）——


def _fresh():
    result = assemble_project(str(FIXTURE_ROOT), trust_python=True)
    fatal = [d.message for d in result.diagnostics if d.severity is DiagnosticSeverity.ERROR]
    assert result.engine is not None, f"装配 fatal：{fatal}"
    assert result.instance is not None
    return result


def _world(result):
    return result.instance.world


def _comp(result, eid: EntityId, ct: ComponentTypeId):
    return _world(result).entities[eid].components.get(ct)


def _num(data: dict | None, key: str) -> float | None:
    if not data:
        return None
    v = data.get(key)
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _run_seq(result, actions: list[tuple[str, dict]], ticks: int) -> None:
    """确定性输入序列：动作（执行序）+ 尾部 advance。"""
    for action_id, args in actions:
        result.engine.submit_action(OPERATOR, action_id, args)
    for _ in range(ticks):
        result.engine.advance(1)


# —— a0：装配面 ——


def test_a0_assembly_no_fatal_diagnostics():
    """装配链（load→materialize→extensions→binding→authority）零 ERROR。"""
    result = _fresh()
    errors = [d for d in result.diagnostics if d.severity is DiagnosticSeverity.ERROR]
    assert not errors, [d.message for d in errors]


# —— a1–a3：tick-0 初始状态物化（M1 面，无首访自举）——


def test_a1_tick0_attributes_materialized():
    result = _fresh()
    player_attrs = _comp(result, OPERATOR, ATTRIBUTES)
    assert _num(player_attrs, "calibration_skill") is None  # 值是嵌套 dict，非裸数
    assert player_attrs["calibration_skill"]["value"] == 6.0
    assert player_attrs["calibration_skill"]["min"] == 0.0
    assert player_attrs["calibration_skill"]["max"] == 10.0
    assert player_attrs["shift_minutes"]["value"] == 0.0
    npc_attrs = _comp(result, RESPONDER, ATTRIBUTES)
    assert npc_attrs["attentiveness"]["value"] == 5.0


def test_a2_tick0_inventory_authoritative_entity_ids():
    """inventory 引用解析 = authoritative entity ID（非 slug 第二身份）。"""
    result = _fresh()
    assert _comp(result, OPERATOR, INVENTORY)["items"] == ["ent_authoring_gauge", "ent_authoring_kit"]
    assert _comp(result, RESPONDER, INVENTORY)["items"] == ["ent_authoring_kit"]
    for ref in _comp(result, OPERATOR, INVENTORY)["items"]:
        assert _world(result).has_entity(EntityId(ref))


def test_a3_tick0_item_state_and_properties():
    result = _fresh()
    gauge_item = _comp(result, GAUGE, ITEM)
    assert gauge_item["object_type"] == "instrument"
    assert gauge_item["state"] == "calibrated"
    assert gauge_item["properties"] == {"scale_max": 100.0, "bias": 1.5}
    kit_item = _comp(result, KIT, ITEM)
    # 最小字段面：state=None / properties={} → 键缺席（确定性空值行为）。
    assert set(kit_item) == {"name", "description", "object_type"}


# —— a4：自定义 executor + 纯 solver（production 绑定）——


def test_a4_executor_solver_component_write():
    result = _fresh()
    r = result.engine.submit_action(OPERATOR, "adjust_reading", {"delta": 2.5})
    assert r.ok, r.diagnostics
    assert _num(_comp(result, GAUGE, GAUGE_READING), "value") == 2.5
    committed = [t for t in r.transactions if t.status.name == "COMMITTED"]
    assert len(committed) == 1 and len(committed[0].effects) == 1
    # solver 夹取：上界来自 tick-0 item 组件 properties.scale_max（作者数据）。
    r2 = result.engine.submit_action(OPERATOR, "adjust_reading", {"delta": 9999.0})
    assert r2.ok, r2.diagnostics
    assert _num(_comp(result, GAUGE, GAUGE_READING), "value") == 100.0


# —— a5：一次动作 → 多 ProposedEffect（多实体 + 组件域 + state domain）——


def test_a5_multi_effect_action():
    result = _fresh()
    r = result.engine.submit_action(OPERATOR, "multi_write", {})
    assert r.ok, r.diagnostics
    committed = [t for t in r.transactions if t.status.name == "COMMITTED"]
    total_effects = sum(len(t.effects) for t in committed)
    assert total_effects == 3
    assert _num(_comp(result, GAUGE, GAUGE_READING), "value") == 10.0
    assert _comp(result, OPERATOR, ATTRIBUTES)["shift_minutes"]["value"] == 30.0
    # calibration_skill 不被整体替换覆盖（attributes 组件全量重写真值保留）。
    assert _comp(result, OPERATOR, ATTRIBUTES)["calibration_skill"]["value"] == 6.0
    assert _world(result).world_variables.get("audit") == "multi_write"


# —— a6：failure 路径 → 零效果 + 世界零变更（字节面）——


def test_a6_failure_path_zero_state_change():
    result = _fresh()
    # 无锁分支：ok + 世界变量写入（确定性分支两向）。
    r0 = result.engine.submit_action(OPERATOR, "fail_when_locked", {})
    assert r0.ok, r0.diagnostics
    assert _world(result).world_variables.get("last_action") == "fail_when_locked_ok"
    # 上锁 → 确定性 failure：诊断显式 + 世界字节不变 + revision 不变。
    r1 = result.engine.submit_action(OPERATOR, "set_lock", {})
    assert r1.ok, r1.diagnostics
    pre = dump_json(_world(result))
    pre_rev = int(_world(result).world_revision)
    r2 = result.engine.submit_action(OPERATOR, "fail_when_locked", {})
    assert not r2.ok
    assert any("lock" in d for d in r2.diagnostics), r2.diagnostics
    assert dump_json(_world(result)) == pre
    assert int(_world(result).world_revision) == pre_rev


# —— a7–a10：dynamics production 绑定 + state-domain 写面 ——


def test_a7_dynamics_component_write():
    result = _fresh()
    assert _num(_comp(result, GAUGE, GAUGE_READING), "value") in (None, 0.0)
    result.engine.advance(1)
    assert _num(_comp(result, GAUGE, GAUGE_READING), "value") == 0.1
    result.engine.advance(1)
    assert _num(_comp(result, GAUGE, GAUGE_READING), "value") == 0.2


def test_a8_state_domain_grant_world_variable_write():
    """dynamics 经 grant 写 world_variables（M2 domain_tag 选择器面）。"""
    result = _fresh()
    assert "world_time_s" not in _world(result).world_variables
    r = result.engine.advance(1)
    assert r.ok, r.diagnostics
    assert _world(result).world_variables.get("world_time_s") == 1.0


def test_a9_world_time_increment_depends_on_world_state():
    """Δ世界时间 = f(当前 WorldState)：time_scale 经授权动作改写后增量随之变。"""
    result = _fresh()
    result.engine.advance(1)
    t1 = _world(result).world_variables["world_time_s"]
    r = result.engine.submit_action(OPERATOR, "set_time_scale", {"scale": 3.0})
    assert r.ok, r.diagnostics
    result.engine.advance(1)
    t2 = _world(result).world_variables["world_time_s"]
    assert t1 == 1.0 and t2 == 4.0
    assert (t2 - t1) / (t1 - 0.0) == pytest.approx(3.0, abs=1e-6)


def test_a10_scenario_write_via_grant():
    result = _fresh()
    result.engine.advance(1)
    s1 = _world(result).scenario_state
    assert s1.stage == "running"
    assert s1.data.get("ticks") is not None
    result.engine.advance(1)
    s2 = _world(result).scenario_state
    assert s2.data["ticks"] > s1.data["ticks"]  # 单调推进（相位偏移无关断言）


# —— a11：无授权 producer → deny + 世界零变更 ——


def test_a11_ungranted_producer_denied_world_unchanged():
    result = _fresh()
    pre = dump_json(_world(result))
    pre_rev = int(_world(result).world_revision)
    r = result.engine.submit_action(OPERATOR, "ungranted_write", {})
    assert not r.ok
    assert any("authority" in d for d in r.diagnostics), r.diagnostics
    assert dump_json(_world(result)) == pre
    assert int(_world(result).world_revision) == pre_rev


# —— a12：deterministic replay-by-input（双独立装配 + 同输入序列）——


def _input_sequence(result) -> None:
    _run_seq(
        result,
        [
            ("adjust_reading", {"delta": 2.5}),
            ("multi_write", {}),
            ("set_time_scale", {"scale": 3.0}),
            ("fail_when_locked", {}),
        ],
        ticks=3,
    )
    result.engine.submit_action(OPERATOR, "set_lock", {})
    result.engine.submit_action(OPERATOR, "fail_when_locked", {})
    result.engine.advance(1)


def test_a12_deterministic_double_run_byte_equal():
    r_a, r_b = _fresh(), _fresh()
    _input_sequence(r_a)
    _input_sequence(r_b)
    assert dump_json(_world(r_a)) == dump_json(_world(r_b))


# —— a13：production 链零 tests 依赖（AST 字面 + sys.modules 双查）——


def _imports_of(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.append(node.module or "")
    return names


def test_a13_production_chain_zero_tests_import():
    targets = sorted(RUNTIME_DIR.glob("*.py")) + [RUNNER_SCRIPT]
    assert all(t.exists() for t in targets), f"缺文件：{[str(t) for t in targets if not t.exists()]}"
    offenders = {
        f"{t.name}:{n}"
        for t in targets
        for n in _imports_of(t)
        if n == "tests" or n.startswith("tests.")
    }
    assert not offenders, sorted(offenders)
    # 装配后 sys.modules 面：零 tests.* 载入（trust assembly 全链）。
    before = set(sys.modules)
    _fresh()
    leaked = {m for m in set(sys.modules) - before if m == "tests" or m.startswith("tests.")}
    assert not leaked, sorted(leaked)


# —— a14：扩展协议面零直写（frozen 数据面 + import 面双查）——


def test_a14_no_direct_write_surface():
    # ExecutorResult / WorldSnapshot 均为 frozen dataclass（不可变契约面）。
    assert dataclasses.is_dataclass(ExecutorResult)
    assert ExecutorResult.__dataclass_params__.frozen
    assert dataclasses.is_dataclass(WorldSnapshot)
    assert WorldSnapshot.__dataclass_params__.frozen
    snap_fields = dataclasses.fields(WorldSnapshot)
    assert {f.name for f in snap_fields} >= {"world_state", "world_revision", "logical_tick"}
    # 扩展 import 面：零 core 状态变更函数（K2 机械口）。
    ext_src = (FIXTURE_ROOT / "alpha_contract" / "extension.py").read_text(encoding="utf-8")
    tree = ast.parse(ext_src)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported |= {a.asname or a.name for a in node.names}
        elif isinstance(node, ast.Import):
            imported |= {a.asname or a.name for a in node.names}
    mutators = {"state_set_component", "state_remove_component", "state_set_world_variable",
                "state_remove_world_variable", "state_set_scenario_data",
                "state_create_entity", "state_remove_entity"}
    assert not (imported & mutators), sorted(imported & mutators)


# —— a15：alpha runner（M4.1）可跑通两个项目 ——
# 注：§0.3 黑名单禁 tests/engine_v2/ 用 subprocess（进程 IO 面）——
# runner 经 importlib 进程内加载 + main(argv) 直调（零 subprocess /
# 零网络；capsys 捕获 stdout 面）。


def _load_runner():
    import importlib.util

    spec = importlib.util.spec_from_file_location("v2_alpha_run", RUNNER_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a15_runner_runs_both_projects(capsys):
    runner = _load_runner()
    rc1 = runner.main(
        [
            "--root", str(FIXTURE_ROOT),
            "--action", "adjust_reading:ent_authoring_operator",
            "--ticks", "2",
        ]
    )
    out1 = capsys.readouterr().out
    assert rc1 == 0, out1
    assert "revision" in out1
    rc2 = runner.main(
        [
            "--root", str(REPO_ROOT / "examples" / "complex_minimal"),
            "--action", "inject_heat:ent_authoring_operator",
            "--ticks", "2",
        ]
    )
    out2 = capsys.readouterr().out
    assert rc2 == 0, out2
    assert "revision" in out2
