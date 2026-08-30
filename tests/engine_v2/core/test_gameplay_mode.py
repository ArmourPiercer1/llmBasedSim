"""P4 Wave D 模块单测：engine_v2 core GameplayMode 游戏模式（test_gameplay_mode.py）。

任务：新文件 tests/engine_v2/core/test_gameplay_mode.py（§3.10 / 口径 L730 /
§6.1 行 L1657 全量）。

依据（docs/v2/contracts/P4-actor-context-space-mode-design.md，下称"设计文档"）：

- **§3.10（L585-731，含代码块与 M-INV-1~6）**：14 导出（上半 8 项 + 下半 6 项）
  代码块逐字钉死；错误族行 L728（``UnknownModeError(LookupError)``（M-INV-2
  查找点）、``ModeInvariantError(ValueError)``（M-INV-1/2 构造期））；
- **单测口径行 L730**：本文件覆盖清单的口径原文；
- **§6.1 表格 L1657（全量）**：M-INV-1（overlay 字段冻结）/ M-INV-2（operations
  非空 + origin 映射合法性，provenance.py:49/53/55）/ M-INV-3（三关键字签名无
  world 参数）/ M-INV-4（effects 恒空）/ M-INV-5（rebuild_runtime 唯一重建通道
  + 其余字段位级不变 + context 别名断裂）/ M-INV-6（input_policy 不透明透传）；
  merge_modes 确定性（A4 单测像）；is_action_available 判定序（deny > allow
  交集 > 无约束）；origin 非法 → ModeInvariantError；
- **§4 D-P4-14**（模式合并规则：每字段单一胜者、平手 casefold 较小 mode_id、
  deny > allow 交集 > 无约束、P4 取交集 = 保守侧 D-P4-14b）/ **D-P4-15**
  （模式变更 = RuntimeState 簿记、P4 世界效果零、origin 映射
  Script→SCENARIO provenance.py:53 / RuleEngine、Plugin→SYSTEM :55 /
  LLM Director→BEHAVIOR_POLICY :49）/ **D-P4-17**（错误两族分类法，测试按族
  断言基类）；
- M-INV-5 / M-INV-6 锚点：§3.10 L718-720（rebuild_runtime 唯一重建通道，
  model_dump/model_validate roundtrip 保证位级不变 + 别名断裂，A6 断言）、
  L607（input_policy 不透明 JsonValue，P4 直通不解释，P8 表现层消费）。

被测模块：``src/engine_v2/core/gameplay_mode.py``（14 导出，已提交；构造前已
逐行核验源码实际模式）。

覆盖项（每项独立命名 test_ 函数；编号 ↔ 函数名）：

1. **M-INV-1 三拒绝**（非法 mode_id / none+非空 ids / allow+空 ids）——
   ``test_m_inv_1_invalid_mode_id_rejected_both_paths``（pattern 违例两路径
   均 ValidationError，**不**转具名类型——源码实际模式：gameplay_mode.py
   :186-200 的 ``__init__`` 只转译 msg 含 "M-INV-1" 的 value_error，pattern
   违例原样穿透）/
   ``test_m_inv_1_none_with_nonempty_action_ids_rejected_both_paths``（直接构造
   具名 ``ModeInvariantError`` + ``model_validate`` → ``ValidationError`` 两路径）/
   ``test_m_inv_1_allow_with_empty_action_ids_rejected_both_paths`` /
   ``test_m_inv_1_deny_with_empty_action_ids_rejected_both_paths``（源码实际
   模式：allow/deny 同分支，gameplay_mode.py:129-138，设计文档逐字
   "allow/deny ⇒ action_ids 非空"的 deny 侧同式覆盖）；
2. **M-INV-2**——``test_m_inv_2_empty_operations_rejected_both_paths``（空
   operations → 构造期 ``ModeInvariantError``，两路径）/
   ``test_m_inv_2_missing_source_rejected_both_paths``（source 必填字段，缺失
   两路径 ValidationError）/ ``test_m_inv_2_legal_origin_image_set_accepted``
   （SCENARIO / SYSTEM / BEHAVIOR_POLICY 接受，D-P4-15 origin 映射
   provenance.py:49/53/55）/ ``test_m_inv_2_illegal_origins_rejected``（RULE /
   SCRIPT / DYNAMICS_BACKEND / DEVELOPER 拒绝，两路径）；
3. **registry 键不匹配拒绝**——``test_registry_key_mismatch_rejected``
   （ModeOverlayRegistry 键 != overlay.mode_id → ``ModeInvariantError``，
   上半既有面；附正例 get/mode_ids）；
4. **merge 五性质**——``test_merge_single_overlay_passthrough``（单 overlay
   透传）/ ``test_merge_dual_overlay_higher_priority_wins``（双 overlay 高
   priority 胜）/ ``test_merge_priority_tie_casefold_smaller_mode_id_wins``
   （平手 casefold 较小 mode_id 胜）/ ``test_merge_empty_input_all_defaults``
   （空输入全缺省）/ ``test_merge_winner_by_field_keys_and_values``（
   winner_by_field 键集与值——Spec:1433 冲突策略可检查：单胜者字段 = 排序
   首现非空值、action_filter = 排序首现 kind==最终 kind，gameplay_mode.py
   :284-318 源码语义）；
5. **action_filter 四态**——``test_merge_action_filter_none_state`` /
   ``test_merge_action_filter_allow_single`` /
   ``test_merge_action_filter_allow_dual_intersection``（P4 保守侧，
   D-P4-14b）/ ``test_merge_action_filter_deny_beats_allow``（deny 压 allow，
   ids = 各 deny 集并集）；
6. **is_action_available 三态**——
   ``test_is_action_available_deny_hit_false``（deny 命中 → False）/
   ``test_is_action_available_allow_intersection``（allow 交集含 → True /
   不含 → False）/ ``test_is_action_available_no_constraint_true``（无约束 →
   True；判定序 deny > allow 交集 > 无约束，D-P4-14）；
7. **apply 五路径**——``test_apply_activate_new`` /
   ``test_apply_activate_duplicate_ignored`` / ``test_apply_deactivate_active``
   / ``test_apply_deactivate_absent_ignored`` /
   ``test_apply_unknown_mode_atomic_rejection``（未知 mode 原子拒绝：
   ``UnknownModeError``，LookupError 族（D-P4-17）；断言原 runtime
   model_dump 全字段不变）；
8. **M-INV-5**——``test_m_inv_5_other_fields_bitwise_unchanged``（apply 后
   new_runtime 与旧 runtime model_dump 除 active_modes / mode_context 外全键
   相等；new_runtime is not runtime；rng_state / backend_refs /
   scheduler_queue / active_actions / pending_proposals 位级不变——INV-P4-5
   零世界状态效果、零事件、零事务、零队列变更）；
9. **context 别名断裂**——``test_context_alias_break_after_apply``（apply
   activate 成功后 mutate 原 overlay.context → new_runtime.mode_context 不含
   注入键——rebuild_runtime roundtrip 断别名，A6 断言面）；
10. **§6.1 补充**——``test_m_inv_3_apply_signature_three_keyword_only_params_no_world``
    （inspect.signature 参数集 == {request, runtime, registry} 且全
    keyword-only、无 world 参数——G4-6 结构面）/
    ``test_m_inv_4_effects_always_empty``（所有 apply 成功路径
    resolution.effects == ()）/ ``test_m_inv_6_input_policy_opaque_passthrough``
    （overlay.input_policy 经 merge 单一胜者透传、内容不被解释）/
    ``test_merge_determinism_repeat_calls_and_input_order_perturbation``
    （A4 单测像：同输入重复调用 → 全等输出；overlay 输入序扰动 → 同一胜者
    口径。注明：以 §3.10 实际语义为准——merge_modes 纯函数，内部按
    (-priority, casefold(mode_id)) 排序（gameplay_mode.py:275-278），确定性
    且排列不变；平手裁定 = casefold 较小 id，D-P4-14）。

错误族断言纪律（D-P4-17）：``ModeInvariantError`` 按 ValueError 族断言基类，
``UnknownModeError`` 按 LookupError 族断言基类。
"""

from __future__ import annotations

import inspect
from typing import Any

import pytest
from pydantic import ValidationError

from src.engine_v2.core.actions import (
    ActionInstanceId,
    ActionLifecycleStatus,
    ActionProposal,
    ActionTypeId,
    ActiveAction,
)
from src.engine_v2.core.gameplay_mode import (
    MergedModeConfiguration,
    ModeChangeRequest,
    ModeChangeResolution,
    ModeInvariantError,
    ModeOperation,
    ModeOperationKind,
    ModeOverlay,
    ModeOverlayRegistry,
    UnknownModeError,
    apply_mode_change,
    is_action_available,
    merge_modes,
)
from src.engine_v2.core.ids import EntityId, ProducerId, ScheduledEntryId
from src.engine_v2.core.provenance import OriginKind, Provenance
from src.engine_v2.core.revision import INITIAL_WORLD_REVISION
from src.engine_v2.core.scheduler import TimePolicy
from src.engine_v2.core.state import (
    BackendStateRef,
    RngState,
    RuntimeState,
    ScheduledEvent,
)

# ─────────────────────────── 公共构件 ───────────────────────────


def make_provenance(origin: OriginKind) -> Provenance:
    """确定性 Provenance 构造（K6；producer 名字型词法 ids.py:77）。"""
    return Provenance(producer_id=ProducerId("policy.test"), origin=origin)


def make_overlay(mode_id: str, priority: int, **overrides: Any) -> ModeOverlay:
    """确定性 ModeOverlay 构造助手（缺省 action_filter_kind="none" / 空集）。"""
    data: dict[str, Any] = {"mode_id": mode_id, "priority": priority}
    data.update(overrides)
    return ModeOverlay(**data)


def activate(mode_id: str) -> ModeOperation:
    """ACTIVATE 操作快捷构造（ModeOperation.mode_id 无 pattern，成员资格归
    解析期原子预校验——gameplay_mode.py:113-115 钉死）。"""
    return ModeOperation(operation_kind=ModeOperationKind.ACTIVATE, mode_id=mode_id)


def deactivate(mode_id: str) -> ModeOperation:
    """DEACTIVATE 操作快捷构造。"""
    return ModeOperation(operation_kind=ModeOperationKind.DEACTIVATE, mode_id=mode_id)


def make_request(
    operations: list[ModeOperation],
    origin: OriginKind = OriginKind.SCENARIO,
    request_id: str = "req_test_0001",
) -> ModeChangeRequest:
    """确定性 ModeChangeRequest 构造（origin 缺省 SCENARIO——合法源像集成员）。"""
    return ModeChangeRequest(
        request_id=request_id,
        source=make_provenance(origin),
        operations=tuple(operations),
    )


# ─────────────── 1. M-INV-1 三拒绝（§3.10 L609-610 逐字）───────────────


def test_m_inv_1_invalid_mode_id_rejected_both_paths() -> None:
    """1a: 非法 mode_id（不匹配 ``^[a-z][a-z0-9_]*$``）→ 两路径 ValidationError。

    pattern 是 pydantic 字段级校验（非 M-INV-1 跨字段 value_error）：直接构造
    路径的 ``__init__`` 只转译 msg 含 "M-INV-1" 的 value_error
    （gameplay_mode.py:186-200），pattern 违例原样穿透为 ValidationError。
    """
    with pytest.raises(ValidationError) as exc_direct:
        ModeOverlay(mode_id="Dialogue", priority=0)
    assert exc_direct.value.errors()[0]["type"] == "string_pattern_mismatch"

    with pytest.raises(ValidationError) as exc_validate:
        ModeOverlay.model_validate({"mode_id": "DIALOGUE_2X", "priority": 0})
    assert exc_validate.value.errors()[0]["type"] == "string_pattern_mismatch"


def test_m_inv_1_none_with_nonempty_action_ids_rejected_both_paths() -> None:
    """1b: action_filter_kind="none" + 非空 action_ids → 构造期拒绝（两路径）。"""
    # 直接构造路径：具名 ModeInvariantError（ValueError 族，不静默、不包裹）。
    with pytest.raises(ModeInvariantError) as exc_direct:
        ModeOverlay(
            mode_id="dialogue",
            priority=0,
            action_filter_kind="none",
            action_ids=("attack",),
        )
    assert isinstance(exc_direct.value, ValueError)
    assert "M-INV-1" in str(exc_direct.value)
    assert "none" in str(exc_direct.value)

    # model_validate 路径：ValidationError（value_error 条目保留 M-INV-1 原文）。
    with pytest.raises(ValidationError) as exc_validate:
        ModeOverlay.model_validate(
            {
                "mode_id": "dialogue",
                "priority": 0,
                "action_filter_kind": "none",
                "action_ids": ["attack"],
            }
        )
    errors = [e for e in exc_validate.value.errors() if e["type"] == "value_error"]
    assert len(errors) == 1
    assert "M-INV-1" in errors[0]["msg"]


def test_m_inv_1_allow_with_empty_action_ids_rejected_both_paths() -> None:
    """1c: action_filter_kind="allow" + 空 action_ids → 构造期拒绝（两路径）。"""
    with pytest.raises(ModeInvariantError) as exc_direct:
        ModeOverlay(mode_id="dialogue", priority=0, action_filter_kind="allow")
    assert isinstance(exc_direct.value, ValueError)
    assert "M-INV-1" in str(exc_direct.value)
    assert "allow" in str(exc_direct.value)

    with pytest.raises(ValidationError) as exc_validate:
        ModeOverlay.model_validate(
            {"mode_id": "dialogue", "priority": 0, "action_filter_kind": "allow"}
        )
    errors = [e for e in exc_validate.value.errors() if e["type"] == "value_error"]
    assert len(errors) == 1
    assert "M-INV-1" in errors[0]["msg"]


def test_m_inv_1_deny_with_empty_action_ids_rejected_both_paths() -> None:
    """1d: action_filter_kind="deny" + 空 action_ids → 构造期拒绝（两路径）。

    源码实际模式：allow/deny 同分支（gameplay_mode.py:129-138
    "``'allow'`` / ``'deny'`` ⇒ ``action_ids`` 非空"）——设计文档逐字
    "allow/deny ⇒ action_ids 非空"的 deny 侧同式覆盖。
    """
    with pytest.raises(ModeInvariantError) as exc_direct:
        ModeOverlay(mode_id="dialogue", priority=0, action_filter_kind="deny")
    assert isinstance(exc_direct.value, ValueError)
    assert "M-INV-1" in str(exc_direct.value)
    assert "deny" in str(exc_direct.value)

    with pytest.raises(ValidationError) as exc_validate:
        ModeOverlay.model_validate(
            {"mode_id": "dialogue", "priority": 0, "action_filter_kind": "deny"}
        )
    errors = [e for e in exc_validate.value.errors() if e["type"] == "value_error"]
    assert len(errors) == 1
    assert "M-INV-1" in errors[0]["msg"]


# ─────────────── 2. M-INV-2（operations 非空 + origin 映射）───────────────


def test_m_inv_2_empty_operations_rejected_both_paths() -> None:
    """2a: 空 operations → 构造期 ModeInvariantError（两路径）。"""
    # 直接构造路径：具名 ModeInvariantError（ValueError 族）。
    with pytest.raises(ModeInvariantError) as exc_direct:
        ModeChangeRequest(
            request_id="req_test_0001",
            source=make_provenance(OriginKind.SCENARIO),
            operations=(),
        )
    assert isinstance(exc_direct.value, ValueError)
    assert "M-INV-2" in str(exc_direct.value)
    assert "operations" in str(exc_direct.value)

    # model_validate 路径：ValidationError（value_error 条目保留 M-INV-2 原文）。
    with pytest.raises(ValidationError) as exc_validate:
        ModeChangeRequest.model_validate(
            {
                "request_id": "req_test_0001",
                "source": {"producer_id": "policy.test", "origin": "scenario"},
                "operations": [],
            }
        )
    errors = [e for e in exc_validate.value.errors() if e["type"] == "value_error"]
    assert len(errors) == 1
    assert "M-INV-2" in errors[0]["msg"]


def test_m_inv_2_missing_source_rejected_both_paths() -> None:
    """2b: source（Provenance，K6 Spec:315）必填——缺失两路径 ValidationError。

    缺失字段是 pydantic required 错误（非 M-INV-2 跨字段 value_error），
    直接构造路径的 ``__init__`` 不转译、原样穿透（设计文档 §3.10
    ModeChangeRequest docstring 逐字口径）。
    """
    with pytest.raises(ValidationError) as exc_direct:
        ModeChangeRequest(
            request_id="req_test_0001",
            operations=[activate("dialogue")],
        )
    assert exc_direct.value.errors()[0]["type"] == "missing"
    assert exc_direct.value.errors()[0]["loc"] == ("source",)

    with pytest.raises(ValidationError) as exc_validate:
        ModeChangeRequest.model_validate(
            {
                "request_id": "req_test_0001",
                "operations": [{"operation_kind": "activate", "mode_id": "dialogue"}],
            }
        )
    assert exc_validate.value.errors()[0]["type"] == "missing"


def test_m_inv_2_legal_origin_image_set_accepted() -> None:
    """2c: M-INV-2 合法源像集（D-P4-15 origin 映射，provenance.py:49/53/55）。

    Script → SCENARIO（provenance.py:53）/ RuleEngine、Plugin → SYSTEM（:55）/
    行为策略侧源（Spec:1442）→ BEHAVIOR_POLICY（:49）——三值接受，其余同式拒绝。
    """
    for origin in (OriginKind.SCENARIO, OriginKind.SYSTEM, OriginKind.BEHAVIOR_POLICY):
        request = make_request([activate("dialogue")], origin=origin)
        assert request.source.origin is origin
        assert request.operations == (activate("dialogue"),)


def test_m_inv_2_illegal_origins_rejected() -> None:
    """2d: origin 非法（RULE / SCRIPT / DYNAMICS_BACKEND / DEVELOPER）→ 拒绝（两路径）。

    D-P4-15 末段：SCRIPT / RULE 字面值属 P1 writer 族 origin 值
    （provenance.py:49-55），P4 映射不复用 SCRIPT 字面值而归入 SCENARIO 族——
    字面值层面 RULE / SCRIPT 本身不在合法源像集，同式拒绝。
    """
    for origin in (
        OriginKind.RULE,
        OriginKind.SCRIPT,
        OriginKind.DYNAMICS_BACKEND,
        OriginKind.DEVELOPER,
    ):
        # 直接构造路径：具名 ModeInvariantError（ValueError 族）。
        with pytest.raises(ModeInvariantError) as exc_direct:
            make_request([activate("dialogue")], origin=origin)
        assert isinstance(exc_direct.value, ValueError)
        assert "M-INV-2" in str(exc_direct.value)
        assert origin.value in str(exc_direct.value)

        # model_validate 路径：ValidationError（value_error 条目保留 M-INV-2 原文）。
        with pytest.raises(ValidationError) as exc_validate:
            ModeChangeRequest.model_validate(
                {
                    "request_id": "req_test_0001",
                    "source": {
                        "producer_id": "policy.test",
                        "origin": origin.value,
                    },
                    "operations": [
                        {"operation_kind": "activate", "mode_id": "dialogue"}
                    ],
                }
            )
        errors = [e for e in exc_validate.value.errors() if e["type"] == "value_error"]
        assert len(errors) == 1
        assert "M-INV-2" in errors[0]["msg"]


# ─────────────── 3. registry 键不匹配拒绝（INV-P4-3 上半既有面）───────────────


def test_registry_key_mismatch_rejected() -> None:
    """3: ModeOverlayRegistry 键 != overlay.mode_id → ModeInvariantError。"""
    dialogue = make_overlay("dialogue", 0)
    with pytest.raises(ModeInvariantError) as exc:
        ModeOverlayRegistry({"wrong_key": dialogue})
    assert isinstance(exc.value, ValueError)
    assert "wrong_key" in str(exc.value)
    assert "dialogue" in str(exc.value)

    # 正例：键 == overlay.mode_id 逐条通过后保留不可变快照（INV-P4-3）。
    registry = ModeOverlayRegistry({"zeta": make_overlay("zeta", 1), "dialogue": dialogue})
    assert registry.get("dialogue") is dialogue
    assert registry.get("ghost") is None  # 查找点不抛（拒绝语义归下半 T09 解析期）
    assert registry.mode_ids() == ("dialogue", "zeta")  # casefold 排序


# ─────────────── 4. merge 五性质（Spec:1424-1433 / D-P4-14）───────────────


def test_merge_single_overlay_passthrough() -> None:
    """4a: 单 overlay 透传——全部字段值 == overlay 原值，winner 全为自身。"""
    time_policy = TimePolicy(
        fast_forward_enabled=False,
        checkpoint_interval_ticks=7,
        max_ticks_per_step=3,
        pause_on_player_boundary=False,
    )
    solo = make_overlay(
        "solo",
        5,
        action_filter_kind="allow",
        action_ids=("jump", "look"),
        systems=("combat", "ai"),
        time_policy=time_policy,
        checkpoint_interval=9,
        input_policy={"weights": {"focus": 0.5}},
        context={"k": "v"},
    )
    merged = merge_modes({"solo": solo})
    assert merged.time_policy == time_policy  # 整对象替换（Spec:1428）
    assert merged.checkpoint_interval == 9
    assert merged.input_policy == {"weights": {"focus": 0.5}}
    assert merged.action_filter_kind == "allow"
    assert merged.action_ids == ("jump", "look")
    assert merged.activated_systems == frozenset({"combat", "ai"})
    assert merged.context == {"k": "v"}
    assert merged.winner_by_field == {
        "time_policy": "solo",
        "checkpoint_interval": "solo",
        "input_policy": "solo",
        "action_filter": "solo",
    }


def test_merge_dual_overlay_higher_priority_wins() -> None:
    """4b: 双 overlay 高 priority 胜（D-P4-14 胜者 = priority 最大）。"""
    low = make_overlay(
        "low",
        1,
        time_policy=TimePolicy(max_ticks_per_step=1),
        checkpoint_interval=2,
        input_policy={"src": "low"},
        context={"shared": "low", "only_low": 1},
    )
    high = make_overlay(
        "high",
        10,
        time_policy=TimePolicy(max_ticks_per_step=2),
        checkpoint_interval=3,
        input_policy={"src": "high"},
        context={"shared": "high"},
    )
    merged = merge_modes({"low": low, "high": high})
    assert merged.time_policy == high.time_policy
    assert merged.checkpoint_interval == 3
    assert merged.input_policy == {"src": "high"}
    # context 浅合并：高 priority 逐键胜，低优先独有键保留（D-P4-14）。
    assert merged.context == {"shared": "high", "only_low": 1}
    # 两者均 none 过滤 → 无 "action_filter" 胜者键（仅非空值在场时收录）。
    assert merged.winner_by_field == {
        "time_policy": "high",
        "checkpoint_interval": "high",
        "input_policy": "high",
    }


def test_merge_priority_tie_casefold_smaller_mode_id_wins() -> None:
    """4c: 平手 → casefold 较小 mode_id 胜（D-P4-14 确定性裁决，A4b）。"""
    zeta = make_overlay(
        "zeta",
        3,
        time_policy=TimePolicy(max_ticks_per_step=1),
        input_policy={"src": "zeta"},
        context={"shared": "zeta"},
    )
    mid = make_overlay(
        "mid",
        3,
        time_policy=TimePolicy(max_ticks_per_step=2),
        input_policy={"src": "mid"},
        context={"shared": "mid"},
    )
    merged = merge_modes({"zeta": zeta, "mid": mid})  # 插入序 = 胜者靠后
    assert merged.winner_by_field == {
        "time_policy": "mid",
        "input_policy": "mid",
    }
    assert merged.time_policy == mid.time_policy
    assert merged.input_policy == {"src": "mid"}
    assert merged.context["shared"] == "mid"


def test_merge_empty_input_all_defaults() -> None:
    """4d: 空输入 → 全缺省（A4③：winner_by_field == {} 且各字段取缺省）。"""
    merged = merge_modes({})
    assert isinstance(merged, MergedModeConfiguration)
    assert merged.winner_by_field == {}
    assert merged.time_policy is None
    assert merged.checkpoint_interval is None
    assert merged.input_policy is None
    assert merged.action_filter_kind == "none"
    assert merged.action_ids == ()
    assert merged.activated_systems == frozenset()
    assert merged.context == {}


def test_merge_winner_by_field_keys_and_values() -> None:
    """4e: winner_by_field 键集与值（Spec:1433 冲突策略 MUST 可检查）。

    源码语义（gameplay_mode.py:284-318）：单胜者字段 = 排序（-priority,
    casefold(mode_id)）**首现非空值**（不必是全局 leader）；action_filter
    胜者 = 排序**首现 kind == 最终 kind** 的 overlay。
    """
    leader = make_overlay("leader", 20)  # 无 time_policy / checkpoint / input
    mid = make_overlay("mid", 10, time_policy=TimePolicy(max_ticks_per_step=5))
    denier = make_overlay(
        "denier", 3, action_filter_kind="deny", action_ids=("zeta", "beta")
    )
    merged = merge_modes({"leader": leader, "mid": mid, "denier": denier})
    # 键集：仅非空值在场时收录（leader 虽全局第一，time_policy 胜者仍是 mid）。
    assert set(merged.winner_by_field) == {"time_policy", "action_filter"}
    assert merged.winner_by_field["time_policy"] == "mid"
    assert merged.winner_by_field["action_filter"] == "denier"
    assert merged.action_filter_kind == "deny"
    assert merged.action_ids == ("beta", "zeta")


# ─────────────── 5. action_filter 四态（Spec:1424-1425 / D-P4-14b）───────────────


def test_merge_action_filter_none_state() -> None:
    """5a: 全 none → kind="none" / ids=()，无 "action_filter" 胜者键。"""
    a = make_overlay("alpha", 2)
    b = make_overlay("beta", 1)
    merged = merge_modes({"alpha": a, "beta": b})
    assert merged.action_filter_kind == "none"
    assert merged.action_ids == ()
    assert "action_filter" not in merged.winner_by_field


def test_merge_action_filter_allow_single() -> None:
    """5b: 单 allow overlay（+ 无约束 overlay 不干扰）→ kind="allow" / ids 原集。"""
    none_overlay = make_overlay("none_side", 5)
    allow_overlay = make_overlay(
        "allow_side", 1, action_filter_kind="allow", action_ids=("walk", "sprint")
    )
    merged = merge_modes({"none_side": none_overlay, "allow_side": allow_overlay})
    assert merged.action_filter_kind == "allow"
    assert merged.action_ids == ("sprint", "walk")  # 排序元组
    assert merged.winner_by_field["action_filter"] == "allow_side"


def test_merge_action_filter_allow_dual_intersection() -> None:
    """5c: 双 allow overlay → ids = 交集（P4 保守侧，D-P4-14b）。"""
    first = make_overlay(
        "first", 2, action_filter_kind="allow", action_ids=("walk", "sprint")
    )
    second = make_overlay(
        "second", 1, action_filter_kind="allow", action_ids=("walk", "rest")
    )
    merged = merge_modes({"first": first, "second": second})
    assert merged.action_filter_kind == "allow"
    assert merged.action_ids == ("walk",)
    # 胜者记录 = 排序首现 kind == "allow" 的 overlay（first）。
    assert merged.winner_by_field["action_filter"] == "first"


def test_merge_action_filter_deny_beats_allow() -> None:
    """5d: deny 压 allow → kind="deny" / ids = 各 deny 集并集（安全默认）。"""
    allow_overlay = make_overlay(
        "allow_side", 2, action_filter_kind="allow", action_ids=("walk",)
    )
    deny_overlay = make_overlay(
        "deny_side", 1, action_filter_kind="deny", action_ids=("attack", "cast")
    )
    merged = merge_modes({"allow_side": allow_overlay, "deny_side": deny_overlay})
    assert merged.action_filter_kind == "deny"
    assert merged.action_ids == ("attack", "cast")
    assert "walk" not in merged.action_ids
    assert merged.winner_by_field["action_filter"] == "deny_side"


# ─────────────── 6. is_action_available 三态（D-P4-14 判定序）───────────────


def test_is_action_available_deny_hit_false() -> None:
    """6a: deny 命中 → False（判定序第一级：deny 大于 allow 交集 大于 无约束）。"""
    merged = merge_modes(
        {
            "denier": make_overlay(
                "denier", 0, action_filter_kind="deny", action_ids=("attack", "move")
            )
        }
    )
    assert is_action_available(merged, "attack") is False
    assert is_action_available(merged, "move") is False
    assert is_action_available(merged, "cast") is True


def test_is_action_available_allow_intersection() -> None:
    """6b: allow 交集含 → True / 不含 → False（判定序第二级）。"""
    first = make_overlay(
        "first", 2, action_filter_kind="allow", action_ids=("walk", "sprint")
    )
    second = make_overlay(
        "second", 1, action_filter_kind="allow", action_ids=("walk", "rest")
    )
    merged = merge_modes({"first": first, "second": second})
    assert is_action_available(merged, "walk") is True  # 交集成员
    assert is_action_available(merged, "sprint") is False  # 非交集成员
    assert is_action_available(merged, "rest") is False


def test_is_action_available_no_constraint_true() -> None:
    """6c: 无约束（kind="none"）→ 恒 True（判定序第三级）。"""
    merged = merge_modes({})
    assert is_action_available(merged, "attack") is True
    assert is_action_available(merged, "any_action") is True


# ─────────────── 7. apply 五路径（T09 核心；P4 唯一 mode 写面）───────────────


def test_apply_activate_new() -> None:
    """7a: activate 新模式 → applied；active_modes / mode_context 增量写入。"""
    dialogue = make_overlay("dialogue", 0, context={"mood": "calm"})
    registry = ModeOverlayRegistry({"dialogue": dialogue})
    runtime = RuntimeState()
    new_runtime, resolution = apply_mode_change(
        request=make_request([activate("dialogue")]),
        runtime=runtime,
        registry=registry,
    )
    assert new_runtime.active_modes == ["dialogue"]
    assert new_runtime.mode_context == {"dialogue": {"mood": "calm"}}
    assert resolution.applied == ("activate:dialogue",)
    assert resolution.ignored == ()
    assert resolution.new_active_modes == ("dialogue",)
    assert resolution.new_mode_context == {"dialogue": {"mood": "calm"}}
    # 旧 runtime 不原地修改（ContractModel frozen + 零公共 mutator）。
    assert runtime.active_modes == []
    assert runtime.mode_context == {}


def test_apply_activate_duplicate_ignored() -> None:
    """7b: activate 已激活模式 → ignored（幂等簿记，无重复激活）。"""
    dialogue = make_overlay("dialogue", 0, context={"mood": "calm"})
    registry = ModeOverlayRegistry({"dialogue": dialogue})
    runtime = RuntimeState(
        active_modes=["dialogue"], mode_context={"dialogue": {"mood": "calm"}}
    )
    new_runtime, resolution = apply_mode_change(
        request=make_request([activate("dialogue")]),
        runtime=runtime,
        registry=registry,
    )
    assert resolution.applied == ()
    assert resolution.ignored == ("activate:dialogue",)
    assert new_runtime.active_modes == ["dialogue"]
    assert new_runtime.mode_context == {"dialogue": {"mood": "calm"}}


def test_apply_deactivate_active() -> None:
    """7c: deactivate 在位模式 → applied；active_modes / mode_context 弹出。"""
    dialogue = make_overlay("dialogue", 0, context={"mood": "calm"})
    registry = ModeOverlayRegistry({"dialogue": dialogue})
    runtime = RuntimeState(
        active_modes=["dialogue"], mode_context={"dialogue": {"mood": "calm"}}
    )
    new_runtime, resolution = apply_mode_change(
        request=make_request([deactivate("dialogue")]),
        runtime=runtime,
        registry=registry,
    )
    assert resolution.applied == ("deactivate:dialogue",)
    assert resolution.ignored == ()
    assert new_runtime.active_modes == []
    assert new_runtime.mode_context == {}
    assert resolution.new_active_modes == ()
    assert resolution.new_mode_context == {}


def test_apply_deactivate_absent_ignored() -> None:
    """7d: deactivate 缺席模式 → ignored（幂等簿记，无重复停用）。"""
    dialogue = make_overlay("dialogue", 0)
    registry = ModeOverlayRegistry({"dialogue": dialogue})
    runtime = RuntimeState()
    new_runtime, resolution = apply_mode_change(
        request=make_request([deactivate("dialogue")]),
        runtime=runtime,
        registry=registry,
    )
    assert resolution.applied == ()
    assert resolution.ignored == ("deactivate:dialogue",)
    assert new_runtime.active_modes == []
    assert new_runtime.mode_context == {}


def test_apply_unknown_mode_atomic_rejection() -> None:
    """7e: 未知 mode 原子拒绝（UnknownModeError，LookupError 族；D-P4-17）。

    原子预校验先于任何簿记变更（apply_mode_change 第 1 步）：请求序首条合法、
    次条未知 → 整体拒绝，原 runtime model_dump 全字段不变。
    """
    dialogue = make_overlay("dialogue", 0, context={"mood": "calm"})
    registry = ModeOverlayRegistry({"dialogue": dialogue})
    runtime = RuntimeState(
        active_modes=["dialogue"], mode_context={"dialogue": {"mood": "calm"}}
    )
    before = runtime.model_dump()

    with pytest.raises(UnknownModeError) as exc:
        apply_mode_change(
            request=make_request([activate("dialogue"), activate("ghost")]),
            runtime=runtime,
            registry=registry,
        )
    assert isinstance(exc.value, LookupError)  # D-P4-17 按族断言基类
    assert runtime.model_dump() == before  # 原子性：零簿记变更

    with pytest.raises(UnknownModeError):
        apply_mode_change(
            request=make_request([activate("ghost")]),
            runtime=runtime,
            registry=registry,
        )
    assert runtime.model_dump() == before


# ─────────────── 8. M-INV-5（rebuild_runtime 位级不变，INV-P4-5）───────────────


def test_m_inv_5_other_fields_bitwise_unchanged() -> None:
    """8: apply 后除 active_modes / mode_context 外 model_dump 全键相等。

    new_runtime is not runtime（唯一重建通道 rebuild_runtime，clock.py:
    151-158）；rng_state / backend_refs / scheduler_queue / active_actions /
    pending_proposals 位级不变（INV-P4-5：零世界状态效果、零事件、零事务、
    零队列变更）。
    """
    actor = EntityId("ent_player")
    provenance = make_provenance(OriginKind.SCENARIO)
    instance_id = ActionInstanceId("act_0001")
    proposal = ActionProposal(
        proposal_id=instance_id,
        actor_id=actor,
        action_id=ActionTypeId("rest"),
        base_world_revision=INITIAL_WORLD_REVISION,
        provenance=provenance,
    )
    active_action = ActiveAction(
        instance_id=instance_id,
        action_id=ActionTypeId("rest"),
        actor_id=actor,
        status=ActionLifecycleStatus.ACTIVE,
        start_tick=0,
        base_world_revision=INITIAL_WORLD_REVISION,
        provenance=provenance,
    )
    runtime = RuntimeState(
        logical_tick=42,
        scheduler_queue=[
            ScheduledEvent(
                entry_id=ScheduledEntryId("sch_0001"),
                due_tick=10,
                kind="wakeup",
                payload={"instance_id": "act_0001"},
            )
        ],
        active_actions={instance_id: active_action},
        active_modes=["dialogue"],
        mode_context={"dialogue": {"mood": "calm"}},
        rng_state=RngState(algorithm="pcg32", state={"counter": 7, "seed": "s0"}),
        pending_proposals=[proposal],
        backend_refs={
            "dyn_1": BackendStateRef(
                backend_id="dyn_1", backend_kind="dynamics", checkpointable=True
            )
        },
    )
    tactical = make_overlay("tactical", 5, context={"stance": "aggressive"})
    registry = ModeOverlayRegistry({"dialogue": make_overlay("dialogue", 0),
                                    "tactical": tactical})
    new_runtime, _resolution = apply_mode_change(
        request=make_request([activate("tactical")]),
        runtime=runtime,
        registry=registry,
    )
    assert new_runtime is not runtime
    old_dump = runtime.model_dump()
    new_dump = new_runtime.model_dump()
    assert set(old_dump) == set(new_dump)
    # M-INV-5：除 active_modes / mode_context 外全键相等（位级不变口径 =
    # model_dump 深相等，P1 唯一合法序列化路径）。
    for key, value in old_dump.items():
        if key in {"active_modes", "mode_context"}:
            continue
        assert new_dump[key] == value, key
    # INV-P4-5 点名五字段逐一钉死。
    for key in ("rng_state", "backend_refs", "scheduler_queue",
                "active_actions", "pending_proposals"):
        assert new_dump[key] == old_dump[key]
    # 变更字段按预期。
    assert new_dump["active_modes"] == ["dialogue", "tactical"]
    assert new_dump["mode_context"]["dialogue"] == {"mood": "calm"}
    assert new_dump["mode_context"]["tactical"] == {"stance": "aggressive"}


# ─────────────── 9. context 别名断裂（M-INV-5 后半；A6 断言面）───────────────


def test_context_alias_break_after_apply() -> None:
    """9: apply activate 成功后 mutate 原 overlay.context → 新 runtime 不含注入键。

    activate 以引用赋值 ``ctx[mode_id] = overlay.context``，唯一重建通道
    rebuild_runtime 的 model_dump → model_validate roundtrip 天然断裂容器
    别名（clock.py:151-158）——apply 后 mutate 原 overlay.context（浅冻结
    不防深层 dict 变更）不得反映到 new_runtime.mode_context。
    """
    dialogue = make_overlay("dialogue", 0, context={"mood": "calm"})
    registry = ModeOverlayRegistry({"dialogue": dialogue})
    new_runtime, _resolution = apply_mode_change(
        request=make_request([activate("dialogue")]),
        runtime=RuntimeState(),
        registry=registry,
    )
    assert new_runtime.mode_context["dialogue"] == {"mood": "calm"}
    dialogue.context["injected_key"] = "must_not_leak"
    assert "injected_key" not in new_runtime.mode_context["dialogue"]
    assert new_runtime.mode_context["dialogue"] == {"mood": "calm"}


# ─────────────── 10. §6.1 补充（M-INV-3/4/6 + merge 确定性 A4）───────────────


def test_m_inv_3_apply_signature_three_keyword_only_params_no_world() -> None:
    """10a: M-INV-3 结构面（G4-6 结构断言面）。

    ``apply_mode_change`` 签名 = 三 keyword-only 参数 {request, runtime,
    registry}，**无世界状态参数**（Spec:1409 "Mode 是 overlay，不是另一个
    world"；设计文档 §3.10 L710-711 逐字）。
    """
    params = inspect.signature(apply_mode_change).parameters
    assert set(params) == {"request", "runtime", "registry"}
    for name, param in params.items():
        assert param.kind is inspect.Parameter.KEYWORD_ONLY, name
    assert "world" not in params
    assert not any(
        param.kind is inspect.Parameter.VAR_POSITIONAL for param in params.values()
    )


def test_m_inv_4_effects_always_empty() -> None:
    """10b: M-INV-4——所有 apply 成功路径 resolution.effects == ()。

    模式变更零世界效果（P4 域恒空；P5 扩展位保留字段，Spec:1452 由
    ModePolicy 解析的扩展空间）。
    """
    dialogue = make_overlay("dialogue", 0)
    registry = ModeOverlayRegistry({"dialogue": dialogue})
    cases = [
        (RuntimeState(), [activate("dialogue")]),  # activate 新
        (
            RuntimeState(active_modes=["dialogue"], mode_context={"dialogue": {}}),
            [activate("dialogue")],  # activate 重复 ignored
        ),
        (
            RuntimeState(active_modes=["dialogue"], mode_context={"dialogue": {}}),
            [deactivate("dialogue")],  # deactivate 在位
        ),
        (RuntimeState(), [deactivate("dialogue")]),  # deactivate 缺席 ignored
    ]
    for runtime, operations in cases:
        new_runtime, resolution = apply_mode_change(
            request=make_request(operations),
            runtime=runtime,
            registry=registry,
        )
        assert isinstance(resolution, ModeChangeResolution)
        assert resolution.effects == ()
        assert new_runtime is not runtime  # 唯一重建通道（M-INV-5 前半）


def test_m_inv_6_input_policy_opaque_passthrough() -> None:
    """10c: M-INV-6——input_policy 不透明透传（P4 直通不解释，P8 表现层消费）。

    overlay.input_policy 经 merge 单一胜者整值透传（Spec:1428 per-property
    winner 同式），内容（任意嵌套 JsonValue）不被 P4 解释——深相等断言。
    """
    opaque = {
        "schema": "custom_input/1",
        "weights": {"focus": 0.25, "pan": 0.75},
        "nested": [{"key": "a", "flag": True}, [1, 2, 3]],
    }
    low = make_overlay("low", 1, input_policy={"src": "low"})
    high = make_overlay("high", 10, input_policy=opaque)
    merged = merge_modes({"low": low, "high": high})
    assert merged.input_policy == opaque  # 单一胜者整值透传
    assert merged.winner_by_field["input_policy"] == "high"
    assert merged.input_policy != {"src": "low"}  # 低优先整值弃用，无字段级合并
    # 序列化 roundtrip 后深结构仍相等（不透明 JsonValue，无 P4 侧解释痕迹）。
    assert merged.model_dump()["input_policy"] == opaque


def test_merge_determinism_repeat_calls_and_input_order_perturbation() -> None:
    """10d: merge_modes 确定性（A4 单测像，§6.1 A4 行 L1681 口径）。

    以 §3.10 实际语义为准并注明：merge_modes 是纯函数，内部按
    (-priority, casefold(mode_id)) 排序（gameplay_mode.py:275-278）——确定性
    且排列不变，故：① 同输入重复调用 → 全等输出（model_dump 字段逐一相等）；
    ② overlay 输入序（dict 插入序）扰动 → 同一胜者口径：平手裁定 =
    casefold 较小 id（A4b 钉死样例 "tactical" vs "alpha" → 胜者 "alpha"，
    D-P4-14）。
    """
    tactical = make_overlay(
        "tactical",
        7,
        time_policy=TimePolicy(max_ticks_per_step=1),
        input_policy={"src": "tactical"},
        context={"shared": "tactical"},
    )
    alpha = make_overlay(
        "alpha",
        7,
        time_policy=TimePolicy(max_ticks_per_step=2),
        input_policy={"src": "alpha"},
        context={"shared": "alpha"},
    )
    first = merge_modes({"tactical": tactical, "alpha": alpha})
    # ① 同输入重复调用 → 全等输出。
    repeat = merge_modes({"tactical": tactical, "alpha": alpha})
    assert repeat.model_dump() == first.model_dump()
    # ② overlay 输入序扰动 → 同一胜者口径（排列不变）。
    perturbed = merge_modes({"alpha": alpha, "tactical": tactical})
    assert perturbed.model_dump() == first.model_dump()
    assert perturbed.winner_by_field["time_policy"] == "alpha"
    assert perturbed.winner_by_field["input_policy"] == "alpha"
    assert perturbed.context["shared"] == "alpha"
