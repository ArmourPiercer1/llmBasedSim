"""engine_v2 core 层 Effect 契约（P1-T04）。

依据 ``docs/v2/contracts/P1-core-data-contracts.md``（下称"设计文档"）：

- §1.1 本文件职责：``EffectTypeId`` / ``StateDomainId`` / ``EntityTarget`` /
  ``StateDomainTarget`` / ``EffectTarget``（tagged union）/ ``ProposedEffect`` /
  ``CommittedEffect``；
- §5.3 :class:`ProposedEffect` 与 Spec §16.1 逐字段一致；两处具体化均有依据：
  ``target`` 的 union 用 tagged union 落 JSON（§0.2），``cause_ids`` 用
  ``CauseRef`` 落 K6 的类型可追踪性；
- §5.4 :class:`CommittedEffect` **内嵌** :class:`ProposedEffect` 而非只存
  ``effect_id``——事务/快照记录自包含，event-level replay（Spec §30.4）无需
  回查 trace 索引；
- §5.7 级联数据承载：effect 的因果链经 ``cause_ids`` 串联（``CascadeContext``
  承载于 DomainEvent/Transaction 侧，``provenance.py``）。

**``StateDomainId`` 必须在本文件定义**：``components.py``（T03）已以
``TYPE_CHECKING`` 前向引用本模块的 ``StateDomainId``（``ComponentSchema.
authority_domain``，Spec §17.2 domain tag 维度预留），位置不可变（设计文档
§1.1 / §5.3）。

类型标识符（``EffectTypeId`` / ``StateDomainId``）为**名字型** typed ``str``
子类：小写点分字符串（正则 ``[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*)*``，设计文档
§2.2 类型标识符族统一词法）。Kernel 不预置任何 RPG 语义取值（Plan §10 强制
约束，设计文档 §8 非目标 1）。

Pydantic 兼容性（设计文档 §2.1 风险项，与 T01/T03 同根因）：本仓 pydantic 2.13
对裸 str 子类注解不再生成 core schema，故名字型 ID 提供与 ID 族同构的
``__get_pydantic_core_schema__`` 兜底：接受原生 ``str`` 值，校验链末端重建为
子类实例——``model_validate`` 后保持 ``type(x) is <IdClass>``，JSON 序列化为
纯字符串（§0.2 铁律 2 / §6.1 规则 3）。

本模块只 import 标准库、pydantic 与同包 ``src.engine_v2``（§0.3 import 边界
白名单），不触碰 v1。
"""

from __future__ import annotations

import re
from typing import Annotated, Any, Final, Literal

from pydantic import AfterValidator, Field, JsonValue

from src.engine_v2.core.components import ComponentTypeId
from src.engine_v2.core.entity import ContractModel
from src.engine_v2.core.ids import EffectId, EntityId, ProducerId, TransactionId
from src.engine_v2.core.provenance import CauseRef
from src.engine_v2.core.revision import Revision

__all__ = [
    "EFFECT_TYPE_ID_PATTERN",
    "STATE_DOMAIN_ID_PATTERN",
    "EffectTypeId",
    "StateDomainId",
    "parse_effect_type_id",
    "parse_state_domain_id",
    "EntityTarget",
    "StateDomainTarget",
    "EffectTarget",
    "ProposedEffect",
    "CommittedEffect",
]

# —— 词法规则（设计文档 §2.2：类型标识符族统一词法，与 ComponentTypeId 同）——

#: EffectTypeId 词法：名字型小写点分字符串（如 ``unlock``、``space.apply_force``）。
EFFECT_TYPE_ID_PATTERN: Final = re.compile(r"[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*")

#: StateDomainId 词法：名字型小写点分字符串（Spec §17.2 domain tag；如
#: ``world_variables`` 域 / ``scenario`` 域，词表由 P2 authority 配置声明）。
STATE_DOMAIN_ID_PATTERN: Final = re.compile(r"[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*")


class _NameTypeId(str):
    """名字型类型标识符公共基类（本模块私有，不导出）。

    typed ``str`` 子类（决策 D-1 模式推广，与 ``ids.py`` ``_TypedId`` 同构）：

    - 构造函数不做词法校验（确定性构造合法，与 ID 族/ComponentTypeId 一致）；
      词法校验的公共入口是本模块各 ``parse_*`` 函数；
    - ``__get_pydantic_core_schema__`` 是设计文档 §2.1 的 pydantic 类型保持兜底。
    """

    __slots__ = ()

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler: Any) -> Any:
        """Pydantic v2 集成：接受原生 str 值，校验链末端重建为子类实例。

        内层 ``str`` schema 完成字符串校验，``AfterValidator(cls)`` 在校验完成
        后重建为 ``cls`` 实例——``model_validate`` 后保持 ``type(x) is cls``，
        JSON 序列化为纯字符串（设计文档 §0.2 / §2.1 / §6.1 规则 3）。仅依赖
        pydantic 公共 API。
        """
        return handler(Annotated[str, AfterValidator(cls)])


class EffectTypeId(_NameTypeId):
    """Effect 类型标识（设计文档 §2.2 类型标识符族 / §5.3）。

    名字型；词表由模块/项目注册（如 ``unlock``、``space.apply_force``），
    Kernel 无内置取值（§8 非目标 1）；值一经使用即稳定（G1）。
    """


class StateDomainId(_NameTypeId):
    """状态域标识（设计文档 §5.3；Spec §17.2 authority selector 的 domain tag 维度）。

    名字型 domain tag（如 ``world_variables`` 域 / ``scenario`` 域）；词表由
    P2 authority 配置声明，Kernel 无内置取值。本类型定义于本模块（T04），
    ``components.py``（T03）以 ``TYPE_CHECKING`` 前向引用之——位置不可变。
    """


def parse_effect_type_id(text: str) -> EffectTypeId:
    """校验 effect 类型标识词法（设计文档 §2.2 类型标识符族统一词法）。

    Args:
        text: 待校验的 effect 类型标识字符串。

    Returns:
        对应的 ``EffectTypeId``（值与输入逐字相同）。

    Raises:
        ValueError: 非法输入——非字符串、空串、大写、段以数字开头、连续点、
            前导/尾随点、非法字符。

    只做词法校验，不做注册存在性判定（词表归模块/项目，设计文档 §5.3）。
    """
    if not isinstance(text, str):
        raise ValueError(f"effect 类型标识必须是字符串，得到 {type(text).__name__}")
    if not EFFECT_TYPE_ID_PATTERN.fullmatch(text):
        raise ValueError(
            f"非法 EffectTypeId {text!r}：不匹配 {EFFECT_TYPE_ID_PATTERN.pattern!r}"
        )
    return EffectTypeId(text)


def parse_state_domain_id(text: str) -> StateDomainId:
    """校验状态域标识词法（设计文档 §2.2 类型标识符族统一词法）。

    Args:
        text: 待校验的状态域标识字符串。

    Returns:
        对应的 ``StateDomainId``（值与输入逐字相同）。

    Raises:
        ValueError: 非法输入——非字符串、空串、大写、段以数字开头、连续点、
            前导/尾随点、非法字符。

    只做词法校验；domain 词表由 P2 authority 配置声明（设计文档 §5.3）。
    """
    if not isinstance(text, str):
        raise ValueError(f"状态域标识必须是字符串，得到 {type(text).__name__}")
    if not STATE_DOMAIN_ID_PATTERN.fullmatch(text):
        raise ValueError(
            f"非法 StateDomainId {text!r}：不匹配 {STATE_DOMAIN_ID_PATTERN.pattern!r}"
        )
    return StateDomainId(text)


class EntityTarget(ContractModel):
    """Effect 目标的 entity 分支（设计文档 §5.3；Spec §16.1 target）。

    与 ``entity.py`` ``EntityRef`` 字段同形（entity_id / component_type /
    field_path），但以 ``kind`` 判别字面量参与 tagged union（§0.2 JSON 落位）。
    ``field_path`` 仅限 schema 已注册的组件使用（设计文档 §3.2），P2 validation
    按 schema 校验其合法性。
    """

    kind: Literal["entity"] = "entity"
    entity_id: EntityId
    component_type: ComponentTypeId | None = None
    field_path: str | None = None


class StateDomainTarget(ContractModel):
    """Effect 目标的 state domain 分支（设计文档 §5.3；Spec §16.1 target）。

    ``domain`` 为名字型 domain tag（如 ``world_variables`` 域 / ``scenario``
    域）；词表由 P2 authority 配置声明，Kernel 无内置取值。
    """

    kind: Literal["state_domain"] = "state_domain"
    domain: StateDomainId


#: Effect 目标 tagged union（设计文档 §5.3）：JSON 中以 ``"kind"`` 作判别
#: （§0.2 JSON-friendly 铁律的落位）。未知 ``kind`` → 校验失败（测试口径 C3）。
EffectTarget = Annotated[
    EntityTarget | StateDomainTarget,
    Field(discriminator="kind"),
]


class ProposedEffect(ContractModel):
    """拟议效果（设计文档 §5.3；与 Spec §16.1 逐字段一致）。

    字段逐项：

    - ``effect_id``：每个 ProposedEffect 一个；WorldInstance 内唯一；去重依据
      （规避 v1 KBC-2 重复累加，设计文档 §9）；
    - ``effect_type``：名字型，词表由模块/项目注册；
    - ``source``：产生者名字（ProducerId，决策 D-4）；
    - ``target``：``EntityRef | StateDomain`` 的 tagged union 落位；
    - ``payload``：变更内容，schema 由 effect_type 约定；**必填且无缺省**——
      任何变化只能经完整 payload 的 effect 完成（KBC-4 防线，设计文档 §4.2 D-6）；
    - ``base_revision``：提案所基于的世界版本（Spec §16.1；提交前 revalidation
      是 P2 强制行为，数据契约保证字段在场，设计文档 §2.3）；
    - ``cause_ids``：类型化因果引用（``CauseRef``，设计文档 §5.0）；
    - ``authority_scope`` / ``priority_hint``：P2 authority selector 与 conflict
      resolver 的输入（Spec §17 / §19）；
    - ``metadata``：开放元数据（``dict[str, JsonValue]``，§0.1）。
    """

    effect_id: EffectId
    effect_type: EffectTypeId
    source: ProducerId
    target: EffectTarget
    payload: dict[str, JsonValue]
    base_revision: Revision
    cause_ids: list[CauseRef] = Field(default_factory=list)
    authority_scope: str | None = None
    priority_hint: int | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class CommittedEffect(ContractModel):
    """已提交效果（设计文档 §5.4；原子提交单元的成员证明）。

    字段逐项：

    - ``effect``：被接受的原始提案**完整保留**（provenance 不丢失）；
    - ``transaction_id``：归属事务（原子单元成员证明）；
    - ``commit_revision``：该事务产生的唯一新 revision（Spec §20.1）；
    - ``sequence``：事务内应用序号——reducer 确定性应用顺序（Spec §20.2
      deterministic）；唯一且自 0 连续的不变量在 ``Transaction`` 层强制
      （设计文档 §5.6 不变量 3）。

    设计取舍（§5.4）：内嵌 ``ProposedEffect`` 而非只存 ``effect_id``——事务/
    快照记录自包含，event-level replay（Spec §30.4）无需回查 trace 索引。
    """

    effect: ProposedEffect
    transaction_id: TransactionId
    commit_revision: Revision
    sequence: int
