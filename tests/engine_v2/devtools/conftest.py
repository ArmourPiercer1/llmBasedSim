"""P8 devtools 侧 conftest（SOT §6.2 devtools 行；自包含紧凑 SC-1 构件）。

构件（SOT §6.2 表逐项对应）：

- ``_barrier_isolation``（autouse）：写屏障 opt-in 纪律（P7 gate L113–118
  同形）——测试前后各 ``uninstall_write_barrier()`` 还原全局未武装态；
- ``make_p8_world()`` / ``make_p8_runtime(backend_refs=())``：SC-1 初始
  ``WorldState``（§6.4 字面量 entity id ``"ent_a"`` / ``"ent_b"`` + ``score``
  世界变量）/ ``RuntimeState``（``backend_refs`` 参数化）；
- ``make_sc3_runtime()``：**SC-3 变体**（G8-4 负样本）：SC-1 runtime + 一条
  ``checkpointable=False`` 的 ``BackendStateRef``；
- ``make_p8_policy()`` / ``make_p8_executor()``：测试侧 authority（通配单
  规则放行 ``devtools.developer`` + ``p8.rule``，P7 gate 同族）+ 执行器
  （handlers = 冻结 ``default_handler_registry()``）；
- ``run_p8_script()``：SC-1 3 回合脚本（§5.1）→ ``P8RunBundle``（模块级
  私有 dataclass）；
- ``make_p8_backend(tmp_path)`` / ``build_p8_envelope(run)`` /
  ``build_p8_save(tmp_path, run)``：结构 save 构建面（**零 P7 依赖**——
  devtools CLI 面只需结构 save；§6.2 重复口径：两侧各一份）；
- ``cli_runner(tmp_path)``：``argv → (stdout, exit_code)`` 助手（体内惰性
  导入 W4 ``run_devcontrol_cli``——跨波次缝，W4 交付前不顶层导入）。

纪律：全部 id / wall time / 版本串为**字面量**（§6.4：零随机、零时钟，
D5/D6）；扁平构件（函数非 fixture），与 persistence 侧同契约。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from src.engine_v2.core import (
    AuthorityPolicy,
    AuthorityRule,
    AuthoritySelector,
    BackendStateRef,
    CauseKind,
    CauseRef,
    CascadeExecutor,
    ComponentRegistry,
    ComponentSchema,
    ComponentTypeId,
    EFFECT_SET_COMPONENT,
    EFFECT_SET_WORLD_VARIABLE,
    EntityId,
    EntityRecord,
    EffectId,
    EntityTarget,
    OriginKind,
    ProducerId,
    ProducerInfo,
    ProducerRegistry,
    ProposedEffect,
    Provenance,
    Revision,
    RuntimeLifecycle,
    RuntimeState,
    StateDomainId,
    StateDomainTarget,
    Snapshot,
    TraceKind,
    TraceRecord,
    TraceRecordId,
    WorldState,
    default_handler_registry,
    uninstall_write_barrier,
)
from src.engine_v2.persistence.filesystem import FilesystemPersistenceBackend
from src.engine_v2.persistence.snapshot import PersistenceSnapshot, to_persistence_snapshot

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

__all__ = [
    "P8RunBundle",
    "make_p8_world",
    "make_p8_runtime",
    "make_sc3_runtime",
    "make_p8_policy",
    "make_p8_executor",
    "run_p8_script",
    "make_p8_backend",
    "build_p8_envelope",
    "build_p8_save",
    "cli_runner",
]

# —— §6.4 钉死字面量（零随机、零时钟；与 persistence 侧同族同值）——

_WSI_SC1 = "wsi_p8_sc1"
_WALL_TIME = "1970-01-01T00:00:00+00:00"
_SAVE_ID_SC1 = "save_p8_base"
_PROJECT_VERSION = "1.0.0"
_MODULE_VERSIONS: dict[str, str] = {"core": "84a5d4f"}

_DEV_PRODUCER = "devtools.developer"
_RULE_PRODUCER = "p8.rule"

_CMD_PATCH_ID = "dev-patch-1"
_CMD_INJECT_ID = "dev-inject-1"
_RECORD_PATCH_ID = "trc_00000000000000000000000000000042"
_RECORD_INJECT_ID = "trc_00000000000000000000000000000043"

_EFFECT_PATCH_ID = "eff_p8_dev_patch_1"
_EFFECT_RULE_MARK_ID = "eff_p8_rule_mark_1"
_EFFECT_INJECT_ID = "eff_p8_dev_inject_1"
_CAUSAL_ROOT_RULE_TURN2 = "rule_p8_turn2"

_SC1_TURNS = 3


@dataclass(frozen=True)
class P8RunBundle:
    """SC-1 3 回合脚本管道结果（conftest 私有载体；SOT §6.2 同契约）。

    - ``final_state``：3 笔 committed 事务后的 ``WorldState``
      （``world_revision`` 0→3）；
    - ``runtime_state``：``logical_tick`` = 3（3 回合后读数）；
    - ``trace_records``：全量 trace（dev_intervention ×2 前置各回合级联
      trace；文件序）；
    - ``dev_command_ids``：回 1 / 回 3 的 devtools 命令 id（§6.4 字面量）；
    - ``rule_producer_id``：回 2 测试侧 rule producer（``"p8.rule"``）。
    """

    final_state: WorldState
    runtime_state: RuntimeState
    trace_records: tuple[TraceRecord, ...]
    dev_command_ids: tuple[str, ...]
    rule_producer_id: str


@pytest.fixture(autouse=True)
def _barrier_isolation() -> None:
    """写屏障 opt-in 纪律（P7 gate L113–118 同形）：CascadeExecutor 构造即
    武装屏障，测试前后各还原一次全局未武装态。"""
    uninstall_write_barrier()
    yield
    uninstall_write_barrier()


# —— SC-1 世界 / 运行时 / authority / 执行器 ——


def make_p8_world() -> WorldState:
    """SC-1 初始 ``WorldState``（§5.1；§6.4 字面量 entity id）。

    2 entity（``ent_a`` / ``ent_b``，确定性字面量 id）+ world variable
    ``{"score": 0}``。
    """
    return WorldState(
        entities={
            EntityId("ent_a"): EntityRecord(entity_id=EntityId("ent_a")),
            EntityId("ent_b"): EntityRecord(entity_id=EntityId("ent_b")),
        },
        world_variables={"score": 0},
    )


def make_p8_runtime(backend_refs: "Sequence[BackendStateRef]" = ()) -> RuntimeState:
    """SC-1 ``RuntimeState``（``backend_refs`` 参数化——SC-3 注入
    non-checkpointable ref；``lifecycle=STEPPING`` 语义不强制）。"""
    refs = {ref.backend_id: ref for ref in backend_refs}
    return RuntimeState(lifecycle=RuntimeLifecycle.STEPPING, backend_refs=refs)


def make_sc3_runtime() -> RuntimeState:
    """**SC-3 变体**（G8-4 负样本）：SC-1 runtime + 一条
    ``checkpointable=False`` 的 ``BackendStateRef``（§5.1）。"""
    return make_p8_runtime(
        backend_refs=(
            BackendStateRef(
                backend_id="rigid_body",
                backend_kind="dynamics",
                checkpointable=False,
            ),
        )
    )


def _p8_component_registry() -> ComponentRegistry:
    """SC-1 测试侧组件注册表：``marker`` 描述型 schema（不透明 payload）。"""
    registry = ComponentRegistry()
    registry.register(
        ComponentSchema(
            component_type=ComponentTypeId("marker"),
            description="P8 SC-1 回 2 marker 组件（描述型 schema，不透明 payload）",
        )
    )
    return registry


def make_p8_producer_registry() -> ProducerRegistry:
    """测试侧 producer 注册表：``devtools.developer`` + ``p8.rule``（各
    priority 100）。"""
    registry = ProducerRegistry()
    registry.register(
        ProducerInfo(
            producer_id=ProducerId(_DEV_PRODUCER),
            origin=OriginKind.DEVELOPER,
            priority=100,
            description="P8 devtools developer 干预 producer",
        )
    )
    registry.register(
        ProducerInfo(
            producer_id=ProducerId(_RULE_PRODUCER),
            origin=OriginKind.RULE,
            priority=100,
            description="P8 测试侧 rule producer",
        )
    )
    return registry


def make_p8_policy() -> AuthorityPolicy:
    """测试侧 authority：通配单规则放行 ``devtools.developer`` + ``p8.rule``
    （P7 gate L131–146 同族：closed-by-default，K3）。"""
    return AuthorityPolicy(
        rules=[
            AuthorityRule(
                selector=AuthoritySelector(),
                allowed_writers=[
                    ProducerId(_DEV_PRODUCER),
                    ProducerId(_RULE_PRODUCER),
                ],
                priority=100,
            )
        ]
    )


def make_p8_executor() -> CascadeExecutor:
    """SC-1 执行器（SOT §6.2 逐参：policy / handlers = 冻结
    ``default_handler_registry()`` / component_registry 测试侧）。"""
    return CascadeExecutor(
        policy=make_p8_policy(),
        handlers=default_handler_registry(),
        component_registry=_p8_component_registry(),
        producer_registry=make_p8_producer_registry(),
    )


# —— SC-1 3 回合脚本管道（§5.1）——


def _dev_intervention_record(
    *,
    record_id: str,
    command_id: str,
    kind: str,
    payload: Mapping[str, object],
    world_revision: "Revision",
    logical_tick: int,
) -> TraceRecord:
    """DEV_INTERVENTION 记录合成（§3.7 步骤 2 精确口径；K7 零 uuid4——
    record_id host 字面量给出）。"""
    return TraceRecord(
        record_id=TraceRecordId(record_id),
        kind=TraceKind.DEV_INTERVENTION,
        world_revision=world_revision,
        logical_tick=logical_tick,
        producer_id=ProducerId(_DEV_PRODUCER),
        payload={"command": {"command_id": command_id, "kind": kind, "payload": payload}},
    )


def run_p8_script() -> P8RunBundle:
    """SC-1 3 回合脚本（§5.1；全结构效果，零推理侧消费）→ ``P8RunBundle``。

    回合（全部经正常提交管道 ``CascadeExecutor.run``，K2/K3 同面）：

    - 回 1：``patch_state`` world_variable ``score→1``
      （``devtools.developer``；INTERVENTION cause；causal_root =
      ``"dev-patch-1"``）；
    - 回 2：测试侧 rule producer ``p8.rule`` 对 ``ent_a``
      ``core.set_component``（组件 ``marker`` = ``{"tag": "p8_rule"}``）；
    - 回 3：``inject_event`` 通用包裹 ``core.set_world_variable``
      ``score→2``（causal_root = ``"dev-inject-1"``）。

    trace 序：dev 记录前置各回合级联 trace（DEV_INTERVENTION ×2，host
    字面量 record_id）/ authority / validation / transaction /
    domain_event 族。
    """
    world = make_p8_world()
    executor = make_p8_executor()
    state = world
    traces: list[TraceRecord] = []

    # —— 回 1：patch_state（devtools.developer；INTERVENTION cause）——
    pre_revision = state.world_revision
    dev_record_1 = _dev_intervention_record(
        record_id=_RECORD_PATCH_ID,
        command_id=_CMD_PATCH_ID,
        kind="patch_state",
        payload={"target": "world_variable", "key": "score", "value": 1},
        world_revision=pre_revision,
        logical_tick=1,
    )
    effect_1 = ProposedEffect(
        effect_id=EffectId(_EFFECT_PATCH_ID),
        effect_type=EFFECT_SET_WORLD_VARIABLE,
        source=ProducerId(_DEV_PRODUCER),
        target=StateDomainTarget(domain=StateDomainId("world_variables")),
        payload={"key": "score", "value": 1},
        base_revision=pre_revision,
        cause_ids=[CauseRef(kind=CauseKind.INTERVENTION, ref_id=_RECORD_PATCH_ID)],
    )
    result_1 = executor.run(
        (effect_1,),
        state,
        causal_root_id=_CMD_PATCH_ID,
        origin=Provenance(producer_id=ProducerId(_DEV_PRODUCER), origin=OriginKind.DEVELOPER),
    )
    state = result_1.final_state
    traces.extend((dev_record_1, *result_1.trace_records))

    # —— 回 2：p8.rule 对 ent_a core.set_component（marker）——
    pre_revision = state.world_revision
    effect_2 = ProposedEffect(
        effect_id=EffectId(_EFFECT_RULE_MARK_ID),
        effect_type=EFFECT_SET_COMPONENT,
        source=ProducerId(_RULE_PRODUCER),
        target=EntityTarget(entity_id=EntityId("ent_a"), component_type=ComponentTypeId("marker")),
        payload={"tag": "p8_rule"},
        base_revision=pre_revision,
    )
    result_2 = executor.run(
        (effect_2,),
        state,
        causal_root_id=_CAUSAL_ROOT_RULE_TURN2,
        origin=Provenance(producer_id=ProducerId(_RULE_PRODUCER), origin=OriginKind.RULE),
    )
    state = result_2.final_state
    traces.extend(result_2.trace_records)

    # —— 回 3：inject_event 通用包裹 core.set_world_variable score→2 ——
    pre_revision = state.world_revision
    dev_record_3 = _dev_intervention_record(
        record_id=_RECORD_INJECT_ID,
        command_id=_CMD_INJECT_ID,
        kind="inject_event",
        payload={
            "effect_id": _EFFECT_INJECT_ID,
            "effect_type": EFFECT_SET_WORLD_VARIABLE,
            "target_kind": "state_domain",
            "domain": "world_variables",
            "payload": {"key": "score", "value": 2},
        },
        world_revision=pre_revision,
        logical_tick=3,
    )
    effect_3 = ProposedEffect(
        effect_id=EffectId(_EFFECT_INJECT_ID),
        effect_type=EFFECT_SET_WORLD_VARIABLE,
        source=ProducerId(_DEV_PRODUCER),
        target=StateDomainTarget(domain=StateDomainId("world_variables")),
        payload={"key": "score", "value": 2},
        base_revision=pre_revision,
        cause_ids=[CauseRef(kind=CauseKind.INTERVENTION, ref_id=_RECORD_INJECT_ID)],
    )
    result_3 = executor.run(
        (effect_3,),
        state,
        causal_root_id=_CMD_INJECT_ID,
        origin=Provenance(producer_id=ProducerId(_DEV_PRODUCER), origin=OriginKind.DEVELOPER),
    )
    state = result_3.final_state
    traces.extend((dev_record_3, *result_3.trace_records))

    runtime_state = RuntimeState(
        lifecycle=RuntimeLifecycle.STEPPING,
        logical_tick=_SC1_TURNS,
    )
    return P8RunBundle(
        final_state=state,
        runtime_state=runtime_state,
        trace_records=tuple(traces),
        dev_command_ids=(_CMD_PATCH_ID, _CMD_INJECT_ID),
        rule_producer_id=_RULE_PRODUCER,
    )


# —— save 构建面（结构 save；零 P7 依赖）——


def make_p8_backend(tmp_path: Path) -> FilesystemPersistenceBackend:
    """``FilesystemPersistenceBackend(tmp_path / "saves_root")``（SOT §6.2）。"""
    return FilesystemPersistenceBackend(tmp_path / "saves_root")


def build_p8_envelope(run: P8RunBundle) -> PersistenceSnapshot:
    """SC-1 run → P8 信封（``to_persistence_snapshot`` 纯函数；D6 确定性）。

    字面量面（§6.4 同族）：``created_wall_time`` = 固定 ISO 串；
    ``project_version`` / ``module_versions`` 字面量（冗余镜像构造上自嵌套
    一致）；``trace_ref`` = ``"trace.jsonl"``。
    """
    snapshot = Snapshot(
        world_state=run.final_state,
        runtime_state=run.runtime_state,
        world_instance_id=_WSI_SC1,
        created_logical_tick=_SC1_TURNS,
        project_version=_PROJECT_VERSION,
        module_versions=dict(_MODULE_VERSIONS),
    )
    return to_persistence_snapshot(
        snapshot,
        trace_ref="trace.jsonl",
        created_wall_time=_WALL_TIME,
    )


def build_p8_save(tmp_path: Path, run: P8RunBundle) -> Path:
    """SC-1 → 完整 save（``save_id="save_p8_base"``；wall time 固定串——D6）。

    返回 save 目录 ``<tmp_path>/saves_root/saves/save_p8_base``。
    """
    backend = make_p8_backend(tmp_path)
    backend.save(
        save_id=_SAVE_ID_SC1,
        envelope=build_p8_envelope(run),
        checkpoint_payloads={},
        trace_records=run.trace_records,
    )
    return tmp_path / "saves_root" / "saves" / _SAVE_ID_SC1


# —— W4 CLI 缝（跨波次；惰性导入）——


def cli_runner(tmp_path: Path):
    """``argv → (stdout, exit_code)`` 助手（SOT §6.2 devtools 行）。

    体内惰性导入 W4 ``run_devcontrol_cli``（跨波次缝：W4 交付前不顶层
    导入未交付模块——ERR-P7-10 先例同族）；捕获 stdout 后返回
    ``(stdout, exit_code)``。
    """

    def _run(argv: list[str]) -> tuple[str, int]:
        import contextlib
        import io

        from src.engine_v2.devtools.cli import run_devcontrol_cli

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            exit_code = run_devcontrol_cli(argv, base_dir=tmp_path)
        return buffer.getvalue(), exit_code

    return _run
