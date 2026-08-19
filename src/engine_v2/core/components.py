"""engine_v2 core 层 typed component 的 schema 注册机制（P1-T03）。

依据 ``docs/v2/contracts/P1-core-data-contracts.md``（下称"设计文档"）：

- §1.1 本文件职责：``ComponentTypeId`` / ``ComponentSchema`` / ``ComponentRegistry`` /
  ``ComponentData``（``dict[str, JsonValue]`` 别名）；
- §2.2 类型标识符族词法统一规定：``ComponentTypeId`` 为**名字型** typed ``str``
  子类（小写点分字符串，正则 ``[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*)*``）；Kernel
  不预置任何 RPG 语义取值（Plan §10 强制约束，设计文档 §8 非目标 1）；
- §3.3 组件 schema 注册：``ComponentRegistry.register`` 同类型重复注册——schema
  完全相同 → 幂等返回，否则抛 :class:`ComponentConflictError`；
- 决策 D-8（§3.3 未知组件类型的边界策略）：WorldState 接受**未注册**组件类型的
  数据（按不透明 JSON dict 存储）——本模块侧表现为 :meth:`ComponentRegistry.get`
  对未注册类型返回 None、:meth:`ComponentRegistry.validate_payload` 放行；
  校验只发生在 (a) 注册时、(b) P2 reducer 应用 effect 时若 registry 有 schema
  则校验。

Pydantic 兼容性（设计文档 §2.1 风险项，与 T01 同根因）：本仓 pydantic 2.13 对裸
str 子类注解不再生成 core schema（落入 unknown type），故 ``ComponentTypeId``
提供与 ID 族同构的 ``__get_pydantic_core_schema__`` 兜底：接受原生 ``str`` 值，
校验链末端重建为子类实例——``model_validate`` 后（含 dict 键、list 元素）保持
``type(x) is ComponentTypeId``，JSON 序列化为纯字符串（§0.2 铁律 2 / §6.1 规则 3）。

Import 边界（§0.3）：本模块只 import 标准库与 pydantic，不触碰 v1；``effects.py``
（T04，定义 ``StateDomainId``）仅在 ``TYPE_CHECKING`` 下被前向引用——frozen
dataclass 运行时不评估注解，且 ``effects.py`` 运行时单向 import 本模块
（``ComponentTypeId``），不构成循环依赖。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Any, Final

from pydantic import AfterValidator, BaseModel, JsonValue

if TYPE_CHECKING:
    # 前向引用：``StateDomainId`` 由 T04 的 ``effects.py`` 定义（设计文档 §1.1 /
    # §5.3）。``ComponentSchema.authority_domain`` 为 P2 authority selector 的
    # domain tag 维度预留（Spec §17.2，设计文档 §10）。
    from src.engine_v2.core.effects import StateDomainId

__all__ = [
    "COMPONENT_TYPE_ID_PATTERN",
    "ComponentTypeId",
    "ComponentData",
    "ComponentSchema",
    "ComponentRegistry",
    "ComponentConflictError",
    "parse_component_type_id",
]

# —— 词法规则（设计文档 §2.2：类型标识符族统一词法）——

#: 类型标识符族词法：小写点分字符串（如 ``space.position``、``health``）。
#: 段以 ``[a-z]`` 开头，其后 ``[a-z0-9_]*``；段间以单个 ``.`` 分隔。
COMPONENT_TYPE_ID_PATTERN: Final = re.compile(r"[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*")


class ComponentTypeId(str):
    """组件类型标识（设计文档 §2.2 类型标识符族 / §3.3）。

    - 名字型 typed ``str`` 子类（与 ID 族同构，决策 D-1 的模式推广）：运行时
      ``isinstance`` 可区分，JSON 中为纯字符串；
    - 构造函数不做词法校验（与 ``ids.py`` ID 族一致：确定性构造合法）；词法
      校验的公共入口是 :func:`parse_component_type_id`（非法即抛 ``ValueError``）；
    - 词表由模块/项目注册（如 ``space.position``），Kernel 无内置取值（设计
      文档 §8 非目标 1：不预置 RPG 语义）；值一经使用即稳定（G1）；
    - ``__get_pydantic_core_schema__``：pydantic 2.13 类型保持兜底（设计文档
      §2.1 风险项，与 T01 同根因）。
    """

    __slots__ = ()

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler: Any) -> Any:
        """Pydantic v2 集成：接受原生 str 值，校验链末端重建为子类实例。

        内层 ``str`` schema 完成字符串校验，``AfterValidator(cls)`` 在校验完成
        后重建为 ``cls`` 实例——``model_validate`` 后（含 dict 键、list 元素）
        保持 ``type(x) is cls``，JSON 序列化为纯字符串（设计文档 §0.2 / §2.1 /
        §6.1 规则 3）。仅依赖 pydantic 公共 API。
        """
        return handler(Annotated[str, AfterValidator(cls)])


def parse_component_type_id(text: str) -> ComponentTypeId:
    """校验组件类型标识词法（设计文档 §2.2 类型标识符族统一词法）。

    Args:
        text: 待校验的组件类型标识字符串。

    Returns:
        对应的 ``ComponentTypeId``（值与输入逐字相同）。

    Raises:
        ValueError: 非法输入——非字符串、空串、大写、段以数字开头、连续点、
            前导/尾随点、非法字符（``-``/空格等）。

    只做词法校验，不做注册存在性判定（后者属 registry 与 P2 validation，
    设计文档 §3.3 D-8）。
    """
    if not isinstance(text, str):
        raise ValueError(f"组件类型标识必须是字符串，得到 {type(text).__name__}")
    if not COMPONENT_TYPE_ID_PATTERN.fullmatch(text):
        raise ValueError(
            f"非法 ComponentTypeId {text!r}：不匹配 {COMPONENT_TYPE_ID_PATTERN.pattern!r}"
        )
    return ComponentTypeId(text)


#: 组件数据（设计文档 §1.1）：开放字段一律 ``dict[str, JsonValue]``（§0.1），
#: 保证 JSON 原生（§0.2）；未注册组件类型同样按此不透明结构存储（决策 D-8）。
ComponentData = dict[str, JsonValue]


class ComponentConflictError(ValueError):
    """同 component_type 以不同 schema 重复注册（设计文档 §3.3，测试口径 E1）。

    派生自 ``ValueError``：与词法/数据校验错误族统一，调用方可按
    ``ValueError`` 一类捕获。
    """


@dataclass(frozen=True)
class ComponentSchema:
    """组件 schema（设计文档 §3.3；纯运行时辅助结构，frozen dataclass，§0.1）。

    - ``component_type``：由模块/项目注册，Kernel 无内置（如 ``space.position``）；
    - ``payload_model``：``None`` = 该组件按不透明 JSON dict 存储（决策 D-8）；
    - ``authority_domain``：P2 authority selector 的 domain tag 维度（Spec
      §17.2）预留；``StateDomainId`` 定义于 T04 ``effects.py``（TYPE_CHECKING
      前向引用，运行时不评估）。
    """

    component_type: ComponentTypeId
    version: int = 1
    description: str = ""
    payload_model: type[BaseModel] | None = None
    authority_domain: StateDomainId | None = None


class ComponentRegistry:
    """组件 schema 注册表（设计文档 §3.3）。

    运行时注册表，**不是**契约模型、不进入 WorldState round-trip（注册信息
    属运行时配置，非世界状态数据）。

    - 注册时校验是决策 D-8 两个校验点之一（另一个是 P2 reducer 应用 effect
      时若有 schema 则校验）；
    - 未注册组件类型 ≠ 错误（D-8）：:meth:`get` 返回 None、:meth:`validate_payload`
      放行——WorldState 可接受其数据（按不透明 JSON dict 存储），WorldState 侧
      落位在 T02（测试口径 E2 的 registry 侧在此验证）。
    """

    __slots__ = ("_schemas",)

    def __init__(self) -> None:
        self._schemas: dict[ComponentTypeId, ComponentSchema] = {}

    def register(self, schema: ComponentSchema) -> None:
        """注册组件 schema（设计文档 §3.3）。

        同类型重复注册：schema 完全相同（frozen dataclass 字段级相等）→ 幂等
        返回；否则抛 :class:`ComponentConflictError`（测试口径 E1）。
        """
        existing = self._schemas.get(schema.component_type)
        if existing is not None:
            if existing == schema:
                return
            raise ComponentConflictError(
                f"组件类型 {str(schema.component_type)!r} 已注册不同 schema："
                f"existing={existing!r}，new={schema!r}"
            )
        self._schemas[schema.component_type] = schema

    def get(self, ct: ComponentTypeId) -> ComponentSchema | None:
        """查询 schema；未注册组件类型返回 None（D-8：未注册 ≠ 错误）。"""
        return self._schemas.get(ct)

    def validate_payload(self, ct: ComponentTypeId, data: ComponentData) -> None:
        """校验组件数据（设计文档 §3.3 / 决策 D-8）。

        - 无注册或 ``payload_model is None`` → 放行（不透明 JSON dict，E2）；
        - 有 ``payload_model`` → 经 ``model_validate`` 做 schema 校验，非法
          payload 使 pydantic ``ValidationError`` 原样传播（E2"有 schema 时
          拒绝非法 payload"）。
        """
        schema = self.get(ct)
        if schema is None or schema.payload_model is None:
            return
        schema.payload_model.model_validate(data)
