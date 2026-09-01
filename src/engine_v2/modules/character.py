"""P9 W1 官方模块：character（T05；SOT §3.5；导出 5 名）。

来源 = v1 ``_decide_one_char``（src/graph/game_graph.py:302，保留思想）
+ v1 ``player_intent_process``（src/graph/game_graph.py:125，43.1-7
player subconscious policy）+ v1 character yaml 形状（P5 冻结面
``CharacterSpec``:250 已承接）。Spec §12.3 CharacterState（L852–856）
声明 emotion/goals，但 P5 冻结面 ``CharacterSpec`` 无此 2 字段 → P9 不
建模（非 P9 面）。

冻结消费（SOT §2.1/§2.4/§2.5）：core ``actions``
（``ActionProposal``:145）/ ``context_provider``（``ActorDecisionContext``，
签名面）；推理适配面（``MonotonicClock``:47 / ``InferenceBackend``:150
/ ``InferenceRequest``:98 / ``InferenceResponse``:132）；prompts
``registry``（``TemplateStore``:161 / ``render_template``:116）；content
``schemas``（``CharacterSpec``:250）；模块公共面 ``modules.base``；
``modules.attributes``（``AttributeField``）。

纪律（K2/K5/D6）：``NpcBehaviorPolicy`` = 纯函数 policy 对象（Agent is
Policy not Engine；零第三方编排/推理 SDK 导入，SOT §0.5 D7 12 名闭集
（P4 §3.4））；零
直接状态写入；零全局随机源 / wall clock（随机源与推理均经注入调用面）。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from src.engine_v2.content.schemas import CharacterSpec
from src.engine_v2.core.actions import ActionProposal
from src.engine_v2.llm.adapter import (
    InferenceBackend,
    InferenceRequest,
    InferenceResponse,
    MonotonicClock,
)
from src.engine_v2.modules.attributes import AttributeField
from src.engine_v2.modules.base import OFFICIAL_MODULE_VERSION, ModuleIdentity
from src.engine_v2.prompts.registry import TemplateStore, render_template

if TYPE_CHECKING:
    from src.engine_v2.core.context_provider import ActorDecisionContext

__all__ = [
    "CharacterRecord",
    "PolicyPromptContext",
    "NpcBehaviorPolicy",
    "build_character_record",
    "build_npc_policy",
]

#: 策略身份（模板 id = capability 同串，adapter #19 约定：model /
#: logical_role / profile 三值同串）。
_POLICY_ID: Final[str] = "npc_policy"

#: 模块身份（SOT §3.1 MODULE_REQUIRES 表：character 含属性表 →
#: requires = ("llmsim-standard-attributes",)）。
IDENTITY: Final[ModuleIdentity] = ModuleIdentity(
    "llmsim-standard-character",
    OFFICIAL_MODULE_VERSION,
    ("llmsim-standard-attributes",),
)


@dataclass(frozen=True)
class CharacterRecord:
    """v1 character 条目 → 冻结记录（经 ``CharacterSpec`` 校验后构建）。

    ``personality`` 规范键 = traits/motivations/speech_style/background
    （SOT §3.5 表行 1）；``attributes`` =
    ``modules.attributes.AttributeField`` 映射（character 含属性表 →
    MODULE_REQUIRES attributes）；``position`` = ``{"x": int, "y": int,
    "z": int}``（int 截断；v1 无位置 = None）。
    """

    character_id: str
    name: str
    personality: Mapping[str, str]
    attributes: Mapping[str, AttributeField]
    position: Mapping[str, int] | None


@dataclass(frozen=True)
class PolicyPromptContext:
    """策略 prompt 上下文（渲染经 P6 ``render_template``:116 冻结面）。

    ``actor_id`` = record 的 ``character_id``（B-CON-5 一致性源头）；
    ``persona_text`` = 人格确定性拼接；``scene_text`` = 唤醒原因（W1
    约定）；``constraints`` = W1 恒空（宿主约束面归 W6+）。
    """

    actor_id: str
    scene_text: str
    persona_text: str
    constraints: tuple[str, ...]


@dataclass(frozen=True)
class NpcBehaviorPolicy:
    """角色行为策略：实现 core ``BehaviorPolicy``（behavior_policy.py:54，
    结构化协议——``decide`` 同步单参签名即 B-CON-1/2 面）。

    B-CON-4 面：类体不创建 random/时钟/网络——``backend`` /
    ``prompt_store`` / ``clock`` 构造期注入，仅作调用面。W1 ``decide``
    零时钟消费：延迟权威 = ``InferenceResponse.latency_ms``（adapter
    :132）；``clock`` = 工厂签名钉定的注入调用面（宿主延迟统计面，W6+
    消费）。
    B-CON-5 一致性源头：提案 ``actor_id`` 恒 =
    ``record.character_id``；门面 ``run_policy_decide``
    （behavior_policy.py:83）强制与 ``context.actor_id`` 一致，违规 →
    ``PolicyActorMismatchError``（behavior_policy.py:107）透传。
    仅 wakeup 时被调用（43.2-2 移除面的实现保证，A8 面）。
    """

    record: CharacterRecord
    backend: InferenceBackend
    prompt_store: TemplateStore
    clock: MonotonicClock

    def decide(self, context: ActorDecisionContext) -> ActionProposal | None:
        """单次决策（同步、单参）；任何异常面 → ``None``（B-CON-3 no-op）。

        内部流程（W1 钉定解析面；全部失败路径静默 ``None``，不抛）：

        1. 模板缺失（``prompt_store.by_id`` 无 ``npc_policy``）→
           ``None``（fail-safe，宿主诊断面）；
        2. 构建 ``PolicyPromptContext``：``persona_text`` = record 人格
           sorted 键序 ``"; ".join(f"{k}: {v}")``；``scene_text`` =
           ``context.wake_reason or ""``（W1 约定）；
        3. P6 ``render_template``:116 渲染（token = actor_id/persona/
           scene；诊断不拦截——W1 面 = 文本流）；
        4. ``InferenceRequest``:98 构造：messages = 单条 user 消息
           （dict 形式，pydantic 强转 ``WireMessage``）；model /
           logical_role / profile = capability 同串 ``npc_policy``；
           端点空串、零凭据 env（W1 脚本 backend 面，真机端点归 P6
           后端，非 P9 面）；零 uuid4——id 确定性拼装；
        5. ``backend.generate``（Protocol，adapter.py:150）→
           ``InferenceResponse``:132；
        6. 回应 JSON 解析（``_parse_proposal_payload``）：坏 JSON /
           非 dict / ``action_id`` 缺失或非 str 或空 / ``arguments``
           非 dict → ``None``；
        7. ``ActionProposal``:145 构造：``actor_id`` =
           ``record.character_id``（B-CON-5 一致性源头）；
           ``proposal_id`` = ``act_{character_id}_{tick}`` 确定性拼装
           （P1 ``ids.py`` 语法，零 uuid4）；``base_world_revision`` /
           ``actor_state_revision`` = ``context.base_world_revision``；
           ``provenance`` = host 约定 dict
           ``{"producer_id": "policy.{character_id}", "origin":
           "behavior_policy"}``（pydantic 强转；零 core.provenance
           导入——SOT §2.1 provenance 非 P9 消费面）。
        """
        document = self.prompt_store.by_id.get(_POLICY_ID)
        if document is None:
            return None
        persona_text = "; ".join(
            f"{key}: {value}"
            for key, value in sorted(self.record.personality.items())
        )
        scene_text = context.wake_reason or ""
        prompt_context = PolicyPromptContext(
            actor_id=self.record.character_id,
            scene_text=scene_text,
            persona_text=persona_text,
            constraints=(),
        )
        rendered = render_template(
            document,
            {
                "actor_id": prompt_context.actor_id,
                "persona": prompt_context.persona_text,
                "scene": prompt_context.scene_text,
            },
        )
        request = InferenceRequest(
            messages=[{"role": "user", "content": rendered.text}],
            model=_POLICY_ID,
            base_url="",
            api_key_env=None,
            temperature=0.0,
            max_tokens=None,
            timeout_seconds=0.0,
            logical_role=_POLICY_ID,
            profile=_POLICY_ID,
            base_revision=context.base_world_revision,
            prompt_metadata_ref=(
                f"prompt://{context.actor_id}:{context.tick}:"
                f"{context.base_world_revision}"
            ),
        )
        response: InferenceResponse = self.backend.generate(request)
        payload = _parse_proposal_payload(response.text)
        if payload is None:
            return None
        action_id, arguments, intent, confidence = payload
        return ActionProposal(
            proposal_id=f"act_{self.record.character_id}_{context.tick}",
            actor_id=self.record.character_id,
            action_id=action_id,
            arguments=arguments,
            intent=intent,
            confidence=confidence,
            base_world_revision=context.base_world_revision,
            actor_state_revision=context.base_world_revision,
            provenance={
                "producer_id": f"policy.{self.record.character_id}",
                "origin": "behavior_policy",
            },
        )


def build_character_record(spec: CharacterSpec) -> CharacterRecord:
    """经 ``CharacterSpec``（content/schemas.py:250 冻结面）构建冻结角色
    记录。

    对齐 v1 character yaml 形状思想（``CharacterSpec`` 冻结面已承接）。
    ``CharacterSpec`` 自身完成 id 文法 / 重复 / 界校验（P5 诊断路径，
    spec 构造期），本函数不重校验。
    转换面（W1 钉定）：

    - ``personality``：值一律 ``str(v)`` 规整（lossless 键面透传；规范
      键 traits/motivations/speech_style/background，额外键原样）；
    - ``attributes``：dict 键 → ``AttributeField``（``name`` = dict 键，
      v1 name 键面不读）；value/min/max 数值透传；
      ``natural_delta_per_tick`` = v1 ``natural_delta_per_minute`` 值
      透传（单位差异披露：v1 每分钟 × 分钟 ≡ v2 每 tick × ticks，宿主
      约定 1 tick = 1 分钟）；locked/hidden 非 v1 CharacterSpec 面 →
      恒 False；
    - ``position``：x/y/z ``int()`` 截断（v1 ``PositionSpec`` float →
      v2 int 格面，W1 约定）；spec 无位置 → None。
    """
    personality = {key: str(value) for key, value in spec.personality.items()}
    attributes = {
        key: AttributeField(
            name=key,
            value=float(item.value),
            min=float(item.min),
            max=float(item.max),
            natural_delta_per_tick=float(item.natural_delta_per_minute),
        )
        for key, item in spec.attributes.items()
    }
    position: Mapping[str, int] | None = None
    if spec.position is not None:
        position = {
            "x": int(spec.position.x),
            "y": int(spec.position.y),
            "z": int(spec.position.z),
        }
    return CharacterRecord(
        character_id=spec.id,
        name=spec.name,
        personality=personality,
        attributes=attributes,
        position=position,
    )


def build_npc_policy(
    record: CharacterRecord,
    backend: InferenceBackend,
    prompt_store: TemplateStore,
    clock: MonotonicClock,
) -> NpcBehaviorPolicy:
    """策略工厂（SOT §3.5 表行 4 签名钉定）。

    对齐 v1 ``_decide_one_char``（src/graph/game_graph.py:302）思想 =
    policy 对象化重写（43.1-7：策略是可调对象，非引擎步骤）。
    ``backend`` = Protocol 注入（测试 = ``FakeInferenceBackend``，
    adapter.py:296；真机 = P6 后端，非 P9 面）；``clock`` = D6 注入
    时钟（W1 ``decide`` 零消费，见类 docstring B-CON-4 面）。
    """
    return NpcBehaviorPolicy(
        record=record,
        backend=backend,
        prompt_store=prompt_store,
        clock=clock,
    )


def _parse_proposal_payload(
    text: str,
) -> tuple[str, dict[str, object], str | None, float | None] | None:
    """脚本回应 JSON → 提案载荷；任何异常面 → None（B-CON-3 no-op）。

    W1 钉定解析面（SOT §3.5 回应 JSON = ``{"action_id": str,
    "arguments": dict, "intent": str|None, "confidence": float}``）：

    - 坏 JSON / 非 dict → None；
    - ``action_id`` 缺失 / 非 str / 空串 → None；
    - ``arguments`` 缺失 → ``{}``；非 dict → None；
    - ``intent`` 非 str → None（缺失 → None）；
    - ``confidence`` 缺失 / bool / 非数值 / 越 ``[0, 1]`` → None。
    """
    try:
        payload = json.loads(text)
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    action_id = payload.get("action_id")
    if not isinstance(action_id, str) or not action_id:
        return None
    arguments = payload.get("arguments")
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        return None
    intent = payload.get("intent")
    if intent is not None and not isinstance(intent, str):
        intent = None
    confidence = payload.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        confidence = None
    elif not 0.0 <= float(confidence) <= 1.0:
        confidence = None
    else:
        confidence = float(confidence)
    return action_id, arguments, intent, confidence
