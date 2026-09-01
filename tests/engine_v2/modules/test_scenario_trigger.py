"""W4 测试钉面：scenario（T07；SOT §3.8；测试表 §6.1 行 1–4）。

钉面清单（SOT §3.8 表行 1–3，任务书 §1.1）：
- ``ScenarioTrigger`` / ``TriggerFiring`` frozen dataclass 字段面（firing
  = 至多一效果或一提案，互斥恰一非 None）；
- ``check_triggers`` 纯函数：评估序 = firing 序 = (priority 降, id 升)；
  仅 ALLOWED 触发；``once`` 语义（fired_once 命中 → 跳过，once=False 不
  受其约束）；parse 失败 / 语义错误 / uncertain → 确定性跳过、零异常（P5 永不抛
  口径，rule_module.py:1169）；零入参修改（K2）；零 rng 消费（K5）。

零 fixture：全部输入本地字面量构造；``_NoRng`` 钉零随机（任何随机调用
= AssertionError）。确定性：零 uuid（firing id 确定性派生，测试钉死）。
"""

from __future__ import annotations

from src.engine_v2.core.actions import ActionTiming, ActionTypeId
from src.engine_v2.core.effects import (
    EffectTypeId,
    StateDomainId,
    StateDomainTarget,
)
from src.engine_v2.core.ids import (
    ActionInstanceId,
    EffectId,
    EntityId,
    ProducerId,
)
from src.engine_v2.core.provenance import OriginKind
from src.engine_v2.core.revision import Revision
from src.engine_v2.modules.scenario import (
    ScenarioTrigger,
    TriggerFiring,
    check_triggers,
)

#: 钉死条件（P5 文法：if 必含 else 输出）：gold >= 100 → allowed，否则
#: blocked（确定性二值，零 roll）。
_COND = "if(gold >= 100, allowed; blocked)"


class _NoRng:
    """确定性零消费 rng：任何随机调用 = AssertionError（K5 钉面）。"""

    def rand(self) -> float:
        raise AssertionError("_NoRng.rand 不得被调用")

    def uniform(self, lo: float, hi: float) -> float:
        raise AssertionError("_NoRng.uniform 不得被调用")

    def randint(self, lo: int, hi: int) -> int:
        raise AssertionError("_NoRng.randint 不得被调用")


def test_scenario_trigger_t1_fires() -> None:
    """t1：条件真 → firing（动作 / 效果双面字段钉 + K2 零入参修改）。"""
    trig_a = ScenarioTrigger(
        id="trig_a",
        condition_dsl=_COND,
        action_type=ActionTypeId("move"),
        effect_description="攻城",
    )
    trig_b = ScenarioTrigger(
        id="trig_b",
        condition_dsl=_COND,
        action_type=None,
        effect_description="门虚掩着",
    )
    facts: dict[str, object] = {"gold": 150}
    result = check_triggers(
        (trig_a, trig_b), frozenset(), facts, 12, _NoRng(),
    )
    assert isinstance(result, tuple) and len(result) == 2
    f_a, f_b = result
    # ── 动作面（trig_a：action_type 非 None → ActionProposal）──
    assert isinstance(f_a, TriggerFiring)
    assert f_a.trigger_id == "trig_a" and f_a.tick == 12
    assert f_a.proposed is None and f_a.action_proposal is not None
    p = f_a.action_proposal
    assert type(p.proposal_id) is ActionInstanceId
    assert p.proposal_id == "act_scenario_trig_a_12"
    assert type(p.actor_id) is EntityId
    assert p.actor_id == "ent_scenario_trig_a"
    assert type(p.action_id) is ActionTypeId
    assert p.action_id == "move"
    assert p.arguments == {}
    assert p.intent == "攻城"
    assert p.timing == ActionTiming()
    assert p.confidence is None
    assert p.fallback_action is None
    assert p.base_world_revision == Revision(0)
    assert p.observation_id is None
    assert p.actor_state_revision is None
    assert p.valid_until is None
    assert type(p.provenance.producer_id) is ProducerId
    assert p.provenance.producer_id == "scenario.trigger"
    assert p.provenance.origin is OriginKind.SCENARIO
    assert p.provenance.source_record_id is None
    assert p.provenance.notes is None
    # ── 效果面（trig_b：action_type = None → ProposedEffect）──
    assert isinstance(f_b, TriggerFiring)
    assert f_b.trigger_id == "trig_b" and f_b.tick == 12
    assert f_b.action_proposal is None and f_b.proposed is not None
    e = f_b.proposed
    assert type(e.effect_id) is EffectId
    assert e.effect_id == "eff_scenario_trig_b_12"
    assert type(e.effect_type) is EffectTypeId
    assert e.effect_type == "scenario.trigger"
    assert type(e.source) is ProducerId
    assert e.source == "scenario.trigger"
    assert type(e.target) is StateDomainTarget
    assert e.target.kind == "state_domain"
    assert type(e.target.domain) is StateDomainId
    assert e.target.domain == "scenario_state"
    assert e.payload == {
        "trigger_id": "trig_b",
        "description": "门虚掩着",
    }
    assert e.base_revision == Revision(0)
    assert e.cause_ids == []
    assert e.authority_scope is None
    assert e.priority_hint is None
    assert e.metadata == {}
    # ── K2：零入参修改 ──
    assert facts == {"gold": 150}
    assert (trig_a.id, trig_a.condition_dsl, trig_a.once, trig_a.priority) == \
        ("trig_a", _COND, True, 0)
    assert (trig_b.action_type, trig_b.effect_description) == \
        (None, "门虚掩着")


def test_scenario_trigger_t2_not_fires() -> None:
    """t2：条件假 / parse 失败 / 语义错误 / uncertain → 零 firing（零异常、
    零 rng 消费）。"""
    trig = ScenarioTrigger(
        id="trig_a",
        condition_dsl=_COND,
        action_type=ActionTypeId("move"),
        effect_description="攻城",
    )
    # 条件假（gold = 50 < 100 → blocked）：
    assert check_triggers(
        (trig,), frozenset(), {"gold": 50}, 5, _NoRng(),
    ) == ()
    # parse 失败（缺 else 输出；gold = 150 本可触发 → 钉跳过而非误触发）：
    broken = ScenarioTrigger(
        id="trig_b",
        condition_dsl="if(gold >= 100, allowed)",
        action_type=None,
        effect_description="门虚掩着",
    )
    assert check_triggers(
        (broken,), frozenset(), {"gold": 150}, 6, _NoRng(),
    ) == ()
    # 语义错误（parse 成功、求值期未知变量 → DslEvalError；P5 永不抛：
    # 确定性跳过、零异常）：
    semantic = ScenarioTrigger(
        id="trig_c",
        condition_dsl="if(no_such_var >= 1, allowed; blocked)",
        action_type=None,
        effect_description="未知变量",
    )
    assert check_triggers(
        (semantic,), frozenset(), {"gold": 150}, 7, _NoRng(),
    ) == ()
    # uncertain（需掷骰；确定性检查面零消费 → 不 firing，_NoRng 钉零随机
    # 消费）：
    uncertain = ScenarioTrigger(
        id="trig_d",
        condition_dsl="if(gold >= 100, uncertain:0.5; blocked)",
        action_type=None,
        effect_description="需掷骰",
    )
    assert check_triggers(
        (uncertain,), frozenset(), {"gold": 150}, 8, _NoRng(),
    ) == ()


def test_scenario_trigger_t3_once_semantics() -> None:
    """t3：``once`` 语义——fired_once 命中跳过；``once=False`` 不受约束。"""

    def _one(once: bool) -> ScenarioTrigger:
        return ScenarioTrigger(
            id="trig_a",
            condition_dsl=_COND,
            action_type=None,
            effect_description="门虚掩着",
            once=once,
        )

    fired = frozenset({"trig_a"})
    # once=True 且 id 已入 fired_once（上一 tick 已 firing）→ 跳过：
    assert check_triggers(
        (_one(True),), fired, {"gold": 150}, 20, _NoRng(),
    ) == ()
    # once=False → 不受 fired_once 约束 → firing：
    result = check_triggers(
        (_one(False),), fired, {"gold": 150}, 21, _NoRng(),
    )
    assert len(result) == 1 and result[0].trigger_id == "trig_a"
    assert result[0].proposed is not None
    assert result[0].proposed.effect_id == "eff_scenario_trig_a_21"
    # once=True 但未命中 → firing：
    result = check_triggers(
        (_one(True),), frozenset(), {"gold": 150}, 22, _NoRng(),
    )
    assert len(result) == 1
    assert result[0].proposed is not None
    assert result[0].proposed.effect_id == "eff_scenario_trig_a_22"


def test_scenario_trigger_t4_priority_order() -> None:
    """t4：多触发器 (priority 降, id 升) 确定性序（评估序 = firing 序）。"""

    def _effect_trigger(tid: str, priority: int) -> ScenarioTrigger:
        return ScenarioTrigger(
            id=tid,
            condition_dsl=_COND,
            action_type=None,
            effect_description=f"desc-{tid}",
            priority=priority,
        )

    trig_a = _effect_trigger("trig_a", 1)
    trig_b = _effect_trigger("trig_b", 1)
    trig_c = _effect_trigger("trig_c", 5)
    trig_d = _effect_trigger("trig_d", 0)
    facts: dict[str, object] = {"gold": 200}
    # 乱序输入 1：
    result = check_triggers(
        (trig_b, trig_d, trig_a, trig_c), frozenset(), facts, 30, _NoRng(),
    )
    assert tuple(f.trigger_id for f in result) == (
        "trig_c", "trig_a", "trig_b", "trig_d",
    )
    # 乱序输入 2：输出序不变（确定性 = 输入序无关）：
    result = check_triggers(
        (trig_d, trig_c, trig_b, trig_a), frozenset(), facts, 31, _NoRng(),
    )
    assert tuple(f.trigger_id for f in result) == (
        "trig_c", "trig_a", "trig_b", "trig_d",
    )
    # 确定性 id 钉（firing 序第 1 位 = priority 最高的 trig_c）：
    assert result[0].proposed is not None
    assert result[0].proposed.effect_id == "eff_scenario_trig_c_31"
