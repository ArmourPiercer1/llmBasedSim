"""P9 W7 g9 sandbox 样例切片测试（SOT §6.1 / §3.16.2；A6–A11 + A23 + 加载门）。

样例面（SOT §3.19 白名单行 36–40）：``tests/fixtures/
v2_project_sandbox/``（game.yaml / world 1 文件 / characters×2 /
rules 1 文件；2 地点 + 2 角色 + 1 DSL 规则；零 prompts 节——模板由宿主
经 ``prompt_root`` 参数落盘，W1 先例形状）。

宿主协议面（SOT §3.16.2 步骤 1–8；conftest ``p9_host`` 工厂）：加载
（零 ERROR）→ 世界构建 → A6 长动作（``start_action`` scheduler.py:468
两跳）→ A7 世界时间（tick × ticks_per_game_minute 确定值，零墙钟）→
A8 NPC 唤醒（``enqueue_actor_wakeup`` 定向）→ A9 知识边界（异地点零
观察、KNOWLEDGE 载荷字节不变）→ A10 推理 dynamics（``run_dynamics_turn``
host.py:86 + ``LLMWorldDynamics``）→ A11 规则 dynamics（``RuleDynamics``
rule.py:273）→ A23 确定性重跑（效果流逐条相等）。

预裁决值披露（任务书）：DEV-W7-1（scenario id = scenario_sandbox /
ticks_per_game_minute = 0.5）/ DEV-W7-2（长动作 ActionSpec = 测试侧
注册，fixture 白名单无 actions/ 节）/ DEV-W7-3（t5 = LLMWorldDynamics
直接绑定 + build_standard_dynamics 装配单元断言同函数；t6 =
RuleDynamics 单绑定）。

纪律：本文件零墙钟 / 零 uuid / 零 random 导入（A7 无墙钟面 = import
闭集自证）；实体 ID 词表 = 规范型 ``ent_authoring_<slug>``；宿主方法面
入参与组件 payload = authoring slug 词表。
"""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from src.engine_v2.core.action_lifecycle import (
    LifecycleEvent,
    LifecycleTransition,
)
from src.engine_v2.core.action_registry import (
    ActionSpec,
    DurationPolicy,
)
from src.engine_v2.core.actions import (
    ActiveAction,
    ActionLifecycleStatus,
    ActionProposal,
    ActionTiming,
    ActionTypeId,
)
from src.engine_v2.core.authority import (
    AuthorityDecision,
    AuthorityPolicy,
    AuthorityRule,
    AuthoritySelector,
    ProducerId,
    ProducerInfo,
    ProducerRegistry,
)
from src.engine_v2.core.cascade import CascadeExecutor
from src.engine_v2.core.clock import rebuild_runtime
from src.engine_v2.core.components import ComponentRegistry, ComponentTypeId
from src.engine_v2.core.effects import EntityTarget, ProposedEffect
from src.engine_v2.core.ids import ActionInstanceId, EntityId
from src.engine_v2.core.knowledge import (
    KnowledgeState,
    encode_knowledge,
)
from src.engine_v2.core.provenance import OriginKind, Provenance
from src.engine_v2.core.revision import Revision
from src.engine_v2.core.reducer import default_handler_registry
from src.engine_v2.core.scheduler import start_action
from src.engine_v2.core.state import RuntimeState, WorldState
from src.engine_v2.core.transaction import TransactionStatus
from src.engine_v2.content.loader import load_project
from src.engine_v2.content.project_ir import build_ir
from src.engine_v2.content.rule_module import (
    DslContext,
    Feasibility,
    evaluate_condition,
    parse_dsl,
)
from src.engine_v2.content.validator import validate_project
from src.engine_v2.dynamics.backend import (
    DynamicsContext,
    WorldSnapshot,
    new_deterministic_effect_id,
)
from src.engine_v2.dynamics.composite import CompositeDynamics
from src.engine_v2.dynamics.host import run_dynamics_turn
from src.engine_v2.dynamics.llm_world import LLMWorldDynamics, LLMWorldDynamicsConfig
from src.engine_v2.dynamics.rule import RuleDynamics, WorldRule
from src.engine_v2.llm.adapter import FakeInferenceBackend, FixedMonotonicClock
from src.engine_v2.modules.dynamics import (
    DynamicsBinding,
    build_standard_dynamics,
)
from src.engine_v2.modules.perception import (
    ObservationSource,
    PerceptionRange,
    build_observations,
)
from src.engine_v2.modules.knowledge import (
    apply_observations,
    knowledge_summary,
    memory_append,
)

_PLAYER = "ent_authoring_player"
_MERCHANT = "ent_authoring_merchant"
_WANDERER = "ent_authoring_wanderer"
_SANDBOX = "tests/fixtures/v2_project_sandbox"
_ATTRS = ComponentTypeId("p9.attributes")
_FLAG = ComponentTypeId("p9.fatigue_flag")
_WS = "p9.sandbox.wsi"
#: A8 唤醒脚本（脚本 = 测试侧常量；key 形状对齐 P7 host 先例）。
_WAKE_SCRIPT = (
    '{"action_id": "inspect", "arguments": {"target": "player"},'
    ' "intent": "watch_merchant", "confidence": 0.8}'
)
#: A10 推理 dynamics 脚本（wire 形状 = llm_world.py 冻结面）。
_LLM_WIRE = (
    '{"effects": [{"effect_type": "core.set_component",'
    f' "entity_id": "{_MERCHANT}", "component_type": "p9.attributes",'
    ' "payload": {"attributes": {"fatigue": 12.0, "morale": 41.0}}}]'
    ', "reasoning": "merchant took a nap"}'
)
#: A9 位置面（fixture 钉：player (1,1) / merchant (1,2) / wanderer (8,8)）。
_POSITIONS = {
    _PLAYER: {"x": 1, "y": 1},
    _MERCHANT: {"x": 1, "y": 2},
    _WANDERER: {"x": 8, "y": 8},
}


def _long_action_spec() -> ActionSpec:
    """DEV-W7-2：长动作 ActionSpec = 测试侧注册（fixture 白名单无
    actions/ 节）——fixed 3 tick（A6 钉）。"""
    return ActionSpec(
        action_id=ActionTypeId("rest_long"),
        executor="p9.test.rest_long",
        parameters={},
        duration_policy=DurationPolicy(kind="fixed", duration_ticks=3),
    )


def _long_action_proposal(host) -> ActionProposal:
    """A6 玩家长动作提案（producer = scenario.test；K6 追溯面）。"""
    return ActionProposal(
        proposal_id=ActionInstanceId("act_sandbox_rest"),
        actor_id=EntityId(_PLAYER),
        action_id=ActionTypeId("rest_long"),
        arguments={},
        intent="长休息（3 tick）",
        timing=ActionTiming(),
        base_world_revision=host.world.world_revision,
        provenance=Provenance(
            producer_id=ProducerId("scenario.test"), origin=OriginKind.SCENARIO,
        ),
    )


def _start_long_action(host) -> None:
    """A6 共享面：PROPOSED 预播种 → ``start_action`` 两跳 → ACTIVE
    （expected_end_tick = 3；零 revision 推进）；runtime 回写宿主。"""
    spec = _long_action_spec()
    proposal = _long_action_proposal(host)
    runtime = rebuild_runtime(
        host.runtime,
        active_actions={
            proposal.proposal_id: ActiveAction(
                instance_id=proposal.proposal_id,
                action_id=proposal.action_id,
                actor_id=proposal.actor_id,
                status=ActionLifecycleStatus.PROPOSED,
                start_tick=0,
                base_world_revision=host.world.world_revision,
                provenance=proposal.provenance,
            ),
        },
    )
    new_world, new_runtime, transitions = start_action(
        host.world, runtime, proposal, spec,
        at_tick=0, checkpoint_interval=None,
    )
    assert new_world is host.world
    assert new_world.world_revision == host.world.world_revision
    assert len(transitions) == 2
    t1, t2 = transitions
    assert isinstance(t1, LifecycleTransition)
    assert isinstance(t2, LifecycleTransition)
    assert t1.event is LifecycleEvent.VALIDATION_ACCEPTED
    assert t1.from_status is ActionLifecycleStatus.PROPOSED
    assert t1.to_status is ActionLifecycleStatus.VALIDATING
    assert t2.event is LifecycleEvent.SCHEDULED
    assert t2.from_status is ActionLifecycleStatus.VALIDATING
    assert t2.to_status is ActionLifecycleStatus.ACTIVE
    active = new_runtime.active_actions[proposal.proposal_id]
    assert active.status is ActionLifecycleStatus.ACTIVE
    assert active.start_tick == 0
    assert active.expected_end_tick == 3
    host.runtime = new_runtime


def _a11_rule() -> WorldRule:
    """A11 P7 结构化规则（冻结面 rule.py:82）：merchant 属性表整表等值
    = 阈值穿越点（fatigue 15.0 + morale 40.0）单命中面。"""
    return WorldRule(
        rule_id="rule_merchant_fatigue_p7",
        when={
            "component_field_equals": {
                "entity": _MERCHANT,
                "component": "p9.attributes",
                "field": "attributes",
                "value": {"fatigue": 15.0, "morale": 40.0},
            }
        },
        emit_effect_type="merchant.fatigued",
        emit_target_entity=_MERCHANT,
        emit_component_type="p9.fatigue_flag",
        emit_field_path=None,
        emit_payload={"state": "fatigued"},
    )


def _authority_executor(
    producer: str,
    component: ComponentTypeId,
    handlers: tuple[tuple[str, object], ...] = (),
) -> CascadeExecutor:
    """测试宿主授权面（K2 授权对象）：默认 DENY + 单条白名单规则授予
    指定 producer 对指定组件的写权（producer 注册进 registry，K2 面）；
    handler = core 缺省注册表（``core.set_component`` 内置面）+ 本测试
    语义扩展（D-P7-13 测试侧注册先例；D-P2-05：未注册 effect_type 不
    推断 → 不提交）。"""
    producer_registry = ProducerRegistry()
    producer_registry.register(
        ProducerInfo(
            producer_id=ProducerId(producer),
            origin=OriginKind.DYNAMICS_BACKEND,
            priority=50,
            description=f"P9 sandbox 测试宿主：{producer} 授权面",
        ),
    )
    policy = AuthorityPolicy(
        rules=[
            AuthorityRule(
                selector=AuthoritySelector(component_type=component),
                allowed_writers=[ProducerId(producer)],
                priority=100,
                rule_id=f"p9.test.sandbox_{producer}",
            ),
        ],
        default_decision=AuthorityDecision.DENY,
    )
    handler_registry = default_handler_registry()
    for effect_type, handler in handlers:
        handler_registry.register(effect_type, handler)
    return CascadeExecutor(
        policy=policy,
        component_registry=ComponentRegistry(),
        producer_registry=producer_registry,
        handlers=handler_registry,
    )


def _fatigue_flag_handler(state: WorldState, effect: ProposedEffect) -> WorldState:
    """A11 语义 handler（测试侧，D-P7-13 先例）：``merchant.fatigued``
    → 对目标实体 set ``p9.fatigue_flag`` = effect.payload（纯函数；
    reducer.py:609 签名 + entity 唯一变更缝隙 ``_with_components``）。"""
    target = effect.target
    if not isinstance(target, EntityTarget) or target.entity_id is None:
        return state
    record = state.entities.get(target.entity_id)
    if record is None:
        return state
    components = dict(record.components)
    components[_FLAG] = dict(effect.payload)
    return state.model_copy(
        update={
            "entities": {
                **state.entities,
                target.entity_id: record._with_components(components),
            }
        }
    )


def _no_rng() -> object:
    """D6 注入纪律测试替身：任何随机调用 = 断言失败（零随机面自证）。"""

    class _NoRng:
        def rand(self) -> float:
            raise AssertionError("rand 不应被调用（零随机面）")

        def uniform(self, lo: float, hi: float) -> float:
            raise AssertionError("uniform 不应被调用（零随机面）")

        def randint(self, lo: int, hi: int) -> int:
            raise AssertionError("randint 不应被调用（零随机面）")

    return _NoRng()


def _merchant_table(world: WorldState) -> dict[str, object]:
    return world.entities[EntityId(_MERCHANT)].components[_ATTRS]["attributes"]


def test_g9_sandbox_t1_long_action(p9_host) -> None:
    """A6：玩家长动作提案（duration 3 tick）→ ``start_action`` 两跳
    VALIDATION_ACCEPTED/SCHEDULED → ACTIVE；tick 3 → COMPLETED
    （宿主相位 5 ``complete_action``；零完成效果）。状态序列钉：
    tick0–2 ACTIVE / tick3 恰 COMPLETED（R1 S-1 补充钉）。"""
    host = p9_host(_SANDBOX)
    _start_long_action(host)
    assert host.runtime.active_actions[
        ActionInstanceId("act_sandbox_rest")
    ].status is ActionLifecycleStatus.ACTIVE
    host.tick(2)
    mid = host.runtime.active_actions[ActionInstanceId("act_sandbox_rest")]
    assert mid.status is ActionLifecycleStatus.ACTIVE
    host.tick(3)
    completed = host.runtime.active_actions[ActionInstanceId("act_sandbox_rest")]
    assert completed.status is ActionLifecycleStatus.COMPLETED
    host.tick(4)
    # 相位 5 零完成效果（action_lifecycle.py:491 completion_effects=()）：
    # host.effects 仅含相位 4 自然差 4 条（merchant 唯一有差角色）。
    assert len(host.effects) == 4


def test_g9_sandbox_t2_world_time(p9_host) -> None:
    """A7：逻辑刻 0→4（宿主 ``set_logical_tick`` 面）→ 游戏分钟 =
    tick × ticks_per_game_minute（0.5）确定值（无墙钟——本文件 import
    闭集零 time/datetime）；自然差消费同钟确定值（merchant fatigue
    10.0 → 14.0 整点推进，2.0/分钟 × 0.5 分钟/刻 = 1.0/刻，binary
    精确 0.5 乘）。"""
    host = p9_host(_SANDBOX)
    assert host.ir.scenario.ticks_per_game_minute == 0.5  # DEV-W7-1 钉
    assert host.runtime.logical_tick == 0
    host.tick(4)
    assert host.runtime.logical_tick == 4
    # 游戏分钟公式（逐刻钉确定值）：
    expected_minutes = {0: 0.0, 1: 0.5, 2: 1.0, 3: 1.5, 4: 2.0}
    for tick, minutes in expected_minutes.items():
        assert tick * host.ir.scenario.ticks_per_game_minute == minutes
    # 自然差消费（2.0/分钟 × 0.5 分钟/刻 = 1.0/刻；4 刻 → +4.0；
    # 夹取 [0, 100] 未触界）：
    assert host.attributes["merchant"]["fatigue"]["value"] == 14.0
    assert host.attributes["merchant"]["morale"]["value"] == 40.0  # 零差面
    # K2 组件面（committed → world；整表 payload）：
    assert _merchant_table(host.world) == {"fatigue": 14.0, "morale": 40.0}
    # 每刻恰 1 条自然差效果（merchant 唯一有差 slug）→ revision 推进 4：
    assert len(host.effects) == 4
    assert host.world.world_revision == Revision(4)


def test_g9_sandbox_t3_npc_wakeup(p9_host, tmp_path) -> None:
    """A8：``enqueue_actor_wakeup`` 仅 merchant → tick 5 相位 1 恰 1 次
    backend 调用（logical_role npc_policy + 提案 actor = merchant +
    proposal_id 确定性钉）；未唤醒 wanderer 零调用；无执行器 → 提案零
    效果（host.effects 仅自然差 5 条 = ticks 1..5）。

    模板面：``prompt_root`` 参数落盘 npc_policy 模板（W1 先例形状；
    无模板 → decide fail-safe None 零调用，宿主诊断面外）。"""
    host = p9_host(
        _SANDBOX,
        backend_script={("npc_policy", Revision(4), 1): _WAKE_SCRIPT},
        prompt_root=tmp_path,
    )
    assert host.backend.calls == ()
    host.enqueue_wakeup("merchant", 5, "scene")
    assert [(str(w.actor_id), w.due_tick, w.reason)
            for w in host.runtime.actor_wakeups] == [(_MERCHANT, 5, "scene")]
    host.tick(5)
    # 到期 wakeup 已消费（相位 1 队列面；actor_wakeups = list 型字段）：
    assert host.runtime.actor_wakeups == []
    assert len(host.backend.calls) == 1
    # 脚本 key 面：相位 1 请求 base_revision = tick 4 后世界 revision 4
    # （自然差 ticks 1..4 已提交）→ 命中 (npc_policy, Revision(4), 1)：
    assert host.backend.calls[0].base_revision == Revision(4)
    assert host.backend.calls[0].logical_role == "npc_policy"
    assert len(host.proposals) == 1
    proposal = host.proposals[0]
    assert str(proposal.actor_id) == _MERCHANT
    assert str(proposal.action_id) == "inspect"
    assert str(proposal.proposal_id) == f"act_{_MERCHANT}_5"
    # 提案无执行器（host.executors 空）→ 零动作效果；host.effects =
    # 相位 4 自然差（ticks 1..5 → 5 条）：
    assert len(host.effects) == 5


def test_g9_sandbox_t4_knowledge_boundary(p9_host) -> None:
    """A9：player 视距 5.0 / 听距 8.0（fixture PlayerSpec.capabilities
    投影面）→ merchant 同地点（曼哈顿 1）恰 sight + hearing 各 1 条；
    wanderer 异地点（曼哈顿 14）零观察、KNOWLEDGE 载荷字节不变
    （core knowledge.py:165 零观察零变化面）；KNOWLEDGE/MEMORY 组件
    哈希不变钉 = encode_knowledge 前后相等 + 信念主体集合钉。"""
    host = p9_host(_SANDBOX)
    # 宿主位置面（world_positions 投影钉）：
    assert host.world_positions("world") == _POSITIONS
    # fixture 能力面（宿主投影源）：
    assert host.ir.player.capabilities["sight_range_m"] == 5.0
    assert host.ir.player.capabilities["hearing_range_m"] == 8.0
    entities = {
        _PLAYER: {"name": "测试者"},
        _MERCHANT: {"name": "商人"},
        _WANDERER: {"name": "旅人"},
    }
    source = ObservationSource(observer_id=_PLAYER, domain="world", tick=1)
    result = build_observations(
        _POSITIONS,
        {_PLAYER: PerceptionRange(sight_m=5.0, hearing_m=8.0)},
        entities,
        source,
    )
    assert [(r.payload["entity_id"], r.payload["kind"], r.payload["distance_m"])
            for r in result.records] == [
        (_MERCHANT, "hearing", 1),
        (_MERCHANT, "sight", 1),
    ]
    # 玩家知识面：2 条信念（sight/hearing，主体 = merchant，置信 0.5）：
    player_knowledge = KnowledgeState()
    new_knowledge, events = apply_observations(player_knowledge, result)
    assert len(events) == 2
    assert len(new_knowledge.beliefs) == 2
    assert {b.subject for b in new_knowledge.beliefs} == {_MERCHANT}
    assert {b.predicate for b in new_knowledge.beliefs} == {"hearing", "sight"}
    assert {b.confidence for b in new_knowledge.beliefs} == {0.5}
    assert {b.formed_tick for b in new_knowledge.beliefs} == {1}
    # prompt 摘要面（W3 格式钉：subject=predicate=value:confidence）：
    summary = knowledge_summary(new_knowledge, _PLAYER)
    assert summary.startswith("knowledge[ent_authoring_player]: ")
    assert "ent_authoring_merchant=hearing=" in summary
    assert "ent_authoring_merchant=sight=" in summary
    assert ":0.5" in summary
    # wanderer 边界（异地点 → 零观察 → 零变化）：
    wanderer_result = build_observations(
        _POSITIONS,
        {_WANDERER: PerceptionRange(sight_m=5.0, hearing_m=8.0)},
        entities,
        ObservationSource(observer_id=_WANDERER, domain="world", tick=1),
    )
    assert wanderer_result.records == ()
    wanderer_knowledge = KnowledgeState()
    unchanged, zero_events = apply_observations(wanderer_knowledge, wanderer_result)
    assert zero_events == ()
    # KNOWLEDGE 载荷字节不变（core:165 面）：
    assert encode_knowledge(unchanged) == encode_knowledge(wanderer_knowledge)
    # MEMORY 面（零 belief 事件 → 零 memory 追加；事件驱动语义面）：
    memory: tuple[str, ...] = ()
    for _event in zero_events:  # 零事件 → 循环零次 → memory 不变
        memory = memory_append(memory, "entry")
    assert memory == ()
    # memory_append 确定性面（保时序 tuple 追加 + cap 保留最新）：
    assert memory_append((), "w1") == ("w1",)
    assert memory_append(("w1", "w2"), "w3", cap=2) == ("w2", "w3")
    assert memory_append(("w1",), "w2", cap=0) == ()


def test_g9_sandbox_t5_llm_dynamics(p9_host) -> None:
    """A10 + 装配单元（DEV-W7-3）：LLMWorldDynamics 直接绑定（frozen
    面 llm_world.py）+ 脚本 backend（key 形状对齐 P7 host 先例）→
    ``run_dynamics_turn``（host.py:86）产恰 1 条 ProposedEffect（host
    授权/事务面 = 测试宿主 CascadeExecutor 组装，默认 DENY + 单白名单）
    → COMMITTED + 世界变化可见（目标组件 diff 钉 + 输入纯不变）+
    调用面钉；同函数装配单元 = build_standard_dynamics（CompositeDynamics
    rule-first + 推理补位；metadata 折叠钉 + 子序 fan-out 委托钉）。"""
    host = p9_host(
        _SANDBOX,
        backend_script={("world_dynamics", Revision(0), 1): _LLM_WIRE},
    )
    llm_backend = LLMWorldDynamics(
        backend=host.backend,
        config=LLMWorldDynamicsConfig(
            capability_id="world_dynamics",
            prompt_ref="prompt://sandbox/dynamics",
        ),
        clock=FixedMonotonicClock(start_ms=0, step_ms=1),
    )
    # 冻结面 metadata 钉（llm_world.py:210）：
    meta = llm_backend.metadata()
    assert meta.backend_id == "llm_world_dynamics"
    assert meta.determinism == "nondeterministic"
    assert meta.implementation_type == "inference"
    assert meta.fidelity == "semantic"
    assert meta.replayable is False
    # 宿主驱动（P7 host 驱动 + 测试宿主授权面）：
    executor = _authority_executor("llm_world_dynamics", _ATTRS)
    snapshot = WorldSnapshot(
        world_state=host.world,
        world_revision=host.world.world_revision,
        logical_tick=1,
        world_instance_id=_WS,
    )
    context = DynamicsContext(base_revision=int(host.world.world_revision))
    turn = run_dynamics_turn(
        backend=llm_backend,
        snapshot=snapshot,
        stimuli=(),
        context=context,
        state=host.world,
        executor=executor,
        causal_root_id="dyn_sandbox_t5",
        origin=Provenance(
            producer_id=ProducerId("llm_world_dynamics"),
            origin=OriginKind.DYNAMICS_BACKEND,
        ),
    )
    # 产出面（≥1 → 恰 1 条；K6 归属 + 确定性 effect_id 钉）：
    assert len(turn.effects) == 1
    effect = turn.effects[0]
    assert effect.source == "llm_world_dynamics"
    assert effect.effect_type == "core.set_component"
    assert effect.effect_id == new_deterministic_effect_id(
        "inference", 0, 0, "core.set_component", _MERCHANT,
    )
    assert str(effect.target.entity_id) == _MERCHANT
    assert turn.diagnostics == ()
    # 事务面（COMMITTED + 世界变化可见 + 纯函数零输入变更）：
    assert len(turn.result.transactions) == 1
    assert turn.result.transactions[0].status is TransactionStatus.COMMITTED
    assert _merchant_table(turn.result.final_state) == {
        "fatigue": 12.0, "morale": 41.0,
    }
    assert _merchant_table(host.world) == {"fatigue": 10.0, "morale": 40.0}
    # 推理调用面（脚本 backend 恰 1 次；key 形状对齐 P7 host 先例）：
    assert len(host.backend.calls) == 1
    assert host.backend.calls[0].logical_role == "world_dynamics"
    # 装配单元（DEV-W7-3）：build_standard_dynamics = P7 CompositeDynamics
    # 标准装配（rule 子在前 + 推理子在后；weight 声明参数不消费）：
    llm_backend_2 = LLMWorldDynamics(
        backend=FakeInferenceBackend(
            # 装配 world = tick 5 后（revision 5）→ 脚本 key 的
            # base_revision 面 = Revision(5)：
            script={("world_dynamics", Revision(5), 1): _LLM_WIRE},
        ),
        config=LLMWorldDynamicsConfig(
            capability_id="world_dynamics",
            prompt_ref="prompt://sandbox/dynamics",
        ),
        clock=FixedMonotonicClock(start_ms=0, step_ms=1),
    )
    binding = build_standard_dynamics(RuleDynamics(rules=(_a11_rule(),)), llm_backend_2)
    assert isinstance(binding, DynamicsBinding)
    # frozen 面钉（SOT §3.13 行 1「frozen dataclass」；R3 S-4 补充）：
    # 突变必须抛 FrozenInstanceError（frozen=True 被移除 = 本断言红）。
    try:
        binding.backend = None  # type: ignore[misc]
    except FrozenInstanceError:
        pass
    else:
        raise AssertionError("DynamicsBinding 非 frozen（SOT §3.13 行 1 面）")
    assert isinstance(binding.backend, CompositeDynamics)
    with pytest.raises(ValueError):
        build_standard_dynamics(RuleDynamics(rules=()), llm_backend_2, weight=1)
    # metadata 折叠钉（composite.py:87–120 冻结语义）：
    composite_meta = binding.backend.metadata()
    assert composite_meta.backend_id == "composite_dynamics"
    assert composite_meta.implementation_type == "composite"
    assert composite_meta.determinism == "nondeterministic"
    assert composite_meta.fidelity == "composite.abstract.semantic"
    assert composite_meta.replayable is False
    assert composite_meta.checkpointable is True
    assert composite_meta.restorable is True
    # 子序 fan-out（rule 在前 + 推理补位）：threshold 点 world → rule 命中
    # 在前、推理效果在后：
    host_assembly = p9_host(_SANDBOX)
    host_assembly.tick(5)  # fatigue = 15.0（自然差阈值穿越点 → rule 命中）
    effects = binding.turn(host_assembly.world, 5)
    assert [e.source for e in effects] == ["rule_dynamics", "llm_world_dynamics"]
    assert effects[0].effect_type == "merchant.fatigued"
    assert effects[1].effect_type == "core.set_component"
    assert llm_backend_2.diagnostics == ()


def test_g9_sandbox_t6_rules_dynamics(p9_host) -> None:
    """A11 + DSL 交叉面：RuleDynamics 单绑定（冻结面 rule.py:273；非
    composite，保证非命中刻零效果）→ 命中 tick = 5（fixture 规则穿越带
    [15.0, 16.0) ≡ 等值 15.0；相位 4 后首次观察）产恰 1 条效果
    （COMMITTED + p9.fatigue_flag 组件面可见 + 确定性 effect_id 钉）；
    逐刻效果流计数钉 {3:0, 4:0, 5:1, 6:0, 7:0}；DSL 面同源交叉验证
    （fixture 规则 parse_dsl/evaluate_condition 逐刻判定 == 规则效果
    产生集合，零随机注入）。"""
    host = p9_host(_SANDBOX)
    # fixture 规则面（validate 零 ERROR 前件已由宿主加载保证；parse 面钉）：
    assert [r.id for r in host.ir.rules] == ["rule_merchant_fatigue"]
    rule_spec = host.ir.rules[0]
    parsed = parse_dsl(rule_spec.condition, path_label="sandbox_rules:rule_merchant_fatigue")
    assert parsed.ast is not None
    assert parsed.diagnostics == ()
    # P7 RuleDynamics 单绑定（非 composite 面）：
    rule_backend = RuleDynamics(rules=(_a11_rule(),))
    assert rule_backend.metadata().backend_id == "rule_dynamics"
    assert rule_backend.metadata().determinism == "deterministic"
    executor = _authority_executor(
        "rule_dynamics", _FLAG,
        handlers=(("merchant.fatigued", _fatigue_flag_handler),),
    )
    origin = Provenance(producer_id=ProducerId("rule_dynamics"), origin=OriginKind.RULE)

    def _turn_at(tick: int):
        snapshot = WorldSnapshot(
            world_state=host.world,
            world_revision=host.world.world_revision,
            logical_tick=tick,
            world_instance_id=_WS,
        )
        context = DynamicsContext(base_revision=int(host.world.world_revision))
        return run_dynamics_turn(
            backend=rule_backend,
            snapshot=snapshot,
            stimuli=(),
            context=context,
            state=host.world,
            executor=executor,
            causal_root_id=f"dyn_sandbox_t6_{tick}",
            origin=origin,
        )

    # 逐刻效果流计数钉（ticks 3..7：相位 4 后 fatigue 13→17；命中刻 = 5 唯一）：
    counts: dict[int, int] = {}
    hit_tick: int | None = None
    for tick in range(3, 8):
        host.tick(tick)  # 逐刻推进（tick 1..tick；每刻相位 4 提交 1 条自然差）
        turn = _turn_at(tick)
        counts[tick] = len(turn.effects)
        assert turn.diagnostics == ()
        if turn.effects:
            assert hit_tick is None, "命中刻必须唯一"
            hit_tick = tick
            effect = turn.effects[0]
            assert effect.source == "rule_dynamics"
            assert effect.effect_type == "merchant.fatigued"
            # 确定性 effect_id 钉（tick 5 时宿主 revision = 5 条自然差）：
            assert effect.effect_id == new_deterministic_effect_id(
                "rule", "rule_merchant_fatigue_p7", 5, 0,
            )
            assert len(turn.result.transactions) == 1
            assert turn.result.transactions[0].status is TransactionStatus.COMMITTED
            # 世界变化可见（p9.fatigue_flag 组件面；纯函数零输入变更）：
            assert (
                turn.result.final_state.entities[EntityId(_MERCHANT)]
                .components[_FLAG]
                == {"state": "fatigued"}
            )
            assert _FLAG not in host.world.entities[EntityId(_MERCHANT)].components
    assert counts == {3: 0, 4: 0, 5: 1, 6: 0, 7: 0}
    assert hit_tick == 5
    # DSL 面同源交叉验证（fixture 规则逐刻判定 == 规则效果产生集合）：
    val = 10.0
    for tick in range(1, 9):
        val += 2.0 * 0.5
        outcome = evaluate_condition(
            parsed.ast,
            DslContext(variables={"merchant_fatigue": val}),
            _no_rng(),
        )
        assert (outcome.feasibility is Feasibility.ALLOWED) == (
            counts.get(tick, 0) == 1
        )


def test_g9_sandbox_t7_project_loads() -> None:
    """加载 + 构建前件（§3.16.2 步骤 1）：零 ERROR 加载
    （load/build_ir/validate_project 三面）；IR 面钉（5 文件白名单行
    36–40 形状：manifest/scenario DEV-W7-1 预裁决值 + 2 角色 + 2 地点
    + 1 规则 + 零 items/actions）。注：A16 = 迁移门（1:1 唯一挂
    test_v1_migration::t1，SOT G9-15 行），非本函数判据。"""
    result = load_project(_SANDBOX)
    assert result.raw is not None
    assert result.diagnostics == ()
    ir_result = build_ir(result.raw)
    assert ir_result.ir is not None
    assert ir_result.diagnostics == ()
    validation = validate_project(ir_result.ir, result.raw)
    assert validation.ok is True
    assert validation.diagnostics == ()
    ir = ir_result.ir
    assert ir.manifest.project_id == "sandbox"
    assert ir.scenario.id == "scenario_sandbox"
    assert ir.scenario.ticks_per_game_minute == 0.5
    assert ir.scenario.max_ticks == 16
    assert ir.player.player_id == "player"
    assert [c.id for c in sorted(ir.characters, key=lambda c: c.id)] == [
        "merchant", "wanderer",
    ]
    assert {l.id for l in ir.world.locations} == {"square", "camp"}
    assert ir.world.locations[0].connections["east"] == "camp"
    assert ir.items == ()
    assert ir.actions == ()
    assert [r.id for r in ir.rules] == ["rule_merchant_fatigue"]


def _canonical_runtime(runtime: RuntimeState) -> dict:
    """I-3 规范投影：跨构建允许的唯一差异 = scheduler_queue entry_id
    （uuid4 工厂面，scheduler ids.py:263–265）→ 占位符归一；其余字段
    原样保留（K7 JSON 规范化逐项比较）。"""
    dump = runtime.model_dump(mode="json")
    dump["scheduler_queue"] = [
        {**entry, "entry_id": "<entry_id:uuid>"}
        for entry in dump["scheduler_queue"]
    ]
    return dump


def _run_slice(factory, prompts_root: Path) -> tuple[dict, dict, tuple[dict[str, object], ...]]:
    """A23 切片序列 1–7 完整重跑（同脚本 + 同项目）：A6 长动作 →
    A7/A8（tick 4 + merchant 唤醒 tick 5）→ A10 推理 turn → A11 规则
    turn（tick 5 相位 4 后）→ 返回（世界权威状态 JSON, runtime 帧 I-3
    规范 JSON, 效果流 JSON 规范化逐条）。效果流 = 宿主 committed 流 +
    两 dynamics turn 流（执行序）。"""
    host = factory(
        _SANDBOX,
        backend_script={
            # 共享 backend 调用序号面：#1 = npc_policy（tick 5 相位 1，
            # base_revision 4）；#2 = world_dynamics（turn 在 tick 5 后，
            # base_revision 5，seq 2）：
            ("npc_policy", Revision(4), 1): _WAKE_SCRIPT,
            ("world_dynamics", Revision(5), 2): _LLM_WIRE,
        },
        prompt_root=prompts_root,
    )
    _start_long_action(host)
    host.tick(4)
    host.enqueue_wakeup("merchant", 5, "scene")
    host.tick(5)
    llm_backend = LLMWorldDynamics(
        backend=host.backend,
        config=LLMWorldDynamicsConfig(
            capability_id="world_dynamics",
            prompt_ref="prompt://sandbox/dynamics",
        ),
        clock=FixedMonotonicClock(start_ms=0, step_ms=1),
    )
    executor = _authority_executor("llm_world_dynamics", _ATTRS)
    snapshot = WorldSnapshot(
        world_state=host.world,
        world_revision=host.world.world_revision,
        logical_tick=5,
        world_instance_id=_WS,
    )
    context = DynamicsContext(base_revision=int(host.world.world_revision))
    llm_turn = run_dynamics_turn(
        backend=llm_backend,
        snapshot=snapshot,
        stimuli=(),
        context=context,
        state=host.world,
        executor=executor,
        causal_root_id="dyn_sandbox_t8_llm",
        origin=Provenance(
            producer_id=ProducerId("llm_world_dynamics"),
            origin=OriginKind.DYNAMICS_BACKEND,
        ),
    )
    rule_executor = _authority_executor(
        "rule_dynamics", _FLAG,
        handlers=(("merchant.fatigued", _fatigue_flag_handler),),
    )
    rule_context = DynamicsContext(base_revision=int(host.world.world_revision))
    rule_turn = run_dynamics_turn(
        backend=RuleDynamics(rules=(_a11_rule(),)),
        snapshot=snapshot,
        stimuli=(),
        context=rule_context,
        state=host.world,
        executor=rule_executor,
        causal_root_id="dyn_sandbox_t8_rule",
        origin=Provenance(producer_id=ProducerId("rule_dynamics"), origin=OriginKind.RULE),
    )
    stream = [e.model_dump(mode="json") for e in host.effects]
    stream.extend(e.model_dump(mode="json") for e in llm_turn.effects)
    stream.extend(e.model_dump(mode="json") for e in rule_turn.effects)
    assert len(llm_turn.effects) == 1 and len(rule_turn.effects) == 1
    return (
        host.world.model_dump(mode="json"),
        _canonical_runtime(host.runtime),
        tuple(stream),
    )


def test_g9_sandbox_t8_determinism_rerun(p9_host, tmp_path) -> None:
    """A23：完整重跑序列 1–7（两次独立宿主构建，同脚本同 seed）→
    效果流逐条相等（JSON 规范化后逐项比较）+ 世界权威状态逐字节相等
    （K7 JSON 规范化比较面）；I-3 裁定面：跨构建唯一差异 = scheduler
    entry_id uuid4（宿主相位 1 只消费 actor_wakeups 面，scheduler_queue
    孪生记录留存且 entry_id 跨构建异值——入 P8 快照 runtime 帧）→
    runtime 帧经 I-3 规范投影（entry_id 占位归一）后相等钉。"""
    world_a, runtime_a, stream_a = _run_slice(p9_host, tmp_path / "a")
    world_b, runtime_b, stream_b = _run_slice(p9_host, tmp_path / "b")
    # 效果流逐条相等（SOT §3.16.2 步骤 8 钉）：
    assert len(stream_a) == len(stream_b) == 7  # 宿主 5 + 推理 1 + 规则 1
    assert stream_a == stream_b
    # 世界权威状态逐字节相等（K7）：
    assert world_a == world_b
    # I-3：跨构建差异 = 仅 scheduler entry uuid4（规范投影后相等）：
    assert runtime_a == runtime_b
    assert len(runtime_a["scheduler_queue"]) == 1  # 唤醒孪生记录留存面
    assert runtime_a["scheduler_queue"][0]["entry_id"] == "<entry_id:uuid>"
    # 效果流 / 世界面 JSON-clean（json.dumps 零失败）：
    json.dumps(stream_a, sort_keys=True)
    json.dumps(world_a, sort_keys=True)
