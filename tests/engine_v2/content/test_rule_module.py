"""rule_module v2 面测试（SOT §6.1 L744）：只测 v2 特有面，66 例 parity 不重复。

覆盖：§8.2 43 导出台账（序）；§5.2 断言 #12 AST 闭合（23 kind 闭集可产 +
Python 形 → LLMSIM_DSL_PARSE）；两阶段分离面（D-P5-DEV-3/6/7 结构错误、
parse 永不抛、path_label 透传）；DslRng 协议注入（runtime_checkable、同 seed
确定性、区间契约、rng=None 钉死错误）；resolve_variable 查找序（player 四层
fall-through、target 别名表、显式 None = 缺失、target=None 无法读取）；
action_text / resolve_target（id 直查 → 文本扫描 → location 回退、source
出处标记）；check_action_feasibility 项目规则面（(priority, id.casefold())
排序、disabled 过滤、warn+skip 与 re.error 静默 skip 分流）；内置 3/4 阈值
边界与概率钳制；模型 frozen/discriminator 契约。

hermetic：顶层平铺函数；零真实随机（seeded_rng 注入）；零网络。
"""

from __future__ import annotations

import logging

import pytest
from pydantic import ValidationError

import src.engine_v2.content.rule_module as rule_module
from src.engine_v2.content.rule_module import (
    DSL_NODE_KINDS,
    BUILTIN_RULE_IDS,
    ActionInput,
    ComparisonNode,
    DslContext,
    DslEvalError,
    DslParseResult,
    DslRng,
    Feasibility,
    FeasibilityNode,
    NumberNode,
    check_action_feasibility,
    evaluate_condition,
    parse_dsl,
    resolve_target,
    resolve_variable,
    tokenize_dsl,
)
from src.engine_v2.content.schemas import DiagnosticSeverity, RuleSpec

EXPECTED_ALL = [
    "DslRng",
    "DslToken",
    "tokenize_dsl",
    "DslNode",
    "DSL_NODE_KINDS",
    "IfChainNode",
    "ComparisonNode",
    "InTestNode",
    "NotInTestNode",
    "ContainsNode",
    "SubsetNode",
    "SupersetNode",
    "IntersectsNode",
    "DisjointNode",
    "TruthyNode",
    "AddNode",
    "SubNode",
    "MulNode",
    "DivNode",
    "NegNode",
    "NumberNode",
    "StringNode",
    "VariableNode",
    "FunctionCallNode",
    "FeasibilityNode",
    "AndNode",
    "OrNode",
    "NotNode",
    "DslParseResult",
    "DslEvalError",
    "Feasibility",
    "ConditionOutcome",
    "DslContext",
    "resolve_variable",
    "parse_dsl",
    "evaluate_condition",
    "ActionInput",
    "action_text",
    "resolve_target",
    "TargetRef",
    "FeasibilityResult",
    "check_action_feasibility",
    "BUILTIN_RULE_IDS",
]

EXPECTED_KINDS = frozenset(
    {
        "if_chain",
        "comparison",
        "in",
        "not_in",
        "contains",
        "subset",
        "superset",
        "intersects",
        "disjoint",
        "truthy",
        "add",
        "sub",
        "mul",
        "div",
        "neg",
        "number",
        "string",
        "variable",
        "function_call",
        "feasibility",
        "and",
        "or",
        "not",
    }
)

# 23 kind 全产 mega 表达式（每 kind ≥1 次；parse-only，不求值）。
_MEGA_EXPRESSION = (
    'if((a = "x" or b != 2) and not (c in tags) and d not in tags'
    " and e contains fighting and f subset g and h superset i"
    " and j intersects k and l disjoint m and n"
    " and (o + p - q) * (r / s) >= -t"
    " and rand() < 1 and rand(0, 1) < 1 and randint(1, 6) > 0"
    " and len(tags) > 1 and min(a, b) < max(c, d),"
    " if(a < 1, blocked; uncertain:0.2);"
    " allowed)"
)


def _collect_kinds(node) -> set:
    """model_dump 递归收集所有 kind 值（AST 闭合面检查用）。"""
    found: set = set()

    def _scan(obj) -> None:
        if isinstance(obj, dict) and "kind" in obj:
            found.add(obj["kind"])
            for value in obj.values():
                _scan(value)
        elif isinstance(obj, tuple):
            for item in obj:
                _scan(item)

    _scan(node.model_dump())
    return found


class _NoRng:
    """非 rand 面用例的注入占位：任何消费即断言失败（零随机面保证）。"""

    def rand(self) -> float:
        raise AssertionError("非 rand 面用例不得消费 rng")

    def uniform(self, lo: float, hi: float) -> float:
        raise AssertionError("非 rand 面用例不得消费 rng")

    def randint(self, lo: int, hi: int) -> int:
        raise AssertionError("非 rand 面用例不得消费 rng")


_NO_RNG = _NoRng()


def _action(description: str = "", action_type: str | None = None,
            target_object_id: str | None = None, speech: str = ""):
    return ActionInput(
        action_description=description,
        action_type=action_type,
        target_object_id=target_object_id,
        speech_content=speech,
    )


def _player(strength: float | None = None,
            body_width_cm: float | None = None,
            lockpicking: float | None = None) -> dict:
    profile: dict = {}
    if strength is not None:
        profile["strength"] = strength
    if body_width_cm is not None:
        profile["body_width_cm"] = body_width_cm
    skills: dict = {}
    if lockpicking is not None:
        skills["lockpicking"] = lockpicking
    return {"physical_profile": profile, "capabilities": {"skill_levels": skills}}


def test_all_43_names_in_ledger_order():
    # SOT §8.2 台账：43 名逐字按序（独立硬编码核验，不复用被测 __all__）
    assert rule_module.__all__ == EXPECTED_ALL
    assert len(rule_module.__all__) == 43
    for name in rule_module.__all__:
        assert callable(getattr(rule_module, name)) or isinstance(
            getattr(rule_module, name), (type, frozenset, tuple)
        )


def test_dsl_node_kinds_exact_23():
    assert isinstance(DSL_NODE_KINDS, frozenset)
    assert DSL_NODE_KINDS == EXPECTED_KINDS
    assert len(DSL_NODE_KINDS) == 23


def test_ast_closure_all_23_kinds_producible():
    # 断言 #12 闭合面正向：23 kind 全部可由 parse 产生且 ⊆ 闭集
    parsed = parse_dsl(_MEGA_EXPRESSION, "closure")
    assert parsed.ast is not None, parsed.diagnostics
    assert _collect_kinds(parsed.ast) == EXPECTED_KINDS


def test_ast_closure_rejects_pythonish_forms():
    # 断言 #12 闭合面反向：Python 形 → 结构诊断（parse 永不抛）
    for expression in ("while (x) { ... }", "def f(): ...", "lambda x: x"):
        parsed = parse_dsl(expression, "closure")
        assert parsed.ast is None
        assert [d.code for d in parsed.diagnostics] == ["LLMSIM_DSL_PARSE"]


def test_parse_never_raises_on_garbage():
    garbage = (
        "",
        "!!",
        "if(",
        "if(a < 1, blocked)",
        "if(a < 1, blocked; allowed",
        "player.sanity < 30",
    )
    for expression in garbage:
        parsed = parse_dsl(expression, "surface/path")
        assert isinstance(parsed, DslParseResult)
        assert parsed.ast is None
        assert len(parsed.diagnostics) == 1
        diag = parsed.diagnostics[0]
        assert diag.code == "LLMSIM_DSL_PARSE"
        assert diag.severity == DiagnosticSeverity.ERROR
        assert diag.path == "surface/path"


def test_dev3_garbage_after_matched_branch():
    # D-P5-DEV-3：1 = 1 命中 → v1 运行时 _skip_until_if_end 跳过剩余分支、
    # 容忍该垃圾并返回 allowed；v2 parse 期解析全部分支 → 结构错误（v1
    # 消息逐字保留，v1 仅在垃圾恰好被解析到时抛同一消息）。
    parsed = parse_dsl("if(1 = 1, allowed; allowed allowed)", "dev3")
    assert parsed.ast is None
    assert len(parsed.diagnostics) == 1
    assert parsed.diagnostics[0].message == "预期 ')'，但得到 'allowed'"


def test_dev6_missing_trailing_is_parse_error():
    # D-P5-DEV-6：v1 仅在该分支为假（走到缺失的 else 需求）时于 evaluate
    # 期报「if(...) 缺少 else 输出」；命中时返回 blocked。v2 无条件 parse
    # 期结构错误（观测差异已登记 §8.4）。
    parsed = parse_dsl("if(a < 1, blocked)", "dev6")
    assert parsed.ast is None
    assert parsed.diagnostics[0].message == "if(...) 缺少 else 输出"


def test_dev7_uncertain_probability_must_be_number_literal():
    # D-P5-DEV-7：v1 允许 `uncertain:` 后任意算术表达式；v2 parse 生产 =
    # 数字字面唯一 → 结构错误（新消息，v1 无此阶段）。
    parsed = parse_dsl("if(a < 1, uncertain: p + 0.1; allowed)", "dev7")
    assert parsed.ast is None
    assert parsed.diagnostics[0].message == "uncertain 概率必须是数字字面"


def test_uncertain_probability_range_validated():
    for probability in ("0", "1.5"):
        expression = f"if(a < 1, uncertain:{probability}; allowed)"
        parsed = parse_dsl(expression, "range")
        assert parsed.ast is None
        assert parsed.diagnostics[0].message == "uncertain 概率必须在 0 和 1 之间"


def test_tokenize_dsl_verbatim():
    tokens = tokenize_dsl("if(player.sanity < 40, blocked; allowed)")
    assert [(t.kind, t.value) for t in tokens] == [
        ("name", "if"),
        ("op", "("),
        ("name", "player.sanity"),
        ("op", "<"),
        ("number", "40"),
        ("op", ","),
        ("name", "blocked"),
        ("op", ";"),
        ("name", "allowed"),
        ("op", ")"),
    ]
    with pytest.raises(DslEvalError, match="无法解析条件表达式片段"):
        tokenize_dsl("if(x < @ 1, allowed; blocked)")


def test_uncertain_default_half_applied_at_eval():
    # 裸 uncertain → 节点 probability=None；0.5 在 evaluate 期施加（SOT §3.5 L387
    # FeasibilityNode probability 可 None + v1 condition_eval.py:293-294 裸 uncertain → 0.5）
    parsed = parse_dsl("if(a < 1, uncertain; allowed)", "default")
    assert parsed.ast is not None
    branch_outcome = parsed.ast.branches[0][1]
    assert isinstance(branch_outcome, FeasibilityNode)
    assert branch_outcome.probability is None
    outcome = evaluate_condition(
        parsed.ast, DslContext(variables={"a": 0.5}), _NO_RNG
    )
    assert outcome.feasibility == Feasibility.UNCERTAIN
    assert outcome.probability == 0.5


def test_feasibility_enum_str_values():
    assert Feasibility.ALLOWED == "allowed"
    assert Feasibility.BLOCKED == "blocked"
    assert Feasibility.UNCERTAIN == "uncertain"
    assert Feasibility("uncertain") is Feasibility.UNCERTAIN


def test_frozen_models_reject_assignment():
    context = DslContext(player={"a": 1})
    with pytest.raises(ValidationError):
        context.player = {}
    node = NumberNode(kind="number", value=1.0)
    with pytest.raises(ValidationError):
        node.value = 2.0


def test_node_kind_discriminator_enforced():
    node = NumberNode(kind="number", value=1.5)
    assert node.kind == "number"
    assert node.value == 1.5
    with pytest.raises(ValidationError):
        NumberNode(kind="string", value=1.5)


def test_evaluate_root_must_be_if_chain():
    root = ComparisonNode(
        kind="comparison",
        op="<",
        left=NumberNode(kind="number", value=1.0),
        right=NumberNode(kind="number", value=2.0),
    )
    with pytest.raises(DslEvalError, match="根节点必须为 if_chain"):
        evaluate_condition(root, DslContext(), _NO_RNG)


def test_and_or_eager_right_operand_evaluates():
    """and/or 急进求值钉死（SOT §3.5 L391 evaluate_condition 急进遍历，
    与 v1 parse+eval 融合行为等价，v1 condition_eval.py:100-112）：右操作数
    无条件求值、异常原样上抛（左假 and / 左真 or 均不短路）；异常序左先行
    （左操作数抛错时右不求值）。"""

    def _eval(expr: str):
        parsed = parse_dsl(expr, "eager")
        assert parsed.ast is not None
        return evaluate_condition(parsed.ast, DslContext(), _NO_RNG)

    # ① and 左假不短路：右操作数未知变量上抛
    with pytest.raises(DslEvalError, match="未知变量 player.missing"):
        _eval("if(0 > 1 and player.missing > 0, allowed; blocked)")
    # ② or 左真不短路：右操作数未知变量上抛
    with pytest.raises(DslEvalError, match="未知变量 player.missing"):
        _eval("if(1 > 0 or player.missing > 0, allowed; blocked)")
    # ③ and 左假不短路：右操作数除零上抛
    with pytest.raises(DslEvalError, match="条件表达式中出现除零"):
        _eval("if(0 > 1 and 1/0 > 0, allowed; blocked)")
    # ④ or 左真不短路：右操作数除零上抛
    with pytest.raises(DslEvalError, match="条件表达式中出现除零"):
        _eval("if(1 > 0 or 1/0 > 0, allowed; blocked)")
    # ⑤ 左先行序：左操作数抛未知变量时右操作数除零不求值（不得为除零消息）
    with pytest.raises(DslEvalError, match="未知变量 player.missing"):
        _eval("if(player.missing > 0 and 1/0 > 0, allowed; blocked)")
    # ⑥ 正常真值表 sanity
    assert _eval("if(1 > 0 and 2 > 1, allowed; blocked)").feasibility == Feasibility.ALLOWED
    assert _eval("if(0 > 1 or 0 > 2, allowed; blocked)").feasibility == Feasibility.BLOCKED


def test_resolve_variable_player_lookup_order():
    context = DslContext(
        player={
            "attributes": {"hp": {"value": 35}},
            "physical_profile": {"strength": 2.0},
            "capabilities": {"skill_levels": {"lockpicking": 0.4}},
            "mood": "calm",
        }
    )
    assert resolve_variable("player.hp", context) == 35
    assert resolve_variable("player.strength", context) == 2.0
    assert resolve_variable("player.lockpicking", context) == 0.4
    assert resolve_variable("player.mood", context) == "calm"
    with pytest.raises(DslEvalError, match="未知变量 player.ghost"):
        resolve_variable("player.ghost", context)


def test_resolve_variable_player_attr_fallthrough():
    # 非 dict / 无 "value" 的 attributes 项 → 逐层 fall-through（v1 口径）
    context = DslContext(
        player={
            "attributes": {"x": 5, "y": {"other": 1}},
            "physical_profile": {"x": 7.5},
        }
    )
    assert resolve_variable("player.x", context) == 7.5
    with pytest.raises(DslEvalError, match="未知变量 player.y"):
        resolve_variable("player.y", context)


def test_resolve_variable_target_lookup_and_aliases():
    context = DslContext(
        target={
            "properties": {
                "weight_kg": 120,
                "width": 33,
                "effective_width_cm": 44,
            },
            "label": "top",
        }
    )
    # 别名表：weight → weight_kg 优先；width → effective_width_cm 优先
    assert resolve_variable("target.weight", context) == 120
    assert resolve_variable("target.width", context) == 44
    assert resolve_variable("target.effective_width_cm", context) == 44
    assert resolve_variable("target.label", context) == "top"
    with pytest.raises(DslEvalError, match="未知变量 target.lock_difficulty"):
        resolve_variable("target.lock_difficulty", context)


def test_resolve_variable_target_none_unreadable():
    context = DslContext(target=None)
    with pytest.raises(DslEvalError, match="无法读取 target.weight"):
        resolve_variable("target.weight", context)


def test_resolve_variable_free_name_none_is_missing():
    context = DslContext(variables={"known": 1, "empty": None})
    assert resolve_variable("known", context) == 1
    with pytest.raises(DslEvalError, match="未知变量 'empty'"):
        resolve_variable("empty", context)
    with pytest.raises(DslEvalError, match="未知变量 'ghost'"):
        resolve_variable("ghost", context)


def test_action_text_join():
    action = ActionInput(
        raw_input="r",
        interpreted_intent="",
        action_description="d",
        speech_content="s",
    )
    assert rule_module.action_text(action) == "r\nd\ns"
    assert rule_module.action_text(ActionInput()) == ""


def test_resolve_target_id_direct_and_width_source():
    objects = {
        "table": {
            "id": "tbl",
            "name": "长餐桌",
            "properties": {"effective_width_cm": 42.0, "width_cm": 41.0},
        }
    }
    ref = resolve_target(_action("推桌子", target_object_id="table"), objects, {})
    # 内容相等（frozen 模型校验期对可变容器做防御性拷贝，身份非契约面）
    assert ref.object == objects["table"]
    assert ref.width_cm == 42.0  # effective_width_cm 优先
    assert ref.source == "object:table"  # source = objects 映射键

    # 非 dict 值被过滤（v2 类型面；v1 原样返回）
    ref = resolve_target(_action("推桌子", target_object_id="bad"), {"bad": 42}, {})
    assert ref.object is None
    assert ref.width_cm is None
    assert ref.source is None


def test_resolve_target_text_scan_and_location_fallback():
    objects = {
        "first": {"id": "f1", "name": "甲", "properties": {}},
        "second": {"id": "s2", "name": "乙", "properties": {}},
    }
    locations = {
        "hall": {
            "id": "hall",
            "name": "走廊",
            "properties": {"width_cm": 60.0},
        }
    }
    ref = resolve_target(_action("我穿过乙的门"), objects, {})
    assert ref.object == objects["second"]  # name-in-text 首命中（映射序）

    ref = resolve_target(_action("走过走廊"), objects, locations)
    assert ref.object is None
    assert ref.width_cm == 60.0
    assert ref.source == "location:hall"


def test_resolve_target_no_match():
    ref = resolve_target(_action("发呆"), {}, {})
    assert ref.object is None
    assert ref.width_cm is None
    assert ref.source is None


def test_resolve_target_object_id_in_text_third_order():
    """resolve_target 第三序 object_id-in-text（SOT §6.1 L744 三序：
    id 直查 → name → object_id-in-text）：action 描述文本仅含 id 串
    （不含 name）→ 文本扫描命中该对象。v1 探针核验 v1 rules.py:49-51
    同输入行为（同一对象命中）→ v1/v2 等价钉死。"""
    objects = {
        "door": {
            "id": "door01",
            "name": "门",
            "properties": {"effective_width_cm": 80.0},
        },
        "table": {
            "id": "tbl9",
            "name": "桌",
            "properties": {"width_cm": 42.0},
        },
    }
    assert "门" not in "推 door01 一下"  # 文本仅含 id 串，不含 name
    ref = resolve_target(_action("推 door01 一下"), objects, {})
    assert ref.object == objects["door"]  # name 未命中，object_id-in-text 命中
    assert ref.width_cm == 80.0
    assert ref.source == "object:door"


def test_dsl_rng_protocol_runtime_checkable():
    class _PartialRng:
        def rand(self) -> float:
            return 0.5

    assert isinstance(_PartialRng(), object)
    assert not isinstance(_PartialRng(), DslRng)  # 缺 uniform/randint


def test_seeded_rng_intervals_and_determinism(seeded_rng):
    rng_a, rng_b = seeded_rng(7), seeded_rng(7)
    assert [rng_a.rand() for _ in range(500)] == [
        rng_b.rand() for _ in range(500)
    ]
    rng = seeded_rng(1)
    for _ in range(500):
        assert 0.0 <= rng.rand() < 1.0
        assert 2.0 <= rng.uniform(2.0, 3.0) <= 3.0
        assert 1 <= rng.randint(1, 6) <= 6
    assert rng.randint(1, 1) == 1


def test_rand_family_without_rng_raises():
    # rng=None + rand 族 → DslEvalError（SOT §3.5 L391 必填 rng；v1 用模块级全局
    # 随机源，condition_eval.py:4）
    parsed = parse_dsl("if(rand() < 1, blocked; allowed)", "rng")
    assert parsed.ast is not None
    with pytest.raises(DslEvalError, match="rand 族函数需要注入 DslRng"):
        evaluate_condition(parsed.ast, DslContext(), None)


def test_check_feasibility_rand_condition_without_rng_warns_and_skips(caplog):
    rules = (
        RuleSpec(
            id="lucky",
            description="随机门",
            condition="if(rand() < 1, blocked; allowed)",
        ),
    )
    with caplog.at_level(logging.WARNING, logger="src.engine_v2.content.rule_module"):
        result = check_action_feasibility(
            rules, _action("观察"), DslContext(), {}, {}
        )
    assert result is None  # 永不抛；失效条件 → skip
    assert any("deterministic rule 'lucky' condition failed" in rec.message
               for rec in caplog.records)


def test_custom_rule_sort_priority_then_id_casefold():
    # id 由 RuleSpec 模式锁死小写，casefold 为防御面；此处验证同 priority
    # 按 id 字典序（apple < zed）定序。
    base = [
        RuleSpec(id="zed", description="z", match="观察", feasibility="blocked",
                 priority=50),
        RuleSpec(id="apple", description="a", match="观察", feasibility="allowed",
                 priority=50),
        RuleSpec(id="mid", description="m", match="观察", feasibility="blocked",
                 priority=10),
    ]
    action = _action("观察房间")
    result = check_action_feasibility(tuple(base), action, DslContext(), {}, {})
    assert result is not None
    assert result.matched_rule == "custom:mid"  # priority 10 最小者优先

    # disabled frozenset 按内置 ID 门禁内置规则，不作用于项目规则
    result = check_action_feasibility(
        tuple(base), action, DslContext(), {}, {}, disabled=frozenset({"apple"})
    )
    assert result is not None
    assert result.matched_rule == "custom:mid"

    # mid 经 RuleSpec.disabled 字段禁用 → 同 priority 50 按 id：apple < zed
    mid_disabled = [
        rule.model_copy(update={"disabled": True}) if rule.id == "mid" else rule
        for rule in base
    ]
    result = check_action_feasibility(tuple(mid_disabled), action, DslContext(), {}, {})
    assert result is not None
    assert result.matched_rule == "custom:apple"


def test_custom_invalid_condition_warns_and_skips(caplog):
    # 失效条件分流：parse 诊断 / DslEvalError → 同一 warn 格式 + skip，
    # 内置规则继续（v1 口径逐字；本层不产 Diagnostic）
    objects = {
        "table": {
            "id": "table",
            "name": "长餐桌",
            "properties": {"weight_kg": 120.0},
        }
    }
    rules = (
        RuleSpec(
            id="bad_condition",
            description="坏条件",
            condition="if(player.missing < 1, blocked; allowed)",
        ),
    )
    action = _action("把长餐桌推到墙边", "interact", "table")
    with caplog.at_level(logging.WARNING, logger="src.engine_v2.content.rule_module"):
        result = check_action_feasibility(
            rules, action, DslContext(player=_player(strength=2.0)), objects, {}
        )
    assert result is not None
    assert result.matched_rule == "strength_vs_weight"
    assert [rec.message for rec in caplog.records] == [
        "deterministic rule 'bad_condition' condition failed: 未知变量 player.missing"
    ]


def test_custom_invalid_regex_silently_skipped(caplog):
    # re.error 分流：静默 skip（无日志、无诊断——SOT「无诊断」口径）
    objects = {
        "table": {
            "id": "table",
            "name": "长餐桌",
            "properties": {"weight_kg": 120.0},
        }
    }
    rules = (
        RuleSpec(id="bad_regex", description="坏正则", match="[",
                 feasibility="blocked"),
    )
    action = _action("把长餐桌推到墙边", "interact", "table")
    with caplog.at_level(logging.WARNING, logger="src.engine_v2.content.rule_module"):
        result = check_action_feasibility(
            rules, action, DslContext(player=_player(strength=2.0)), objects, {}
        )
    assert result is not None
    assert result.matched_rule == "strength_vs_weight"
    assert caplog.records == []


def test_custom_uncertain_result_fields():
    rules = (
        RuleSpec(
            id="gated",
            description="条件门",
            condition="if(a < 1, uncertain:0.42; allowed)",
        ),
    )
    context = DslContext(player={}, target=None, variables={"a": 0.5})
    result = check_action_feasibility(
        rules, _action("观察"), context, {}, {}
    )
    assert result is not None
    assert result.feasibility == Feasibility.UNCERTAIN
    assert result.success_probability == 0.42
    assert result.requires_roll is True
    assert result.matched_rule == "custom:gated"
    assert "gated" in result.reason


def test_custom_rule_match_and_condition_both_required(caplog):
    """custom 规则流 regex+condition 双命中（SOT §6.1 L744）：同一 RuleSpec
    同时携带 match（regex）与 condition（DSL）→ 双命中规则才生效。三向矩阵：
    双命中 → matched_rule=custom:<id>；condition 不命中（求值失败）→
    warn+skip 该规则不命中、落回内置；match 不命中 → 该规则不命中（无内置
    并存 → None）。v1 探针核验（v1 deterministic rules 同输入，逐字段等值）：
    双命中 → blocked/系统规则预判（storm_heavy_lift）：暴风中搬运重物/
    custom:storm_heavy_lift/None/False（v1 rules.py:105-111）；condition
    不命中 → warn + strength_vs_weight 落回（v1 rules.py:102-104）；match
    不命中 → None（v1 rules.py:140-141）。v1/v2 等价钉死。"""
    objects = {
        "banquet_table": {
            "id": "banquet_table",
            "name": "长餐桌",
            "properties": {"weight_kg": 120.0},
        }
    }
    player = {
        "attributes": {"sanity": {"value": 35}, "storm_tolerance": {"value": 45}},
        "physical_profile": {"strength": 0.4, "body_width_cm": 60.0},
        "capabilities": {
            "blocked_common_actions": [],
            "allowed_extraordinary_actions": [],
            "skill_levels": {"lockpicking": 0.2},
        },
    }
    rules = (
        RuleSpec(
            id="storm_heavy_lift",
            description="暴风中搬运重物",
            match="搬运|推动|抬起",
            condition="if(player.storm_tolerance < 50, blocked; allowed)",
        ),
    )
    context = DslContext(player=player)

    # ① 双命中：regex 命中 ∧ condition guard 命中（45 < 50）→ 规则生效，
    # 并存内置（interact+120kg，20kg<120kg）不被采用
    hit = check_action_feasibility(
        rules, _action("推动长餐桌", "interact", "banquet_table"), context, objects, {}
    )
    assert hit is not None
    assert hit.feasibility == Feasibility.BLOCKED
    assert hit.reason == "系统规则预判（storm_heavy_lift）：暴风中搬运重物"
    assert hit.matched_rule == "custom:storm_heavy_lift"
    assert hit.success_probability is None
    assert hit.requires_roll is False

    # ② condition 不命中（求值失败）→ warn+skip：regex 虽命中该规则仍不生效，
    # 落回内置（v1 rules.py:102-104 逐字口径）
    ghost_rules = (
        RuleSpec(
            id="ghost_rule",
            description="幽灵条件",
            match="搬运|推动|抬起",
            condition="if(player.ghost < 1, blocked; allowed)",
        ),
    )
    with caplog.at_level(logging.WARNING, logger="src.engine_v2.content.rule_module"):
        cond_miss = check_action_feasibility(
            ghost_rules, _action("推动长餐桌", "interact", "banquet_table"),
            context, objects, {},
        )
    assert cond_miss is not None
    assert cond_miss.matched_rule == "strength_vs_weight"  # 该规则不命中，落回内置
    assert [rec.message for rec in caplog.records] == [
        "deterministic rule 'ghost_rule' condition failed: 未知变量 player.ghost"
    ]

    # ③ match 不命中：regex 未命中 action 文本 → 该规则不命中（observe 无
    # 内置并存 → None；v1 rules.py:140-141 口径）
    match_miss = check_action_feasibility(
        rules, _action("观察长餐桌", "observe", "banquet_table"), context, objects, {}
    )
    assert match_miss is None


def test_custom_rule_priority_over_builtin():
    """custom 规则流优先级 custom > builtin（SOT §6.1 L744）：custom 规则
    （合法 match+condition 双命中）与命中内置规则并存 → matched_rule =
    custom id（项目规则先于内置 1..5 求值，v1 rules.py:139-144 custom 循环
    先于 :146+ 内置；v1 用例口径 tests/test_rules.py:196/:220/:290）。变体：
    custom 不命中（regex 不命中）→ 落回内置规则 id（v1 rules.py:140-141
    skip → :169-187 内置）。v1 探针核验同输入逐字段等值：
    custom:storm_heavy_lift/blocked/系统规则预判（storm_heavy_lift）：暴风中
    搬运重物/None/False；strength_vs_weight/blocked/系统规则预判：玩家力量
    约可移动 20.0kg，但目标物体重约 120.0kg。/None/False。v1/v2 等价钉死。"""
    objects = {
        "banquet_table": {
            "id": "banquet_table",
            "name": "长餐桌",
            "properties": {"weight_kg": 120.0},
        }
    }
    player = {
        "attributes": {"sanity": {"value": 35}, "storm_tolerance": {"value": 45}},
        "physical_profile": {"strength": 0.4, "body_width_cm": 60.0},
        "capabilities": {
            "blocked_common_actions": [],
            "allowed_extraordinary_actions": [],
            "skill_levels": {"lockpicking": 0.2},
        },
    }
    rules = (
        RuleSpec(
            id="storm_heavy_lift",
            description="暴风中搬运重物",
            match="搬运|推动|抬起",
            condition="if(player.storm_tolerance < 50, blocked; allowed)",
        ),
    )
    context = DslContext(player=player)

    # custom 双命中 ∧ 内置并存（interact+120kg，strength 0.4 → 20kg < 120kg）
    # → custom 优先
    custom_win = check_action_feasibility(
        rules, _action("推动长餐桌", "interact", "banquet_table"), context, objects, {}
    )
    assert custom_win is not None
    assert custom_win.matched_rule == "custom:storm_heavy_lift"
    assert custom_win.feasibility == Feasibility.BLOCKED
    assert custom_win.reason == "系统规则预判（storm_heavy_lift）：暴风中搬运重物"
    assert custom_win.success_probability is None
    assert custom_win.requires_roll is False

    # 变体：custom regex 不命中（"移动" ∉ 搬运|推动|抬起）→ 落回内置规则 id
    builtin_fallback = check_action_feasibility(
        rules, _action("移动长餐桌", "interact", "banquet_table"), context, objects, {}
    )
    assert builtin_fallback is not None
    assert builtin_fallback.matched_rule == "strength_vs_weight"
    assert builtin_fallback.feasibility == Feasibility.BLOCKED
    assert builtin_fallback.reason == (
        "系统规则预判：玩家力量约可移动 20.0kg，但目标物体重约 120.0kg。"
    )
    assert builtin_fallback.success_probability is None
    assert builtin_fallback.requires_roll is False


def test_builtin_rule_ids_verbatim():
    assert BUILTIN_RULE_IDS == (
        "blocked_common",
        "extraordinary",
        "strength_vs_weight",
        "skill_vs_lock",
        "body_width_vs_passage",
    )


def test_builtin_strength_boundaries():
    objects = {
        "table": {
            "id": "table",
            "name": "长餐桌",
            "properties": {"weight_kg": 120.0},
        }
    }
    action = _action("推长餐桌", "interact", "table")

    def _run(strength: float):
        return check_action_feasibility(
            (), action, DslContext(player=_player(strength=strength)), objects, {}
        )

    blocked = _run(2.0)  # 100 < 120 → blocked
    assert blocked is not None
    assert blocked.feasibility == Feasibility.BLOCKED

    close = _run(2.4)  # 120 ≥ 120 且 < 180 → uncertain，p = 120/180
    assert close is not None
    assert close.feasibility == Feasibility.UNCERTAIN
    assert close.success_probability == 120.0 / 180.0
    assert close.requires_roll is True

    near = _run(3.0)  # 150 < 180 → uncertain，p = 150/180
    assert near is not None
    assert near.success_probability == 150.0 / 180.0

    assert _run(4.0) is None  # 200 ≥ 180 → 规则不出结果


def test_builtin_lock_probability_clamps():
    objects = {
        "lock": {
            "id": "lock",
            "name": "门锁",
            "properties": {"lock_difficulty": 0.8},
        }
    }
    action = _action("开门锁", "interact", "lock")

    weak = check_action_feasibility(
        (), action, DslContext(player=_player(lockpicking=0.01)), objects, {}
    )
    assert weak is not None
    assert weak.feasibility == Feasibility.UNCERTAIN
    assert weak.success_probability == 0.05  # 0.0125 钳制到 0.05
    assert weak.requires_roll is True

    strong = check_action_feasibility(
        (), action, DslContext(player=_player(lockpicking=0.9)), objects, {}
    )
    assert strong is not None
    assert strong.feasibility == Feasibility.ALLOWED
    assert strong.success_probability is None
    assert strong.requires_roll is False
