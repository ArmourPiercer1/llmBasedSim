"""P9 W1 attributes 模块单测（SOT §6.1：t1–t12 共 12 函数；T02）。

设计依据 = ``docs/v2/contracts/P9-official-modules-migration-design.md``
§3.2（函数级锚表）+ §6.1（测试表）+ §3.17（D-α 方法学：t12 = v1 纯函数
直引 ``src.game.attributes`` 模块级函数，非运行时回放）+ SOT §9
（ERR-P9-07 钉面）+ §6.3（AD-P9-1 锁条件 DSL 注入）。

覆盖项（每项独立 test 函数）：

1. t1_clamp_within：界内值原样返回；
2. t2_clamp_bounds：低于 min → min，高于 max → max（界上钉）；
3. t3_apply_delta_unlocked：delta 事件面 + 入参不变 + 返回新 Mapping；
4. t4_apply_delta_locked：locked → LockedAttributeError（message 含属性
   名 + locked；检查先于钳制）；
5. t5_apply_new_value_locked：同上 new_value 面；
6. t6_apply_new_value_clamped：v2 钳制差异面（150 → 100；v1 不钳制）；
7. t7_natural_deltas：3 tick × 2 属性钉值 + 零增量缺席 + ticks=0 全零
   面；
8. t8_lock_condition_dsl：条件真/假双面 + uncertain:0.5 → False
   （ERR-P9-07 仅 ALLOWED → True）+ AD-P9-1 未知变量/除零 →
   DslEvalError 透传（不吞、不误锁）+ 裸表达式结构错误 → DslEvalError；
9. t9_derive_attributes：truthy → 1.0 / 0 → 0.0 + 派生字段 0/1 界 +
   零反写源字段 + 仅返回派生条目 + 结构错误 → DslEvalError；
10. t10_snapshot：创建面 hidden+locked+min=max=value + 既有键仅覆写
    value（无 locked 检查）+ 零事件 + 入参不变；
11. t11_summarize_hidden：hidden 零泄漏（名/值均缺席）+ 键序 sorted 钉
    + 空可见集面；
12. t12_v1_parity_case：钉死夹具 10 属性 × 3 变更 × 2 tick，与 v1
    apply_attribute_changes / apply_natural_attribute_deltas 同序同值
    （D-α 单元面）。
"""

from __future__ import annotations

import importlib

import pytest

from src.engine_v2.content.rule_module import DslEvalError
from src.engine_v2.modules.attributes import (
    AttributeEvent,
    AttributeField,
    LockedAttributeError,
    apply_delta,
    apply_new_value,
    clamp_value,
    compute_natural_deltas,
    derive_attributes,
    evaluate_lock_condition,
    summarize_attributes_for_prompt,
    take_attribute_snapshot,
)


def _field(
    value: float = 50.0,
    *,
    name: str = "hp",
    min: float = 0.0,
    max: float = 100.0,
    locked: bool = False,
    hidden: bool = False,
    natural_delta_per_tick: float = 0.0,
) -> AttributeField:
    """构造合法 AttributeField（默认 hp 50 [0,100]）。"""
    return AttributeField(
        name=name,
        value=value,
        min=min,
        max=max,
        locked=locked,
        hidden=hidden,
        natural_delta_per_tick=natural_delta_per_tick,
    )


def test_attributes_t1_clamp_within() -> None:
    """1) 界内值原样返回（v1 _clamp:10 对齐）。"""
    field = _field()
    assert clamp_value(50.0, field) == 50.0
    assert clamp_value(1.0, field) == 1.0
    assert clamp_value(99.5, field) == 99.5


def test_attributes_t2_clamp_bounds() -> None:
    """2) 低于 min → min，高于 max → max（含界上钉）。"""
    field = _field()
    assert clamp_value(-5.0, field) == 0.0
    assert clamp_value(150.0, field) == 100.0
    assert clamp_value(0.0, field) == 0.0
    assert clamp_value(100.0, field) == 100.0


def test_attributes_t3_apply_delta_unlocked() -> None:
    """3) delta 事件面 + 入参不变 + 返回新 Mapping。"""
    fields = {"hp": _field(value=80.0)}
    new_fields, events = apply_delta(fields, "player_1", "hp", -30.0, 5)
    assert new_fields is not fields
    assert fields["hp"].value == 80.0  # 入参未修改
    assert new_fields["hp"].value == 50.0
    assert events == (
        AttributeEvent(
            actor_id="player_1",
            name="hp",
            old=80.0,
            new=50.0,
            reason="delta",
            tick=5,
        ),
    )
    # 零变化（delta=0）→ 无事件
    same, zero_events = apply_delta(fields, "player_1", "hp", 0.0, 5)
    assert zero_events == ()
    assert same["hp"].value == 80.0
    # 属性名缺失 → KeyError（显式失败面）
    with pytest.raises(KeyError):
        apply_delta(fields, "player_1", "nope", -1.0, 5)


def test_attributes_t4_apply_delta_locked() -> None:
    """4) locked → LockedAttributeError（message 含属性名 + locked；
    检查先于钳制：越界 delta 同样拒绝，不静默钳制）。"""
    fields = {"seal": _field(name="seal", locked=True)}
    with pytest.raises(LockedAttributeError, match="seal"):
        apply_delta(fields, "player_1", "seal", -1.0, 0)
    with pytest.raises(LockedAttributeError, match="locked"):
        apply_delta(fields, "player_1", "seal", -1.0, 0)
    with pytest.raises(LockedAttributeError):
        apply_delta(fields, "player_1", "seal", 1000.0, 0)


def test_attributes_t5_apply_new_value_locked() -> None:
    """5) new_value 面 locked → LockedAttributeError（同上序）。"""
    fields = {"seal": _field(name="seal", locked=True)}
    with pytest.raises(LockedAttributeError, match="seal.*locked"):
        apply_new_value(fields, "player_1", "seal", 99.0, 0)


def test_attributes_t6_apply_new_value_clamped() -> None:
    """6) v2 钳制差异面：越界新值钳至 max（v1 _apply_new_value 不钳制）。"""
    fields = {"hp": _field(value=90.0)}
    new_fields, events = apply_new_value(fields, "player_1", "hp", 150.0, 2)
    assert new_fields["hp"].value == 100.0
    assert events == (
        AttributeEvent(
            actor_id="player_1",
            name="hp",
            old=90.0,
            new=100.0,
            reason="new_value",
            tick=2,
        ),
    )


def test_attributes_t7_natural_deltas() -> None:
    """7) 3 tick × 2 属性钉值 + 零增量缺席 + ticks=0 全零面。"""
    fields = {
        "stamina": _field(name="stamina", natural_delta_per_tick=-2.0),
        "satiety": _field(name="satiety", natural_delta_per_tick=1.0),
        "mood": _field(name="mood"),
    }
    assert dict(compute_natural_deltas(fields, 3)) == {
        "satiety": 3.0,
        "stamina": -6.0,
    }
    assert "mood" not in compute_natural_deltas(fields, 3)
    assert dict(compute_natural_deltas(fields, 0)) == {}


def test_attributes_t8_lock_condition_dsl(dsl_rng) -> None:
    """8) 条件真/假双面 + uncertain → False + AD-P9-1 注入透传 +
    结构错误外化。"""
    fields = {"hp": _field(value=80.0)}
    # 条件真 → ALLOWED → True
    assert (
        evaluate_lock_condition(
            fields, "player_1", "hp", "if(hp < 90, allowed; blocked)",
            dsl_rng, 1,
        )
        is True
    )
    # 条件假 → BLOCKED → False
    assert (
        evaluate_lock_condition(
            fields, "player_1", "hp", "if(hp < 50, allowed; blocked)",
            dsl_rng, 1,
        )
        is False
    )
    # uncertain:0.5 → UNCERTAIN → False（ERR-P9-07：仅 ALLOWED → True）
    assert (
        evaluate_lock_condition(
            fields, "player_1", "hp",
            "if(hp < 90, uncertain:0.5; blocked)", dsl_rng, 1,
        )
        is False
    )
    # AD-P9-1a：未知变量 → DslEvalError 透传（不吞、不误锁）
    with pytest.raises(DslEvalError):
        evaluate_lock_condition(
            fields, "player_1", "hp",
            "if(hp < unknown_var, allowed; blocked)", dsl_rng, 1,
        )
    # AD-P9-1b：除零 → DslEvalError 透传
    with pytest.raises(DslEvalError):
        evaluate_lock_condition(
            fields, "player_1", "hp", "if(hp / 0 > 5, allowed; blocked)",
            dsl_rng, 1,
        )
    # 结构错误（裸表达式 ≠ if-chain 根产生式）→ DslEvalError 外化
    with pytest.raises(DslEvalError):
        evaluate_lock_condition(
            fields, "player_1", "hp", "hp < 90", dsl_rng, 1,
        )


def test_attributes_t9_derive_attributes(dsl_rng) -> None:
    """9) DSL 求值 + 零反写源字段 + 仅返回派生条目 + 结构错误透传。"""
    fields = {
        "hp": _field(value=80.0),
        "mood": _field(name="mood", value=30.0),
    }
    spec = {"strong": "hp > 50", "calm": "mood > 90", "zero": "0"}
    derived = derive_attributes(fields, "player_1", spec, dsl_rng)
    assert set(derived) == {"strong", "calm", "zero"}
    assert derived["strong"].value == 1.0  # truthy → ALLOWED → 1.0
    assert derived["calm"].value == 0.0  # 假 → BLOCKED → 0.0
    assert derived["zero"].value == 0.0  # 0 falsy → 0.0
    for field in derived.values():
        assert field.min == 0.0
        assert field.max == 1.0
        assert field.locked is False
        assert field.hidden is False
        assert field.natural_delta_per_tick == 0.0
    assert derived["strong"].name == "strong"
    # 零反写源字段（源 Mapping 原样）
    assert set(fields) == {"hp", "mood"}
    assert fields["hp"].value == 80.0
    assert "strong" not in fields
    # 结构错误（spec 表达式破坏 if-chain 合成）→ DslEvalError
    with pytest.raises(DslEvalError):
        derive_attributes(fields, "player_1", {"bad": "hp +"}, dsl_rng)


def test_attributes_t10_snapshot() -> None:
    """10) 创建面 hidden+locked（min=max=value）+ 既有键仅覆写 value
    （无 locked 检查）+ 零事件 + 入参不变。"""
    fields = {"hp": _field(value=80.0)}
    new_fields, events = take_attribute_snapshot(
        fields, "player_1", "snap_hp", 42.0,
    )
    assert events == ()
    snap = new_fields["snap_hp"]
    assert snap.value == 42.0
    assert snap.min == 42.0
    assert snap.max == 42.0
    assert snap.locked is True
    assert snap.hidden is True
    assert fields["hp"].value == 80.0  # 入参未修改
    # 既有键路径：仅 value 覆写（不追加 locked/hidden，v1 :851–861 对齐）
    new_fields2, events2 = take_attribute_snapshot(new_fields, "player_1", "hp", 10.0)
    assert events2 == ()
    assert new_fields2["hp"].value == 10.0
    assert new_fields2["hp"].locked is False
    assert new_fields2["hp"].hidden is False
    assert new_fields2["snap_hp"].locked is True


def test_attributes_t11_summarize_hidden() -> None:
    """11) hidden 零泄漏 + 键序 sorted 钉 + 空可见集面。"""
    fields = {
        "zeta": _field(name="zeta", value=3.0, max=10.0),
        "alpha": _field(name="alpha", value=1.5, max=10.0),
        "hidden_seal": _field(name="hidden_seal", value=77.0, hidden=True),
    }
    text = summarize_attributes_for_prompt(fields, "player_1")
    # hidden 零泄漏（属性名与值均不出现在文本）
    assert "hidden_seal" not in text
    assert "77" not in text
    # 键序钉（sorted：alpha 先于 zeta）+ 全文精确钉
    assert text.index("alpha") < text.index("zeta")
    assert text == (
        "attributes[player_1]: alpha=1.5 (min=0, max=10); "
        "zeta=3 (min=0, max=10)"
    )
    # 空可见集面
    only_hidden = {"h": _field(name="h", hidden=True)}
    assert summarize_attributes_for_prompt(only_hidden, "player_1") == (
        "attributes[player_1]: (空)"
    )


# ── t12 v1 parity 夹具（D-α 钉死面；SOT §3.17 方法学）─────────────────
# 10 属性按字母序插入（v1 迭代序 = v2 sorted 序 → 拒绝同序可比）；
# 整点数值（±0 精确相等判据）。

_V1_ATTR_KEYS = (
    "agility", "charm", "composure", "focus", "hp",
    "mood", "satiety", "seal", "stamina", "wits",
)

_V1_CHANGES = (
    {
        "entity_type": "player",
        "entity_id": "player_1",
        "attribute_key": "hp",
        "delta": -20.0,
        "reason": "战斗损伤",
    },
    {
        "entity_type": "player",
        "entity_id": "player_1",
        "attribute_key": "seal",
        "new_value": 99.0,
        "reason": "封印测试",
    },
    {
        "entity_type": "player",
        "entity_id": "player_1",
        "attribute_key": "stamina",
        "new_value": 35.0,
    },
)


def _v1_player() -> dict:
    """v1 形状 player dict（属性名键 = 键名；整点值）。"""
    attrs: dict = {}
    for key in _V1_ATTR_KEYS:
        attr: dict = {"name": key, "value": 50.0, "min": 0.0, "max": 100.0}
        if key == "hp":
            attr["value"] = 80.0
        if key == "seal":
            attr["locked"] = True
            attr["natural_delta_per_minute"] = 7.0
        if key == "stamina":
            attr["natural_delta_per_minute"] = -5.0
        attrs[key] = attr
    return {
        "player_id": "player_1",
        "name": "玩家",
        "attributes": attrs,
    }


def _v2_fields() -> dict:
    """v2 形状 fields Mapping（natural_delta_per_tick = v1 每分钟值透传，
    宿主约定 1 tick = 1 分钟）。"""
    fields: dict = {}
    for key in _V1_ATTR_KEYS:
        kwargs: dict = {}
        if key == "hp":
            kwargs["value"] = 80.0
        if key == "seal":
            kwargs["locked"] = True
            kwargs["natural_delta_per_tick"] = 7.0
        if key == "stamina":
            kwargs["natural_delta_per_tick"] = -5.0
        fields[key] = _field(name=key, **kwargs)
    return fields


def test_attributes_t12_v1_parity_case() -> None:
    """12) v1 直引同序同值（D-α 单元面；非运行时回放）。"""
    # v1 纯函数直引（SOT §3.17 D-α；D-P9-14）：经 importlib 动态载入
    # src.game.attributes 模块级纯函数（非运行时回放、零第三方依赖）。
    v1_attrs = importlib.import_module("src.game.attributes")
    apply_attribute_changes = v1_attrs.apply_attribute_changes
    apply_natural_attribute_deltas = v1_attrs.apply_natural_attribute_deltas
    # ── 变更相位：v1 apply_attribute_changes 直引 ──
    player_v1, _, events_v1 = apply_attribute_changes(
        _v1_player(), {}, list(_V1_CHANGES),
    )
    # v1 事件面精确钉（delta 路径 :g 无冒号；new_value 路径带冒号）；
    # 变更 idx 1（seal locked）静默拒绝、零事件
    assert events_v1 == [
        "[属性] 玩家的hp 80 → 60（战斗损伤）",
        "[属性] 玩家的stamina: 50.0 → 35.0（属性事件）",
    ]
    # ── v2 变更相位（宿主 try/except 钉拒绝序）──
    fields = _v2_fields()
    events_v2: list = []
    v2_change_rejections: list = []
    for idx, change in enumerate(_V1_CHANGES):
        name = change["attribute_key"]
        try:
            if change.get("new_value") is not None:
                fields, evs = apply_new_value(
                    fields, "player_1", name,
                    float(change["new_value"]), 0,
                )
            else:
                fields, evs = apply_delta(
                    fields, "player_1", name, float(change["delta"]), 0,
                )
        except LockedAttributeError:
            v2_change_rejections.append(idx)
            continue
        events_v2.extend(evs)
    # 拒绝同序：同一变更 idx 1（seal）被拒
    assert v2_change_rejections == [1]
    assert [e.name for e in events_v2] == ["hp", "stamina"]
    assert events_v2[0].old == 80.0 and events_v2[0].new == 60.0
    assert events_v2[1].old == 50.0 and events_v2[1].new == 35.0

    # ── 自然相位：v1 tick_duration_minutes=2.0 直引 ──
    player_v1, _, events_v1_nat = apply_natural_attribute_deltas(
        player_v1, {}, tick_duration_minutes=2.0,
    )
    # v1 自然事件面精确钉（seal locked 静默跳过；stamina 35 → 25）
    assert events_v1_nat == ["[属性] 玩家的stamina自然变化 35 → 25"]
    # ── v2 自然相位（compute_natural_deltas + 宿主全键序 apply_delta）──
    deltas = compute_natural_deltas(fields, 2)
    assert dict(deltas) == {"seal": 14.0, "stamina": -10.0}
    events_v2_nat: list = []
    v2_nat_rejections: list = []
    for idx, key in enumerate(sorted(fields)):
        delta = deltas.get(key, 0.0)
        if delta == 0.0:
            continue
        try:
            fields, evs = apply_delta(fields, "player_1", key, delta, 1)
        except LockedAttributeError:
            v2_nat_rejections.append(idx)
            continue
        events_v2_nat.extend(evs)
    # 拒绝同序：seal = 字母序全键 idx 7（与 v1 迭代序同位）
    assert v2_nat_rejections == [7]
    assert [e.name for e in events_v2_nat] == ["stamina"]
    assert events_v2_nat[0].old == 35.0 and events_v2_nat[0].new == 25.0

    # ── 终值面：10 属性逐属性 ±0 精确相等 ──
    for key in _V1_ATTR_KEYS:
        v1_value = float(player_v1["attributes"][key]["value"])
        assert fields[key].value == v1_value, key
    # 终值钉（整点：hp 60 / stamina 25 / 余 50 / seal 50 未动）
    assert fields["hp"].value == 60.0
    assert fields["stamina"].value == 25.0
    assert fields["seal"].value == 50.0
    assert fields["agility"].value == 50.0
