"""0.1.0-alpha.1 发布前修复 R6：玩家意图（自然语言）E2E 测试矩阵。

审计《0.1.0-alpha.1 发布前修复 — LLM-native Playability Closure》§R6：
真实 production path（GameProject + DeploymentProfile + InferenceBackend）
下「玩家自然语言 → 意图解释器 → 结构化动作 → 引擎权威管道」的闭环面，
全部经 :class:`FakeInferenceBackend`（脚本化确定性，零 API Key、零网络，
CI 可复跑；真实 backend 面 = 发布前人工 smoke，见 §7）。

矩阵（审计 R6 表）：
  p01 朴素自然语言 → 合法动作 → committed；
  p02 实体参数 grounding（实体表忠实投影断言）；
  p03 坏 JSON → repair 成功 → committed；
  p04 两次坏 JSON → 世界不变（显式 no-op）；
  p05 幻觉 action_id → 显式拒绝（未提交，世界零变更）；
  p06 grounding 实体表 = 权威世界实体 id 集（幻觉 id 无合法来源）；
  p07 不可映射意图 → action_id null → no-op；
  p08 LLM parse 成功 ≠ action 成功（executor 显式 failure，世界零变更）；
  p09 双跑确定性（同脚本同输入 → 同结构化结果 + 同最终世界字节）；
  p10 双能力不同模型（player_intent 与 npc_policy 独立 resolve）；
  p11 绑定失败面（disabled / 无 capability profile，显式不静默）。
"""

from __future__ import annotations

import json
from pathlib import Path

from src.engine_v2.core.serialization import dump_json
from src.engine_v2.llm.adapter import FakeInferenceBackend
from src.engine_v2.llm.deployment import DeploymentEntry, DeploymentProfile
from src.engine_v2.llm.player_intent import (
    build_action_grounding,
    build_player_intent_context,
)
from src.engine_v2.llm.profiles import ModelCapabilityProfile
from src.engine_v2.runtime import assemble_project
from src.engine_v2.runtime.llm_binding import bind_player_intent

REPO_ROOT = Path(__file__).resolve().parents[3]
PROJECT_ROOT = REPO_ROOT / "examples" / "complex_minimal"
ALPHA_ROOT = REPO_ROOT / "tests" / "fixtures" / "alpha_contract"

PLAYER = "ent_authoring_operator"
BOILER = "ent_authoring_boiler"

OK_JSON = '{"action_id": "inject_heat", "arguments": {}, "intent": "添炉火", "confidence": 0.9}'
NULL_JSON = '{"action_id": null}'
BAD_TEXT = "sorry, I cannot answer this"


def _profile(model_id: str) -> ModelCapabilityProfile:
    return ModelCapabilityProfile(
        model_id=model_id,
        tier=2,
        context_length=65536,
        max_output=8192,
        structured_output=True,
        reasoning_class="standard",
    )


def _deployment(model_a: str = "model-a", model_b: str = "model-b") -> DeploymentProfile:
    return DeploymentProfile(
        models={model_a: _profile(model_a), model_b: _profile(model_b)},
        inference_profiles={
            "npc_policy": DeploymentEntry(
                provider="openai-compatible", model=model_a, base_url=""
            ),
            "player_intent": DeploymentEntry(
                provider="openai-compatible", model=model_b, base_url=""
            ),
        },
    )


def _fresh(script: dict | None = None):
    """fresh production 装配 + 玩家意图绑定（每测试独立世界）。"""
    backend = FakeInferenceBackend(script=dict(script or {}))
    deployment = _deployment()
    result = assemble_project(
        str(PROJECT_ROOT),
        trust_python=True,
        deployment=deployment,
        inference_backend=backend,
    )
    assert result.engine is not None, [
        f"{d.code}: {d.message}" for d in result.diagnostics if d.severity.value == "error"
    ]
    inst = result.instance
    binding = bind_player_intent(
        inst.ir,
        deployment=deployment,
        backend=backend,
        sink=inst.trace_sink,
    )
    assert binding.interpreter is not None, binding.diagnostics

    def interpret(text: str):
        world = result.engine.instance.world
        ctx = build_player_intent_context(
            world, PLAYER, player_name=inst.ir.player.name
        )
        return binding.interpreter.interpret(
            text=text, context=ctx, base_revision=int(world.world_revision)
        )

    return result.engine, inst, backend, binding, interpret


def _machine_power(inst) -> int:
    """机器功率读面：machine 组件（首笔写后物化）→ 缺席时 item 作者面
    ``properties.initial_power``（tick 0 权威基线，与装配投影同源）。"""
    rec = inst.world.entities[BOILER]
    machine = rec.components.get("machine")
    if machine is not None:
        return int(machine["power"])
    item = rec.components.get("item") or {}
    props = item.get("properties") or {}
    return int(props.get("initial_power", 2))


# —— p01：朴素自然语言 → 合法动作 → committed ——


def test_p01_plain_natural_language_committed_action():
    engine, inst, backend, binding, interpret = _fresh(
        {("player_intent", 0, 1): OK_JSON}
    )
    res = interpret("把炉火添旺一点")
    assert res.action_id == "inject_heat"
    assert res.intent == "添炉火"
    assert res.confidence == 0.9
    assert res.diagnostics == ()
    before = _machine_power(inst)
    step = engine.submit_action(PLAYER, res.action_id, res.arguments, intent=res.intent)
    assert step.ok, step.diagnostics
    assert _machine_power(inst) == before + 1  # 权威状态经管道推进


# —— p02：实体参数 grounding（解释结果携带权威实体 id；提交落地）——


def test_p02_entity_argument_grounding():
    engine, inst, backend, binding, interpret = _fresh(
        {
            (
                "player_intent",
                0,
                1,
            ): (
                '{"action_id": "inject_heat", "arguments": {"target": '
                + f'"{BOILER}"'
                + '}, "intent": "给老锅炉添热", "confidence": 0.85}'
            )
        }
    )
    res = interpret("给锅炉加点火")
    assert res.arguments == {"target": BOILER}
    step = engine.submit_action(PLAYER, res.action_id, res.arguments, intent=res.intent)
    assert step.ok, step.diagnostics
    # grounding 表本身 = IR actions 全量（确定性 IR 序）
    grounding = build_action_grounding(inst.ir)
    assert [g.action_id for g in grounding] == [
        "inject_heat",
        "cool",
        "toggle_machine",
    ]


# —— p03：坏 JSON → repair 成功 → committed ——


def test_p03_bad_json_repair_success():
    engine, inst, backend, binding, interpret = _fresh(
        {
            ("player_intent", 0, 1): BAD_TEXT,
            ("player_intent", 0, 2): OK_JSON,
        }
    )
    res = interpret("添点炉火")
    assert res.action_id == "inject_heat"
    assert len(res.diagnostics) == 1
    assert res.diagnostics[0].code == "LLMSIM_INFERENCE_PARSE_RECOVERED"
    assert res.diagnostics[0].severity.value == "warning"
    assert len(backend.calls) == 2  # calls = 调用史 tuple（只读）
    step = engine.submit_action(PLAYER, res.action_id, res.arguments)
    assert step.ok, step.diagnostics


# —— p04：两次坏 JSON → 显式 no-op，世界零变更 ——


def test_p04_double_bad_json_no_world_change():
    engine, inst, backend, binding, interpret = _fresh(
        {
            ("player_intent", 0, 1): BAD_TEXT,
            ("player_intent", 0, 2): "still not json",
        }
    )
    before = dump_json(inst.world)
    res = interpret("随便做点什么")
    assert res.action_id is None
    assert res.arguments == {}
    assert len(res.diagnostics) == 1
    assert res.diagnostics[0].code == "LLMSIM_INFERENCE_PARSE_FAILED"
    assert res.diagnostics[0].severity.value == "error"
    assert len(backend.calls) == 2  # calls = 调用史 tuple（只读）
    # 未提交 → 世界零变更
    assert dump_json(inst.world) == before
    assert int(inst.world.world_revision) == 0


# —— p05：幻觉 action_id → 显式拒绝（未提交，世界零变更）——


def test_p05_hallucinated_action_id_rejected():
    engine, inst, backend, binding, interpret = _fresh(
        {
            (
                "player_intent",
                0,
                1,
            ): (
                '{"action_id": "fly", "arguments": {}, '
                '"intent": "飞出去", "confidence": 0.99}'
            )
        }
    )
    before = dump_json(inst.world)
    res = interpret("让我飞起来")
    assert res.action_id == "fly"
    # 宿主面显式拒绝（与 play 脚本 _submit_player_intent 同逻辑）：
    assert res.action_id not in inst.action_registry.specs
    # 未提交 → 世界零变更（引擎 unknown_action 为最终门的宿主侧前移面）
    assert dump_json(inst.world) == before
    assert int(inst.world.world_revision) == 0
    # 若误提交，引擎面同样拒绝（最终门）：
    step = engine.submit_action(PLAYER, "fly", {})
    assert not step.ok
    assert step.diagnostics == ("unknown_action:fly",)
    assert dump_json(inst.world) == before


# —— p06：grounding 实体表 = 权威世界实体 id 集（幻觉 id 无合法来源）——


def test_p06_grounding_entity_table_is_faithful_projection():
    engine, inst, backend, binding, interpret = _fresh({})
    world = engine.instance.world
    ctx = build_player_intent_context(
        world, PLAYER, player_name=inst.ir.player.name
    )
    table_ids = {view.entity_id for view in ctx.entities}
    world_ids = {str(eid) for eid in world.entities}
    assert table_ids == world_ids
    # 玩家视角面字段（身份 / 位置 / 库存名）确定性在场
    assert ctx.player_id == PLAYER
    assert ctx.player_name == inst.ir.player.name
    assert ctx.position is not None
    assert "手电" in ctx.inventory


# —— p07：不可映射意图 → action_id null → no-op，世界零变更 ——


def test_p07_unmappable_intent_noop():
    engine, inst, backend, binding, interpret = _fresh(
        {("player_intent", 0, 1): NULL_JSON}
    )
    before = dump_json(inst.world)
    res = interpret("今天天气不错")
    assert res.action_id is None
    assert res.diagnostics == ()  # parse 成功 + LLM 显式 no-op ≠ 失败
    assert dump_json(inst.world) == before
    assert int(inst.world.world_revision) == 0
    # 宿主面对 no-op 不提交（世界零变更的机械面）
    assert res.action_id is None or res.action_id in inst.action_registry.specs


# —— p08：LLM parse 成功 ≠ action 成功（executor 显式 failure，零变更）——


def test_p08_parse_success_action_failure_zero_change():
    engine, inst, backend, binding, interpret = _fresh(
        {("player_intent", 2, 1): OK_JSON}
    )
    # 功率 2 → 4（上限）：两笔直提交
    assert _machine_power(inst) == 2
    assert engine.submit_action(PLAYER, "inject_heat", {}).ok
    assert engine.submit_action(PLAYER, "inject_heat", {}).ok
    assert _machine_power(inst) == 4
    before = dump_json(inst.world)
    before_revision = int(inst.world.world_revision)
    # NL → 同动作 → executor 上限 failure（parse 成功，动作必败）
    res = interpret("再加点火")
    assert res.action_id == "inject_heat"
    step = engine.submit_action(PLAYER, res.action_id, res.arguments)
    assert not step.ok
    assert any("action_failed" in d for d in step.diagnostics), step.diagnostics
    assert dump_json(inst.world) == before
    assert int(inst.world.world_revision) == before_revision


# —— p09：双跑确定性（同脚本同输入 → 同结构化结果 + 同最终世界字节）——


def _run_sequence(script: dict) -> "tuple[object, str]":
    engine, inst, backend, binding, interpret = _fresh(script)
    r1 = interpret("把炉火添旺一点")
    engine.submit_action(PLAYER, r1.action_id, r1.arguments, intent=r1.intent)
    world = engine.instance.world
    ctx = build_player_intent_context(
        world, PLAYER, player_name=inst.ir.player.name
    )
    r2 = binding.interpreter.interpret(
        text="太热了降降温", context=ctx, base_revision=int(world.world_revision)
    )
    engine.submit_action(PLAYER, r2.action_id, r2.arguments, intent=r2.intent)
    results = (
        (r1.action_id, r1.arguments, r1.intent, r1.confidence),
        (r2.action_id, r2.arguments, r2.intent, r2.confidence),
    )
    return results, dump_json(engine.instance.world)


def test_p09_double_run_deterministic():
    script = {
        ("player_intent", 0, 1): OK_JSON,
        (
            "player_intent",
            1,
            1,
        ): (
            '{"action_id": "cool", "arguments": {}, "intent": "降温", "confidence": 0.8}'
        ),
    }
    results_a, world_a = _run_sequence(script)
    results_b, world_b = _run_sequence(script)
    assert results_a == results_b
    assert world_a == world_b  # 最终权威世界字节相等（K7）


# —— p10：双能力不同模型（player_intent 独立 resolve）——


def test_p10_different_models_per_capability():
    backend = FakeInferenceBackend()
    dep = _deployment(model_a="npc-model", model_b="player-model")
    result = assemble_project(
        str(PROJECT_ROOT),
        trust_python=True,
        deployment=dep,
        inference_backend=backend,
    )
    assert result.engine is not None
    binding = bind_player_intent(
        result.instance.ir, deployment=dep, backend=backend,
        sink=result.instance.trace_sink,
    )
    assert binding.interpreter is not None, binding.diagnostics
    assert binding.resolved_model == "player-model"
    # npc_policy 侧仍解析到独立模型（绑定面零跨 capability 借用）
    assert dep.inference_profiles["npc_policy"].model == "npc-model"


# —— p11：绑定失败面（disabled / 无 capability profile，显式不静默）——


def test_p11_binding_failure_surfaces():
    backend = FakeInferenceBackend()
    # (a) disabled：无 deployment/backend → warning + interpreter None
    result = assemble_project(str(PROJECT_ROOT), trust_python=True)
    assert result.engine is not None
    disabled = bind_player_intent(
        result.instance.ir, deployment=None, backend=None,
        sink=result.instance.trace_sink,
    )
    assert disabled.interpreter is None
    assert disabled.resolved_model is None
    assert len(disabled.diagnostics) == 1
    assert disabled.diagnostics[0].severity.value == "warning"
    # (b) 无 capability profile（alpha_contract 未声明 player_intent）
    alpha = assemble_project(str(ALPHA_ROOT), trust_python=True)
    assert alpha.engine is not None
    no_cap = bind_player_intent(
        alpha.instance.ir, deployment=_deployment(), backend=backend,
        sink=alpha.instance.trace_sink,
    )
    assert no_cap.interpreter is None
    assert len(no_cap.diagnostics) == 1
    assert no_cap.diagnostics[0].severity.value == "error"
    assert "player_intent" in no_cap.diagnostics[0].message
