"""P9 W2 relationships 模块单测（SOT §6.1：t1–t4 共 4 函数；T04）。

设计依据 = ``docs/v2/contracts/P9-official-modules-migration-design.md``
§3.4（函数级锚表）+ §6.1（测试表）+ SOT §8.4（DEV-P9-05 夹取面 / 差分
覆盖边界）+ SOT §8.1（K2 零直写钉面）。

零 fixture 引用（纯 stdlib 数据面，W2 派工决定）；全部入参 = 本地字面量
构造，不引用 conftest fixture。

覆盖项（每项独立 test 函数）：

1. t1_init_from_v1_dict：v1 dict（whisperheads.yaml:373–380 形状样例，
   7 条真实值）→ 有序元组（target_id 升序钉 + 各 affinity 钉值 +
   holder_id 面）+ init 面夹取（DEV-P9-05）；
2. t2_adjust_clamped：越界夹取 [-1, 1]（DEV-P9-05 面：0.8 + 0.5 →
   1.0；-0.9 - 0.5 → -1.0）+ 事件面（old/new/reason/tick 钉）+ 入参
   零修改（K2）；
3. t3_adjust_new_target：缺席目标新建（初值 0.0 → 0.0 + delta 夹取；
   old = 0.0 钉；返回元组保持排序位钉）；
4. t4_summary：prompt 文本确定性（同输入两次同串）+ holder 视角过滤面
   + 排序钉 + 格式逐字钉 + 空集面。
"""

from __future__ import annotations

from src.engine_v2.modules.relationships import (
    RelationshipEvent,
    RelationshipState,
    adjust_relationship,
    init_relationships,
    relationship_summary,
)


def test_relationships_t1_init_from_v1_dict() -> None:
    """1) v1 dict（whisperheads.yaml:373–380 形状样例，7 条真实值）→ 有序元组。"""
    # v1 角色 yaml relationships dict（whisperheads.yaml:373–380 逐字值）。
    entries = {
        "garviel_loken": 0.95,
        "xavyer_jubal": 0.4,
        "kyril_sindermann": 0.6,
        "euphrati_keeler": 0.2,
        "ignace_karkasy": 0.0,
        "rassek": 0.7,
        "maloghurst": 0.3,
    }
    states = init_relationships(entries, "player_1")
    assert isinstance(states, tuple)
    # target_id 升序钉（确定性序）。
    assert [s.target_id for s in states] == [
        "euphrati_keeler",
        "garviel_loken",
        "ignace_karkasy",
        "kyril_sindermann",
        "maloghurst",
        "rassek",
        "xavyer_jubal",
    ]
    # 各 affinity 钉值 + holder_id 面。
    expected = {
        "euphrati_keeler": 0.2,
        "garviel_loken": 0.95,
        "ignace_karkasy": 0.0,
        "kyril_sindermann": 0.6,
        "maloghurst": 0.3,
        "rassek": 0.7,
        "xavyer_jubal": 0.4,
    }
    for state in states:
        assert state.holder_id == "player_1"
        assert state.affinity == expected[state.target_id]
    # init 面夹取（DEV-P9-05，SOT §8.4）：越界值 → [-1, 1]。
    clamped = init_relationships({"hot": 1.5, "cold": -2.0}, "player_1")
    assert [s.affinity for s in clamped] == [-1.0, 1.0]
    assert [s.holder_id for s in clamped] == ["player_1", "player_1"]


def test_relationships_t2_adjust_clamped() -> None:
    """2) 越界夹取 [-1, 1]（DEV-P9-05 面）+ 事件面 + 入参零修改（K2）。"""
    states = init_relationships(
        {"garviel_loken": 0.8, "euphrati_keeler": -0.9}, "player_1",
    )
    new_states, event = adjust_relationship(
        states, "player_1", "garviel_loken", 0.5, "battle_bond", 12,
    )
    # 0.8 + 0.5 = 1.3 → 夹取 1.0（上界）。
    by_target = {s.target_id: s.affinity for s in new_states}
    assert by_target["garviel_loken"] == 1.0
    # 其余条目原样（值不变）。
    assert by_target["euphrati_keeler"] == -0.9
    # 事件面逐字钉（old = 调整前；new = 夹取后；reason / tick 透传）。
    assert event == RelationshipEvent(
        holder_id="player_1",
        target_id="garviel_loken",
        old=0.8,
        new=1.0,
        reason="battle_bond",
        tick=12,
    )
    # K2：入参零修改。
    assert [s.affinity for s in states] == [-0.9, 0.8]
    # 下界：-0.9 - 0.5 = -1.4 → 夹取 -1.0。
    new_states2, event2 = adjust_relationship(
        states, "player_1", "euphrati_keeler", -0.5, "betrayal", 13,
    )
    assert {s.target_id: s.affinity for s in new_states2} == {
        "garviel_loken": 0.8,
        "euphrati_keeler": -1.0,
    }
    assert event2.old == -0.9
    assert event2.new == -1.0
    assert event2.reason == "betrayal"
    assert event2.tick == 13
    # K2：入参仍然零修改（二次调整后复查）。
    assert [s.affinity for s in states] == [-0.9, 0.8]


def test_relationships_t3_adjust_new_target() -> None:
    """3) 缺席目标新建（初值 0.0）+ old = 0.0 钉 + 排序位钉。"""
    states = init_relationships(
        {"garviel_loken": 0.5, "rassek": 0.7}, "player_1",
    )
    new_states, event = adjust_relationship(
        states, "player_1", "kyril_sindermann", 0.6, "first_meet", 3,
    )
    # 缺席 → 新建（affinity 初值 0.0；old = 0.0 钉）。
    assert event == RelationshipEvent(
        holder_id="player_1",
        target_id="kyril_sindermann",
        old=0.0,
        new=0.6,
        reason="first_meet",
        tick=3,
    )
    # 返回元组保持 target_id 升序（新建目标插入排序位：g < k < r）。
    assert [s.target_id for s in new_states] == [
        "garviel_loken",
        "kyril_sindermann",
        "rassek",
    ]
    new_entry = new_states[1]
    assert new_entry.holder_id == "player_1"
    assert new_entry.affinity == 0.6
    # 缺席 + 越界：初值 0.0 + 2.0 = 2.0 → 夹取 1.0。
    new_states2, event2 = adjust_relationship(
        states, "player_1", "zeta", 2.0, "huge_gift", 4,
    )
    assert event2.old == 0.0
    assert event2.new == 1.0
    assert [s.target_id for s in new_states2] == [
        "garviel_loken",
        "rassek",
        "zeta",
    ]


def test_relationships_t4_summary() -> None:
    """4) prompt 文本确定性 + holder 视角过滤 + 排序 + 格式逐字钉。"""
    states = (
        RelationshipState("player_1", "garviel_loken", 0.95),
        RelationshipState("player_1", "euphrati_keeler", 0.2),
        # 他 holder 条目：holder 视角过滤面（player_1 摘要零出现）。
        RelationshipState("npc_1", "player_1", -0.5),
    )
    text = relationship_summary(states, "player_1")
    # 排序钉（euphrati_keeler < garviel_loken）+ 格式逐字钉
    # （affinity 数值 :g 格式）。
    assert text == (
        "relationships[player_1]: "
        "euphrati_keeler=0.2; garviel_loken=0.95"
    )
    # 同输入两次调用同串（确定性）。
    assert relationship_summary(states, "player_1") == text
    # holder 视角过滤面：npc_1 视角仅其自身条目。
    assert relationship_summary(states, "npc_1") == (
        "relationships[npc_1]: player_1=-0.5"
    )
    # 空集面（该 holder 无任何条目）。
    assert relationship_summary(states, "ghost") == (
        "relationships[ghost]: (空)"
    )
