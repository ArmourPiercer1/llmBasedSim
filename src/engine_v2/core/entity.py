"""engine_v2 core 层 Entity 身份记录 + 只读逻辑门面（P1-T03）。

依据 ``docs/v2/contracts/P1-core-data-contracts.md``（下称"设计文档"）§3：

- §3.1 :class:`EntityRecord`——存于 ``WorldState.entities``（T02）内的实体身份
  记录：稳定 identity + 其组件的归属点（Spec §10.1/§10.2）。数据记录，不是
  "活的"运行时对象——禁止任何代码持有跨 revision 的 entity 对象引用作为权威
  来源（规避 v1 KBC-3 陈旧数据进 prompt，设计文档 §9）；
- §3.2 :class:`EntityRef`（Spec §16.1 target 的 entity 分支）与
  :class:`EntityView`（只读逻辑门面，Spec §10.3）。门面**不提供**任何写方法；
  不绑定真实 ECS（Spec §10.3 / 决策 D-7）：公共 API 形态与底层存储（dict/
  table/ECS）解耦，P1 底层为 dict，未来替换不破坏本门面签名；
- §3.4 组件存储布局（决策 D-7）：组件数据**嵌入** EntityRecord
  （entity-centric），本模块 :class:`EntityRecord.components` 字段即其落位；
- §3.5 reducer-only 写入预留（P2 兼容保证）三条纪律：
  1. **零公共写 API**：:class:`ContractModel` ``frozen=True`` 阻断字段再赋值，
     :class:`EntityView` 为 frozen dataclass 且无任何写方法；
  2. **入口深拷贝**：一切外部数据经 ``model_validate``/构造函数进入即重建
     容器，调用方持有的可变 dict 不会被别名进状态树（T06 J3 口径，本模块
     测试有隔离用例）；
  3. **唯一变更缝隙**：``_with_*`` / ``_build_*`` 私有构造助手供测试与未来
     P2 reducer（``apply_transaction`` 唯一公共路径，Plan P2-T06）使用，
     **不得导出为公共 API**（私有前缀，不在 ``__all__``）。

:class:`ContractModel` 是 P1 全部数据契约模型的基类（设计文档 §0.1 统一模型
基类约定），按"core/_base.py 或各文件内联"在此内联；后续 T02/T04 模块可复用
或内联。本模块只 import 标准库与 pydantic（§0.3 import 边界白名单），不触碰 v1。
"""

from __future__ import annotations

import types
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from src.engine_v2.core.components import ComponentData, ComponentTypeId
from src.engine_v2.core.ids import EntityId
from src.engine_v2.core.revision import INITIAL_WORLD_REVISION, Revision

__all__ = [
    "ContractModel",
    "EntityRecord",
    "EntityRef",
    "EntityView",
]


class ContractModel(BaseModel):
    """P1 全部数据契约模型的基类（设计文档 §0.1 统一模型基类约定，此处内联）。

    - ``frozen=True``：字段不可再赋值（浅冻结；深层不变量见设计文档 §6.2
      D-15）——§3.5 纪律 1"零公共写 API"的数据层基础；
    - ``extra="forbid"``：未知字段立即报错——G1「Contract 冻结」的数据表达；
      存档前向兼容由迁移层（P8）负责版本转换，契约模型不静默吞掉未知字段
      （Plan S3）；
    - ``validate_assignment=True``：赋值路径（若存在）同样触发重校验。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        validate_assignment=True,
    )


# —— 私有构造/查询助手（§3.5 纪律 3：唯一变更缝隙；私有前缀，不导出）——


def _freeze_value(value: Any) -> Any:
    """递归深冻结一个 JSON 值（设计文档 §3.2 / §6.2 决策 D-15）。

    ``dict`` → :class:`types.MappingProxyType`（嵌套递归冻结），
    ``list``/``tuple`` → ``tuple``，标量/None 原样返回。深冻结视图是**咨询性**
    （advisory）不变量：强制性由 P2 写屏障 + reducer-only 公共 API 承担（D-15）。
    """
    if isinstance(value, dict):
        return types.MappingProxyType({k: _freeze_value(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_value(v) for v in value)
    return value


def _build_entities(records: Iterable[EntityRecord]) -> dict[EntityId, EntityRecord]:
    """私有构造助手（设计文档 §7.2 E4 / §3.5 纪律 3）：由 EntityRecord 序列组装 entities 映射。

    重复 ``entity_id`` **显式抛错**（``ValueError``）——dict 语义对重复键静默
    折叠（静默数据丢失，KBC 类陷阱），builder 必须拒绝（测试口径 E4）。
    供 T02 ``WorldState`` 构造与未来 P2 reducer 复用；不导出。
    """
    entities: dict[EntityId, EntityRecord] = {}
    for record in records:
        if record.entity_id in entities:
            raise ValueError(
                f"重复 EntityId：{str(record.entity_id)!r}——dict 语义会静默折叠"
                "重复键，builder 必须显式拒绝（E4）"
            )
        entities[record.entity_id] = record
    return entities


def _entity_ids_with_component(
    entities: Mapping[EntityId, EntityRecord], ct: ComponentTypeId
) -> tuple[EntityId, ...]:
    """私有查询助手（设计文档 §3.2 门面方法语义 / §7.2 E4）：返回挂载组件 ``ct`` 的 entity id 序列。

    纯函数；顺序 = entities 映射插入顺序（确定性）；无匹配返回空元组。
    供 T02 ``WorldState.entities_with_component()`` 委托；不导出。
    """
    return tuple(eid for eid, record in entities.items() if ct in record.components)


class EntityRecord(ContractModel):
    """Entity 身份记录（设计文档 §3.1；存于 ``WorldState.entities``，T02）。

    Entity 是**稳定 identity + 其组件的归属点**（Spec §10.1/§10.2）：

    - ``entity_class`` / ``tags``：P2 authority selector 预留（Spec §17.2
      明确 selector 可用 entity class/tag）；Kernel 不定义其取值词表；
    - ``created_revision``：entity 签发时的 world_revision；
    - ``components``：组件数据嵌入 EntityRecord（决策 D-7，§3.4，
      entity-centric）；未注册组件类型的数据同样按不透明 JSON dict 存储
      （决策 D-8，§3.3——本记录不持有 registry 引用，注册与否不影响存储）；
    - 数据记录，不是"活的"运行时对象：禁止持有跨 revision 的 entity 对象
      引用作为权威来源（KBC-3 防线，设计文档 §9）。

    §3.5 纪律 1：零公共写 API——``frozen=True`` 阻断字段再赋值；唯一变更缝隙
    是 :meth:`_with_components`（私有，不导出）。
    """

    entity_id: EntityId
    entity_class: str | None = None
    tags: list[str] = Field(default_factory=list)
    created_revision: Revision = INITIAL_WORLD_REVISION
    components: dict[ComponentTypeId, ComponentData] = Field(default_factory=dict)

    def _with_components(
        self, components: Mapping[ComponentTypeId, ComponentData]
    ) -> EntityRecord:
        """私有构造助手（§3.5 纪律 3）：返回替换 components 后的新 EntityRecord。

        - ``self`` 不变（frozen）；结果是全字段新容器的全新实例；
        - 新 ``components`` 经 ``model_validate`` 重建（纪律 2 入口深拷贝）：
          调用方持有的可变 Mapping 不被别名进新记录；
        - **整体替换**，不提供部分覆写——KBC-4（部分 dict 覆写丢字段）防线：
          组件数据一律以完整 payload 变更；
        - 供测试与未来 P2 reducer（``apply_transaction`` 唯一公共路径）使用；
          不导出。
        """
        payload = self.model_dump()
        payload["components"] = dict(components)
        return EntityRecord.model_validate(payload)


class EntityRef(ContractModel):
    """对 entity（及其可选的组件/字段）的引用（设计文档 §3.2；Spec §16.1 target 的 entity 分支）。

    - 纯引用数据：构造**不**校验 entity 存在性（非法引用的"判定"属 P2
      validation，设计文档 §7.2 E5）；门面查询对缺失目标安全返回 None，
      不抛未定义异常；
    - ``field_path``：字段级定位；Spec §17.2 警示脆弱裸路径——field_path 仅供
      schema 已注册的组件使用，P2 validation 按 schema 校验其合法性。
    """

    entity_id: EntityId
    component_type: ComponentTypeId | None = None
    field_path: str | None = None


@dataclass(frozen=True)
class EntityView:
    """只读逻辑门面（设计文档 §3.2；Spec §10.3：公共 API 只承诺 Entity + typed components）。

    - 由 ``WorldState`` 查询方法构造（T02，经私有缝隙 :meth:`_from_record`）；
      内部持有组件数据的 ``MappingProxyType`` **深冻结**视图（§3.2 docstring /
      §6.2 D-15），**不持有 WorldState 引用**——视图由构造时的 revision 派生并
      携带 ``revision`` 标记（视图有效性判据；KBC-3 防线，设计文档 §9）；
    - 不绑定真实 ECS（决策 D-7）：门面签名与底层存储解耦，未来换 table/ECS
      不破坏本签名；
    - 无任何写方法（§3.5 纪律 1）；frozen dataclass 阻断字段再赋值；
    - 值为 MappingProxyType 的成员使其**不可哈希**（与含 dict 的普通值对象
      同语义：按值相等可比较，``hash()`` 抛 ``TypeError``）。
    """

    entity_id: EntityId
    entity_class: str | None
    tags: tuple[str, ...]
    #: 构造时的 world_revision（视图有效性判据；§3.2）
    revision: Revision
    #: 组件数据深冻结视图（内部字段——§3.2 docstring "内部持有 MappingProxyType
    #: 深冻结视图"的落位；未列入 §3.2 展示的公共字段清单）
    components: Mapping[ComponentTypeId, Mapping[str, JsonValue]] = field(
        default_factory=lambda: types.MappingProxyType({})
    )

    @classmethod
    def _from_record(cls, record: EntityRecord, revision: Revision) -> EntityView:
        """私有构造助手（§3.5 纪律 3）：由 EntityRecord 构造深冻结只读视图。

        供 T02 ``WorldState.entity_view()`` / ``component_view()`` 委托。
        返回视图与 record 零别名（构造后 record 侧数据变化不影响已建视图——
        KBC-3：视图由当前 revision 派生，禁止持有跨 revision 权威副本）。
        不导出。
        """
        return cls(
            entity_id=record.entity_id,
            entity_class=record.entity_class,
            tags=tuple(record.tags),
            revision=revision,
            components=types.MappingProxyType(
                {ct: _freeze_value(data) for ct, data in record.components.items()}
            ),
        )

    def component_types(self) -> tuple[ComponentTypeId, ...]:
        """该 entity 携带的组件类型集合（顺序 = 构造顺序，确定性）。"""
        return tuple(self.components)

    def get_component(self, ct: ComponentTypeId) -> Mapping[str, JsonValue] | None:
        """读取指定组件类型的数据（深冻结只读视图，决策 D-15）。

        未挂载该组件返回 ``None``（不抛异常——测试口径 E5：非法引用的"判定"
        属 P2 validation，P1 只保证查询安全）。
        """
        return self.components.get(ct)
