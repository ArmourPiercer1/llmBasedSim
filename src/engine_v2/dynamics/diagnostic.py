"""P7-W1 dynamics 运行时诊断载体（SOT §3.2，P7-INV-7；码闭集 = 8 码全表）。

P7 不 import P6 ``RuntimeDiagnostic``（其码闭集 = P6 21 码推理运行时域），
而是新立与其字段同构的本地载体——同字段集、同构造期校验语义、闭集换 P7
8 码 dynamics 运行时域（``p7.`` 前缀，与 P5 18 码 / P6 21 码机械不相交，
§3.2/A20）；severity 仅复用 P5 ``DiagnosticSeverity``（跨包只读单名
import，content/schemas.py:102-107）。纯数据 + 纯常量，零 I/O，零 core
依赖，DAG 叶。
"""

from __future__ import annotations

from typing import Final

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.engine_v2.content.schemas import DiagnosticSeverity

__all__ = ["DynamicsDiagnostic", "P7_DYNAMICS_DIAGNOSTIC_CODES"]


class DynamicsDiagnostic(BaseModel):
    """P7 dynamics 运行时诊断（ERR-P6-10(a) JSON-clean twin 模式载体）。

    - ``code`` ∈ ``P7_DYNAMICS_DIAGNOSTIC_CODES``（8 码闭集）；闭集外 =
      构造期拒绝（``model_validator(mode="after")`` 镜像
      prompts/diagnostic.py:44-51 口径）——构造期 ``ValidationError`` 是本
      载体唯一错误通道；
    - ``severity`` 复用 P5 str-Enum（``ERROR="error"`` / ``WARNING="warning"``）；
    - ``path`` 非空（诊断归因对象：backend_id / stimulus_id / checkpoint
      字段等，K6 可追踪面）；
    - ``message`` 非空且为**确定性文本**（无时间戳 / 无指针 / 无随机，
      D-P5-15 纪律）；
    - ``refs`` 结构化引用（机械断言面，构造时定序）。
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    severity: DiagnosticSeverity
    path: str = Field(min_length=1)
    message: str = Field(min_length=1)
    refs: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _check_code_in_closed_set(self) -> "DynamicsDiagnostic":
        if self.code not in P7_DYNAMICS_DIAGNOSTIC_CODES:
            raise ValueError(
                f"DynamicsDiagnostic.code 必须属于 8 码闭集 "
                f"P7_DYNAMICS_DIAGNOSTIC_CODES：{self.code!r}"
            )
        return self


#: P7 dynamics 运行时诊断 8 码闭集（SOT §3.2 全表逐字；D-P7-10；与 P5 18 码、
#: P6 21 码机械不相交——``p7.`` 前缀天然隔离，A20 断言面）。frozenset 只装码
#: 字符串；severity 归属是每条诊断的实例值，不入库为码表结构字段。
P7_DYNAMICS_DIAGNOSTIC_CODES: Final[frozenset[str]] = frozenset(
    {
        # 推理面（3）：预算耗尽 / wire 抽取失败 / wire schema 非法
        "p7.budget_exhausted",
        "p7.wire_parse_failed",
        "p7.wire_schema_invalid",
        # 运行面刺激（1）：构造期外发现的刺激违规（纵深防御）
        "p7.stimulus_rejected",
        # 构造/装配面（4）：restore 失败 / 组合子诊断上浮 / 词表运行面违规 /
        # host 装配 backend_id 不一致
        "p7.checkpoint_restore_failed",
        "p7.composite_child_failed",
        "p7.metadata_vocabulary_violation",
        "p7.unknown_backend_id",
    }
)
