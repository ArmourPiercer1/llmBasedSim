"""P6-W1 运行时诊断载体（SOT §3.11，D-P6-21；码闭集 = §8.1 21 码全表）。

P6 不 import P5 ``Diagnostic``（其码闭集 = P5 18 码项目文件诊断域），而是
新立与其字段同构的本地载体——同字段集、同构造期校验语义、闭集换 P6 21 码
运行时域（RESOLVER 6 / INFERENCE 7 / PROMPT 8，§8.1）；severity 仅复用 P5
``DiagnosticSeverity``（跨包只读单名 import，content/schemas.py:102-107）。
纯数据 + 纯常量，零 I/O，零 core 依赖，DAG 叶。
"""

from __future__ import annotations

from typing import Final

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.engine_v2.content.schemas import DiagnosticSeverity

__all__ = ["RuntimeDiagnostic", "P6_RUNTIME_DIAGNOSTIC_CODES"]


class RuntimeDiagnostic(BaseModel):
    """P6 运行时诊断（与 P5 Diagnostic 字段同构，闭集换 21 码）。

    - ``code`` ∈ ``P6_RUNTIME_DIAGNOSTIC_CODES``（21 码闭集，§8.1）；闭集外
      = 构造期拒绝（``model_validator(mode="after")`` 镜像
      content/schemas.py:542-548 口径）——构造期 ``ValidationError`` 是本载体
      唯一错误通道；
    - ``severity`` 复用 P5 str-Enum（``ERROR="error"`` / ``WARNING="warning"``）；
    - ``path`` 非空（诊断归因对象：capability id / 部署路径 / policy id /
      template ref 等，K6 可追踪面）；
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
    def _check_code_in_closed_set(self) -> "RuntimeDiagnostic":
        if self.code not in P6_RUNTIME_DIAGNOSTIC_CODES:
            raise ValueError(
                f"RuntimeDiagnostic.code 必须属于 21 码闭集 "
                f"P6_RUNTIME_DIAGNOSTIC_CODES：{self.code!r}"
            )
        return self


#: P6 运行时诊断码 21 码闭集（SOT §8.1 全表逐字；D-P6-18；与 P5 18 码零
#: 重叠）。frozenset 只装码字符串；severity 归属由 §8.1 表钉死，是每条诊断
#: 的实例值，不入库为码表结构字段。
P6_RUNTIME_DIAGNOSTIC_CODES: Final[frozenset[str]] = frozenset(
    {
        # RESOLVER 族（6）
        "LLMSIM_RESOLVER_DEPLOYMENT_MISSING",
        "LLMSIM_RESOLVER_DEPLOYMENT_PARSE",
        "LLMSIM_RESOLVER_NO_DEPLOYMENT",
        "LLMSIM_RESOLVER_MODEL_UNDECLARED",
        "LLMSIM_RESOLVER_TIER_MISMATCH",
        "LLMSIM_RESOLVER_BELOW_IDEAL",
        # INFERENCE 族（7）
        "LLMSIM_INFERENCE_ENDPOINT_MISSING",
        "LLMSIM_INFERENCE_CREDENTIAL_MISSING",
        "LLMSIM_INFERENCE_TRANSPORT",
        "LLMSIM_INFERENCE_HTTP",
        "LLMSIM_INFERENCE_MALFORMED_RESPONSE",
        "LLMSIM_INFERENCE_PARSE_FAILED",
        "LLMSIM_INFERENCE_PARSE_RECOVERED",
        # PROMPT 族（8）
        "LLMSIM_PROMPT_TEMPLATE_MISSING",
        "LLMSIM_PROMPT_PATH_ESCAPE",
        "LLMSIM_PROMPT_DUPLICATE_POLICY",
        "LLMSIM_PROMPT_VARIABLE_UNSUPPORTED",
        "LLMSIM_PROMPT_SCOPE_UNKNOWN",
        "LLMSIM_PROMPT_TEMPLATE_EMPTY",
        "LLMSIM_PROMPT_UNDECLARED_VARIABLE",
        "LLMSIM_PROMPT_VARIABLE_MISSING",
    }
)
