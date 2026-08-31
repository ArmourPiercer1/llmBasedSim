"""P5 对抗测试：SOT §6.3 对抗表 A1–A13（L769-786）落面。

落点分配（A11/A12 预裁定口径，本文件 docstring 首段记录）：

- **A1**（duplicated ID）/ **A2**（missing entity）/ **A3**（stale revision）/
  **A4**（conflicting effects）/ **A5**（circular module dependency）/
  **A10**（unauthorized context access = DSL 未定义变量）/ **A13**（DSL 含
  def/while）→ 本文件 7 个扁平测试函数；
- **A6**（event loop）= **N/A**：P5 无事件面，事件循环归 P6 runtime——P5 面
  零事件概念，无落点可对抗（§6.3 A6 行原文）；
- **A7**（invalid mode merge）→ ``test_validator``（§6.3 A7 行测试列：
  test_rule_module 外置 → test_validator；LLMSIM_SCHEMA pydantic 层）；
- **A8**（non-checkpointable backend branch）= **N/A**（P8 状态快照面）：P5
  侧镜像保证 = ProjectIR 全数据态可序列化，镜像落在 W2 ``test_project_ir``
  （非本文件）；
- **A9**（out-of-order async result）= **N/A**（D-P5-15：P5 零 asyncio）：
  静态面由 Leader 的 TestP5Boundary（test_import_boundary.py）覆盖；
- **A11**（rogue .py in plugins/）→ 门场景断言 #7（test_p5_gate_scenario，
  动态全链 + sys.modules 面）；
- **A12**（K8 探针字段名位于 fixture #38 player.capabilities）→ 门场景断言
  #19a + fixture #38（K8 探针表 P1 面）。
"""

from __future__ import annotations

import logging

import pytest

from src.engine_v2.content.loader import load_project
from src.engine_v2.content.project_ir import build_ir
from src.engine_v2.content.rule_module import (
    BUILTIN_RULE_IDS,
    DslContext,
    DslEvalError,
    ActionInput,
    check_action_feasibility,
    evaluate_condition,
    parse_dsl,
)
from src.engine_v2.content.validator import validate_project
from tests.engine_v2.content.conftest import (
    make_authority_policy,
    make_ir,
    make_item,
    make_location,
    make_module_node,
    make_player,
    make_rule_spec,
    make_world,
)


def test_a1_duplicated_id_one_diagnostic_exact_refs(broken_project) -> None:
    """A1：duplicated ID → 每重复 id 恰 1 条 LLMSIM_DUPLICATE_ID（refs 精确）。

    refs = [id, 首次出现索引, 重复出现索引]（池 tuple 内 0-based、字符串化）。
    双落面：fixture #39（broken world/dup_world.yaml 双 dup_room）+ 合成 items 池。
    """
    loaded = load_project(broken_project)
    assert loaded.raw is not None
    built = build_ir(loaded.raw)
    assert built.ir is not None
    result = validate_project(built.ir, loaded.raw)
    dups = [d for d in result.diagnostics if d.code == "LLMSIM_DUPLICATE_ID"]
    assert len(dups) == 1
    dup = dups[0]
    assert dup.path == "locations"
    assert dup.refs == ("dup_room", "0", "1")

    synthetic = make_ir(
        items=(make_item(id="item_x"), make_item(id="item_x")),
    )
    result2 = validate_project(synthetic)
    dups2 = [d for d in result2.diagnostics if d.code == "LLMSIM_DUPLICATE_ID"]
    assert len(result2.diagnostics) == 1
    assert dups2[0].path == "items"
    assert dups2[0].refs == ("item_x", "0", "1")


def test_a2_missing_entity_refs() -> None:
    """A2：missing entity → 悬空 connection / inventory 引用各 1 条 UNRESOLVED_REF。"""
    ir = make_ir(
        world=make_world(
            locations=(make_location(id="loc_a", connections={"east": "ghost_loc"}),),
        ),
        player=make_player(inventory=["ghost_item"]),
    )
    result = validate_project(ir)
    refs = [d for d in result.diagnostics if d.code == "LLMSIM_UNRESOLVED_REF"]
    assert len(result.diagnostics) == 2
    assert len(refs) == 2
    assert refs[0].path == "loc_a"
    assert refs[0].refs == ("connection", "ghost_loc")
    assert refs[1].path == "player_1"
    assert refs[1].refs == ("inventory", "ghost_item")


def test_a3_stale_revision_module_version() -> None:
    """A3：stale revision → requires 版本 > 目标声明版本 → MODULE_VERSION（需求方 path）。"""
    ir = make_ir(
        modules=(
            make_module_node(id="mod.new", version="2.0.0", requires=("mod.old >= 3.0.0",)),
            make_module_node(id="mod.old", version="2.0.0"),
        )
    )
    result = validate_project(ir)
    stale = [d for d in result.diagnostics if d.code == "LLMSIM_MODULE_VERSION"]
    assert len(result.diagnostics) == 1
    assert len(stale) == 1
    assert stale[0].path == "mod.new"
    assert stale[0].refs == ("mod.old:>=3.0.0", "have 2.0.0")


def test_a4_conflicting_effects() -> None:
    """A4：conflicting effects → 声明域重叠 AUTHORITY_CONFLICT 1 + 模块互指 MODULE_CONFLICT 1。"""
    ir = make_ir(
        authority=(
            make_authority_policy(id="auth.a", owner="core.x"),
            make_authority_policy(id="auth.b", owner="core.y"),
        ),
        modules=(
            make_module_node(id="mod.a", conflicts=("mod.b",)),
            make_module_node(id="mod.b", conflicts=("mod.a",)),
        ),
    )
    result = validate_project(ir)
    assert len(result.diagnostics) == 2
    auth = [d for d in result.diagnostics if d.code == "LLMSIM_AUTHORITY_CONFLICT"]
    conf = [d for d in result.diagnostics if d.code == "LLMSIM_MODULE_CONFLICT"]
    assert len(auth) == 1
    assert auth[0].path == "attributes.sanity"
    assert auth[0].refs == ("core.x", "core.y")
    assert len(conf) == 1
    assert conf[0].path == "mod.a"
    assert conf[0].refs == ("mod.a", "mod.b")


def test_a5_circular_module_dependency() -> None:
    """A5：circular module dependency → 恰 1 条 LLMSIM_MODULE_CYCLE（门场景 #9 同源镜像）。"""
    ir = make_ir(
        modules=(
            make_module_node(id="x.a", requires=("x.b",)),
            make_module_node(id="x.b", requires=("x.c",)),
            make_module_node(id="x.c", requires=("x.a",)),
        )
    )
    result = validate_project(ir)
    cycles = [d for d in result.diagnostics if d.code == "LLMSIM_MODULE_CYCLE"]
    assert len(cycles) == 1
    assert list(result.diagnostics) == cycles
    assert cycles[0].refs == ("x.a", "x.b", "x.c")
    assert cycles[0].path == "x.a"


def test_a10_undefined_dsl_variable(caplog) -> None:
    """A10：unauthorized context access → 未定义变量：evaluate_condition 抛
    DslEvalError；check_action_feasibility 层 warn+skip 不崩（v1 rules.py:102-104）。
    """
    expression = "if(ghost_var > 1, allowed; blocked)"
    parsed = parse_dsl(expression, "a10")
    assert parsed.ast is not None
    with pytest.raises(DslEvalError):
        evaluate_condition(parsed.ast, DslContext(), None)

    rule = make_rule_spec(id="rule_undef", condition=expression)
    with caplog.at_level(logging.WARNING, logger="src.engine_v2.content.rule_module"):
        result = check_action_feasibility(
            (rule,), ActionInput(raw_input="probe"), DslContext(), {}, {}
        )
    assert "deterministic rule 'rule_undef' condition failed" in caplog.text
    # skip 后内置规则继续；本输入（空 player / 空 objects / 空 locations）
    # 无内置规则命中 → None（零崩溃 = 永不抛）。
    assert result is None or result.matched_rule in BUILTIN_RULE_IDS


def test_a13_dsl_def_while_rejected() -> None:
    """A13：DSL 含 def/while → LLMSIM_DSL_PARSE（AST 无对应种类，#12 同源语料扩展）。"""
    corpus = ("def f(): pass", "while (x) {", "while a, b; c")
    for expression in corpus:
        parsed = parse_dsl(expression, "a13")
        assert parsed.ast is None, expression
        assert len(parsed.diagnostics) == 1, expression
        assert parsed.diagnostics[0].code == "LLMSIM_DSL_PARSE", expression
