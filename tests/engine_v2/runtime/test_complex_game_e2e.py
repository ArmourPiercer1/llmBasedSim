"""T11 E2E 独立验收（runtime 12h closure 计划 T11 卡；gate C1–C9 逐字覆盖）。

单入口：``from src.engine_v2.runtime import assemble_project`` /
``build_actor_context``（零测试包导入）。样例 = ``examples/complex_minimal``
（T10；只读消费——C2 经 ``shutil.copytree`` 复制到 tmp_path 做隔离，零修改
样例文件）。fixture/helper 风格对齐 T9 ``test_assembly.py`` 与 T5
``test_llm_binding.py`` 的绿色参照（helper 自包含移植，**不 import 那两个
测试模块**）。

Gate 实际路径（T11 独立验收；Leader 修复窗 L1–L3 + F1–F3 后重钉；细节见
各测试 docstring 与 handoff）：

- **C1** 生产路径零测试包导入：AST 扫描 + 严格字面双查 + delta sys.modules
  全绿（L3 docstring 字面违例已在修复窗修正）。
- **C2 / C3 / C4 / C6**：按卡面期望全绿。
- **C5** 自定义动作走权威管道：实际路径 = **成功提交**（F1 machine 缺位
  自举 power=2 + F2 单写权拆分：cool 改 power−1、executor grant 只 claim
  machine、temperature 归 dynamics 单写）：``inject_heat`` → ok、
  power 2→3、1 COMMITTED txn；``cool`` → ok、power 2→1（自举）、
  temperature 不变面。
- **C7** NPC 经 P6 LLMPolicy：engine 循环**全链通过**（G1 装配重映射
  policies 键 = 世界实体 id + G2 ``JsonCleanContextPolicyAdapter``
  影子 context + F3 prompt 变量回归封闭集）——wake + advance →
  decide 命中脚本 → machine 2→3 COMMITTED + dynamics 20.0→26.8
  （power=3 积分）+ 2 COMMITTED txns + sink prompt_assembly/llm_call
  两事件 + 双跑 dump_json 字节相等。
- **C8** 同一管道 provenance：C7 提交可观察——事务级 provenance =
  ``engine`` / SYSTEM（T2 assumption 7 事务装配者分层）；effect 级
  source = ``complex_minimal.actions``（NPC 动作笔，cause 含 PROPOSAL
  ref）/ ``complex_minimal.dynamics``（dynamics 笔）；
  ``behavior_policy`` origin 在 P6 提案构造面（``make_action_proposal``
  钉 origin=BEHAVIOR_POLICY），经 cause ref 可溯至提案。
- **C9** (a) 上下文可见性绿（global None + self 可见 + 感知并集精确面）；
  (b) SceneView 10 键绿——组件数据落在**权威世界面**（SceneView 按 P10
  设计不携带组件载荷，actors 面 = id/name/position/mood/tags）；
  (c) 双跑字节相同绿（``dump_json(world)`` + sink 逐事件 ``to_dict()``
  + artifacts + sink 诊断全等）。

纪律：零测试包导入（本 docstring 同守）；导入风格一律
``from src.engine_v2...``；零墙钟 / 零 uuid / 零网络 / 零随机
（C9c 双跑确定性 = 本文件最强纪律断言）；自包含（不 import 任何其他
测试模块）；只读消费 T1–T10 交付（发现实现问题一律不修，写 handoff）。

跑法：``cd <repo root> && PYTHONPATH=. .venv/bin/python -m pytest
tests/engine_v2/runtime/test_complex_game_e2e.py -q -p no:cacheprovider``
（完成后加跑 tests/engine_v2/runtime/ 全目录确认零回归）。
"""

from __future__ import annotations

import ast
import shutil
import sys
from pathlib import Path

import pytest

from src.engine_v2.content.schemas import DiagnosticSeverity
from src.engine_v2.core.context_provider import ActorDecisionContext
from src.engine_v2.core.ids import EntityId
from src.engine_v2.core.provenance import CauseKind, OriginKind
from src.engine_v2.core.revision import Revision
from src.engine_v2.core.serialization import dump_json
from src.engine_v2.core.transaction import TransactionStatus
from src.engine_v2.llm.adapter import FakeInferenceBackend
from src.engine_v2.llm.deployment import DeploymentEntry, DeploymentProfile
from src.engine_v2.llm.profiles import ModelCapabilityProfile
from src.engine_v2.llm.structured import make_action_proposal
from src.engine_v2.prompts.assembler import LLMActionProposal
from src.engine_v2.runtime import (
    JsonCleanContextPolicyAdapter,
    assemble_project,
    build_actor_context,
)

# —— 路径面（repo 根 = tests/engine_v2/runtime 的 parents[3]；test_assembly 同款）——

REPO_ROOT = Path(__file__).resolve().parents[3]
RUNTIME_SRC_DIR = REPO_ROOT / "src" / "engine_v2" / "runtime"
COMPLEX_ROOT = REPO_ROOT / "examples" / "complex_minimal"

# —— 实体身份面（内容侧确定性命名 ent_authoring_<slug>，ids.py:68 约定）——

PLAYER_ENTITY = "ent_authoring_operator"
WATCHMAN_ENTITY = "ent_authoring_watchman"
BOILER_ENTITY = "ent_authoring_boiler"
ROOM_ENTITY = "ent_authoring_boiler_room"

# —— C7 脚本（卡面字面 wire JSON；LLMActionProposal extra="ignore"，
#    arguments/intent/confidence 缺省合法——字段名经 llm/policy.py 解析面确认）——

INJECT_SCRIPT = '{"action_id": "inject_heat"}'

# —— C1 禁用字面串（T1 教训面：docstring/注释内字面串同查）——

_FORBIDDEN_LITERALS = ("import tests", "from tests")

#: C1 扫描面（src/engine_v2/runtime 全部模块，sorted 确定性序）。
_RUNTIME_PY = sorted(RUNTIME_SRC_DIR.glob("*.py"))


# —— 构造助手（确定性；风格对齐 T9/T5 绿色参照）——


def _deployment() -> DeploymentProfile:
    """最小合法部署：1 个 tier 2 模型 + npc_policy 能力位指向它
    （T9 Gate 4 / T5 绿色参照同款构造）。"""
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


def _assemble_trust() -> object:
    """trust=True 全链装配（headless：无 deployment → LLM 绑定 disabled）。"""
    return assemble_project(COMPLEX_ROOT, trust_python=True)


def _assemble_llm(backend: FakeInferenceBackend) -> object:
    """trust=True + deployment + 注入 backend（C7/C8/C9c 的 LLM 面）。"""
    return assemble_project(
        COMPLEX_ROOT,
        trust_python=True,
        deployment=_deployment(),
        inference_backend=backend,
    )


def _c7_chain(base_rev: Revision) -> tuple:
    """C7 全链：全新装配（脚本命中：seq=1、base=base_rev）+ wake +
    advance(1)。返回 (result, backend, StepResult)。"""
    backend = FakeInferenceBackend(
        script={("npc_policy", base_rev, 1): INJECT_SCRIPT}
    )
    result = _assemble_llm(backend)
    result.engine.wake(WATCHMAN_ENTITY, reason="e2e_c7")
    sr = result.engine.advance(1)
    return result, backend, sr


def _module_delta(before: set[str], after: set[str]) -> set[str]:
    """sys.modules 差集（卡面纪律：delta-based、测试顺序无关——前面的
    trust=True 装配会把 complex_minimal 留在 sys.modules，裸断言会脆）。"""
    return after - before


def _offenders(delta: set[str], *names: str) -> tuple[str, ...]:
    """差集中命中模块名（精确或子包前缀）的违规项。"""
    return tuple(
        sorted(
            n
            for n in delta
            if any(n == name or n.startswith(name + ".") for name in names)
        )
    )


def _temperature(instance) -> dict | None:
    """锅炉房 temperature 组件快照（缺位 → None；authoring 面不物化）。"""
    data = instance.world.entities[EntityId(ROOM_ENTITY)].components.get(
        "temperature"
    )
    return dict(data) if data is not None else None


def _minimal_json_native_context(
    actor_id: str, base: Revision, *, tick: int = 0
) -> ActorDecisionContext:
    """JSON-native 最小 13 字段 context（T5 ``_make_context`` 先例移植：
    plain frozen dataclass 无运行时校验；容器全用 JSON 原生替身——tuple
    而非 frozenset，避开 G2 的 L3 序列化缺口，用于隔离验证 P6 解析面）。"""
    return ActorDecisionContext(
        actor_id=EntityId(actor_id),
        tick=tick,
        base_world_revision=base,
        wake_reason="e2e_c7",
        self_view={
            "entity_id": actor_id,
            "entity_class": "character",
            "tags": (),
            "revision": int(base),
            "components": {},
        },
        visible_entities=(actor_id,),
        local_entity_views={},
        global_entity_views=None,
        observations=(),
        knowledge=None,
        memory=(),
        candidate_actions=("inject_heat",),
        granted_capabilities=("knowledge.read",),
    )


# ═══════════════════════════ C1 生产路径零测试包导入 ═══════════════════════════


def test_c1_runtime_src_zero_tests_import_ast() -> None:
    """AST 扫描：runtime 全部模块的 Import / ImportFrom 顶层包 ≠ tests。"""
    assert _RUNTIME_PY, "扫描面为空：src/engine_v2/runtime/*.py 必须非空"
    for path in _RUNTIME_PY:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] != "tests", (
                        path.name,
                        alias.name,
                    )
            elif isinstance(node, ast.ImportFrom):
                assert (node.module or "").split(".")[0] != "tests", (
                    path.name,
                    node.module,
                )


def test_c1_runtime_src_zero_tests_import_literals_strict() -> None:
    """严格字面双查：runtime 全部源文本不含禁用字面串（docstring 同查，
    T1 教训面）。T11 首验发现的 L3 违例（context / dynamics_binding /
    llm_binding 三处 docstring 字面）已在 Leader 修复窗修正 → 本测回归
    常规绿测试（原 xfail(strict) 标记已摘除）。"""
    for path in _RUNTIME_PY:
        text = path.read_text(encoding="utf-8")
        for literal in _FORBIDDEN_LITERALS:
            assert literal not in text, (path.name, literal)


def test_c1_sys_modules_delta_no_tests_after_trust_assembly() -> None:
    """delta sys.modules：trust=True 装配后差集不含 tests 开头模块
    （delta-based：本进程先前装配留下的 tests.* 测试包模块在 before 内，
    只有装配**新引入**的 tests 模块才进差集——真正的违例面）。"""
    before = set(sys.modules)
    result = assemble_project(COMPLEX_ROOT, trust_python=True)
    after = set(sys.modules)
    assert result.engine is not None
    offenders = _offenders(_module_delta(before, after), "tests")
    assert offenders == ()


# ═══════════════════════════ C2 未声明 .py 永不导入 ═══════════════════════════


def test_c2_undeclared_module_never_imported(tmp_path: Path) -> None:
    """tmp 副本 + 未声明 rogue.py（内容随意）→ trust=True 装配成功且
    差集 sys.modules 无 rogue（T3 零扫描面：import 只触声明的 entrypoint）。"""
    copy_root = tmp_path / "complex_minimal_copy"
    shutil.copytree(COMPLEX_ROOT, copy_root)
    rogue = copy_root / "complex_minimal" / "rogue.py"
    rogue.write_text(
        "MARKER = 1  # C2：未被 plugin.yaml/pyproject 声明，必须永不导入\n",
        encoding="utf-8",
    )
    before = set(sys.modules)
    result = assemble_project(copy_root, trust_python=True)
    after = set(sys.modules)

    assert result.engine is not None, result.diagnostics
    # 声明的 entrypoint 正常装载（对照面：rogue 缺席是选择性，非全禁）
    assert {"inject_heat", "cool", "toggle_machine"} <= set(result.instance.executors)
    assert _offenders(
        _module_delta(before, after), "rogue", "complex_minimal.rogue"
    ) == ()


# ═══════════════════════════ C3 trust 门 ═══════════════════════════


def test_c3_trust_gate_engine_still_assembles() -> None:
    """trust=False → engine 非 None + LLMSIM_PLUGIN_ENTRY_UNRESOLVED 诊断
    （message 提 trust_python）+ 差集 sys.modules 无 complex_minimal 前缀
    （T3 零 import 面）+ executors 无 cool（标准面 move 恒在）。"""
    before = set(sys.modules)
    result = assemble_project(COMPLEX_ROOT, trust_python=False)
    after = set(sys.modules)

    assert result.engine is not None
    assert result.instance is not None
    trust_errors = [
        d for d in result.diagnostics if d.code == "LLMSIM_PLUGIN_ENTRY_UNRESOLVED"
    ]
    assert trust_errors
    assert all(d.severity == DiagnosticSeverity.ERROR for d in trust_errors)
    assert all("trust_python" in d.message for d in trust_errors)
    assert _offenders(_module_delta(before, after), "complex_minimal") == ()
    assert "cool" not in result.instance.executors
    assert "move" in result.instance.executors  # 标准面恒在（对照）


# ═══════════════════════════ C4 扩展面在场 ═══════════════════════════


def test_c4_extension_surface_present() -> None:
    """trust=True → 三自定义 executor 在场（同一实例注册在 3 个 id 下，
    T10 绑定口径）+ dynamics ≥1 且 backend_id = complex_minimal.boiler_thermal。"""
    result = _assemble_trust()
    assert result.engine is not None
    assert {"inject_heat", "cool", "toggle_machine"} <= set(result.instance.executors)
    # T10 冻结面：单个 BoilerMachineExecutor 实例注册在全部 3 个 action id 下
    assert result.instance.executors["inject_heat"] is result.instance.executors["cool"]
    assert result.instance.executors["cool"] is result.instance.executors["toggle_machine"]
    assert len(result.instance.dynamics) >= 1
    assert result.instance.dynamics[0].metadata().backend_id == (
        "complex_minimal.boiler_thermal"
    )


# ═══════════════════════════ C5 自定义动作走权威管道 ═══════════════════════════


def test_c5_inject_heat_commit_success_bootstrap() -> None:
    """C5：``submit_action(operator, inject_heat, {})``——executor 不收参数
    （T10 ``BoilerMachineExecutor.execute`` 按 action_id 分派，arguments
    零消费），空参合法。

    **实际路径 = 成功提交**（修复窗 F1：machine 组件缺位 → power 取 schema
    缺省 DEFAULT_POWER=2 自举，首个动作经管道落位组件）：ok + 零诊断 +
    machine power 2→3 + 恰 1 COMMITTED txn + revision 0→1（C6 风格口径）。
    拒绝分支保留为防御性文档面：任何回归下的拒绝必须显式诊断、零静默、
    世界与 revision 原样。
    """
    result = _assemble_trust()
    engine = result.engine
    before_rev = result.instance.world.world_revision
    sr = engine.submit_action(PLAYER_ENTITY, "inject_heat", {})

    if sr.ok:
        # 实际路径（F1 自举）：零诊断 + machine.power 2→3 + 恰 1 COMMITTED
        # txn + revision 恰 +1（base/commit 口径同 C6）
        assert sr.diagnostics == ()
        machine = engine.instance.world.entities[EntityId(BOILER_ENTITY)].components.get(
            "machine"
        )
        assert machine is not None and machine["power"] == 3
        committed = [
            t for t in sr.transactions if t.status is TransactionStatus.COMMITTED
        ]
        assert len(committed) == 1
        assert committed[0].base_revision == before_rev
        assert committed[0].commit_revision == before_rev.next()
        assert int(sr.world_revision) == int(before_rev) + 1
    else:
        # 防御性文档面（修复窗后不可达）：拒绝必须显式诊断，零静默
        assert sr.diagnostics, "拒绝必须显式诊断，零静默"
        assert all(
            d.startswith("action_failed:inject_heat:") for d in sr.diagnostics
        ), sr.diagnostics
        assert sr.transactions == ()
        assert sr.world_revision == before_rev
        assert (
            engine.instance.world.entities[EntityId(BOILER_ENTITY)].components.get(
                "machine"
            )
            is None
        )


def test_c5_cool_commit_success_power_down() -> None:
    """C5 补充：``cool`` 走权威管道**成功提交**——修复窗 F2 单写权拆分：
    cool 语义改为 power−1（下限 0，越界显式 failure）；executor grant 只
    claim machine，temperature 归 dynamics 单写（授权规则集现为
    dynamics.temperature / actions.machine / actions.move.spaces，每组件
    恰 1 writer，原 A8 rule_deny 缺口消除）。machine 缺位 → F1 自举
    （2−1=1，首个动作经管道落位组件）。advance(1) 后 temperature=24.0
    不变面保留断言（cool 不再写 temperature；dynamics 该 tick 已按
    power=2 积分落位）。"""
    result = _assemble_trust()
    engine = result.engine
    engine.advance(1)  # 相位 3 dynamics 落位 temperature = 24.0（power 自举 2）
    before_rev = engine.instance.world.world_revision
    assert _temperature(result.instance) == {"celsius": pytest.approx(24.0, abs=1e-9)}
    sr = engine.submit_action(PLAYER_ENTITY, "cool", {})

    assert sr.ok is True
    assert sr.diagnostics == ()
    machine = engine.instance.world.entities[EntityId(BOILER_ENTITY)].components.get(
        "machine"
    )
    assert machine is not None and machine["power"] == 1  # 自举 2 → 1
    committed = [t for t in sr.transactions if t.status is TransactionStatus.COMMITTED]
    assert len(committed) == 1
    assert committed[0].base_revision == before_rev
    assert committed[0].commit_revision == before_rev.next()
    assert str(committed[0].effects[0].effect.source) == "complex_minimal.actions"
    assert sr.world_revision == before_rev.next()
    # temperature 不变面：cool 不再写 temperature（F2）
    assert _temperature(engine.instance) == {"celsius": pytest.approx(24.0, abs=1e-9)}


# ═══════════════════════════ C6 dynamics 进 tick 并提交 ═══════════════════════════


def test_c6_dynamics_tick_commit() -> None:
    """fresh 装配 advance(1) → temperature 缺省 20.0 → 24.0（精确值：
    20 + 0.2·(12 + 14·power − 20)·dt，power 缺省 2、dt=1.0；round 6 位
    后恰 24.0，保险用 approx）+ 事务非空 + revision 0→1 + 零诊断。
    组件缺位时 dynamics 首次 tick 自动落位 schema 缺省（T10 契约面）。"""
    result = _assemble_trust()
    engine = result.engine
    assert _temperature(result.instance) is None  # authoring 面不物化 temperature
    sr = engine.advance(1)

    assert sr.ok is True
    assert sr.diagnostics == ()
    assert _temperature(result.instance) == {"celsius": pytest.approx(24.0, abs=1e-9)}
    assert sr.world_revision == Revision(1)
    committed = [t for t in sr.transactions if t.status is TransactionStatus.COMMITTED]
    assert len(committed) == 1
    assert committed[0].base_revision == Revision(0)
    assert committed[0].commit_revision == Revision(1)


# ═══════════════════════════ C7 NPC 经 P6 LLMPolicy ═══════════════════════════


def test_c7_engine_loop_policy_full_chain() -> None:
    """C7：engine 循环（wake + advance）**全链通过**——NPC 经 P6 LLMPolicy
    产 ActionProposal 并走同一管道提交。

    修复窗三缺口全补：G1（assembly 步 12 将 policies 键重映射为
    ``ent_authoring_<slug>`` 世界实体 id，T2 engine 契约）+ G2
    （``JsonCleanContextPolicyAdapter``：decide 前探测 13 个
    CONTEXT_VARIABLES JSON-clean，不可序列化字段以影子 context 置 None，
    全 clean 原实例直通）+ F3（样例 prompt 变量回归封闭集）→
    wake + advance：decide 命中脚本（base_rev = 装配后 rev 运行时动态
    读取，seq=1）→ inject_heat 提交（power 自举 2→3）→ 同 tick 相位 3
    dynamics 按 power=3 积分（20.0 → 20+0.2·(12+42−20)·1 = 26.8）→
    2 COMMITTED txns + sink prompt_assembly/llm_call 两事件 + 双跑字节相等。
    """
    # 卡面纪律：base_revision 运行时动态读取（硬编码数字 = 脆）
    probe = _assemble_llm(FakeInferenceBackend())
    base_rev = probe.instance.world.world_revision  # 动态读取（装配后 = 0）
    result, backend, sr = _c7_chain(base_rev)
    inst = result.instance

    # 绑定面（G1 修复后）：policies 键 = 世界实体 id；adapter 包裹 +
    # resolved 透传（LLMPolicy 本体不再直接外露）
    assert list(inst.policies) == [WATCHMAN_ENTITY]
    policy = inst.policies[WATCHMAN_ENTITY]
    assert isinstance(policy, JsonCleanContextPolicyAdapter)
    assert policy.resolved.model_id == "m-test-1"

    # 全链：ok + 零诊断 + 恰 1 次推理调用（脚本命中，base = 装配后 rev）
    assert sr.ok is True
    assert sr.diagnostics == ()
    assert len(backend.calls) == 1
    assert backend.calls[0].logical_role == "npc_policy"
    assert backend.calls[0].base_revision == base_rev
    # machine：策略笔 power 自举 2→3（F1）；temperature：dynamics 笔
    # 按 power=3 积分
    machine = inst.world.entities[EntityId(BOILER_ENTITY)].components.get("machine")
    assert machine is not None and machine["power"] == 3
    assert _temperature(inst) == {"celsius": pytest.approx(26.8, abs=1e-9)}
    # 2 COMMITTED txns + revision 0→2
    committed = [t for t in sr.transactions if t.status is TransactionStatus.COMMITTED]
    assert len(committed) == 2
    assert sr.world_revision == base_rev.next().next()
    # sink：prompt_assembly + llm_call 两事件（顺序 = 组装 → 调用）
    sink = inst.trace_sink
    assert [ev.kind for ev in sink.records] == ["prompt_assembly", "llm_call"]
    assert [d.code for d in sink.diagnostics] == []
    assert sorted(sink.artifacts) == [
        "output://" + WATCHMAN_ENTITY + ":0:0",
        "prompt://" + WATCHMAN_ENTITY + ":0:0",
    ]
    # 双跑字节相等（K7）：第二次全新全链 → dump_json 相等
    result2, backend2, sr2 = _c7_chain(base_rev)
    assert sr2.ok is True and sr2.diagnostics == ()
    assert backend2.calls == backend.calls
    assert dump_json(result2.instance.world) == dump_json(inst.world)


def test_c7_policy_decide_real_context_proposal() -> None:
    """C7 补充：真实 T4 context → ``decide`` 正常返回（G2 修复面）。

    T11 首验发现的 G2 缺口（真实 context 的 ``granted_capabilities`` =
    ``frozenset[Capability]``，assembler 无条件 json.dumps 必抛 ValueError）
    已在修复窗补上：
    ``JsonCleanContextPolicyAdapter`` decide 前探测 13 个
    CONTEXT_VARIABLES 的 JSON-clean 性（与 assembler
    ``context_variable_value`` 完全同口径的 dumps 参数），不可序列化
    字段以 ``dataclasses.replace`` 影子 context 置 ``None``（assembler
    渲染字面 "null"——与 global_entity_views 未授权同款 K4 不泄漏面），
    全 clean 原实例直通。本测钉：真实 context（富类型字段在场，
    ``type is frozenset`` 显式断言 G2 回归面）decide 不抛；脚本命中
    → 提案（actor_id = 世界实体 id、origin = BEHAVIOR_POLICY、
    producer = ``llm:<actor>``）。脚本缺席 → 默认 null no-op 见
    兄弟测试（JSON-native 面）。"""
    probe = _assemble_llm(FakeInferenceBackend())
    base_rev = probe.instance.world.world_revision
    backend = FakeInferenceBackend(
        script={("npc_policy", base_rev, 1): INJECT_SCRIPT}
    )
    result = _assemble_llm(backend)
    # 真实 T4 context（富类型字段在场——G2 回归面显式断言）
    ctx = build_actor_context(result.instance, WATCHMAN_ENTITY)
    assert type(ctx.granted_capabilities) is frozenset

    proposal = result.instance.policies[WATCHMAN_ENTITY].decide(ctx)
    assert proposal is not None  # 脚本命中：合法提案，非异常
    assert str(proposal.actor_id) == WATCHMAN_ENTITY
    assert str(proposal.action_id) == "inject_heat"
    assert proposal.provenance.origin is OriginKind.BEHAVIOR_POLICY
    assert str(proposal.provenance.producer_id) == "llm:" + WATCHMAN_ENTITY
    assert len(backend.calls) == 1


def test_c7_policy_decide_json_native_context_noop() -> None:
    """C7 补充：JSON-native context + 脚本缺席 → 合法 no-op（F3 修复面）。

    T11 首验发现的样例缺口 G3（watchman_scene.yaml 声明变量不在 P6
    CONTEXT_VARIABLES 封闭集 → 3 条 VARIABLE_UNSUPPORTED → package None）
    已在修复窗修正：模板变量集重写为封闭集成员（actor_id / tick /
    wake_reason / candidate_actions）。本测钉 no-op 合法面：空脚本 →
    decide 走默认 ``{"action_id": null}`` → None（B-CON-3，非异常）；
    no-op 分支 sink 面 = 仅 1 条 ``llm_call`` 事件（无 prompt_assembly、
    无 assembly_failed），诊断通道零记录。"""
    result = _assemble_llm(FakeInferenceBackend())  # 空脚本：decide 走默认
    base_rev = result.instance.world.world_revision
    ctx = _minimal_json_native_context(WATCHMAN_ENTITY, base_rev)

    proposal = result.instance.policies[WATCHMAN_ENTITY].decide(ctx)
    assert proposal is None  # 合法 no-op（B-CON-3），非异常

    sink = result.instance.trace_sink
    assert [ev.kind for ev in sink.records] == ["llm_call"]
    llm_call = sink.records[0].to_dict()["payload"]
    assert llm_call["logical_role"] == "npc_policy"
    assert llm_call["parse_retry"] == 0
    assert llm_call["base_revision"] == int(base_rev)
    assert [d.code for d in sink.diagnostics] == []  # F3：不再有 VARIABLE_UNSUPPORTED


# ═══════════════════════════ C8 同一管道 provenance ═══════════════════════════


def test_c8_commit_provenance_surface() -> None:
    """C8：同一管道提交 provenance 面——修复窗后 C7 提交**可观察**。

    分层口径（T2 assumption 7：事务装配者 ≠ 各 effect 提案者，
    engine.py:108-117）：
    - 事务级：两笔提交 ``provenance = engine / SYSTEM``；
    - effect 级：NPC 动作笔（相位 2，先）``source =
      complex_minimal.actions``，cause 含 ``PROPOSAL`` ref（→ P6 提案，
      其 origin = behavior_policy、producer = ``llm:<actor>``）；
      dynamics 笔（相位 3，后）``source = complex_minimal.dynamics``、
      无 cause；
    - 卡面期望 ``behavior_policy`` origin 在 P6 提案构造面（
      ``make_action_proposal`` 钉 origin=BEHAVIOR_POLICY，
      llm/structured.py:206）——本测以 P6 冻结面直构确定性钉死该
      origin 词表与 producer 命名（``llm:<actor_id>``）。
    """
    probe = _assemble_llm(FakeInferenceBackend())
    base_rev = probe.instance.world.world_revision
    result, _backend, sr = _c7_chain(base_rev)

    committed = [t for t in sr.transactions if t.status is TransactionStatus.COMMITTED]
    assert len(committed) == 2
    # 事务级：引擎装配者（两笔同口径，T2 assumption 7 钉面）
    assert all(
        str(t.provenance.producer_id) == "engine"
        and t.provenance.origin is OriginKind.SYSTEM
        for t in committed
    )
    # effect 级：NPC 动作笔（机载 power 自举 2→3；cause 含 PROPOSAL ref）
    machine_txn = committed[0]
    machine_effect = machine_txn.effects[0].effect
    assert str(machine_effect.source) == "complex_minimal.actions"
    assert str(machine_effect.target.component_type) == "machine"
    assert machine_effect.payload == {"power": 3}
    assert machine_effect.cause_ids
    assert any(c.kind is CauseKind.PROPOSAL for c in machine_effect.cause_ids)
    assert all(str(c.ref_id).startswith("act_") for c in machine_effect.cause_ids)
    assert machine_txn.base_revision == base_rev
    assert machine_txn.commit_revision == base_rev.next()
    # effect 级：dynamics 笔（按 power=3 积分 20.0 → 26.8；无 cause）
    dyn_txn = committed[1]
    dyn_effect = dyn_txn.effects[0].effect
    assert str(dyn_effect.source) == "complex_minimal.dynamics"
    assert dyn_effect.payload == {"celsius": pytest.approx(26.8, abs=1e-9)}
    assert dyn_effect.cause_ids == []
    assert dyn_txn.base_revision == base_rev.next()
    assert dyn_txn.commit_revision == base_rev.next().next()

    # 卡面期望 origin 的词表钉 + P6 提案构造面（behavior_policy 在提案层）
    assert OriginKind.BEHAVIOR_POLICY.value == "behavior_policy"
    wire = LLMActionProposal(action_id="inject_heat")
    ctx = _minimal_json_native_context(WATCHMAN_ENTITY, base_rev)
    proposal = make_action_proposal(ctx, wire)
    assert proposal.provenance.origin is OriginKind.BEHAVIOR_POLICY
    assert str(proposal.provenance.producer_id) == "llm:" + WATCHMAN_ENTITY
    assert str(proposal.action_id) == "inject_heat"


# ═══════════════════════════ C9 上下文可见性 + 场景视图 + 双跑 ═══════════════════════════


def test_c9a_actor_context_visibility() -> None:
    """C9(a)：``build_actor_context(instance, watchman)`` →
    ``global_entity_views is None``（T4 结果钉：默认能力表不授予
    world.read.global）+ watchman 自身在可见面（self_view + visible）。
    感知并集精确面（T4 物化 + 曼哈顿 L1 ≤ 视觉半径 5）：watchman(1,1)
    可见 boiler(3,1) / operator(2,2)；boiler_room 无位置声明 → 不可见。
    candidate_actions 含 3 个扩展动作（T6 注册面投影）。"""
    result = _assemble_trust()
    ctx = build_actor_context(result.instance, WATCHMAN_ENTITY)

    assert ctx.actor_id == EntityId(WATCHMAN_ENTITY)
    assert ctx.global_entity_views is None
    assert ctx.self_view is not None
    assert ctx.actor_id in ctx.visible_entities
    assert {str(e) for e in ctx.visible_entities} == {
        WATCHMAN_ENTITY,
        BOILER_ENTITY,
        PLAYER_ENTITY,
    }
    assert {str(a) for a in ctx.candidate_actions} == {
        "cool",
        "drop",
        "inject_heat",
        "inspect",
        "move",
        "pickup",
        "talk",
        "toggle_machine",
        "wait",
    }


def test_c9b_scene_view_face() -> None:
    """C9(b)：``engine.view()`` → 10 个顶层键（P10 冻结面）+
    view_revision 与权威 world_revision 一致；machine/temperature 组件
    数据在场 = **权威世界面**（SceneView 按 P10 设计不携带组件载荷：
    actors 面 = id/name/position/mood/tags，且 authoring 实体 tags=[] →
    actors 空；卡面「组件数据在场」在视图自身不成立，钉权威面 + 注释）。
    machine 组件缺席 = dynamics 只落 temperature（machine 的落位入口 =
    首个动作 F1 自举；本测 headless 装配无策略笔，advance 后缺席，
    C5 同源面）。"""
    result = _assemble_trust()
    result.engine.advance(1)
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
    # 组件数据在场（权威世界面）：temperature 已提交；machine 缺席（文档化）
    assert _temperature(result.instance) == {"celsius": pytest.approx(24.0, abs=1e-9)}
    assert (
        result.instance.world.entities[EntityId(BOILER_ENTITY)].components.get(
            "machine"
        )
        is None
    )


def test_c9c_double_run_byte_equal() -> None:
    """C9(c) 完整双跑：两次全新装配（同参数，含 fake 脚本）+ 相同
    advance(1) + 相同 submit_action 序列 → ``dump_json(world)`` 字节相等
    + sink 逐事件 ``to_dict()`` 记录相等 + artifacts + sink 诊断全等。

    序列（两次逐字相同）：装配（script 键 = 探针装配动态读的 base_rev，
    seq=1）→ wake watchman → advance(1)（**engine 循环命中脚本**——
    策略笔 power 自举 2→3 提交 + dynamics 按 power=3 积分 26.8，
    rev 0→2）→ JSON-native context 直驱 decide（seq=2 → 脚本缺席 →
    默认 no-op，sink 追加 1 条 llm_call——LLM 面进双跑比较）→
    submit_action(inject_heat {})（power 3→4 提交，F1）→
    submit_action(cool {})（power 4→3 提交，F2 语义）。

    注：StepResult.diagnostics 串**不**进比较面（本序列全绿、零诊断，
    保留该口径备回归时 uuid 串不脆）；gate 面 = 世界字节 + sink 记录。
    uuid effect id（玩家 submit 的提案 id 派生）不持久化进世界面
    （WorldState = entities/world_variables/revision/scenario_state），
    故 dump_json 字节相等成立。
    InMemoryTraceSink 无 sink 级 to_dict（T8 面：逐事件 TraceEvent.
    to_dict()）——卡面「to_dict() sink 记录」按该冻结面执行。
    """

    def one_run() -> tuple[str, list, dict, list]:
        probe = _assemble_llm(FakeInferenceBackend())
        base_rev = probe.instance.world.world_revision  # 运行时动态读取
        backend = FakeInferenceBackend(
            script={("npc_policy", base_rev, 1): INJECT_SCRIPT}
        )
        result = _assemble_llm(backend)
        engine = result.engine
        engine.wake(WATCHMAN_ENTITY, reason="e2e_c9")
        engine.advance(1)
        ctx = _minimal_json_native_context(WATCHMAN_ENTITY, base_rev)
        result.instance.policies[WATCHMAN_ENTITY].decide(ctx)
        engine.submit_action(PLAYER_ENTITY, "inject_heat", {})
        engine.submit_action(PLAYER_ENTITY, "cool", {})
        sink = result.instance.trace_sink
        return (
            dump_json(result.instance.world),
            [ev.to_dict() for ev in sink.records],
            dict(sink.artifacts),
            [d.model_dump(mode="json") for d in sink.diagnostics],
        )

    first, second = one_run(), one_run()
    assert first[0] == second[0]  # 世界 dump_json 字节相等
    assert first[1] == second[1]  # sink 记录（逐事件 to_dict）相等
    assert first[2] == second[2]  # artifacts 相等
    assert first[3] == second[3]  # sink 诊断通道相等
