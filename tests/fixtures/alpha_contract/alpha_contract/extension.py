"""alpha_contract — 0.1.0-alpha.1 contract 验证扩展（中性，零玩法语义）。

M3.5：不依赖具体玩法语义的通用 test extension。本包只做 contract 面的
机械验证：纯 solver 可被 executor 调用、一次动作 0..N 效果（多实体/多
域）、确定性 failure 路径（零效果）、无授权 producer 的 deny 路径、
数值后端经正式 authority 管道写组件与 state domain（world_variables /
scenario）、世界时间增量 = 当前 WorldState 的函数。

K2：零直写——只返回 ProposedEffect；K7：零随机 / 零墙钟 / 零 I/O。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import TYPE_CHECKING, Final

from src.engine_v2.core.components import ComponentTypeId
from src.engine_v2.core.effects import (
    EffectTypeId,
    EntityTarget,
    ProposedEffect,
    StateDomainTarget,
)
from src.engine_v2.core.ids import EntityId, ProducerId
from src.engine_v2.core.provenance import CauseKind, CauseRef
from src.engine_v2.core.revision import Revision
from src.engine_v2.dynamics.backend import BackendMetadata, new_deterministic_effect_id
from src.engine_v2.modules.actions import ExecutorResult
from src.engine_v2.runtime.extensions import ExtensionBundle, ProducerGrant

if TYPE_CHECKING:
    from src.engine_v2.core.actions import ActionProposal
    from src.engine_v2.core.reducer import GuardedWorldState
    from src.engine_v2.dynamics.backend import DynamicsContext, Stimulus, WorldSnapshot
    from src.engine_v2.runtime.extensions import ExtensionContext

__all__ = [
    "ActionsExecutor",
    "UngrantedExecutor",
    "LabDynamics",
    "clamp_add",
    "build_extension",
]

GAUGE_COMPONENT = ComponentTypeId("gauge_reading")
ATTRIBUTES_COMPONENT = ComponentTypeId("attributes")

GAUGE_SLUG: Final[str] = "gauge"
RESPONDER_SLUG: Final[str] = "responder"
OPERATOR_SLUG: Final[str] = "operator"

# 授权面口径（P2 首匹配语义）：同一维度（组件类型 / 状态域名）的两条
# grant 规则中，先注册者首匹配拍板——后注册 producer 的写会被先注册
# 规则 deny（allowed_writers 单 producer）。因此本扩展用**单一受信
# producer** ``alpha_contract.core`` 承载 executor 与数值后端的全部
# 权威写（同维度不重叠），另设**零 grant** producer
# ``alpha_contract.ungranted`` 供 deny 路径验证。
CORE_PRODUCER: Final[ProducerId] = ProducerId("alpha_contract.core")
UNGRANTED_PRODUCER: Final[ProducerId] = ProducerId("alpha_contract.ungranted")

_SET_COMPONENT: Final[EffectTypeId] = EffectTypeId("core.set_component")
_SET_WORLD_VARIABLE: Final[EffectTypeId] = EffectTypeId("core.set_world_variable")
_SET_SCENARIO_DATA: Final[EffectTypeId] = EffectTypeId("core.set_scenario_data")

_ROUND = 6  # 数值面统一舍入位（K7 确定性；浮点面钉死）
_TICK_SECONDS: Final[float] = 1.0  # 世界时间每 tick 基准增量（秒）


def clamp_add(value: float, delta: float, lo: float, hi: float) -> float:
    """纯 solver：夹取增量（确定性、纯函数、无副作用）。

    executor 调用面（feature_support §3.3/§8.4：纯函数 solver 由 executor
    调用；engine 不消费、不内建任何数值语义）。
    """
    return round(min(hi, max(lo, value + delta)), _ROUND)


def _entity(world: "GuardedWorldState", slug: str) -> EntityId | None:
    eid = EntityId(f"ent_authoring_{slug}")
    return eid if world.has_entity(eid) else None


def _json_default(value: object) -> object:
    """guard 深冻结视图 → JSON 原生 plain 值（递归；json.dumps default
    钩子对每一层不可序列化对象各触发一次）。"""
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, (list, tuple)):
        return list(value)
    raise TypeError(f"组件数据含非 JSON 原生值：{type(value).__name__}")


def _component_data(world: "GuardedWorldState", slug: str, ct: ComponentTypeId) -> dict:
    eid = _entity(world, slug)
    if eid is None:
        return {}
    data = world.entities[eid].components.get(ct)
    if data is None:
        return {}
    # P0-A（审计发布前修复）：production 执行器面 = GuardedWorldState 深冻结
    # 视图——嵌套值是 _FrozenMapping / 冻结序列（非 JSON 原生值，不得入
    # ProposedEffect payload）。组件合并重写模式（读全量 → 改字段 → 整体
    # 写回）在此显式递归转 JSON 原生 plain 值（deterministic、无损）。
    return json.loads(
        json.dumps(dict(data), default=_json_default, ensure_ascii=False)
    )


def _num(data: dict, key: str, default: float) -> float:
    v = data.get(key)
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else default


def _arg_num(args: dict, key: str, default: float) -> float:
    v = args.get(key)
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else default


class ActionsExecutor:
    """producer ``alpha_contract.actions``——五 contract 动作。

    覆盖：纯 solver 调用 / 单效果组件写 / 一次动作三效果（多实体 + 组件域 +
    state domain）/ world 变量写（failure 前置 + 时间标度）/ 确定性
    failure 路径（零效果）。
    """

    def execute(
        self, proposal: "ActionProposal", world: "GuardedWorldState", tick: int
    ) -> ExecutorResult:
        handler = {
            "adjust_reading": self._adjust_reading,
            "multi_write": self._multi_write,
            "set_time_scale": self._set_time_scale,
            "set_lock": self._set_lock,
            "fail_when_locked": self._fail_when_locked,
        }.get(str(proposal.action_id))
        if handler is None:
            return ExecutorResult((), f"contract executor 不处理动作 {proposal.action_id!r}", 0)
        return handler(proposal, world)

    # —— 效果构造（K2 零直写；base_revision 对照当前权威修订）——

    def _effect(
        self,
        proposal: "ActionProposal",
        world: "GuardedWorldState",
        effect_type: EffectTypeId,
        target,
        payload: dict,
        tag: str,
    ) -> ProposedEffect:
        return ProposedEffect(
            effect_id=new_deterministic_effect_id(
                "alpha_contract.action", str(proposal.proposal_id), tag
            ),
            effect_type=effect_type,
            source=CORE_PRODUCER,
            target=target,
            payload=payload,
            base_revision=world.world_revision,
            cause_ids=[CauseRef(kind=CauseKind.PROPOSAL, ref_id=str(proposal.proposal_id))],
        )

    # —— 动作面 ——

    def _adjust_reading(self, proposal: "ActionProposal", world: "GuardedWorldState") -> ExecutorResult:
        gauge = _entity(world, GAUGE_SLUG)
        if gauge is None:
            return ExecutorResult((), "gauge 实体缺席（contract 前置不满足）", 0)
        current = _num(_component_data(world, GAUGE_SLUG, GAUGE_COMPONENT), "value", 0.0)
        scale_max = _num(_component_data(world, GAUGE_SLUG, ComponentTypeId("item")).get("properties", {}), "scale_max", 100.0)
        delta = _arg_num(proposal.arguments, "delta", 1.0)
        new_value = clamp_add(current, delta, 0.0, scale_max)
        effect = self._effect(
            proposal,
            world,
            _SET_COMPONENT,
            EntityTarget(entity_id=gauge, component_type=GAUGE_COMPONENT),
            {"value": new_value},
            "adjust_reading",
        )
        return ExecutorResult((effect,), None, 0)

    def _multi_write(self, proposal: "ActionProposal", world: "GuardedWorldState") -> ExecutorResult:
        gauge = _entity(world, GAUGE_SLUG)
        operator = _entity(world, OPERATOR_SLUG)
        if gauge is None or operator is None:
            return ExecutorResult((), "gauge/operator 实体缺席（contract 前置不满足）", 0)
        reading = _num(_component_data(world, GAUGE_SLUG, GAUGE_COMPONENT), "value", 0.0)
        shift = _num(_component_data(world, OPERATOR_SLUG, ATTRIBUTES_COMPONENT), "shift_minutes", 0.0)
        effects = (
            self._effect(
                proposal,
                world,
                _SET_COMPONENT,
                EntityTarget(entity_id=gauge, component_type=GAUGE_COMPONENT),
                {"value": round(reading + 10.0, _ROUND)},
                "multi_write.gauge",
            ),
            self._effect(
                proposal,
                world,
                _SET_COMPONENT,
                EntityTarget(entity_id=operator, component_type=ATTRIBUTES_COMPONENT),
                dict(_component_data(world, OPERATOR_SLUG, ATTRIBUTES_COMPONENT) | {
                    "shift_minutes": {
                        **_component_data(world, OPERATOR_SLUG, ATTRIBUTES_COMPONENT).get("shift_minutes", {}),
                        "value": round(shift + 30.0, _ROUND),
                    },
                }),
                "multi_write.attributes",
            ),
            self._effect(
                proposal,
                world,
                _SET_WORLD_VARIABLE,
                StateDomainTarget(domain="world_variables"),
                {"key": "audit", "value": "multi_write"},
                "multi_write.audit",
            ),
        )
        return ExecutorResult(effects, None, 0)

    def _set_time_scale(self, proposal: "ActionProposal", world: "GuardedWorldState") -> ExecutorResult:
        scale = _arg_num(proposal.arguments, "scale", 1.0)
        effect = self._effect(
            proposal,
            world,
            _SET_WORLD_VARIABLE,
            StateDomainTarget(domain="world_variables"),
            {"key": "time_scale", "value": round(scale, _ROUND)},
            "set_time_scale",
        )
        return ExecutorResult((effect,), None, 0)

    def _set_lock(self, proposal: "ActionProposal", world: "GuardedWorldState") -> ExecutorResult:
        value = proposal.arguments.get("value", True)
        effect = self._effect(
            proposal,
            world,
            _SET_WORLD_VARIABLE,
            StateDomainTarget(domain="world_variables"),
            {"key": "lock", "value": value},
            "set_lock",
        )
        return ExecutorResult((effect,), None, 0)

    def _fail_when_locked(self, proposal: "ActionProposal", world: "GuardedWorldState") -> ExecutorResult:
        if bool(world.world_variables.get("lock")):
            return ExecutorResult((), "world locked（确定性 failure 路径：零效果、零状态变更）", 0)
        effect = self._effect(
            proposal,
            world,
            _SET_WORLD_VARIABLE,
            StateDomainTarget(domain="world_variables"),
            {"key": "last_action", "value": "fail_when_locked_ok"},
            "fail_when_locked",
        )
        return ExecutorResult((effect,), None, 0)


class UngrantedExecutor:
    """producer ``alpha_contract.ungranted``——**无 grant** 的组件写。

    contract 面：closed-by-default authority——该 producer 无任何
    ProducerGrant，其效果必须被 authority 拒绝且世界零变更（M4.3 面 11）。
    """

    def execute(
        self, proposal: "ActionProposal", world: "GuardedWorldState", tick: int
    ) -> ExecutorResult:
        gauge = _entity(world, GAUGE_SLUG)
        if gauge is None:
            return ExecutorResult((), "gauge 实体缺席", 0)
        effect = ProposedEffect(
            effect_id=new_deterministic_effect_id(
                "alpha_contract.ungranted", str(proposal.proposal_id), "ungranted_write"
            ),
            effect_type=_SET_COMPONENT,
            source=UNGRANTED_PRODUCER,
            target=EntityTarget(entity_id=gauge, component_type=GAUGE_COMPONENT),
            payload={"value": 999.0},
            base_revision=world.world_revision,
            cause_ids=[CauseRef(kind=CauseKind.PROPOSAL, ref_id=str(proposal.proposal_id))],
        )
        return ExecutorResult((effect,), None, 0)


class LabDynamics:
    """数值后端：组件写 + state-domain 写（world 时间 / scenario）。

    世界时间增量依赖当前 WorldState（feature_support §6/§21.5）：
    Δ = 基准 1.0s × world_variables["time_scale"]（缺位 1.0）——
    time_scale 经授权动作改写后，同一 tick 间隔的增量随之改变。
    世界时间 / 时间标度 / 审计等 world 变量**不存在作者声明面**——
    全部由本 backend 经 core.set_world_variable 建立（engine 不内建
    任何时间语义；§13 边界）。

    授权面（M2 口径）：``metadata().domains`` 声明组件类型 + 状态域名
    （world_variables / scenario）——bind_dynamics 据此派生 ProducerGrant，
    assembly 逐名分派（component_type 维 / domain_tag 维），写面全部经
    正式 authority 管道。
    """

    METADATA: Final[BackendMetadata] = BackendMetadata(
        backend_id="alpha_contract.lab_dynamics",
        producer_id=str(CORE_PRODUCER),
        domains=("gauge_reading", "scenario", "world_variables"),
        determinism="deterministic",
        implementation_type="numerical",
        fidelity="discrete_1d",
        checkpointable=True,
        restorable=True,
        replayable=True,
    )

    def metadata(self) -> BackendMetadata:
        return self.METADATA

    def simulate(
        self,
        snapshot: "WorldSnapshot",
        stimuli: tuple["Stimulus", ...],
        context: "DynamicsContext",
    ) -> tuple[ProposedEffect, ...]:
        world = snapshot.world_state
        base = Revision(context.base_revision)
        effects: list[ProposedEffect] = []

        # 1) 组件写：gauge 读数离散积分（+0.1/tick；缺位自举 0.0 参与，
        #    结果恒 > 0.0 → 每 tick 必产效果——K7 确定性）。
        gauge = _entity(world, GAUGE_SLUG)
        if gauge is not None:
            current = _num(_component_data(world, GAUGE_SLUG, GAUGE_COMPONENT), "value", 0.0)
            effects.append(
                ProposedEffect(
                    effect_id=new_deterministic_effect_id(
                        "alpha_contract.lab_dynamics", "gauge", base
                    ),
                    effect_type=_SET_COMPONENT,
                    source=CORE_PRODUCER,
                    target=EntityTarget(entity_id=gauge, component_type=GAUGE_COMPONENT),
                    payload={"value": round(current + 0.1, _ROUND)},
                    base_revision=base,
                )
            )

        # 2) 世界时间（state 依赖增量）：Δ = 1.0s × time_scale（当前 WorldState）。
        world_time = _num(world.world_variables, "world_time_s", 0.0)
        time_scale = _num(world.world_variables, "time_scale", 1.0)
        effects.append(
            ProposedEffect(
                effect_id=new_deterministic_effect_id(
                    "alpha_contract.lab_dynamics", "world_time", base
                ),
                effect_type=_SET_WORLD_VARIABLE,
                source=CORE_PRODUCER,
                target=StateDomainTarget(domain="world_variables"),
                payload={"key": "world_time_s", "value": round(world_time + _TICK_SECONDS * time_scale, _ROUND)},
                base_revision=base,
            )
        )

        # 3) scenario 写：stage/推进数据（contract 面：scenario 域经 grant）。
        effects.append(
            ProposedEffect(
                effect_id=new_deterministic_effect_id(
                    "alpha_contract.lab_dynamics", "scenario", base
                ),
                effect_type=_SET_SCENARIO_DATA,
                source=CORE_PRODUCER,
                target=StateDomainTarget(domain="scenario"),
                payload={
                    "scenario_id": "scenario_lab",
                    "stage": "running",
                    "data": {"ticks": int(snapshot.logical_tick)},
                },
                base_revision=base,
            )
        )
        return tuple(effects)

    @property
    def diagnostics(self) -> tuple[dict, ...]:
        return ()


def build_extension(context: "ExtensionContext") -> ExtensionBundle:
    """contract 扩展装配（trust_python=True 时由 production 装配链加载）。

    grant 面：单一受信 producer ``alpha_contract.core``（executor 显式
    ProducerGrant：组件 + world_variables；dynamics 侧由 host 从
    metadata().domains 派生：组件 + world_variables + scenario）——
    P2 首匹配语义下同维度不重叠（见模块 docstring 口径）；
    ``alpha_contract.ungranted`` 刻意零 grant。
    """
    return ExtensionBundle(
        action_executors={
            "adjust_reading": ActionsExecutor(),
            "multi_write": ActionsExecutor(),
            "set_time_scale": ActionsExecutor(),
            "set_lock": ActionsExecutor(),
            "fail_when_locked": ActionsExecutor(),
            "ungranted_write": UngrantedExecutor(),
        },
        dynamics_backends=(LabDynamics(),),
        policies={},
        producer_grants=(
            ProducerGrant(
                producer_id=str(CORE_PRODUCER),
                component_types=("gauge_reading", "attributes", "world_variables"),
                priority=50,
            ),
        ),
    )
