"""T6 ``runtime/action_binding.py`` 单元测试（Runtime Closure T6 Gate）。

覆盖 Gate（冻结）：

1. IR 含 3 个 declared actions → ``registry.lookup`` 全非 None + spec 字段
   面正确（executor 串 / duration kind none / interruptible / tags）；
2. bundle（duck stub：``action_executors={"cool": stub}``、
   ``producer_grants=(ProducerGrant 形状对象,)``）→ ``executors["cool"] is
   stub`` + grants 透传验证（字段逐值）；
3. 未绑执行器的标准动作（``"talk"``）→ 不在 ``executors`` 映射（不崩）+
   registry 有 spec + ``"p9.executor-missing"`` 标记存在；
4. ``executors["move"]`` 存在（``MoveExecutor``）+ 其 producer（
   ``actions.move``）的 grant 存在（producer_id 词法合法 +
   ``component_types`` 含 spaces 组件名 + priority 50）；
5. src 侧零 ``tests.*`` import（本模块 AST 机械扫描）。

另覆盖：project 重 id = error + 跳过 / project id 撞 standard id = error
+ 标准 spec 保留 / grant producer_id 词法违例 = error + 丢弃 / extension
executor 覆盖 = warning 显式诊断 / 无 bundle 缺省面。

全部用例无网络、无 LLM、无 API key；确定性（零随机/零墙钟）。
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from src.engine_v2.content.schemas import DiagnosticSeverity
from src.engine_v2.core.action_registry import ActionRegistry
from src.engine_v2.core.actions import ActionTypeId
from src.engine_v2.core.ids import PRODUCER_ID_PATTERN
from src.engine_v2.core.space import (
    GridSpace,
    SPACES_COMPONENT,
    SpaceRegistry,
    SpatialDomain,
)
from src.engine_v2.modules.actions import ExecutorResult, MoveExecutor
from src.engine_v2.runtime.action_binding import ActionBindingResult, bind_actions

from tests.engine_v2.content.conftest import make_action_spec, make_ir

REPO_ROOT = Path(__file__).resolve().parents[3]
_ACTION_BINDING_PATH = REPO_ROOT / "src" / "engine_v2" / "runtime" / "action_binding.py"


# —— duck stubs（contract §3 T6 卡：bundle 侧可传 duck-typed stub 对象）——


@dataclass(frozen=True)
class _StubExecutor:
    """ActionExecutor 协议 stub（execute 面确定性 failure，零副作用）。"""

    label: str = "stub"

    def execute(self, proposal: Any, world: Any, tick: int) -> ExecutorResult:
        return ExecutorResult((), f"{self.label} stub 执行失败（确定性面）", 0)


@dataclass(frozen=True)
class _StubGrant:
    """ProducerGrant 形状 stub（字段 = contract §3 逐字）。"""

    producer_id: str
    component_types: tuple[str, ...]
    priority: int = 50


class _StubBundle:
    """ExtensionBundle duck stub（只持 T6 消费的两侧字段）。"""

    def __init__(
        self,
        action_executors: dict[str, _StubExecutor] | None = None,
        producer_grants: tuple[_StubGrant, ...] = (),
    ) -> None:
        self.action_executors = action_executors or {}
        self.producer_grants = producer_grants


# —— fixtures（模块级 helper，非 pytest fixture——同目录零共享 conftest 依赖）——


def _make_spaces() -> SpaceRegistry:
    """最小 grid 空间域（domain_id="world"，3x3）。"""
    domain = SpatialDomain(domain_id="world", backend_kind="grid", parameters={})
    return SpaceRegistry({"world": (domain, GridSpace(width=3, height=3))})


def _make_ir(action_ids: tuple[tuple[str, str], ...] = ()) -> Any:
    """ProjectIR 构造（action id/verb 对列表 → content ActionSpec 元组）。"""
    actions = tuple(make_action_spec(id=aid, name=aid, verb=verb) for aid, verb in action_ids)
    return make_ir(actions=actions)


def _grant_by_producer(result: ActionBindingResult, producer_id: str):
    """按 producer_id 取 grant（不存在 → None；多义时 = 测试构造缺陷）。"""
    matches = [g for g in result.producer_grants if getattr(g, "producer_id", None) == producer_id]
    assert len(matches) <= 1, f"producer_id {producer_id!r} grant 多义"
    return matches[0] if matches else None


def _diagnostics_by_code(result: ActionBindingResult, code: str):
    return [d for d in result.diagnostics if d.code == code]


# —— Gate 1：project-declared actions → registry 全量 + 字段面 ——


class TestProjectDeclaredActions:
    def test_three_declared_actions_all_registered_with_spec_face(self) -> None:
        """Gate 1：3 个 declared actions → lookup 全非 None + 字段面正确。"""
        result = bind_actions(_make_ir((("attack", "act"), ("rest", "sleep"), ("craft", "build"))), _make_spaces())

        assert isinstance(result.action_registry, ActionRegistry)
        for aid, verb in (("attack", "act"), ("rest", "sleep"), ("craft", "build")):
            spec = result.action_registry.lookup(ActionTypeId(aid))
            assert spec is not None, f"declared action {aid!r} 未注册"
            assert str(spec.action_id) == aid
            assert spec.executor == f"llmsim-project-actions.{aid}"
            assert spec.parameters == {}
            assert spec.duration_policy.kind == "none"
            assert spec.interruptible is True
            assert spec.completion_trigger is None
            assert spec.tags == ["project", verb]

        # 标准面 6 动作与 project 面并存（3 + 6 = 9 键，键唯一）
        assert len(result.action_registry.specs) == 9

    def test_duplicate_project_id_error_and_skip(self) -> None:
        """project 重 id → error 诊断 + 跳过（registry 键唯一）。"""
        ir = _make_ir((("attack", "act"), ("attack", "act")))
        result = bind_actions(ir, _make_spaces())

        spec = result.action_registry.lookup(ActionTypeId("attack"))
        assert spec is not None
        assert len(result.action_registry.specs) == 7  # 6 standard + 1 attack
        dupes = _diagnostics_by_code(result, "LLMSIM_DUPLICATE_ID")
        assert len(dupes) == 1
        assert dupes[0].severity is DiagnosticSeverity.ERROR
        assert dupes[0].path == "attack"

    def test_project_id_colliding_with_standard_id_error_and_keep_standard(self) -> None:
        """project id 撞 standard id（"move"）→ error + 跳过，标准 spec 保留。"""
        ir = _make_ir((("move", "go"),))
        result = bind_actions(ir, _make_spaces())

        spec = result.action_registry.lookup(ActionTypeId("move"))
        assert spec is not None
        assert "p9-standard-actions" in spec.tags  # 标准 spec 未被顶替
        dupes = _diagnostics_by_code(result, "LLMSIM_DUPLICATE_ID")
        assert len(dupes) == 1
        assert dupes[0].path == "move"


# —— Gate 2：bundle duck stub → extension executors + grants 透传 ——


class TestExtensionBundle:
    def test_extension_executors_merged_and_grants_passed_through(self) -> None:
        """Gate 2：executors["cool"] is stub + grants 透传（字段逐值）。"""
        stub = _StubExecutor(label="cool")
        grant = _StubGrant(producer_id="ext.cool", component_types=("coolness",), priority=70)
        result = bind_actions(
            _make_ir(),
            _make_spaces(),
            bundle=_StubBundle(action_executors={"cool": stub}, producer_grants=(grant,)),
        )

        assert result.executors["cool"] is stub
        passed = _grant_by_producer(result, "ext.cool")
        assert passed is not None, "bundle grant 未透传"
        assert passed.component_types == ("coolness",)
        assert passed.priority == 70
        # 透传后对象为解析类（T3 缺席窗口 = 结构等价替代；字段面 contract §3）
        assert type(passed).__name__ in ("ProducerGrant", "_FallbackProducerGrant")
        assert isinstance(result.producer_grants, tuple)
        assert not _diagnostics_by_code(result, "LLMSIM_SCHEMA")

    def test_extension_executor_override_conflict_warning(self) -> None:
        """extension executor 撞 standard 已绑 id（"move"）→ 覆盖 + warning 显式诊断。"""
        stub = _StubExecutor(label="rogue-move")
        result = bind_actions(
            _make_ir(),
            _make_spaces(),
            bundle=_StubBundle(action_executors={"move": stub}),
        )

        assert result.executors["move"] is stub
        warnings = _diagnostics_by_code(result, "LLMSIM_MODULE_CONFLICT")
        assert len(warnings) == 1
        assert warnings[0].severity is DiagnosticSeverity.WARNING
        assert warnings[0].path == "move"

    def test_grant_producer_id_violation_error_and_drop(self) -> None:
        """grant producer_id 词法违例 → error + 丢弃该条；合法条保留。"""
        bad = _StubGrant(producer_id="Bad-Id", component_types=("x",))
        good = _StubGrant(producer_id="ext.ok", component_types=("y",))
        result = bind_actions(
            _make_ir(),
            _make_spaces(),
            bundle=_StubBundle(producer_grants=(bad, good)),
        )

        assert _grant_by_producer(result, "Bad-Id") is None
        assert _grant_by_producer(result, "ext.ok") is not None
        # move 自产 grant 不受影响
        assert _grant_by_producer(result, "actions.move") is not None
        errors = _diagnostics_by_code(result, "LLMSIM_SCHEMA")
        assert len(errors) == 1
        assert errors[0].severity is DiagnosticSeverity.ERROR
        assert "Bad-Id" in errors[0].message

    def test_real_producer_grant_instance_passes_through_unchanged(self) -> None:
        """T3 就位时：bundle 携带真 ProducerGrant 实例 → 原样透传（同一对象）。"""
        extensions = pytest.importorskip(
            "src.engine_v2.runtime.extensions",
            reason="T3 模块缺席窗口（并行开发中）——真类透传分支由结构等价面覆盖",
        )
        real = extensions.ProducerGrant(
            producer_id="real.grant", component_types=("spaces",), priority=10,
        )
        result = bind_actions(
            _make_ir(),
            _make_spaces(),
            bundle=_StubBundle(producer_grants=(real,)),
        )
        passed = _grant_by_producer(result, "real.grant")
        assert passed is real  # 原样透传，非重建


# —— Gate 3：未绑执行器的标准动作 ——


class TestStandardActionsWithoutExecutors:
    def test_talk_declared_but_unbound(self) -> None:
        """Gate 3："talk" 不在 executors（不崩）+ registry 有 spec + p9 标记。"""
        result = bind_actions(_make_ir(), _make_spaces())

        assert "talk" not in result.executors
        spec = result.action_registry.lookup(ActionTypeId("talk"))
        assert spec is not None
        assert "p9.executor-missing" in spec.tags
        assert spec.tags[0] == "p9-standard-actions"

    def test_only_move_bound_among_standard_actions(self) -> None:
        """五个无 production executor 的标准动作全不绑（本轮零实现）。"""
        result = bind_actions(_make_ir(), _make_spaces())

        assert set(result.executors) == {"move"}
        for aid in ("talk", "inspect", "pickup", "drop", "wait"):
            assert aid not in result.executors
            spec = result.action_registry.lookup(ActionTypeId(aid))
            assert spec is not None
            assert "p9.executor-missing" in spec.tags


# —— Gate 4：move executor + 自产 grant ——


class TestMoveExecutorGrant:
    def test_move_bound_as_move_executor(self) -> None:
        """Gate 4a：executors["move"] = MoveExecutor（构造面参数序确认）。"""
        spaces = _make_spaces()
        result = bind_actions(_make_ir(), spaces)

        move = result.executors["move"]
        assert isinstance(move, MoveExecutor)
        assert move.space is spaces
        assert move.domain == "world"

    def test_custom_domain_id_flows_into_move_executor(self) -> None:
        """domain_id kwarg 透传 MoveExecutor.domain。"""
        domain = SpatialDomain(domain_id="city", backend_kind="grid", parameters={})
        spaces = SpaceRegistry({"city": (domain, GridSpace(width=2, height=2))})
        result = bind_actions(_make_ir(), spaces, domain_id="city")

        move = result.executors["move"]
        assert isinstance(move, MoveExecutor)
        assert move.domain == "city"

    def test_move_grant_shape(self) -> None:
        """Gate 4b：actions.move grant 存在 + producer_id 词法合法 +
        component_types 含 spaces 组件名 + priority 50。"""
        result = bind_actions(_make_ir(), _make_spaces())

        grant = _grant_by_producer(result, "actions.move")
        assert grant is not None, "MoveExecutor 自产 grant 缺失"
        assert PRODUCER_ID_PATTERN.fullmatch(grant.producer_id), (
            f"producer_id {grant.producer_id!r} 词法非法"
        )
        assert str(SPACES_COMPONENT) in grant.component_types
        assert grant.component_types == ("spaces",)
        assert grant.priority == 50

    def test_grants_without_bundle_is_exactly_move_grant(self) -> None:
        """无 bundle 缺省面：grants 恰 1 条（move 自产）；零诊断。"""
        result = bind_actions(_make_ir(), _make_spaces())

        assert len(result.producer_grants) == 1
        assert result.producer_grants[0].producer_id == "actions.move"
        assert result.diagnostics == ()


# —— Gate 5：src 侧零 tests.* import（AST 机械扫描）——


class TestImportBoundary:
    def test_no_tests_import_in_action_binding_src(self) -> None:
        """Gate 5：action_binding.py 全部 import（含函数内 lazy import）零 tests 根。"""
        tree = ast.parse(_ACTION_BINDING_PATH.read_text(encoding="utf-8"))
        offenders = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "tests" or alias.name.startswith("tests."):
                        offenders.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module == "tests" or module.startswith("tests."):
                    offenders.append(module)
        assert offenders == [], f"src 侧出现 tests.* import：{offenders!r}"
