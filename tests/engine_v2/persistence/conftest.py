"""P8 持久化侧 conftest（SOT §6.2；SC-1 结构世界 + SC-2 动力学 flavor + SC-4 破坏面）。

构件（SOT §6.2 表逐项对应）：

- ``_barrier_isolation``（autouse）：写屏障 opt-in 纪律（P7 gate L113–118
  同形）——测试前后各 ``uninstall_write_barrier()`` 还原全局未武装态；
- ``make_p8_world()`` / ``make_p8_runtime(backend_refs=())``：SC-1 初始
  ``WorldState``（§6.4 字面量 entity id ``"ent_a"`` / ``"ent_b"`` + ``score``
  世界变量）/ ``RuntimeState``（``backend_refs`` 参数化——SC-3 注入
  non-checkpointable ref）；
- ``make_p8_policy()`` / ``make_p8_executor()``：测试侧 authority（通配单规则
  放行 ``devtools.developer`` + ``p8.rule``，P7 gate 同族）+ 执行器
  （handlers = 冻结 ``default_handler_registry()``）；
- ``run_p8_script()``：SC-1 3 回合脚本（§5.1）→ ``P8RunBundle``（模块级
  私有 dataclass）；DEV_INTERVENTION 记录按 §3.7 精确口径合成（T06 波次前
  无 ``devtools.intervention`` 可导入——conftest 零 T06 依赖）；
- ``make_p8_backend(tmp_path)`` / ``build_p8_envelope(run)`` /
  ``build_p8_save(tmp_path, run)`` / ``build_p8_dynamics_save(tmp_path)``：
  save 构建面（SC-1 结构 save / SC-2 P7 动力学 flavor save，§2.7 冻结
  测试侧缝复用）；
- ``corrupt_save(save_dir, kind)``：SC-4 字节级破坏函数（6 kind 闭集，
  AD 族共用——W2/W5 消费）。

纪律：全部 id / wall time / 版本串为**字面量**（§6.4：零随机、零时钟，
D5/D6）；P7 动力学构件经 ``tests.engine_v2.dynamics.conftest`` 冻结缝导入
（§2.7；函数内惰性导入，ERR-P7-10 先例同族）。
"""

from __future__ import annotations

import json
import re
import shutil
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
    LLM_CALL_PAYLOAD_KEYS,
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

    from src.engine_v2.dynamics.toy_rigid import ToyRigidDynamics

__all__ = [
    "P8RunBundle",
    "P8DynamicsSave",
    "make_p8_world",
    "make_p8_runtime",
    "make_p8_policy",
    "make_p8_executor",
    "run_p8_script",
    "make_p8_backend",
    "build_p8_envelope",
    "build_p8_save",
    "build_p8_dynamics_save",
    "corrupt_save",
]

# —— §6.4 钉死字面量（零随机、零时钟）——

_WSI_SC1 = "wsi_p8_sc1"
_WSI_SC2 = "wsi_p8_sc2"
_WALL_TIME = "1970-01-01T00:00:00+00:00"
_SAVE_ID_SC1 = "save_p8_base"
_SAVE_ID_SC2 = "save_p8_dyn"
_PROJECT_VERSION = "1.0.0"
_MODULE_VERSIONS: dict[str, str] = {"core": "84a5d4f"}

_DEV_PRODUCER = "devtools.developer"
_RULE_PRODUCER = "p8.rule"

_CMD_PATCH_ID = "dev-patch-1"
_CMD_INJECT_ID = "dev-inject-1"
_RECORD_PATCH_ID = "trc_00000000000000000000000000000042"
_RECORD_INJECT_ID = "trc_00000000000000000000000000000043"
_RECORD_LLM_CALL_ID = "trc_00000000000000000000000000000044"

_EFFECT_PATCH_ID = "eff_p8_dev_patch_1"
_EFFECT_RULE_MARK_ID = "eff_p8_rule_mark_1"
_EFFECT_INJECT_ID = "eff_p8_dev_inject_1"
_CAUSAL_ROOT_RULE_TURN2 = "rule_p8_turn2"

_SC1_TURNS = 3
_TOY_SEED = 7


@dataclass(frozen=True)
class P8RunBundle:
    """SC-1 3 回合脚本管道结果（conftest 私有载体；SOT §6.2）。

    - ``final_state``：3 笔 committed 事务后的 ``WorldState``
      （``world_revision`` 0→3）；
    - ``runtime_state``：``logical_tick`` = 3（3 回合后读数）；
    - ``trace_records``：全量 trace（dev_intervention ×2 前置各回合级联
      trace；文件序）;
    - ``dev_command_ids``：回 1 / 回 3 的 devtools 命令 id（§6.4 字面量）；
    - ``rule_producer_id``：回 2 测试侧 rule producer（``"p8.rule"``）。
    """

    final_state: WorldState
    runtime_state: RuntimeState
    trace_records: tuple[TraceRecord, ...]
    dev_command_ids: tuple[str, ...]
    rule_producer_id: str


@dataclass(frozen=True)
class P8DynamicsSave:
    """SC-2 save 载体（SOT §6.2：save + registry toy 绑定）。

    - ``save_dir``：``<base>/saves/save_p8_dyn``（含 checkpoint 体
      ``checkpoints/rigid_body.json``，体 = ``toy.checkpoint()``）；
    - ``toy_registry``：backend_id → ``ToyRigidDynamics`` 绑定
      （checkpointable=True；W2 checkpoint 族消费面）。
    """

    save_dir: Path
    toy_registry: "Mapping[str, ToyRigidDynamics]"


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

    ⇒ committed 事务 3 笔、``world_revision`` 0→3、events 3 条；trace 含
    command（DEV_INTERVENTION ×2，host 字面量 record_id）/ authority /
    validation / transaction / domain_event 族。
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

    # —— 回 3：inject_event（通用包裹 core.set_world_variable score→2）——
    pre_revision = state.world_revision
    dev_record_3 = _dev_intervention_record(
        record_id=_RECORD_INJECT_ID,
        command_id=_CMD_INJECT_ID,
        kind="inject_event",
        payload={
            "effect_id": _EFFECT_INJECT_ID,
            "effect_type": "core.set_world_variable",
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


# —— save 构建面 ——


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


def build_p8_dynamics_save(tmp_path: Path) -> P8DynamicsSave:
    """**SC-2**：P7 动力学 flavor save（SOT §6.2；§2.7 冻结测试侧缝复用）。

    P7 gate 同形接线（函数内惰性导入——ERR-P7-10 先例同族；P7 缝为冻结
    交付，零改动）：``make_p7_world`` + scripted wire（``gem.moved``，
    §6.4 同族字面量响应串；wire 钉 ``component_type="gem_state"`` ——
    SOT 钉死的 ``make_p7_executor`` policy 为组件型规则（rigid / gem_state），
    无 component 目标的 effect 命中 default DENY，故钉 ``gem_state`` 目标使
    ``gem.moved`` 经正常管道 committed；§6.4 "同族" 许可此面）+
    ``FakeInferenceBackend(script={
    ("world_dynamics", Revision(0), 1): …})`` + ``run_dynamics_turn`` ⇒
    committed trace 含 ``gem.moved`` 语义 effect；``llm_call`` 记录 host
    合成（冻结 P7 管道不产出 ``TraceKind.LLM_CALL`` 记录，按
    DEV_INTERVENTION 同族口径由 conftest 侧产出，键面 == 核心冻结面
    ``LLM_CALL_PAYLOAD_KEYS``，逐键钉字面量）。

    save 面：``save_id="save_p8_dyn"``；checkpoint 体 = toy 绑定
    （``ToyRigidDynamics(seed=7)``，checkpointable=True）→
    ``checkpoints/rigid_body.json``（体 ``{"version": 1, "seed": 7}``）+
    信封 ref 面 ``{"rigid_body": "checkpoints/rigid_body.json"}``。
    """
    from src.engine_v2.dynamics.backend import (
        DynamicsContext,
        Stimulus,
        WorldSnapshot,
        _FixedMonotonicClock,
    )
    from src.engine_v2.dynamics.host import run_dynamics_turn
    from src.engine_v2.dynamics.llm_world import LLMWorldDynamics, LLMWorldDynamicsConfig
    from src.engine_v2.dynamics.toy_rigid import ToyRigidDynamics
    from src.engine_v2.llm.adapter import FakeInferenceBackend
    from tests.engine_v2.dynamics.conftest import (
        _det_entity_id,
        make_p7_executor,
        make_p7_world,
    )

    world = make_p7_world()
    gem_entity_id = _det_entity_id("gem")
    wire = json.dumps(
        {
            "effects": [
                {
                    "effect_type": "gem.moved",
                    "entity_id": str(gem_entity_id),
                    "component_type": "gem_state",
                    "payload": {},
                }
            ],
            "reasoning": "support removed",
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    fake = FakeInferenceBackend(script={("world_dynamics", Revision(0), 1): wire})
    llm_backend = LLMWorldDynamics(
        backend=fake,
        config=LLMWorldDynamicsConfig(
            capability_id="world_dynamics", prompt_ref="prompt://p8/gem"
        ),
        clock=_FixedMonotonicClock(),
    )
    stim = Stimulus(
        stimulus_id="stim_support_removed",
        kind="external",
        source="anvil",
        entity_id=gem_entity_id,
        payload={"support": "removed"},
    )
    world_snapshot = WorldSnapshot(
        world_state=world,
        world_revision=world.world_revision,
        logical_tick=0,
        world_instance_id=_WSI_SC2,
    )
    turn = run_dynamics_turn(
        backend=llm_backend,
        snapshot=world_snapshot,
        stimuli=(stim,),
        context=DynamicsContext(base_revision=0),
        state=world,
        executor=make_p7_executor(),
        causal_root_id="turn_p8_sc2",
        origin=Provenance(
            producer_id=ProducerId("llm_world_dynamics"),
            origin=OriginKind.DYNAMICS_BACKEND,
        ),
    )

    # —— llm_call 记录（host 合成：冻结 P7 管道不产出 ``TraceKind.LLM_CALL``
    #    记录；K7 零 uuid4 —— 钉死字面量 record_id；键面 == 核心冻结面
    #    ``LLM_CALL_PAYLOAD_KEYS``，逐键钉字面量）——
    llm_call_payload = {
        "logical_role": "world_dynamics",
        "profile": "world_dynamics",
        "resolved_model": "model_high",
        "input_token_estimate": 128,
        "prompt_metadata_ref": "prompt://p8/gem",
        "output_ref": "output://world_dynamics:0:0",
        "latency_ms": 5.0,
        "parse_retry": 0,
        "base_revision": 0,
    }
    assert frozenset(llm_call_payload) == LLM_CALL_PAYLOAD_KEYS
    llm_call_record = TraceRecord(
        record_id=TraceRecordId(_RECORD_LLM_CALL_ID),
        kind=TraceKind.LLM_CALL,
        world_revision=world.world_revision,
        logical_tick=0,
        producer_id=ProducerId("llm_world_dynamics"),
        payload=llm_call_payload,
    )

    # —— toy 绑定（registry 面；checkpoint 体随 save 落盘）——
    toy = ToyRigidDynamics(seed=_TOY_SEED)
    toy_registry: dict[str, ToyRigidDynamics] = {"rigid_body": toy}

    snapshot = Snapshot(
        world_state=turn.result.final_state,
        runtime_state=make_p8_runtime(),
        world_instance_id=_WSI_SC2,
        created_logical_tick=0,
        project_version=_PROJECT_VERSION,
        module_versions=dict(_MODULE_VERSIONS),
    )
    envelope = to_persistence_snapshot(
        snapshot,
        backend_checkpoints={"rigid_body": "checkpoints/rigid_body.json"},
        trace_ref="trace.jsonl",
        created_wall_time=_WALL_TIME,
    )
    backend = make_p8_backend(tmp_path)
    backend.save(
        save_id=_SAVE_ID_SC2,
        envelope=envelope,
        checkpoint_payloads={"rigid_body": toy.checkpoint()},
        trace_records=(llm_call_record, *turn.result.trace_records),
    )
    return P8DynamicsSave(
        save_dir=tmp_path / "saves_root" / "saves" / _SAVE_ID_SC2,
        toy_registry=toy_registry,
    )


# —— SC-4 字节级破坏面（AD 族共用；W2/W5 消费）——


def corrupt_save(save_dir: Path, kind: str) -> None:
    """SC-4 破坏函数（一函数一破坏；kind 6 闭集；其余 → ``ValueError``）。

    - ``truncate_snapshot``：snapshot.json 截断半文（JSON 词法损坏）；
    - ``bad_checkpoint_seed``：checkpoint 体 seed 值类型篡改（数字 → 串）；
    - ``version_zero``：顶层 ``persistence_format_version`` 1 → 0（版本降级）;
    - ``drop_middle_txn``：trace 中间一行删除（回放连续性断裂）；
    - ``bad_trace_line``：trace 第 2 行替换为垃圾串（中间行垃圾）；
    - ``dangling_index``：save 目录整体删除（index 悬空条目）。
    """
    if kind == "truncate_snapshot":
        path = save_dir / "snapshot.json"
        text = path.read_text(encoding="utf-8")
        path.write_text(text[: max(1, len(text) // 2)], encoding="utf-8")
    elif kind == "bad_checkpoint_seed":
        checkpoint_dir = save_dir / "checkpoints"
        files = sorted(checkpoint_dir.glob("*.json"))
        if not files:
            raise ValueError(
                f"corrupt_save(bad_checkpoint_seed) 需 SC-2 save（含 checkpoint 体）：{save_dir}"
            )
        text = files[0].read_text(encoding="utf-8")
        corrupted = re.sub(r'"seed"\s*:\s*-?\d+', '"seed": "corrupt"', text, count=1)
        if corrupted == text:
            raise ValueError(f"corrupt_save(bad_checkpoint_seed) 未找到 seed 数值：{files[0]}")
        files[0].write_text(corrupted, encoding="utf-8")
    elif kind == "version_zero":
        from src.engine_v2.persistence.base import PERSISTENCE_FORMAT_VERSION

        path = save_dir / "snapshot.json"
        text = path.read_text(encoding="utf-8")
        marker = f'"persistence_format_version": {PERSISTENCE_FORMAT_VERSION}'
        if marker not in text:
            raise ValueError("corrupt_save(version_zero) 未找到顶层版本字段")
        path.write_text(
            text.replace(marker, '"persistence_format_version": 0', 1), encoding="utf-8"
        )
    elif kind == "drop_middle_txn":
        path = save_dir / "trace.jsonl"
        lines = path.read_text(encoding="utf-8").splitlines()
        if len(lines) < 3:
            raise ValueError("corrupt_save(drop_middle_txn) 需 ≥3 行 trace")
        del lines[len(lines) // 2]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    elif kind == "bad_trace_line":
        path = save_dir / "trace.jsonl"
        lines = path.read_text(encoding="utf-8").splitlines()
        if len(lines) < 2:
            raise ValueError("corrupt_save(bad_trace_line) 需 ≥2 行 trace")
        lines[1] = "{not valid json"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    elif kind == "dangling_index":
        shutil.rmtree(save_dir)
    else:
        raise ValueError(f"corrupt_save kind {kind!r} 不在 6 闭集")
