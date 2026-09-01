"""P8 T05：WorldInstance branch / fork 原型（零 IO，零模块状态）。

本模块是 ``src.engine_v2.persistence`` 包 branch 面（P8 T05，SOT §3.6）：
以 :class:`WorldInstanceHandle`（信封层实例身份，D-9 + ``WorldState`` /
``RuntimeState``）为源，顺序执行 Spec §30.5 三项闭集检查（P8-INV-5），
任一失败 → :class:`BranchError`（message 含检查名 + 涉事对象/backend_id）：

1. ``backend_checkpoint_support``——``runtime_state.backend_refs`` 逐条
   能力核对（``checkpointable=False`` 默认**明确拒绝**，G8-4 非静默；
   ``allow_degraded=True`` → 记入 ``degraded_backends`` 显式点名；
   ``checkpointable=True`` → ``checkpoints`` 必含该 backend 的 payload——
   缺 → 拒绝，非 dict → ``schema_invalid``）；
   ``BackendCheckpointRegistry.validate_refs`` 注册面交叉核对 issue 面并入
   该检查行 detail（报告面，不抛）；
2. ``runtime_snapshot_availability``——以 ``new_world_instance_id`` 构造
   冻结 ``snapshot``（零别名固化内建，D-15 第 4 条）；
   ``check_snapshot_versions`` 非空 → ``version_mismatch``（issues 并入
   message/detail）；
3. ``project_compatibility``——project version 双方均给且不等 → 拒绝；
   ``module_versions`` 双方共有键值不同 → 拒绝；任一侧 None → 该项通过
   （兼容面锚定 host 给值，不猜）。

重建：冻结 ``restore_snapshot``（零别名还原内建）→ ``(world_state,
runtime_state)`` 零别名新对象 → ``WorldInstanceHandle(new_world_instance_id,
…)``（G8-3 独立性的机械根据——A5/A22）。branch **不 bump**
``world_revision``（分支非提交；新分支首笔提交由 host 经正常管道完成）。

导出（SOT §8.2 台账 5 名）：

- :data:`BRANCH_CHECKS`——三项闭集检查名锚（Spec §30.5 L1617–1620）；
- :class:`BranchError`——T05 错误族（``PersistenceError`` 子类；默认码
  ``branch_rejected``；D7 fail-loud 单错误族）；
- :class:`WorldInstanceHandle`——branch 源载体（frozen dataclass；
  ``to_dict`` JSON-clean，D3）；
- :class:`BranchResult`——branch 结果载体（frozen dataclass；
  ``degraded_backends`` 显式点名面 + 3 行 ``checks``；``to_dict``
  JSON-clean）；
- :func:`branch_world`——三检查 + 零别名重建（纯函数；零 IO，D4）。

纪律：零 IO（D4）；零时钟 / 零随机（D5/D6）；零模块状态；文档面不出现
推理侧 12 名独立词（D2）。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from src.engine_v2.core import (
    RuntimeState,
    WorldState,
    assert_json_clean,
    check_snapshot_versions,
    restore_snapshot,
)
from src.engine_v2.core.snapshot import snapshot
from src.engine_v2.persistence.base import PersistenceError
from src.engine_v2.persistence.checkpoint import BackendCheckpointRegistry

__all__ = (
    "BRANCH_CHECKS",
    "BranchError",
    "WorldInstanceHandle",
    "BranchResult",
    "branch_world",
)

#: Spec §30.5 L1617–1620 三项闭集（P8-INV-5）；``BranchResult.checks``
#: 行名锚（snake_case 归一）。
BRANCH_CHECKS: Final[tuple[str, ...]] = (
    "backend_checkpoint_support",
    "runtime_snapshot_availability",
    "project_compatibility",
)


class BranchError(PersistenceError):
    """T05 branch 错误族（``PersistenceError`` 子类；D7 fail-loud）。

    默认码 ``branch_rejected``（SOT §3.6）；``code=`` 可显式指定 P8 错误码
    闭集另一成员（``schema_invalid``——payload 形态 / id 词法坏；
    ``version_mismatch``——``check_snapshot_versions`` 非空）。
    """

    def __init__(self, message: str, *, code: str = "branch_rejected") -> None:
        super().__init__(code, message)


@dataclass(frozen=True)
class WorldInstanceHandle:
    """branch 源载体（SOT §3.6；D-9 信封层身份）。

    - ``world_instance_id``：host 给出（实例身份在信封层，不在
      ``WorldState`` 内——``core/snapshot.py:130`` 注释同族）；
    - ``world_state`` / ``runtime_state``：两态（branch 只读不写——零
      状态直写，K2）。
    """

    world_instance_id: str
    world_state: WorldState
    runtime_state: RuntimeState

    def to_dict(self) -> dict[str, object]:
        """JSON-clean 全量面（D3）：实例身份 + 两态
        （``model_dump(mode="json")``）。"""
        result: dict[str, object] = {
            "world_instance_id": self.world_instance_id,
            "world_state": self.world_state.model_dump(mode="json"),
            "runtime_state": self.runtime_state.model_dump(mode="json"),
        }
        assert_json_clean(result)
        return result


@dataclass(frozen=True)
class BranchResult:
    """branch 结果载体（SOT §3.6；零别名重建产物）。

    - ``handle``：新实例句柄（``world_instance_id`` = 新 id；G8-3）；
    - ``degraded_backends``：degraded 开关下的点名面（G8-4 非静默）；
    - ``checks``：3 行，行名 = :data:`BRANCH_CHECKS`，每行
      ``{"check", "ok", "detail"}``（detail = 报告面并入串，如
      ``validate_refs`` issue）。
    """

    handle: WorldInstanceHandle
    degraded_backends: tuple[str, ...]
    checks: tuple[dict[str, object], ...]

    def to_dict(self) -> dict[str, object]:
        """JSON-clean 全量面（D3）：handle + degraded 点名 + 3 行检查。"""
        result: dict[str, object] = {
            "handle": self.handle.to_dict(),
            "degraded_backends": list(self.degraded_backends),
            "checks": [dict(row) for row in self.checks],
        }
        assert_json_clean(result)
        return result


def _check_backend_support(
    source: WorldInstanceHandle,
    registry: BackendCheckpointRegistry,
    checkpoints: Mapping[str, Mapping[str, object]] | None,
    allow_degraded: bool,
) -> tuple[tuple[str, ...], str]:
    """检查 1（``backend_checkpoint_support``）：逐条能力核对 + 报告面并入。

    返回 ``(degraded_backends, check1_detail)``；默认拒绝 / payload 缺失 /
    payload 非 dict 均抛 :class:`BranchError`（message 点名 backend_id）。
    """
    check_name = BRANCH_CHECKS[0]
    refs = tuple(source.runtime_state.backend_refs.values())
    degraded: list[str] = []
    for ref in refs:
        if not ref.checkpointable:
            if not allow_degraded:
                raise BranchError(
                    message=(
                        f"check {check_name}: backend {ref.backend_id!r} "
                        "non-checkpointable，默认明确拒绝 branch（G8-4；"
                        "需降级时显式 allow_degraded=True）"
                    )
                )
            degraded.append(ref.backend_id)
        else:
            if checkpoints is None or ref.backend_id not in checkpoints:
                raise BranchError(
                    message=(
                        f"check {check_name}: backend {ref.backend_id!r} 声明 "
                        "checkpointable=True，但未提供 checkpoint payload"
                        "（checkpoints 须含其体）"
                    )
                )
            payload = checkpoints[ref.backend_id]
            if not isinstance(payload, Mapping):
                raise BranchError(
                    code="schema_invalid",
                    message=(
                        f"check {check_name}: backend {ref.backend_id!r} "
                        f"checkpoint payload 非 dict：{type(payload).__name__}"
                    ),
                )
    issues = registry.validate_refs(refs)
    return (tuple(degraded), "; ".join(issues) if issues else "")


def _check_snapshot(source: WorldInstanceHandle, new_world_instance_id: str):
    """检查 2（``runtime_snapshot_availability``）：构造冻结 Snapshot +
    版本门禁（非空 → ``version_mismatch``，issues 并入 message）。

    返回通过检查的 Snapshot（重建面消费——冻结缝 `core/snapshot.py`）。
    """
    check_name = BRANCH_CHECKS[1]
    snap = snapshot(source.world_state, source.runtime_state, new_world_instance_id)
    issues = check_snapshot_versions(snap)
    if issues:
        raise BranchError(
            code="version_mismatch",
            message=(
                f"check {check_name}: 快照版本检查非空（{len(issues)} 项）："
                + "; ".join(issues)
            ),
        )
    return snap


def _check_project_compat(
    source_project_version: str | None,
    target_project_version: str | None,
    source_module_versions: Mapping[str, str] | None,
    target_module_versions: Mapping[str, str] | None,
) -> None:
    """检查 3（``project_compatibility``）：版本面 host 给值核对。

    双方均给且不等 → 拒绝；module versions 共有键值冲突 → 拒绝；任一侧
    None → 通过（不猜）。
    """
    check_name = BRANCH_CHECKS[2]
    if (
        source_project_version is not None
        and target_project_version is not None
        and source_project_version != target_project_version
    ):
        raise BranchError(
            message=(
                f"check {check_name}: project version 不兼容——source="
                f"{source_project_version!r} != target={target_project_version!r}"
            )
        )
    if source_module_versions is not None and target_module_versions is not None:
        conflicts = sorted(
            key
            for key in set(source_module_versions) & set(target_module_versions)
            if source_module_versions[key] != target_module_versions[key]
        )
        if conflicts:
            raise BranchError(
                message=(
                    f"check {check_name}: module version 共有键值冲突："
                    f"{conflicts!r}"
                )
            )


def branch_world(
    source: WorldInstanceHandle,
    *,
    new_world_instance_id: str,
    registry: BackendCheckpointRegistry,
    checkpoints: Mapping[str, Mapping[str, object]] | None = None,
    allow_degraded: bool = False,
    source_project_version: str | None = None,
    target_project_version: str | None = None,
    source_module_versions: Mapping[str, str] | None = None,
    target_module_versions: Mapping[str, str] | None = None,
) -> BranchResult:
    """branch / fork WorldInstance 原型（SOT §3.6；零 IO，D4）。

    三检查顺序执行（任一失败 → :class:`BranchError`，message 含检查名 +
    涉事对象），随后冻结 ``restore_snapshot`` 零别名重建：

    - 前置：``new_world_instance_id`` 空串 / 纯空白 →
      ``schema_invalid``（id host 给出，D5）；
    - 检查 1 ``backend_checkpoint_support``（默认拒绝 non-checkpointable，
      G8-4；degraded 显式点名）；
    - 检查 2 ``runtime_snapshot_availability``（冻结 Snapshot +
      ``check_snapshot_versions`` 门禁）；
    - 检查 3 ``project_compatibility``（host 给值核对）；
    - 重建：``restore_snapshot`` → 零别名 ``(world_state, runtime_state)``
      → ``WorldInstanceHandle(new_world_instance_id, …)``；**不 bump**
      ``world_revision``（分支非提交）。
    """
    if not new_world_instance_id.strip():
        raise BranchError(
            code="schema_invalid",
            message="new_world_instance_id 为空/纯空白（id 由 host 给出，须非空）",
        )
    degraded, check1_detail = _check_backend_support(
        source, registry, checkpoints, allow_degraded
    )
    snap = _check_snapshot(source, new_world_instance_id)
    _check_project_compat(
        source_project_version,
        target_project_version,
        source_module_versions,
        target_module_versions,
    )
    world_state, runtime_state = restore_snapshot(snap)
    handle = WorldInstanceHandle(
        world_instance_id=new_world_instance_id,
        world_state=world_state,
        runtime_state=runtime_state,
    )
    checks = (
        {"check": BRANCH_CHECKS[0], "ok": True, "detail": check1_detail},
        {"check": BRANCH_CHECKS[1], "ok": True, "detail": ""},
        {"check": BRANCH_CHECKS[2], "ok": True, "detail": ""},
    )
    return BranchResult(
        handle=handle, degraded_backends=degraded, checks=checks
    )
