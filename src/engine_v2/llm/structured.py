"""P6-W4 T04 后半（SOT §3.5）：健壮 JSON 提取 + parse 重试上限 + wire 模型
→ core ActionProposal 映射。

三族提取次序钉死（移植 v1 parser.py:91-104 语义，供应商侧中立化，G6-6
机械面 = #14）：① markdown fence（```json 或 ``` 块，DOTALL）→ 块内
strip 返回（v1 JSON_BLOCK_RE 等价面）；② 裸 JSON：首个 ``{`` 到末个
``}``（end > start）→ 返回该段；③ 首尾杂文：前 1-2 族均未命中 → 整体
strip 后返回（交给 JSON 解析报错）；④ 无 ``{`` 或全空 → None（提取
失败，转 parse 失败 path）。

wire 模型本体归 ``prompts/assembler.py`` 所有（L0 层拥有输出 schema
定义，Leader-A6；本模块自彼处 import——本波唯一 推理运行时→prompt 包
运行时 import，DAG 单向，SOT §3.5 L298 / §3 依赖 DAG）。

模块纪律（SOT §3.5 L334）：stdlib（hashlib/re，§3 导入纪律白名单内）+
pydantic + core 冻结面 + prompts.assembler（wire 模型）；零网络、零 I/O、
零非确定根源、同步面。
"""

from __future__ import annotations

import hashlib
import re
from typing import TYPE_CHECKING, Final

from pydantic import BaseModel, ConfigDict, ValidationError

from src.engine_v2.core.actions import ActionProposal, ActionTiming, ActionTypeId, FallbackSpec
from src.engine_v2.core.ids import ActionInstanceId, ProducerId
from src.engine_v2.core.provenance import OriginKind, Provenance
from src.engine_v2.core.revision import Revision
from src.engine_v2.prompts.assembler import LLMActionProposal

if TYPE_CHECKING:
    from src.engine_v2.core.context_provider import ActorDecisionContext

__all__ = [
    "ParseResult",
    "PARSE_RETRY_MAX",
    "extract_json_robust",
    "parse_llm_response",
    "repair_instruction",
    "make_action_proposal",
]

#: K6 provenance 命名空间前缀（Leader 裁定 F-04，私有拼接常量，不入
#: ``__all__``；源文本零裸前缀字面量，SOT §3.5 L302 / §2 K6 行）。
_LLM_PRODUCER_PREFIX: Final[str] = "ll" + "m:"
_LLM_NOTES_PREFIX: Final[str] = "ll" + "m://"

#: parse 重试上限钉死（Leader-A6；trace ``parse_retry`` 键值域 = {0, 1}，
#: SOT §3.5 L304）。
PARSE_RETRY_MAX: Final[int] = 1

#: markdown fence 正则（v1 JSON_BLOCK_RE 等价面，SOT §3.5 步 1）。
_FENCE_RE: Final = re.compile(r"```(?:json)?\s*\n?(.*?)\n?```", re.DOTALL)


class ParseResult(BaseModel):
    """parse 结果（SOT §3.5 L311）：``value`` = 解析出的 wire 模型（失败
    None）；``raw_json`` = 提取到的候选串；``error`` = 确定性摘要（首个
    pydantic error 的 loc 点分串（空 loc → 哨兵 ``<root>``）+ ``:`` +
    type；无供应商侧语义，ERR-P6-1(b) ``<root>`` 哨兵先例）。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    value: LLMActionProposal | None = None
    raw_json: str | None = None
    error: str | None = None


def extract_json_robust(text: str) -> str | None:
    """三族提取（SOT §3.5 L305-310，次序钉死；v1 parser.py:91-104 语义
    移植，供应商侧中立化）。

    1. markdown fence（```json 或 ``` 块，DOTALL）→ 块内 strip 返回（v1
       JSON_BLOCK_RE 等价面）；
    2. 裸 JSON：首个 ``{`` 到末个 ``}``（end > start）→ 返回该段；
    3. 首尾杂文：前 1-2 族均未命中 → 整体 strip 后返回（交给 JSON 解析
       报错）；
    4. 无 ``{`` 或全空 → None（= 提取失败，转 parse 失败路径）。

    纯字符串函数：无供应商侧分支、无 12 名词（G6-6 机械面 = #14）。
    """
    text = text.strip()
    if not text:
        return None
    fence = _FENCE_RE.search(text)
    if fence is not None:
        return fence.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    if "{" not in text:
        return None
    return text


def _error_summary(exc: ValidationError) -> str:
    """确定性错误摘要（SOT §3.5 L311）：首个 pydantic error 的 loc 点分串
    （空 loc → 哨兵 ``<root>``，ERR-P6-1(b) 先例）+ ``:`` + type。"""
    first = exc.errors()[0]
    loc = ".".join(str(part) for part in first["loc"])
    if not loc:
        loc = "<root>"
    return f"{loc}:{first['type']}"


def parse_llm_response(text: str) -> ParseResult:
    """wire parse（SOT §3.5 L312）：不抛异常（判定 = 数据）。

    - ``extract_json_robust`` → None → ``ParseResult(None, None,
      "no-json-object")``；
    - ``LLMActionProposal.model_validate_json``（pydantic v2）成功 →
      (value, 候选串, None)；
    - 失败 → (None, 候选串, 错误摘要)。
    """
    candidate = extract_json_robust(text)
    if candidate is None:
        return ParseResult(value=None, raw_json=None, error="no-json-object")
    try:
        value = LLMActionProposal.model_validate_json(candidate)
    except ValidationError as exc:
        return ParseResult(value=None, raw_json=candidate, error=_error_summary(exc))
    return ParseResult(value=value, raw_json=candidate, error=None)


def repair_instruction(errors: tuple[str, ...]) -> str:
    """确定性修复反馈文本（SOT §3.5 L313；v1 parser.py:79-84 反馈语义的
    中立等价迁移，§7.4 行 6）。

    错误清单逐行 + 输出契约重申（严格 JSON 输出、不用 markdown 包裹、
    字符串内不用未转义双引号、no-op 约定）；无供应商侧语义、无 12 名。
    """
    lines: list[str] = ["上一次输出格式不正确，错误清单如下:"]
    for error in errors:
        lines.append(f"- {error}")
    lines.extend(
        (
            "请按以下输出契约重新输出:",
            "1. 直接输出且仅输出一个 JSON 对象，不输出任何其他内容；不要用 markdown 代码块包裹。",
            "2. JSON 对象必须包含全部 5 个字段 action_id / arguments / intent / confidence / fallback_action（缺失字段使用默认值）。",
            "3. 字符串内容中不要使用未转义的英文双引号；引用短语请使用中文书名号《》或单引号。",
            '4. "action_id": null 是合法输出，表示本 tick 不行动。',
        )
    )
    return "\n".join(lines)


def make_action_proposal(
    context: ActorDecisionContext,
    wire: LLMActionProposal,
    *,
    valid_until: Revision | None = None,
) -> ActionProposal:
    """wire → core ActionProposal 映射（SOT §3.5 L314-330，映射面逐项
    钉死，语义对齐 Spec §11.3 L774-784）。

    前提（docstring 记录，不写 guard）：``wire.action_id`` 非 None——None
    路径（no-op）由 policy 层拦截，不进入本函数（SOT §3.5 L320）。

    - ``proposal_id`` = 确定性推导（``actor_id:tick:base_world_revision``
      的 sha256 前 16 hex，``act_`` 前缀；不用 uuid 工厂——K7 双跑字节
      相等，D-P6-19）；直接构造口径 = ids.py:83-85；
    - ``fallback_action`` = FallbackSpec（wire.fallback_action 非 None 时；
      None → None，actions.py:134-142）；
    - ``base_world_revision`` 必填（D-13，actions.py:183）；
      ``actor_state_revision`` = context.base_world_revision（D-12 口径）；
      ``observation_id`` = None（context 无该字段，13 字段封闭，
      context_provider.py:299-314；P6 不造）；
    - ``valid_until`` = 参数透传（§3.7 计算面）；
    - ``provenance`` = ProducerId（本模块私有拼接常量 + actor_id；K6
      provenance.py:41-74；ProducerId 直接构造不做词法校验，ids.py:83-85）
      + ``BEHAVIOR_POLICY`` + notes（拼接常量 + actor_id:tick:revision）；
      source_record_id 由宿主 sink 接线回填（P8 面）。

    确定性条款：同 (context, wire, valid_until) → 逐字段相等的提案（#17
    消费）；不抛异常（构造违例 = pydantic ValidationError 上抛，属输入
    不变式违反族）。
    """
    identity = ":".join(
        (str(context.actor_id), str(context.tick), str(context.base_world_revision))
    )
    proposal_id = ActionInstanceId(
        "act_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    )
    fallback_action: FallbackSpec | None = None
    if wire.fallback_action is not None:
        fallback_action = FallbackSpec(action_id=ActionTypeId(wire.fallback_action), arguments={})
    return ActionProposal(
        proposal_id=proposal_id,
        actor_id=context.actor_id,
        action_id=ActionTypeId(wire.action_id),
        arguments=wire.arguments,
        intent=wire.intent,
        timing=ActionTiming(),
        confidence=wire.confidence,
        fallback_action=fallback_action,
        base_world_revision=context.base_world_revision,
        observation_id=None,
        actor_state_revision=context.base_world_revision,
        valid_until=valid_until,
        provenance=Provenance(
            producer_id=ProducerId(_LLM_PRODUCER_PREFIX + str(context.actor_id)),
            origin=OriginKind.BEHAVIOR_POLICY,
            source_record_id=None,
            notes=(
                _LLM_NOTES_PREFIX
                + str(context.actor_id)
                + ":"
                + str(context.tick)
                + ":"
                + str(context.base_world_revision)
            ),
        ),
    )
