"""engine_v2 core 层 Capability 授权表：能力 token、单条授权、授权表与读门判定
（P4-T03，§3.5）。

依据 ``docs/v2/contracts/P4-actor-context-space-mode-design.md``（下称"设计文档"）：

- **§3.5（全量）**：本模块 6 个导出符号——:class:`Capability` /
  :class:`CapabilityGrant` / :class:`CapabilityTable` / :func:`check_capability` /
  :data:`DEFAULT_NPC_CAPABILITIES` / :class:`CapabilityScopeError`；
- **Spec:884-892（§2.1 Spec 映射表）**：8 个能力 token → :class:`Capability`
  （str-Enum 保证 JSON/比较透明），值逐字；
- **Spec:895-899**：:data:`DEFAULT_NPC_CAPABILITIES` = "Observation + Knowledge +
  Memory" 3 元集逐字映射；
- **C-INV-1（§3.5 构造期不变量）**：``(actor_id, capability)`` 组合重复 →
  :class:`CapabilityScopeError`（静默覆盖 = KBC 类陷阱，数据层拒绝）；直接
  构造路径抛具名类型（:meth:`CapabilityTable.__init__`），pydantic 校验路径
  （``model_validate`` / ``model_validate_json``）由 pydantic 重抛为
  ``ValidationError``（ValueError 子类，同族口径，D-P4-17），C-INV-1 文案保留；
- **D-P4-06**：``world.read.local`` 的 scope 约定键为 ``{"radius": int ≥ 1}`` /
  ``{"domain": str}`` / 两者 / 缺省；无 scope（None）= 该 capability 的全量
  授权；其余 capability 的 scope 由使用方约定，P4 不解释（JSON 不透明值）；
- **D-P4-08（capability ⊥ authority，INV-P4-4）**：本模块只门控决策面读（context
  能看见什么）；与 authority 零 import 边，grant 不授予写权；
- **D-P4-17**：:class:`CapabilityScopeError` 归 ValueError 族（输入/配置违反
  不变式），测试按族断言基类；
- **INV-P4-3**：:class:`CapabilityTable` 为构造期注入的不可变配置（K7：重对象 =
  构造期配置）；无模块级可变全局、无单例注册表。

Import 边界（设计文档 §3.3 依赖图 / §3.4 黑名单）：本模块只 import 标准库、
pydantic 与同包 ``src.engine_v2``（entity → ContractModel；ids → EntityId；
actions → ActionTypeId）；asyncio / random / datetime / time / uuid / json 直接
import / os / subprocess / 网络栈全部缺席；M1④ 封闭 12 标识符集 0 命中。
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Final

from pydantic import JsonValue, ValidationError, model_validator

from src.engine_v2.core.actions import ActionTypeId
from src.engine_v2.core.entity import ContractModel
from src.engine_v2.core.ids import EntityId

__all__ = [
    "Capability",
    "CapabilityGrant",
    "CapabilityTable",
    "check_capability",
    "DEFAULT_NPC_CAPABILITIES",
    "CapabilityScopeError",
]


class Capability(str, Enum):
    """8 能力 token（Spec:884-892 逐字；str-Enum 保证 JSON/比较透明）。"""

    OBSERVATION_READ = "observation.read"
    KNOWLEDGE_READ = "knowledge.read"
    MEMORY_READ = "memory.read"
    WORLD_READ_LOCAL = "world.read.local"
    WORLD_READ_GLOBAL = "world.read.global"
    PHYSICS_SUMMARY = "physics.summary"
    PHYSICS_RAW = "physics.raw"
    TRACE_READ = "trace.read"


class CapabilityGrant(ContractModel):
    """单条授权：actor × capability × 可选 scope。

    - ``scope``：JSON 不透明值；``world.read.local`` 约定键
      ``{"radius": int ≥ 1}`` / ``{"domain": str}`` / 两者 / 缺省（D-P4-06）；
      其余 capability 的 scope 由使用方约定，P4 不解释；
    - 无 scope（None）= 该 capability 的全量授权。
    """

    actor_id: EntityId
    capability: Capability
    scope: JsonValue | None = None


def _check_grants_unique(grants: tuple[CapabilityGrant, ...]) -> None:
    """C-INV-1：``(actor_id, capability)`` 组合重复在数据层拒绝。

    静默覆盖 = KBC 类陷阱（后值无声吞掉前值的 scope 差异），构造期即报错。
    """
    seen: set[tuple[EntityId, Capability]] = set()
    for grant in grants:
        key = (grant.actor_id, grant.capability)
        if key in seen:
            raise CapabilityScopeError(
                f"C-INV-1 违反：grants 中 (actor_id, capability) 组合 {key!r} 重复"
            )
        seen.add(key)


def _c_inv_1_message(exc: ValidationError) -> str | None:
    """从 pydantic 重抛的 ``ValidationError`` 中取出 C-INV-1 原文；其余校验错误返回 None。"""
    for error in exc.errors():
        if error.get("type") == "value_error" and "C-INV-1" in str(error.get("msg", "")):
            msg = str(error.get("msg", ""))
            return msg.removeprefix("Value error, ") or msg
    return None


class CapabilityTable(ContractModel):
    """授权表（K7 配置面，INV-P4-3）。

    构造期不变量 **C-INV-1**：``(actor_id, capability)`` 组合重复 →
    :class:`CapabilityScopeError`（静默覆盖 = KBC 类陷阱，数据层拒绝）。
    """

    grants: tuple[CapabilityGrant, ...] = ()
    action_requirements: dict[ActionTypeId, tuple[Capability, ...]] = {}

    @model_validator(mode="after")
    def _check_grant_uniqueness(self) -> "CapabilityTable":
        """C-INV-1：(actor_id, capability) 组合重复在数据层拒绝（全部构造路径）。"""
        _check_grants_unique(self.grants)
        return self

    def __init__(self, /, **data: Any) -> None:
        """直接构造：C-INV-1 抛具名 :class:`CapabilityScopeError`（不静默、不包裹）。

        校验器在 ``super().__init__`` 的校验内运行，其抛出的
        :class:`CapabilityScopeError`（ValueError 族）会被 pydantic 重抛为
        ``ValidationError``——本覆盖将其还原为具名类型（其余校验错误原样
        穿透，不转换）。
        """
        try:
            super().__init__(**data)
        except ValidationError as exc:
            message = _c_inv_1_message(exc)
            if message is not None:
                raise CapabilityScopeError(message) from exc
            raise

    def grants_for(self, actor_id: EntityId) -> tuple[CapabilityGrant, ...]:
        """actor 的全部授权（保持 ``grants`` 插入顺序）。"""
        return tuple(grant for grant in self.grants if grant.actor_id == actor_id)

    def requires(self, action_id: ActionTypeId) -> tuple[Capability, ...]:
        """action 的 capability 要求；未注册 action = 空要求（恒满足）。"""
        return self.action_requirements.get(action_id, ())

    def satisfied(self, actor_id: EntityId, action_id: ActionTypeId) -> bool:
        """actor 对 action 的全部要求 capability 均已授权（scope 缺省检查）。"""
        return all(
            check_capability(self, actor_id, capability)
            for capability in self.requires(action_id)
        )


def _scope_covers(granted: JsonValue | None, requested: JsonValue | None) -> bool:
    """scope 覆盖判定（§3.5 覆盖语义，逐字落位）。

    - ``requested`` 为 None → 仅需授权存在（调用方已裁定存在性）；
    - ``granted`` 为 None → 全量授权，覆盖任意 ``requested``；
    - 双方 dict → ``requested`` 的每个键值对必须等于 ``granted`` 同键值
      （子集语义）；
    - 其余 → 逐字相等。
    """
    if requested is None or granted is None:
        return True
    if isinstance(granted, dict) and isinstance(requested, dict):
        return all(key in granted and granted[key] == value for key, value in requested.items())
    return granted == requested


def check_capability(
    table: CapabilityTable, actor_id: EntityId, capability: Capability, *,
    scope: JsonValue | None = None,
) -> bool:
    """核查：存在 (actor, capability) 授权且请求 scope 被授权 scope 覆盖。

    覆盖语义钉死：请求 scope 为 None → 仅需授权存在；双方均为 dict →
    请求的每个键值对必须等于授权同键值（子集语义）；非 dict → 逐字相等。
    未授权 / 覆盖不足 → False（不抛——读门是判定不是错误）。
    """
    for grant in table.grants_for(actor_id):
        if grant.capability == capability and _scope_covers(grant.scope, scope):
            return True
    return False


#: 普通 NPC 默认（Spec:895-899 "Observation + Knowledge + Memory" 逐字映射）
DEFAULT_NPC_CAPABILITIES: Final[frozenset[Capability]] = frozenset(
    {Capability.OBSERVATION_READ, Capability.KNOWLEDGE_READ, Capability.MEMORY_READ}
)


class CapabilityScopeError(ValueError):
    """C-INV-1 重复授权 / scope 结构非法。"""
