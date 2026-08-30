"""P4 Wave D 模块单测：``capability.py``（设计文档 §3.5 全量 + 单测口径行 L261 + §6.1 L1652 行）。

依据 ``docs/v2/contracts/P4-actor-context-space-mode-design.md``（下称"设计文档"）：

- **§3.5 代码块（L201-262）**：6 导出 Capability / CapabilityGrant /
  CapabilityTable / check_capability / DEFAULT_NPC_CAPABILITIES /
  CapabilityScopeError；构造期不变量 **C-INV-1**（(actor_id, capability) 组合
  重复 → CapabilityScopeError，静默覆盖 = KBC 类陷阱，数据层拒绝）；覆盖语义
  钉死（请求 scope None → 仅需授权存在；双方 dict → 子集语义；非 dict → 逐字
  相等；未授权/覆盖不足 → False，不抛）；
- **单测口径行（L261）**：8 token 逐字断言（值集合 + 字符串相等）；C-INV-1
  重复 → CapabilityScopeError；satisfied 全满足/缺一/空要求三态；
  check_capability scope 子集四态（None/None、dict⊆dict、dict⊄dict、非 dict
  相等/不等）；DEFAULT_NPC_CAPABILITIES == 3 元集；
- **§6.1 模块单测表（L1652 行）**：C-INV-1（组合重复 → CapabilityScopeError）；
  check_capability 子集语义（actor 无 grant / grant 为请求真子集 → False）；
  DEFAULT_NPC_CAPABILITIES 恰 3 权（Spec:895-899）；CapabilityTable 序列化
  往返；8 token 全集（Spec:884-892）逐值核对；
- **Spec:884-892**（主规范 ``docs/plans/llmBasedSim_Engine_Architecture_v2_Spec.md``
  §13.2 逐字）：8 个能力 token；
- **Spec:895-899**：普通 NPC 默认 "Observation + Knowledge + Memory" 3 元集
  逐字映射；
- **D-P4-08（capability ⊥ authority，双门正交）**：capability 只门控 context
  构建（策略能看见什么）；与 authority 零 import 边，grant 不授予写权
  （INV-P4-4，写授权唯一来源为 P2 authority，K4 Spec:295-303）——本文件不
  import authority、不构造任何写授权断言（注释引口径；A8 AST 依赖方向检查
  属 test_import_boundary.py 覆盖面，不在此重复）；
- **D-P4-17**：CapabilityScopeError 归 ValueError 族，测试按族断言基类。

覆盖项（逐项对应独立 test_ 函数）：

1. ``test_capability_enum_exactly_8_tokens``：Capability 恰 8 成员；值集合与
   §3.5 代码块（Spec:884-892）逐值相等（含成员名→值映射）；全部为 str
   实例；
2. ``test_c_inv_1_duplicate_grant_rejected``：(actor_id, capability) 组合
   重复 → 直接构造抛具名 CapabilityScopeError（消息含 C-INV-1 标记，D-P4-17
   按族断言 ValueError 基类）；model_validate 路径 → ValidationError
   （同族口径，C-INV-1 文案保留）；
3. ``test_satisfied_three_states``：全部要求满足 → True；缺一 → False；
   空要求（未注册 action / 注册零要求）→ True；
4. ``test_check_capability_scope_subset_four_states``：(None, None) → True；
   dict⊆dict → True；dict⊄dict → False；非 dict 相等 → True / 不等 →
   False；actor 无 grant → False；
5. ``test_default_npc_capabilities_exact_three``：DEFAULT_NPC_CAPABILITIES
   == 恰 3 权 frozenset（Spec:895-899 逐值核对）；
6. ``test_capability_table_serialization_roundtrip``：CapabilityTable 序列化
   往返（§6.1 L1652 行"CapabilityTable 序列化往返"；实际序列化面口径见函数
   内注释）。

布局：``tests/engine_v2/core/``；直接从子模块 import，不经包级导出；全部用例
无网络、无 LLM、无 API key；确定性构造（EntityId / ActionTypeId 构造函数不
做词法校验，设计文档 §2.2 通用规则）。
"""

from __future__ import annotations

import pytest
from pydantic import JsonValue, ValidationError

from src.engine_v2.core.actions import ActionTypeId
from src.engine_v2.core.capability import (
    DEFAULT_NPC_CAPABILITIES,
    Capability,
    CapabilityGrant,
    CapabilityScopeError,
    CapabilityTable,
    check_capability,
)
from src.engine_v2.core.ids import EntityId

# —— 样本工厂（自包含、确定性构造）——


def _grant(
    actor: EntityId, capability: Capability, scope: JsonValue | None = None
) -> CapabilityGrant:
    return CapabilityGrant(actor_id=actor, capability=capability, scope=scope)


ALICE = EntityId("ent_alice")
BOB = EntityId("ent_bob")
ATTACK = ActionTypeId("combat.attack")
LOCAL_READ = Capability.WORLD_READ_LOCAL


def test_capability_enum_exactly_8_tokens() -> None:
    """覆盖项 1：8 token 逐字断言（§3.5 代码块 / Spec:884-892）。"""
    # 恰 8 成员
    members = list(Capability)
    assert len(members) == 8
    # 值集合与 §3.5 代码块（Spec:884-892 逐字）逐值相等
    assert {member.value for member in members} == {
        "observation.read",
        "knowledge.read",
        "memory.read",
        "world.read.local",
        "world.read.global",
        "physics.summary",
        "physics.raw",
        "trace.read",
    }
    # 成员名 → 值映射逐字（防值互换：8 成员 × 8 不同值一一对应）
    assert {member.name: member.value for member in members} == {
        "OBSERVATION_READ": "observation.read",
        "KNOWLEDGE_READ": "knowledge.read",
        "MEMORY_READ": "memory.read",
        "WORLD_READ_LOCAL": "world.read.local",
        "WORLD_READ_GLOBAL": "world.read.global",
        "PHYSICS_SUMMARY": "physics.summary",
        "PHYSICS_RAW": "physics.raw",
        "TRACE_READ": "trace.read",
    }
    # str-Enum：成员本身即 str 实例（JSON/比较透明，Spec 映射表口径）
    assert all(isinstance(member, str) for member in members)
    assert all(isinstance(member.value, str) for member in members)


def test_c_inv_1_duplicate_grant_rejected() -> None:
    """覆盖项 2：C-INV-1 (actor_id, capability) 组合重复（§3.5 / §6.1 L1652 行）。"""
    duplicate = (
        _grant(ALICE, Capability.OBSERVATION_READ),
        _grant(ALICE, Capability.OBSERVATION_READ, scope={"radius": 2}),
    )
    # 直接构造路径：抛具名类型（不静默、不包裹），消息含 C-INV-1 标记
    with pytest.raises(CapabilityScopeError, match="C-INV-1"):
        CapabilityTable(grants=duplicate)
    # D-P4-17：归 ValueError 族（按族断言基类）
    assert issubclass(CapabilityScopeError, ValueError)
    # pydantic 校验路径（model_validate）：重抛为 ValidationError（ValueError
    # 子类，同族口径 D-P4-17），C-INV-1 文案保留
    with pytest.raises(ValidationError) as excinfo:
        CapabilityTable.model_validate(
            {
                "grants": [
                    {"actor_id": "ent_alice", "capability": "observation.read"},
                    {
                        "actor_id": "ent_alice",
                        "capability": "observation.read",
                        "scope": {"radius": 2},
                    },
                ]
            }
        )
    assert "C-INV-1" in str(excinfo.value)


def test_satisfied_three_states() -> None:
    """覆盖项 3：satisfied 三态（§3.5 / 口径行 L261；scope 缺省检查）。"""
    # 全部要求满足 → True
    table_ok = CapabilityTable(
        grants=(
            _grant(BOB, Capability.PHYSICS_SUMMARY),
            _grant(BOB, Capability.TRACE_READ),
        ),
        action_requirements={ATTACK: (Capability.PHYSICS_SUMMARY, Capability.TRACE_READ)},
    )
    assert table_ok.satisfied(BOB, ATTACK) is True
    # 缺一 → False
    table_missing = CapabilityTable(
        grants=(_grant(BOB, Capability.PHYSICS_SUMMARY),),
        action_requirements={ATTACK: (Capability.PHYSICS_SUMMARY, Capability.TRACE_READ)},
    )
    assert table_missing.satisfied(BOB, ATTACK) is False
    # 空要求：未注册 action（requires → 空元组）→ True
    assert table_ok.satisfied(BOB, ActionTypeId("unregistered.act")) is True
    # 空要求：已注册但零要求 → True
    table_zero = CapabilityTable(action_requirements={ActionTypeId("zero.req"): ()})
    assert table_zero.satisfied(BOB, ActionTypeId("zero.req")) is True


def test_check_capability_scope_subset_four_states() -> None:
    """覆盖项 4：check_capability scope 子集四态（§3.5 覆盖语义钉死 / 口径行 L261）。"""
    # (None, None)：grant 无 scope（全量授权）、请求无 scope → 仅需授权存在 → True
    table_none = CapabilityTable(grants=(_grant(ALICE, LOCAL_READ),))
    assert check_capability(table_none, ALICE, LOCAL_READ) is True
    # 同形态补充：请求 None、grant 有 scope → 覆盖判定直接 True（§3.5："请求
    # scope 为 None → 仅需授权存在"）
    table_radius = CapabilityTable(
        grants=(_grant(ALICE, LOCAL_READ, scope={"radius": 5}),)
    )
    assert check_capability(table_radius, ALICE, LOCAL_READ) is True
    # dict ⊆ dict：请求每个键值对等于授权同键值（子集语义）→ True
    table_both = CapabilityTable(
        grants=(_grant(ALICE, LOCAL_READ, scope={"radius": 5, "domain": "market"}),)
    )
    assert check_capability(table_both, ALICE, LOCAL_READ, scope={"radius": 5}) is True
    assert (
        check_capability(table_both, ALICE, LOCAL_READ, scope={"radius": 5, "domain": "market"})
        is True
    )
    # dict ⊄ dict：值不匹配 / 请求键授权缺失 → False
    assert check_capability(table_both, ALICE, LOCAL_READ, scope={"radius": 6}) is False
    assert check_capability(table_both, ALICE, LOCAL_READ, scope={"domain": "docks"}) is False
    assert check_capability(table_both, ALICE, LOCAL_READ, scope={"nope": 1}) is False
    # 非 dict：逐字相等 → True；不等 → False
    table_str = CapabilityTable(
        grants=(_grant(ALICE, LOCAL_READ, scope="market"),)
    )
    assert check_capability(table_str, ALICE, LOCAL_READ, scope="market") is True
    assert check_capability(table_str, ALICE, LOCAL_READ, scope="docks") is False
    # actor 无 grant → False（读门是判定不是错误，不抛）
    nobody = EntityId("ent_nobody")
    assert check_capability(table_str, nobody, LOCAL_READ, scope="market") is False
    assert check_capability(table_str, nobody, LOCAL_READ) is False


def test_default_npc_capabilities_exact_three() -> None:
    """覆盖项 5：DEFAULT_NPC_CAPABILITIES 恰 3 权（Spec:895-899 逐值核对）。"""
    # Spec:895-899 "Observation + Knowledge + Memory" 逐字映射；恰 3 权
    assert isinstance(DEFAULT_NPC_CAPABILITIES, frozenset)
    assert len(DEFAULT_NPC_CAPABILITIES) == 3
    assert DEFAULT_NPC_CAPABILITIES == frozenset(
        {
            Capability.OBSERVATION_READ,
            Capability.KNOWLEDGE_READ,
            Capability.MEMORY_READ,
        }
    )
    # 值逐字核对（token 串相等，非仅枚举相等）
    assert {capability.value for capability in DEFAULT_NPC_CAPABILITIES} == {
        "observation.read",
        "knowledge.read",
        "memory.read",
    }


def test_capability_table_serialization_roundtrip() -> None:
    """覆盖项 6：CapabilityTable 序列化往返（§6.1 L1652 行）。

    实际序列化面口径（以源码为准）：``capability.py`` 不 import P1
    ``serialization.py``（该 helper 为测试侧工具，serialization.py:82 口径），
    亦禁 ``json`` 标准库直接 import（§3.4 黑名单）；模块自身的序列化面即
    pydantic ``model_dump`` / ``model_validate``（含 JSON 面
    ``model_dump_json`` / ``model_validate_json``），本测试按此面断言。
    """
    table = CapabilityTable(
        grants=(
            _grant(ALICE, Capability.WORLD_READ_LOCAL, scope={"radius": 5, "domain": "market"}),
            _grant(BOB, Capability.KNOWLEDGE_READ),
            _grant(BOB, Capability.MEMORY_READ, scope="short"),
        ),
        action_requirements={ATTACK: (Capability.PHYSICS_SUMMARY, Capability.TRACE_READ)},
    )
    # model_dump → model_validate → 相等（typed 子类重建：EntityId /
    # ActionTypeId / Capability 保持，dict 键经 model_validate 还原）
    restored = CapabilityTable.model_validate(table.model_dump())
    assert restored == table
    # JSON 面同口径往返
    json_restored = CapabilityTable.model_validate_json(table.model_dump_json())
    assert json_restored == table
    # 往返后行为不变（satisfied 判定面）
    assert restored.satisfied(BOB, ATTACK) is False
    assert json_restored.grants == table.grants
