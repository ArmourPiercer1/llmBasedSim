"""P9 W2 inventory 模块单测（SOT §6.1：t1–t6 共 6 函数；T03）。

设计依据 = ``docs/v2/contracts/P9-official-modules-migration-design.md``
§3.3（函数级锚表）+ §6.1（测试表）+ §3.15.2（M-4 state dict 折叠规范）
+ SOT §9（ERR-P9-08 ItemState 缺默认值更正面）+ SOT §8.1（K2 零直写钉
面）。

零 fixture 引用（纯 stdlib 数据面，W2 派工决定）；全部入参 = 本地字面量
构造，不引用 conftest fixture。

覆盖项（每项独立 test 函数）：

1. t1_item_state_roundtrip：ItemState 构造 → 字段读回 + 冻结面
   （FrozenInstanceError：变更尝试被拒）+ state 扁平串（M-4 折叠样例
   "closed=true,unlocked=true" 原样存、原样读，零解析）+ ERR-P9-08
   缺默认值面（position=None / state=None / properties={}）；
2. t2_can_carry_under：限内 → allowed=True（strength×50 面：
   strength=10 → CarryLimit(500.0)；weight_kg=100.0 → used_kg /
   limit_kg 钉值）+ weight_kg 缺失 / 非数值 → allowed=True 面；
3. t3_can_carry_over：超限 → allowed=False + reason 逐字钉 + 边界相等
   面（weight == limit → allowed，v1 仅 capacity < weight 时 blocked）；
4. t4_apply_pickup：位置转移面（返回 positions 无 item_id；入参零修改
   K2 钉）+ 事件 str 逐字钉 + ItemState.position 快照保持面 +
   item_id 缺席 → ValueError；
5. t5_apply_drop：镜像面（返回 positions 含 item_id 且位置 =
   ItemState.position 快照；入参零修改）+ item_id 缺席 / position
   is None → ValueError；
6. t6_item_summary：prompt 文本确定性（同输入两次调用同串）+ 键序钉
   （多物品按 id 升序）+ state 扁平串原样呈现钉 + scope_id 零消费面 +
   空集面。
"""

from __future__ import annotations

import dataclasses

import pytest

from src.engine_v2.modules.inventory import (
    CarryCheck,
    CarryLimit,
    ItemState,
    apply_drop,
    apply_pickup,
    can_carry,
    item_summary,
)


def test_inventory_t1_item_state_roundtrip() -> None:
    """1) ItemState 构造 → 字段读回 + 冻结面 + state 扁平串零解析。"""
    position = {"x": 5, "y": 0, "z": 0}
    properties = {"material": "oak_and_iron", "weight_kg": 42.0}
    item = ItemState(
        id="oak_door",
        name="橡木门",
        description="一扇厚重的橡木门",
        object_type="decoration",
        position=position,
        state="closed=true,unlocked=true",
        properties=properties,
    )
    assert item.id == "oak_door"
    assert item.name == "橡木门"
    assert item.description == "一扇厚重的橡木门"
    assert item.object_type == "decoration"
    assert item.position == position
    # state 扁平串（M-4 折叠样例，v1 dict {closed: true, unlocked: true}，
    # test_empty.yaml:40–42）原样存、原样读，零解析。
    assert item.state == "closed=true,unlocked=true"
    assert item.properties == properties
    # 冻结面：变更尝试 → FrozenInstanceError（AttributeError 子类）。
    with pytest.raises(dataclasses.FrozenInstanceError):
        item.name = "改不动"
    # ERR-P9-08 更正面：position/state 缺省 None / properties 缺省 {}。
    bare = ItemState(id="bare", name="bare")
    assert bare.position is None
    assert bare.state is None
    assert bare.properties == {}


def test_inventory_t2_can_carry_under() -> None:
    """2) 限内 → allowed=True（strength×50 面）+ 无重量数据放行面。"""
    items = {
        "crate": ItemState(
            id="crate",
            name="板条箱",
            properties={"weight_kg": 100.0},
        ),
        "feather": ItemState(id="feather", name="羽毛"),
        "heavy_text": ItemState(
            id="heavy_text",
            name="重标物",
            properties={"weight_kg": "heavy"},
        ),
    }
    # strength=10 → 50.0 × 10 = 500.0（调用侧经 attributes 面构造，
    # v1 STRENGTH_TO_KG_FACTOR = 50.0，rules.py:9）。
    limit = CarryLimit(max_kg=500.0)
    check = can_carry(items, "npc_1", "crate", limit)
    assert check == CarryCheck(
        allowed=True,
        reason="负重充足",
        used_kg=100.0,
        limit_kg=500.0,
    )
    # weight_kg 缺失 → allowed=True（v1 :169 weight is not None 门，
    # 无规则 = 放行）。
    no_weight = can_carry(items, "npc_1", "feather", limit)
    assert no_weight.allowed is True
    assert no_weight.used_kg == 0.0
    assert no_weight.limit_kg == 500.0
    assert no_weight.reason == "无重量数据，负重规则未触发"
    # weight_kg 非数值 → allowed=True（v2 防御性放行收窄面）。
    not_numeric = can_carry(items, "npc_1", "heavy_text", limit)
    assert not_numeric.allowed is True
    assert not_numeric.used_kg == 0.0
    assert not_numeric.reason == "无重量数据，负重规则未触发"
    # weight_kg = bool → 无重量数据面（bool 不在数值面；v2 防御性收窄，
    # 与实现 can_carry docstring 自述一致）。
    bool_weight = can_carry(
        {"b": ItemState(
            id="b",
            name="布尔物",
            properties={"weight_kg": True},
        )},
        "npc_1", "b", limit,
    )
    assert bool_weight.allowed is True
    assert bool_weight.used_kg == 0.0
    assert bool_weight.reason == "无重量数据，负重规则未触发"
    # target 缺席 → KeyError（v1 宿主侧警告面不迁移）。
    with pytest.raises(KeyError):
        can_carry(items, "npc_1", "ghost", limit)


def test_inventory_t3_can_carry_over() -> None:
    """3) 超限 → allowed=False + reason 逐字钉 + 边界相等面。"""
    items = {
        "anvil": ItemState(
            id="anvil",
            name="铁砧",
            properties={"weight_kg": 600.0},
        ),
    }
    limit = CarryLimit(max_kg=500.0)
    check = can_carry(items, "npc_1", "anvil", limit)
    assert check.allowed is False
    assert check.used_kg == 600.0
    assert check.limit_kg == 500.0
    assert check.reason == "负重超限：目标重 600kg > 上限 500kg"
    # 边界相等面：weight == limit → allowed（v1 仅 capacity < weight
    # 时 blocked，相等放行，rules.py:174）。
    edge = can_carry(items, "npc_1", "anvil", CarryLimit(max_kg=600.0))
    assert edge.allowed is True
    assert edge.reason == "负重充足"
    assert edge.used_kg == 600.0


def test_inventory_t4_apply_pickup() -> None:
    """4) 位置转移面 + 入参零修改（K2）+ 事件 str 逐字钉。"""
    items = {
        "crate": ItemState(
            id="crate",
            name="板条箱",
            position={"x": 3, "y": 1, "z": 0},
        ),
    }
    positions = {
        "crate": {"x": 3, "y": 1, "z": 0},
        "npc_1": {"x": 0, "y": 0, "z": 0},
    }
    items_snapshot = dict(items)
    positions_snapshot = {k: dict(v) for k, v in positions.items()}
    new_items, new_positions, events = apply_pickup(
        items, positions, "npc_1", "crate", 7,
    )
    # 位置转移：物品离开世界位置注册表。
    assert "crate" not in new_positions
    assert new_positions == {"npc_1": {"x": 0, "y": 0, "z": 0}}
    # items = 新 dict，ItemState 内容不变（含 position 快照保持）。
    assert new_items is not items
    assert new_items == items_snapshot
    assert new_items["crate"].position == {"x": 3, "y": 1, "z": 0}
    # K2：入参零修改。
    assert items == items_snapshot
    assert positions == positions_snapshot
    # 事件 str 逐字钉（v1 风格 [标签] 前缀 + actor_id + 物品名）。
    assert events == ("[拾取] npc_1 拾取了 板条箱",)
    # item_id 缺席 → ValueError（message 逐字钉）。
    with pytest.raises(ValueError, match="不存在，无法拾取"):
        apply_pickup(items, positions, "npc_1", "ghost", 7)


def test_inventory_t5_apply_drop() -> None:
    """5) 镜像面：放回最后已知世界位置 + 入参零修改（K2）。"""
    items = {
        "crate": ItemState(
            id="crate",
            name="板条箱",
            position={"x": 3, "y": 1, "z": 0},
        ),
    }
    positions = {"npc_1": {"x": 0, "y": 0, "z": 0}}
    positions_snapshot = {k: dict(v) for k, v in positions.items()}
    new_items, new_positions, events = apply_drop(
        items, positions, "npc_1", "crate", 9,
    )
    # 放回最后已知世界位置（ItemState.position 快照）。
    assert new_positions == {
        "npc_1": {"x": 0, "y": 0, "z": 0},
        "crate": {"x": 3, "y": 1, "z": 0},
    }
    # 零别名：返回的位置 dict 独立于 ItemState.position。
    new_positions["crate"]["x"] = 99
    assert new_items["crate"].position == {"x": 3, "y": 1, "z": 0}
    # items 内容不变 + 新 dict。
    assert new_items is not items
    assert new_items == items
    # K2：入参零修改。
    assert positions == positions_snapshot
    # 事件 str 逐字钉。
    assert events == ("[放下] npc_1 放下了 板条箱",)
    # 确定性错误：item_id 缺席 / position is None（message 逐字钉）。
    with pytest.raises(ValueError, match="不存在，无法放下"):
        apply_drop(items, positions, "npc_1", "ghost", 9)
    held = {"held": ItemState(id="held", name="持物")}
    with pytest.raises(ValueError, match="无世界位置快照，无法放下"):
        apply_drop(held, positions, "npc_1", "held", 9)


def test_inventory_t6_item_summary() -> None:
    """6) prompt 文本确定性 + id 升序键序 + state 扁平串原样呈现。"""
    items = {
        "z_door": ItemState(
            id="z_door",
            name="铁门",
            state="closed=true,unlocked=false",
        ),
        "a_crystal": ItemState(id="a_crystal", name="发光水晶"),
    }
    text = item_summary(items, "player_1")
    # 键序钉：id 升序（a_crystal 先于 z_door）；state 非 None →
    # 扁平串原样呈现（不解析、不回译）。
    assert text == (
        "items: a_crystal=发光水晶; "
        "z_door=铁门 (state=closed=true,unlocked=false)"
    )
    # 同输入两次调用同串（确定性）。
    assert item_summary(items, "player_1") == text
    # scope_id 零消费面：不同 scope_id 输出同串。
    assert item_summary(items, "npc_1") == text
    # 空集面。
    assert item_summary({}, "player_1") == "items: (空)"
