"""0.1.0-alpha.1 发布前修复 R1/R2：玩家意图解释器（玩家自然语言 → 结构化
动作提案）。

版本语义（审计《0.1.0-alpha.1 发布前修复》计划（推理原生
Playability Closure）§1）：

> **推理组件负责理解意图和提出动作，不负责决定 authoritative outcome。**

本模块只产 :class:`PlayerIntentResult`（中间结构化结果）——不修改 Engine、
不运行 action、不写 WorldState（K2/K3/K5）。authoritative outcome 由引擎
既有 executor / authority / transaction / reducer 管道独占决定（宿主在
interpret 之后自行调用 ``engine.submit_action``，与 NPC 路径同一权威管道）。

复用面（审计 §3：不复制第二 parser、不复制引擎 registry/authority 逻辑）：

- ``InferenceBackend`` / ``InferenceRequest`` / ``InferenceResponse``
  （本包 adapter 模块）——backend 注入，供应商中立，零硬编码端点/凭据；
- ``parse_llm_response`` / ``repair_instruction``（本包 structured 模块）
  ——同一健壮 JSON 提取 + 至多一次 repair（``PARSE_RETRY_MAX=1``）；
- ``LLMActionProposal``（:mod:`prompts.assembler`）——同一 wire 输出 schema；
- ``ResolvedModel``（本包 router 产物）——部署 → 模型解析在宿主侧
  （:func:`runtime.llm_binding.bind_player_intent`），本模块零 resolve 逻辑。

显式拒绝面：幻觉 action_id / 幻觉 entity id **不在本模块预过滤**（不复制
引擎 registry 逻辑）——宿主层显式拒绝（debug 面 [result]），引擎
``unknown_action:<id>`` / executor failure = 最终门（零世界变更）。
「parse 成功 ≠ action 必须成功」：interpret 只保证结构化结果，动作
是否成功由权威管道决定。

模块纪律：stdlib（json/math 经 estimator）+ pydantic + core 冻结面 +
本包 + prompts（wire 模型 / 诊断载体，与 policy.py 同 import 先例）；
零网络、零 I/O、零非确定源（prompt 纯文本拼接，无时间戳/无随机）、同步面。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pydantic import JsonValue

from src.engine_v2.content.schemas import DiagnosticSeverity
from src.engine_v2.core.trace import LLM_CALL_PAYLOAD_KEYS
from src.engine_v2.llm.adapter import (
    InferenceBackend,
    InferenceRequest,
    WireMessage,
)
from src.engine_v2.llm.structured import parse_llm_response, repair_instruction
from src.engine_v2.llm.router import ResolvedModel
from src.engine_v2.prompts.assembler import (
    CharDivisorTokenEstimator,
    LLMActionProposal,
)
from src.engine_v2.prompts.diagnostic import RuntimeDiagnostic

if TYPE_CHECKING:  # 仅注解面（运行时零 import）
    from src.engine_v2.content.schemas import ProjectIR
    from src.engine_v2.core.state import WorldState
    from src.engine_v2.llm.policy import TraceSink

__all__ = [
    "PLAYER_INTENT_CAPABILITY",
    "ActionGrounding",
    "PlayerIntentContext",
    "PlayerIntentEntityView",
    "PlayerIntentInterpreter",
    "PlayerIntentResult",
    "build_action_grounding",
    "build_player_intent_context",
]

#: player_intent 能力键（审计 R3：与 npc_policy 同形，deployment
#: ``inference_profiles`` 可配不同模型；CAPABILITY_RE 约定内）。
PLAYER_INTENT_CAPABILITY: Final[str] = "player_intent"

#: parse 双次失败的诊断码（复用 INFERENCE 族闭集码，零新码）。
_PARSE_FAILED: Final[str] = "LLMSIM_INFERENCE_PARSE_FAILED"
_PARSE_RECOVERED: Final[str] = "LLMSIM_INFERENCE_PARSE_RECOVERED"

#: token 估计器（确定性无状态；与 llm_binding 的 _TOKEN_DIVISOR=4.0 同口径）。
_ESTIMATOR = CharDivisorTokenEstimator(divisor=4.0)

#: wire 输出契约段（与 L0 契约模板同族的中立措辞：JSON-only + wire 5 字段
#: + no-op 约定 + repair 约定）。
_OUTPUT_CONTRACT: Final[str] = (
    "输出要求（必须遵守）：\n"
    "1. 只输出一个 JSON 对象，不要输出任何解释、前缀或 markdown 围栏。\n"
    "2. JSON 字段：action_id（string 或 null）、arguments（object）、"
    "intent（string 或 null）、confidence（0 到 1 的 number 或 null）。\n"
    "3. action_id 必须取自下方候选动作表；玩家意图与表中任何动作都不对应时，"
    'action_id 输出 null（合法 no-op）。\n'
    "4. arguments 只填写动作需要的参数；实体类参数一律使用场景实体表中的 "
    "'entity_id' 原文，禁止自造实体 id。\n"
    "5. intent 用一句简短中文复述玩家意图；无法判断时输出 null。\n"
)


@dataclass(frozen=True, slots=True)
class ActionGrounding:
    """最小动作 grounding（审计 R2：薄 grounding seam，不重构 ActionSpec
    authoring；参数 schema 通用化留后续版本）。

    - ``action_id`` / ``name`` / ``verb`` / ``description`` = GameProject
      ``actions`` 声明面（P5 ``ActionSpec``，零新 Kernel 契约）；
    - ``argument_hints`` = 可选参数提示（本轮默认空——项目 action 绑定
      参数表尚未生产接线，审计 §2 裁定薄 seam 先行）。
    """

    action_id: str
    name: str
    verb: str
    description: str
    argument_hints: tuple[str, ...] = ()


def build_action_grounding(ir: "ProjectIR") -> tuple[ActionGrounding, ...]:
    """从 ProjectIR.actions（IR 序，确定性）构建 grounding 表。"""
    return tuple(
        ActionGrounding(
            action_id=spec.id,
            name=spec.name,
            verb=spec.verb,
            description=spec.description,
        )
        for spec in ir.actions
    )


@dataclass(frozen=True, slots=True)
class PlayerIntentEntityView:
    """场景实体名目面（id + 名字 + 类别；零组件 payload 泄漏）。"""

    entity_id: str
    name: str
    kind: str  # "player" | "npc" | "item" | "location" | "other"


@dataclass(frozen=True, slots=True)
class PlayerIntentContext:
    """玩家视角的权威状态子集（审计 R2：不 dump 整个 WorldState）。

    只含：玩家身份 / 位置 / 所持物品名 / 场景实体名目表——全部经只读面
    投影（guard 门面或裸 WorldState 均可；组件 payload 不出本面）。
    """

    player_id: str
    player_name: str
    position: "tuple[int, int] | None"
    inventory: "tuple[str, ...]"
    entities: "tuple[PlayerIntentEntityView, ...]"


def _component_get(
    world: "WorldState", entity_id: object, component_type: str
) -> dict:
    record = world.entities.get(entity_id)
    if record is None:
        return {}
    data = record.components.get(component_type)
    return dict(data) if data is not None else {}


def _int_or_none(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def build_player_intent_context(
    world: "WorldState",
    player_id: object,
    *,
    player_name: str | None = None,
) -> PlayerIntentContext:
    """确定性只读投影：玩家组件 + 场景实体名目（同输入同输出）。

    - 名字面：``character_profile.name`` → 宿主注入的 ``player_name``
      （authoring 玩家名，M1 玩家面无 character_profile 投影时的正规
      供给）→ 实体 id（逐层回退，不猜）；
    - 位置面：``position`` 组件 int x/y → 缺席时 ``spaces`` 组件
      ``world`` 域映射（M1 空间物化面，x/y 数值）→ 皆缺席 = None；
    - 库存面：``inventory`` 组件的 entity_id 序列 → 对应物品名（物品缺席
      = 原 id，不静默丢项）；
    - 实体序：id 字符串升序（确定性）。
    """
    # 玩家缺席 = KeyError（宿主契约：interpret 前玩家必在权威世界内）
    world.entities[player_id]
    profile = _component_get(world, player_id, "character_profile")
    player_name_resolved = str(profile.get("name") or player_name or player_id)

    position: "tuple[int, int] | None" = None
    pos = _component_get(world, player_id, "position")
    x, y = _int_or_none(pos.get("x")), _int_or_none(pos.get("y"))
    if x is not None and y is not None:
        position = (x, y)
    else:
        spaces = _component_get(world, player_id, "spaces")
        for mapping in spaces.get("mappings") or ():
            if not isinstance(mapping, Mapping):
                continue
            if mapping.get("domain_id") == "world":
                mpos = mapping.get("position")
                if isinstance(mpos, Mapping):
                    mx, my = _int_or_none(mpos.get("x")), _int_or_none(mpos.get("y"))
                    if mx is not None and my is not None:
                        position = (mx, my)
            if position is not None:
                break

    inventory: "tuple[str, ...]" = ()
    inv = _component_get(world, player_id, "inventory")
    items = inv.get("items")
    if isinstance(items, (list, tuple)):  # 裸态 list / guard 深冻结 tuple 双态
        inventory = tuple(
            str(
                _component_get(world, ref, "item").get("name")
                or (ref if isinstance(ref, str) else str(ref))
            )
            for ref in items
        )

    entities: "list[PlayerIntentEntityView]" = []
    for entity_id in sorted(world.entities, key=str):
        eid_str = str(entity_id)
        name = (
            _component_get(world, entity_id, "character_profile").get("name")
            or _component_get(world, entity_id, "item").get("name")
            or _component_get(world, entity_id, "location").get("name")
        )
        if eid_str == str(player_id):
            kind = "player"
        elif "character_profile" in (world.entities[entity_id].components or {}):
            kind = "npc"
        elif "item" in (world.entities[entity_id].components or {}):
            kind = "item"
        elif "location" in (world.entities[entity_id].components or {}):
            kind = "location"
        else:
            kind = "other"
        entities.append(
            PlayerIntentEntityView(
                entity_id=eid_str, name=str(name or eid_str), kind=kind
            )
        )
    return PlayerIntentContext(
        player_id=str(player_id),
        player_name=player_name_resolved,
        position=position,
        inventory=inventory,
        entities=tuple(entities),
    )


def _build_prompt(
    grounding: "tuple[ActionGrounding, ...]",
    context: PlayerIntentContext,
    text: str,
) -> str:
    """确定性 prompt 拼接（无时间戳/无随机；同输入同字节）。"""
    lines: "list[str]" = [
        "你是游戏模拟引擎的玩家意图理解层。玩家用自然语言表达想做的事，"
        "你的任务是从候选动作表中选出对应动作并填写参数。",
        "",
        "候选动作表：",
    ]
    if grounding:
        for entry in grounding:
            line = f"- {entry.action_id}（{entry.name}）"
            if entry.description:
                line += f"：{entry.description}"
            if entry.argument_hints:
                line += f"（参数提示：{', '.join(entry.argument_hints)}）"
            lines.append(line)
    else:
        lines.append("-（本项目未声明任何动作）")
    lines += [
        "",
        _OUTPUT_CONTRACT,
        "",
        f"当前玩家：id={context.player_id}，名字={context.player_name}",
    ]
    if context.position is not None:
        lines.append(f"玩家位置：{context.position[0]}, {context.position[1]}")
    if context.inventory:
        lines.append(f"玩家持有：{', '.join(context.inventory)}")
    lines.append("")
    lines.append("场景实体表：")
    for view in context.entities:
        lines.append(f"- id={view.entity_id}，名字={view.name}，类别={view.kind}")
    lines += ["", f"玩家输入：{text}", ""]
    return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class PlayerIntentResult:
    """中间结构化结果（审计 §3 建议面；宿主消费，引擎不消费）。

    - ``action_id`` None = 显式 no-op（parse 成功但意图理解层判定无对应动作，
      或 parse 双次失败）——宿主不提交动作，世界零变更；
    - ``arguments`` = 提议参数（宿主提交前可校验；引擎 validate 期
      再次把关）；
    - ``raw_output_ref`` = 原始输出 artifact 句柄（宿主 debug 面可经
      trace sink ``store_artifact`` 取原文）；
    - ``diagnostics`` = 本模块诊断（parse 失败 / 恢复；经 sink
      ``record_diagnostic`` 同步记录）。
    """

    action_id: "str | None"
    arguments: "dict[str, JsonValue]"
    intent: "str | None"
    confidence: "float | None"
    raw_output_ref: "str | None"
    diagnostics: "tuple[RuntimeDiagnostic, ...]"


@dataclass(frozen=True, slots=True)
class PlayerIntentInterpreter:
    """玩家意图解释器（宿主侧推理 seam；非 Engine 一部分）。

    调用契约：``interpret(text=..., context=..., base_revision=...)`` →
    :class:`PlayerIntentResult`；parse 至多一次 repair（与 NPC
    ``LLMPolicy`` 同上限），双次失败 = 显式 no-op（ERROR 诊断 + 零提交）。
    传输异常原样上抛（house 语义：fake 永不抛，httpx 面异常属运行时环境
    失败族，不吞不转）。
    """

    capability: str
    resolved: ResolvedModel
    backend: InferenceBackend
    grounding: "tuple[ActionGrounding, ...]"
    sink: "TraceSink"

    def interpret(
        self,
        *,
        text: str,
        context: PlayerIntentContext,
        base_revision: int,
    ) -> PlayerIntentResult:
        prompt = _build_prompt(self.grounding, context, text)
        prompt_ref = f"player_intent://{context.player_id}:{base_revision}"
        output_ref = (
            f"output://player_intent:{context.player_id}:{base_revision}"
        )
        messages: "tuple[WireMessage, ...]" = (
            WireMessage(role="system", content=prompt),
        )
        request = InferenceRequest(
            messages=messages,
            model=self.resolved.model_id,
            base_url=self.resolved.base_url,
            api_key_env=self.resolved.api_key_env,
            temperature=self.resolved.temperature,
            max_tokens=None,
            timeout_seconds=self.resolved.timeout_seconds,
            logical_role=self.capability,
            profile=self.capability,
            base_revision=base_revision,
            prompt_metadata_ref=prompt_ref,
        )
        response = self.backend.generate(request)
        parse = parse_llm_response(response.text)
        parse_retry = 0
        first_error: "str | None" = None
        if parse.value is None:
            first_error = parse.error or "no-json-object"
            messages = messages + (
                WireMessage(role="user", content=repair_instruction((first_error,))),
            )
            request = request.model_copy(update={"messages": messages})
            response = self.backend.generate(request)
            parse_retry = 1
            parse = parse_llm_response(response.text)

        # —— trace 面（与 LLMPolicy llm_call 同 9 键封闭集；宿主可直读）——
        payload: "dict[str, object]" = {
            "logical_role": self.capability,
            "profile": self.capability,
            "resolved_model": self.resolved.model_id,
            "input_token_estimate": _ESTIMATOR.estimate(prompt),
            "prompt_metadata_ref": prompt_ref,
            "output_ref": output_ref,
            "latency_ms": response.latency_ms,
            "parse_retry": parse_retry,
            "base_revision": base_revision,
        }
        assert frozenset(payload) == LLM_CALL_PAYLOAD_KEYS, (
            "llm_call payload 键集必须与 LLM_CALL_PAYLOAD_KEYS 精确等值"
        )
        self.sink.record("llm_call", payload)
        self.sink.store_artifact(output_ref, {"text": response.text})

        if parse.value is None:
            diag = RuntimeDiagnostic(
                code=_PARSE_FAILED,
                severity=DiagnosticSeverity.ERROR,
                path=self.capability,
                message="parse 双次失败，玩家意图 no-op（不提交动作，世界零变更）",
                refs=(first_error or "no-json-object", parse.error or "no-json-object"),
            )
            self.sink.record_diagnostic(diag)
            return PlayerIntentResult(
                action_id=None,
                arguments={},
                intent=None,
                confidence=None,
                raw_output_ref=output_ref,
                diagnostics=(diag,),
            )
        wire: LLMActionProposal = parse.value
        diagnostics: "tuple[RuntimeDiagnostic, ...]" = ()
        if parse_retry and first_error is not None:
            recovered = RuntimeDiagnostic(
                code=_PARSE_RECOVERED,
                severity=DiagnosticSeverity.WARNING,
                path=self.capability,
                message=f"parse 重试后恢复（首次错误：{first_error}）",
                refs=(first_error,),
            )
            self.sink.record_diagnostic(recovered)
            diagnostics = (recovered,)
        return PlayerIntentResult(
            action_id=wire.action_id,
            arguments=dict(wire.arguments),
            intent=wire.intent,
            confidence=wire.confidence,
            raw_output_ref=output_ref,
            diagnostics=diagnostics,
        )
