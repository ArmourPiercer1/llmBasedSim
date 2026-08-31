"""P7-W1 1D 刚体 toy 数值 backend（SOT §3.4，T06；3 exports）。

pos/vel/acc 标量积分：``pos' = pos + vel * dt`` / ``vel' = vel + acc * dt``
（acc 缺省 0.0）；只产**结构型** ``core.set_component``（整组件替换，
payload = ``{"pos": pos', "vel": vel'}`` 恰 2 键，JSON-clean dict）；
effect ID = 确定性工厂（K7）。

纪律（D-P7-04/K7）：零模块级 RNG、零模块级可变容器、零 ``random`` import
（test_toy_rigid.py t13 AST 断言面）；seed 为显式接口统一位，当前纯确定性
积分**不消费** RNG（seed 仅存于 checkpoint 供未来扩展）；浮点纪律 = 直接
IEEE 双精度运算（确定性 = 同平台同输入同输出，跨平台位级一致不承诺，
fidelity 声明 ``rigid_1d`` 如实）。

Case C 读法（D-P7-04 裁定）：同一 checkpoint dict 两次独立 ``restore()`` =
两条独立 continuation（各自 ``simulate`` 输出 byte-identical 即 branch 语义
成立），不依赖 P8 世界实例层 fork——backend 层 checkpoint/restore 自足。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from src.engine_v2.core.components import ComponentTypeId
from src.engine_v2.core.effects import EntityTarget, ProposedEffect
from src.engine_v2.core.serialization import assert_json_clean
from src.engine_v2.dynamics.backend import (
    BackendMetadata,
    DynamicsContext,
    DynamicsError,
    Stimulus,
    WorldSnapshot,
    new_deterministic_effect_id,
)
from src.engine_v2.dynamics.diagnostic import DynamicsDiagnostic

__all__ = ["ToyRigidDynamics", "RIGID_COMPONENT", "TOY_CHECKPOINT_VERSION"]

#: rigid 组件类型（P7 自持；测试侧 ComponentRegistry 注册，§5.1 世界夹具）。
RIGID_COMPONENT: Final[ComponentTypeId] = ComponentTypeId("rigid")

#: toy checkpoint 版本（restore 版本匹配口径；SOT §3.4 钉死 = 1）。
TOY_CHECKPOINT_VERSION: Final[int] = 1


class ToyRigidDynamics:
    """1D 刚体 toy 数值 backend（SOT §3.4；``WorldDynamicsBackend`` 结构化满足）。

    构造仅存 seed（显式接口统一位，不消费 RNG）+ 空 last-run 诊断通道
    （D-P7-15）；实例零共享状态，双跑同输入 → 输出 byte-identical（K7）。
    """

    __slots__ = ("_seed", "_diagnostics")

    def __init__(self, *, seed: int = 0) -> None:
        self._seed: int = seed
        # last-run 诊断通道（D-P7-15）：simulate 入口重置
        self._diagnostics: list[DynamicsDiagnostic] = []

    # —— WorldDynamicsBackend 协议（同步，D-P7-01）——

    def metadata(self) -> BackendMetadata:
        """自描述元数据（SOT §3.4 钉死；A14 断言面）。"""
        return BackendMetadata(
            backend_id="rigid_body",
            producer_id="rigid_body",
            domains=("rigid",),
            determinism="deterministic",
            implementation_type="numerical",
            fidelity="rigid_1d",
            checkpointable=True,
            restorable=True,
            replayable=True,
        )

    def simulate(
        self,
        snapshot: WorldSnapshot,
        stimuli: tuple[Stimulus, ...],
        context: DynamicsContext,
    ) -> tuple[ProposedEffect, ...]:
        """同步单步积分（K7：同 snapshot/刺激/context 双跑 → byte-identical）。

        对快照中**按 entity_id 字典序**遍历每个含 ``rigid`` 组件的实体：
        ``pos' = pos + vel * dt``；``vel' = vel + acc * dt``（acc 缺省
        0.0）；产出结构型 ``core.set_component``（EntityTarget(entity,
        "rigid")，payload = ``{"pos": pos', "vel": vel'}``——整组件替换）。
        ``effect_id = new_deterministic_effect_id("rigid", entity_id,
        context.base_revision)``。无 rigid 组件 → 空元组（零 effect，合法）。
        """
        self._diagnostics = []
        effects: list[ProposedEffect] = []
        entities = snapshot.world_state.entities
        for entity_id in sorted(entities):
            components = entities[entity_id].components
            rigid = components.get(RIGID_COMPONENT)
            if rigid is None:
                continue
            pos = float(rigid.get("pos", 0.0))
            vel = float(rigid.get("vel", 0.0))
            acc = float(rigid.get("acc", 0.0))
            next_pos = pos + vel * context.dt
            next_vel = vel + acc * context.dt
            effects.append(
                ProposedEffect(
                    effect_id=new_deterministic_effect_id(
                        "rigid", entity_id, context.base_revision
                    ),
                    effect_type="core.set_component",
                    source="rigid_body",
                    target=EntityTarget(
                        entity_id=entity_id, component_type=RIGID_COMPONENT
                    ),
                    payload={"pos": next_pos, "vel": next_vel},
                    base_revision=context.base_revision,
                )
            )
        return tuple(effects)

    @property
    def diagnostics(self) -> tuple[DynamicsDiagnostic, ...]:
        """last-run 诊断视图（D-P7-15：``simulate`` 入口重置）。"""
        return tuple(self._diagnostics)

    # —— checkpoint / restore（Case C 自足口径，D-P7-04）——

    def checkpoint(self) -> dict[str, object]:
        """checkpoint：``{"version": 1, "seed": <int>}``。

        无本地状态（实体面为空）；整体 JSON-clean（A11 断言面）。
        """
        return {"version": TOY_CHECKPOINT_VERSION, "seed": self._seed}

    def restore(self, cp: Mapping) -> ToyRigidDynamics:
        """restore：返回**新实例**（frozen 纪律，零就地变更）。

        校验序列：整体 ``assert_json_clean`` → ``version ==
        TOY_CHECKPOINT_VERSION`` → ``seed`` 为 int（bool 拒绝）——违规 →
        :class:`DynamicsError`（运行面另发 ``p7.checkpoint_restore_failed``
        诊断，D-P7-15 通道）。
        """
        if not isinstance(cp, Mapping):
            self._record_restore_failure(
                f"checkpoint 必须为 mapping，得到 {type(cp).__name__}"
            )
        try:
            assert_json_clean(cp)
        except AssertionError as exc:
            self._record_restore_failure(f"checkpoint 非 JSON-clean：{exc}")
        if cp.get("version") != TOY_CHECKPOINT_VERSION:
            self._record_restore_failure(
                f"checkpoint.version 不符：{cp.get('version')!r} "
                f"!= {TOY_CHECKPOINT_VERSION}"
            )
        seed = cp.get("seed")
        if isinstance(seed, bool) or not isinstance(seed, int):
            self._record_restore_failure(
                f"checkpoint.seed 必须为 int（bool 拒绝）：{seed!r}"
            )
        return ToyRigidDynamics(seed=seed)

    def _record_restore_failure(self, message: str) -> None:
        """记录 ``p7.checkpoint_restore_failed`` 诊断并抛异常（二分纪律）。

        运行面诊断先落 last-run 通道（可达性 = AD-6/t11/t12 断言面），构造
        期异常随后抛出（非静默吞错）。
        """
        self._diagnostics.append(
            DynamicsDiagnostic(
                code="p7.checkpoint_restore_failed",
                severity="error",
                path="checkpoint",
                message=message,
            )
        )
        raise DynamicsError(f"toy restore 契约违规：{message}")
