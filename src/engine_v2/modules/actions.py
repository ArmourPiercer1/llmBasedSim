"""P9 W4 官方模块：actions（T08；SOT §3.9；导出 5 名）。

来源 = v1 固定六动作类型（43.2-4 移除）→ v2 = **项目声明动作 + P9 标准
执行器库**；执行器 = 纯函数对象（K2：产 ProposedEffect / 状态变更提案，
kernel 应用）。

v1 移动对齐面（``MoveExecutor`` 披露面）：v1 玩家移动 =
src/game/state_apply.py:35–39（``action_type == "move"`` →
``target_position`` 直拷）；v1 NPC 移动 = state_apply.py:158–166（intent
move → ``new_positions[cid] = {x, y, z}``）；v1 规则 5 体宽预检 =
src/game/rules.py:208–222（``body_width_cm`` > 通道宽度 → blocked）=
v2 空间校验重写披露面（v2 以 ``SpaceRegistry`` 距离 / 邻接校验取代体宽
对照）；v1 固定六动作类型 43.2-4 移除（v2 项目 actions yaml 可增删 /
覆盖；``STANDARD_ACTION_IDS`` = 执行器库覆盖集，非「固定」集）。

冻结消费（SOT §3.0 导入闭集）：stdlib + core action_registry
（``ActionRegistry``:203 / ``ActionSpec``:145 / ``DurationPolicy``:102）+
core actions（``ActionProposal``:145 / ``ActionTypeId``:71）+ core effects（``ProposedEffect``:197 /
``EffectTypeId`` / ``EntityTarget``）+ core ids（``EffectId`` /
``ProducerId``）+ core provenance（``CauseRef`` / ``CauseKind``）+ core
state（``WorldState``:246）+ core space（``SpaceRegistry``:175 /
``SPACES_COMPONENT``:447 / ``decode_spaces``:492 /
``InvalidPositionError`` / ``UnknownDomainError``）+ 模块公共面
``modules.base``。本模块**不 import** ``modules.space`` /
``modules.inventory``（W6 交付 / 本波零 inventory 类型引用——声明面 =
SOT §3.1.2 表 requires =
("llmsim-standard-space", "llmsim-standard-inventory")）。

纪律（K2/K5/D6）：执行器 = 纯函数对象——``world`` 只读（零直写：
``failure`` 面 = committed 空 + 入参原样返回 = 零状态变更）；零推理消费
（零随机、零推理模型）；零模块级可变对象（registry 绑定面 = registry 侧
``specs`` 结构化记录，见 ``register_standard_actions`` docstring）；零
uuid（effect id = 确定性派生）。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, Protocol, runtime_checkable

from src.engine_v2.core.action_registry import (
    ActionRegistry,
    ActionSpec,
    DurationPolicy,
)
from src.engine_v2.core.actions import ActionProposal, ActionTypeId
from src.engine_v2.core.effects import (
    EffectTypeId,
    EntityTarget,
    ProposedEffect,
)
from src.engine_v2.core.ids import EffectId, ProducerId
from src.engine_v2.core.provenance import CauseKind, CauseRef
from src.engine_v2.core.space import (
    SPACES_COMPONENT,
    InvalidPositionError,
    SpaceRegistry,
    UnknownDomainError,
    decode_spaces,
)
from src.engine_v2.core.state import WorldState
from src.engine_v2.modules.base import OFFICIAL_MODULE_VERSION, ModuleIdentity

__all__ = [
    "STANDARD_ACTION_IDS",
    "ActionExecutor",
    "ExecutorResult",
    "MoveExecutor",
    "register_standard_actions",
]

#: 模块身份（SOT §3.1.2 MODULE_REQUIRES 表：actions 声明 requires =
#: ("llmsim-standard-space", "llmsim-standard-inventory")——移动经空间域
#: + 拾取 / 放下经物品 = 声明面；本波仅 ``MoveExecutor``（空间域），零
#: inventory 类型引用 → 两模块均零 import（deviations 披露））。
IDENTITY: Final[ModuleIdentity] = ModuleIdentity(
    "llmsim-standard-actions", OFFICIAL_MODULE_VERSION,
    ("llmsim-standard-space", "llmsim-standard-inventory"),
)

#: 标准动作 id 参考集（SOT §3.9 表行 1，逐字）——≠ v1 固定六类型：此处为
#: **执行器库**覆盖集，项目可用 actions yaml 增删 / 覆盖；43.2-4 移除的
#: 是「固定」，不是「存在」。
STANDARD_ACTION_IDS: Final[tuple[str, ...]] = (
    "move",
    "talk",
    "inspect",
    "pickup",
    "drop",
    "wait",
)

#: move 成功的拟议效果类型（名字型，词表由本模块注册、宿主侧消费）。
_MOVE_EFFECT_TYPE: Final[EffectTypeId] = EffectTypeId("space.move")

#: move 效果的产生者名字（名字型 ProducerId，决策 D-4 词法）。
_MOVE_PRODUCER: Final[ProducerId] = ProducerId("actions.move")


@runtime_checkable
class ActionExecutor(Protocol):
    """执行器协议（SOT §3.9 表行 2）：纯函数对象；``world`` 只读。

    ``execute`` 不得修改 ``world`` / ``proposal`` 入参（K2）；结果 =
    :class:`ExecutorResult`（committed 效果清单 / failure 面二选一）。
    """

    def execute(
        self,
        proposal: ActionProposal,
        world: WorldState,
        tick: int,
    ) -> ExecutorResult:
        """执行动作提案：零直写，产 committed 效果或确定性 failure。"""
        ...


@dataclass(frozen=True)
class ExecutorResult:
    """执行结果（SOT §3.9 表行 3）。

    ``failure`` 非 None ⇔ ``committed`` = ()（确定性二值面：失败零效果）。
    ``duration_ticks > 0`` = 长动作：宿主经 ``start_action``
    （core scheduler.py:468）+ ``DurationPolicy``（core
    action_registry.py:102）推进生命周期；``= 0`` = 短动作（事件驱动
    完成，无需调度条目）。
    """

    committed: tuple[ProposedEffect, ...]
    failure: str | None
    duration_ticks: int = 0


@dataclass(frozen=True)
class MoveExecutor:
    """标准移动执行器（SOT §3.9 表行 4；A14 确定性动作主面）。

    v1 移动对齐面（D1 披露）：玩家 = state_apply.py:35–39 / NPC =
    state_apply.py:158–166；v1 规则 5 体宽预检（rules.py:208–222）=
    v2 空间校验重写面（体宽对照 → ``SpaceRegistry`` 距离 / 邻接校验）；
    v1 固定六动作类型 43.2-4 移除；零推理消费（K5）。

    当前位置读取（必备解释 (b)）：``world.entities[actor].components[
    SPACES_COMPONENT]``（core space.py:447 冻结 spaces 组件面，P4 设计
    文档 §8.5 偏离 D6「P9 必须复用、不得重复注册」，core space.py:443–446
    注释同款）→ ``decode_spaces``
    （space.py:492）→ ``domain_id == self.domain`` 映射的 ``position``
    （不透明 SpacePosition，D-P4-10 backend 自校验）——与 W2
    world_positions 注册表面同惯例（域 → 坐标映射）。

    目标位置（必备解释 (c)）：``proposal.arguments["target_position"]``
    （SpacePosition = JsonValue：graph = 节点串 / grid = 恰含 x / y 两键
    的 int 坐标映射；参数 schema 不覆盖——P4 无全局位置校验器，
    ``execute`` = 权威校验面）。

    校验语义（必备解释 (d)，确定性检查序，失败面零异常）：

    1. actor 不在世界 → failure；
    2. actor 无 spaces 组件 → failure（退化面）；
    3. spaces 载荷畸形（``decode_spaces`` 抛 ValueError 族）→ failure；
    4. actor 无 ``self.domain`` 域映射 → failure（退化面）；
    5. 缺 ``target_position`` 参数 → failure；
    6. 域未在 registry 注册 → failure（运行期复查面）；
    7. 当前位置 backend 非法（``validate_position`` 抛
       ``InvalidPositionError``）→ failure；
    8. 目标位置 ∉ ``backend.positions()`` → 越界 failure；
    9. 目标位置 ∉ ``backend.neighbors(当前位置)`` → 不可达 failure
       （邻接语义 = neighbors 集合成员判定，core space.py:160——graph =
       边邻接 / grid = 4 邻，与 distance==1 同面）。

    成功面（必备解释 (e)）：``committed`` = 恰 1 条 ProposedEffect
    （``space.move`` 位置更新；payload = {"domain", "position"}；
    ``effect_id`` = ``eff_move_<actor>_<tick>`` 确定性派生；
    ``base_revision`` = ``world.world_revision``；``cause_ids`` = 本
    proposal 的 PROPOSAL 因果引用（K6）），``failure`` = None，
    ``duration_ticks`` = 0。失败面：``committed`` = ()、``failure`` =
    确定性 message。``world`` 只读（K2 零直写）。
    """

    space: SpaceRegistry
    domain: str

    def execute(
        self,
        proposal: ActionProposal,
        world: WorldState,
        tick: int,
    ) -> ExecutorResult:
        """执行 move 提案（实现 ``ActionExecutor`` 协议；世界只读）。"""
        actor = proposal.actor_id
        record = world.entities.get(actor)
        if record is None:
            return ExecutorResult(
                (), f"move 执行失败：实体 {str(actor)!r} 不存在于世界", 0,
            )
        payload = record.components.get(SPACES_COMPONENT)
        if payload is None:
            return ExecutorResult(
                (), f"move 执行失败：实体 {str(actor)!r} 无 spaces 组件", 0,
            )
        try:
            mappings = decode_spaces(payload)
        except ValueError:
            return ExecutorResult(
                (), f"move 执行失败：实体 {str(actor)!r} spaces 载荷畸形", 0,
            )
        current = next(
            (m.position for m in mappings if m.domain_id == self.domain),
            None,
        )
        if current is None:
            return ExecutorResult(
                (),
                f"move 执行失败：实体 {str(actor)!r} 无 {self.domain!r} "
                f"域位置映射",
                0,
            )
        target = proposal.arguments.get("target_position")
        if target is None:
            return ExecutorResult(
                (), "move 执行失败：缺失 target_position 参数", 0,
            )
        try:
            backend = self.space.backend(self.domain)
        except UnknownDomainError:
            return ExecutorResult(
                (), f"move 执行失败：域 {self.domain!r} 未注册", 0,
            )
        try:
            backend.validate_position(current)
        except InvalidPositionError:
            return ExecutorResult(
                (),
                f"move 执行失败：当前位置非法 {current!r}"
                f"（域 {self.domain!r}）",
                0,
            )
        if target not in backend.positions():
            return ExecutorResult(
                (),
                f"move 执行失败：目标位置越界 {target!r}"
                f"（域 {self.domain!r}）",
                0,
            )
        try:
            neighbors = backend.neighbors(current)
        except InvalidPositionError:
            # 防御性兜底（current 已校验，理论上不可达；确定性不静默）。
            return ExecutorResult(
                (),
                f"move 执行失败：当前位置非法 {current!r}"
                f"（域 {self.domain!r}）",
                0,
            )
        if target not in neighbors:
            return ExecutorResult(
                (),
                f"move 执行失败：目标位置不可达 {target!r}"
                f"（当前 {current!r} 非邻接）",
                0,
            )
        effect = ProposedEffect(
            effect_id=EffectId(f"eff_move_{str(actor)}_{tick}"),
            effect_type=_MOVE_EFFECT_TYPE,
            source=_MOVE_PRODUCER,
            target=EntityTarget(
                entity_id=actor, component_type=SPACES_COMPONENT,
            ),
            payload={"domain": self.domain, "position": target},
            base_revision=world.world_revision,
            cause_ids=[
                CauseRef(
                    kind=CauseKind.PROPOSAL,
                    ref_id=str(proposal.proposal_id),
                ),
            ],
        )
        return ExecutorResult((effect,), None, 0)


def register_standard_actions(
    registry: ActionRegistry,
    space: SpaceRegistry,
    executors: Mapping[str, ActionExecutor],
) -> None:
    """把标准动作 ``ActionSpec`` + 执行器挂入注册表（SOT §3.9 表行 5）。

    **幂等**：重复注册同 id 覆盖（``registry.specs`` dict 语义，
    ``ActionRegistry`` frozen 模型字段级再赋值被阻断，原地 dict 更新为
    唯一落位）并记结构化诊断（registry 侧 ``spec.tags``——零模块级可变
    对象，D6；零 print）：

    - ``tags[0]`` = ``"p9-standard-actions"``（标记：本函数注册）；
    - ``tags[1]`` = ``"p9.register-count.<n>"``（n = 该 action id 累计
      注册次数，自上一次 ``spec.tags`` 推导——零状态：第二次注册 →
      n = 2，诊断可观察面）；
    - action id 缺席 ``executors`` 映射 → ``tags`` 追加
      ``"p9.executor-missing"``（缺失 → 诊断，不静默——SOT §3.9 表注；
      宿主经该标记核对执行器面）。

    ActionSpec 字段方案（必备解释 delegated 面）：

    - ``action_id`` = ``ActionTypeId(<action id>)``（逐字，键一致性 =
      ``ActionRegistry`` model_validator 天然保证）；
    - ``executor`` = ``"llmsim-standard-actions.<action id>"``（名字型；
      非 ProducerId 取值——其词法（core ids.py:77）不含连字符；
      ActionSpec.executor = free-form str（core action_registry.py:164）
      零词法校验——注册表侧执行器名字；执行器**对象**绑定 =
      宿主按 action id 查 ``executors`` 映射——ActionSpec 是 JSON 数据
      契约（extra=forbid）零对象字段，SOT §3.9 表注「执行器与 yaml 的
      绑定 = 宿主按 action id 查 executors」）；
    - ``parameters`` = {}（标准动作参数面 = 开放 ``arguments``；move
      目标位置 = SpacePosition JsonValue，P4 D-P4-10 无全局位置校验器，
      ``execute`` = 权威校验面）；
    - ``duration_policy`` = ``DurationPolicy(kind="none")``（事件驱动；
      长动作面 = ``ExecutorResult.duration_ticks``，宿主经
      ``start_action``（core scheduler.py:468）推进）；
    - ``interruptible`` = True（缺省）；``completion_trigger`` = None。

    ``space`` = ``MoveExecutor`` 构造参考面（宿主以同一 registry 构造
    ``MoveExecutor(space, domain)`` 并经 ``executors`` 传入；本函数签名
    无 domain 参数，不构造执行器对象——本波仅 ``MoveExecutor``，
    talk / inspect / pickup / drop / wait 执行器对象 = 后续波）。
    """
    for action_id in STANDARD_ACTION_IDS:
        typed_id = ActionTypeId(action_id)
        previous = registry.specs.get(typed_id)
        count = 1
        if previous is not None and "p9-standard-actions" in previous.tags:
            for tag in previous.tags:
                if tag.startswith("p9.register-count."):
                    count = int(tag.removeprefix("p9.register-count.")) + 1
        tags = ["p9-standard-actions", f"p9.register-count.{count}"]
        if action_id not in executors:
            tags.append("p9.executor-missing")
        registry.specs[typed_id] = ActionSpec(
            action_id=typed_id,
            executor=f"llmsim-standard-actions.{action_id}",
            parameters={},
            duration_policy=DurationPolicy(kind="none"),
            interruptible=True,
            completion_trigger=None,
            tags=tags,
        )
