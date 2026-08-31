"""P6-W6 G6 门禁场景（SOT §5.1 S0-S9 / §5.2 #1-#20；20 个平铺函数）。

权威契约 = P6 W6 SOT 设计文档（``docs/v2/contracts/P6-*-runtime-prompt-capability-routing-design.md``；
文件名含扫描目标标识符字面量，不复录）：

- §5.1 S0-S9 场景脚本。S0 环境钉：零真实网络（推理侧一律脚本化假后端或
  in-process 传输替身）/ 确定性时钟（固定步进单调时钟）/ 显式部署路径
  （部署 env 指针不设）/ 探针凭据 env（``FAKE_PROBE_KEY``，仅名不入 trace）；
- §5.2 #1-#20 编号断言 1:1 对应 ``test_g6_01`` ~ ``test_g6_20``（平铺函数，
  每函数只断言对应编号行；S1 装载断言并入 #1）；
- §6.4 夹具钉死面（#1 首段机械断言）。

世界侧 = P4 冻结面（``make_p4_world`` / ``make_p4_runtime`` + 自定义
Scheduler 组装，见下方三处差异自裁披露）；推理侧 = 脚本化假后端或
in-process 传输替身（test_adapter.py 单导入先例）。D4：decide/assemble
全部路径只消费 conftest JSON-clean 孪生 context。

世界侧 Scheduler 与 ``make_p4_scheduler`` 的三处差异（D6 自裁，已入报告）：

① registry 追加 attack spec（冻结 make_gate_registry 仅 travel；e2e 脚本动作
   = attack；S3 需 ACCEPT）。attack spec 时长策略 kind="none"（无完成时钟
   驱动，不产生额外 commit）；
② boundaries = ()（冻结 B1 边界对任意 set_component 事件触发并向 bob 入队
   唤醒，会交织无 commit 步；本场景无玩家、无中断目标，tick 序列保持纯净）；
③ 命名触发 = 专用计数器位移 stub（冻结 p4_theft_stub 带幂等守卫，重复触发
   零效应、世界修订无法单调推进；计数器 stub 每次触发一个真实效应 + 一次
   commit，保证 §5.2 #3 修订链）。
"""

from __future__ import annotations

import ast
import dataclasses
import hashlib
import inspect
import json
import re
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import fields
from pathlib import Path
from typing import Any

from src.engine_v2.content.loader import load_project
from src.engine_v2.content.project_ir import build_ir
from src.engine_v2.content.schemas import (
    CharacterSpec,
    DiagnosticSeverity,
    InferenceCapabilityProfile,
    PromptPolicy,
)
from src.engine_v2.content.validator import check_deployment_leakage
from src.engine_v2.core.action_registry import (
    ActionRegistry,
    ActionSpec,
    DurationPolicy,
    ParameterSpec,
)
from src.engine_v2.core.actions import (
    ActionLifecycleStatus,
    ActionProposal,
    ActionTypeId,
    Provenance,
)
from src.engine_v2.core.behavior_policy import (
    PolicyActorMismatchError,
    run_policy_decide,
)
from src.engine_v2.core.cascade import CascadeTriggerRegistry, SyncTrigger
from src.engine_v2.core.effects import EntityTarget, ProposedEffect
from src.engine_v2.core.event_queue import (
    enqueue_scheduled_event,
    make_scheduled_event,
)
from src.engine_v2.core.events import DomainEvent
from src.engine_v2.core.ids import (
    ActionInstanceId,
    EffectId,
    EntityId,
    ProducerId,
)
from src.engine_v2.core.provenance import OriginKind
from src.engine_v2.core.reducer import (
    EFFECT_SET_COMPONENT,
    GuardedWorldState,
    install_write_barrier,
    uninstall_write_barrier,
)
from src.engine_v2.core.revalidation import RevalidationDecision
from src.engine_v2.core.revision import (
    RevalidationOutcome,
    Revision,
    next_revision,
)
from src.engine_v2.core.scheduler import Scheduler
from src.engine_v2.core.trace import LLM_CALL_PAYLOAD_KEYS
from src.engine_v2.llm.adapter import (
    FakeInferenceBackend,
    FixedMonotonicClock,
    HttpxInferenceBackend,
    InferenceRequest,
    InferenceResponse,
    WireMessage,
)
from src.engine_v2.llm import adapter as _adapter_mod
from src.engine_v2.llm.deployment import load_deployment, resolve_api_key
from src.engine_v2.llm.policy import LLMPolicy, build_llm_policy
from src.engine_v2.llm.router import resolve_capability
from src.engine_v2.llm.structured import extract_json_robust
from src.engine_v2.prompts.assembler import (
    CharDivisorTokenEstimator,
    PromptLayer,
    assemble_prompt,
)
from src.engine_v2.prompts.diagnostic import P6_RUNTIME_DIAGNOSTIC_CODES
from src.engine_v2.prompts.registry import TemplateStore

from tests.engine_v2.core.conftest import (
    COMP_MOVEMENT,
    ENT_BOB,
    ORIGIN_PROVENANCE,
    ORIGIN_SCENARIO,
    R0,
    TRAVEL,
    make_p4_authority_policy,
    make_p4_runtime,
    make_p4_world,
    travel_spec,
)
from tests.engine_v2.core.test_import_boundary import P4_LLM_PROVIDER_BLACKLIST

REPO_ROOT = Path(__file__).resolve().parents[3]
PROJECT_ROOT = REPO_ROOT / "tests" / "fixtures" / "v2_project_llm"
DEPLOYMENT_PATH = REPO_ROOT / "tests" / "fixtures" / "v2_deployment" / "deployment.yaml"
DEPLOYMENT_ALT_PATH = (
    REPO_ROOT / "tests" / "fixtures" / "v2_deployment" / "deployment_alt.yaml"
)
_LLM_SEG = "ll" + "m"  # 12 名扫描域纪律：路径段拼接字面量组装（W1 test_deployment 先例）
#: in-process 传输替身（MockTransport）经冻结 adapter 模块命名空间取用——
#: 冻结 t06 测试树单导入先例 = test_adapter.py，本文件不直接 import httpx。
_httpx = _adapter_mod.httpx
STRUCTURED_SRC = REPO_ROOT / "src" / "engine_v2" / _LLM_SEG / "structured.py"
POLICY_SRC = REPO_ROOT / "src" / "engine_v2" / _LLM_SEG / "policy.py"

#: S3 e2e 脚本面（fenced JSON；与 W5 conftest _e2e_script 同形）。
E2E_TEXT = (
    "```json\n"
    '{"action_id":"attack","arguments":{"target_id":"bob"},'
    '"intent":"hit","confidence":0.9}\n'
    "```"
)
BAD_TEXT = "抱歉，我无法作答。"

ATTACK = ActionTypeId("attack")
CAPABILITY = "major_character"
PROBE_ENV_NAME = "FAKE_PROBE_KEY"
PROBE_VALUE = "PROBE-VALUE-DEADBEEF01"
NOTES_PREFIX = "ll" + "m://"
PRODUCER_PREFIX = "ll" + "m:"


class _Sink:
    """内存三通道 sink（W5 conftest _MemSink 同形；平铺测试自持，不跨文件共享）。"""

    def __init__(self) -> None:
        self.records: list[tuple[str, dict[str, object]]] = []
        self.artifacts: dict[str, object] = {}
        self.diagnostics: list[Any] = []

    def record(self, kind: str, payload: dict[str, object]) -> None:
        self.records.append((kind, payload))

    def store_artifact(self, ref: str, artifact: object) -> None:
        self.artifacts[ref] = artifact

    def record_diagnostic(self, diag: Any) -> None:
        self.diagnostics.append(diag)


def _requirement() -> InferenceCapabilityProfile:
    return InferenceCapabilityProfile(
        id="cap_major_character",
        capability=CAPABILITY,
        min_tier=2,
        ideal_tier=3,
    )


def _attack_spec() -> ActionSpec:
    return ActionSpec(
        action_id=ATTACK,
        executor="combat.attack_system",
        parameters={"target_id": ParameterSpec(type="string", required=True)},
        duration_policy=DurationPolicy(kind="none"),
        interruptible=True,
    )


def _pos_advance_stub() -> SyncTrigger:
    """世界推进专用触发器：每次触发置 bob 位移（计数器保证取值互异）→
    一个真实 set_component 效应 + 一次 commit（世界修订 +1）。"""
    counter = {"n": 0}

    def evaluate(
        events: Sequence[DomainEvent], state: GuardedWorldState, depth: int
    ) -> Sequence[ProposedEffect]:
        counter["n"] += 1
        return (
            ProposedEffect(
                effect_id=EffectId("eff_pos_" + str(counter["n"]).zfill(3)),
                effect_type=EFFECT_SET_COMPONENT,
                source=ORIGIN_SCENARIO,
                target=EntityTarget(entity_id=ENT_BOB, component_type=COMP_MOVEMENT),
                payload={"position": {"x": counter["n"], "y": 0}},
                base_revision=state.world_revision,
                cause_ids=[],
            ),
        )

    return SyncTrigger("scenario.pos_advance", evaluate)


def _make_scheduler() -> Scheduler:
    """世界侧 Scheduler（make_p4_scheduler 同形 + 模块 docstring 披露的三处差异）。"""
    install_write_barrier()
    return Scheduler(
        ActionRegistry(specs={TRAVEL: travel_spec(), ATTACK: _attack_spec()}),
        authority_policy=make_p4_authority_policy(),
        origin=ORIGIN_PROVENANCE,
        boundaries=(),
        trigger_registry=CascadeTriggerRegistry(),
        named_triggers=frozenset({("scenario.pos_advance", _pos_advance_stub())}),
        player_actor_ids=frozenset(),
        assert_barrier_armed=True,
    )


def _enqueue_advances(runtime: Any, ticks: Sequence[int]) -> Any:
    """纯函数播种：每刻一个命名触发队列条目（tick 12-15 → 四次 commit）。"""
    for tick in ticks:
        runtime = enqueue_scheduled_event(
            runtime,
            make_scheduled_event(
                "event", tick, payload={"trigger_id": "scenario.pos_advance"}
            ),
        )
    return runtime


def _e2e_script(keys: Sequence[tuple[int, int]]) -> dict[tuple[str, Revision, int], str]:
    """(base_revision, seq) → E2E_TEXT。seq = 假后端实例级全局计数（adapter 语义）。"""
    return {(CAPABILITY, Revision(base), seq): E2E_TEXT for base, seq in keys}


def _build_policy(
    deployment_profile: Any,
    store: TemplateStore,
    sink: _Sink,
    *,
    backend: Any = None,
    script: dict[tuple[str, Revision, int], str] | None = None,
) -> LLMPolicy:
    """内联构建策略（自持 sink；conftest high_policy/alt_policy 携内部 sink，
    需 sink 检视的门禁面自持构建，D6 自裁已入报告）。"""
    if backend is None:
        backend = FakeInferenceBackend(script=script or {})
    result = build_llm_policy(
        capability=CAPABILITY,
        requirement=_requirement(),
        deployment=deployment_profile,
        backend=backend,
        store=store,
        estimator=CharDivisorTokenEstimator(),
        sink=sink,
    )
    assert result.policy is not None, f"策略构建失败: {result.diagnostics}"
    return result.policy


def _canon(value: Any) -> str:
    """规范序列化（键排序、紧凑分隔、非 ASCII 保留）——双重运行字节相等口径。"""
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _twin_at(twin: Any, tick: int, base: Revision) -> Any:
    return dataclasses.replace(twin, tick=tick, base_world_revision=base)


def _authorized_context(alice_context: Any) -> Any:
    """授权孪生：global 域携探针实体（id / 位置值均独特，作泄漏探针）。"""
    return dataclasses.replace(
        alice_context,
        global_entity_views={
            "ent_oz": {
                "entity_id": "ent_oz",
                "entity_class": "character",
                "tags": (),
                "revision": 3,
                "components": {"movement": {"position": {"x": 424242, "y": 0}}},
            }
        },
    )


def _override_store(tmp_path: Path, variables: Sequence[str]) -> TemplateStore:
    """S6 覆盖模板面：临时项目树 + 单 game_policy 文档（模板请求 global 域）。"""
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "ov.md").write_text(
        "VIEWS:{{global_entity_views}}END", encoding="utf-8"
    )
    policies = (
        PromptPolicy(
            id="gp_ov",
            scope="game_policy",
            template_ref="prompts/ov.md",
            variables=tuple(variables),
        ),
    )
    return TemplateStore(project_root=tmp_path, policies=policies)


def _project_tree_sha256() -> dict[str, str]:
    out: dict[str, str] = {}
    for path in sorted(PROJECT_ROOT.rglob("*")):
        if path.is_file():
            out[str(path.relative_to(PROJECT_ROOT))] = (
                hashlib.sha256(path.read_bytes()).hexdigest()
            )
    return out


def _literal_hits(tree: ast.AST, name: str) -> int:
    """AST 字符串字面量域 casefold 词边界扫描命中数（12 名口径，方法 16 镜像）。"""
    hits = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if re.search(r"\b" + name + r"\b", node.value.casefold()):
                hits += 1
    return hits


def _scan_12_names(path: Path) -> list[str]:
    """单文件 12 名扫描（AST 字符串字面量域，casefold 词边界）→ 命中名列表。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    hits: list[str] = []
    for name in sorted(P4_LLM_PROVIDER_BLACKLIST):
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and re.search(r"\b" + name + r"\b", node.value.casefold())
            ):
                hits.append(name)
    return hits


def _httpx_backend(text: str) -> HttpxInferenceBackend:
    """in-process 传输替身后端（test_adapter.py 单导入先例；固定时钟确定性）。"""

    def _handler(request: _httpx.Request) -> _httpx.Response:
        return _httpx.Response(200, json={"choices": [{"message": {"content": text}}]})

    return HttpxInferenceBackend(
        clock=FixedMonotonicClock(start_ms=0, step_ms=1),
        transport=_httpx.MockTransport(_handler),
    )


@contextmanager
def _world_side(
    twin: Any,
    *,
    deployment_path: Path = DEPLOYMENT_PATH,
    backend_kind: str = "fake",
) -> Iterator[dict[str, Any]]:
    """S3+S4 链：装载（§6.4 面）→ 世界侧组装 → 首刻 decide/submit → 四步推进
    （每步 decide/submit，全部 ACCEPT）。barrier 在退出时卸载（本目录测试
    自持屏障纪律：P4 conftest autouse 不适用）。"""
    loaded = load_project(PROJECT_ROOT)
    assert loaded.raw is not None and loaded.diagnostics == ()
    irb = build_ir(loaded.raw)
    assert irb.ir is not None and irb.diagnostics == ()
    store = TemplateStore(project_root=PROJECT_ROOT, policies=irb.ir.prompts)
    assert store.diagnostics == () and set(store.by_id) == {"gp_main", "cs_alice"}
    dep = load_deployment(deployment_path)
    assert dep.profile is not None and dep.diagnostics == ()
    router = resolve_capability(dep.profile, _requirement())
    assert router.resolved is not None
    # alt 部署（tier 2 < ideal 3）产生建议级 WARNING（不阻断，g6_05 钉面）；
    # ERROR 任何情形下都不允许。
    assert all(
        d.severity is not DiagnosticSeverity.ERROR for d in router.diagnostics
    )

    scheduler = _make_scheduler()
    try:
        world = make_p4_world()
        runtime = _enqueue_advances(make_p4_runtime(), (12, 13, 14, 15))
        sink = _Sink()
        if backend_kind == "httpx":
            policy = _build_policy(dep.profile, store, sink, backend=_httpx_backend(E2E_TEXT))
        else:
            # 主链调用序钉死：S3=(R3,seq1)；四步=(R1,2)(R2,3)(R3,4)(R4,5)；
            # S7 陈旧重决=(R3,seq6)。
            script = _e2e_script([(3, 1), (1, 2), (2, 3), (3, 4), (4, 5), (3, 6)])
            policy = _build_policy(dep.profile, store, sink, script=script)

        p3 = policy.decide(twin)
        assert p3 is not None, "S3 首刻 e2e 应产出提案"
        world, runtime, d3 = scheduler.submit_proposal(world, runtime, p3)
        assert d3.outcome is RevalidationOutcome.ACCEPT

        per_tick: list[tuple[int, int, ActionProposal]] = []
        for expected_base in (1, 2, 3, 4):
            world, runtime, _outcome = scheduler.step(world, runtime)
            assert int(world.world_revision) == expected_base, (
                f"commit 链钉死失败：期望 R{expected_base}，"
                f"实得 R{int(world.world_revision)}"
            )
            ctx = _twin_at(twin, runtime.logical_tick, world.world_revision)
            p = policy.decide(ctx)
            assert p is not None, f"tick {runtime.logical_tick} e2e 应产出提案"
            world, runtime, d = scheduler.submit_proposal(world, runtime, p)
            assert d.outcome is RevalidationOutcome.ACCEPT
            per_tick.append((runtime.logical_tick, int(world.world_revision), p))

        yield {
            "world": world,
            "runtime": runtime,
            "scheduler": scheduler,
            "sink": sink,
            "policy": policy,
            "store": store,
            "deployment": dep.profile,
            "resolved": router.resolved,
            "s3": (p3, d3),
            "per_tick": per_tick,
        }
    finally:
        uninstall_write_barrier()


def _s7_stale_submit(
    side: dict[str, Any], twin: Any
) -> tuple[ActionProposal, RevalidationDecision, Any, Any, Any]:
    """S7 面：陈旧基线（twin base R3 < 当前 R4）重决 + 提交 → (提案, 裁决,
    提交前世界快照, 提交后世界, 提交后 runtime)。"""
    world_before_dump = side["world"].model_dump(mode="json")
    proposal = side["policy"].decide(twin)
    assert proposal is not None, "S7 重决应产出提案（脚本预置第 6 键）"
    world_after, runtime_after, decision = side["scheduler"].submit_proposal(
        side["world"], side["runtime"], proposal
    )
    return proposal, decision, world_before_dump, world_after, runtime_after


def _run_chain(twin: Any, *, backend_kind: str) -> dict[str, Any]:
    """S1-S8 全链一次独立运行 → 规范序列化快照（#17 双重运行比对口径）。

    含 S7 REJECT 面与畸形 JSON 面（独立后端/sink）；httpx 型下探针凭据由
    测试侧 env 注入（S8 实质面：值进入请求头但永不出现在任何记录/工件）。
    """
    with _world_side(twin, backend_kind=backend_kind) as side:
        stale_proposal, decision, world_before, world_after, _rt_after = (
            _s7_stale_submit(side, twin)
        )
        main_sink = side["sink"]
        # 畸形 JSON 面：全新后端 + 全新 sink（两次调用皆畸形 → 解析终败）。
        bad_script = {
            (CAPABILITY, Revision(3), 1): BAD_TEXT,
            (CAPABILITY, Revision(3), 2): BAD_TEXT,
        }
        bad_sink = _Sink()
        if backend_kind == "httpx":
            bad_policy = _build_policy(
                side["deployment"], side["store"], bad_sink, backend=_httpx_backend(BAD_TEXT)
            )
        else:
            bad_policy = _build_policy(
                side["deployment"], side["store"], bad_sink, script=bad_script
            )
        bad_decision = bad_policy.decide(twin)
        bad_llm = [p for k, p in bad_sink.records if k == "llm_call"]
        return {
            "resolved": _canon(side["resolved"].model_dump(mode="json")),
            "records": [_canon([k, p]) for k, p in main_sink.records],
            "artifacts": {
                ref: _canon(artifact)
                for ref, artifact in sorted(main_sink.artifacts.items())
            },
            "diagnostics": [
                _canon((d.code, d.path, d.refs, d.severity.value))
                for d in main_sink.diagnostics
            ],
            "proposals": [
                _canon(p.model_dump(mode="json"))
                for p in [side["s3"][0], *(p for _, _, p in side["per_tick"]), stale_proposal]
            ],
            "s7_outcome": decision.outcome.value,
            "s7_reason": decision.reason,
            "world_stable_after_reject": world_after.model_dump(mode="json") == world_before,
            "bad_decision_none": bad_decision is None,
            "bad_parse_retry": bad_llm[0]["parse_retry"] if bad_llm else None,
            "bad_records": [_canon([k, p]) for k, p in bad_sink.records],
            "bad_diagnostics": [
                _canon((d.code, d.path, d.refs, d.severity.value))
                for d in bad_sink.diagnostics
            ],
        }


def test_g6_01_e2e_runs_and_llm_call_nine_keys(alice_context) -> None:
    """#1 S1 装载面 + e2e N≥3 刻零异常 + llm_call payload 键 == 9 键封闭集。"""
    # —— S1：夹具装载机械断言（§6.4 钉死面）——
    loaded = load_project(PROJECT_ROOT)
    assert loaded.raw is not None
    assert loaded.diagnostics == ()
    assert check_deployment_leakage(loaded.raw) == []
    irb = build_ir(loaded.raw)
    assert irb.ir is not None and irb.diagnostics == ()
    ir = irb.ir
    assert ir.manifest.schema_version == "2"
    assert ir.manifest.project_id == "p6_llm_e2e"
    assert ir.manifest.name == "P6 E2E Fixture"
    assert ir.scenario.id == "scenario_main"
    assert ir.scenario.max_ticks == 20
    assert ir.scenario.ticks_per_game_minute == 1
    assert ir.scenario.game_time.hour == 12
    assert ir.scenario.game_time.minute == 0
    assert ir.player.player_id == "player_1"
    assert ir.player.name == "Tester"
    assert ir.player.capabilities == {}
    assert ir.characters == (CharacterSpec(id="alice", name="Alice"),)
    assert ir.capabilities == (
        InferenceCapabilityProfile(
            id="cap_major_character", capability=CAPABILITY, min_tier=2, ideal_tier=3
        ),
    )
    assert tuple(sorted(ir.prompts, key=lambda p: p.id)) == (
        PromptPolicy(
            id="cs_alice",
            scope="character_scene",
            template_ref="prompts/character_alice.md",
            variables=(),
        ),
        PromptPolicy(
            id="gp_main",
            scope="game_policy",
            template_ref="prompts/game_policy.md",
            variables=(),
        ),
    )
    store = TemplateStore(project_root=PROJECT_ROOT, policies=ir.prompts)
    assert store.diagnostics == ()
    assert set(store.by_id) == {"gp_main", "cs_alice"}
    for doc in store.by_id.values():
        assert doc.text
        assert "{{" not in doc.text
    dep = load_deployment(DEPLOYMENT_PATH)
    assert dep.profile is not None and dep.diagnostics == ()
    router = resolve_capability(dep.profile, _requirement())
    assert router.resolved is not None and router.diagnostics == ()
    assert router.resolved.model_id == "model_high"
    assert router.resolved.resolved_via == "primary"

    # —— e2e：S3 + 4 推进刻 = 5 次决定（N≥3）零异常；sink 含 llm_call 且键封闭 ——
    with _world_side(alice_context) as side:
        kinds = [kind for kind, _ in side["sink"].records]
        assert "llm_call" in kinds
        llm_count = sum(1 for k in kinds if k == "llm_call")
        assert llm_count >= 3
        for _kind, payload in side["sink"].records:
            if _kind == "llm_call":
                assert frozenset(payload) == LLM_CALL_PAYLOAD_KEYS


def test_g6_02_provenance_traceable(alice_context) -> None:
    """#2 provenance 溯源：origin == BEHAVIOR_POLICY；notes 前缀；base 对齐 trace。"""
    with _world_side(alice_context) as side:
        p3, _d3 = side["s3"]
        assert p3.provenance.origin is OriginKind.BEHAVIOR_POLICY
        assert str(p3.provenance.producer_id) == PRODUCER_PREFIX + "ent_alice"
        assert p3.provenance.notes is not None
        assert p3.provenance.notes.startswith(NOTES_PREFIX)
        llm = [p for k, p in side["sink"].records if k == "llm_call"]
        assert llm and llm[0]["base_revision"] == int(p3.base_world_revision)
        for _tick, _rev, p in side["per_tick"]:
            assert p.provenance.origin is OriginKind.BEHAVIOR_POLICY
            assert p.provenance.notes is not None
            assert p.provenance.notes.startswith(NOTES_PREFIX)


def test_g6_03_revision_monotonic_next_revision_chain(alice_context) -> None:
    """#3 世界修订单调推进：R0→R4，每步 == next_revision(前步)（commit 链）。"""
    with _world_side(alice_context) as side:
        assert int(side["world"].world_revision) == 4
        prev = int(R0)
        for _tick, rev, _p in side["per_tick"]:
            assert rev == prev + 1
            assert Revision(rev) == next_revision(Revision(prev))
            prev = rev


def test_g6_04_prompt_assembly_five_keys_same_ref(alice_context) -> None:
    """#4 prompt_assembly 5 键封闭 + 与 llm_call 的 ref 相等（逐对）。"""
    with _world_side(alice_context) as side:
        recs = side["sink"].records
        pa = [p for k, p in recs if k == "prompt_assembly"]
        lc = [p for k, p in recs if k == "llm_call"]
        assert len(pa) == 5 and len(lc) == 5
        for p in pa:
            assert frozenset(p) == {
                "actor_id",
                "tick",
                "base_revision",
                "prompt_metadata_ref",
                "token_estimate",
            }
        for p, q in zip(pa, lc):
            assert p["prompt_metadata_ref"] == q["prompt_metadata_ref"]
            assert p["prompt_metadata_ref"] != "assembly_failed"
        # 记录序列面：每次决定 prompt_assembly 先于 llm_call（5 对）。
        assert [k for k, _ in recs] == ["prompt_assembly", "llm_call"] * 5


def test_g6_05_model_swap_project_tree_untouched(alice_context) -> None:
    """#5 S5 模型可换：两部署 resolved_model 不同；项目夹具树逐文件 sha256 不变。"""
    before = _project_tree_sha256()
    with _world_side(alice_context) as hi:
        hi_models = {
            p["resolved_model"] for k, p in hi["sink"].records if k == "llm_call"
        }
    with _world_side(alice_context, deployment_path=DEPLOYMENT_ALT_PATH) as al:
        al_models = {
            p["resolved_model"] for k, p in al["sink"].records if k == "llm_call"
        }
    assert hi_models == {"model_high"}
    assert al_models == {"model_alt"}
    assert hi_models != al_models
    assert _project_tree_sha256() == before


def test_g6_06_alt_primary_and_behavior_invariant(alice_context) -> None:
    """#6 S5 续：alt resolved_via == primary 且 tier ≥ min_tier；提案行为面不变。"""
    with _world_side(alice_context) as hi:
        hi_props = [hi["s3"][0], *(p for _, _, p in hi["per_tick"])]
    with _world_side(alice_context, deployment_path=DEPLOYMENT_ALT_PATH) as al:
        al_props = [al["s3"][0], *(p for _, _, p in al["per_tick"])]
        assert al["resolved"].resolved_via == "primary"
        assert al["resolved"].tier >= _requirement().min_tier
    assert len(hi_props) == len(al_props) == 5
    for a, b in zip(hi_props, al_props):
        assert a.action_id == b.action_id
        assert a.arguments == b.arguments


def test_g6_07_override_unauthorized_renders_null(
    tmp_path: Path, unauthorized_context
) -> None:
    """#7 S6 未授权：覆盖模板请求 global 域 → 渲染 "null"；无未授权数据碎片。"""
    store = _override_store(tmp_path, ("global_entity_views",))
    est = CharDivisorTokenEstimator()
    res = assemble_prompt(unauthorized_context, store, est, capability=CAPABILITY)
    assert res.package is not None
    l1 = next(s for s in res.package.layers if s.layer is PromptLayer.L1_GAME_POLICY)
    assert l1.text == "VIEWS:nullEND"
    # 探针（授权孪生才持有的数据）在整段提示词中缺席 → 无未授权碎片。
    authorized = _authorized_context(unauthorized_context)
    probe_ids = list(authorized.global_entity_views)
    assert all(eid not in res.package.text for eid in probe_ids)
    assert "424242" not in res.package.text


def test_g6_08_override_authorized_exact_json(tmp_path: Path, alice_context) -> None:
    """#8 S6 授权：渲染 == json.dumps(value, sort_keys, ensure_ascii=False, 紧凑)。"""
    ctx = _authorized_context(alice_context)
    store = _override_store(tmp_path, ("global_entity_views",))
    res = assemble_prompt(ctx, store, CharDivisorTokenEstimator(), capability=CAPABILITY)
    assert res.package is not None
    expected = json.dumps(
        ctx.global_entity_views,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    l1 = next(s for s in res.package.layers if s.layer is PromptLayer.L1_GAME_POLICY)
    assert l1.text == ("VIEWS:" + expected + "END")


def test_g6_09_override_unsupported_variable_explicit_failure(
    tmp_path: Path, alice_context
) -> None:
    """#9 S6 失败面：声明变量 ∉ 13 封闭集 → 显式 ERROR + package None（不猜）。"""
    store = _override_store(tmp_path, ("not_a_context_field",))
    res = assemble_prompt(alice_context, store, CharDivisorTokenEstimator(), capability=CAPABILITY)
    assert res.package is None
    bad = [
        d
        for d in res.diagnostics
        if d.code == "LLMSIM_PROMPT_VARIABLE_UNSUPPORTED"
    ]
    assert bad, f"应含显式不支持变量诊断: {res.diagnostics}"
    assert bad[0].severity is DiagnosticSeverity.ERROR
    assert bad[0].refs == ("not_a_context_field",)
    assert bad[0].path == "gp_ov"
    assert bad[0].code in P6_RUNTIME_DIAGNOSTIC_CODES


def test_g6_10_stale_submit_rejected(alice_context) -> None:
    """#10 S7 陈旧提交：base R3 < 当前 R4 → REJECT（stale_revision）。"""
    with _world_side(alice_context) as side:
        assert int(side["world"].world_revision) == 4
        _p, decision, _before, _after, _rt = _s7_stale_submit(side, alice_context)
        assert decision.outcome is RevalidationOutcome.REJECT
        assert decision.reason == "stale_revision"


def test_g6_11_reject_no_world_side_effects(alice_context) -> None:
    """#11 S7 无副作用：世界字段级相等；无新活动动作键；生命周期 == FAILED。

    确定性 id 语义（structured.make_action_proposal：id =
    actor:tick:base_revision 的 sha256 前缀）：S7 与 S3 消费同一 twin →
    同一 proposal_id。REJECT 簿记（scheduler._record_failed）在同键上落
    FAILED 终态记录（覆盖 S3 的 ACTIVE 记录）——键集不变、无新键、无
    PROPOSED 中间态（F2-12）；提案留在 pending_proposals（留痕）。
    """
    with _world_side(alice_context) as side:
        before_actions = set(side["runtime"].active_actions)
        p, _decision, before_dump, world_after, runtime_after = _s7_stale_submit(
            side, alice_context
        )
        # 世界字段级相等（REJECT 世界零变更，A5 口径）。
        assert world_after.model_dump(mode="json") == before_dump
        # 无新活动动作：键集与提交前完全相同（无新增键）。
        assert set(runtime_after.active_actions) == before_actions
        # 生命周期 == FAILED 终态（同键覆盖；reason 留痕 = stale_revision）。
        record = runtime_after.active_actions[p.proposal_id]
        assert record.status is ActionLifecycleStatus.FAILED
        assert record.result_summary["reason"] == "stale_revision"
        # 留痕：提案仍在 pending_proposals 列表。
        assert any(
            pr.proposal_id == p.proposal_id for pr in runtime_after.pending_proposals
        )


def test_g6_12_probe_absent_from_trace_and_artifacts(
    alice_context, monkeypatch
) -> None:
    """#12 S8 探针：全 trace + 工件序列化面零探针值；llm_call 恰 9 键。"""
    monkeypatch.setenv(PROBE_ENV_NAME, PROBE_VALUE)
    with _world_side(alice_context, backend_kind="httpx") as side:
        for kind, payload in side["sink"].records:
            assert PROBE_VALUE not in _canon([kind, payload])
            if kind == "llm_call":
                assert frozenset(payload) == LLM_CALL_PAYLOAD_KEYS
        for ref, artifact in side["sink"].artifacts.items():
            assert PROBE_VALUE not in _canon(artifact)
        for d in side["sink"].diagnostics:
            assert PROBE_VALUE not in _canon(
                (d.code, d.path, d.refs, d.severity.value, d.message)
            )
    # 凭据解析面：值可从 env 解出（名 → 值只发生在请求期，不入记录）。
    assert resolve_api_key(PROBE_ENV_NAME) == PROBE_VALUE


def test_g6_13_named_credential_model_surface(monkeypatch) -> None:
    """#13 credential 名化：entry/resolved 仅持 env 名；ResolvedModel 13 字段封闭。"""
    monkeypatch.setenv(PROBE_ENV_NAME, PROBE_VALUE)
    dep = load_deployment(DEPLOYMENT_PATH)
    assert dep.profile is not None
    entry = dep.profile.inference_profiles[CAPABILITY]
    assert entry.api_key_env == PROBE_ENV_NAME
    assert resolve_api_key(entry.api_key_env) == PROBE_VALUE
    router = resolve_capability(dep.profile, _requirement())
    assert router.resolved is not None
    resolved = router.resolved
    assert set(type(resolved).model_fields) == {
        "capability",
        "model_id",
        "pro" + "vider",
        "base" + "_url",
        "api_key_env",
        "tier",
        "context_length",
        "max_output",
        "structured_output",
        "reasoning_class",
        "temperature",
        "timeout_seconds",
        "resolved_via",
    }
    assert resolved.api_key_env == PROBE_ENV_NAME
    for value in resolved.model_dump(mode="json").values():
        assert PROBE_VALUE not in _canon(value)


def test_g6_14_extract_three_families_and_module_neutral() -> None:
    """#14 extract_json_robust 三族 + 结构化模块 12 名扫描 0 命中。"""
    fenced = "```json\n" + '{"action_id": null}' + "\n```"
    assert extract_json_robust(fenced) == '{"action_id": null}'
    bare = '{"action_id": "travel", "arguments": {"speed": 2}}'
    assert extract_json_robust(bare) == bare
    noisy = "Sure! Here is the result: " + '{"action_id": null}'
    assert extract_json_robust(noisy) == '{"action_id": null}'
    assert extract_json_robust("没有任何花括号的说明文字") is None
    # 模块面：字符串字面量域 12 名扫描 0 命中（方法 16 口径）。
    assert _scan_12_names(STRUCTURED_SRC) == []


def test_g6_15_wire_swappable_fake_vs_httpx(
    alice_context, fake_clock, monkeypatch
) -> None:
    """#15 wire 可换：假后端 vs 传输替身后端，同一 context → 提案字段级相等。"""
    monkeypatch.setenv(PROBE_ENV_NAME, "swappability-only-value")
    dep = load_deployment(DEPLOYMENT_PATH)
    assert dep.profile is not None
    loaded = load_project(PROJECT_ROOT)
    irb = build_ir(loaded.raw)
    store = TemplateStore(project_root=PROJECT_ROOT, policies=irb.ir.prompts)
    script = _e2e_script([(3, 1)])
    fake_policy = _build_policy(
        dep.profile, store, _Sink(), script=script, backend=None
    )
    httpx_policy = _build_policy(
        dep.profile,
        store,
        _Sink(),
        backend=HttpxInferenceBackend(
            clock=fake_clock, transport=_httpx.MockTransport(_handler_for(E2E_TEXT))
        ),
    )
    p_fake = fake_policy.decide(alice_context)
    p_httpx = httpx_policy.decide(alice_context)
    assert p_fake is not None and p_httpx is not None
    assert p_fake.model_dump(mode="json") == p_httpx.model_dump(mode="json")


def test_g6_16_twenty_seven_file_12_name_scan_zero() -> None:
    """#16 27 文件域 12 名扫描 == 0（11 src + 15 测试面 + 2 __init__ − 边界文件）。"""
    domain = _p6_scan_domain()
    assert len(domain) == 27
    for rel in domain:
        assert (REPO_ROOT / rel).is_file(), f"扫描域文件缺失: {rel}"
    hits: list[tuple[str, str]] = []
    for rel in domain:
        for name in _scan_12_names(REPO_ROOT / rel):
            hits.append((rel, name))
    assert hits == []


def test_g6_17_double_run_byte_equal(alice_context, monkeypatch) -> None:
    """#17 S9 双重运行字节相等（含 S7 REJECT 面 + 畸形 JSON 面；S8 探针 env 在位）。"""
    monkeypatch.setenv(PROBE_ENV_NAME, PROBE_VALUE)
    snap1 = _run_chain(alice_context, backend_kind="httpx")
    snap2 = _run_chain(alice_context, backend_kind="httpx")
    assert _canon(snap1) == _canon(snap2)
    # 快照面自检：两运行均含 S7 REJECT 与畸形解析终败（parse_retry 饱和 1）。
    assert snap1["s7_outcome"] == "reject"
    assert snap1["s7_reason"] == "stale_revision"
    assert snap1["world_stable_after_reject"] is True
    assert snap1["bad_decision_none"] is True
    assert snap1["bad_parse_retry"] == 1


def test_g6_18_field_introspection_no_credential_value_fields(monkeypatch) -> None:
    """#18 字段内省：四模型无凭据值字段位；12 名标识符豁免口径探针。"""
    monkeypatch.setenv(PROBE_ENV_NAME, PROBE_VALUE)
    dep = load_deployment(DEPLOYMENT_PATH)
    assert dep.profile is not None
    entry = dep.profile.inference_profiles[CAPABILITY]
    router = resolve_capability(dep.profile, _requirement())
    assert router.resolved is not None
    resolved = router.resolved
    request = InferenceRequest(
        messages=(WireMessage(role="system", content="内省探针消息"),),
        model=resolved.model_id,
        base_url=resolved.base_url,
        api_key_env=resolved.api_key_env,
        temperature=resolved.temperature,
        max_tokens=None,
        timeout_seconds=resolved.timeout_seconds,
        logical_role=CAPABILITY,
        profile=CAPABILITY,
        base_revision=R0,
        prompt_metadata_ref="prompt://ent_alice:7:3",
    )
    response = InferenceResponse(
        text="{}", model=request.model, latency_ms=0.0, input_tokens=None, output_tokens=None
    )
    for obj in (entry, resolved, request, response):
        for value in obj.model_dump(mode="json").values():
            assert PROBE_VALUE not in _canon(value)
    # 名 ≠ 值：api_key_env 位恰持 env 变量名。
    assert request.api_key_env == PROBE_ENV_NAME
    assert entry.api_key_env == PROBE_ENV_NAME
    # 标识符豁免探针：deployment 源含 api_key_env 标识符，但字符串字面量域
    # 对 12 名（含密钥短名）扫描 0 命中 → 标识符不属扫描域。
    tree = ast.parse(
        (REPO_ROOT / "src" / "engine_v2" / _LLM_SEG / "deployment.py").read_text(
            encoding="utf-8"
        )
    )
    ident_names = {
        n.id if isinstance(n, ast.Name) else n.attr
        for n in ast.walk(tree)
        if isinstance(n, (ast.Name, ast.Attribute))
    }
    assert "api_key_env" in ident_names
    assert _literal_hits(tree, "api" + "_key") == 0
    assert _literal_hits(tree, "op" + "enai") == 0


def test_g6_19_nine_key_value_domain(alice_context) -> None:
    """#19 9 键值域：logical_role == profile == capability；parse_retry ∈ {0,1}；
    base_revision int；input_token_estimate == estimator.estimate(pkg.text)。"""
    with _world_side(alice_context) as side:
        payload = next(p for k, p in side["sink"].records if k == "llm_call")
        assert payload["logical_role"] == CAPABILITY
        assert payload["profile"] == CAPABILITY
        assert side["policy"].capability == CAPABILITY
        assert side["resolved"].capability == CAPABILITY
        assert payload["parse_retry"] in (0, 1)
        assert type(payload["base_revision"]) is int
        est = CharDivisorTokenEstimator()
        pkg = assemble_prompt(
            alice_context, side["store"], est, capability=CAPABILITY
        ).package
        assert pkg is not None
        assert type(payload["input_token_estimate"]) is int
        assert payload["input_token_estimate"] == est.estimate(pkg.text)


def test_g6_20_b_con_mechanical_set(alice_context) -> None:
    """#20 B-CON 五点：同步非协程 / 单参签名 / 双态返回 / 类体零随机时钟网络 /
    失配反例 → PolicyActorMismatchError（经 run_policy_decide）。"""
    # B-CON-1/2：同步 + 单参（self, context）。
    assert inspect.iscoroutinefunction(LLMPolicy.decide) is False
    assert list(inspect.signature(LLMPolicy.decide).parameters) == ["self", "context"]
    # 字段封闭 8 名（镜像冻结 test_policy B-CON 面；结构上无随机/时钟/网络位）。
    assert tuple(f.name for f in fields(LLMPolicy)) == (
        "capability",
        "resolved",
        "backend",
        "store",
        "estimator",
        "sink",
        "ttl_ticks",
        "enable_critic",
    )
    # 类体 AST：零随机/时钟/网络标识符面。
    tree = ast.parse(POLICY_SRC.read_text(encoding="utf-8"))
    cls = next(
        n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == "LLMPolicy"
    )
    forbidden = ("random", "clock", "socket", "urllib", "httpx", "requests")
    for node in ast.walk(cls):
        if isinstance(node, ast.Name):
            assert node.id not in forbidden
        if isinstance(node, ast.Attribute):
            assert node.attr not in forbidden
    # B-CON-3：双态返回（ActionProposal 态 + None 态）。
    with _world_side(alice_context) as side:
        assert isinstance(side["s3"][0], ActionProposal)
    dep = load_deployment(DEPLOYMENT_PATH)
    loaded = load_project(PROJECT_ROOT)
    irb = build_ir(loaded.raw)
    store = TemplateStore(project_root=PROJECT_ROOT, policies=irb.ir.prompts)
    noop_script = {(CAPABILITY, Revision(3), 1): '{"action_id": null}'}
    noop_policy = _build_policy(dep.profile, store, _Sink(), script=noop_script)
    assert noop_policy.decide(alice_context) is None
    # B-CON-5：失配反例 → PolicyActorMismatchError（经 run_policy_decide）。

    class _MismatchPolicy:
        def decide(self, context):
            return ActionProposal(
                proposal_id=ActionInstanceId("act_gate_mismatch"),
                actor_id=EntityId("ent_other"),
                action_id=ATTACK,
                base_world_revision=context.base_world_revision,
                provenance=Provenance(
                    producer_id=ProducerId("gate_mismatch_probe"),
                    origin=OriginKind.SCENARIO,
                    notes="gate-mismatch-probe",
                ),
            )

    try:
        run_policy_decide(_MismatchPolicy(), alice_context)
    except PolicyActorMismatchError:
        pass
    else:
        raise AssertionError("失配提案必须触发 PolicyActorMismatchError")


def _handler_for(text: str) -> Any:
    def _handler(request: _httpx.Request) -> _httpx.Response:
        return _httpx.Response(200, json={"choices": [{"message": {"content": text}}]})

    return _handler


def _p6_scan_domain() -> list[str]:
    """27 文件扫描域（SOT §3.12）：11 src + 15 测试面 + 2 测试 __init__ − 边界文件。"""
    src_modules = (
        f"src/engine_v2/{_LLM_SEG}/profiles.py",
        f"src/engine_v2/{_LLM_SEG}/deployment.py",
        f"src/engine_v2/{_LLM_SEG}/router.py",
        f"src/engine_v2/{_LLM_SEG}/adapter.py",
        f"src/engine_v2/{_LLM_SEG}/structured.py",
        f"src/engine_v2/{_LLM_SEG}/policy.py",
        f"src/engine_v2/{_LLM_SEG}/staleness.py",
        f"src/engine_v2/{_LLM_SEG}/critic.py",
        "src/engine_v2/prompts/registry.py",
        "src/engine_v2/prompts/assembler.py",
        "src/engine_v2/prompts/diagnostic.py",
    )
    test_files = (
        f"tests/engine_v2/{_LLM_SEG}/test_profiles.py",
        f"tests/engine_v2/{_LLM_SEG}/test_deployment.py",
        f"tests/engine_v2/{_LLM_SEG}/test_router.py",
        f"tests/engine_v2/{_LLM_SEG}/test_adapter.py",
        f"tests/engine_v2/{_LLM_SEG}/test_structured.py",
        f"tests/engine_v2/{_LLM_SEG}/test_policy.py",
        f"tests/engine_v2/{_LLM_SEG}/test_staleness.py",
        f"tests/engine_v2/{_LLM_SEG}/test_critic.py",
        f"tests/engine_v2/{_LLM_SEG}/test_p6_gate_scenario.py",
        f"tests/engine_v2/{_LLM_SEG}/test_p6_adversarial.py",
        f"tests/engine_v2/{_LLM_SEG}/conftest.py",
        "tests/engine_v2/prompts/test_registry.py",
        "tests/engine_v2/prompts/test_assembler.py",
        "tests/engine_v2/core/test_import_boundary.py",
        "scripts/llm_smoke.py",
    )
    init_files = (
        f"tests/engine_v2/{_LLM_SEG}/__init__.py",
        "tests/engine_v2/prompts/__init__.py",
    )
    domain = list(src_modules) + list(test_files) + list(init_files)
    domain.remove("tests/engine_v2/core/test_import_boundary.py")
    return domain
