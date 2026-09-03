"""T7 dynamics binding + dynamics-side grants 测试（计划 T7 Gate 1–4 + 语义钉死面）。

覆盖：

1. **Gate 1**：测试内 Python numerical backend stub（实现协议三方法；
   ``metadata()`` 返回合法 ``BackendMetadata``）；``simulate(snapshot, (),
   context)`` 返回 1 个合法 ``ProposedEffect``（``new_deterministic_effect_id``
   产 id / source=producer_id / ``StateDomainTarget`` 自洽）→
   ``bind_dynamics`` 的 ``producer_grants`` 含该 producer + domains 一致；
2. **Gate 2**：IR 含 2 条 rules → dynamics 不含 RuleDynamics + 2 条
   不可投影诊断（Leader 勘误定码：code = ``LLMSIM_SCHEMA`` ∈ P5 18 码闭集、
   severity=warning、refs=(rule.id, "world_rule")）；
3. **Gate 3**：``bundle=None`` 且 ``ir.rules=()`` → dynamics=() +
   grants=() + diagnostics=()（零噪音）；
4. **Gate 4**：两个 extension backends → 顺序 = bundle 声明序。

额外钉死面：``metadata()`` 抛 ``DynamicsError`` → error 诊断 + backend 保留
+ 无 grant；bundle 畸形（缺属性 / 非 tuple）→ ``LLMSIM_PLUGIN_ENTRY_INVALID``
显式 error 诊断不静默；同输入双跑结果相等（K7 确定性）；诊断
``model_dump(mode="json")`` JSON-clean；全部产出诊断码 ∈ 18 码闭集
（构造期 model_validator 机械强制，此处断言复核）。

自包含（不 import 其他测试 helper）：最小 ``ProjectIR`` / duck stub bundle /
stub backend 全部本文件构造。
"""

from __future__ import annotations

from src.engine_v2.content.schemas import (
    DIAGNOSTIC_CODES,
    Diagnostic,
    DiagnosticSeverity,
    PlayerSpec,
    ProjectIR,
    ProjectManifest,
    RuleSpec,
    ScenarioSpec,
    ScenarioTime,
)
from src.engine_v2.core.effects import ProposedEffect, StateDomainTarget
from src.engine_v2.core.serialization import assert_json_clean
from src.engine_v2.core.state import WorldState
from src.engine_v2.dynamics.backend import (
    BackendMetadata,
    DynamicsContext,
    DynamicsError,
    Stimulus,
    WorldSnapshot,
    new_deterministic_effect_id,
)
from src.engine_v2.runtime.dynamics_binding import (
    DynamicsBindingResult,
    bind_dynamics,
)

# —— 测试内 stub 面 ——


class NumericalStubBackend:
    """Python numerical backend stub（``WorldDynamicsBackend`` 协议三方法）。

    ``simulate`` 产恰 1 个合法 ``ProposedEffect``：id 经
    ``new_deterministic_effect_id``（K7 零 uuid4）；``source`` =
    producer_id；``target`` = ``StateDomainTarget``（与 ``metadata.domains``
    的 ``temperature`` 域自洽）。``fail_metadata=True`` 时 ``metadata()`` 抛
    ``DynamicsError``（实现缺陷面）。
    """

    def __init__(
        self,
        *,
        backend_id: str = "test.numerical",
        producer_id: str = "test.numerical",
        domains: tuple[str, ...] = ("temperature",),
        fail_metadata: bool = False,
    ) -> None:
        self._backend_id = backend_id
        self._producer_id = producer_id
        self._domains = domains
        self._fail_metadata = fail_metadata
        self.simulate_calls = 0

    def metadata(self) -> BackendMetadata:
        if self._fail_metadata:
            raise DynamicsError(f"simulated implementation defect in {self._backend_id}")
        return BackendMetadata(
            backend_id=self._backend_id,
            producer_id=self._producer_id,
            domains=self._domains,
            determinism="deterministic",
            implementation_type="numerical",
            fidelity="abstract",
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
        self.simulate_calls += 1
        assert stimuli == ()
        return (
            ProposedEffect(
                effect_id=new_deterministic_effect_id(
                    self._producer_id, "temperature", context.base_revision, 0
                ),
                effect_type="test.temperature_update",
                source=self._producer_id,
                target=StateDomainTarget(domain="temperature"),
                payload={"value": 21.5},
                base_revision=context.base_revision,
                cause_ids=[],
            ),
        )

    @property
    def diagnostics(self) -> tuple:
        return ()


class StubBundle:
    """``ExtensionBundle`` duck stub（T3 模块并行开发中；contract 要求
    dynamics_binding 不顶层 import、测试传 duck stub）。"""

    def __init__(self, dynamics_backends: tuple) -> None:
        self.dynamics_backends = dynamics_backends


class _BundleMissingBackends:
    """缺 ``dynamics_backends`` 属性的畸形 bundle（鸭子检查失败面）。"""


# —— 最小 IR / snapshot 构造器（自包含，最小合法面）——


def make_ir(rules: tuple[RuleSpec, ...] = ()) -> ProjectIR:
    """最小合法 ``ProjectIR``（manifest / scenario / player 必需面，rules 可注入）。"""
    return ProjectIR(
        manifest=ProjectManifest(
            schema_version="2", project_id="proj_t7", name="T7 Project"
        ),
        scenario=ScenarioSpec(
            id="scenario_main",
            max_ticks=10,
            ticks_per_game_minute=1.0,
            game_time=ScenarioTime(hour=9, minute=0),
        ),
        world=None,
        player=PlayerSpec(player_id="player_1", name="Wanderer"),
        rules=rules,
    )


def make_snapshot() -> WorldSnapshot:
    """空世界 ``WorldSnapshot``（Gate 1 simulate 调用面）。"""
    state = WorldState()
    return WorldSnapshot(
        world_state=state,
        world_revision=int(state.world_revision),
        logical_tick=0,
        world_instance_id="wi_t7",
    )


# —— Gate 1：numerical backend stub → 合法 ProposedEffect + grant 派生 ——


def test_gate1_numerical_backend_effect_and_grant() -> None:
    backend = NumericalStubBackend()
    context = DynamicsContext(base_revision=0)

    # simulate 返回 1 个合法 ProposedEffect（K7 确定性 id / source / target 自洽）
    effects = backend.simulate(make_snapshot(), (), context)
    assert len(effects) == 1
    effect = effects[0]
    assert str(effect.effect_id).startswith("eff_")
    assert len(str(effect.effect_id)) == len("eff_") + 32
    assert effect.source == "test.numerical"
    assert effect.target.kind == "state_domain"
    assert str(effect.target.domain) == "temperature"
    assert effect.payload == {"value": 21.5}
    assert int(effect.base_revision) == 0

    # K7：同参双跑 → 同 effect id（零 uuid4 / 零随机）
    again = backend.simulate(make_snapshot(), (), context)
    assert again[0].effect_id == effect.effect_id

    # bind_dynamics：grant 自动派生（producer + domains 一致）
    result = bind_dynamics(make_ir(), bundle=StubBundle((backend,)))
    assert isinstance(result, DynamicsBindingResult)
    assert result.dynamics == (backend,)
    assert len(result.producer_grants) == 1
    grant = result.producer_grants[0]
    assert grant.producer_id == "test.numerical"
    assert grant.component_types == ("temperature",)
    assert grant.priority == 50
    assert result.diagnostics == ()


# —— Gate 2：2 条 rules → 零 RuleDynamics + 2 条 LLMSIM_SCHEMA warning ——


def test_gate2_rules_not_projectable() -> None:
    ir = make_ir(
        rules=(
            RuleSpec(id="rule_a", condition="temperature > 30"),
            RuleSpec(id="rule_b", description="plain rule"),
        )
    )
    result = bind_dynamics(ir)

    # 不投影：零 dynamics backend（RuleDynamics 本轮不产出）、零 grant
    assert result.dynamics == ()
    assert result.producer_grants == ()

    # 2 条不可投影诊断：LLMSIM_SCHEMA（18 码闭集成员）+ warning + IR 序归因
    assert len(result.diagnostics) == 2
    for diag, rule_id in zip(result.diagnostics, ("rule_a", "rule_b")):
        assert isinstance(diag, Diagnostic)
        assert diag.code == "LLMSIM_SCHEMA"
        assert diag.code in DIAGNOSTIC_CODES
        assert diag.severity is DiagnosticSeverity.WARNING
        assert diag.path == rule_id
        assert diag.refs == (rule_id, "world_rule")
    # 文案确定性 + 说明 shape mismatch 与承接面（显式规则翻译器）；JSON-clean
    for diag in result.diagnostics:
        assert "WorldRule" in diag.message
        assert "shape mismatch" in diag.message
        assert "翻译器" in diag.message
        assert_json_clean(diag.model_dump(mode="json"))


# —— Gate 3：bundle=None 且 ir.rules=() → 零噪音 ——


def test_gate3_empty_ir_zero_noise() -> None:
    result = bind_dynamics(make_ir())
    assert result.dynamics == ()
    assert result.producer_grants == ()
    assert result.diagnostics == ()


# —— Gate 4：两个 extension backends → 顺序 = bundle 声明序 ——


def test_gate4_extension_backend_order_preserved() -> None:
    first = NumericalStubBackend(
        backend_id="test.first", producer_id="test.first", domains=("alpha",)
    )
    second = NumericalStubBackend(
        backend_id="test.second",
        producer_id="test.second",
        domains=("delta", "beta"),  # metadata 构造期排序去重 → ("beta", "delta")
    )
    result = bind_dynamics(make_ir(), bundle=StubBundle((second, first)))

    # dynamics 元组 = bundle 声明序（second 在前）
    assert result.dynamics == (second, first)
    # grants 与 dynamics 同源同序；domains 透传 metadata（排序后）
    assert [grant.producer_id for grant in result.producer_grants] == [
        "test.second",
        "test.first",
    ]
    assert result.producer_grants[0].component_types == ("beta", "delta")
    assert result.producer_grants[1].component_types == ("alpha",)
    assert result.diagnostics == ()


# —— 语义钉死面：metadata() 抛 DynamicsError → 保留 + 无 grant + error 诊断 ——


def test_metadata_failure_keeps_backend_without_grant() -> None:
    bad = NumericalStubBackend(
        backend_id="test.bad", producer_id="test.bad", fail_metadata=True
    )
    good = NumericalStubBackend()
    result = bind_dynamics(make_ir(), bundle=StubBundle((bad, good)))

    # backend 保留在 dynamics（simulate 面仍会暴露）
    assert result.dynamics == (bad, good)
    # 无 bad 的 grant（closed-by-default 会拒其 effect）
    assert [grant.producer_id for grant in result.producer_grants] == ["test.numerical"]
    # 恰 1 条 error 诊断：LLMSIM_SCHEMA（形状/契约违规面），归因 dynamics 槽位
    assert len(result.diagnostics) == 1
    diag = result.diagnostics[0]
    assert isinstance(diag, Diagnostic)
    assert diag.code == "LLMSIM_SCHEMA"
    assert diag.code in DIAGNOSTIC_CODES
    assert diag.severity is DiagnosticSeverity.ERROR
    assert diag.path == "dynamics[0]"
    assert diag.refs == ("NumericalStubBackend",)
    assert "closed-by-default" in diag.message
    assert_json_clean(diag.model_dump(mode="json"))


# —— 语义钉死面：bundle 畸形 → 显式 error 诊断不静默 ——


def test_malformed_bundle_missing_attribute() -> None:
    result = bind_dynamics(make_ir(), bundle=_BundleMissingBackends())
    assert result.dynamics == ()
    assert result.producer_grants == ()
    assert len(result.diagnostics) == 1
    diag = result.diagnostics[0]
    assert diag.code == "LLMSIM_PLUGIN_ENTRY_INVALID"
    assert diag.code in DIAGNOSTIC_CODES
    assert diag.severity is DiagnosticSeverity.ERROR


def test_malformed_bundle_non_tuple_backends() -> None:
    backend = NumericalStubBackend()
    result = bind_dynamics(make_ir(), bundle=StubBundle([backend]))  # list ≠ tuple
    assert result.dynamics == ()
    assert result.producer_grants == ()
    assert len(result.diagnostics) == 1
    assert result.diagnostics[0].code == "LLMSIM_PLUGIN_ENTRY_INVALID"
    assert result.diagnostics[0].severity is DiagnosticSeverity.ERROR


# —— K7：同输入双跑 → 结果相等（零墙钟 / 零随机 / 纯数据面）——


def test_deterministic_double_run() -> None:
    backend = NumericalStubBackend()
    bundle = StubBundle((backend,))
    ir = make_ir(rules=(RuleSpec(id="rule_x", match="interact"),))
    first = bind_dynamics(ir, bundle=bundle)
    second = bind_dynamics(ir, bundle=bundle)
    assert first == second
