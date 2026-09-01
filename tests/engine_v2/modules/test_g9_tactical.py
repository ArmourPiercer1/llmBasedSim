"""P9 W6 g9 tactical 样例切片测试（SOT §6.1 / §3.16.3；A12–A15 + A 前件）。

样例面（SOT §3.19 白名单行 41–45）：``tests/fixtures/
v2_project_tactical/``（game.yaml 含顶层 gameplay_modes 节 + 2 兵角色 +
actions 节 3 声明）；hex 网格不在 yaml 声明——空间域 = 测试侧经
``p9_host`` 工厂参数构造（3×3 odd-r，边表 = ``hex_adjacency`` 去重后
的无向集——G-INV 拒绝重复无向边）。

断言面 = SOT §8.2：A12（hex 边表/距离/方格对照/AD-P9-4 构造校验）/
A13（tactical overlay → merge_modes → attack 允许 / talk 拒绝）/
A14（attack 执行零推理 + 同输入同效果流，P9-INV-6）/ A15（探索→战术→
探索模式转移；单一 WorldState，tick 连续）/ A 前件（零 ERROR 加载）。
"""

from __future__ import annotations

import pytest

from src.engine_v2.content.loader import load_project
from src.engine_v2.content.project_ir import build_ir
from src.engine_v2.content.validator import validate_project
from src.engine_v2.core.actions import ActionProposal
from src.engine_v2.core.components import ComponentTypeId
from src.engine_v2.core.effects import EffectTypeId, EntityTarget, ProposedEffect
from src.engine_v2.core.gameplay_mode import (
    ModeChangeRequest,
    ModeOperation,
    ModeOperationKind,
    ModeOverlayRegistry,
    apply_mode_change,
    is_action_available,
    merge_modes,
)
from src.engine_v2.core.ids import EffectId, EntityId, ProducerId
from src.engine_v2.core.provenance import OriginKind, Provenance
from src.engine_v2.core.revision import Revision
from src.engine_v2.core.space import (
    GraphSpace,
    GridSpace,
    SpaceRegistry,
    decode_spaces,
)
from src.engine_v2.core.state import EntityRecord, WorldState
from src.engine_v2.modules import space as space_mod, tactical as tactical_mod
from src.engine_v2.modules.actions import ExecutorResult
from src.engine_v2.modules.space import (
    HexGrid,
    distance_between,
    hex_adjacency,
    register_standard_space,
)
from src.engine_v2.modules.tactical import (
    TACTICAL_ACTION_IDS,
    TacticalModePolicy,
    TacticalOverlaySpec,
    build_tactical_overlay,
)

_TACTICAL = "tests/fixtures/v2_project_tactical"
_SOLDIER_A = "ent_authoring_soldier_a"
_SOLDIER_B = "ent_authoring_soldier_b"
_PLAYER = "ent_authoring_player_1"

#: 3×3 odd-r hex 期望无向边集（16 边；常量钉——hex self-proof 证据面）。
_EXPECTED_3X3_EDGES: tuple[tuple[str, str], ...] = (
    ("hex_0_0", "hex_0_1"),
    ("hex_0_0", "hex_1_0"),
    ("hex_0_1", "hex_0_2"),
    ("hex_0_1", "hex_1_0"),
    ("hex_0_1", "hex_1_1"),
    ("hex_0_1", "hex_1_2"),
    ("hex_0_2", "hex_1_2"),
    ("hex_1_0", "hex_1_1"),
    ("hex_1_0", "hex_2_0"),
    ("hex_1_1", "hex_1_2"),
    ("hex_1_1", "hex_2_0"),
    ("hex_1_1", "hex_2_1"),
    ("hex_1_1", "hex_2_2"),
    ("hex_1_2", "hex_2_2"),
    ("hex_2_0", "hex_2_1"),
    ("hex_2_1", "hex_2_2"),
)


def _hex_nodes(cols: int = 3, rows: int = 3) -> list[str]:
    """节点表（col-major；与 host 世界构建面同序）。"""
    return [f"hex_{c}_{r}" for c in range(cols) for r in range(rows)]


def _hex_domain(cols: int = 3, rows: int = 3) -> GraphSpace:
    """hex 域 backend（有向边表 → 去重无向集；G-INV 面）。"""
    directed = hex_adjacency(HexGrid(cols=cols, rows=rows))
    deduped = sorted({(min(a, b), max(a, b)) for a, b in directed})
    return GraphSpace(_hex_nodes(cols, rows), deduped)


def _tactical_host(p9_host):
    """tactical 样例宿主（hex 域 ``tactical``；3×3 odd-r）。"""
    return p9_host(_TACTICAL, domain_id="tactical", backend=_hex_domain())


def _bfs_distance(edge_table: dict[str, tuple[str, ...]], start: str, target: str) -> int:
    """BFS 跳数（self-proof 交叉核验面；零第三方）。"""
    if start == target:
        return 0
    seen = {start}
    frontier = [start]
    hops = 0
    while frontier:
        hops += 1
        next_frontier = []
        for node in frontier:
            for neighbor in edge_table[node]:
                if neighbor == target:
                    return hops
                if neighbor not in seen:
                    seen.add(neighbor)
                    next_frontier.append(neighbor)
        frontier = next_frontier
    raise AssertionError(f"BFS 不可达：{start} → {target}")


def test_g9_tactical_t1_hex_space() -> None:
    """A12：``hex_adjacency`` 边表 = 期望对称边集（3×3 = 16 无向 / 32
    有向，常量钉）；``distance_between`` 钉值（立方坐标公式）+ 全节点对
    BFS 交叉核验；方格对照（同 3×3 坐标曼哈顿）；AD-P9-4 构造校验；
    1×N 行 = 仅水平边。"""
    grid = HexGrid(cols=3, rows=3)
    directed = hex_adjacency(grid)
    assert len(directed) == 32
    undirected = sorted({(min(a, b), max(a, b)) for a, b in directed})
    assert len(undirected) == 16
    assert tuple(undirected) == _EXPECTED_3X3_EDGES
    # 有向 = 每条无向边双向（对称边集钉）
    assert directed == tuple(
        sorted((a, b) for a, b in _EXPECTED_3X3_EDGES for a, b in ((a, b), (b, a)))
    )
    # 距离钉值（立方坐标公式 max(|dx|,|dy|,|dz|)）
    assert distance_between(grid, "hex_0_0", "hex_1_2") == 2
    assert distance_between(grid, "hex_0_1", "hex_2_0") == 2
    assert distance_between(grid, "hex_0_0", "hex_2_2") == 3
    # 全节点对 BFS 交叉核验（确定性）
    edge_table: dict[str, tuple[str, ...]] = {node: () for node in _hex_nodes()}
    for a, b in directed:
        edge_table[a] = edge_table[a] + (b,)
    for start in _hex_nodes():
        for target in _hex_nodes():
            assert (
                _bfs_distance(edge_table, start, target)
                == distance_between(grid, start, target)
            )

    # 内点邻接数 = 6（hex 满邻接面）
    assert len(_hex_domain().neighbors("hex_1_1")) == 6

    # 方格对照：同 3×3 坐标曼哈顿距离（core GridSpace 语义）
    square = GridSpace(width=3, height=3)
    assert square.distance({"x": 0, "y": 0}, {"x": 1, "y": 2}) == 3

    # AD-P9-4：构造期校验（ValueError 面）
    with pytest.raises(ValueError):
        HexGrid(cols=0, rows=3)
    with pytest.raises(ValueError):
        HexGrid(cols=3, rows=0)
    with pytest.raises(ValueError):
        HexGrid(cols=3, rows=3, offset="diagonal")

    # 1×N 行 = 仅水平边（无垂直邻居）
    row = HexGrid(cols=3, rows=1)
    row_edges = sorted({(min(a, b), max(a, b)) for a, b in hex_adjacency(row)})
    assert row_edges == [("hex_0_0", "hex_1_0"), ("hex_1_0", "hex_2_0")]
    # 幂等 + 核验序钉（SOT §3.11 表行 4「幂等」；R1 补充 F1-2；
    # DEV-W6-8 签名面）：同域同 backend 重注册 = 幂等零变化；文法 /
    # 种类核验失败 = 零写入。
    entries: dict = {}
    register_standard_space(entries, "idem", square)
    first_entry = entries["idem"]
    register_standard_space(entries, "idem", square)
    assert entries["idem"] == first_entry
    with pytest.raises(ValueError):
        register_standard_space(entries, "Bad-Id", square)
    assert set(entries) == {"idem"}
    with pytest.raises(ValueError):
        register_standard_space(entries, "idem2", HexGrid(cols=3, rows=3))
    assert set(entries) == {"idem"}


def test_g9_tactical_t2_tactical_mode(p9_host) -> None:
    """A13：``build_tactical_overlay``（TACTICAL_ACTION_IDS）→
    ``merge_modes`` → 战术模式下 ``is_action_available``：``attack``
    允许、非战术动作（``talk``）拒绝。"""
    host = _tactical_host(p9_host)
    # TACTICAL_ACTION_IDS 5 名钉（SOT §3.12 表行 1；L810）
    assert TACTICAL_ACTION_IDS == ("move", "attack", "reload", "take_cover", "wait")
    overlay = build_tactical_overlay(
        TacticalOverlaySpec(
            mode_id="tactical",
            available_actions=TACTICAL_ACTION_IDS,
            description="战术阶段，动作集限定为战术面（allow 层）。",
        )
    )
    assert overlay.mode_id == "tactical"
    assert overlay.action_filter_kind == "allow"
    assert overlay.action_ids == TACTICAL_ACTION_IDS
    assert overlay.priority == 10
    # 宿主注册表 overlay = 模块面同源（注册期经 build_tactical_overlay）
    registered = host.mode_registry.get("tactical")
    assert registered is not None
    assert registered.action_ids == overlay.action_ids
    # merge_modes（gameplay_mode.py:266）：战术 allow 层 + 探索基线 none 层
    merged = merge_modes(
        {
            "exploration": host.mode_registry.get("exploration"),
            "tactical": overlay,
        }
    )
    assert merged.action_filter_kind == "allow"
    # 合并 allow = 各 allow 集交集（排序；D-P4-14）
    assert merged.action_ids == tuple(sorted(TACTICAL_ACTION_IDS))
    assert is_action_available(merged, "attack") is True
    assert is_action_available(merged, "take_cover") is True
    assert is_action_available(merged, "talk") is False
    assert is_action_available(merged, "inspect") is False
    # 基线层单独（none）：恒真面
    baseline = merge_modes({"exploration": host.mode_registry.get("exploration")})
    assert baseline.action_filter_kind == "none"
    assert is_action_available(baseline, "talk") is True


class AttackExecutor:
    """测试本地纯函数攻击执行器（W4 ``ActionExecutor`` 协议面；A14 主面）。

    ``execute(proposal, world, tick) -> ExecutorResult``：actor / target
    均为 world 实体（缺席 → failure）；位置经 spaces 组件
    （``decode_spaces``，space.py:492）投影；邻接校验 = target ∈
    ``backend.neighbors(current)``（hex 域）；成功 → 恰 1 个
    ``ProposedEffect``（确定性 effect_id 拼装）；失败 → 零 committed +
    failure 串。零推理调用（P9-INV-6；backend 不参与本路径）。
    """

    def __init__(self, spaces: SpaceRegistry, domain_id: str) -> None:
        self._spaces = spaces
        self._domain_id = domain_id

    def execute(self, proposal: ActionProposal, world: WorldState, tick: int) -> ExecutorResult:
        target_id = EntityId(str(proposal.arguments.get("target", "")))
        actor = world.entities.get(proposal.actor_id)
        target = world.entities.get(target_id)
        if actor is None or target is None:
            return ExecutorResult(
                committed=(), failure=f"entity missing: actor/target 缺席"
            )
        actor_pos = _domain_position(actor, self._domain_id)
        target_pos = _domain_position(target, self._domain_id)
        if actor_pos is None or target_pos is None:
            return ExecutorResult(committed=(), failure="spatial mapping 缺席")
        backend = self._spaces.backend(self._domain_id)
        if target_pos not in backend.neighbors(actor_pos):
            return ExecutorResult(
                committed=(),
                failure=f"non-adjacent: {actor_pos} → {target_pos} 非邻接",
            )
        effect = ProposedEffect(
            effect_id=EffectId(f"eff_attack_{proposal.actor_id}_{target_id}_{tick}"),
            effect_type=EffectTypeId("p9.attack"),
            source=ProducerId("p9.attack_executor"),
            target=EntityTarget(entity_id=target_id),
            payload={
                "attacker": str(proposal.actor_id),
                "target": str(target_id),
                "tick": tick,
            },
            base_revision=world.world_revision,
        )
        return ExecutorResult(
            committed=(effect,), failure=None, duration_ticks=0
        )


def _domain_position(record: EntityRecord, domain_id: str):
    """实体 spaces 组件 → 指定域位置（缺席 → None）。"""
    payload = record.components.get(ComponentTypeId("spaces"))
    if payload is None:
        return None
    for mapping in decode_spaces(payload):
        if mapping.domain_id == domain_id:
            return mapping.position
    return None


def test_g9_tactical_t3_deterministic_action(p9_host) -> None:
    """A14：soldier_a ``attack`` 提案 → 纯函数执行器 → 全程
    ``FakeInferenceBackend.calls`` 为空（零推理调用）+ 同输入二次执行
    效果流逐条相等（P9-INV-6）。"""
    host = _tactical_host(p9_host)
    executor = AttackExecutor(host.spaces, "tactical")

    proposal = ActionProposal(
        proposal_id="act_ent_authoring_soldier_a_1",
        actor_id=_SOLDIER_A,
        action_id="attack",
        arguments={"target": _SOLDIER_B},
        intent="strike",
        confidence=1.0,
        base_world_revision=host.world.world_revision,
        actor_state_revision=host.world.world_revision,
        provenance={
            "producer_id": f"policy.{_SOLDIER_A}",
            "origin": "behavior_policy",
        },
    )
    assert host.backend.calls == ()
    world_ref = host.world
    first = executor.execute(proposal, host.world, 1)
    assert first.failure is None
    assert len(first.committed) == 1
    assert str(first.committed[0].effect_id) == (
        f"eff_attack_{_SOLDIER_A}_{_SOLDIER_B}_1"
    )
    # 同输入二次执行 = 同效果流（逐条相等）
    second = executor.execute(proposal, host.world, 1)
    assert second.committed == first.committed
    assert second.failure is None
    # 零推理调用 + 世界零写（纯函数面）
    assert host.backend.calls == ()
    assert host.world is world_ref
    assert host.world.world_revision == Revision(0)

    # 非邻接目标（player 于 hex_1_1；soldier_a 于 hex_0_0 的邻居 =
    # hex_0_1 / hex_1_0）→ 失败面：零 committed + failure 串
    far = ActionProposal(
        proposal_id="act_ent_authoring_soldier_a_2",
        actor_id=_SOLDIER_A,
        action_id="attack",
        arguments={"target": _PLAYER},
        intent="strike",
        confidence=1.0,
        base_world_revision=host.world.world_revision,
        actor_state_revision=host.world.world_revision,
        provenance={
            "producer_id": f"policy.{_SOLDIER_A}",
            "origin": "behavior_policy",
        },
    )
    failed = executor.execute(far, host.world, 2)
    assert failed.committed == ()
    assert failed.failure is not None


def test_g9_tactical_t4_mode_transition(p9_host) -> None:
    """A15：探索→战术→探索（``TacticalModePolicy`` +
    ``apply_mode_change``）→ 两次转移后 ``MergedModeConfiguration`` 回
    到探索集；单一 WorldState 全程（无重建，tick 连续）；战术互斥拒绝
    面（原子拒绝全量）。"""
    host = _tactical_host(p9_host)
    assert host.runtime.active_modes == ["exploration"]
    world_ref = host.world
    initial_runtime = host.runtime
    hash_pin = host.world_hash(initial_runtime)

    source = Provenance(producer_id="p9.host", origin=OriginKind.SCENARIO)
    activate = ModeChangeRequest(
        request_id="p9_req_activate",
        source=source,
        operations=(
            ModeOperation(
                operation_kind=ModeOperationKind.ACTIVATE, mode_id="tactical"
            ),
        ),
    )
    resolution = host.mode_policy.resolve(activate, host.mode_registry, host.runtime)
    assert resolution.applied == ("activate:tactical",)
    assert resolution.ignored == ()
    host.runtime, _ = apply_mode_change(
        request=activate, runtime=host.runtime, registry=host.mode_registry
    )
    assert host.runtime.active_modes == ["exploration", "tactical"]
    merged = merge_modes(
        {mid: host.mode_registry.get(mid) for mid in host.runtime.active_modes}
    )
    assert is_action_available(merged, "attack") is True
    assert is_action_available(merged, "talk") is False

    # 战术互斥拒绝面：战术激活中再激活另一战术 id → 原子拒绝全量
    siege = build_tactical_overlay(
        TacticalOverlaySpec(mode_id="siege", available_actions=TACTICAL_ACTION_IDS)
    )
    # 互斥判定 = 策略侧 tactical id 声明面（两者皆战术 → 互斥）
    exclusive_policy = TacticalModePolicy(tactical_mode_ids=("tactical", "siege"))
    exclusive_registry = ModeOverlayRegistry(
        {
            **{
                mid: host.mode_registry.get(mid)
                for mid in host.mode_registry.mode_ids()
            },
            "siege": siege,
        }
    )
    exclusive = ModeChangeRequest(
        request_id="p9_req_siege",
        source=source,
        operations=(
            ModeOperation(
                operation_kind=ModeOperationKind.ACTIVATE, mode_id="siege"
            ),
        ),
    )
    rejection = exclusive_policy.resolve(
        exclusive, exclusive_registry, host.runtime
    )
    assert rejection.applied == ()
    assert rejection.ignored == ("activate:siege",)
    assert tuple(rejection.new_active_modes) == tuple(host.runtime.active_modes)
    # 拒绝路径：消费侧不经 apply_mode_change（policy = 唯一闸门；
    # 拒绝解析本身即终态）——active_modes 原样
    assert host.runtime.active_modes == ["exploration", "tactical"]

    deactivate = ModeChangeRequest(
        request_id="p9_req_deactivate",
        source=source,
        operations=(
            ModeOperation(
                operation_kind=ModeOperationKind.DEACTIVATE, mode_id="tactical"
            ),
        ),
    )
    host.mode_policy.resolve(deactivate, host.mode_registry, host.runtime)
    host.runtime, _ = apply_mode_change(
        request=deactivate, runtime=host.runtime, registry=host.mode_registry
    )
    assert host.runtime.active_modes == ["exploration"]
    back = merge_modes(
        {mid: host.mode_registry.get(mid) for mid in host.runtime.active_modes}
    )
    assert is_action_available(back, "talk") is True

    # 单一 WorldState 全程（无重建）+ revision 连续（模式变更零世界
    # 效果）+ tick 连续（set_logical_tick 单写点，无回退/跳刻）
    assert host.world is world_ref
    assert host.world.world_revision == Revision(0)
    # 世界哈希不变（钉初始 runtime 帧隔离模式侧簿记——DEV-W6-7 面）
    assert host.world_hash(initial_runtime) == hash_pin
    host.tick(2)
    assert host.runtime.logical_tick == 2


def test_g9_tactical_t5_project_loads() -> None:
    """A 前件：项目加载（零 ERROR）+ 内容面钉（gameplay_modes 顶层键 /
    actions 节 / 兵角色 / 属性 strength）。"""
    result = load_project(_TACTICAL)
    assert result.raw is not None
    assert [d for d in result.diagnostics if d.severity.value == "ERROR"] == []
    ir_result = build_ir(result.raw)
    assert ir_result.ir is not None
    validation = validate_project(ir_result.ir, result.raw)
    assert validation.ok
    assert [
        d for d in validation.diagnostics if d.severity.value == "ERROR"
    ] == []
    # 内容面钉（SOT §3.19 tactical 样例形状）
    ir = ir_result.ir
    assert [m.id for m in ir.gameplay_modes] == ["exploration", "tactical"]
    assert [a.id for a in ir.actions] == ["move", "attack", "take_cover"]
    assert [c.id for c in ir.characters] == ["soldier_a", "soldier_b"]
    assert ir.player.player_id == "player_1"
    assert ir.scenario.id == "scenario_tactical"
    # 动作 DSL 条件引用的属性在场（strength）
    assert "strength" in ir.player.attributes
    assert ir.player.attributes["strength"].value == 6.0
    # 波内身份点钉（R1 补充 F1-1；A18/A21 波内点面；15 文件台账钉 =
    # W7 test_module_face t2/t5）：
    assert tuple(space_mod.__all__) == (
        "HexGrid", "hex_adjacency", "distance_between",
        "register_standard_space",
    )
    assert (
        space_mod.IDENTITY.module_id,
        space_mod.IDENTITY.version,
        space_mod.IDENTITY.requires,
    ) == ("llmsim-standard-space", "1", ())
    assert tuple(tactical_mod.__all__) == (
        "TACTICAL_ACTION_IDS", "TacticalOverlaySpec",
        "build_tactical_overlay", "TacticalModePolicy",
    )
    assert (
        tactical_mod.IDENTITY.module_id,
        tactical_mod.IDENTITY.version,
        tactical_mod.IDENTITY.requires,
    ) == (
        "llmsim-standard-tactical",
        "1",
        ("llmsim-standard-actions", "llmsim-standard-space"),
    )
