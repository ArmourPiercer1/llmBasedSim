"""W4 测试钉面：actions（T08；SOT §3.9；测试表 §6.1 行 1–6）。

钉面清单（SOT §3.9 表行 1–5，任务书 §1.2）：
- ``STANDARD_ACTION_IDS`` 六 id 逐字 + ``IDENTITY`` requires 面；
- ``MoveExecutor``：v1 移动对齐面（state_apply.py:35–39 / :158–166；
  rules.py:208–222 规则 5 体宽预检 = v2 空间校验重写披露面）；当前位置
  读取 = ``SPACES_COMPONENT`` 冻结面（space.py:447）+ ``decode_spaces``；
  确定性 9 步检查序（失败面：零异常、零状态变更，K2）；成功面 = 恰 1
  条 ``space.move`` ``ProposedEffect``（K6 PROPOSAL 因果引用钉）；
- ``ExecutorResult`` 三字段面（``duration_ticks`` 长动作面 +
  ``start_action``（scheduler.py:468）两跳生命周期钉）；
- P5 ``check_action_feasibility``（rule_module.py:1169；v1 对齐面 =
  rules.py:122–225）规则预判面（项目规则 match / condition 分支 + 永不
  抛 skip 钉）；
- ``register_standard_actions`` 幂等（覆盖 + 结构化 tags 诊断钉）。

零 fixture：全部输入本地字面量构造；零随机。确定性：零 uuid。
"""

from __future__ import annotations

from src.engine_v2.content.rule_module import (
    ActionInput,
    DslContext,
    Feasibility,
    RuleSpec,
    check_action_feasibility,
)
from src.engine_v2.core.action_lifecycle import (
    LifecycleEvent,
    LifecycleTransition,
)
from src.engine_v2.core.action_registry import (
    ActionRegistry,
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
from src.engine_v2.core.effects import (
    EffectTypeId,
    EntityTarget,
)
from src.engine_v2.core.ids import (
    ActionInstanceId,
    EffectId,
    EntityId,
    ProducerId,
)
from src.engine_v2.core.provenance import (
    CauseKind,
    CauseRef,
    OriginKind,
    Provenance,
)
from src.engine_v2.core.revision import Revision
from src.engine_v2.core.scheduler import start_action
from src.engine_v2.core.space import (
    SPACES_COMPONENT,
    SpaceMapping,
    SpaceRegistry,
    SpatialDomain,
    encode_spaces,
    make_backend,
)
from src.engine_v2.core.state import (
    EntityRecord,
    RuntimeState,
    WorldState,
)
from src.engine_v2.modules.actions import (
    IDENTITY,
    STANDARD_ACTION_IDS,
    ActionExecutor,
    ExecutorResult,
    MoveExecutor,
    register_standard_actions,
)


def _world_at(actor: str, domain: str, position: object) -> WorldState:
    """单 actor 世界（spaces 组件 = 单域映射，冻结 SPACES_COMPONENT 面）。"""
    return WorldState(
        entities={
            EntityId(actor): EntityRecord(
                entity_id=EntityId(actor),
                components={
                    SPACES_COMPONENT: encode_spaces(
                        (SpaceMapping(domain_id=domain, position=position),),
                    ),
                },
            ),
        },
    )


def _move_proposal(
    actor: str, pid: str, target: object | None,
) -> ActionProposal:
    """确定性 move 提案（``target=None`` = 缺 target_position 参数面）。"""
    arguments: dict[str, object] = {}
    if target is not None:
        arguments["target_position"] = target
    return ActionProposal(
        proposal_id=ActionInstanceId(pid),
        actor_id=EntityId(actor),
        action_id=ActionTypeId("move"),
        arguments=arguments,
        intent="移动",
        timing=ActionTiming(),
        base_world_revision=Revision(0),
        provenance=Provenance(
            producer_id=ProducerId("scenario.test"),
            origin=OriginKind.SCENARIO,
        ),
    )


def _graph_space() -> SpaceRegistry:
    """graph 域 ``outdoor``：hall—door—garden 链。"""
    graph = make_backend(
        "graph",
        {
            "nodes": ["hall", "door", "garden"],
            "edges": [("hall", "door"), ("door", "garden")],
        },
    )
    return SpaceRegistry(
        {"outdoor": (
            SpatialDomain(domain_id="outdoor", backend_kind="graph"),
            graph,
        )},
    )


def test_action_executors_t1_move_graphspace() -> None:
    """t1：``MoveExecutor`` 经 ``GraphSpace`` 邻接移动成功（全字段钉）。"""
    space = _graph_space()
    ex = MoveExecutor(space, "outdoor")
    assert isinstance(ex, ActionExecutor)
    world = _world_at("ent_npc_a", "outdoor", "hall")
    before = world.model_dump()
    result = ex.execute(
        _move_proposal("ent_npc_a", "act_s1", "door"), world, 3,
    )
    assert isinstance(result, ExecutorResult)
    assert result.failure is None and result.duration_ticks == 0
    assert len(result.committed) == 1
    e = result.committed[0]
    assert type(e.effect_id) is EffectId
    assert e.effect_id == "eff_move_ent_npc_a_3"
    assert type(e.effect_type) is EffectTypeId
    assert e.effect_type == "space.move"
    assert type(e.source) is ProducerId
    assert e.source == "actions.move"
    assert type(e.target) is EntityTarget
    assert e.target.kind == "entity"
    assert e.target.entity_id == "ent_npc_a"
    assert e.target.component_type == SPACES_COMPONENT
    assert e.target.field_path is None
    assert e.payload == {"domain": "outdoor", "position": "door"}
    assert e.base_revision == world.world_revision
    assert len(e.cause_ids) == 1
    assert e.cause_ids[0] == CauseRef(
        kind=CauseKind.PROPOSAL, ref_id="act_s1",
    )
    assert world.model_dump() == before  # K2：world 只读


def test_action_executors_t2_move_grid() -> None:
    """t2：``GridSpace`` 曼哈顿邻移（右移一格）。"""
    grid = make_backend("grid", {"width": 3, "height": 2})
    space = SpaceRegistry(
        {"city": (
            SpatialDomain(domain_id="city", backend_kind="grid"),
            grid,
        )},
    )
    ex = MoveExecutor(space, "city")
    world = _world_at("ent_npc_b", "city", {"x": 1, "y": 0})
    before = world.model_dump()
    result = ex.execute(
        _move_proposal("ent_npc_b", "act_s2", {"x": 2, "y": 0}), world, 4,
    )
    assert result.failure is None
    assert len(result.committed) == 1
    e = result.committed[0]
    assert e.effect_id == "eff_move_ent_npc_b_4"
    assert e.payload == {"domain": "city", "position": {"x": 2, "y": 0}}
    assert world.model_dump() == before  # K2：world 只读


def test_action_executors_t3_move_invalid() -> None:
    """t3：9 步检查序 failure 面（不可达/越界/无组件/缺参/无实体/载荷畸形/
    无域映射/域未注册/当前位置非法；零状态变更）。"""
    grid = make_backend("grid", {"width": 3, "height": 2})
    space = SpaceRegistry(
        {"city": (
            SpatialDomain(domain_id="city", backend_kind="grid"),
            grid,
        )},
    )
    ex = MoveExecutor(space, "city")
    world = _world_at("ent_npc_c", "city", {"x": 0, "y": 0})
    before = world.model_dump()
    # 对角非邻接（曼哈顿距离 2）→ 不可达：
    r = ex.execute(
        _move_proposal("ent_npc_c", "act_s3", {"x": 1, "y": 1}), world, 1,
    )
    assert r.committed == () and r.failure
    assert "不可达" in r.failure
    # 越界（x = 5 > width - 1）：
    r = ex.execute(
        _move_proposal("ent_npc_c", "act_s3", {"x": 5, "y": 0}), world, 1,
    )
    assert r.committed == () and r.failure
    assert "越界" in r.failure
    # 无 spaces 组件实体：
    bare = WorldState(
        entities={EntityId("ent_d"): EntityRecord(entity_id=EntityId("ent_d"))},
    )
    r = ex.execute(
        _move_proposal("ent_d", "act_s3", {"x": 1, "y": 0}), bare, 1,
    )
    assert r.committed == () and r.failure
    assert "spaces 组件" in r.failure
    # 缺 target_position 参数：
    r = ex.execute(_move_proposal("ent_npc_c", "act_s3", None), world, 1)
    assert r.committed == () and r.failure
    assert "target_position" in r.failure
    # 实体不存在于世界：
    r = ex.execute(
        _move_proposal("ent_gone", "act_s3", {"x": 1, "y": 0}), world, 1,
    )
    assert r.committed == () and r.failure
    assert "不存在于世界" in r.failure
    # spaces 载荷畸形（decode_spaces 抛 ValueError → 确定性 failure）：
    malformed = WorldState(
        entities={
            EntityId("ent_bad"): EntityRecord(
                entity_id=EntityId("ent_bad"),
                components={
                    SPACES_COMPONENT: {"mappings": [{"domain_id": 42}]},
                },
            ),
        },
    )
    before_m = malformed.model_dump()
    r = ex.execute(
        _move_proposal("ent_bad", "act_s3", {"x": 1, "y": 0}), malformed, 1,
    )
    assert r.committed == () and r.failure
    assert "spaces 载荷畸形" in r.failure
    # 实体有 spaces 组件但本域无映射：
    other_world = _world_at("ent_npc_c", "other", {"x": 0, "y": 0})
    before_o = other_world.model_dump()
    r = ex.execute(
        _move_proposal("ent_npc_c", "act_s3", {"x": 1, "y": 0}), other_world, 1,
    )
    assert r.committed == () and r.failure
    assert "域位置映射" in r.failure
    # 域未注册（有该域映射 → 过第 4 步；backend 查询抛 UnknownDomainError）：
    ex2 = MoveExecutor(space, "unregistered")
    unreg_world = _world_at("ent_npc_c", "unregistered", "hall")
    before_u = unreg_world.model_dump()
    r = ex2.execute(
        _move_proposal("ent_npc_c", "act_s3", {"x": 1, "y": 0}), unreg_world, 1,
    )
    assert r.committed == () and r.failure
    assert "未注册" in r.failure
    # 当前位置非法（有映射但位置越出网格）：
    inv_world = _world_at("ent_npc_c", "city", {"x": 9, "y": 0})
    before_i = inv_world.model_dump()
    r = ex.execute(
        _move_proposal("ent_npc_c", "act_s3", {"x": 1, "y": 0}), inv_world, 1,
    )
    assert r.committed == () and r.failure
    assert "当前位置非法" in r.failure
    # 零状态变更：
    assert world.model_dump() == before
    assert malformed.model_dump() == before_m
    assert other_world.model_dump() == before_o
    assert unreg_world.model_dump() == before_u
    assert inv_world.model_dump() == before_i
    assert bare.model_dump() == WorldState(
        entities={EntityId("ent_d"): EntityRecord(entity_id=EntityId("ent_d"))},
    ).model_dump()


def test_action_executors_t4_long_action_duration() -> None:
    """t4：``duration_ticks`` 面 + ``start_action`` 两跳生命周期（单元级）。"""
    # ExecutorResult 长动作面（committed 空 + failure 空 + 时长 > 0）：
    long_result = ExecutorResult(
        committed=(), failure=None, duration_ticks=3,
    )
    assert long_result.duration_ticks == 3
    assert long_result.committed == () and long_result.failure is None
    # start_action：PROPOSED → VALIDATING → ACTIVE（2 条 LifecycleTransition）：
    spec = ActionSpec(
        action_id=ActionTypeId("move"),
        executor="llmsim-standard-actions.move",
        parameters={},
        duration_policy=DurationPolicy(kind="fixed", duration_ticks=3),
    )
    proposal = _move_proposal("ent_npc_a", "act_long_1", "door")
    runtime = RuntimeState(
        logical_tick=10,
        active_actions={
            ActionInstanceId("act_long_1"): ActiveAction(
                instance_id=ActionInstanceId("act_long_1"),
                action_id=ActionTypeId("move"),
                actor_id=EntityId("ent_npc_a"),
                status=ActionLifecycleStatus.PROPOSED,
                start_tick=10,
                base_world_revision=Revision(0),
                provenance=proposal.provenance,
            ),
        },
    )
    world = _world_at("ent_npc_a", "outdoor", "hall")
    new_world, new_runtime, transitions = start_action(
        world, runtime, proposal, spec,
        at_tick=10, checkpoint_interval=None,
    )
    assert new_world is world  # 输入原样返回、同一对象
    assert new_world.world_revision == world.world_revision  # 零 revision 推进
    assert len(transitions) == 2
    t1, t2 = transitions
    assert isinstance(t1, LifecycleTransition)
    assert isinstance(t2, LifecycleTransition)
    assert t1.event is LifecycleEvent.VALIDATION_ACCEPTED
    assert t1.from_status is ActionLifecycleStatus.PROPOSED
    assert t1.to_status is ActionLifecycleStatus.VALIDATING
    assert t1.at_tick == 10
    assert t2.event is LifecycleEvent.SCHEDULED
    assert t2.from_status is ActionLifecycleStatus.VALIDATING
    assert t2.to_status is ActionLifecycleStatus.ACTIVE
    assert t2.at_tick == 10
    active = new_runtime.active_actions[ActionInstanceId("act_long_1")]
    assert active.status is ActionLifecycleStatus.ACTIVE
    assert active.start_tick == 10
    assert active.expected_end_tick == 13  # 10 + fixed(3)


def test_action_executors_t5_feasibility_dsl() -> None:
    """t5：动作条件经 P5 ``check_action_feasibility`` 判定面（永不抛）。

    v1 对齐面：src/game/rules.py:122–225（v1 ``check_action_feasibility``）；
    v2 = rule_module.py:1169（项目规则 match / condition 分支 + 内置
    1..5；全 miss = None；失效条件 warn + skip，零异常）。
    """
    action = ActionInput(raw_input="拿起 铁锤")
    # ── 项目规则：match 正则命中 + feasibility = blocked → BLOCKED ──
    heavy = RuleSpec(
        id="heavy",
        description="太重无法搬起",
        match="拿起",
        feasibility="blocked",
    )
    r = check_action_feasibility((heavy,), action, DslContext(), {}, {})
    assert r is not None
    assert r.feasibility is Feasibility.BLOCKED
    assert r.matched_rule == "custom:heavy"
    assert r.reason == "系统规则预判（heavy）：太重无法搬起"
    assert r.requires_roll is False
    assert r.success_probability is None
    # ── 项目规则：condition DSL（player.strength 三值判定）──
    gate = RuleSpec(
        id="strength_gate",
        description="力气门槛",
        match="拿起",
        condition="if(player.strength >= 30, allowed; blocked)",
    )
    weak = DslContext(player={"physical_profile": {"strength": 10}})
    r = check_action_feasibility((gate,), action, weak, {}, {})
    assert r is not None
    assert r.feasibility is Feasibility.BLOCKED
    assert r.matched_rule == "custom:strength_gate"
    assert r.reason == "系统规则预判（strength_gate）：力气门槛"
    assert r.requires_roll is False
    strong = DslContext(player={"physical_profile": {"strength": 30}})
    r = check_action_feasibility((gate,), action, strong, {}, {})
    assert r is not None
    assert r.feasibility is Feasibility.ALLOWED
    assert r.matched_rule == "custom:strength_gate"
    assert r.requires_roll is False
    # ── 永不抛：condition parse 失败 → warn + skip（全 miss = None）──
    broken = RuleSpec(
        id="broken_rule",
        description="条件畸形",
        match="拿起",
        condition="if(player.strength >= 30, allowed)",
    )
    assert check_action_feasibility(
        (broken,), action, strong, {}, {},
    ) is None


def test_action_executors_t6_register_idempotent() -> None:
    """t6：``register_standard_actions`` 幂等（重复注册覆盖 + tags 诊断）。"""
    # 六 id 逐字 + 身份面钉：
    assert STANDARD_ACTION_IDS == (
        "move", "talk", "inspect", "pickup", "drop", "wait",
    )
    assert IDENTITY.module_id == "llmsim-standard-actions"
    assert IDENTITY.requires == (
        "llmsim-standard-space", "llmsim-standard-inventory",
    )
    space = _graph_space()
    ex = MoveExecutor(space, "outdoor")
    registry = ActionRegistry()
    register_standard_actions(registry, space, {"move": ex})
    assert len(registry.specs) == 6
    move1 = registry.specs[ActionTypeId("move")]
    talk1 = registry.specs[ActionTypeId("talk")]
    assert move1.action_id == ActionTypeId("move")
    assert move1.executor == "llmsim-standard-actions.move"
    assert move1.parameters == {}
    assert move1.duration_policy.kind == "none"
    assert move1.interruptible is True
    assert move1.completion_trigger is None
    assert move1.tags == ["p9-standard-actions", "p9.register-count.1"]
    # 执行器缺席 → 结构化诊断标记（不静默）：
    assert talk1.tags == [
        "p9-standard-actions", "p9.register-count.1", "p9.executor-missing",
    ]
    # 第二次注册：覆盖（计数诊断 +1；非 tags 字段逐字相等）：
    register_standard_actions(registry, space, {"move": ex})
    assert len(registry.specs) == 6
    move2 = registry.specs[ActionTypeId("move")]
    assert move2.tags == ["p9-standard-actions", "p9.register-count.2"]
    assert (
        move2.executor, move2.parameters, move2.duration_policy,
        move2.interruptible, move2.completion_trigger,
    ) == (
        move1.executor, move1.parameters, move1.duration_policy,
        move1.interruptible, move1.completion_trigger,
    )
