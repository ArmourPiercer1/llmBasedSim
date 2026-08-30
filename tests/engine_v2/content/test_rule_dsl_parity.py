"""66 例 1:1 parity characterization 集（SOT §6.2、断言 #11；G5 门禁）。

来源：``tests/test_condition_eval.py``（41 例）+ ``tests/test_rules.py``（25 例）@
f0a1052。函数名与 v1 逐一同名（v1 ``TestTextMatchesRule`` 5 个类方法 → 顶层平铺
函数，名称不变）。等价口径：(feasibility, probability) 逐位相等（float 按
``==``）；check_action_feasibility 五键字段相等（v2 字段 ``reason`` 对应 v1
``feasibility_reason``）；no-match 保留 None。

映射表（v1 文件:行 → v2 函数 → 期望行为 → 备注）——66 行，逐例 1:1
（行号经 grep -n 核验与 SOT §6.2 清单一致）：

tests/test_condition_eval.py:32 test_simple_comparison_returns_blocked → (blocked, None)
tests/test_condition_eval.py:39 test_ifelse_chain_returns_uncertain_with_probability → (uncertain, 0.4)
tests/test_condition_eval.py:46 test_arithmetic_and_target_weight_alias → (blocked, None)（target.weight→weight_kg）
tests/test_condition_eval.py:52 test_parentheses_and_precedence → (allowed, None)
tests/test_condition_eval.py:58 test_min_max_functions → (allowed, None)（min(35,70)=35 < max(20,30)=30 为假）
tests/test_condition_eval.py:64 test_skill_level_lookup → (uncertain, 0.25)（0.4<0.8）
tests/test_condition_eval.py:71 test_missing_variable_raises → v1 raise ⟺ v2 evaluate DslEvalError（语义：未知变量）
tests/test_condition_eval.py:76 test_division_by_zero_raises → v1 raise ⟺ v2 evaluate DslEvalError（语义：除零）
tests/test_condition_eval.py:81 test_invalid_syntax_raises → v1 raise（parse 期）⟺ v2 结构诊断 LLMSIM_DSL_PARSE
tests/test_condition_eval.py:86 test_invalid_outcome_raises → v1 raise（eval 期）⟺ v2 结构诊断（阶段差：v2 parse 期校验）
tests/test_condition_eval.py:91 test_uncertain_without_probability_defaults_to_half → (uncertain, 0.5)（裸 uncertain 缺省）
tests/test_condition_eval.py:132 test_and_operator → (blocked, None)
tests/test_condition_eval.py:139 test_and_operator_false → (allowed, None)
tests/test_condition_eval.py:146 test_or_operator → (blocked, None)
tests/test_condition_eval.py:153 test_not_operator → (blocked, None)
tests/test_condition_eval.py:160 test_compound_boolean → (blocked, None)（含前导值分组形，ERR-P5-11(5)）
tests/test_condition_eval.py:170 test_in_operator → (blocked, None)
tests/test_condition_eval.py:177 test_in_operator_false → (allowed, None)
tests/test_condition_eval.py:184 test_not_in_operator → (blocked, None)
tests/test_condition_eval.py:191 test_subset_operator → (allowed, None)
tests/test_condition_eval.py:199 test_subset_operator_true → (blocked, None)（自定义 ctx：仅 player.attributes）
tests/test_condition_eval.py:212 test_intersects_operator → (allowed, None)
tests/test_condition_eval.py:220 test_intersects_operator_true → (blocked, None)
tests/test_condition_eval.py:227 test_disjoint_operator → (blocked, None)
tests/test_condition_eval.py:235 test_contains_operator → (blocked, None)（自定义 ctx：仅 player.status_effects）
tests/test_condition_eval.py:245 test_len_function → (blocked, None)
tests/test_condition_eval.py:255 test_string_comparison_equals → (blocked, None)
tests/test_condition_eval.py:262 test_string_comparison_not_equals → (blocked, None)
tests/test_condition_eval.py:272 test_nested_if_as_branch_value → (allowed, None)（未命中分支 outcome 求值后丢弃，命中后其余分支不求值）
tests/test_condition_eval.py:279 test_nested_if_as_branch_value_matched → (blocked, None)（命中分支 outcome = 嵌套 if）
tests/test_condition_eval.py:286 test_nested_if_as_default → (allowed, None)（trailing = 嵌套 if）
tests/test_condition_eval.py:293 test_nested_if_deep → (uncertain, 0.5)（三层嵌套）
tests/test_condition_eval.py:305 test_set_and_bool_combined → (blocked, None)
tests/test_condition_eval.py:313 test_boolean_with_set → (blocked, None)
tests/test_condition_eval.py:324 test_in_with_nonlist_rhs_raises → v1 raise ⟺ v2 evaluate DslEvalError（语义：in 右值类型）
tests/test_condition_eval.py:329 test_subset_with_string_raises → v1 raise ⟺ v2 evaluate DslEvalError（语义：_to_set 类型）
tests/test_condition_eval.py:334 test_len_on_number_raises → v1 raise ⟺ v2 evaluate DslEvalError（语义：len 参数类型）
tests/test_condition_eval.py:342 test_rand_comparison → (allowed, None)（rand 族：点断言 + 同 seed 精确值）
tests/test_condition_eval.py:349 test_rand_range_comparison → (allowed, None)（rand 族：点断言 + 同 seed 精确值）
tests/test_condition_eval.py:356 test_randint_comparison → (allowed, None)（rand 族：点断言 + 同 seed 精确值）
tests/test_condition_eval.py:363 test_rand_with_boolean_input → (uncertain, 0.5)（rand 族：点断言 + 同 seed 精确值）
tests/test_rules.py:44 test_strength_rule_blocks_heavy_table → blocked·strength_vs_weight（20<120）
tests/test_rules.py:57 test_lock_rule_returns_uncertain_probability → uncertain·skill_vs_lock·requires_roll·0<p<1
tests/test_rules.py:72 test_no_rule_returns_none → None
tests/test_rules.py:84 test_body_width_blocks_fat_player_thin_passage → blocked·body_width_vs_passage（v1 target_position 键在 v2 封闭集外丢弃）
tests/test_rules.py:99 test_body_width_allows_thin_player_slim_passage → allowed·body_width_vs_passage
tests/test_rules.py:113 test_extraordinary_action_allows_superhuman → allowed·extraordinary
tests/test_rules.py:128 test_blocked_common_action_blocks_player → blocked·blocked_common
tests/test_rules.py:144 test_skill_vs_lock_allows_high_skill → allowed·skill_vs_lock（0.9≥0.8）
tests/test_rules.py:158 test_strength_rule_uncertain_when_close → blocked→uncertain·requires_roll（25<120；125∈(120,180)）
tests/test_rules.py:184 test_world_rules_with_no_deterministic_key_are_noop → blocked·strength_vs_weight（无 deterministic 键 → rules=∅/disabled=∅）
tests/test_rules.py:196 test_custom_regex_blocked_takes_priority_over_extraordinary → blocked·custom:warp_madness
tests/test_rules.py:220 test_custom_regex_allowed_takes_priority_over_blocked_common → allowed·custom:honor_duel_exception
tests/test_rules.py:244 test_custom_condition_blocks_action → blocked·custom:sanity_gate（sanity 15<20）
tests/test_rules.py:267 test_custom_condition_returns_uncertain_probability → uncertain·p==0.3·requires_roll·custom:sanity_gate
tests/test_rules.py:290 test_custom_match_action_plus_condition_requires_both → None / blocked·custom:storm_heavy_lift
tests/test_rules.py:320 test_disable_strength_rule → None（disable [3] → strength_vs_weight）
tests/test_rules.py:331 test_disable_body_width_rule → None（disable [5] → body_width_vs_passage）
tests/test_rules.py:343 test_invalid_regex_is_skipped_and_builtin_rules_continue → blocked·strength_vs_weight（re.error → skip 本条，无诊断，无 caplog 断言）
tests/test_rules.py:360 test_invalid_condition_is_skipped_and_builtin_rules_continue → blocked·strength_vs_weight（DslEvalError → warn+skip，caplog 断言；SOT §6.2 L763 ①）
tests/test_rules.py:376 test_first_matching_custom_rule_wins → blocked·custom:first（priority/id 序 = v1 append 序）
tests/test_rules.py:394 test_exact_match → True ⟺ blocked_common 命中（类方法平铺，名不变）
tests/test_rules.py:397 test_substring_match → True ⟺ blocked_common 命中
tests/test_rules.py:400 test_comma_separated_keywords → True ⟺ blocked_common 命中
tests/test_rules.py:403 test_no_match → False ⟺ 全 miss = None
tests/test_rules.py:406 test_empty_inputs → False×2 ⟺ None×2

异常映射表（7 例 v1 raise 的 v2 落点）：
- parse 期 ⟺ 结构诊断 LLMSIM_DSL_PARSE（永不抛）：test_invalid_syntax_raises
  （根必须以 if 开始）；test_invalid_outcome_raises（非法输出 'impossible'——
  v1 在 eval 期 raise，v2 提前到 parse 期，观测同为「错误」，阶段差异为两阶段
  分离的既定后果）。
- eval 期 ⟺ evaluate_condition raise DslEvalError（不吞）：test_missing_variable_
  raises（未知变量 'player.missing'）、test_division_by_zero_raises（除零）、
  test_in_with_nonlist_rhs_raises（in 右值类型）、test_subset_with_string_raises
  （_to_set 类型）、test_len_on_number_raises（len 参数类型）。

rand 族 4 例（SOT §6.2 L761）：保留 v1 点断言 + 追加同 seed 精确值断言
（W2 conftest ``seeded_rng`` fixture；SOT §6.2 L761 rand 族处置）：seed=0 → rand() =
0.8444218515250481；uniform(0,100) = 84.4421851525048；randint(1,6) = 4。

静态预检（SOT §6.2 逐例核检项）：66 例集 0 命中 D-P5-DEV-3（命中分支后垃圾，
if-chain 族 L39/L272-293 均良构、else 分支后无多余内容）、0 命中 D-P5-DEV-6
（单分支无尾）、0 命中 D-P5-DEV-7（uncertain 表达式概率；全部为数字字面或裸
uncertain）、0 命中 D-P5-DEV-9（裸 player/target 无点号 truthy 形）→ 无逐例
披露行。

hermetic：顶层平铺函数；零真实随机（非 rand 族用例注入永不消费的
``_UNUSED_RNG``；rand 族经 seeded_rng）；零网络。
"""

from __future__ import annotations

import logging

import pytest

from src.engine_v2.content.rule_module import (
    BUILTIN_RULE_IDS,
    ActionInput,
    DslContext,
    DslEvalError,
    check_action_feasibility,
    evaluate_condition,
    parse_dsl,
    resolve_target,
)
from src.engine_v2.content.schemas import RuleSpec


class _UnusedRng:
    """非 rand 族用例的注入占位：任何消费即断言失败（零随机面保证）。"""

    def rand(self) -> float:
        raise AssertionError("非 rand 族用例不得消费 rng")

    def uniform(self, lo: float, hi: float) -> float:
        raise AssertionError("非 rand 族用例不得消费 rng")

    def randint(self, lo: int, hi: int) -> int:
        raise AssertionError("非 rand 族用例不得消费 rng")


_UNUSED_RNG = _UnusedRng()


# ── 上下文映射（v1 _context()/​_ctx_with_lists() → DslContext）──────────


def _context() -> DslContext:
    return DslContext(
        player={
            "attributes": {
                "sanity": {"value": 35},
                "resolve": {"value": 70},
            },
            "physical_profile": {
                "strength": 2.0,
                "body_width_cm": 60,
            },
            "capabilities": {
                "skill_levels": {"lockpicking": 0.4},
            },
        },
        target={
            "properties": {
                "weight_kg": 120,
                "lock_difficulty": 0.8,
                "width_cm": 80,
            },
        },
        variables={"a": 3},
    )


def _ctx_with_lists() -> DslContext:
    return DslContext(
        player={
            "attributes": {
                "sanity": {"value": 35},
                "resolve": {"value": 70},
                "flags": {"value": ["alert", "danger"]},
                "tags": {"value": ["safe", "calm"]},
                "inventory": {"value": ["a", "b", "c"]},
                "stage": {"value": "active"},
            },
            "physical_profile": {
                "strength": 2.0,
                "body_width_cm": 60,
            },
            "capabilities": {
                "skill_levels": {"lockpicking": 0.4},
            },
            "status_effects": {"fighting": True},
        },
        target={
            "properties": {
                "weight_kg": 120,
                "lock_difficulty": 0.8,
                "width_cm": 80,
            },
        },
        variables={"a": 3},
    )


def _eval_with_rng(expression: str, context: DslContext, rng) -> "object":
    parsed = parse_dsl(expression, "parity")
    assert parsed.ast is not None, f"预期解析成功，实得诊断: {parsed.diagnostics}"
    return evaluate_condition(parsed.ast, context, rng)


def _eval(expression: str, context: DslContext | None = None):
    return _eval_with_rng(expression, context or _context(), _UNUSED_RNG)


# ── tests/test_condition_eval.py 41 例（同名 1:1）──────────────────────


def test_simple_comparison_returns_blocked():
    outcome = _eval("if(player.sanity < 40, blocked; allowed)")

    assert outcome.feasibility == "blocked"
    assert outcome.probability is None


def test_ifelse_chain_returns_uncertain_with_probability():
    outcome = _eval("if(a < 1, blocked; a < 5, uncertain:0.4; allowed)")

    assert outcome.feasibility == "uncertain"
    assert outcome.probability == 0.4


def test_arithmetic_and_target_weight_alias():
    outcome = _eval("if(player.strength * 50 >= target.weight, allowed; blocked)")

    assert outcome.feasibility == "blocked"


def test_parentheses_and_precedence():
    outcome = _eval(
        "if((player.strength + 0.5) * 50 >= target.weight, allowed; blocked)"
    )

    assert outcome.feasibility == "allowed"


def test_min_max_functions():
    outcome = _eval(
        "if(min(player.sanity, player.resolve) < max(20, 30), blocked; allowed)"
    )

    assert outcome.feasibility == "allowed"


def test_skill_level_lookup():
    outcome = _eval(
        "if(player.lockpicking < target.lock_difficulty, uncertain:0.25; allowed)"
    )

    assert outcome.feasibility == "uncertain"
    assert outcome.probability == 0.25


def test_missing_variable_raises():
    with pytest.raises(DslEvalError):
        _eval("if(player.missing < 1, blocked; allowed)")


def test_division_by_zero_raises():
    with pytest.raises(DslEvalError):
        _eval("if(player.sanity / 0 < 1, blocked; allowed)")


def test_invalid_syntax_raises():
    parsed = parse_dsl("player.sanity < 30", "parity")

    assert parsed.ast is None
    assert [d.code for d in parsed.diagnostics] == ["LLMSIM_DSL_PARSE"]


def test_invalid_outcome_raises():
    parsed = parse_dsl("if(player.sanity < 40, impossible; allowed)", "parity")

    assert parsed.ast is None
    assert [d.code for d in parsed.diagnostics] == ["LLMSIM_DSL_PARSE"]


def test_uncertain_without_probability_defaults_to_half():
    outcome = _eval("if(player.sanity < 40, uncertain; allowed)")

    assert outcome.feasibility == "uncertain"
    assert outcome.probability == 0.5


def test_and_operator():
    outcome = _eval(
        "if(player.sanity < 40 and player.resolve > 60, blocked; allowed)"
    )
    assert outcome.feasibility == "blocked"


def test_and_operator_false():
    outcome = _eval(
        "if(player.sanity < 40 and player.resolve < 60, blocked; allowed)"
    )
    assert outcome.feasibility == "allowed"


def test_or_operator():
    outcome = _eval("if(a < 1 or a > 2, blocked; allowed)")
    assert outcome.feasibility == "blocked"


def test_not_operator():
    outcome = _eval("if(not (player.sanity > 80), blocked; allowed)")
    assert outcome.feasibility == "blocked"


def test_compound_boolean():
    outcome = _eval("if((a < 1 or a > 2) and player.resolve > 60, blocked; allowed)")
    assert outcome.feasibility == "blocked"


def test_in_operator():
    outcome = _eval('if("alert" in player.flags, blocked; allowed)', _ctx_with_lists())
    assert outcome.feasibility == "blocked"


def test_in_operator_false():
    outcome = _eval('if("boss" in player.flags, blocked; allowed)', _ctx_with_lists())
    assert outcome.feasibility == "allowed"


def test_not_in_operator():
    outcome = _eval('if("boss" not in player.flags, blocked; allowed)', _ctx_with_lists())
    assert outcome.feasibility == "blocked"


def test_subset_operator():
    outcome = _eval("if(player.tags subset player.flags, blocked; allowed)", _ctx_with_lists())
    assert outcome.feasibility == "allowed"


def test_subset_operator_true():
    ctx = DslContext(
        player={
            "attributes": {
                "required": {"value": ["a"]},
                "inventory": {"value": ["a", "b", "c"]},
            }
        }
    )
    outcome = _eval(
        "if(player.required subset player.inventory, blocked; allowed)", ctx
    )
    assert outcome.feasibility == "blocked"


def test_intersects_operator():
    outcome = _eval(
        "if(player.flags intersects player.tags, blocked; allowed)", _ctx_with_lists()
    )
    assert outcome.feasibility == "allowed"


def test_intersects_operator_true():
    outcome = _eval(
        "if(player.flags intersects player.flags, blocked; allowed)", _ctx_with_lists()
    )
    assert outcome.feasibility == "blocked"


def test_disjoint_operator():
    outcome = _eval("if(player.tags disjoint player.flags, blocked; allowed)", _ctx_with_lists())
    assert outcome.feasibility == "blocked"


def test_contains_operator():
    ctx = DslContext(player={"status_effects": {"fighting": True}})
    outcome = _eval(
        "if(player.status_effects contains fighting, blocked; allowed)", ctx
    )
    assert outcome.feasibility == "blocked"


def test_len_function():
    outcome = _eval("if(len(player.flags) > 1, blocked; allowed)", _ctx_with_lists())
    assert outcome.feasibility == "blocked"


def test_string_comparison_equals():
    outcome = _eval('if(player.stage = "active", blocked; allowed)', _ctx_with_lists())
    assert outcome.feasibility == "blocked"


def test_string_comparison_not_equals():
    outcome = _eval('if(player.stage != "latent", blocked; allowed)', _ctx_with_lists())
    assert outcome.feasibility == "blocked"


def test_nested_if_as_branch_value():
    outcome = _eval(
        "if(a < 1, if(player.sanity < 40, blocked; uncertain:0.3); allowed)"
    )
    assert outcome.feasibility == "allowed"


def test_nested_if_as_branch_value_matched():
    outcome = _eval(
        "if(a > 1, if(player.sanity < 40, blocked; uncertain:0.3); allowed)"
    )
    assert outcome.feasibility == "blocked"


def test_nested_if_as_default():
    outcome = _eval(
        "if(a < 1, blocked; if(player.sanity > 80, uncertain:0.3; allowed))"
    )
    assert outcome.feasibility == "allowed"


def test_nested_if_deep():
    outcome = _eval(
        "if(a < 1, blocked; if(a < 2, uncertain:0.1; if(a < 5, uncertain:0.5; allowed)))"
    )
    assert outcome.feasibility == "uncertain"
    assert outcome.probability == 0.5


def test_set_and_bool_combined():
    outcome = _eval(
        'if("alert" in player.flags and len(player.flags) > 1, blocked; allowed)',
        _ctx_with_lists(),
    )
    assert outcome.feasibility == "blocked"


def test_boolean_with_set():
    outcome = _eval(
        'if(not ("boss" in player.flags) and player.sanity < 50, blocked; allowed)',
        _ctx_with_lists(),
    )
    assert outcome.feasibility == "blocked"


def test_in_with_nonlist_rhs_raises():
    with pytest.raises(DslEvalError):
        _eval('if("alert" in player.sanity, blocked; allowed)', _ctx_with_lists())


def test_subset_with_string_raises():
    with pytest.raises(DslEvalError):
        _eval("if(player.stage subset player.flags, blocked; allowed)", _ctx_with_lists())


def test_len_on_number_raises():
    with pytest.raises(DslEvalError):
        _eval("if(len(player.sanity) > 0, blocked; allowed)", _ctx_with_lists())


def test_rand_comparison(seeded_rng):
    # 同 seed 精确值（SOT §6.2 L761）：SeededRng(0).rand() = 0.8444218515250481
    assert seeded_rng().rand() == 0.8444218515250481
    outcome = _eval_with_rng("if(rand() < 1.0, allowed; blocked)", _context(), seeded_rng())

    assert outcome.feasibility == "allowed"


def test_rand_range_comparison(seeded_rng):
    # 同 seed 精确值：SeededRng(0).uniform(0, 100) = 84.4421851525048
    assert seeded_rng().uniform(0, 100) == 84.4421851525048
    outcome = _eval_with_rng("if(rand(0, 100) >= 0, allowed; blocked)", _context(), seeded_rng())

    assert outcome.feasibility == "allowed"


def test_randint_comparison(seeded_rng):
    # 同 seed 精确值：SeededRng(0).randint(1, 6) = 4
    assert seeded_rng().randint(1, 6) == 4
    outcome = _eval_with_rng(
        "if(randint(1, 6) >= 1, allowed; blocked)", _context(), seeded_rng()
    )

    assert outcome.feasibility == "allowed"


def test_rand_with_boolean_input(seeded_rng):
    # 同 seed 精确值：rand() = 0.8444218515250481（truthy）→ 命中 uncertain:0.5
    assert seeded_rng().rand() == 0.8444218515250481
    outcome = _eval_with_rng(
        "if(rand(), uncertain:0.5; allowed)", _context(), seeded_rng()
    )

    assert outcome.feasibility == "uncertain"
    assert outcome.probability == 0.5


# ── tests/test_rules.py 25 例（同名 1:1）───────────────────────────────


def _test_state():
    player = {
        "attributes": {
            "sanity": {"value": 35},
            "storm_tolerance": {"value": 45},
        },
        "physical_profile": {
            "strength": 0.4,
            "body_width_cm": 60.0,
        },
        "capabilities": {
            "blocked_common_actions": [],
            "allowed_extraordinary_actions": [],
            "skill_levels": {"lockpicking": 0.2},
        },
    }
    objects = {
        "banquet_table": {
            "id": "banquet_table",
            "name": "长餐桌",
            "properties": {"weight_kg": 120.0},
        },
        "study_lock": {
            "id": "study_lock",
            "name": "书房门锁",
            "properties": {"lock_difficulty": 0.8},
        },
    }
    locations = {
        "rose_garden": {
            "id": "rose_garden",
            "name": "玫瑰花园",
            "properties": {"width_cm": 80.0},
        }
    }
    return player, objects, locations


def _deterministic(world_rules: dict | None):
    """v1 world_rules["deterministic"] → v2 (rules, disabled) 映射。

    append → RuleSpec 序列（match=match_action）；disable [N] →
    frozenset({BUILTIN_RULE_IDS[N-1]})；无 deterministic 键 → ((), frozenset())。
    """
    if not world_rules or "deterministic" not in world_rules:
        return (), frozenset()
    det = world_rules["deterministic"]
    rules = tuple(
        RuleSpec(
            id=item["id"],
            description=item.get("description", ""),
            match=item.get("match_action"),
            condition=item.get("condition"),
            feasibility=item.get("feasibility"),
            probability=item.get("probability"),
        )
        for item in det.get("append", [])
    )
    disabled = frozenset(BUILTIN_RULE_IDS[n - 1] for n in det.get("disable", []))
    return rules, disabled


def _run(player, objects, locations, action: dict, world_rules: dict | None = None):
    """v1 check_action_feasibility(player_action, player, objects, locations,
    world_rules) → v2 五参调用（action dict → ActionInput；world_rules →
    (rules, disabled)；context 按 v1 _custom_rule_result 口径构造）。"""
    action_input = ActionInput(
        raw_input=action.get("raw_input", ""),
        interpreted_intent=action.get("interpreted_intent", ""),
        action_description=action.get("action_description", ""),
        speech_content=action.get("speech_content", ""),
        target_object_id=action.get("target_object_id"),
        action_type=action.get("action_type"),
    )
    target_ref = resolve_target(action_input, objects, locations)
    context = DslContext(
        player=player,
        target=target_ref.object or {},
        variables={"action": action_input},
    )
    rules, disabled = _deterministic(world_rules)
    return check_action_feasibility(
        rules, action_input, context, objects, locations, disabled
    )


def test_strength_rule_blocks_heavy_table():
    player, objects, locations = _test_state()
    result = _run(
        player,
        objects,
        locations,
        {
            "action_type": "interact",
            "action_description": "把长餐桌推到墙边",
            "target_object_id": "banquet_table",
        },
    )

    assert result is not None
    assert result.matched_rule == "strength_vs_weight"
    assert result.feasibility == "blocked"


def test_lock_rule_returns_uncertain_probability():
    player, objects, locations = _test_state()
    result = _run(
        player,
        objects,
        locations,
        {
            "action_type": "interact",
            "action_description": "试着打开书房门锁",
            "target_object_id": "study_lock",
        },
    )

    assert result is not None
    assert result.matched_rule == "skill_vs_lock"
    assert result.feasibility == "uncertain"
    assert result.requires_roll is True
    assert 0 < result.success_probability < 1


def test_no_rule_returns_none():
    player, objects, locations = _test_state()
    result = _run(
        player,
        objects,
        locations,
        {
            "action_type": "observe",
            "action_description": "观察吊灯",
        },
    )

    assert result is None


def test_body_width_blocks_fat_player_thin_passage():
    player, objects, locations = _test_state()
    player["physical_profile"]["body_width_cm"] = 100.0
    locations["rose_garden"]["properties"] = {"width_cm": 30.0}
    result = _run(
        player,
        objects,
        locations,
        {
            "action_type": "move",
            "action_description": "穿过狭窄的玫瑰花园入口",
        },
    )

    assert result is not None
    assert result.matched_rule == "body_width_vs_passage"
    assert result.feasibility == "blocked"


def test_body_width_allows_thin_player_slim_passage():
    player, objects, locations = _test_state()
    player["physical_profile"]["body_width_cm"] = 30.0
    locations["rose_garden"]["properties"] = {"width_cm": 80.0}
    result = _run(
        player,
        objects,
        locations,
        {
            "action_type": "move",
            "action_description": "穿过玫瑰花园",
        },
    )

    assert result is not None
    assert result.matched_rule == "body_width_vs_passage"
    assert result.feasibility == "allowed"


def test_extraordinary_action_allows_superhuman():
    player, objects, locations = _test_state()
    player["capabilities"]["allowed_extraordinary_actions"] = [
        "通晓庄园所有秘密通道和暗门的精确位置",
    ]
    result = _run(
        player,
        objects,
        locations,
        {
            "action_type": "move",
            "action_description": "找到一个秘密通道并走进去",
        },
    )

    assert result is not None
    assert result.matched_rule == "extraordinary"
    assert result.feasibility == "allowed"


def test_blocked_common_action_blocks_player():
    player, objects, locations = _test_state()
    player["capabilities"]["blocked_common_actions"] = [
        "对任何人说出真诚的感谢或道歉",
    ]
    result = _run(
        player,
        objects,
        locations,
        {
            "action_type": "speak",
            "action_description": "向对方真诚道歉",
            "speech_content": "对不起，是我错了",
        },
    )

    assert result is not None
    assert result.matched_rule == "blocked_common"
    assert result.feasibility == "blocked"


def test_skill_vs_lock_allows_high_skill():
    player, objects, locations = _test_state()
    player["capabilities"]["skill_levels"]["lockpicking"] = 0.9
    result = _run(
        player,
        objects,
        locations,
        {
            "action_type": "interact",
            "action_description": "打开书房门锁",
            "target_object_id": "study_lock",
        },
    )

    assert result is not None
    assert result.matched_rule == "skill_vs_lock"
    assert result.feasibility == "allowed"


def test_strength_rule_uncertain_when_close():
    player, objects, locations = _test_state()
    player["physical_profile"]["strength"] = 0.5  # 25kg capacity
    result = _run(
        player,
        objects,
        locations,
        {
            "action_type": "interact",
            "action_description": "把长餐桌推到墙边",
            "target_object_id": "banquet_table",  # 120kg
        },
    )

    assert result is not None
    assert result.matched_rule == "strength_vs_weight"
    assert result.feasibility == "blocked"
    # With strength 2.5, capacity=125kg which is > 120kg but < 180kg
    player["physical_profile"]["strength"] = 2.5
    result2 = _run(
        player,
        objects,
        locations,
        {
            "action_type": "interact",
            "action_description": "把长餐桌推到墙边",
            "target_object_id": "banquet_table",
        },
    )
    assert result2 is not None
    assert result2.feasibility == "uncertain"
    assert result2.requires_roll is True


def test_world_rules_with_no_deterministic_key_are_noop():
    player, objects, locations = _test_state()
    result = _run(
        player,
        objects,
        locations,
        {
            "action_type": "interact",
            "action_description": "把长餐桌推到墙边",
            "target_object_id": "banquet_table",
        },
        {"physics": {"disable": [1]}},
    )

    assert result is not None
    assert result.matched_rule == "strength_vs_weight"


def test_custom_regex_blocked_takes_priority_over_extraordinary():
    player, objects, locations = _test_state()
    player["capabilities"]["allowed_extraordinary_actions"] = ["集中精神"]
    world_rules = {
        "deterministic": {
            "append": [
                {
                    "id": "warp_madness",
                    "description": "亚空间低语干扰心智集中",
                    "match_action": "集中精神",
                    "feasibility": "blocked",
                }
            ]
        }
    }

    result = _run(
        player,
        objects,
        locations,
        {
            "action_type": "observe",
            "action_description": "集中精神分析低语",
        },
        world_rules,
    )

    assert result is not None
    assert result.matched_rule == "custom:warp_madness"
    assert result.feasibility == "blocked"


def test_custom_regex_allowed_takes_priority_over_blocked_common():
    player, objects, locations = _test_state()
    player["capabilities"]["blocked_common_actions"] = ["道歉"]
    world_rules = {
        "deterministic": {
            "append": [
                {
                    "id": "honor_duel_exception",
                    "description": "荣誉决斗允许正式致歉",
                    "match_action": "道歉",
                    "feasibility": "allowed",
                }
            ]
        }
    }

    result = _run(
        player,
        objects,
        locations,
        {
            "action_type": "speak",
            "action_description": "向对手道歉",
        },
        world_rules,
    )

    assert result is not None
    assert result.matched_rule == "custom:honor_duel_exception"
    assert result.feasibility == "allowed"


def test_custom_condition_blocks_action():
    player, objects, locations = _test_state()
    player["attributes"]["sanity"]["value"] = 15
    world_rules = {
        "deterministic": {
            "append": [
                {
                    "id": "sanity_gate",
                    "description": "精神崩溃时多数行动受限",
                    "condition": "if(player.sanity < 20, blocked; allowed)",
                }
            ]
        }
    }

    result = _run(
        player,
        objects,
        locations,
        {
            "action_type": "observe",
            "action_description": "观察房间",
        },
        world_rules,
    )

    assert result is not None
    assert result.matched_rule == "custom:sanity_gate"
    assert result.feasibility == "blocked"


def test_custom_condition_returns_uncertain_probability():
    player, objects, locations = _test_state()
    world_rules = {
        "deterministic": {
            "append": [
                {
                    "id": "sanity_gate",
                    "description": "精神不稳时行动不确定",
                    "condition": "if(player.sanity < 40, uncertain:0.3; allowed)",
                }
            ]
        }
    }

    result = _run(
        player,
        objects,
        locations,
        {
            "action_type": "observe",
            "action_description": "观察房间",
        },
        world_rules,
    )

    assert result is not None
    assert result.feasibility == "uncertain"
    assert result.success_probability == 0.3
    assert result.requires_roll is True


def test_custom_match_action_plus_condition_requires_both():
    player, objects, locations = _test_state()
    world_rules = {
        "deterministic": {
            "append": [
                {
                    "id": "storm_heavy_lift",
                    "description": "暴风中搬运重物",
                    "match_action": "搬运|推动|抬起",
                    "condition": "if(player.storm_tolerance < 50, blocked; allowed)",
                }
            ]
        }
    }

    no_match = _run(
        player,
        objects,
        locations,
        {
            "action_type": "observe",
            "action_description": "观察长餐桌",
            "target_object_id": "banquet_table",
        },
        world_rules,
    )
    match = _run(
        player,
        objects,
        locations,
        {
            "action_type": "interact",
            "action_description": "推动长餐桌",
            "target_object_id": "banquet_table",
        },
        world_rules,
    )

    assert no_match is None
    assert match is not None
    assert match.matched_rule == "custom:storm_heavy_lift"
    assert match.feasibility == "blocked"


def test_disable_strength_rule():
    player, objects, locations = _test_state()
    result = _run(
        player,
        objects,
        locations,
        {
            "action_type": "interact",
            "action_description": "把长餐桌推到墙边",
            "target_object_id": "banquet_table",
        },
        {"deterministic": {"disable": [3]}},
    )

    assert result is None


def test_disable_body_width_rule():
    player, objects, locations = _test_state()
    player["physical_profile"]["body_width_cm"] = 100.0
    locations["rose_garden"]["properties"] = {"width_cm": 30.0}
    result = _run(
        player,
        objects,
        locations,
        {
            "action_type": "move",
            "action_description": "穿过玫瑰花园",
        },
        {"deterministic": {"disable": [5]}},
    )

    assert result is None


def test_invalid_regex_is_skipped_and_builtin_rules_continue():
    player, objects, locations = _test_state()
    result = _run(
        player,
        objects,
        locations,
        {
            "action_type": "interact",
            "action_description": "把长餐桌推到墙边",
            "target_object_id": "banquet_table",
        },
        {
            "deterministic": {
                "append": [
                    {
                        "id": "bad_regex",
                        "description": "坏正则",
                        "match_action": "[",
                        "feasibility": "blocked",
                    }
                ]
            }
        },
    )

    assert result is not None
    assert result.matched_rule == "strength_vs_weight"


def test_invalid_condition_is_skipped_and_builtin_rules_continue(caplog):
    player, objects, locations = _test_state()
    with caplog.at_level(logging.WARNING, logger="src.engine_v2.content.rule_module"):
        result = _run(
            player,
            objects,
            locations,
            {
                "action_type": "interact",
                "action_description": "把长餐桌推到墙边",
                "target_object_id": "banquet_table",
            },
            {
                "deterministic": {
                    "append": [
                        {
                            "id": "bad_condition",
                            "description": "坏条件",
                            "condition": "if(player.missing < 1, blocked; allowed)",
                        }
                    ]
                }
            },
        )

    assert result is not None
    assert result.matched_rule == "strength_vs_weight"
    # SOT §6.2 L763 ①：v1 逐字 warn 格式（rules.py:102-104）+ 规则跳过
    assert any(
        rec.levelno == logging.WARNING
        and "deterministic rule 'bad_condition' condition failed" in rec.message
        for rec in caplog.records
    )


def test_first_matching_custom_rule_wins():
    player, objects, locations = _test_state()
    world_rules = {
        "deterministic": {
            "append": [
                {
                    "id": "first",
                    "description": "第一条",
                    "match_action": "观察",
                    "feasibility": "blocked",
                },
                {
                    "id": "second",
                    "description": "第二条",
                    "match_action": "观察",
                    "feasibility": "allowed",
                },
            ]
        }
    }

    result = _run(
        player,
        objects,
        locations,
        {
            "action_type": "observe",
            "action_description": "观察房间",
        },
        world_rules,
    )

    assert result is not None
    assert result.matched_rule == "custom:first"
    assert result.feasibility == "blocked"


# ── TestTextMatchesRule 5 例（类方法 → 顶层平铺函数，名称不变）─────────


def _text_rule_result(text: str, rule: str):
    """谓词等价观测面：内置 blocked_common 管线中 _text_matches_rule 是唯一
    判定点（命中 ⟺ result 非 None 且 matched_rule == 'blocked_common'；
    未命中 ⟺ 全 miss = None）。"""
    player, objects, locations = _test_state()
    player["capabilities"]["blocked_common_actions"] = [rule]
    action = ActionInput(action_description=text)
    context = DslContext(player=player, target={}, variables={"action": action})
    return check_action_feasibility((), action, context, objects, locations)


def test_exact_match():
    # v1: _text_matches_rule("道歉", "道歉") is True ⟺ v2 blocked_common 命中
    result = _text_rule_result("道歉", "道歉")
    assert result is not None
    assert result.matched_rule == "blocked_common"


def test_substring_match():
    # v1: _text_matches_rule("向对方真诚道歉", "道歉") is True
    result = _text_rule_result("向对方真诚道歉", "道歉")
    assert result is not None
    assert result.matched_rule == "blocked_common"


def test_comma_separated_keywords():
    # v1: _text_matches_rule("我想开锁", "开锁，撬锁，门锁") is True
    result = _text_rule_result("我想开锁", "开锁，撬锁，门锁")
    assert result is not None
    assert result.matched_rule == "blocked_common"


def test_no_match():
    # v1: _text_matches_rule("走路", "开锁") is False ⟺ v2 全 miss = None
    assert _text_rule_result("走路", "开锁") is None


def test_empty_inputs():
    # v1: _text_matches_rule("", "rule") is False；_text_matches_rule("text", "") is False
    assert _text_rule_result("", "rule") is None
    assert _text_rule_result("text", "") is None
