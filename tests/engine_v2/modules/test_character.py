"""P9 W1 character 模块单测（SOT §6.1：t1–t4 共 4 函数；T05）。

设计依据 = ``docs/v2/contracts/P9-official-modules-migration-design.md``
§3.5（行为策略 + 记录装配面）+ §6.1（测试表）；actor 一致性权威 =
B-CON-5（core behavior_policy.py:54–75 / :107）。

覆盖项（每项独立 test 函数）：

1. t1_build_record：CharacterSpec → CharacterRecord 全字段装配 +
   位置截断语义（1.7→1 / -2.9→-2）+ 冻结面；
2. t2_policy_proposes：FakeInferenceBackend 脚本响应 → ActionProposal
   全表面钉 + 零推理旁路面（decide 本体零时钟消费）+ 请求面（role 面 /
   prompt_metadata_ref 面 / 渲染文本流入）；
3. t3_actor_mismatch：run_policy_decide 透传 PolicyActorMismatchError
   （B-CON-5 上游钉，core :107）；
4. t4_context_persona：PolicyPromptContext 数据类面（冻结 + 字段）+
   wake_reason → scene 流入渲染文本（persona + scene 双面钉）。
"""

from __future__ import annotations

import dataclasses

import pytest

from src.engine_v2.content.schemas import (
    AttributeSpec,
    CharacterSpec,
    PositionSpec,
    PromptPolicy,
)
from src.engine_v2.core.actions import ActionProposal, ActionTypeId
from src.engine_v2.core.behavior_policy import (
    PolicyActorMismatchError,
    run_policy_decide,
)
from src.engine_v2.core.context_provider import ActorDecisionContext
from src.engine_v2.core.entity import EntityView
from src.engine_v2.core.ids import EntityId
from src.engine_v2.core.revision import Revision
from src.engine_v2.llm.adapter import FakeInferenceBackend, FixedMonotonicClock
from src.engine_v2.modules.attributes import AttributeField
from src.engine_v2.modules.character import (
    NpcBehaviorPolicy,
    PolicyPromptContext,
    build_character_record,
    build_npc_policy,
)
from src.engine_v2.prompts.registry import TemplateStore

_PROMPT_TEXT = "角色 {{actor_id}}；人设：{{persona}}；场景：{{scene}}。请决策。"


def _spec() -> CharacterSpec:
    """钉死 CharacterSpec（id=char_a；hp 80 [0,100]；位置含小数截断面）。"""
    return CharacterSpec(
        id="char_a",
        name="阿葛",
        personality={"traits": "沉稳", "motivations": "看守客栈"},
        position=PositionSpec(x=1.7, y=-2.9),
        attributes={
            "hp": AttributeSpec(name="hp", value=80.0, min=0.0, max=100.0),
        },
    )


def _prompt_store(tmp_path) -> TemplateStore:
    """模板文件 + PromptPolicy + TemplateStore（P6 先例 template_ref 形）。"""
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "npc_policy.md").write_text(
        _PROMPT_TEXT, encoding="utf-8",
    )
    policy = PromptPolicy(
        id="npc_policy",
        scope="game_policy",
        template_ref="prompts/npc_policy.md",
        variables=("actor_id", "persona", "scene"),
    )
    return TemplateStore(project_root=tmp_path, policies=(policy,))


def _context(
    actor_id: str, *, tick: int = 1, wake: str | None = None,
) -> ActorDecisionContext:
    """P4 先例形状 ActorDecisionContext（全字段显式构造）。"""
    entity_id = EntityId(actor_id)
    return ActorDecisionContext(
        actor_id=entity_id,
        tick=tick,
        base_world_revision=Revision(3),
        wake_reason=wake,
        self_view=EntityView(
            entity_id=entity_id,
            entity_class="npc",
            tags=(),
            revision=Revision(3),
        ),
        visible_entities=frozenset({entity_id}),
        local_entity_views={},
        global_entity_views=None,
        observations=(),
        knowledge=None,
        memory=(),
        candidate_actions=(ActionTypeId("talk"),),
        granted_capabilities=frozenset(),
    )


def test_character_t1_build_record() -> None:
    """1) CharacterSpec → CharacterRecord 全字段装配 + 冻结面。"""
    record = build_character_record(_spec())
    assert record.character_id == "char_a"
    assert record.name == "阿葛"
    assert record.personality == {"traits": "沉稳", "motivations": "看守客栈"}
    assert record.attributes == {
        "hp": AttributeField(
            name="hp", value=80.0, min=0.0, max=100.0,
        ),
    }
    # 位置截断语义：int() 截断（1.7→1；-2.9→-2）
    assert record.position == {"x": 1, "y": -2, "z": 0}
    # 无位置面
    spec_no_pos = _spec().model_copy(update={"position": None})
    assert build_character_record(spec_no_pos).position is None
    # 冻结面
    with pytest.raises(dataclasses.FrozenInstanceError):
        record.name = "乙"


def test_character_t2_policy_proposes(
    tmp_path, scripted_backend, fixed_clock,
) -> None:
    """2) 脚本响应 → ActionProposal 全表面钉 + 请求面 + 零时钟消费钉。"""
    record = build_character_record(_spec())
    policy = NpcBehaviorPolicy(
        record=record,
        backend=scripted_backend,
        prompt_store=_prompt_store(tmp_path),
        clock=fixed_clock,
    )
    assert policy.clock is fixed_clock
    before = fixed_clock.now_ms()
    proposal = policy.decide(_context("char_a"))
    # decide() 本体零时钟消费；+1ms = 本次 now_ms() 调用
    # （FixedMonotonicClock 后递增：返回现值后 +step_ms）
    assert fixed_clock.now_ms() == before + 1
    assert isinstance(proposal, ActionProposal)
    # 提案全表面钉（B-CON-5：actor_id 钉 = record.character_id）
    assert proposal.action_id == "talk"
    assert proposal.arguments == {"target": "player"}
    assert proposal.actor_id == "char_a"
    assert proposal.proposal_id == "act_char_a_1"
    assert proposal.intent == "greet"
    assert proposal.confidence == 0.9
    assert proposal.base_world_revision == Revision(3)
    assert proposal.actor_state_revision == Revision(3)
    assert proposal.provenance.origin == "behavior_policy"
    assert proposal.provenance.producer_id == "policy.char_a"
    # 请求面：固定键钉（logical_role/model/profile = 策略 id）
    call = scripted_backend.calls[0]
    assert call.logical_role == "npc_policy"
    assert call.model == "npc_policy"
    assert call.profile == "npc_policy"
    assert call.base_revision == Revision(3)
    assert call.prompt_metadata_ref == (
        "prompt://char_a:1:3"
    )
    assert call.messages[0].role == "user"
    content = call.messages[0].content
    # 渲染文本流入面：persona（personality 值，键序 sorted）+ actor_id
    assert "沉稳" in content
    assert "看守客栈" in content
    assert "char_a" in content
    assert content.index("motivations") < content.index("traits")


def test_character_t3_actor_mismatch(
    tmp_path, scripted_backend, fixed_clock,
) -> None:
    """3) run_policy_decide 透传 PolicyActorMismatchError（B-CON-5，core :107）。"""
    record = build_character_record(_spec())
    policy = NpcBehaviorPolicy(
        record=record,
        backend=scripted_backend,
        prompt_store=_prompt_store(tmp_path),
        clock=fixed_clock,
    )
    with pytest.raises(PolicyActorMismatchError):
        run_policy_decide(policy, _context("char_other"))


def test_character_t4_context_persona(
    tmp_path, scripted_backend, fixed_clock,
) -> None:
    """4) PolicyPromptContext 数据类面 + wake_reason → scene 流入渲染。"""
    # 数据类面：字段可构造 + 冻结
    ctx = PolicyPromptContext(
        actor_id="char_a",
        scene_text="s",
        persona_text="p",
        constraints=("c1",),
    )
    assert ctx.actor_id == "char_a"
    assert ctx.scene_text == "s"
    assert ctx.persona_text == "p"
    assert ctx.constraints == ("c1",)
    with pytest.raises(dataclasses.FrozenInstanceError):
        ctx.scene_text = "t"
    # wake_reason → scene_text 流入渲染文本（persona 双面钉）
    record = build_character_record(_spec())
    policy = NpcBehaviorPolicy(
        record=record,
        backend=scripted_backend,
        prompt_store=_prompt_store(tmp_path),
        clock=fixed_clock,
    )
    assert policy.decide(_context("char_a", wake="客栈起火")) is not None
    content = scripted_backend.calls[0].messages[0].content
    assert "沉稳" in content
    assert "客栈起火" in content
