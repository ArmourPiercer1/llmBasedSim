"""T9 assembly 测试（计划 T9 Gate 1–6 + 冻结面）。

覆盖（卡面逐字）：

1. **Gate 1 headless happy path**：``assemble_project("tests/fixtures/
   v2_project_galgame")`` → engine 非 None；``engine.advance(1)`` ok；
   ``engine.view()`` = SceneView（10 键面；世界 entities 映射非空）；
   ``engine.submit_action("ent_authoring_player_1", "talk", {})`` →
   ok=False + 诊断含 ``no_executor``（talk 标准声明未绑执行器 = T2 显式
   面，**不抛异常**）；
2. **Gate 2 trust gate**：``assemble_project("examples/complex_minimal",
   trust_python=False)`` → engine 非 None + 诊断含 trust 错误（code =
   ``LLMSIM_PLUGIN_ENTRY_UNRESOLVED``、message 含 ``trust_python``）+
   ``instance.executors`` 无 ``cool``；
3. **Gate 3 trusted 全链**：engine 非 None；executors 含
   inject_heat / cool / toggle_machine；dynamics 长度 ≥1；
   authority_policy.rules 非空；``engine.advance(1)`` 后 temperature 组件
   celsius 相对 advance 前**变化**（dynamics 真实提交 = K2 管道实证）；
   同参两次独立 assembly+advance → ``dump_json(world)`` 字节相等（K7）；
4. **Gate 4 LLM 面**：trusted 全链 + deployment（models 含 1 个合法
   ModelCapabilityProfile + inference_profiles["npc_policy"] 指向它）+
   ``FakeInferenceBackend(script={})`` → ``instance.policies`` 含
   watchman（NPC 有 LLM policy）；无 deployment 变体 → policies 空 +
   warning 诊断（headless 合法路径）；
5. **Gate 5 致命面**：临时目录（无 game.yaml）→ engine=None +
   instance=None + diagnostics 非空（``LLMSIM_FILE_MISSING``）；
6. **Gate 6 零测试包 import**：src 侧 AST 扫描 + 字面双查（T1 同款；
   docstring 注释内字面串同查——T1 教训面）。

额外钉死面（assumption 可检查化）：AssemblyResult 三字段冻结；WorldInstance
contract §1 字段序；全链诊断码 ∈ 18 码闭集（构造期机械强制，此处复核）；
producer registry 五 producer 注册 + origin 分类（assumption A3/A8）；
authority 规则卡面公式（rule_id / description / 单 writer / 唯一性，
assumption A4）。

纪律：只 import src 冻结面 + stdlib + pytest；零真实网络
（FakeInferenceBackend）；零修改他人文件（T1–T8 / T10 交付只读消费）；
只跑本文件（完成后可加跑 tests/engine_v2/runtime/ 全目录确认零回归）。
"""

from __future__ import annotations

import ast
from dataclasses import fields, is_dataclass
from pathlib import Path

from src.engine_v2.content.schemas import (
    DIAGNOSTIC_CODES,
    DiagnosticSeverity,
)
from src.engine_v2.core.authority import AuthorityDecision
from src.engine_v2.core.ids import ProducerId
from src.engine_v2.core.provenance import OriginKind
from src.engine_v2.core.serialization import dump_json
from src.engine_v2.llm.adapter import FakeInferenceBackend
from src.engine_v2.llm.deployment import DeploymentEntry, DeploymentProfile
from src.engine_v2.llm.profiles import ModelCapabilityProfile
from src.engine_v2.runtime.assembly import AssemblyResult, assemble_project
from src.engine_v2.runtime.world_instance import WorldInstance

# —— 路径面（repo 根 = tests/engine_v2/runtime 的 parents[3]）——

REPO_ROOT = Path(__file__).resolve().parents[3]
GALGAME_ROOT = REPO_ROOT / "tests" / "fixtures" / "v2_project_galgame"
COMPLEX_ROOT = REPO_ROOT / "examples" / "complex_minimal"
ASSEMBLY_SOURCE = REPO_ROOT / "src" / "engine_v2" / "runtime" / "assembly.py"

# —— 构造助手 ——


def _deployment() -> DeploymentProfile:
    """最小合法部署：1 个 tier 2 模型 + npc_policy 能力位指向它（Gate 4）。"""
    model = ModelCapabilityProfile(
        model_id="m-test-1",
        tier=2,
        context_length=65536,
        max_output=8192,
        structured_output=True,
        reasoning_class="standard",
    )
    return DeploymentProfile(
        models={"m-test-1": model},
        inference_profiles={
            "npc_policy": DeploymentEntry(provider="test-provider", model="m-test-1")
        },
    )


def _assemble_complex(*, trust: bool = True):
    return assemble_project(COMPLEX_ROOT, trust_python=trust)


# —— 形状冻结面 ——


def test_assembly_result_shape() -> None:
    """AssemblyResult = frozen 三字段（卡面冻结 API）。"""
    assert is_dataclass(AssemblyResult)
    assert [f.name for f in fields(AssemblyResult)] == [
        "engine",
        "instance",
        "diagnostics",
    ]


def test_world_instance_field_order_frozen() -> None:
    """WorldInstance 字段序 = contract §1 逐字（T9 组装面复核）。"""
    assert [f.name for f in fields(WorldInstance)] == [
        "world_instance_id",
        "ir",
        "world",
        "runtime",
        "spaces",
        "action_registry",
        "executors",
        "policies",
        "dynamics",
        "component_registry",
        "producer_registry",
        "authority_policy",
        "trace_sink",
    ]


def test_full_chain_diagnostic_codes_closed_set() -> None:
    """全链诊断码 ∈ 18 码闭集（构造期 model_validator 机械强制，复核面）。"""
    for result in (_assemble_complex(trust=True), _assemble_complex(trust=False), assemble_project(GALGAME_ROOT)):
        assert all(d.code in DIAGNOSTIC_CODES for d in result.diagnostics)


# —— Gate 1：headless happy path（galgame fixture）——


def test_gate1_headless_assembly_ok() -> None:
    result = assemble_project(GALGAME_ROOT)
    assert result.engine is not None
    assert result.instance is not None
    assert result.engine.instance is result.instance
    assert result.instance.world_instance_id == "ws_galgame"


def test_gate1_advance_ok() -> None:
    result = assemble_project(GALGAME_ROOT)
    res = result.engine.advance(1)
    assert res.ok is True
    assert res.diagnostics == ()
    assert res.transactions == ()


def test_gate1_view_scene_view() -> None:
    """view() = SceneView（10 键面；entities 映射非空 = 世界实体面复核）。

    注：SceneView.actors 仅收 tags 含 ``actor`` 的实体——T1 materialize
    的实体 ``tags=[]``（authoring 投影面），故 actors 可为空；「entities
    映射非空」按权威面 ``world.entities`` 复核（卡面括注的实体映射面）。
    """
    result = assemble_project(GALGAME_ROOT)
    view = result.engine.view()
    assert set(view) == {
        "schema",
        "view_revision",
        "scene_id",
        "tick",
        "narrative",
        "actors",
        "environment",
        "tactical_overlay",
        "image_slot",
        "clock",
    }
    assert view["view_revision"] == int(result.instance.world.world_revision)
    entity_ids = {str(entity_id) for entity_id in result.instance.world.entities}
    assert len(entity_ids) >= 5  # 1 location + 2 characters + 1 player + 1 item
    assert "ent_authoring_player_1" in entity_ids


def test_gate1_talk_no_executor_explicit() -> None:
    """talk = 标准声明未绑执行器 → no_executor 显式诊断，不抛异常。"""
    result = assemble_project(GALGAME_ROOT)
    step = result.engine.submit_action("ent_authoring_player_1", "talk", {})
    assert step.ok is False
    assert any("no_executor" in diag for diag in step.diagnostics)


# —— Gate 2：trust gate（trust_python=False 默认面）——


def test_gate2_trust_gate_engine_still_assembles() -> None:
    result = _assemble_complex(trust=False)
    assert result.engine is not None
    assert result.instance is not None


def test_gate2_trust_error_diagnostic() -> None:
    result = _assemble_complex(trust=False)
    trust_errors = [
        d for d in result.diagnostics if d.code == "LLMSIM_PLUGIN_ENTRY_UNRESOLVED"
    ]
    assert trust_errors
    assert all(d.severity == DiagnosticSeverity.ERROR for d in trust_errors)
    assert all("trust_python" in d.message for d in trust_errors)


def test_gate2_no_extension_executors() -> None:
    result = _assemble_complex(trust=False)
    assert "cool" not in result.instance.executors
    assert "inject_heat" not in result.instance.executors
    assert "toggle_machine" not in result.instance.executors
    assert "move" in result.instance.executors  # 标准面恒在
    assert result.instance.dynamics == ()  # 零 bundle → 零 dynamics


# —— Gate 3：trusted 全链（K2 管道实证 + K7 确定性）——


def test_gate3_trusted_executors_and_dynamics() -> None:
    result = _assemble_complex(trust=True)
    assert result.engine is not None
    assert {"inject_heat", "cool", "toggle_machine"} <= set(result.instance.executors)
    assert len(result.instance.dynamics) >= 1


def test_gate3_authority_policy_nonempty() -> None:
    result = _assemble_complex(trust=True)
    policy = result.instance.authority_policy
    assert policy.rules
    assert policy.default_decision is AuthorityDecision.DENY


def test_gate3_dynamics_commit_changes_temperature() -> None:
    """advance(1) 后 temperature 组件 celsius 变化（dynamics 真实提交）。

    期望值钉死（T10 冻结参数）：缺省 celsius=20.0 / power=2（组件缺位
    取 schema 缺省）→ heat_source = 12 + 14*2 = 40 →
    celsius' = 20 + 0.2*(40-20)*1.0 = 24.0（dt=1.0，T2 相位 3 钉值）。
    """
    result = _assemble_complex(trust=True)
    instance = result.instance
    before = instance.world.entities["ent_authoring_boiler_room"].components.get(
        "temperature"
    )
    assert before is None  # T1 不 materialize temperature 组件（authoring 面）
    res = result.engine.advance(1)
    after = instance.world.entities["ent_authoring_boiler_room"].components.get(
        "temperature"
    )
    assert after is not None
    assert after != before  # 卡面钉：相对 advance 前变化
    assert after == {"celsius": 24.0}
    assert res.ok is True  # dynamics 提交被 authority 允许 = 零诊断
    assert int(res.world_revision) > int(before_revision_of(instance, res))


def before_revision_of(instance, res) -> object:
    """advance 前 world_revision 下界（初始 revision = 0 面；D-5 只随
    COMMITTED 事务推进——本测试 advance 恰 1 笔 dynamics 提交）。"""
    del instance, res
    return 0


def test_gate3_k7_independent_assemblies_byte_equal() -> None:
    """同参两次独立 assembly+advance → dump_json(world) 字节相等（K7）。"""

    def world_json() -> str:
        result = _assemble_complex(trust=True)
        assert result.engine is not None
        result.engine.advance(1)
        return dump_json(result.instance.world)

    assert world_json() == world_json()


# —— Gate 4：LLM 面 ——


def test_gate4_llm_policy_bound_with_deployment() -> None:
    result = assemble_project(
        COMPLEX_ROOT,
        trust_python=True,
        deployment=_deployment(),
        inference_backend=FakeInferenceBackend(script={}),
    )
    assert result.engine is not None
    # 修复窗 G1（ERR-C-02）：WorldInstance.policies 键空间 = 世界实体 id
    # （T2 engine 契约）；LLM 绑定面的 slug 键经 assembly 步 12 重映射。
    assert "ent_authoring_watchman" in result.instance.policies  # NPC 有 LLM policy
    # player 不绑（人类输入面，T5 冻结语义）
    assert "operator" not in result.instance.policies
    # 适配器包裹（ERR-C-03）：policy 经 JsonCleanContextPolicyAdapter（resolved 透传面）
    from src.engine_v2.runtime import JsonCleanContextPolicyAdapter

    assert isinstance(result.instance.policies["ent_authoring_watchman"], JsonCleanContextPolicyAdapter)


def test_gate4_headless_variant_policies_empty_with_warning() -> None:
    """无 deployment 变体（trusted 全链缺省）→ policies 空 + warning 诊断。"""
    result = _assemble_complex(trust=True)
    assert result.instance.policies == {}
    warnings = [
        d
        for d in result.diagnostics
        if d.severity == DiagnosticSeverity.WARNING
        and "llm binding disabled" in d.message
    ]
    assert warnings


# —— Gate 5：致命面 ——


def test_gate5_fatal_missing_game_yaml(tmp_path: Path) -> None:
    empty_root = tmp_path / "empty_project"
    empty_root.mkdir()
    result = assemble_project(empty_root)
    assert result.engine is None
    assert result.instance is None
    assert result.diagnostics
    assert any(d.code == "LLMSIM_FILE_MISSING" for d in result.diagnostics)


def test_gate5_fatal_nonexistent_root() -> None:
    result = assemble_project(REPO_ROOT / "no_such_project_dir")
    assert result.engine is None
    assert result.instance is None
    assert any(d.code == "LLMSIM_FILE_MISSING" for d in result.diagnostics)


# —— Gate 6：src 侧零测试包 import（AST 扫描 + 字面双查，T1 同款）——


def test_gate6_src_zero_tests_import_ast() -> None:
    """AST 扫描：assembly.py 全部 Import / ImportFrom 节点零 tests 顶层包。"""
    tree = ast.parse(ASSEMBLY_SOURCE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] != "tests", alias.name
        elif isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] != "tests", node.module


def test_gate6_src_zero_tests_import_literals() -> None:
    """字面双查（docstring / 注释内字面串同查——T1 教训面）。"""
    text = ASSEMBLY_SOURCE.read_text(encoding="utf-8")
    assert "import tests" not in text
    assert "from tests" not in text


# —— 额外钉死面（assumption A3/A4/A8 可检查化）——


def test_producer_registry_fixed_producers_and_origins() -> None:
    """五 producer 注册 + origin 分类（assumption A3；T2 assumption 7
    的 engine/player 必注册面）。"""
    result = _assemble_complex(trust=True)
    registry = result.instance.producer_registry
    engine = registry.get(ProducerId("engine"))
    player = registry.get(ProducerId("player"))
    assert engine is not None and engine.origin is OriginKind.SYSTEM
    assert player is not None and player.origin is OriginKind.DEVELOPER
    move = registry.get(ProducerId("actions.move"))
    assert move is not None and move.origin is OriginKind.SYSTEM  # T6 executor 族
    ext_actions = registry.get(ProducerId("complex_minimal.actions"))
    assert ext_actions is not None and ext_actions.origin is OriginKind.SCRIPT
    ext_dynamics = registry.get(ProducerId("complex_minimal.dynamics"))
    assert (
        ext_dynamics is not None
        and ext_dynamics.origin is OriginKind.DYNAMICS_BACKEND
    )  # 两侧皆现 → dynamics 分类胜（assumption A3）


def test_authority_rules_card_formula() -> None:
    """规则卡面公式：rule_id / description / 单 writer / 唯一性（A4）。"""
    result = _assemble_complex(trust=True)
    rules = result.instance.authority_policy.rules
    rule_ids = [rule.rule_id for rule in rules]
    assert len(rule_ids) == len(set(rule_ids))  # 去重后 rule_id 唯一
    for rule in rules:
        assert rule.description == "runtime-closure grant"
        assert rule.selector.component_type is not None
        assert len(rule.allowed_writers) == 1
        assert (
            rule.rule_id
            == f"rtclosure.{str(rule.allowed_writers[0])}.{str(rule.selector.component_type)}"
        )
    # 修复窗 F2（T11 E2E 验收发现）：单写权拆分——P2「首条匹配拍板」语义
    # 下一组件仅一个有效 writer；complex_minimal 样例 = machine 归 executor
    # 独占、temperature 归 dynamics 独占（dynamics grant 由 host 从
    # metadata().domains 派生），故每 component_type 恰 1 条规则，无竞争。
    component_types = [str(rule.selector.component_type) for rule in rules]
    assert len(component_types) == len(set(component_types)), (
        "同组件多规则 = 首条匹配拍板下的写权竞争（F2 单写权口径违例）"
    )
    assert "rtclosure.complex_minimal.dynamics.temperature" in rule_ids
    assert "rtclosure.complex_minimal.actions.machine" in rule_ids


def test_diagnostics_step_order_preserved() -> None:
    """全链诊断按装配步序拼接、不重排序（assumption A6）：materialize 的
    缺省 grid warning（步 4）先于 extension trust 诊断（步 5）。"""
    result = _assemble_complex(trust=False)
    codes = [d.code for d in result.diagnostics]
    grid_warning = next(
        i
        for i, d in enumerate(result.diagnostics)
        if d.code == "LLMSIM_SCHEMA" and d.path == "world"
    )
    trust_error = codes.index("LLMSIM_PLUGIN_ENTRY_UNRESOLVED")
    assert grid_warning < trust_error
