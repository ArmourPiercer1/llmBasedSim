"""P6-W4 T05 后半（SOT §3.10）：L0-L4 组装 + 能力限定变量供给 + wire 模型 +
token 估计。

层序固定 L0→L4（Spec §14 L917-923 封闭 5 值）：

- L0 引擎契约（引擎所有，overridable=False，source="engine"）——wire 输出
  schema 的所有者（本模块拥有 ``LLMActionProposal`` 定义，Leader-A6；
  推理运行时侧 structured 自本模块 import——本波唯一 推理运行时→prompt 包
  运行时 import，DAG 单向，SOT §3.5 L298）；
- L1 game_policy / L2 character_scene（overridable=True——D-P6-12 机械面：
  override 只换 L1/L2 文档文本；同 scope 多条 = casefold 字典序首 id 胜、
  无诊断，确定性兜底）；
- L3 运行时上下文（引擎所有，全 13 名全量供给、无挑选）；
- L4 未受信包装（本相零内容源——空段 = 确定性空文本；扩展 = 版本变更）。

变量供给 K4 天花板（SOT §3.10 L457）：只认 ``CONTEXT_VARIABLES`` 封闭 13 名
（= ActorDecisionContext 13 字段名精确集，context_provider.py:299-314），
context 之外的任何数据无进入 prompt 的通道；未授权
``global_entity_views`` → 字面串 ``"null"``（不泄漏，#7 机械面）。声明变量
∉ 13 名 → ``LLMSIM_PROMPT_VARIABLE_UNSUPPORTED``（error，path=policy id）且
该层停渲染（空文本段）——不支持变量仅可能出现在 L1/L2 声明面（K4 天花板
不分层）。

override 语义（SOT §3.10 L487，G6-3）：宿主 override = 替换 L1/L2 的文档
文本（store 以 override 版 policy 加载即生效）；override 不提升 context
capability（变量仍受 13 名供给约束）。

模块纪律（SOT §3.10 L489）：零推理运行时 import、零网络、零非确定根源、
同步面；pydantic + core/content 冻结面 + stdlib（json/math/enum）。
"""

from __future__ import annotations

import enum
import json
import math
from typing import TYPE_CHECKING, Final, Protocol

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from src.engine_v2.content.schemas import DiagnosticSeverity
from src.engine_v2.core.revision import Revision
from src.engine_v2.prompts.diagnostic import RuntimeDiagnostic
from src.engine_v2.prompts.registry import (
    TemplateDocument,
    TemplateStore,
    render_template,
)

if TYPE_CHECKING:
    from src.engine_v2.core.context_provider import ActorDecisionContext

__all__ = [
    "PromptLayer",
    "LayerSegment",
    "PromptAssembly",
    "PromptPackage",
    "UntrustedContent",
    "TokenEstimator",
    "CharDivisorTokenEstimator",
    "CONTEXT_VARIABLES",
    "L0_CONTRACT_TEMPLATE",
    "LLMActionProposal",
    "context_variable_value",
    "assemble_prompt",
]

#: 诊断码常量（P6 21 码闭集之 PROMPT 族本模块发射面，SOT §8.1）。
_VARIABLE_UNSUPPORTED = "LLMSIM_PROMPT_VARIABLE_UNSUPPORTED"

#: 封闭供给集 = ActorDecisionContext 13 字段名精确集（context_provider.py:
#: 299-314，SOT §3.10 L457）。K4 天花板：assembler 只认这 13 名，context
#: 之外的任何数据无进入 prompt 的通道（#7-9 机械面）。
CONTEXT_VARIABLES: Final[frozenset[str]] = frozenset(
    {
        "actor_id",
        "tick",
        "base_world_revision",
        "wake_reason",
        "self_view",
        "visible_entities",
        "local_entity_views",
        "global_entity_views",
        "observations",
        "knowledge",
        "memory",
        "candidate_actions",
        "granted_capabilities",
    }
)


class PromptLayer(enum.Enum):
    """提示层（封闭 5 值，Spec §14 L917-923）。"""

    L0_ENGINE_CONTRACT = "l0_engine_contract"
    L1_GAME_POLICY = "l1_game_policy"
    L2_CHARACTER_SCENE = "l2_character_scene"
    L3_RUNTIME_CONTEXT = "l3_runtime_context"
    L4_UNTRUSTED = "l4_untrusted"


class LayerSegment(BaseModel):
    """单层段（SOT §3.10 L456）。

    ``source`` = 来源标记（``"engine"`` / policy_id / ``"runtime"`` / 来源
    标签）；``overridable`` = L1/L2 True、余 False（D-P6-12 机械面）。
    无文档的 L1/L2 兜底段 = 空文本 + source="engine"（无诊断）；L4 空段 =
    source="runtime"（本相零内容源）。
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    layer: PromptLayer
    source: str
    text: str
    overridable: bool


class PromptPackage(BaseModel):
    """组装产物（SOT §3.10 L478）。

    ``layers`` 序 = L0→L4 固定；``text`` = 压平全文（L0 居首 + L1-L4 各
    前置本层标记，SOT §3.10 步 6 公式面）；``prompt_metadata_ref`` =
    ``prompt://{actor_id}:{tick}:{base_revision}``（确定性句柄，K6 面）。
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    actor_id: str
    logical_role: str
    base_revision: Revision
    layers: tuple[LayerSegment, ...]
    text: str
    token_estimate: int
    prompt_metadata_ref: str


class PromptAssembly(BaseModel):
    """组装结果（SOT §3.10 L477）：组装失败 = package None + 诊断（显式
    失败，§3.6 步骤 1 消费）。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    package: PromptPackage | None
    diagnostics: tuple[RuntimeDiagnostic, ...] = ()


class UntrustedContent(BaseModel):
    """L4 数据包装（Spec §14 L933 MUST data 语义：非受信内容必须数据化、
    带标记包裹）。本相零内容源，本模型为预留面。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_label: str
    payload: str


class TokenEstimator(Protocol):
    """token 估计注入 seam（同 MonotonicClock 模式，SOT §3.10 L475）。

    结构化使用（无 runtime_checkable，W3 adapter.py MonotonicClock 先例）。
    """

    def estimate(self, text: str) -> int:
        """估计 token 数（>=0，确定性）。"""


class CharDivisorTokenEstimator:
    """字符数除数估计器（SOT §3.10 L476）：``estimate = max(0, ceil(len /
    divisor))``（确定性）；``divisor < 0.5`` → ValueError。"""

    def __init__(self, *, divisor: float = 4.0) -> None:
        if divisor < 0.5:
            raise ValueError(f"估计器除数必须 >= 0.5: {divisor}")
        self.divisor = divisor

    def estimate(self, text: str) -> int:
        return max(0, math.ceil(len(text) / self.divisor))


#: L0 引擎契约层模板（SOT §3.10 L464：中性措辞，零 12 名、零供应商侧语义，
#: G6-6 面；含 wire 输出 schema（5 字段 + 类型 + 默认值）、JSON-only 指令、
#: repair 约定、no-op 约定。v1 json_instruction（parser.py:44-52）的中立
#: 等价迁移，§7.4 行 5）。
L0_CONTRACT_TEMPLATE: Final[str] = (
    "## 输出契约（引擎层，不可覆盖）\n"
    "\n"
    "你是游戏模拟引擎的推理组件。请基于下文给定的游戏规则、角色场景与运行时上下文，\n"
    "为本 tick 做出行动决策，并按下述 JSON 格式输出提案。\n"
    "\n"
    "### 输出格式\n"
    "\n"
    "- 直接输出且仅输出一个 JSON 对象，不输出任何其他内容；不要用 markdown 代码块包裹。\n"
    "- JSON 对象必须包含以下全部 5 个字段（缺失字段使用默认值）：\n"
    "  - \"action_id\": 字符串或 null，行动类型标识；null = 本 tick 不行动（no-op）。\n"
    "  - \"arguments\": 对象，行动参数（键 = 参数名，值 = 任意 JSON 值）；默认 {}。\n"
    "  - \"intent\": 字符串或 null，一句话意图描述；默认 null。\n"
    "  - \"confidence\": 数字或 null，置信度，取值闭区间 [0, 1]；默认 null。\n"
    "  - \"fallback_action\": 字符串或 null，主行动不可执行时使用的回退行动标识；默认 null。\n"
    "- 所有字符串必须是合法 JSON 字符串；字符串内容中不要使用未转义的英文双引号，\n"
    "  引用短语请使用中文书名号《》或单引号。\n"
    "- \"action_id\": null 是合法输出，表示本 tick 不行动。\n"
    "\n"
    "### 修复约定\n"
    "\n"
    "- 若输出格式不正确，系统将返回含错误清单的修复反馈；收到反馈后必须按上述契约\n"
    "  重新输出 JSON，且重新输出不得重复原错误。\n"
)

#: L3 运行时上下文层标题（引擎所有，确定性模板，SOT §3.10 步 4）。
_L3_RUNTIME_TEMPLATE: Final[str] = (
    "## 运行时上下文（引擎层，不可覆盖）\n"
    "以下为本次决策的完整运行时上下文（全量供给，无挑选）：\n"
)


class LLMActionProposal(BaseModel):
    """wire 模型（SOT §3.10 L465-473，L0 层拥有输出 schema 定义）。

    ``extra="ignore"``——供应商侧附加字段容忍（Leader-A4 中立面）。

    - ``action_id`` 默认 None = no-op（本 tick 不行动）；
    - ``arguments`` 开放参数（``JsonValue`` = P5/core JSON 封闭类型族），
      默认 ``{}``；
    - ``confidence`` ∈ [0, 1]（构造期校验），默认 None。
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    action_id: str | None = None
    arguments: dict[str, JsonValue] = Field(default_factory=dict)
    intent: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    fallback_action: str | None = None


def context_variable_value(context: ActorDecisionContext, name: str) -> str | None:
    """变量供给（SOT §3.10 L458-462，K4 天花板机械面）。

    - name ∉ CONTEXT_VARIABLES → None（调用方发
      ``LLMSIM_PROMPT_VARIABLE_UNSUPPORTED``——P5 声明了但运行时不供给的
      变量 = 显式拒绝，不猜）；
    - ``global_entity_views`` 且 context 该字段 = None（未授权）→ 字面串
      ``"null"``（不泄漏，#7 机械面）；
    - 其余 → JSON 清洗确定性序列化（``json.dumps(sort_keys=True,
      ensure_ascii=False, separators=(",", ":"))``，与 core
      serialization.py:82 assert_json_clean 同族口径）；不可序列化值 =
      输入违例，ValueError 上抛（house 族）。
    """
    if name not in CONTEXT_VARIABLES:
        return None
    value = getattr(context, name)
    if name == "global_entity_views" and value is None:
        return "null"
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError, RecursionError) as exc:
        raise ValueError(f"context 变量不可 JSON 序列化: {name}") from exc


def assemble_prompt(
    context: ActorDecisionContext,
    store: TemplateStore,
    estimator: TokenEstimator,
    *,
    capability: str,
) -> PromptAssembly:
    """L0-L4 组装（SOT §3.10 L479-487，步骤 1-7 钉死）。

    - L1/L2：store 内同 scope 文档 = casefold 字典序首 id 胜、无诊断
      （确定性兜底，D-P6-12）；无文档 → 空文本段（无诊断）；渲染 =
      ``render_template(doc, values)``，values = 声明变量逐个
      ``context_variable_value``（render 诊断透传）；
    - 声明变量 ∉ CONTEXT_VARIABLES → 逐名发 VARIABLE_UNSUPPORTED（error，
      path=policy id）且该层停渲染（空文本段，源标签 = policy id）——
      不支持仅可能出现在 L1/L2 声明面（K4 天花板不分层）；
    - L3：引擎所有确定性模板（含标题行）+ 全 13 名 JSON 序列化块（sorted
      序、``indent=2``，每值 = 该变量的字符串化值；``global_entity_views``
      未授权 → ``"null"`` 字符串值），source="runtime"，overridable=False；
    - L4：本相零内容源 → 空文本段（无诊断；``assemble_prompt`` 无 L4 入参，
      扩展 = 版本变更），source="runtime"，overridable=False；
    - 压平 = L0 居首 + L1-L4 各前置本层标记 ``"\\n\\n<!-- LAYER:<name> -->\\n"``
      （name = ``layer.name``，如 ``L1_GAME_POLICY``）；``token_estimate =
      estimator.estimate(text)``；
    - 组装诊断 = store 诊断 + L1/L2 render 诊断 + VARIABLE_UNSUPPORTED，
      合并后按 (code, path, refs) 元组序排序；任一 error 级 →
      package=None（显式失败）；仅 warning → package 正常。
    """
    diagnostics: list[RuntimeDiagnostic] = list(store.diagnostics)
    layers: list[LayerSegment] = [
        LayerSegment(
            layer=PromptLayer.L0_ENGINE_CONTRACT,
            source="engine",
            text=L0_CONTRACT_TEMPLATE,
            overridable=False,
        )
    ]

    def _policy_segment(layer: PromptLayer, scope: str) -> LayerSegment:
        docs = [
            doc
            for doc in store.by_id.values()
            if doc.scope.casefold() == scope.casefold()
        ]
        if not docs:
            return LayerSegment(layer=layer, source="engine", text="", overridable=True)
        doc: TemplateDocument = min(docs, key=lambda d: d.policy_id.casefold())
        unsupported = [var for var in doc.variables if var not in CONTEXT_VARIABLES]
        if unsupported:
            for var in unsupported:
                diagnostics.append(
                    RuntimeDiagnostic(
                        code=_VARIABLE_UNSUPPORTED,
                        severity=DiagnosticSeverity.ERROR,
                        path=doc.policy_id,
                        message=f"声明变量不在封闭供给集内: {var}",
                        refs=(var,),
                    )
                )
            return LayerSegment(layer=layer, source=doc.policy_id, text="", overridable=True)
        values: dict[str, str] = {}
        for var in doc.variables:
            rendered = context_variable_value(context, var)
            if rendered is not None:
                values[var] = rendered
        result = render_template(doc, values)
        diagnostics.extend(result.diagnostics)
        return LayerSegment(layer=layer, source=doc.policy_id, text=result.text, overridable=True)

    layers.append(_policy_segment(PromptLayer.L1_GAME_POLICY, "game_policy"))
    layers.append(_policy_segment(PromptLayer.L2_CHARACTER_SCENE, "character_scene"))

    block_values: dict[str, str] = {}
    for name in sorted(CONTEXT_VARIABLES):
        rendered = context_variable_value(context, name)
        if rendered is not None:
            block_values[name] = rendered
    block = json.dumps(block_values, sort_keys=True, ensure_ascii=False, indent=2)
    layers.append(
        LayerSegment(
            layer=PromptLayer.L3_RUNTIME_CONTEXT,
            source="runtime",
            text=_L3_RUNTIME_TEMPLATE + block,
            overridable=False,
        )
    )
    layers.append(
        LayerSegment(
            layer=PromptLayer.L4_UNTRUSTED,
            source="runtime",
            text="",
            overridable=False,
        )
    )

    text = L0_CONTRACT_TEMPLATE + "".join(
        "\n\n<!-- LAYER:" + seg.layer.name + " -->\n" + seg.text for seg in layers[1:]
    )
    token_estimate = estimator.estimate(text)
    package = PromptPackage(
        actor_id=str(context.actor_id),
        logical_role=capability,
        base_revision=context.base_world_revision,
        layers=tuple(layers),
        text=text,
        token_estimate=token_estimate,
        prompt_metadata_ref=(
            "prompt://"
            + str(context.actor_id)
            + ":"
            + str(context.tick)
            + ":"
            + str(context.base_world_revision)
        ),
    )
    merged = tuple(sorted(diagnostics, key=lambda d: (d.code, d.path, d.refs)))
    if any(d.severity is DiagnosticSeverity.ERROR for d in merged):
        return PromptAssembly(package=None, diagnostics=merged)
    return PromptAssembly(package=package, diagnostics=merged)
