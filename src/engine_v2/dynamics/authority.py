"""P7-W4 producer 注册器 + 缺省权限策略构建器（SOT §3.7，T05；7 exports，
账本序 §8.2 钉死——``P7_PRODUCER_IDS`` 在首）。

P7 权限面 = **构建器 + 缺省值**（D-P7-08）：最终权限配置属 host——
``CascadeExecutor(policy=host_policy, producer_registry=host_registry)`` 的
装配是 host 的（SOT §3.7 引文块末段）。

两权分离（SOT §3.7 A7 引文块，机械核验依据）：authority 管**准入**
（``check_authority`` 首匹配拍板、无 fall-through），producer priority 管
**冲突裁决**（``ProducerPriorityStrategy``）；"physics wins by default" 语义
由 priority 承载（rule/rigid=100 > composite=80 > 推理=50），不由 authority
规则承载。

A7 策略链弃权序前提：Case B 双 effect 同组入 ``DefaultConflictResolver`` 四策
链——(1) ``AuthorityPriorityStrategy``：两 effect 同被**单条** priority=100
规则 ALLOW → rule_priority 并列 → 弃权；(2) ``TimestampStrategy``：P7 全部
effect 的 ``metadata`` 字段保持缺省 ``{}``（不注入任何 timestamp 键）→ 弃权；
(3) ``ProducerPriorityStrategy``：100 唯一最大 vs 50 → 拍板
WINNER=physics / REJECT=推理，strategy=``producer_priority``。此弃权序是 A7
成立的充分条件——本模块只产纯数据构建器，永不改写 effect 面（K4）。

纪律（SOT §0.5/§3.0）：K7 零墙钟 / 零随机 / 零模块级可变状态（全部常量
不可变）；K4 权限面永不写进 wire/effect。
"""

from __future__ import annotations

from typing import Final

from src.engine_v2.core.authority import (
    AuthorityPolicy,
    AuthorityRule,
    AuthoritySelector,
    ProducerInfo,
    ProducerRegistry,
)
from src.engine_v2.core.provenance import OriginKind

__all__ = [
    "P7_PRODUCER_IDS",
    "RULE_DYNAMICS_PRODUCER",
    "LLM_WORLD_DYNAMICS_PRODUCER",
    "RIGID_BODY_PRODUCER",
    "COMPOSITE_DYNAMICS_PRODUCER",
    "build_dynamics_producers",
    "default_dynamics_policy",
]

#: producer id 词表（SOT §3.7 代码块逐字；D-P7-08 定案；全 fullmatch
#: ``PRODUCER_ID_PATTERN`` core/ids.py L77；与 Spec §17.1 示例对齐）。
RULE_DYNAMICS_PRODUCER: Final[str] = "rule_dynamics"
LLM_WORLD_DYNAMICS_PRODUCER: Final[str] = "llm_world_dynamics"
RIGID_BODY_PRODUCER: Final[str] = "rigid_body"
COMPOSITE_DYNAMICS_PRODUCER: Final[str] = "composite_dynamics"
P7_PRODUCER_IDS: Final[tuple[str, ...]] = (
    "rule_dynamics",
    "llm_world_dynamics",
    "rigid_body",
    "composite_dynamics",
)

#: 缺省 priority（SOT §3.7：rule=100 / rigid=100 / composite=80 / 推理=50；
#: 缺省序 **物理/规则 > 推理** = Case B 裁决输入；host 可另构 registry 覆盖）。
_DEFAULT_PRODUCER_PRIORITIES: Final[tuple[tuple[str, int], ...]] = (
    (RULE_DYNAMICS_PRODUCER, 100),
    (RIGID_BODY_PRODUCER, 100),
    (COMPOSITE_DYNAMICS_PRODUCER, 80),
    (LLM_WORLD_DYNAMICS_PRODUCER, 50),
)

#: 缺省单规则并集放行 writer 序（SOT §3.7 代码块逐字）。
_DEFAULT_ALLOWED_WRITERS: Final[tuple[str, ...]] = (
    RULE_DYNAMICS_PRODUCER,
    RIGID_BODY_PRODUCER,
    LLM_WORLD_DYNAMICS_PRODUCER,
    COMPOSITE_DYNAMICS_PRODUCER,
)


def build_dynamics_producers() -> ProducerRegistry:
    """注册 4 个 P7 producer（origin=``DYNAMICS_BACKEND``；priority SOT 钉死）。

    ``rule_dynamics``=100 / ``rigid_body``=100 / ``composite_dynamics``=80 /
    ``llm_world_dynamics``=50。未注册 producer ≠ 错误（core 语义：
    ``priority_of`` 缺省归 0、``origin_of`` 缺省 SYSTEM）——closed-by-default
    下其权限完全由 host policy 规则拍板。
    """
    registry = ProducerRegistry()
    for producer_id, priority in _DEFAULT_PRODUCER_PRIORITIES:
        registry.register(
            ProducerInfo(
                producer_id=producer_id,
                origin=OriginKind.DYNAMICS_BACKEND,
                priority=priority,
            )
        )
    return registry


def default_dynamics_policy(*, component_types: tuple[str, ...] = ()) -> AuthorityPolicy:
    """closed-by-default 基座 + 对每个声明组件类型**一条**并集放行规则。

    每规则：``AuthoritySelector(component_type=ct)`` + ``allowed_writers`` =
    4 P7 producer（并集）+ ``priority=100``。

    单规则并集放行依据（SOT §3.7 引文块）：``check_authority`` 首匹配拍板、
    无 fall-through——若拆 "物理规则 + 推理规则" 两条同 selector 规则，推理
    effect 先撞物理规则即 ``rule_deny``，两个 ProposedEffect 不可同场（违反
    Case B "必须可见两个"）。故单规则并集放行，**裁决权交给冲突层**
    ``ProducerPriorityStrategy``（registry priority 100 vs 50 唯一最大 →
    物理胜）——两权分离（authority 管准入，priority 管裁决），host 可分别覆盖。

    空 ``component_types`` = 完全封闭（零规则：任何 effect → ``default_decision``
    DENY / ``no_matching_rule``）。
    """
    rules = [
        AuthorityRule(
            selector=AuthoritySelector(component_type=ct),
            allowed_writers=list(_DEFAULT_ALLOWED_WRITERS),
            priority=100,
        )
        for ct in component_types
    ]
    return AuthorityPolicy(rules=rules)
