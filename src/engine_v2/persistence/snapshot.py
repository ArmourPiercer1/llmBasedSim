"""P8 持久化信封面：PersistenceSnapshot + 4 函数面（T01，SOT §3.2）。

- :class:`PersistenceSnapshot` —— P8 层信封（``ContractModel`` 继承：frozen +
  ``extra="forbid"``）；嵌套复用冻结 core ``Snapshot``（D-P8-02：零字段重定义）；
  顶层冗余镜像（``project_version`` / ``module_versions``，Spec §30.2
  L1589–1590）经 ``model_validator`` 与嵌套值严格相等交叉校验（失配 →
  ``schema_invalid``，P8-INV-10）；
- :func:`to_persistence_snapshot` —— core ``Snapshot`` → 信封（纯函数；
  ``deep_copy_via_roundtrip`` 固化，零别名，D15）；
- :func:`dump_persistence_snapshot` —— 信封 → JSON 文本（D6 确定性；
  冻结序列化面唯一出口）；
- :func:`load_persistence_snapshot` —— JSON 文本 → 信封（fail-loud 四道门：
  JSON 词法 → 契约结构 → P8 层版本门 → 冻结 ``check_snapshot_versions``
  嵌套交叉校验，P8-INV-10 load 面）；
- :func:`check_persistence_versions` —— 三层版本一致性**报告**面（纯函数；
  空元组 = 一致；处置面 = load 的异常门）。

纪律：零 IO（D4 收拢于 ``filesystem.py``）；数据面零 datetime
（``created_wall_time`` 为 host 给出的 ISO-8601 串，D3/D6）；文档面不出现
推理侧 12 名独立词（D2）。
"""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import Field, ValidationError, model_validator

from src.engine_v2.core import (
    ContractModel,
    Snapshot,
    assert_json_clean,
    check_snapshot_versions,
    deep_copy_via_roundtrip,
    dump_json,
    load_json,
)
from src.engine_v2.persistence.base import (
    PERSISTENCE_FORMAT_VERSION,
    PersistenceError,
)

__all__ = (
    "PersistenceSnapshot",
    "to_persistence_snapshot",
    "dump_persistence_snapshot",
    "load_persistence_snapshot",
    "check_persistence_versions",
)


class PersistenceSnapshot(ContractModel):
    """P8 持久化信封（P8-INV-10 P8 层；嵌套冻结 core 信封，D-P8-02）。

    字段逐项（顺序冻结，SOT §3.2）：

    - ``persistence_format_version``：P8 层版本（默认当前世代；load 门要求
      == 当前世代，否则 ``version_mismatch``）；
    - ``snapshot``：core ``Snapshot`` 信封（嵌套模型而非裸 dict——R6：
      嵌套模型保校验深度）；
    - ``project_version`` / ``module_versions``：顶层冗余镜像（Spec §30.2
      L1589–1590）；``model_validator`` 交叉校验与嵌套值严格相等（失配 →
      ``schema_invalid``）；
    - ``backend_checkpoints``：backend_id → checkpoint_ref（相对路径，如
      ``"checkpoints/toy_rigid.json"``；只存 ref 不存体——体在
      ``checkpoints/`` 目录，T04 消费）；
    - ``trace_ref``：trace 文件相对路径（如 ``"trace.jsonl"``）；
    - ``created_wall_time``：ISO-8601 串（**非 datetime**——P8 数据面零
      datetime，D3/D6；诊断面，host 给出，不参与状态身份）。
    """

    persistence_format_version: int = PERSISTENCE_FORMAT_VERSION
    snapshot: Snapshot
    project_version: str | None = None
    module_versions: dict[str, str] = Field(default_factory=dict)
    backend_checkpoints: dict[str, str] = Field(default_factory=dict)
    trace_ref: str | None = None
    created_wall_time: str | None = None

    @model_validator(mode="after")
    def _check_redundant_mirrors(self) -> PersistenceSnapshot:
        """顶层冗余镜像与嵌套值严格相等（P8-INV-10；失配 → schema_invalid）。"""
        if self.project_version != self.snapshot.project_version:
            raise PersistenceError(
                "schema_invalid",
                "顶层冗余镜像 project_version 与嵌套值失配："
                f"{self.project_version!r} != {self.snapshot.project_version!r}",
            )
        if self.module_versions != self.snapshot.module_versions:
            raise PersistenceError(
                "schema_invalid",
                "顶层冗余镜像 module_versions 与嵌套值失配："
                f"{self.module_versions!r} != {self.snapshot.module_versions!r}",
            )
        return self

    def to_dict(self) -> dict[str, object]:
        """JSON-clean 全量面（D3）：``model_dump(mode="json")`` + 断言 clean。"""
        result = self.model_dump(mode="json")
        assert_json_clean(result)
        return result


def to_persistence_snapshot(
    snapshot: Snapshot,
    *,
    backend_checkpoints: Mapping[str, str] | None = None,
    trace_ref: str | None = None,
    created_wall_time: str | None = None,
) -> PersistenceSnapshot:
    """core ``Snapshot`` → P8 信封（纯函数；零别名固化）。

    - 入参经 ``deep_copy_via_roundtrip`` 固化：信封与入参不共享任何可变
      容器（后置修改入参不波及信封，t9 面）；
    - ``project_version`` / ``module_versions`` 自嵌套镜像（镜像一致性
      不变量构造上成立）；
    - ``backend_checkpoints`` / ``trace_ref`` / ``created_wall_time`` 由
      host 给出（D5/D6：零生成、零时钟）。
    """
    frozen = deep_copy_via_roundtrip(snapshot)
    return PersistenceSnapshot(
        snapshot=frozen,
        project_version=frozen.project_version,
        module_versions=dict(frozen.module_versions),
        backend_checkpoints=dict(backend_checkpoints)
        if backend_checkpoints is not None
        else {},
        trace_ref=trace_ref,
        created_wall_time=created_wall_time,
    )


def dump_persistence_snapshot(envelope: PersistenceSnapshot) -> str:
    """信封 → JSON 文本（D6 确定性；冻结序列化面唯一出口）。

    实现面：先经 ``to_dict()`` 断言 JSON-clean，再经 ``dump_json(envelope)``
    产出确定性文本（``model_dump`` 字段序冻结 → 同信封双跑字节相等）。
    """
    assert_json_clean(envelope.to_dict())
    return dump_json(envelope)


def load_persistence_snapshot(payload: str | bytes) -> PersistenceSnapshot:
    """JSON 文本（str 或 UTF-8 bytes）→ 信封（唯一合法入口；fail-loud 四道门）。

    门序（P8-INV-10：load = P8 信封层门 + 冻结 ``check_snapshot_versions``
    交叉校验）：

    1. JSON 词法层：``json.loads`` 失败 → ``corrupt_file``；
    2. 契约结构层：pydantic ``ValidationError`` → ``schema_invalid``
       （``extra="forbid"`` / 类型不符 / 缺失必填）；
    3. P8 层版本门：``persistence_format_version`` != 当前世代 →
       ``version_mismatch``；
    4. 嵌套交叉校验：``check_snapshot_versions`` 非空 → ``version_mismatch``
       （A2 篡改面：嵌套 ``contract_schema_version`` 篡改等）。
    """
    try:
        envelope = load_json(PersistenceSnapshot, payload)
    except ValidationError as exc:
        raise PersistenceError("schema_invalid", f"信封结构校验失败：{exc}") from exc
    except ValueError as exc:
        # json.JSONDecodeError 为 ValueError 子类
        raise PersistenceError("corrupt_file", f"信封 JSON 解析失败：{exc}") from exc
    if envelope.persistence_format_version != PERSISTENCE_FORMAT_VERSION:
        raise PersistenceError(
            "version_mismatch",
            f"persistence_format_version={envelope.persistence_format_version} "
            f"!= 当前 {PERSISTENCE_FORMAT_VERSION}",
        )
    issues = check_snapshot_versions(envelope.snapshot)
    if issues:
        raise PersistenceError("version_mismatch", "；".join(issues))
    return envelope


def check_persistence_versions(envelope: PersistenceSnapshot) -> tuple[str, ...]:
    """三层版本一致性报告面（P8-INV-10；空元组 = 一致；纯函数只报不处置）。

    报告序：

    1. 冻结 ``check_snapshot_versions(envelope.snapshot)`` 完整输出（core 层：
       ``SNAPSHOT_FORMAT_VERSION`` / ``CONTRACT_SCHEMA_VERSION`` 四字段）；
    2. P8 层：``persistence_format_version`` != 当前世代；
    3. P8 层：顶层冗余镜像（``project_version`` / ``module_versions``）与
       嵌套值失配。

    处置面（抛异常门）在 :func:`load_persistence_snapshot`；本函数供
    inspect / trace_query 等只读面消费。
    """
    issues: list[str] = list(check_snapshot_versions(envelope.snapshot))
    if envelope.persistence_format_version != PERSISTENCE_FORMAT_VERSION:
        issues.append(
            f"信封版本不匹配：persistence_format_version="
            f"{envelope.persistence_format_version} != 当前 {PERSISTENCE_FORMAT_VERSION}"
        )
    if envelope.project_version != envelope.snapshot.project_version:
        issues.append(
            "冗余镜像失配：project_version="
            f"{envelope.project_version!r} != 嵌套 {envelope.snapshot.project_version!r}"
        )
    if envelope.module_versions != envelope.snapshot.module_versions:
        issues.append(
            "冗余镜像失配：module_versions="
            f"{envelope.module_versions!r} != 嵌套 {envelope.snapshot.module_versions!r}"
        )
    return tuple(issues)
