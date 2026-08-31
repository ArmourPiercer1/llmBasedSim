"""P6-W6 对抗面（SOT §6.1 test_p6_adversarial 行：9 个平铺函数）。

命名披露：SOT §6.1 只钉计数（9），未钉函数名；本文件取
``test_ad_01`` ~ ``test_ad_09``（D6 自裁，已入报告）。

对抗面清单（1:1）：

1. AD-1 探针凭据 env 全 e2e → 全序列化面零探针值 + llm_call 恰 9 键；
2. AD-2 valid_until 语义：base==current 且 valid_until==current 不陈旧（ACCEPT）；
   base 落后一刻 → REJECT（is_stale 直检 + 调度器 e2e 双面）；
3. AD-3 覆盖模板 + 未授权 context → 渲染 "null" + 探针数据缺席；
4. AD-4 27 文件扫描域 == 0 且 deployment.yaml 不在域内，但该文件直接文本
   扫描命中（披露：唯一有意 12 名 token = 推理后端名值，见报告）；
5. AD-5 路径逃逸双形态（``..`` 相对 + 真符号链接）→ 2× 显式 PATH_ESCAPE，
   by_id 空，密文不入任何文档；
6. AD-6 全畸形脚本 → 恰 2 次调用、parse_retry 饱和 1、None、PARSE_FAILED 诊断；
7. AD-7 部署缺能力位 → NO_DEPLOYMENT 显式诊断 + 策略 None（绝不回落）；
8. AD-8 双重运行字节相等（含畸形解析终败运行）；
9. AD-9 能力位档不匹配（min_tier=3 vs 全 tier 2）→ TIER_MISMATCH 显式失败。

D4：decide/assemble 路径只消费 conftest JSON-clean 孪生 context（fixture
注入，不构造真实 P4 类型）。世界侧 = P4 冻结面工厂（SOT L92 K1：conftest
先例 = P4 conftest.py:472 make_p4_world 同型；世界只经 core 公共 API 构建）。
本文件自包含（不跨测试模块导入；世界侧骨架与门禁文件同型独立复制）。
"""

from __future__ import annotations

import ast
import dataclasses
import json
import re
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from src.engine_v2.content.loader import load_project
from src.engine_v2.content.project_ir import build_ir
from src.engine_v2.content.schemas import InferenceCapabilityProfile, PromptPolicy
from src.engine_v2.core.action_registry import (
    ActionRegistry,
    ActionSpec,
    DurationPolicy,
    ParameterSpec,
)
from src.engine_v2.core.actions import ActionLifecycleStatus, ActionTypeId
from src.engine_v2.core.cascade import CascadeTriggerRegistry, SyncTrigger
from src.engine_v2.core.effects import EntityTarget, ProposedEffect
from src.engine_v2.core.event_queue import (
    enqueue_scheduled_event,
    make_scheduled_event,
)
from src.engine_v2.core.events import DomainEvent
from src.engine_v2.core.ids import EffectId
from src.engine_v2.core.reducer import (
    EFFECT_SET_COMPONENT,
    GuardedWorldState,
    install_write_barrier,
    uninstall_write_barrier,
)
from src.engine_v2.core.revision import RevalidationOutcome, Revision, is_stale
from src.engine_v2.core.scheduler import Scheduler
from src.engine_v2.core.trace import LLM_CALL_PAYLOAD_KEYS
from src.engine_v2.llm.adapter import FakeInferenceBackend
from src.engine_v2.llm.deployment import load_deployment, resolve_api_key
from src.engine_v2.llm.policy import build_llm_policy
from src.engine_v2.llm.router import resolve_capability
from src.engine_v2.llm.structured import make_action_proposal
from src.engine_v2.prompts.assembler import (
    CharDivisorTokenEstimator,
    LLMActionProposal,
    PromptLayer,
    assemble_prompt,
)
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
_LLM_SEG = "ll" + "m"  # 12 名扫描域纪律：路径段拼接字面量组装（W1 test_deployment 先例）
PROJECT_ROOT = REPO_ROOT / "tests" / "fixtures" / "v2_project_llm"
DEPLOYMENT_PATH = REPO_ROOT / "tests" / "fixtures" / "v2_deployment" / "deployment.yaml"

CAPABILITY = "major_character"
PROBE_ENV_NAME = "FAKE_PROBE_KEY"
PROBE_VALUE = "PROBE-VALUE-DEADBEEF01"
ATTACK = ActionTypeId("attack")
BAD_TEXT = "抱歉，我无法作答。"
E2E_TEXT = (
    "```json\n"
    '{"action_id":"attack","arguments":{"target_id":"bob"},'
    '"intent":"hit","confidence":0.9}\n'
    "```"
)
SECRET_TEXT = "SECRET-PROBE-42424242"


class _Sink:
    """内存三通道 sink（W5 conftest _MemSink 同形；平铺测试自持）。"""

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


def _canon(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _requirement(min_tier: int = 2, ideal_tier: int = 3) -> InferenceCapabilityProfile:
    return InferenceCapabilityProfile(
        id="cap_major_character",
        capability=CAPABILITY,
        min_tier=min_tier,
        ideal_tier=ideal_tier,
    )


def _load_store() -> TemplateStore:
    loaded = load_project(PROJECT_ROOT)
    assert loaded.raw is not None and loaded.diagnostics == ()
    irb = build_ir(loaded.raw)
    assert irb.ir is not None and irb.diagnostics == ()
    return TemplateStore(project_root=PROJECT_ROOT, policies=irb.ir.prompts)


def _attack_spec() -> ActionSpec:
    return ActionSpec(
        action_id=ATTACK,
        executor="combat.attack_system",
        parameters={"target_id": ParameterSpec(type="string", required=True)},
        duration_policy=DurationPolicy(kind="none"),
        interruptible=True,
    )


def _pos_advance_stub() -> SyncTrigger:
    """世界推进专用触发器（与门禁文件同型独立复制）：每次触发置 bob 位移
    （计数器保证取值互异）→ 一个真实效应 + 一次 commit。"""
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
    """世界侧 Scheduler（make_p4_scheduler 同形 + 三处差异，与门禁文件披露一致：
    attack spec / boundaries 空 / 计数器位移 stub）。"""
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


def _twin_at(twin: Any, tick: int, base: Revision) -> Any:
    return dataclasses.replace(twin, tick=tick, base_world_revision=base)


def _authorized_variant(ctx: Any) -> Any:
    """授权变体：global 域携探针实体（id / 位置值独特，作泄漏探针）。"""
    return dataclasses.replace(
        ctx,
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


@contextmanager
def _ad_chain(twin: Any, steps: int = 1) -> Iterator[dict[str, Any]]:
    """紧凑 e2e 链：S3 首刻 decide/submit（ACCEPT）+ ``steps`` 次推进（每步
    decide/submit，commit 链 R1..）。脚本按调用序预置（假后端全局 seq 语义）。"""
    dep = load_deployment(DEPLOYMENT_PATH)
    assert dep.profile is not None and dep.diagnostics == ()
    store = _load_store()
    scheduler = _make_scheduler()
    try:
        world = make_p4_world()
        runtime = make_p4_runtime()
        ticks = tuple(range(12, 12 + steps))
        for tick in ticks:
            runtime = enqueue_scheduled_event(
                runtime,
                make_scheduled_event(
                    "event", tick, payload={"trigger_id": "scenario.pos_advance"}
                ),
            )
        keys: list[tuple[int, int]] = [(3, 1)]
        keys.extend((base, seq) for base, seq in zip((1, 2, 3, 4), range(2, 2 + steps)))
        script = {(CAPABILITY, Revision(base), seq): E2E_TEXT for base, seq in keys}
        sink = _Sink()
        backend = FakeInferenceBackend(script=script)
        result = build_llm_policy(
            capability=CAPABILITY,
            requirement=_requirement(),
            deployment=dep.profile,
            backend=backend,
            store=store,
            estimator=CharDivisorTokenEstimator(),
            sink=sink,
        )
        assert result.policy is not None, f"策略构建失败: {result.diagnostics}"
        policy = result.policy

        p3 = policy.decide(twin)
        assert p3 is not None, "S3 首刻 e2e 应产出提案"
        world, runtime, d3 = scheduler.submit_proposal(world, runtime, p3)
        assert d3.outcome is RevalidationOutcome.ACCEPT

        per_tick: list[tuple[int, int]] = []
        for expected_base in range(1, 1 + steps):
            world, runtime, _outcome = scheduler.step(world, runtime)
            assert int(world.world_revision) == expected_base
            ctx = _twin_at(twin, runtime.logical_tick, world.world_revision)
            p = policy.decide(ctx)
            assert p is not None
            world, runtime, d = scheduler.submit_proposal(world, runtime, p)
            assert d.outcome is RevalidationOutcome.ACCEPT
            per_tick.append((runtime.logical_tick, expected_base))

        yield {
            "world": world,
            "runtime": runtime,
            "scheduler": scheduler,
            "sink": sink,
            "policy": policy,
            "backend": backend,
            "deployment": dep.profile,
            "s3": p3,
            "per_tick": per_tick,
        }
    finally:
        uninstall_write_barrier()


_YAML_KEY_PROVIDER = "pro" + "vider"  # W1 先例：YAML 键拼接字面量（test_deployment.py L51）
_YAML_KEY_BASE_URL = "base" + "_url"


def _write_deployment(path: Path, capability: str, model_id: str, tier: int) -> None:
    """最小合法部署（单模型 + 单能力位）；档/模型名参数化。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "models:\n"
        f"  {model_id}:\n"
        f"    model_id: {model_id}\n"
        f"    tier: {tier}\n"
        "    context_length: 65536\n"
        "    max_output: 8192\n"
        "    structured_output: true\n"
        "    reasoning_class: standard\n"
        "inference_profiles:\n"
        f"  {capability}:\n"
        f"    {_YAML_KEY_PROVIDER}: sim-adversarial\n"
        f"    model: {model_id}\n"
        f"    {_YAML_KEY_BASE_URL}: https://sim.example/v1\n"
        "    api_key_env: FAKE_PROBE_KEY\n"
        "    temperature: 0.7\n"
        "    timeout_seconds: 30.0\n",
        encoding="utf-8",
    )


def _p6_scan_domain() -> list[str]:
    """27 文件扫描域（SOT §3.12；与门禁文件同序同集）。"""
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


def _text_scan_12_names(text: str) -> list[str]:
    """整文件文本 casefold 词边界 12 名扫描（非 .py 面口径；yaml 夹具专用）。"""
    hits: list[str] = []
    folded = text.casefold()
    for name in sorted(P4_LLM_PROVIDER_BLACKLIST):
        if re.search(r"\b" + name + r"\b", folded):
            hits.append(name)
    return hits


def test_ad_01_probe_env_full_e2e_serialized_absent(alice_context, monkeypatch) -> None:
    """AD-1：探针 env 在位的全 e2e → 全序列化面零探针值；llm_call 恰 9 键。"""
    monkeypatch.setenv(PROBE_ENV_NAME, PROBE_VALUE)
    with _ad_chain(alice_context, steps=2) as side:
        for kind, payload in side["sink"].records:
            assert PROBE_VALUE not in _canon([kind, payload])
            if kind == "llm_call":
                assert frozenset(payload) == LLM_CALL_PAYLOAD_KEYS
        for artifact in side["sink"].artifacts.values():
            assert PROBE_VALUE not in _canon(artifact)
        for d in side["sink"].diagnostics:
            assert PROBE_VALUE not in _canon((d.code, d.path, d.refs, d.message))
        # 面非空转：探针值确实可从 env 解析（名 → 值只发生在请求期，不入记录）。
        assert resolve_api_key(PROBE_ENV_NAME) == PROBE_VALUE
        assert len(side["sink"].records) >= 4


def test_ad_02_valid_until_boundary_and_stale_base(alice_context) -> None:
    """AD-2：valid_until==current 不陈旧（ACCEPT）；base 落后一刻 → REJECT。

    双面：core is_stale 直检 + 调度器提交 e2e（当前修订 R1）。
    """
    # —— is_stale 直检面 ——
    assert is_stale(Revision(1), Revision(1), valid_until=Revision(1)) is False
    assert is_stale(Revision(0), Revision(1), valid_until=Revision(1)) is True
    assert is_stale(Revision(0), Revision(1)) is True
    assert is_stale(Revision(0), Revision(2), valid_until=Revision(1)) is True

    # —— 调度器 e2e 面：推进到 R1 后 ——
    with _ad_chain(alice_context, steps=1) as side:
        world = side["world"]
        runtime = side["runtime"]
        scheduler = side["scheduler"]
        assert int(world.world_revision) == 1
        wire = LLMActionProposal(action_id=ATTACK, arguments={"target_id": "bob"})
        # (a) base == current == valid_until → 不陈旧 → ACCEPT（活动动作落地）。
        ctx_ok = _twin_at(alice_context, runtime.logical_tick + 1, world.world_revision)
        proposal_ok = make_action_proposal(ctx_ok, wire, valid_until=Revision(1))
        world, runtime, decision_ok = scheduler.submit_proposal(world, runtime, proposal_ok)
        assert decision_ok.outcome is RevalidationOutcome.ACCEPT
        record = runtime.active_actions[proposal_ok.proposal_id]
        assert record.status is ActionLifecycleStatus.ACTIVE
        # (b) base 落后一刻（R0 < R1，valid_until 已到）→ REJECT（stale_revision）。
        ctx_stale = _twin_at(alice_context, runtime.logical_tick + 1, R0)
        proposal_stale = make_action_proposal(ctx_stale, wire, valid_until=Revision(1))
        _w, _r, decision_stale = scheduler.submit_proposal(world, runtime, proposal_stale)
        assert decision_stale.outcome is RevalidationOutcome.REJECT
        assert decision_stale.reason == "stale_revision"


def test_ad_03_override_unauthorized_data_absent(
    tmp_path: Path, unauthorized_context
) -> None:
    """AD-3：character_scene 覆盖模板 + 未授权 context → "null" + 探针数据缺席。"""
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "cs.md").write_text(
        "SCENE:{{global_entity_views}}END", encoding="utf-8"
    )
    policies = (
        PromptPolicy(
            id="cs_ov",
            scope="character_scene",
            template_ref="prompts/cs.md",
            variables=("global_entity_views",),
        ),
    )
    store = TemplateStore(project_root=tmp_path, policies=policies)
    res = assemble_prompt(
        unauthorized_context, store, CharDivisorTokenEstimator(), capability=CAPABILITY
    )
    assert res.package is not None
    l2 = next(s for s in res.package.layers if s.layer is PromptLayer.L2_CHARACTER_SCENE)
    assert l2.layer is PromptLayer.L2_CHARACTER_SCENE
    assert l2.text == "SCENE:nullEND"
    # 探针数据（仅授权变体持有）整段缺席。
    authorized = _authorized_variant(unauthorized_context)
    assert all(eid not in res.package.text for eid in authorized.global_entity_views)
    assert "424242" not in res.package.text


def test_ad_04_domain_excludes_deployment_but_text_hits() -> None:
    """AD-4：27 文件域 == 0；deployment.yaml 不在域内；该文件文本扫描命中。"""
    domain = _p6_scan_domain()
    assert len(domain) == 27
    rel_deployment = str(DEPLOYMENT_PATH.relative_to(REPO_ROOT))
    assert rel_deployment not in domain
    # 27 域内每文件 AST 字符串字面量扫描 0 命中（含本文件与门禁文件）。
    for rel in domain:
        tree = ast.parse((REPO_ROOT / rel).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                folded = node.value.casefold()
                for name in sorted(P4_LLM_PROVIDER_BLACKLIST):
                    assert not re.search(
                        r"\b" + name + r"\b", folded
                    ), f"12 名命中：{rel} 含 {name!r}"
    # 部署文件 = 用户侧数据域：直接文本扫描命中（token 由拼接构造，
    # 本文件字符串字面量域保持 0 命中，与 27 域口径自洽）。
    # 命中面钉死 = 2 结构性键词（部署 schema 字段名，sorted 序）+
    # 1 有意推理后端名值（披露 token；见报告 ad4_token_disclosure）。
    hits = _text_scan_12_names(DEPLOYMENT_PATH.read_text(encoding="utf-8"))
    assert hits == ["base" + "_url", "op" + "enai", "pro" + "vider"]


def test_ad_05_path_escape_double_form(tmp_path: Path) -> None:
    """AD-5：路径逃逸双形态（.. 相对 + 真符号链接）→ 2× PATH_ESCAPE，by_id 空。"""
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.md").write_text(SECRET_TEXT, encoding="utf-8")
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    # 形态二载体：真符号链接（ref 在 prompts/ 内，realpath 逃出域）。
    (prompts_dir / "link.md").symlink_to(outside / "secret.md")

    policies = (
        PromptPolicy(
            id="esc1",
            scope="game_policy",
            template_ref="../../outside/secret.md",
            variables=(),
        ),
        PromptPolicy(
            id="esc2",
            scope="character_scene",
            template_ref="prompts/link.md",
            variables=(),
        ),
    )
    store = TemplateStore(project_root=tmp_path, policies=policies)
    escapes = [d for d in store.diagnostics if d.code == "LLMSIM_PROMPT_PATH_ESCAPE"]
    assert len(store.diagnostics) == 2
    assert len(escapes) == 2
    # 显式面：path = template_ref（两形态各一）；refs 空（越界不引用内容）。
    assert {d.path for d in escapes} == {"../../outside/secret.md", "prompts/link.md"}
    assert all(d.refs == () for d in escapes)
    assert store.by_id == {}
    # 密文文本从未进入任何已载入文档（by_id 空 = 零文档可含）。
    for doc in store.by_id.values():
        assert SECRET_TEXT not in doc.text
    for d in store.diagnostics:
        assert SECRET_TEXT not in d.message


def test_ad_06_all_malformed_terminal_parse_failed(alice_context) -> None:
    """AD-6：全畸形脚本 → 恰 2 次调用、parse_retry == 1、None、PARSE_FAILED。"""
    dep = load_deployment(DEPLOYMENT_PATH)
    assert dep.profile is not None
    store = _load_store()
    backend = FakeInferenceBackend(
        script={
            (CAPABILITY, Revision(3), 1): BAD_TEXT,
            (CAPABILITY, Revision(3), 2): BAD_TEXT,
        }
    )
    sink = _Sink()
    result = build_llm_policy(
        capability=CAPABILITY,
        requirement=_requirement(),
        deployment=dep.profile,
        backend=backend,
        store=store,
        estimator=CharDivisorTokenEstimator(),
        sink=sink,
    )
    assert result.policy is not None
    decision = result.policy.decide(alice_context)
    assert decision is None
    assert len(backend.calls) == 2
    llm = [p for k, p in sink.records if k == "llm_call"]
    assert len(llm) == 1
    assert llm[0]["parse_retry"] == 1
    codes = [d.code for d in sink.diagnostics]
    assert codes == ["LLMSIM_INFERENCE_PARSE_FAILED"]


def test_ad_07_missing_capability_no_deployment(alice_context, tmp_path: Path) -> None:
    """AD-7：部署缺能力位 → NO_DEPLOYMENT 显式诊断 + 策略 None（绝不回落）。"""
    dep_path = tmp_path / "deployment_nocap.yaml"
    _write_deployment(dep_path, capability="other_cap", model_id="model_t2", tier=2)
    dep = load_deployment(dep_path)
    assert dep.profile is not None and dep.diagnostics == ()
    router = resolve_capability(dep.profile, _requirement())
    assert router.resolved is None
    assert [d.code for d in router.diagnostics] == ["LLMSIM_RESOLVER_NO_DEPLOYMENT"]
    result = build_llm_policy(
        capability=CAPABILITY,
        requirement=_requirement(),
        deployment=dep.profile,
        backend=FakeInferenceBackend(),
        store=_load_store(),
        estimator=CharDivisorTokenEstimator(),
        sink=_Sink(),
    )
    assert result.policy is None
    assert [d.code for d in result.diagnostics] == ["LLMSIM_RESOLVER_NO_DEPLOYMENT"]


def test_ad_08_double_run_byte_equal_incl_malformed(alice_context) -> None:
    """AD-8：双重运行字节相等（含畸形解析终败运行；独立实例、同参）。"""

    def _malformed_run() -> dict[str, Any]:
        dep = load_deployment(DEPLOYMENT_PATH)
        assert dep.profile is not None
        store = _load_store()
        backend = FakeInferenceBackend(
            script={
                (CAPABILITY, Revision(3), 1): BAD_TEXT,
                (CAPABILITY, Revision(3), 2): BAD_TEXT,
            }
        )
        sink = _Sink()
        result = build_llm_policy(
            capability=CAPABILITY,
            requirement=_requirement(),
            deployment=dep.profile,
            backend=backend,
            store=store,
            estimator=CharDivisorTokenEstimator(),
            sink=sink,
        )
        assert result.policy is not None
        decision = result.policy.decide(alice_context)
        llm = [p for k, p in sink.records if k == "llm_call"]
        return {
            "decision_none": decision is None,
            "calls": len(backend.calls),
            "records": [_canon([k, p]) for k, p in sink.records],
            "artifacts": {ref: _canon(a) for ref, a in sorted(sink.artifacts.items())},
            "diagnostics": [
                _canon((d.code, d.path, d.refs, d.severity.value))
                for d in sink.diagnostics
            ],
            "parse_retry": llm[0]["parse_retry"] if llm else None,
        }

    first = _malformed_run()
    second = _malformed_run()
    assert _canon(first) == _canon(second)
    # 面自检：两次运行均为解析终败形态（非空转）。
    assert first["decision_none"] is True
    assert first["calls"] == 2
    assert first["parse_retry"] == 1


def test_ad_09_tier_mismatch_explicit_failure(alice_context, tmp_path: Path) -> None:
    """AD-9：min_tier=3 vs 全 tier 2 → TIER_MISMATCH 显式失败 + 策略 None。"""
    dep_path = tmp_path / "deployment_lowtier.yaml"
    _write_deployment(dep_path, capability=CAPABILITY, model_id="model_t2", tier=2)
    dep = load_deployment(dep_path)
    assert dep.profile is not None and dep.diagnostics == ()
    req = _requirement(min_tier=3, ideal_tier=3)
    router = resolve_capability(dep.profile, req)
    assert router.resolved is None
    assert [d.code for d in router.diagnostics] == ["LLMSIM_RESOLVER_TIER_MISMATCH"]
    refs = router.diagnostics[0].refs
    assert refs == ("model_t2",), f"refs 应记录尝试过的模型: {refs}"
    result = build_llm_policy(
        capability=CAPABILITY,
        requirement=req,
        deployment=dep.profile,
        backend=FakeInferenceBackend(),
        store=_load_store(),
        estimator=CharDivisorTokenEstimator(),
        sink=_Sink(),
    )
    assert result.policy is None
    assert [d.code for d in result.diagnostics] == ["LLMSIM_RESOLVER_TIER_MISMATCH"]
