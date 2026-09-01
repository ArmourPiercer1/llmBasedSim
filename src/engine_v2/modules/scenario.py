"""P9 W4 官方模块：scenario（T07；SOT §3.8；导出 3 名）。

来源 = v1 无对应物（v2 新模块，Spec §40）；触发器条件 = P5 冻结 DSL
（43.1-3 思想的 v2 归宿）；v1 `post_narrative_update`
（src/graph/game_graph.py:842，确定性无推理后处理节点）的后处理职责由
本模块 + kernel lifecycle 承接（本模块只产 firing 清单，lifecycle 推进
归 kernel）。

冻结消费（SOT §3.0 导入闭集）：stdlib + core actions（``ActionTypeId``:71 /
``ActionProposal``:145）+ core effects（``ProposedEffect``:197 /
``EffectTypeId`` / ``StateDomainTarget`` / ``StateDomainId``）+ core ids
（确定性 id 族）+ core revision（``Revision``）+ core provenance
（``Provenance`` / ``OriginKind``）+ P5 content rule_module（``DslRng``:149 /
``DslContext``:441 / ``parse_dsl``:812 / ``evaluate_condition``:903 /
``DslEvalError`` / ``Feasibility``）+ 模块公共面 ``modules.base``。本模块
**不 import** ``modules.actions``（W4 同波模块；类型面经 core actions /
effects 消费，类型引用不需要则零 import——声明面 = SOT §3.1.2 表
requires = ("llmsim-standard-actions",)）。

纪律（K2/K5/D6）：``check_triggers`` = 纯函数——零入参修改、零异常（parse
失败 / 语义错误均确定性跳过，对齐 P5 ``check_action_feasibility``「永不抛」
口径，rule_module.py:1169）；零推理消费（零随机、零推理模型）；零模块级
可变对象；零 uuid（firing id = 确定性派生）。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from src.engine_v2.content.rule_module import (
    DslContext,
    DslEvalError,
    DslRng,
    Feasibility,
    evaluate_condition,
    parse_dsl,
)
from src.engine_v2.core.actions import (
    ActionProposal,
    ActionTiming,
    ActionTypeId,
)
from src.engine_v2.core.effects import (
    EffectTypeId,
    ProposedEffect,
    StateDomainId,
    StateDomainTarget,
)
from src.engine_v2.core.ids import (
    ActionInstanceId,
    EffectId,
    EntityId,
    ProducerId,
)
from src.engine_v2.core.provenance import OriginKind, Provenance
from src.engine_v2.core.revision import Revision
from src.engine_v2.modules.base import OFFICIAL_MODULE_VERSION, ModuleIdentity

__all__ = [
    "ScenarioTrigger",
    "TriggerFiring",
    "check_triggers",
]

#: 模块身份（SOT §3.1.2 MODULE_REQUIRES 表：scenario 声明
#: requires = ("llmsim-standard-actions",)——触发器 firing 产动作提案 /
#: 效果 = 语义依赖；类型面经 core actions / effects 消费，本模块不 import
#: ``modules.actions``（W4 同波模块，类型引用不需要则零 import））。
IDENTITY: Final[ModuleIdentity] = ModuleIdentity(
    "llmsim-standard-scenario", OFFICIAL_MODULE_VERSION,
    ("llmsim-standard-actions",),
)

#: 效果分支的 state domain 目标（kernel 只给信封、语义归 P9 的
#: ``WorldState.scenario_state`` 面，core state.py:246 docstring 面）。
_SCENARIO_STATE_DOMAIN: Final[StateDomainId] = StateDomainId("scenario_state")

#: firing 产生者名字（名字型 ProducerId，决策 D-4 词法；firing 面统一）。
_FIRING_PRODUCER: Final[ProducerId] = ProducerId("scenario.trigger")

#: 效果分支的 effect 类型（名字型，词表由本模块注册、宿主侧消费）。
_TRIGGER_EFFECT_TYPE: Final[EffectTypeId] = EffectTypeId("scenario.trigger")

#: 无世界输入的确定性 base revision 常量（签名面无 WorldState；K2 语义：
#: firing 待 kernel 裁决，提交时由 kernel 以裁决时世界 revision 再定，
#: 见 check_triggers docstring）。
_BASE_REVISION: Final[Revision] = Revision(0)


@dataclass(frozen=True)
class ScenarioTrigger:
    """场景触发器声明（SOT §3.8 表行 1）。

    宿主从 ScenarioSpec 扩展区 / 项目 modules 声明构建。``condition_dsl``
    = P5 冻结 DSL 条件串（``parse_dsl`` 文法，rule_module.py:812——必含
    else 输出）；``action_type`` 非 None → firing 产动作提案；None →
    firing 产拟议效果（一次 firing 至多一效果或一提案，K2 均待 kernel
    裁决）；``once=True`` 且 id 已入 fired_once → 跳过；``priority``
    参与 firing 序（priority 降, id 升）。
    """

    id: str
    condition_dsl: str
    action_type: ActionTypeId | None
    effect_description: str
    once: bool = True
    priority: int = 0


@dataclass(frozen=True)
class TriggerFiring:
    """一次触发 firing（SOT §3.8 表行 2）。

    一次 firing = **至多一效果或一提案**（K2：均待 kernel 裁决；本模块
    构造面保证恰一非 None——``proposed`` 与 ``action_proposal`` 互斥）。
    ``tick`` = ``check_triggers`` 的 tick 入参（firing 时刻）。
    """

    trigger_id: str
    tick: int
    proposed: ProposedEffect | None
    action_proposal: ActionProposal | None


def _firing_proposal(trigger: ScenarioTrigger, tick: int) -> ActionProposal:
    """action_type 非 None 分支的确定性 ActionProposal 构造（零 uuid）。

    必填字段确定性方案（任务书 §1.1 必备解释 (b) delegated 面）：

    - ``proposal_id`` = ``act_scenario_<trigger.id>_<tick>``（同 tick 同
      trigger 确定性恒等；跨 tick 天然唯一）；
    - ``actor_id`` = ``ent_scenario_<trigger.id>``（签名面无世界 / actor
      输入——场景级确定性占位 actor，宿主可于 kernel 裁决期重映射）；
    - ``base_world_revision`` = ``Revision(0)``（签名面无 WorldState；
      提交时 kernel 以裁决时世界 revision 再定，K2）；
    - ``provenance`` = producer ``scenario.trigger`` + origin
      ``OriginKind.SCENARIO``（K6 来源钉死）。
    """
    return ActionProposal(
        proposal_id=ActionInstanceId(f"act_scenario_{trigger.id}_{tick}"),
        actor_id=EntityId(f"ent_scenario_{trigger.id}"),
        action_id=trigger.action_type,
        arguments={},
        intent=trigger.effect_description,
        timing=ActionTiming(),
        confidence=None,
        fallback_action=None,
        base_world_revision=_BASE_REVISION,
        observation_id=None,
        actor_state_revision=None,
        valid_until=None,
        provenance=Provenance(
            producer_id=_FIRING_PRODUCER, origin=OriginKind.SCENARIO,
        ),
    )


def _firing_effect(trigger: ScenarioTrigger, tick: int) -> ProposedEffect:
    """action_type = None 分支的确定性 ProposedEffect 构造（零 uuid）。

    必填字段确定性方案（任务书 §1.1 必备解释 (b) delegated 面）：

    - ``effect_id`` = ``eff_scenario_<trigger.id>_<tick>``（确定性恒等 /
      跨 tick 唯一）；
    - ``target`` = ``StateDomainTarget(domain="scenario_state")``——
      kernel 只给信封、语义归 P9 的 scenario 状态面（core state.py:246
      docstring）；
    - ``payload`` = ``{"trigger_id", "description"}``——``effect_description``
      的承载位（delegated 面，测试钉）；
    - ``base_revision`` = ``Revision(0)``（同 ``_BASE_REVISION`` 口径）。
    """
    return ProposedEffect(
        effect_id=EffectId(f"eff_scenario_{trigger.id}_{tick}"),
        effect_type=_TRIGGER_EFFECT_TYPE,
        source=_FIRING_PRODUCER,
        target=StateDomainTarget(domain=_SCENARIO_STATE_DOMAIN),
        payload={
            "trigger_id": trigger.id,
            "description": trigger.effect_description,
        },
        base_revision=_BASE_REVISION,
        cause_ids=[],
    )


def check_triggers(
    triggers: Sequence[ScenarioTrigger],
    fired_once: frozenset[str],
    world_facts: Mapping[str, object],
    tick: int,
    rng: DslRng,
) -> tuple[TriggerFiring, ...]:
    """触发器检查（SOT §3.8 表行 3）：纯函数，零异常，确定性 firing 清单。

    逐触发器（**评估序 = firing 序** = (priority 降, id 升) 确定性——评估
    可能消费 rng，故评估序即 rng 消费序，firing 元组按此序返回）：

    1. ``once=True`` 且 ``trigger.id in fired_once`` → 跳过（once 语义）；
    2. ``parse_dsl(condition_dsl, trigger.id)``（rule_module.py:812，永不
       抛）——``ast is None``（parse 失败）→ 确定性跳过：零 firing 零异常
       （对齐 P5 ``check_action_feasibility``「永不抛」口径，
       rule_module.py:1169——parse / 语义错误同族跳过）；
    3. ``evaluate_condition(ast, context, rng)``（rule_module.py:903，
       注入 rng）——抛 ``DslEvalError``（语义错误：未知变量 / 除零 /
       类型错误）→ 同族确定性跳过；
    4. 条件真 = 结果 ``feasibility is Feasibility.ALLOWED`` → firing；
       假（BLOCKED / UNCERTAIN）→ 无 firing（UNCERTAIN = 概率性结果需
       roll，确定性触发检查不做 roll——最小改动读法，deviations 披露）；
    5. firing 构造分工（必备解释 (b)）：``action_type`` 非 None →
       ``action_proposal`` 非 None、``proposed`` = None；None →
       ``proposed`` 非 None、``action_proposal`` = None（恰一非 None）。

    ``world_facts`` → ``DslContext``（必备解释 (a)）：全部事实入
    ``variables`` 映射（``DslContext(variables=dict(world_facts))``）——
    DSL 自由名直接索引世界事实（``player.*`` / ``target.*`` 前缀名不经
    本映射）；新 dict 构造，零入参别名（K2）。``fired_once`` /
    ``triggers`` / ``world_facts`` 零修改。
    """
    context = DslContext(variables=dict(world_facts))
    firings: list[TriggerFiring] = []
    ordered = sorted(triggers, key=lambda t: (-t.priority, t.id))
    for trigger in ordered:
        if trigger.once and trigger.id in fired_once:
            continue
        parsed = parse_dsl(trigger.condition_dsl, trigger.id)
        if parsed.ast is None:
            continue
        try:
            outcome = evaluate_condition(parsed.ast, context, rng)
        except DslEvalError:
            continue
        if outcome.feasibility is not Feasibility.ALLOWED:
            continue
        if trigger.action_type is not None:
            firings.append(
                TriggerFiring(
                    trigger_id=trigger.id,
                    tick=tick,
                    proposed=None,
                    action_proposal=_firing_proposal(trigger, tick),
                ),
            )
        else:
            firings.append(
                TriggerFiring(
                    trigger_id=trigger.id,
                    tick=tick,
                    proposed=_firing_effect(trigger, tick),
                    action_proposal=None,
                ),
            )
    return tuple(firings)
