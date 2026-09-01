"""P9 W2 官方模块：inventory（T03；SOT §3.3；导出 7 名）。

来源 = v1 objects（src/models/world.py ``WorldObject`` 族，:24）+ v1 规则
``rules.py`` 编号 1–5（负重 :169 / 门锁 :190 等）；43.2-4「fixed
six action types」移除 → 物品操作 = 项目声明动作（SOT §3.9）。

冻结消费（SOT §3.0 导入闭集）：stdlib + 模块公共面 ``modules.base``
（``ModuleIdentity`` / ``OFFICIAL_MODULE_VERSION``）。本模块**不 import**
``modules.attributes``——``requires = ("llmsim-standard-attributes",)`` =
声明面（SOT §3.1.2 表，宿主校验用）；负重上限 strength×50.0 由调用侧经
attributes 模块面取值后构造 ``CarryLimit``（v1 ``STRENGTH_TO_KG_FACTOR``
= 50.0，rules.py:9）。

纪律（K2/D6）：全部函数为纯函数——返回新 Mapping / 新元组，不修改入参；
零模块级可变对象；零 wall-clock / 全局 RNG；零推理消费。
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from src.engine_v2.modules.base import OFFICIAL_MODULE_VERSION, ModuleIdentity

__all__ = [
    "ItemState",
    "CarryLimit",
    "CarryCheck",
    "can_carry",
    "apply_pickup",
    "apply_drop",
    "item_summary",
]

#: 模块身份（SOT §3.1.2 MODULE_REQUIRES 表：inventory 负重上限读
#: strength 属性 → requires = ("llmsim-standard-attributes",)；声明面，
#: 宿主校验用——本模块零 attributes import，函数签名零 attributes 类型）。
IDENTITY: Final[ModuleIdentity] = ModuleIdentity(
    "llmsim-standard-inventory",
    OFFICIAL_MODULE_VERSION,
    ("llmsim-standard-attributes",),
)


@dataclass(frozen=True)
class ItemState:
    """v1 object dict 的冻结 dataclass 化（零可变；SOT §3.3 表行 1）。

    形状对齐目标 = P5 冻结面 ``ObjectSpec``（schemas.py:187–200）；字段
    序以 SOT §3.3 为准（id/name 居前，与 ``ObjectSpec`` 不同序）。
    ``state`` = 扁平 str（SOT §3.15.2 M-4 折叠规范：v1 dict
    ``{closed: true, unlocked: true}``（test_empty.yaml:40–42）→
    ``"closed=true,unlocked=true"``；消费侧原样呈现，零解析、不回译）。
    ``properties`` 开放（D-P5-05 豁免）。
    ERR-P9-08 更正面（SOT 正文已落）：``position`` 缺省 ``None`` /
    ``properties`` 缺省 ``field(default_factory=dict)``（字段名/型/序零改）。
    """

    id: str
    name: str
    description: str = ""
    object_type: str = ""
    position: Mapping[str, int] | None = None
    state: str | None = None
    properties: Mapping[str, object] = dataclasses.field(default_factory=dict)


@dataclass(frozen=True)
class CarryLimit:
    """对齐 v1 src/game/rules.py:9（``STRENGTH_TO_KG_FACTOR`` = 50.0）。

    负重上限 = strength × 50.0。本模块不实现 strength 读取；调用侧经
    attributes 模块面取值后构造本 struct（requires 声明面，SOT §3.1.2 表）。
    """

    max_kg: float


@dataclass(frozen=True)
class CarryCheck:
    """v1 规则 3（strength_vs_weight）判定结果（SOT §3.3 表行 3）。

    v2 差异（对齐范围，D1）：v1 有 blocked / uncertain /（放行）三面；
    v2 = 布尔面（``allowed`` + ``reason``）。v1 uncertain 带
    （rules.py:180–187，success_probability / requires_roll 面）在 v2 布尔
    面无对应——SOT ``CarryCheck`` 设计即布尔（D-P9 裁决面）。
    """

    allowed: bool
    reason: str
    used_kg: float
    limit_kg: float


def can_carry(
    items: Mapping[str, ItemState],
    actor_id: str,
    target: str,
    limit: CarryLimit,
) -> CarryCheck:
    """对齐 v1 src/game/rules.py:169（规则 3 strength_vs_weight 门，
    :166–187 块）。

    纯判定（零状态变更）：``weight = items[target].properties[
    "weight_kg"]``（v1 同名键 rules.py:168）；``weight <= limit →
    allowed``（v1 仅 ``capacity < weight`` 时 blocked，相等放行，
    rules.py:174）。``used_kg`` = 该 weight（无重量数据 → 0.0）；
    ``limit_kg`` = ``limit.max_kg``。
    对齐范围（D1）：v1 uncertain 带（rules.py:180–187，
    success_probability / requires_roll）在 v2 布尔面无对应——v2 仅承载
    blocked / 放行二面。
    v2 差异：

    - ``weight_kg`` 缺失 / 非数值（含 bool）→ ``allowed=True``（v1 :169
      ``weight is not None`` 门，无规则 = 放行；v1 非数值会 ``float()``
      异常，v2 防御性放行（bool 排除出数值面）= 收窄面）；
    - ``actor_id`` = 签名面保留（strength×50 面已承载于
      ``CarryLimit``；当前未消费）；
    - target 缺席 → ``KeyError``（v1 宿主侧「目标不存在」警告面不迁移）。
    """
    limit_kg = float(limit.max_kg)
    weight = items[target].properties.get("weight_kg")
    if isinstance(weight, bool) or not isinstance(weight, (int, float)):
        return CarryCheck(
            allowed=True,
            reason="无重量数据，负重规则未触发",
            used_kg=0.0,
            limit_kg=limit_kg,
        )
    weight_kg = float(weight)
    if weight_kg <= limit_kg:
        return CarryCheck(
            allowed=True,
            reason="负重充足",
            used_kg=weight_kg,
            limit_kg=limit_kg,
        )
    return CarryCheck(
        allowed=False,
        reason=f"负重超限：目标重 {weight_kg:g}kg > 上限 {limit_kg:g}kg",
        used_kg=weight_kg,
        limit_kg=limit_kg,
    )


def apply_pickup(
    items: Mapping[str, ItemState],
    positions: Mapping[str, Mapping[str, int]],
    actor_id: str,
    item_id: str,
    tick: int,
) -> tuple[dict[str, ItemState], dict[str, Mapping[str, int]], tuple[str, ...]]:
    """对齐 v1 src/game/state_apply.py:53（玩家拾取事件面；NPC 镜像 :180）。

    零直写（K2）：返回 (新 items Mapping, 新 positions Mapping, 事件 str
    元组)；入参 dict 零修改。``positions`` = 世界位置注册表（entity_id →
    位置 Mapping，SOT §3.6 ``world_positions`` 同面惯例）：pickup = 物品
    离开世界位置 → 返回 positions = 输入去掉 ``item_id`` 条目。返回
    items = 新 dict，各 ``ItemState`` 内容不变（含 ``position`` 字段——
    最后已知世界位置快照，供 ``apply_drop`` 镜像放回）。
    事件 = v1 风格 str 元组（措辞 v2 新定：含 actor_id 与物品名；确定性，
    测试逐字钉）。
    v2 差异（确定性错误，经 deviations 披露）：

    - ``item_id`` 不在 items → ``ValueError``（message 逐字钉）；
    - ``actor_id`` 承载于事件措辞（通用 actor；v1 = 玩家 / NPC 双措辞面，
      :53 / :180）；
    - ``tick`` = 签名面保留（事件流时间戳槽位；本函数当前未消费）。
    """
    if item_id not in items:
        raise ValueError(f"物品 {item_id!r} 不存在，无法拾取")
    item = items[item_id]
    new_items = dict(items)
    new_positions = {
        key: pos for key, pos in positions.items() if key != item_id
    }
    event = f"[拾取] {actor_id} 拾取了 {item.name}"
    return new_items, new_positions, (event,)


def apply_drop(
    items: Mapping[str, ItemState],
    positions: Mapping[str, Mapping[str, int]],
    actor_id: str,
    item_id: str,
    tick: int,
) -> tuple[dict[str, ItemState], dict[str, Mapping[str, int]], tuple[str, ...]]:
    """v2 新增 / 无 v1 对齐面（43.2-4 移除 fixed six action types；v1 状态
    应用层无 drop 逻辑）。

    ``apply_pickup`` 同形镜像（K2 零直写）：返回 positions = 输入
    positions + ``{item_id: items[item_id].position}``（物品放回最后已知
    世界位置；位置 dict 独立拷贝，零别名）；items 内容不变（新 dict）。
    事件 = v1 风格 str 元组（措辞 v2 新定：含 actor_id 与物品名；
    确定性，测试逐字钉）。
    确定性错误（经 deviations 披露）：

    - ``item_id`` 不在 items → ``ValueError``（message 逐字钉）；
    - ``ItemState.position is None`` → ``ValueError``（无最后已知世界
      位置快照，无法放回）。
    ``tick`` = 签名面保留（同 ``apply_pickup``；当前未消费）。
    """
    if item_id not in items:
        raise ValueError(f"物品 {item_id!r} 不存在，无法放下")
    item = items[item_id]
    if item.position is None:
        raise ValueError(f"物品 {item_id!r} 无世界位置快照，无法放下")
    new_items = dict(items)
    new_positions = dict(positions)
    new_positions[item_id] = dict(item.position)
    event = f"[放下] {actor_id} 放下了 {item.name}"
    return new_items, new_positions, (event,)


def item_summary(items: Mapping[str, ItemState], scope_id: str) -> str:
    """v2 新增 / 无 v1 对齐面（v1 无物品 prompt 摘要函数面）。

    确定性 prompt 文本（SOT §3.3 表行 7：键序 sorted；state 扁平串原样
    呈现——不解析、不回译）。按 ``sorted(items)``（id 序）遍历全部物品。
    格式钉（W2）：``items: id=name`` 条目以 ``"; "`` 连接；``state`` 非
    ``None`` 时 → ``id=name (state=<扁平串>)``；空集 → ``items: (空)``。
    ``scope_id`` = 签名面保留（视角持有者槽位；当前未消费——输出不含该值，
    零消费）。
    """
    entries = [
        f"{item.id}={item.name} (state={item.state})"
        if item.state is not None
        else f"{item.id}={item.name}"
        for key in sorted(items)
        for item in (items[key],)
    ]
    if not entries:
        return "items: (空)"
    return "items: " + "; ".join(entries)
