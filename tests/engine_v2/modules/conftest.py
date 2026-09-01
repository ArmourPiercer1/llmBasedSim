"""P9 W1 tests/engine_v2/modules fixtures（SOT §6.2 的 W1 子集；零测试函数）。

W1 交付 = ``fixed_clock`` / ``scripted_backend`` / ``dsl_rng``。

波次拆分注（派工决定，SOT §6.2 = 最终形态）：``p9_host`` /
``p9_world_builder`` 两 fixture 待 W6（首个 g9 样例测试波）随宿主协议
（SOT §3.16）落盘；W1–W5 单测波不引用。

``SeededRng`` = 本包自含一份（口径对齐
``tests/engine_v2/content/conftest.py::SeededRng`` 先例；**不 import**
P5 测试侧 conftest）：实现 P5 ``DslRng`` Protocol 三方法
rand/uniform/randint，固定 seed（W1 默认 20240501）。
"""

from __future__ import annotations

import random

import pytest

from src.engine_v2.core.revision import Revision
from src.engine_v2.llm.adapter import FakeInferenceBackend, FixedMonotonicClock

#: 脚本钉面（测试侧常量）：键 = (logical_role, base_revision, 调用序号)；
#: 值 = 脚本回应 JSON（character 策略 capability 同串约定
#: ``npc_policy``；W1 t2/t3 消费）。
_SCRIPT_KEY = ("npc_policy", Revision(3), 1)
_SCRIPT_TEXT = (
    '{"action_id": "talk", "arguments": {"target": "player"},'
    ' "intent": "greet", "confidence": 0.9}'
)


class SeededRng:
    """确定性随机源（仅测试侧；实现 P5 ``DslRng`` Protocol 三方法口径）。

    - ``rand()`` → [0, 1) float；
    - ``uniform(lo, hi)`` → float；
    - ``randint(lo, hi)`` → 闭区间 int。

    底层 = stdlib ``random.Random``（固定 seed；测试代码允许 import
    random——src 不允许，确定性纪律的测试侧注脚）。
    """

    def __init__(self, seed: int = 20240501) -> None:
        self._random = random.Random(seed)

    def rand(self) -> float:
        return self._random.random()

    def uniform(self, lo: float, hi: float) -> float:
        return self._random.uniform(lo, hi)

    def randint(self, lo: int, hi: int) -> int:
        return self._random.randint(lo, hi)


@pytest.fixture
def fixed_clock() -> FixedMonotonicClock:
    """D6 注入时钟（后置自增：首次 ``now_ms()`` = 0）。"""
    return FixedMonotonicClock(start_ms=0, step_ms=1)


@pytest.fixture
def scripted_backend() -> FakeInferenceBackend:
    """脚本化 backend（钉死脚本映射；``calls`` 可供断言；未命中落
    default no-op 文本 ``{"action_id": null}``）。"""
    return FakeInferenceBackend(script={_SCRIPT_KEY: _SCRIPT_TEXT})


@pytest.fixture
def dsl_rng() -> SeededRng:
    """固定 seed ``DslRng``（t8/t9 确定性面；t12 = 零随机直引面，§3.17 D-α）。"""
    return SeededRng()


# ══════════════════════════════════════════════════════════════════════
# P9 W6 追加面（SOT §6.2 L1644–1656 / §3.16 宿主协议；W1 74 行块后纯
# 追加；零测试函数；宿主 = 测试代码，零 src 落位——SOT §3.16「宿主 =
# 测试代码，零 src 落位（runtime = P1）」）
#
# tick 循环相位序（常量钉；与 P7 host 相位同风格，
# run_dynamics_turn，dynamics/host.py:86）：
#
#   1. scheduler 到期事件：消费 ``actor_wakeups`` 中 due_tick == 本刻者
#      → ``run_policy_decide``（behavior_policy.py:83，脚本 backend）→
#      ActionProposal → 执行器（``register_executor`` 注册面）→ K2 管道
#      应用（无提案 / 无执行器 = 零效果）；
#   2. dynamics 轮：``set_dynamics`` 绑定面（W7 传 ``modules/dynamics.
#      py::DynamicsBinding``，SOT §3.13）；未绑定 = no-op（本波
#      galgame/tactical 零 dynamics）；
#   3. 触发器：W6 = 零触发器（扩展位，no-op）；
#   4. 属性自然差：``natural_delta_per_minute × ticks_per_game_minute``
#      （游戏分钟/刻 = scenario 字段，A7 口径公式），夹取 [min, max] →
#      ``core.set_component`` 效果（零差 / 无变化 = 零效果；本波样例
#      全 0 → 零效果）；
#   5. 生命周期推进：``ActiveAction.expected_end_tick == 本刻`` 且
#      ACTIVE → ``complete_action``（action_lifecycle.py:491；零完成
#      效果——completion_trigger 求值 = W7 消费面）。
#
# W7 兼容五面（DEV-W6-3）：相位序 + ``set_dynamics`` +
# ``enqueue_wakeup``（scheduler.py:374）+ K2 管道（authority/transaction
# 冻结面）+ 可重跑（宿主零模块级可变状态；同 (project_dir, seed,
# backend_script) 双构造 = 同效果流）。
# 备选（否）：无可枚举备选（SOT §6.2 未钉宿主五面具体值；实现设计面，
# W7 接缝 + 双构造可重跑约束）。
#
# K2 管道接线（常量钉，DEV-W6-3 项 4）：``ProposedEffect →
# check_authority（AuthorityPolicy，authority.py:550）→ validation →
# conflicts → Transaction → reducer``，经 ``CascadeExecutor``
# （cascade.py:767/867）：缺省 handler 注册表（结构效果
# ``core.set_component`` 等）；``AuthorityPolicy`` = 缺省 DENY + 单规则
# 授 host producer 写 P9 两组件（relationships/attributes）；零私有
# 访问。
#
# 关系组件（A3 组件面）：``ComponentTypeId("p9.relationships")``，
# payload = ``{"holder_id": str, "entries": [{"target_id", "affinity"},
# ...]}``（target_id 升序；W2 ``RelationshipState`` 元组 JSON 投影；
# pydantic payload_model 注册——reducer 应用点 D-8 校验面）。
#
# 世界哈希（DEV-W6-7）：P8 冻结快照面 ``to_persistence_snapshot``
# （persistence/snapshot.py:104）→ ``dump_persistence_snapshot``（:133）
# → sha256 hex（确定性、零 git 依赖；runtime 帧可显式钉定——A15 模式
# 变更面钉初始帧隔离世界侧不变性）。
# 备选（否）：git 依赖哈希（否因：违 D6 确定性）；手写序列化（否因：
# 与 P8 冻结快照面重复，漂移风险）。
#
# 实体 ID 词表（L1 校验 face，validation.py ``bad_id_kind`` 阶段钉）：
# 世界实体键 / 效果 target / wakeup / 上下文 actor_id = 规范型
# ``ent_authoring_<slug>``（core ids.py 内容侧确定性命名 ID 约定；
# 无前缀 slug 无法通过 K2 L1 ID 种类复检）。slug（authoring 词表）
# 保留面：relationships 组件 payload 的 holder_id/target_id、backend
# 脚本 JSON 参数、宿主方法面入参（``enqueue_wakeup("yuki")`` 经宿主
# 内部映射至规范型）。
# ══════════════════════════════════════════════════════════════════════

from hashlib import sha256
from pathlib import Path

from pydantic import BaseModel

from src.engine_v2.content.loader import load_project
from src.engine_v2.content.project_ir import build_ir
from src.engine_v2.content.schemas import ProjectIR
from src.engine_v2.content.validator import validate_project
from src.engine_v2.core.action_lifecycle import complete_action
from src.engine_v2.core.action_registry import ActionRegistry, ActionSpec, DurationPolicy
from src.engine_v2.core.actions import (
    ActionLifecycleStatus,
    ActionProposal,
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
from src.engine_v2.core.behavior_policy import run_policy_decide
from src.engine_v2.core.cascade import CascadeExecutor
from src.engine_v2.core.clock import rebuild_runtime, set_logical_tick
from src.engine_v2.core.components import (
    ComponentRegistry,
    ComponentSchema,
    ComponentTypeId,
)
from src.engine_v2.core.context_provider import ActorDecisionContext
from src.engine_v2.core.entity import EntityRecord
from src.engine_v2.core.effects import EffectTypeId, EntityTarget, ProposedEffect
from src.engine_v2.core.gameplay_mode import (
    ModeOverlay,
    ModeOverlayRegistry,
    apply_mode_change,
)
from src.engine_v2.core.ids import EffectId, EntityId
from src.engine_v2.core.provenance import OriginKind, Provenance
from src.engine_v2.core.revision import INITIAL_WORLD_REVISION
from src.engine_v2.core.scheduler import enqueue_actor_wakeup
from src.engine_v2.core.snapshot import snapshot
from src.engine_v2.core.space import (
    GraphSpace,
    GridSpace,
    SpaceBackend,
    SpaceMapping,
    SpaceRegistry,
    decode_spaces,
    encode_spaces,
)
from src.engine_v2.core.state import RuntimeState, WorldState
from src.engine_v2.core.transaction import TransactionStatus
from src.engine_v2.llm.adapter import FakeInferenceBackend, FixedMonotonicClock
from src.engine_v2.modules.actions import register_standard_actions
from src.engine_v2.modules.character import (
    build_character_record,
    build_npc_policy,
)
from src.engine_v2.modules.relationships import (
    RelationshipState,
    init_relationships,
)
from src.engine_v2.modules.space import register_standard_space
from src.engine_v2.modules.tactical import (
    TACTICAL_ACTION_IDS,
    TacticalModePolicy,
    TacticalOverlaySpec,
    build_tactical_overlay,
)
from src.engine_v2.persistence.snapshot import (
    dump_persistence_snapshot,
    to_persistence_snapshot,
)
from src.engine_v2.prompts.registry import PromptPolicy, TemplateStore

# ── P9 宿主常量（测试侧；确定性）──

#: P9 relationships 组件（A3 组件面；SOT 无内置——P9 注册，D-8）。
_RELATIONSHIPS_COMPONENT = ComponentTypeId("p9.relationships")
#: P9 attributes 组件（相位 4 自然差面）。
_ATTRIBUTES_COMPONENT = ComponentTypeId("p9.attributes")
#: host producer（K2 授权对象；OriginKind.DEVELOPER——宿主 = 测试侧驱动）。
_HOST_PRODUCER = ProducerId("p9.host")
_HOST_PROVENANCE = Provenance(producer_id=_HOST_PRODUCER, origin=OriginKind.DEVELOPER)
#: D-9：instance 身份在信封层（快照面）。
_WORLD_INSTANCE_ID = "p9_g9_instance"
#: 缺省 policy 模板（W1 先例文本；fixture 项目零 prompts 节时的宿主侧
#: 落盘面）。
_DEFAULT_POLICY_PROMPT = "角色 {{actor_id}}；人设：{{persona}}；场景：{{scene}}。请决策。"
_POLICY_TEMPLATE_REF = "prompts/npc_policy.md"


class _RelationshipEntry(BaseModel):
    """relationships 组件条目（payload_model 校验面，D-8 应用点）。"""

    target_id: str
    affinity: float


class _RelationshipPayload(BaseModel):
    """relationships 组件载荷（target_id 升序 = W2 输出序）。"""

    holder_id: str
    entries: list[_RelationshipEntry]


def _project_position(backend: SpaceBackend, x: float, y: float) -> object:
    """spec 坐标 → 域内位置（宿主投影面，常量钉）：grid = 恰含 x/y 两键
    int 坐标映射（core D-P4-10）；graph = ``hex_<x>_<y>`` 节点串
    （int 截断——W1 character.py position 同款口径）。"""
    if isinstance(backend, GridSpace):
        return {"x": int(x), "y": int(y)}
    return f"hex_{int(x)}_{int(y)}"


def _relationships_payload(holder_id: str, states) -> dict:
    """W2 状态元组 → 组件载荷（target_id 升序；W2 输出序已钉）。"""
    return {
        "holder_id": holder_id,
        "entries": [
            {"target_id": s.target_id, "affinity": s.affinity} for s in states
        ],
    }


def _build_mode_overlay(spec_id: str, mode_type: str, description: str) -> ModeOverlay:
    """GameplayModeSpec → ModeOverlay（宿主映射面，常量钉）：
    ``tactical`` 类型 → W6 ``build_tactical_overlay``（TACTICAL_ACTION_IDS
    allow 层）；其余（探索基线层）→ ``action_filter_kind = "none"``
    priority 0（无约束基线）。"""
    if mode_type == "tactical" or spec_id == "tactical":
        return build_tactical_overlay(
            TacticalOverlaySpec(
                mode_id=spec_id,
                available_actions=TACTICAL_ACTION_IDS,
                description=description,
            )
        )
    return ModeOverlay(
        mode_id=spec_id, priority=0, action_filter_kind="none",
        context={"description": description},
    )


class P9Host:
    """P9 通用宿主（conftest 私有类，零 src 落位；SOT §3.16 协议）。

    公开断言面：

    - ``world`` / ``runtime``：权威状态（单 WorldState 全程——tick 循环
      无重建）；
    - ``backend``：``FakeInferenceBackend``（``calls`` 计数可断言，A8/
      A14 面）；
    - ``effects``：committed 效果流（只追加元组；A23 双跑逐条对比面）；
    - ``proposals``：policy 产 ActionProposal 流（只追加元组；A2 面）；
    - ``ir`` / ``spaces`` / ``policies`` / ``mode_registry`` /
      ``action_registry`` / ``relationships`` / ``attributes``。

    宿主方法面：``tick(n)`` / ``enqueue_wakeup`` / ``register_executor``
    / ``set_dynamics`` / ``apply_effects`` / ``place_relationships`` /
    ``world_hash``。
    """

    def __init__(
        self,
        *,
        ir: ProjectIR,
        world: WorldState,
        runtime: RuntimeState,
        backend: FakeInferenceBackend,
        spaces: SpaceRegistry,
        policies: dict,
        mode_registry: ModeOverlayRegistry,
        action_registry: ActionRegistry,
        relationships: dict,
        attributes: dict,
        component_registry: ComponentRegistry,
    ) -> None:
        self.ir = ir
        self.world = world
        self.runtime = runtime
        self.backend = backend
        self.spaces = spaces
        self.policies = policies
        self.mode_registry = mode_registry
        self.action_registry = action_registry
        self.relationships = relationships
        self.attributes = attributes
        self.executors: dict = {}
        self.mode_policy: TacticalModePolicy = TacticalModePolicy()
        self.effects: tuple = ()
        self.proposals: tuple = ()
        self._dynamics = None
        producer_registry = ProducerRegistry()
        producer_registry.register(
            ProducerInfo(
                producer_id=_HOST_PRODUCER,
                origin=OriginKind.DEVELOPER,
                priority=100,
                description="P9 测试宿主（K2 管道写授权对象）",
            )
        )
        self._component_registry = component_registry
        authority_policy = AuthorityPolicy(
            rules=[
                AuthorityRule(
                    selector=AuthoritySelector(
                        component_type=_RELATIONSHIPS_COMPONENT,
                    ),
                    allowed_writers=[_HOST_PRODUCER],
                    priority=100,
                    rule_id="p9.host.relationships",
                ),
                AuthorityRule(
                    selector=AuthoritySelector(
                        component_type=_ATTRIBUTES_COMPONENT,
                    ),
                    allowed_writers=[_HOST_PRODUCER],
                    priority=100,
                    rule_id="p9.host.attributes",
                ),
            ],
            default_decision=AuthorityDecision.DENY,
        )
        self._cascade = CascadeExecutor(
            policy=authority_policy,
            component_registry=component_registry,
            producer_registry=producer_registry,
        )

    # —— W7 接缝面（DEV-W6-3）——

    def set_dynamics(self, binding) -> None:
        """绑定 dynamics 驱动闭包（W7 传 SOT §3.13 DynamicsBinding 适配
        闭包；驱动协议 = 宿主面：``callable(world, tick) ->
        Sequence[ProposedEffect]``）；未绑定 = 相位 2 no-op。"""
        self._dynamics = binding

    def register_executor(self, action_id: str, executor) -> None:
        """宿主执行器注册面（W4 ``ActionExecutor`` 协议对象；A14 面）。"""
        self.executors[action_id] = executor

    def enqueue_wakeup(self, actor_id: str, due_tick: int, reason: str | None = None) -> None:
        """``enqueue_actor_wakeup``（scheduler.py:374）宿主包装；
        ``actor_id`` = authoring slug（内部映射规范型实体 id）。"""
        self.runtime = enqueue_actor_wakeup(
            self.runtime, EntityId(_canonical(actor_id)), due_tick, reason
        )

    # —— tick 循环（相位序 = 追加段头注释块常量钉；SOT §6.2 面）——

    def tick(self, n: int) -> None:
        """推进逻辑刻至 ``n``（逐刻相位 1–5；n <= 当前刻 = no-op）。

        单一 WorldState / RuntimeState 全程（对象身份不变；revision 仅
        随 COMMITTED transaction 推进）。
        """
        while self.runtime.logical_tick < n:
            self.runtime = set_logical_tick(
                self.runtime, self.runtime.logical_tick + 1
            )
            tick = self.runtime.logical_tick
            self._phase_1_due_events(tick)
            self._phase_2_dynamics(tick)
            # 相位 3 = 触发器：W6 零触发器（扩展位 no-op）。
            self._phase_4_natural_delta(tick)
            self._phase_5_lifecycle(tick)

    def _phase_1_due_events(self, tick: int) -> None:
        """相位 1：到期 wakeup → policy 决策 → 执行器 → K2 应用。"""
        due = [w for w in self.runtime.actor_wakeups if w.due_tick == tick]
        if not due:
            return
        remaining = [w for w in self.runtime.actor_wakeups if w.due_tick != tick]
        for wakeup in due:  # 队列序（确定性）
            policy = self.policies.get(str(wakeup.actor_id))
            if policy is None:
                continue  # 无 policy 绑定（player / item）→ 零决策
            context = self._build_context(wakeup, tick)
            if context is None:
                continue
            proposal = run_policy_decide(policy, context)
            if proposal is None:
                continue
            self.proposals = self.proposals + (proposal,)
            self._execute_proposal(proposal, tick)
        self.runtime = rebuild_runtime(self.runtime, actor_wakeups=remaining)

    def _build_context(self, wakeup, tick: int) -> ActorDecisionContext | None:
        """ActorDecisionContext 构建（P4 先例形状；全字段显式）。"""
        view = self.world.entity_view(wakeup.actor_id)
        if view is None:
            return None
        return ActorDecisionContext(
            actor_id=wakeup.actor_id,
            tick=tick,
            base_world_revision=self.world.world_revision,
            wake_reason=wakeup.reason,
            self_view=view,
            visible_entities=frozenset(),
            local_entity_views={},
            global_entity_views=None,
            observations=(),
            knowledge=None,
            memory=(),
            candidate_actions=(),
            granted_capabilities=frozenset(),
        )

    def _execute_proposal(self, proposal: ActionProposal, tick: int) -> None:
        """提案 → 注册执行器（纯函数）→ committed 效果 K2 应用；无注册
        执行器（如 talk）= 提案记录、零效果。"""
        executor = self.executors.get(str(proposal.action_id))
        if executor is None:
            return
        result = executor.execute(proposal, self.world, tick)
        if result.failure is not None or not result.committed:
            return
        self.apply_effects(result.committed, causal_root_id=str(proposal.proposal_id))

    def _phase_2_dynamics(self, tick: int) -> None:
        """相位 2 = dynamics 轮（DEV-W6-3 项 3；W7 接缝）。

        绑定驱动闭包（``set_dynamics``）本刻求值产 ProposedEffect → K2
        应用；本波样例零绑定（no-op）。
        """
        if self._dynamics is None:
            return
        effects = self._dynamics(self.world, tick)
        if effects:
            self.apply_effects(tuple(effects), causal_root_id=f"dyn_{tick}")

    def _phase_4_natural_delta(self, tick: int) -> None:
        """相位 4 = 属性自然差（A7 口径公式；夹取 [min, max]；变化才产
        ``core.set_component`` 效果；本波样例零差 → 零效果）。"""
        minutes_per_tick = self.ir.scenario.ticks_per_game_minute
        effects: list[ProposedEffect] = []
        for slug in sorted(self.attributes):
            table = self.attributes[slug]
            changed = False
            for name in sorted(table):
                entry = table[name]
                delta = entry["natural_delta_per_minute"] * minutes_per_tick
                if delta == 0.0:
                    continue
                new_value = max(
                    entry["min"], min(entry["max"], entry["value"] + delta)
                )
                if new_value != entry["value"]:
                    entry["value"] = new_value
                    changed = True
            if changed:
                effects.append(
                    ProposedEffect(
                        effect_id=EffectId(
                            f"eff_attr_{slug}_{tick}_{len(self.effects)}"
                        ),
                        effect_type=EffectTypeId("core.set_component"),
                        source=_HOST_PRODUCER,
                        target=EntityTarget(
                            entity_id=EntityId(_canonical(slug)),
                            component_type=_ATTRIBUTES_COMPONENT,
                        ),
                        payload={
                            "attributes": {
                                name: entry["value"] for name, entry in table.items()
                            }
                        },
                        base_revision=self.world.world_revision,
                    )
                )
        if effects:
            self.apply_effects(tuple(effects), causal_root_id=f"attr_{tick}")

    def _phase_5_lifecycle(self, tick: int) -> None:
        """相位 5 = 生命周期推进（DEV-W6-3 项 2；A6 面）：ACTIVE 且
        ``expected_end_tick == 本刻`` → ``complete_action``
        （action_lifecycle.py:491；零完成效果）。"""
        for instance_id in sorted(self.runtime.active_actions):
            action = self.runtime.active_actions[instance_id]
            if action.status is not ActionLifecycleStatus.ACTIVE:
                continue
            if action.expected_end_tick != tick:
                continue
            self.world, self.runtime, _transition = complete_action(
                self.world,
                self.runtime,
                instance_id,
                at_tick=tick,
                completion_effects=(),
            )

    # —— K2 管道与宿主写面 ——

    def apply_effects(self, effects: tuple, *, causal_root_id: str) -> None:
        """经 core 冻结 authority/transaction 面应用 ProposedEffect（K2
        管道；DEV-W6-3 项 4）：``CascadeExecutor.run``（cascade.py:867）
        authority → validation → conflicts → Transaction → reducer；
        COMMITTED 效果流追加 ``host.effects``；``world`` =
        ``result.final_state``（单 WorldState 全程）。"""
        result = self._cascade.run(
            list(effects),
            self.world,
            causal_root_id=causal_root_id,
            origin=_HOST_PROVENANCE,
        )
        self.world = result.final_state
        committed = [
            committed_effect.effect
            for txn in result.transactions
            if txn.status is TransactionStatus.COMMITTED
            for committed_effect in txn.effects
        ]
        if committed:
            self.effects = self.effects + tuple(committed)

    def place_relationships(self, holder_id: str, states: tuple) -> None:
        """宿主关系落位面（A3；K2）：W2 ``adjust_relationship`` 产物 →
        relationships 组件（``core.set_component`` 结构效果 → K2 管道 →
        组件面可见）。``holder_id`` = authoring slug（内部映射规范型
        实体 target）。"""
        self.relationships[holder_id] = states
        effect = ProposedEffect(
            effect_id=EffectId(
                f"eff_rel_{holder_id}_{self.runtime.logical_tick}_{len(self.effects)}"
            ),
            effect_type=EffectTypeId("core.set_component"),
            source=_HOST_PRODUCER,
            target=EntityTarget(
                entity_id=EntityId(_canonical(holder_id)),
                component_type=_RELATIONSHIPS_COMPONENT,
            ),
            payload=_relationships_payload(holder_id, states),
            base_revision=self.world.world_revision,
        )
        self.apply_effects(
            (effect,),
            causal_root_id=f"rel_{holder_id}_{self.runtime.logical_tick}",
        )

    def world_hash(self, runtime: RuntimeState | None = None) -> str:
        """世界哈希（DEV-W6-7）：P8 冻结快照面
        ``to_persistence_snapshot``（persistence/snapshot.py:104）→
        ``dump_persistence_snapshot``（:133）→ sha256 hex（确定性、零 git
        依赖）。``runtime`` 缺省 = 当前 runtime 帧；显式帧 = 隔离世界侧
        不变性（A15 模式变更面钉初始帧）。"""
        frame = runtime if runtime is not None else self.runtime
        core_snapshot = snapshot(
            self.world,
            frame,
            _WORLD_INSTANCE_ID,
            project_version=self.ir.manifest.project_id,
            module_versions={},
        )
        envelope = to_persistence_snapshot(core_snapshot)
        text = dump_persistence_snapshot(envelope)
        return sha256(text.encode("utf-8")).hexdigest()

    def world_positions(self, domain_id: str) -> dict:
        """世界位置面（A4 感知 / A14 执行器消费）：实体规范 id
        （``ent_authoring_<slug>``）→ 域内位置（spaces 组件
        ``decode_spaces``（space.py:492）投影；无该域映射 = 缺席，不入
        表）。"""
        positions: dict = {}
        for entity_id, record in self.world.entities.items():
            payload = record.components.get(ComponentTypeId("spaces"))
            if payload is None:
                continue
            for mapping in decode_spaces(payload):
                if mapping.domain_id == domain_id:
                    positions[str(entity_id)] = mapping.position
        return positions


def _canonical(slug: str) -> str:
    """slug → 规范实体 id（core ids.py 内容侧确定性命名约定；L1
    ``bad_id_kind`` 校验面——无前缀 slug 无法通过 K2 管道复检）。"""
    return f"ent_authoring_{slug}"


def _build_world(ir: ProjectIR, domain_id: str, backend: SpaceBackend) -> tuple:
    """IR → WorldState + 宿主侧镜像（p9_world_builder 内核；三样例共用）。

    实体装配序（确定性）：characters（sorted id）→ player → items（sorted
    id）。实体键 = 规范型 ``ent_authoring_<slug>``；每实体组件：spaces
    （域投影，``_project_position`` 面）+ relationships（角色非空；
    payload = authoring slug 词表）+ attributes（非空）。宿主镜像
    （relationships/attributes）= slug 键（测试面）。
    """
    entries: dict = {}
    register_standard_space(entries, domain_id, backend)
    spaces = SpaceRegistry(entries)

    relationships: dict[str, tuple] = {}
    attributes: dict[str, dict] = {}
    records: list[EntityRecord] = []

    def _add(slug: str, entity_class: str, spec_position, rels, attrs) -> None:
        entity_id = _canonical(slug)
        components: dict = {}
        if spec_position is not None:
            position = _project_position(
                backend, float(spec_position.x), float(spec_position.y)
            )
            components[ComponentTypeId("spaces")] = encode_spaces(
                (SpaceMapping(domain_id=domain_id, position=position,
                              entered_tick=0),)
            )
        states = None
        if rels:
            states = init_relationships(rels, holder_id=slug)
            relationships[slug] = states
            components[_RELATIONSHIPS_COMPONENT] = _relationships_payload(
                slug, states
            )
        if attrs:
            table = {
                name: {
                    "value": float(item.value),
                    "min": float(item.min),
                    "max": float(item.max),
                    "natural_delta_per_minute": float(
                        item.natural_delta_per_minute
                    ),
                }
                for name, item in sorted(attrs.items())
            }
            attributes[slug] = table
            components[_ATTRIBUTES_COMPONENT] = {
                "attributes": {name: entry["value"] for name, entry in table.items()}
            }
        records.append(
            EntityRecord(
                entity_id=EntityId(entity_id),
                entity_class=entity_class,
                tags=[],
                created_revision=INITIAL_WORLD_REVISION,
                components=components,
            )
        )

    for character in sorted(ir.characters, key=lambda c: c.id):
        _add(
            character.id,
            "character",
            character.position,
            character.relationships,
            character.attributes,
        )
    _add(
        ir.player.player_id,
        "player",
        ir.player.position,
        {},
        ir.player.attributes,
    )
    for item in sorted(ir.items, key=lambda o: o.id):
        _add(item.id, "item", item.position, {}, {})

    world = WorldState(
        entities={record.entity_id: record for record in records}
    )
    return world, spaces, relationships, attributes


def _build_mode_surfaces(ir: ProjectIR) -> tuple:
    """GameplayModeSpec 节 → (ModeOverlayRegistry, 初始 active_modes,
    初始 mode_context)（宿主映射面，常量钉）：tactical 类型经 W6 模块
    overlay；探索基线 = none 层；初始 active = 探索基线（缺席 = 空）。"""
    overlays: dict[str, ModeOverlay] = {}
    for spec in sorted(ir.gameplay_modes, key=lambda s: s.id):
        overlays[spec.id] = _build_mode_overlay(
            spec.id, spec.mode_type, spec.description
        )
    registry = ModeOverlayRegistry(overlays) if overlays else ModeOverlayRegistry({})
    initial_active: list[str] = []
    initial_context: dict = {}
    if "exploration" in overlays:
        initial_active = ["exploration"]
        initial_context = {"exploration": overlays["exploration"].context}
    return registry, initial_active, initial_context


@pytest.fixture
def p9_world_builder():
    """helper fixture：IR → WorldState + 组件 + 空间域（SOT §6.2；三样例
    共用；参数 = 空间域构造器——tactical 样例传 hex 构造器，galgame 传
    缺省 grid 构造器）。返回可调用：
    ``(ir, domain_id, backend) -> (world, spaces, relationships,
    attributes)``。"""

    def _build(
        ir: ProjectIR, domain_id: str, backend: SpaceBackend
    ) -> tuple:
        return _build_world(ir, domain_id, backend)

    return _build


@pytest.fixture
def p9_host(p9_world_builder):
    """factory fixture：``(project_dir, *, seed=20240501,
    backend_script=None, domain_id="world", backend=None, prompt_root=
    None) -> P9Host``（SOT §6.2 形 + 空间域/模板扩展参）。

    职责链（§3.16 通用宿主协议）：``load_project`` → ``build_ir`` →
    ``validate_project``（断言零 ERROR，失败 = pytest.fail 携诊断）→
    依 IR 构建 WorldState（entities + 组件 + 空间域）→ 注册模块面
    （actions / space / mode / policy / narration 样式 / K2 管道）→
    返回 host 对象（``.tick(n)`` / ``.world`` / ``.effects`` /
    ``.backend``）。

    - ``backend`` 缺省 = 3×3 缺省 grid（galgame 面）；tactical 传
      hex ``GraphSpace``（``hex_adjacency`` 构造）+ 第二 grid 域由测试
      侧另注（A12 方格对照面）；
    - ``prompt_root`` 非 None 且无模板文件 → 宿主落盘缺省 policy 模板
      （W1 先例形状；fixture 项目零 prompts 节——白名单闭集）；
    - 缺省空间域 = grid 域 ``world``（10×10，覆盖样例坐标）；
    - 可重跑（DEV-W6-3 项 5）：宿主零模块级可变状态，同参数双构造 =
      同效果流。
    """

    def _make(
        project_dir,
        *,
        seed: int = 20240501,
        backend_script=None,
        domain_id: str = "world",
        backend: SpaceBackend | None = None,
        prompt_root: Path | None = None,
    ) -> P9Host:
        _seed = seed  # 宿主当前零随机消费；接缝保留（可重跑面）
        result = load_project(str(project_dir))
        assert result.raw is not None, f"load_project 失败：{project_dir}"
        ir_result = build_ir(result.raw)
        validation = validate_project(ir_result.ir, result.raw) if ir_result.ir else None
        errors = (
            [d for d in validation.diagnostics if d.severity.value == "ERROR"]
            if validation is not None
            else ["build_ir 失败"]
        )
        assert not errors, f"validate_project 非零 ERROR：{errors}"
        ir = ir_result.ir

        domain_backend = backend if backend is not None else GridSpace(
            width=10, height=10
        )
        world, spaces, relationships, attributes = p9_world_builder(
            ir, domain_id, domain_backend
        )
        mode_registry, initial_active, initial_context = _build_mode_surfaces(ir)
        runtime = RuntimeState(
            logical_tick=0,
            active_modes=initial_active,
            mode_context=initial_context,
        )

        # —— 动作注册表（IR 声明 + W4 标准六动作注册面）——
        action_registry = ActionRegistry(
            specs={
                ActionTypeId(spec.id): ActionSpec(
                    action_id=ActionTypeId(spec.id),
                    executor=f"p9.{spec.id}",
                    parameters={},
                    duration_policy=DurationPolicy(kind="none"),
                    interruptible=True,
                    completion_trigger=None,
                    tags=["p9-project-action"],
                )
                for spec in ir.actions
            }
        )
        register_standard_actions(action_registry, spaces, {})

        # —— 组件注册表（P9 两组件 payload_model 校验面）——
        component_registry = ComponentRegistry()
        component_registry.register(
            ComponentSchema(
                component_type=_RELATIONSHIPS_COMPONENT,
                version=1,
                description="P9 关系组件（W2 状态投影）",
                payload_model=_RelationshipPayload,
            )
        )

        # —— policy 面（W1 build_npc_policy；每角色一 policy）——
        if prompt_root is not None:
            prompts_dir = Path(prompt_root) / "prompts"
            template_file = prompts_dir / "npc_policy.md"
            if not template_file.exists():
                prompts_dir.mkdir(parents=True, exist_ok=True)
                template_file.write_text(
                    _DEFAULT_POLICY_PROMPT, encoding="utf-8"
                )
        store_root = Path(prompt_root) if prompt_root is not None else Path(project_dir)
        template_store = TemplateStore(
            project_root=store_root,
            policies=(
                PromptPolicy(
                    id="npc_policy",
                    scope="character_scene",
                    template_ref=_POLICY_TEMPLATE_REF,
                    variables=("actor_id", "persona", "scene"),
                ),
            ),
        )
        clock = FixedMonotonicClock(start_ms=0, step_ms=1)
        fake_backend = FakeInferenceBackend(
            script=dict(backend_script) if backend_script else {}
        )
        policies: dict = {}
        for character in sorted(ir.characters, key=lambda c: c.id):
            # 规范型 character_id（B-CON-5：提案 actor_id 恒 = record
            # character_id，须与世界实体键同词表——ent_authoring_ 前缀）
            record = build_character_record(
                character.model_copy(update={"id": _canonical(character.id)})
            )
            policies[_canonical(character.id)] = build_npc_policy(
                record, fake_backend, template_store, clock
            )

        return P9Host(
            ir=ir,
            world=world,
            runtime=runtime,
            backend=fake_backend,
            spaces=spaces,
            policies=policies,
            mode_registry=mode_registry,
            action_registry=action_registry,
            relationships=relationships,
            attributes=attributes,
            component_registry=component_registry,
        )

    return _make

