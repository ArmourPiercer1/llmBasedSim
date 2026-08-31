"""P7-W1 dynamics backend 核心契约（SOT §3.1，T01；12 exports，账本序 §8.2 钉死）。

WorldDynamics 契约面载体：输入数据类（``Stimulus`` / ``DynamicsContext``，
D-P7-09）、快照投影（``WorldSnapshot``，核心 ``Snapshot`` 的薄只读投影，
D-P7-14）、backend 自描述（``BackendMetadata``，闭集词表 D-P7-03）、backend
协议（``WorldDynamicsBackend``，同步 + tuple 化，D-P7-01/DEV-P7-1）与确定性
effect ID 工厂（``new_deterministic_effect_id``，K7：零 uuid4、零 random、
零墙钟）。

纪律（SOT §0.5/§3.0）：

- JSON-clean 铁律：``Stimulus.payload`` / ``DynamicsContext`` 数据面 /
  ``BackendMetadata.to_dict()`` 必须过 ``core/serialization.py``
  ``assert_json_clean``（构造期机械断言，违规 → :class:`DynamicsError`）；
- K2/K5：本模块只定义契约输入/输出类型，永不写 WorldState——世界写入唯一
  形式是 backend ``simulate`` 返回 ``ProposedEffect``；
- ``DynamicsContext.clock`` 持协议实例（非数据，不进 checkpoint，host 重建，
  D-P7-14）；W1 按 §3.0 import 闭集不消费 P6 运行时，本地定义结构化镜像
  协议 ``_MonotonicClock``（与 P6 ``MonotonicClock`` Protocol 同形：单方法
  ``now_ms() -> int``，结构兼容，host 可注入 P6 时钟实现）。
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final, Mapping, Protocol

from src.engine_v2.core.effects import ProposedEffect
from src.engine_v2.core.ids import PRODUCER_ID_PATTERN, EffectId
from src.engine_v2.core.serialization import assert_json_clean
from src.engine_v2.core.snapshot import Snapshot
from src.engine_v2.core.state import WorldState

if TYPE_CHECKING:
    from src.engine_v2.dynamics.diagnostic import DynamicsDiagnostic

__all__ = [
    "WorldSnapshot",
    "Stimulus",
    "STIMULUS_KINDS",
    "DynamicsContext",
    "InferenceBudget",
    "BackendMetadata",
    "DETERMINISM_CLASSES",
    "IMPLEMENTATION_TYPES",
    "FIDELITY_PATTERN",
    "WorldDynamicsBackend",
    "new_deterministic_effect_id",
    "DynamicsError",
]

# —— 闭集词表（D-P7-03，SOT §3.1 逐字钉死）——

#: backend 确定性类闭集（metadata 构造期校验词表）。
DETERMINISM_CLASSES: Final[tuple[str, ...]] = (
    "deterministic",
    "seeded",
    "nondeterministic",
)

#: backend 实现类型闭集（Spec §15.4 描述性口径，D-P7-03）。
IMPLEMENTATION_TYPES: Final[tuple[str, ...]] = ("rule", "llm", "numerical", "composite")

#: 名字型（点分）词法：fidelity / backend_id 共用（Spec §15.4，D-P7-03）。
FIDELITY_PATTERN: Final[str] = r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)*$"

#: ``Stimulus.kind`` 闭集：``event`` = 世界内事件（DomainEvent 衍生的事实）；
#: ``external`` = host 注入事实（anvil 场景中"支撑被移除"即 external 刺激）。
STIMULUS_KINDS: Final[tuple[str, ...]] = ("event", "external")


class DynamicsError(Exception):
    """P7 本地构造/契约错误基类（SOT §3.1；二分纪律，镜像 P5/P6）。

    构造期违规（闭集词表违规、restore 版本不符、JSON-clean 数据面污染、
    预算参数非法等）走异常；非致命运行面走 ``DynamicsDiagnostic`` last-run
    通道（D-P7-15）。
    """


@dataclass(frozen=True)
class InferenceBudget:
    """推理预算（仅推理型 backend 消费；D-P7-04 显式化 K7 预算面）。

    构造校验：非 int（bool 亦拒）/ 负值 → :class:`DynamicsError`。
    """

    max_calls: int = 1
    max_repair_retries: int = 1

    def __post_init__(self) -> None:
        for name in ("max_calls", "max_repair_retries"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise DynamicsError(
                    f"InferenceBudget.{name} 必须为非负 int（bool 拒绝），得到 {value!r}"
                )


@dataclass(frozen=True)
class Stimulus:
    """dynamics 输入刺激（host 给定，SOT §3.1；P7-INV-4 JSON-clean 面）。

    - ``stimulus_id`` 非空、host 给定（backend 不发明）；
    - ``kind`` ∈ ``STIMULUS_KINDS`` 闭集（``event`` / ``external``）；
    - ``source`` 非空来源描述（entity_id / host 引用）；
    - ``entity_id`` 可选实体目标；
    - ``payload`` 必须 ``assert_json_clean``（``__post_init__`` 机械断言，
      违规 → :class:`DynamicsError`）。
    """

    stimulus_id: str
    kind: str
    source: str
    entity_id: str | None
    payload: Mapping[str, object]

    def __post_init__(self) -> None:
        if not self.stimulus_id:
            raise DynamicsError("Stimulus.stimulus_id 必须非空（host 给定，不发明）")
        if self.kind not in STIMULUS_KINDS:
            raise DynamicsError(
                f"Stimulus.kind 必须属于 STIMULUS_KINDS 闭集，得到 {self.kind!r}"
            )
        if not self.source:
            raise DynamicsError("Stimulus.source 必须为非空来源描述")
        try:
            assert_json_clean(self.payload)
        except AssertionError as exc:
            raise DynamicsError(f"Stimulus.payload 非 JSON-clean：{exc}") from exc


class _MonotonicClock(Protocol):
    """P6 ``MonotonicClock`` Protocol（推理 adapter 模块 L47 钉死面）本地结构镜像。

    W1 按 §3.0 import 闭集不消费 P6 运行时；本镜像与其结构同形（单方法
    ``now_ms() -> int``），host 注入的 P6 ``SystemMonotonicClock`` /
    ``FixedMonotonicClock`` 实例按鸭子类型直接兼容。不导出（12-export 账本
    钉死，§8.2）。
    """

    def now_ms(self) -> int: ...


class _FixedMonotonicClock:
    """确定性默认时钟：start_ms=0、step_ms=1、后自增（post-increment）。

    语义同 P6 ``FixedMonotonicClock`` 缺省构造（SOT §3.1 ``FixedMonotonicClock
    (0.0)`` 口径的 W1 合规落位）；K7 零墙钟——同一实例序列调用输出恒定。
    """

    __slots__ = ("_next_ms",)

    def __init__(self) -> None:
        self._next_ms: int = 0

    def now_ms(self) -> int:
        current = self._next_ms
        self._next_ms += 1
        return current


@dataclass(frozen=True)
class DynamicsContext:
    """单回合 dynamics 调用上下文（SOT §3.1 输入数据类，D-P7-09）。

    - 数据面（``base_revision``/``dt``/``seed``）JSON-clean（``__post_init__``
      机械断言）；
    - ``seed`` 显式种子（K7/D-P7-04）：None = backend 必须声明 deterministic；
    - ``clock`` 为协议实例（非数据，不进 checkpoint，host 重建——D-P7-14），
      缺省 = 确定性固定时钟（0 起、步长 1、后自增）；
    - ``budget`` 推理预算（仅推理型 backend 消费）。
    """

    base_revision: int
    dt: float = 1.0
    seed: int | None = None
    clock: _MonotonicClock = field(default_factory=_FixedMonotonicClock)
    budget: InferenceBudget | None = None

    def __post_init__(self) -> None:
        try:
            assert_json_clean([self.base_revision, self.dt, self.seed])
        except AssertionError as exc:
            raise DynamicsError(
                f"DynamicsContext 数据面（base_revision/dt/seed）非 JSON-clean：{exc}"
            ) from exc


@dataclass(frozen=True)
class WorldSnapshot:
    """核心 ``Snapshot`` 的薄只读投影（D-P7-14；SOT §3.1）。

    - ``world_state`` 全字段（entities/world_variables/scenario_state/
      world_revision）；
    - ``world_revision`` 冗余投影（来源 = ``snap.world_state.world_revision``，
      backend 免拆包）；
    - ``logical_tick`` = ``snap.created_logical_tick``（逻辑刻，权威序整型，
      §0.2 铁律 3）；
    - ``world_instance_id`` = D-9 身份（信封层）；
    - **丢弃 ``created_wall_time``**：墙钟永不进入 dynamics 路径（K7 机械口）；
    - 冻结：任何字段赋值 → ``FrozenInstanceError``（§6.3 AD-5）。
    """

    world_state: WorldState
    world_revision: int
    logical_tick: int
    world_instance_id: str

    def __post_init__(self) -> None:
        if self.world_revision != self.world_state.world_revision:
            raise DynamicsError(
                "WorldSnapshot.world_revision 必须等于 world_state.world_revision："
                f"{self.world_revision} != {self.world_state.world_revision}"
            )

    @classmethod
    def from_snapshot(cls, snap: Snapshot) -> WorldSnapshot:
        """从核心 ``Snapshot`` 信封投影（丢弃 ``created_wall_time``，D-P7-14）。"""
        return cls(
            world_state=snap.world_state,
            world_revision=snap.world_state.world_revision,
            logical_tick=snap.created_logical_tick,
            world_instance_id=snap.world_instance_id,
        )


@dataclass(frozen=True)
class BackendMetadata:
    """backend 自描述元数据（D-P7-03 核心；SOT §3.1 逐字段钉死）。

    - ``backend_id`` 名字型（FIDELITY_PATTERN 同款词法）；
    - ``producer_id`` fullmatch ``PRODUCER_ID_PATTERN``（ids.py L77）；
    - ``domains`` 闭包域声明（组件类型/状态域名），**构造即排序去重**；
    - ``determinism`` ∈ ``DETERMINISM_CLASSES``；
      ``implementation_type`` ∈ ``IMPLEMENTATION_TYPES``；
    - ``fidelity`` 名字型（描述性：如 ``rigid_1d`` / ``semantic`` /
      ``abstract``）；
    - metadata 永不出现在游戏项目文件（K8/P7-INV-9）：声明载体 = 各 backend
      模块导出常量 + host 注册。
    """

    backend_id: str
    producer_id: str
    domains: tuple[str, ...]
    determinism: str
    implementation_type: str
    fidelity: str
    checkpointable: bool
    restorable: bool
    replayable: bool

    def __post_init__(self) -> None:
        if not isinstance(self.backend_id, str) or re.fullmatch(
            FIDELITY_PATTERN, self.backend_id
        ) is None:
            raise DynamicsError(f"BackendMetadata.backend_id 词法非法：{self.backend_id!r}")
        if not isinstance(self.producer_id, str) or PRODUCER_ID_PATTERN.fullmatch(
            self.producer_id
        ) is None:
            raise DynamicsError(
                f"BackendMetadata.producer_id 词法非法：{self.producer_id!r}"
            )
        if self.determinism not in DETERMINISM_CLASSES:
            raise DynamicsError(
                f"BackendMetadata.determinism 必须属于 DETERMINISM_CLASSES："
                f"{self.determinism!r}"
            )
        if self.implementation_type not in IMPLEMENTATION_TYPES:
            raise DynamicsError(
                f"BackendMetadata.implementation_type 必须属于 IMPLEMENTATION_TYPES："
                f"{self.implementation_type!r}"
            )
        if not isinstance(self.fidelity, str) or re.fullmatch(FIDELITY_PATTERN, self.fidelity) is None:
            raise DynamicsError(f"BackendMetadata.fidelity 词法非法：{self.fidelity!r}")
        object.__setattr__(self, "domains", tuple(sorted(set(self.domains))))

    def to_dict(self) -> dict[str, object]:
        """JSON-clean dict 视图（``domains`` tuple → list）。

        SOT §3.1：``to_dict()`` 必须过 ``assert_json_clean``（A17 双构造
        稳定断言的机械面）。
        """
        data: dict[str, object] = {
            "backend_id": self.backend_id,
            "producer_id": self.producer_id,
            "domains": list(self.domains),
            "determinism": self.determinism,
            "implementation_type": self.implementation_type,
            "fidelity": self.fidelity,
            "checkpointable": self.checkpointable,
            "restorable": self.restorable,
            "replayable": self.replayable,
        }
        assert_json_clean(data)
        return data


class WorldDynamicsBackend(Protocol):
    """WorldDynamics backend 协议（D-P7-01 同步定案；DEV-P7-1 tuple 化）。

    - ``simulate`` 同步 + tuple 化输入/输出；全部世界写入只能以返回
      ``ProposedEffect`` 形式出现（K2/K5）；
    - ``diagnostics`` = 本实例 last-run 视图（D-P7-15：``simulate`` 入口
      重置，运行面非致命违规经此上报）。
    """

    def metadata(self) -> BackendMetadata: ...

    def simulate(
        self,
        snapshot: WorldSnapshot,
        stimuli: tuple[Stimulus, ...],
        context: DynamicsContext,
    ) -> tuple[ProposedEffect, ...]: ...

    @property
    def diagnostics(self) -> tuple[DynamicsDiagnostic, ...]: ...


def new_deterministic_effect_id(*parts: object) -> EffectId:
    """确定性 effect ID 工厂（K7；SOT §3.1 公式逐字）。

    ``"eff_" + sha256(canonical).hexdigest()[:32]``；canonical =
    ``json.dumps([str(p) for p in parts], sort_keys=True, ensure_ascii=False,
    separators=(",", ":"))``。满足 EffectId 词法（``eff_`` + 32 hex）；
    **禁 uuid4**（core ``new_effect_id`` 为 K7 禁用面）；双跑同参 → 同 ID。
    """
    canonical = json.dumps(
        [str(part) for part in parts],
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return EffectId("eff_" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32])
