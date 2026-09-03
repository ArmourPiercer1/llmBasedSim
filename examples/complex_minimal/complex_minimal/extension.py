"""complex_minimal 游戏 Python 扩展（runtime closure T10；contract §3 冻结形状）。

锅炉房值守最小闭环（只写游戏侧，引擎侧 = ``src.engine_v2``）：

- 1 个 custom :class:`BoilerMachineExecutor`：处理锅炉房三动作
  ``inject_heat`` / ``cool`` / ``toggle_machine``（按 ``proposal.action_id``
  分派）；
- 1 个数值 :class:`BoilerThermalBackend`：锅炉房温度离散积分
  （热源由 ``machine.power`` 驱动）；
- 1 个 :class:`ProducerGrant`（executor 侧，machine 独占写权）；dynamics
  侧 grant 由 host（T9 assembly）从 ``metadata().domains``（temperature）
  自动派生——P2 首条匹配拍板语义下的单写权拆分（每组件恰一 writer）。

纪律：

- K2 零直写 world：一切世界写入只以返回 :class:`ProposedEffect`
  （``core.set_component``）形式出现；``payload`` = 完整组件数据 dict
  （与 ``state_set_component`` handler 一致：整体替换、无部分合并）；
- K7 零随机、零墙钟、零 I/O；``effect_id`` 一律经
  ``new_deterministic_effect_id`` 确定性派生；
- 参数越界 / 实体缺失 → 确定性 ``failure``（零效果、零异常）；
- dynamics 的 ``stimuli`` 接受但不消费（最小闭环 = 纯状态函数；
  事件刺激面留 follow-up）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from src.engine_v2.core.components import ComponentTypeId
from src.engine_v2.core.effects import EffectTypeId, EntityTarget, ProposedEffect
from src.engine_v2.core.ids import EntityId, ProducerId
from src.engine_v2.core.provenance import CauseKind, CauseRef
from src.engine_v2.core.revision import Revision
from src.engine_v2.dynamics.backend import BackendMetadata, new_deterministic_effect_id
from src.engine_v2.modules.actions import ExecutorResult
from src.engine_v2.runtime.extensions import ExtensionBundle, ProducerGrant

if TYPE_CHECKING:  # 类型引用面（contract §3：ExtensionContext = project_root + ir）
    from src.engine_v2.core.actions import ActionProposal
    from src.engine_v2.core.state import WorldState
    from src.engine_v2.dynamics.backend import (
        DynamicsContext,
        Stimulus,
        WorldSnapshot,
    )
    from src.engine_v2.runtime.extensions import ExtensionContext

__all__ = [
    "BOILER_SLUG",
    "MAX_POWER",
    "ROOM_SLUG",
    "BoilerMachineExecutor",
    "BoilerThermalBackend",
    "build_extension",
]

# —— 组件 / 实体身份（对应 game.yaml component_schemas 声明）——

#: machine 组件类型 id（machine {power}）。
MACHINE_COMPONENT: Final[ComponentTypeId] = ComponentTypeId("machine")
#: temperature 组件类型 id（temperature {celsius}；挂地点实体，见 assumption）。
TEMPERATURE_COMPONENT: Final[ComponentTypeId] = ComponentTypeId("temperature")

#: 锅炉（机器）实体 authoring slug（= items/boiler.yaml 的 id）。
BOILER_SLUG: Final[str] = "boiler"
#: 锅炉房（地点）实体 authoring slug（= world 节 location id）。
ROOM_SLUG: Final[str] = "boiler_room"

# —— producer 身份（词法 = core/ids.py PRODUCER_ID_PATTERN）——

#: 动作执行器 producer 名。
EXECUTOR_PRODUCER_ID: Final[ProducerId] = ProducerId("complex_minimal.actions")
#: 数值动力学 producer 名。
DYNAMICS_PRODUCER_ID: Final[ProducerId] = ProducerId("complex_minimal.dynamics")

#: 本扩展消费的唯一结构 effect 类型。
_SET_COMPONENT: Final[EffectTypeId] = EffectTypeId("core.set_component")

# —— 机器功率边界（executor 权威校验面）——

#: 功率上限（超过 = 参数越界 failure）。
MAX_POWER: Final[int] = 4
#: 停机功率（toggle 的目标之一）。
OFF_POWER: Final[int] = 0
#: 默认功率（toggle 自停机恢复的目标）。
DEFAULT_POWER: Final[int] = 2

# —— 温度缺省值 ——

#: 温度组件缺位时的缺省值（= game.yaml schema default）。
DEFAULT_CELSIUS: Final[float] = 20.0

# —— 热动力学参数（确定性离散积分）——

#: 环境热源（摄氏度：机器停机时房间平衡温度）。
AMBIENT_HEAT_SOURCE_CELSIUS: Final[float] = 12.0
#: 每档功率的热源增量（摄氏度）。
POWER_HEAT_RATE_CELSIUS: Final[float] = 14.0
#: 温度趋近系数 k（每单位时间）。
THERMAL_COEFFICIENT: Final[float] = 0.2

#: 结果舍入精度（确定性）。
_ROUND_DIGITS: Final[int] = 6
#: 「无变化」判定 epsilon。
_EPSILON: Final[float] = 1e-9


# —— 私有 helper（零 I/O、零随机、确定性）——


def _resolve_entity_id(
    world: "WorldState", slug: str, component_type: ComponentTypeId
) -> "EntityId | None":
    """authoring slug → 实体 id。

    首选 = core ids.py 内容侧确定性命名约定 ``ent_authoring_<slug>``；
    规范 id 缺席时退化为**第一个**携带目标组件的实体（按 sorted id 序，
    确定性退化面，不依赖 materialize 细节）；两者皆无 → None。
    """
    canonical = EntityId(f"ent_authoring_{slug}")
    if world.has_entity(canonical):
        return canonical
    for entity_id in sorted(world.entities, key=str):
        if component_type in world.entities[entity_id].components:
            return entity_id
    return None


def _read_component(
    world: "WorldState", entity_id: "EntityId", component_type: ComponentTypeId
) -> dict:
    """读组件数据快照（只读；缺失 → 空 dict）。"""
    data = world.entities[entity_id].components.get(component_type)
    return dict(data) if data is not None else {}


def _valid_number(value: object) -> bool:
    """JSON number 判定（bool 显式拒绝）。"""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


# —— 动作执行器（K2 纯函数对象：world 只读）——


class BoilerMachineExecutor:
    """锅炉房三动作纯函数执行器（实现 ``modules.actions.ActionExecutor`` 协议）。

    绑定方式（记录）：**单个执行器实例注册在全部 3 个 action id 下**
    （contract §3 ``ExtensionBundle.action_executors`` = action id → executor
    映射面），内部按 ``proposal.action_id`` 分派。

    语义（全部确定性；成功面 = 恰 1 条 ``core.set_component`` 效果，
    ``duration_ticks = 0`` 短动作）：

    - ``inject_heat``：power += 1；结果 > MAX_POWER → 参数越界 failure；
    - ``cool``：power -= 1；结果 < OFF_POWER → 参数越界 failure（F2 修复
      窗：冷却改走 machine 侧单写权——temperature 归 dynamics 独占，
      P2 首条匹配拍板下一组件仅一个有效 writer）；
    - ``toggle_machine``：开机 → power 置 OFF_POWER；停机 → 置 DEFAULT_POWER。

    machine 组件缺位（F1 修复窗：P5 作者面无组件挂载面、materialize 不产
    machine）→ 首个动作自举：power 取 schema 缺省（DEFAULT_POWER = 2，与
    game.yaml component_schemas default 一致），由效果经管道落位（与
    dynamics 温度自举同款）。
    """

    def execute(
        self, proposal: "ActionProposal", world: "WorldState", tick: int
    ) -> ExecutorResult:
        """执行动作提案（协议签名；tick 仅参与签名面，分派按 action_id）。"""
        del tick  # 最小闭环：effect 身份由 proposal_id 派生（见 _set_component）
        action_id = str(proposal.action_id)
        if action_id == "inject_heat":
            return self._inject_heat(proposal, world)
        if action_id == "cool":
            return self._cool(proposal, world)
        if action_id == "toggle_machine":
            return self._toggle_machine(proposal, world)
        return ExecutorResult((), f"锅炉执行器不处理动作 {action_id!r}", 0)

    # —— 内部面 ——

    def _machine_state(
        self, world: "WorldState"
    ) -> "tuple[EntityId | None, int | None, str | None]":
        """(锅炉实体 id, 当前功率, 失败面)；成功时 error = None。

        F1：machine 组件缺位 → power 取 schema 缺省 DEFAULT_POWER（自举
        口径，见类 docstring）；组件在场但 power 非法（非 int / bool）→
        显式 failure（不猜）。
        """
        entity_id = _resolve_entity_id(world, BOILER_SLUG, MACHINE_COMPONENT)
        if entity_id is None:
            return None, None, "锅炉房缺少锅炉实体（machine 组件）"
        power = _read_component(world, entity_id, MACHINE_COMPONENT).get("power")
        if power is None:
            return entity_id, DEFAULT_POWER, None
        if not isinstance(power, int) or isinstance(power, bool):
            return entity_id, None, f"machine 组件 power 字段非法：{power!r}"
        return entity_id, power, None

    def _inject_heat(self, proposal: "ActionProposal", world: "WorldState") -> ExecutorResult:
        entity_id, power, error = self._machine_state(world)
        if error is not None:
            return ExecutorResult((), error, 0)
        new_power = power + 1
        if new_power > MAX_POWER:
            return ExecutorResult(
                (),
                f"inject_heat 参数越界：power {new_power} 超过上限 {MAX_POWER}",
                0,
            )
        effect = self._set_component(
            proposal,
            world,
            entity_id,
            MACHINE_COMPONENT,
            {"power": new_power},
            "inject_heat",
        )
        return ExecutorResult((effect,), None, 0)

    def _toggle_machine(self, proposal: "ActionProposal", world: "WorldState") -> ExecutorResult:
        entity_id, power, error = self._machine_state(world)
        if error is not None:
            return ExecutorResult((), error, 0)
        new_power = OFF_POWER if power > OFF_POWER else DEFAULT_POWER
        effect = self._set_component(
            proposal,
            world,
            entity_id,
            MACHINE_COMPONENT,
            {"power": new_power},
            "toggle_machine",
        )
        return ExecutorResult((effect,), None, 0)

    def _cool(self, proposal: "ActionProposal", world: "WorldState") -> ExecutorResult:
        """F2：冷却 = 功率档位减一（machine 侧单写权；温度由 dynamics 按
        功率积分自然回落，平衡温度 = AMBIENT + POWER_HEAT_RATE * power）。"""
        entity_id, power, error = self._machine_state(world)
        if error is not None:
            return ExecutorResult((), error, 0)
        new_power = power - 1
        if new_power < OFF_POWER:
            return ExecutorResult(
                (),
                f"cool 参数越界：power {new_power} 低于下限 {OFF_POWER}",
                0,
            )
        effect = self._set_component(
            proposal,
            world,
            entity_id,
            MACHINE_COMPONENT,
            {"power": new_power},
            "cool",
        )
        return ExecutorResult((effect,), None, 0)

    def _set_component(
        self,
        proposal: "ActionProposal",
        world: "WorldState",
        entity_id: "EntityId",
        component_type: ComponentTypeId,
        payload: dict,
        action_id: str,
    ) -> ProposedEffect:
        """构造 ``core.set_component`` 效果（payload = 完整组件数据，整体替换）。

        ``effect_id`` 由 (扩展名, action_id, proposal_id) 确定性派生：
        同一提案恒同 id（K7 去重面），不同提案恒异 id。
        """
        return ProposedEffect(
            effect_id=new_deterministic_effect_id(
                "complex_minimal.boiler_action", action_id, str(proposal.proposal_id)
            ),
            effect_type=_SET_COMPONENT,
            source=EXECUTOR_PRODUCER_ID,
            target=EntityTarget(entity_id=entity_id, component_type=component_type),
            payload=payload,
            base_revision=world.world_revision,
            cause_ids=[
                CauseRef(kind=CauseKind.PROPOSAL, ref_id=str(proposal.proposal_id))
            ],
        )


# —— 数值动力学 backend（K2/K5：只返回 ProposedEffect）——


class BoilerThermalBackend:
    """数值动力学：锅炉房温度离散积分（零随机、零 I/O）。

    更新规则（每次 ``simulate``，dt = ``context.dt``）::

        heat_source = AMBIENT_HEAT_SOURCE_CELSIUS
                      + POWER_HEAT_RATE_CELSIUS * machine.power
        celsius'    = celsius + THERMAL_COEFFICIENT * (heat_source - celsius) * dt

    - 平衡态（|delta| < epsilon）→ 零效果（不浪费 revision）；
    - 组件缺位 → 取 schema 缺省（power = 2 / celsius = 20.0）参与积分，
      变化时产出 set_component 效果完成组件落位；
    - ``stimuli`` 接受但不消费（纯状态函数；事件刺激面留 follow-up）。
    """

    def metadata(self) -> BackendMetadata:
        """backend 自描述（词表 = dynamics.backend 闭集常量取值）。"""
        return BackendMetadata(
            backend_id="complex_minimal.boiler_thermal",
            producer_id=str(DYNAMICS_PRODUCER_ID),
            # F2 单写权拆分：dynamics 只写 temperature（machine 归 executor
            # 独占）；host（T9）从本 domains 自动派生 dynamics grant。
            domains=(str(TEMPERATURE_COMPONENT),),
            determinism="deterministic",
            implementation_type="numerical",
            fidelity="discrete_1d",
            checkpointable=True,
            restorable=True,
            replayable=True,
        )

    def simulate(
        self,
        snapshot: "WorldSnapshot",
        stimuli: "tuple[Stimulus, ...]",
        context: "DynamicsContext",
    ) -> "tuple[ProposedEffect, ...]":
        """单 tick 温度积分；产 0 或 1 条 ``core.set_component`` 效果。"""
        del stimuli  # 最小闭环 = 纯状态函数（见类 docstring）
        world = snapshot.world_state

        boiler_id = _resolve_entity_id(world, BOILER_SLUG, MACHINE_COMPONENT)
        power = DEFAULT_POWER
        if boiler_id is not None:
            candidate = _read_component(world, boiler_id, MACHINE_COMPONENT).get("power")
            if isinstance(candidate, int) and not isinstance(candidate, bool):
                power = candidate

        room_id = _resolve_entity_id(world, ROOM_SLUG, TEMPERATURE_COMPONENT)
        if room_id is None:
            return ()
        raw_celsius = _read_component(world, room_id, TEMPERATURE_COMPONENT).get("celsius")
        component_present = _valid_number(raw_celsius)
        celsius = float(raw_celsius) if component_present else DEFAULT_CELSIUS

        heat_source = AMBIENT_HEAT_SOURCE_CELSIUS + POWER_HEAT_RATE_CELSIUS * power
        new_celsius = round(
            celsius + THERMAL_COEFFICIENT * (heat_source - celsius) * context.dt,
            _ROUND_DIGITS,
        )
        if component_present and abs(new_celsius - celsius) < _EPSILON:
            return ()

        effect = ProposedEffect(
            effect_id=new_deterministic_effect_id(
                "complex_minimal.boiler_thermal",
                snapshot.world_instance_id,
                context.base_revision,
            ),
            effect_type=_SET_COMPONENT,
            source=DYNAMICS_PRODUCER_ID,
            target=EntityTarget(entity_id=room_id, component_type=TEMPERATURE_COMPONENT),
            payload={"celsius": new_celsius},
            base_revision=Revision(context.base_revision),
        )
        return (effect,)

    @property
    def diagnostics(self) -> tuple:
        """last-run 诊断视图（D-P7-15 面）：本 backend 永不产非致命诊断。"""
        return ()


# —— contract §3 入口 ——


def build_extension(context: "ExtensionContext") -> ExtensionBundle:
    """contract §3 冻结入口：``build_extension(context) -> ExtensionBundle``。

    ``context`` = ``ExtensionContext``（frozen；``project_root: Path`` +
    ``ir: ProjectIR``）。最小闭环不消费 context 内容（游戏参数全部由 YAML
    声明）；签名按 contract 保留，供后续扩展（如自 IR 读场景参数）。

    返回（全部纯数据，零副作用）：

    - ``action_executors``：单个 :class:`BoilerMachineExecutor` 实例注册在
      全部 3 个 action id 下（分派按 ``proposal.action_id``）；
    - ``dynamics_backends``：单个 :class:`BoilerThermalBackend`；
    - ``policies``：空（NPC 策略归 runtime 装配面，不经扩展）；
    - ``producer_grants``：仅 executor 侧 1 条（machine 独占写权）。
      F2 单写权拆分：P2 授权面「优先级 → 特异性 → 注册序，首条匹配拍板」
      语义下一组件仅一个有效 writer——executor 独占 machine、dynamics
      独占 temperature（其 grant 由 host 从 ``metadata().domains`` 自动
      派生，T3 契约；显式重复声明只会触发 LLMSIM_DUPLICATE_ID 且遮蔽
      动作侧授权，故不声明）。
    """
    del context  # 见 docstring：最小闭环不消费
    executor = BoilerMachineExecutor()
    return ExtensionBundle(
        action_executors={
            "inject_heat": executor,
            "cool": executor,
            "toggle_machine": executor,
        },
        dynamics_backends=(BoilerThermalBackend(),),
        policies={},
        producer_grants=(
            ProducerGrant(
                producer_id=str(EXECUTOR_PRODUCER_ID),
                component_types=(str(MACHINE_COMPONENT),),
            ),
        ),
    )
