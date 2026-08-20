"""P1-T06 收尾验收：core 包 re-export 收尾（设计文档 §0.4）+ 快照隔离（§7.5 J4）验收闭环。

覆盖：

- **re-export 一致性**（设计文档 §0.4 / 任务包要求"re-export 后
  ``from src.engine_v2.core import <类型>`` 可用且有测试断言 ``__all__``
  与各模块导出一致"）：
  - 包 ``__all__`` 与 13 个契约模块 ``__all__`` 的并集**逐名相等**，唯一
    差异为**同名遮蔽豁免**（与子模块撞名的导出——当前恰为
    ``snapshot`` 函数——不绑包属性，否则遮蔽子模块属性，破坏
    ``import src.engine_v2.core.snapshot as m``；机械推导 + 恰为豁免集
    断言，非硬编码裁剪；``CONTRACT_SCHEMA_VERSION`` 双模块同名按同一
    对象去重）；
  - 每个 re-export 名称与**定义来源模块**的属性为同一对象（``is``——
    单一来源、无第二副本）；豁免名称仍可经子模块路径访问；
  - ``CONTRACT_SCHEMA_VERSION`` 单一来源（state.py 定义，snapshot.py
    复用，包级再复用——三处同一对象，T02 已确立的事实）；
  - ``from src.engine_v2.core import *`` 的表面与 ``__all__`` 完全一致；
  - ``from src.engine_v2.core import <类型>`` 直接可用（本文件模块级
    import 即证明）+ 契约类型族形态抽查（ContractModel 子类 / str-Enum /
    frozen dataclass / 常量 / 纯函数）。
- **快照隔离收尾**（设计文档 §7.5 J4 的 T06 验收口径"从快照还原后与原
  状态语义一致、互不别名"；实现级用例已由 T05 固化，本文件是验收层
  闭环）：
  - ``restore_snapshot`` 产物与原状态 **== 语义一致** + 类型重建保持
    （Revision / typed ID / 枚举）；
  - 还原产物 ↔ 活状态 **双向零别名**（嵌套 dict/list 逐一非共享，修改
    还原产物不波及活状态）；
  - 快照本体 ↔ 活状态 / 还原产物零别名（D-15 第 4 条 ``snapshot()`` 与
    ``restore_snapshot()`` 双向深拷贝固化）；
  - 两个不同 revision 的快照各自还原后互不影响（J4 前段）；
  - 干净快照 ``check_snapshot_versions`` 空报告（J6 收尾）。

**不重复项**：R1 ID 唯一性压力（每种 ``new_*_id()`` ≥10⁴ 无碰撞）已由
T01 ``tests/engine_v2/core/test_ids.py::TestR1Generation`` 覆盖——按任务
包口径不重复。

全部用例无网络、无 LLM、无 API key（Spec §47 Phase 1 验收）。
"""

from __future__ import annotations

import dataclasses
import importlib
from dataclasses import is_dataclass
from enum import Enum
from typing import Any

import pytest

import src.engine_v2.core as core_pkg
from src.engine_v2.core import (
    # 常量（单一来源断言对象）
    CONTRACT_SCHEMA_VERSION,
    SNAPSHOT_FORMAT_VERSION,
    # 契约类型（模块级 import 即证明 from src.engine_v2.core import <类型> 可用）
    ActionInstanceId,
    ActionProposal,
    ActionTypeId,
    BackendStateRef,
    ComponentTypeId,
    ContractModel,
    DomainEvent,
    EntityId,
    EntityRecord,
    EntityView,
    OriginKind,
    ProducerId,
    ProposedEffect,
    Provenance,
    Revision,
    RuntimeLifecycle,
    RuntimeState,
    ScenarioState,
    ScheduledEntryId,
    ScheduledEvent,
    Snapshot,
    TraceKind,
    TraceRecord,
    Transaction,
    WorldState,
    # 纯函数（``snapshot()`` 经子模块路径导入：与子模块同名，包级不
    # re-export——同名遮蔽豁免，见 __init__.py docstring 与下方测试）
    check_snapshot_versions,
    restore_snapshot,
)
from src.engine_v2.core.snapshot import snapshot as take_snapshot

#: 19 个 core 模块（P2 设计规范 §1.1 / D-P2-19：13 个契约模块 + 6 个 P2
#: 行为模块——authority / cascade / conflicts / reducer /
#: transaction_executor / validation；re-export 的唯一来源集合）。
_CORE_SUBMODULE_NAMES: tuple[str, ...] = (
    "actions",
    "authority",
    "cascade",
    "components",
    "conflicts",
    "effects",
    "entity",
    "events",
    "ids",
    "provenance",
    "reducer",
    "revision",
    "serialization",
    "snapshot",
    "state",
    "trace",
    "transaction",
    "transaction_executor",
    "validation",
)

#: 模块对象在**测试收集期**经 ``importlib``（直接读 sys.modules）捕获：
#: 套件内其他 import 边界测试会 pop 并重载部分 core 模块（T01–T05 既有
#: 口径），执行期动态取模块可能拿到混合代次实例——收集期捕获保证本文件
#: 全部断言在同一自洽模块图上进行（与模块级 re-export import 同源）。
#: 不用 ``import a.b.c as x`` 属性链形态是同一纪律的另一面：bpo-30024
#: 语义下属性链成功时不回退 sys.modules，包属性与子模块撞名时（如历史
#: 版本把 ``snapshot`` 函数绑到包属性）会静默拿到函数而非模块。
CORE_SUBMODULES: dict[str, Any] = {
    name: importlib.import_module(f"src.engine_v2.core.{name}")
    for name in _CORE_SUBMODULE_NAMES
}


class TestCorePackageReexports:
    """设计文档 §0.4：全部契约类型的导出集中在 core/__init__.py。"""

    @staticmethod
    def _module_all_union() -> set[str]:
        union: set[str] = set()
        for mod in CORE_SUBMODULES.values():
            union.update(mod.__all__)
        return union

    @staticmethod
    def _shadowed_names(union: set[str]) -> set[str]:
        """同名遮蔽豁免集（机械推导，非硬编码）：与子模块撞名的模块导出。

        此类名称若绑到包属性，会覆盖 import 系统在子模块加载时设置的同名
        模块属性，使 ``import src.engine_v2.core.<子模块> as m``（bpo-30024
        属性链成功不回退 sys.modules）拿到被遮蔽对象——故包级只豁免它们，
        其余名称一律 re-export。
        """
        return {name for name in union if name in CORE_SUBMODULES}

    def test_package_all_equals_union_minus_shadowed(self) -> None:
        """包 ``__all__`` == 模块 ``__all__`` 并集 − 同名遮蔽豁免集（机械推导）。"""
        union = self._module_all_union()
        shadowed = self._shadowed_names(union)
        assert shadowed == {"snapshot"}, (
            f"同名遮蔽豁免集应为 {{'snapshot'}}（当前唯一撞名），实际 {shadowed}"
        )
        assert set(core_pkg.__all__) == union - shadowed, (
            f"包 __all__ 与（模块 __all__ 并集 − 豁免集）不一致："
            f"仅包有={set(core_pkg.__all__) - (union - shadowed)}，"
            f"仅模块有={(union - shadowed) - set(core_pkg.__all__)}"
        )

    def test_package_all_no_private_no_duplicates(self) -> None:
        assert len(core_pkg.__all__) == len(set(core_pkg.__all__)), "__all__ 存在重复项"
        assert not any(name.startswith("_") for name in core_pkg.__all__), "__all__ 泄漏私有名称"
        # 规模锚点：138 个唯一名称（13 个契约模块 __all__ 共 95 项，
        # CONTRACT_SCHEMA_VERSION 在 state/snapshot 双模块同名、同一对象，
        # 去重后 94；再减去同名遮蔽豁免的 snapshot 函数 = 93；再加 P2 行为
        # 模块导出——authority 8 项（P2-T02/T03）+ reducer 37 项（P2-T01）
        # = 138；validation/conflicts/transaction_executor/cascade 四个占位
        # 骨架模块（D-P2-19）尚无公开导出，随各自任务包落地时本锚点同步）
        assert len(core_pkg.__all__) == 138

    def test_every_reexport_is_same_object_as_source_module(self) -> None:
        """每个包级 re-export 名称与定义来源模块的属性同一对象（无第二副本）。"""
        union = self._module_all_union()
        shadowed = self._shadowed_names(union)
        for sub, mod in CORE_SUBMODULES.items():
            for name in mod.__all__:
                if name in shadowed:
                    continue  # 豁免名称不经包级 re-export（专门用例见下）
                assert getattr(core_pkg, name) is getattr(mod, name), (
                    f"{name}：包级 re-export 与 {sub} 模块定义不是同一对象"
                )

    def test_shadowed_name_stays_reachable_via_submodule(self) -> None:
        """豁免名称仍可经子模块路径访问，且包属性保持为子模块（不遮蔽）。

        反例即本豁免要防的事故：包属性 ``core.snapshot`` 被同名函数覆盖后，
        ``import src.engine_v2.core.snapshot as m`` 会拿到函数（T05 测试文件
        的既有 import 形态）。
        """
        union = self._module_all_union()
        shadowed = self._shadowed_names(union)
        for name in shadowed:
            mod = CORE_SUBMODULES[name]
            # 包属性必须是子模块本身（import a.b.c as m 的属性链语义）
            assert getattr(core_pkg, name) is mod, f"包属性 core.{name} 被子模块之外的对象遮蔽"
            # 原导出（当前为 snapshot() 纯函数）经子模块路径仍可达且可用
            original = getattr(mod, name)
            assert original is not mod
        assert callable(take_snapshot)

    def test_contract_schema_version_single_source(self) -> None:
        """CONTRACT_SCHEMA_VERSION 单一来源（T02 事实 + T05 严禁双源复写）。"""
        state_mod = CORE_SUBMODULES["state"]
        snapshot_mod = CORE_SUBMODULES["snapshot"]
        assert core_pkg.CONTRACT_SCHEMA_VERSION is state_mod.CONTRACT_SCHEMA_VERSION
        assert core_pkg.CONTRACT_SCHEMA_VERSION is snapshot_mod.CONTRACT_SCHEMA_VERSION
        assert CONTRACT_SCHEMA_VERSION == 1
        assert SNAPSHOT_FORMAT_VERSION == 1

    def test_star_import_surface_matches_all(self) -> None:
        """``from src.engine_v2.core import *`` 的表面与 __all__ 完全一致。"""
        namespace: dict[str, Any] = {}
        exec("from src.engine_v2.core import *", namespace)  # noqa: S102
        assert set(namespace) - {"__builtins__"} == set(core_pkg.__all__)


class TestReexportedTypeFamilies:
    """re-export 后的契约类型族形态抽查（§0.1 统一约定）。"""

    def test_contract_models_are_contract_model_subclasses(self) -> None:
        for cls in (
            WorldState,
            RuntimeState,
            ScenarioState,
            EntityRecord,
            ProposedEffect,
            Transaction,
            DomainEvent,
            TraceRecord,
            Snapshot,
            Provenance,
        ):
            assert issubclass(cls, ContractModel), f"{cls.__name__} 不是 ContractModel 子类"

    def test_enums_are_str_enums(self) -> None:
        for cls in (RuntimeLifecycle, TraceKind):
            assert issubclass(cls, str) and issubclass(cls, Enum), f"{cls.__name__}"

    def test_readonly_facade_is_frozen_dataclass(self) -> None:
        assert is_dataclass(EntityView)
        view = EntityView(
            entity_id=EntityId("ent_close_probe"),
            entity_class=None,
            tags=(),
            revision=Revision(0),
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            view.revision = Revision(1)  # type: ignore[misc]

    def test_constants_and_functions_reexported(self) -> None:
        assert callable(core_pkg.parse_id)
        assert callable(core_pkg.is_stale)
        assert callable(core_pkg.dump_json)
        assert callable(core_pkg.load_json)
        # snapshot() 函数经子模块路径可达（同名遮蔽豁免，包属性是子模块）
        assert callable(take_snapshot)
        assert callable(core_pkg.restore_snapshot)
        assert callable(core_pkg.check_snapshot_versions)
        assert callable(core_pkg.freeze_view)
        assert callable(core_pkg.assert_json_clean)
        assert callable(core_pkg.deep_copy_via_roundtrip)


# —— 快照隔离收尾：样本工厂（自包含、确定性构造）——


def _make_world_state(world_revision: int = 5) -> WorldState:
    return WorldState(
        world_revision=Revision(world_revision),
        entities={
            EntityId("ent_close_alice"): EntityRecord(
                entity_id=EntityId("ent_close_alice"),
                entity_class="npc",
                tags=["shopkeeper"],
                created_revision=Revision(3),
                components={
                    ComponentTypeId("space.position"): {
                        "x": 1,
                        "y": 2,
                        "z": [0, 0],
                        "label": "客栈门口",
                    },
                    ComponentTypeId("knowledge.belief"): {
                        "facts": [{"id": "f1", "text": "钥匙在柜台下"}]
                    },
                },
            )
        },
        world_variables={
            "calendar": {"day": 3, "hour": 12, "minute": 0},
            "note": "中文世界变量",
        },
        scenario_state=ScenarioState(
            scenario_id="scn_close",
            stage="first_encounter",
            data={"goal": "找到钥匙", "depth": 2},
        ),
    )


def _make_runtime_state(logical_tick: int = 42) -> RuntimeState:
    return RuntimeState(
        logical_tick=logical_tick,
        lifecycle=RuntimeLifecycle.RUNNING,
        scheduler_queue=[
            ScheduledEvent(
                entry_id=ScheduledEntryId("sch_close_1"),
                due_tick=logical_tick + 1,
                kind="wakeup",
                payload={"instance_id": "act_close_1"},
            )
        ],
        pending_proposals=[
            ActionProposal(
                proposal_id=ActionInstanceId("act_close_1"),
                actor_id=EntityId("ent_close_alice"),
                action_id=ActionTypeId("move"),
                arguments={"to": {"x": 1, "y": 2}},
                intent="移动到客栈门口",
                base_world_revision=Revision(5),
                provenance=Provenance(
                    producer_id=ProducerId("policy.alice"), origin=OriginKind.BEHAVIOR_POLICY
                ),
            )
        ],
        backend_refs={
            "dynamics_01": BackendStateRef(
                backend_id="dynamics_01",
                backend_kind="dynamics",
                checkpointable=True,
                checkpoint_ref="ckpt://dynamics/01",
            )
        },
    )


class TestSnapshotIsolationCloseout:
    """J4 验收口径：从快照还原后与原状态语义一致、互不别名。"""

    def test_restore_semantic_identity_and_type_preservation(self) -> None:
        """restore 产物与原状态 == 语义一致 + 类型重建保持（§2.1 / §0.2 判据 5）。"""
        ws = _make_world_state(5)
        rs = _make_runtime_state(42)
        snap = take_snapshot(ws, rs, "inst_close")
        assert snap.world_state == ws and snap.runtime_state == rs
        assert check_snapshot_versions(snap) == (), "干净快照应无版本问题（J6 收尾）"

        ws2, rs2 = restore_snapshot(snap)
        assert ws2 == ws, "restore 产物必须与原 WorldState 语义一致"
        assert rs2 == rs, "restore 产物必须与原 RuntimeState 语义一致"
        # 类型重建保持
        assert type(ws2.world_revision) is Revision
        assert all(type(k) is EntityId for k in ws2.entities)
        record = ws2.entities[EntityId("ent_close_alice")]
        assert all(type(k) is ComponentTypeId for k in record.components)
        assert type(record.created_revision) is Revision
        assert rs2.lifecycle is RuntimeLifecycle.RUNNING
        proposal = rs2.pending_proposals[0]
        assert type(proposal.proposal_id) is ActionInstanceId
        assert type(proposal.base_world_revision) is Revision

    def test_restore_product_zero_aliasing_with_live_state(self) -> None:
        """还原产物 ↔ 活状态双向零别名：修改还原产物不波及活状态。"""
        ws = _make_world_state(5)
        rs = _make_runtime_state(42)
        snap = take_snapshot(ws, rs, "inst_close")
        ws2, rs2 = restore_snapshot(snap)

        # world_variables 顶层与嵌套 dict 均非共享
        assert ws2.world_variables is not ws.world_variables
        assert ws2.world_variables["calendar"] is not ws.world_variables["calendar"]
        ws2.world_variables["calendar"]["day"] = 99
        assert ws.world_variables["calendar"]["day"] == 3, "修改还原产物污染了活状态"

        # entity 组件数据非共享（决策 D-7 entity-centric 的嵌套层）
        pos_key = ComponentTypeId("space.position")
        assert (
            ws2.entities[EntityId("ent_close_alice")].components[pos_key]
            is not ws.entities[EntityId("ent_close_alice")].components[pos_key]
        )
        ws2.entities[EntityId("ent_close_alice")].components[pos_key]["x"] = 111
        assert ws.entities[EntityId("ent_close_alice")].components[pos_key]["x"] == 1

        # scenario_state 嵌套 data 非共享
        assert ws2.scenario_state.data is not ws.scenario_state.data
        ws2.scenario_state.data["goal"] = "篡改"
        assert ws.scenario_state.data["goal"] == "找到钥匙"

        # runtime：pending proposal 嵌套 arguments 非共享
        assert rs2.pending_proposals[0].arguments is not rs.pending_proposals[0].arguments
        rs2.pending_proposals[0].arguments["to"]["x"] = 999
        assert rs.pending_proposals[0].arguments["to"]["x"] == 1

        # runtime：scheduler_queue 列表与其条目 payload 非共享
        assert rs2.scheduler_queue is not rs.scheduler_queue
        assert rs2.scheduler_queue[0].payload is not rs.scheduler_queue[0].payload

    def test_live_state_zero_aliasing_with_snapshot_body(self) -> None:
        """活状态 ↔ 快照本体零别名（D-15 第 4 条：snapshot() 入参先深拷贝固化）。"""
        ws = _make_world_state(5)
        rs = _make_runtime_state(42)
        snap = take_snapshot(ws, rs, "inst_close")

        assert snap.world_state is not ws
        assert (
            snap.world_state.world_variables["calendar"] is not ws.world_variables["calendar"]
        )
        snap.world_state.world_variables["calendar"]["minute"] = 59
        assert ws.world_variables["calendar"]["minute"] == 0, "修改快照本体污染了活状态"

        assert snap.runtime_state is not rs
        assert (
            snap.runtime_state.pending_proposals[0].arguments
            is not rs.pending_proposals[0].arguments
        )
        snap.runtime_state.pending_proposals[0].arguments["to"]["y"] = 777
        assert rs.pending_proposals[0].arguments["to"]["y"] == 2

    def test_restore_product_zero_aliasing_with_snapshot_body(self) -> None:
        """还原产物 ↔ 快照本体零别名（restore_snapshot 产物经独立 round-trip 重建）。"""
        ws = _make_world_state(5)
        rs = _make_runtime_state(42)
        snap = take_snapshot(ws, rs, "inst_close")
        ws2, _ = restore_snapshot(snap)

        assert ws2 is not snap.world_state
        assert (
            ws2.world_variables["calendar"] is not snap.world_state.world_variables["calendar"]
        )
        ws2.world_variables["calendar"]["day"] = 77
        assert snap.world_state.world_variables["calendar"]["day"] == 3, (
            "修改还原产物污染了快照本体"
        )

    def test_two_revisions_snapshots_isolated(self) -> None:
        """J4 前段：两个不同 revision 的快照各自还原后互不影响。"""
        ws_a = _make_world_state(5)
        rs_a = _make_runtime_state(42)
        ws_b = _make_world_state(6)
        rs_b = _make_runtime_state(43)
        snap_a = take_snapshot(ws_a, rs_a, "inst_close_a")
        snap_b = take_snapshot(ws_b, rs_b, "inst_close_b")

        ws_a2, rs_a2 = restore_snapshot(snap_a)
        ws_b2, rs_b2 = restore_snapshot(snap_b)
        assert ws_a2.world_revision == Revision(5)
        assert ws_b2.world_revision == Revision(6)

        # 修改还原 A 的嵌套数据 → 还原 B 与活 B / 快照 B 均不受影响
        ws_a2.world_variables["calendar"]["day"] = 31
        rs_a2.pending_proposals[0].arguments["to"]["x"] = -5
        assert ws_b2.world_variables["calendar"]["day"] == 3
        assert rs_b2.pending_proposals[0].arguments["to"]["x"] == 1
        assert ws_b.world_variables["calendar"]["day"] == 3
        assert snap_b.world_state.world_variables["calendar"]["day"] == 3

        # 反向：修改还原 B → 还原 A / 快照 A 不受影响
        ws_b2.world_variables["calendar"]["hour"] = 23
        assert ws_a2.world_variables["calendar"]["hour"] == 12
        assert snap_a.world_state.world_variables["calendar"]["hour"] == 12
