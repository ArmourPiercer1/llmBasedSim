"""P8 T04：backend checkpoint 注册 / 恢复（零 IO）。

本模块是 ``src.engine_v2.persistence`` 包 checkpoint 面（P8 T04，SOT
§3.5）：维护 dynamics backend 三声明（``checkpointable`` / ``restorable`` /
``replayable``，镜像 ``dynamics/backend.py`` ``BackendMetadata``）与实例
绑定；``checkpoint_all`` 按注册序统一采集 checkpoint 体（确定性）；
``restore`` 委派实例自有 ``restore``（toy 模式：返回**新实例**）；
``validate_refs`` 交叉核对信封 ``BackendStateRef`` 面与注册面（报告面，
不抛——声明漂移显式可见）。

导出（§8.2 账目 3 名）：

- :class:`CheckpointError` —— T04 错误族（``PersistenceError`` 子类；默认
  码 ``checkpoint_unavailable``；D7 fail-loud 单错误族）；
- :class:`CheckpointSnapshot` —— checkpoint 快照载体（frozen dataclass；
  non-checkpointable → ``checkpoint=None``，**降级可见**——非静默丢弃；
  ``to_dict`` JSON-clean，D3）；
- :class:`BackendCheckpointRegistry` —— 注册表（零 IO——checkpoint 体进出
  = 调用方 / filesystem 面，D4；零模块状态，D6）。

纪律：零 IO（D4）；零时钟 / 零随机（D5/D6）；文档面不出现推理侧 12 名
独立词（D2）。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from src.engine_v2.core import BackendStateRef, assert_json_clean
from src.engine_v2.dynamics.backend import BackendMetadata
from src.engine_v2.persistence.base import PersistenceError

__all__ = ("CheckpointError", "CheckpointSnapshot", "BackendCheckpointRegistry")


class CheckpointError(PersistenceError):
    """T04 checkpoint 错误族（``PersistenceError`` 子类；D7 fail-loud）。

    默认码 ``checkpoint_unavailable``（SOT §3.5）；``code=`` 可显式指定 P8
    错误码闭集另一成员（``schema_invalid``——声明/能力不符或体形态坏；
    ``version_mismatch``——实例侧版本门失败）。
    """

    def __init__(self, message: str, *, code: str = "checkpoint_unavailable") -> None:
        super().__init__(code, message)


@dataclass(frozen=True)
class CheckpointSnapshot:
    """checkpoint 快照载体（frozen dataclass；D3 JSON-clean 面）。

    - ``backend_id``：注册键（host 给出，K7 零生成）；
    - ``checkpointable`` / ``restorable`` / ``replayable``：镜像注册
      ``BackendMetadata`` 三声明；
    - ``checkpoint``：checkpoint 体（non-checkpointable → ``None``——降级
      可见，``to_dict`` 面可辨，非静默丢弃）。
    """

    backend_id: str
    checkpointable: bool
    restorable: bool
    replayable: bool
    checkpoint: Mapping[str, object] | None

    def to_dict(self) -> dict[str, object]:
        """JSON-clean 全量面（D3）：三声明 + checkpoint 体（None 可辨）。"""
        result: dict[str, object] = {
            "backend_id": self.backend_id,
            "checkpointable": self.checkpointable,
            "restorable": self.restorable,
            "replayable": self.replayable,
            "checkpoint": dict(self.checkpoint) if self.checkpoint is not None else None,
        }
        assert_json_clean(result)
        return result


class BackendCheckpointRegistry:
    """backend checkpoint 注册表（零 IO——SOT §3.5）。

    绑定面 ``backend_id → (metadata, instance)``；全部操作确定性（注册序
    = ``checkpoint_all`` 快照序，D6）。checkpoint 体进出本注册表 = 调用方 /
    filesystem 面（D4：本模块零 IO）。
    """

    def __init__(self) -> None:
        self._backends: dict[str, tuple[BackendMetadata, object]] = {}

    def register(
        self,
        *,
        backend_id: str,
        metadata: BackendMetadata,
        instance: object,
    ) -> None:
        """绑定 ``backend_id → (metadata, instance)``。

        失败面（D7 fail-loud）：

        - 重复 id → ``CheckpointError``（默认码 ``checkpoint_unavailable``）；
        - 一致性门（声明/能力不符，显式）：``metadata.checkpointable ==
          True`` 而 instance 无可调用 ``checkpoint`` →
          ``CheckpointError(schema_invalid)``；``metadata.restorable == True``
          而 instance 无可调用 ``restore`` → 同。
        """
        if backend_id in self._backends:
            raise CheckpointError(f"backend {backend_id!r} 已注册（重复 id）")
        if metadata.checkpointable and not callable(getattr(instance, "checkpoint", None)):
            raise CheckpointError(
                code="schema_invalid",
                message=(
                    f"backend {backend_id!r} 声明 checkpointable=True，"
                    f"但 instance 无可调用 checkpoint()"
                ),
            )
        if metadata.restorable and not callable(getattr(instance, "restore", None)):
            raise CheckpointError(
                code="schema_invalid",
                message=(
                    f"backend {backend_id!r} 声明 restorable=True，"
                    f"但 instance 无可调用 restore()"
                ),
            )
        self._backends[backend_id] = (metadata, instance)

    def checkpoint_all(self) -> tuple[CheckpointSnapshot, ...]:
        """按注册序采集全部 backend 的 checkpoint 快照（确定性，D6）。

        - checkpointable → ``instance.checkpoint()``（返回值必须 dict 且
          JSON-clean——``assert_json_clean``；非 dict →
          ``CheckpointError(schema_invalid)``）；
        - non-checkpointable → ``checkpoint=None``（降级可见）。
        """
        snapshots: list[CheckpointSnapshot] = []
        for backend_id, (metadata, instance) in self._backends.items():
            if metadata.checkpointable:
                payload = instance.checkpoint()
                if not isinstance(payload, dict):
                    raise CheckpointError(
                        code="schema_invalid",
                        message=(
                            f"backend {backend_id!r} checkpoint() 返回非 dict："
                            f"{type(payload).__name__}"
                        ),
                    )
                assert_json_clean(payload)
                checkpoint: Mapping[str, object] | None = payload
            else:
                checkpoint = None
            snapshots.append(
                CheckpointSnapshot(
                    backend_id=backend_id,
                    checkpointable=metadata.checkpointable,
                    restorable=metadata.restorable,
                    replayable=metadata.replayable,
                    checkpoint=checkpoint,
                )
            )
        return tuple(snapshots)

    def restore(self, *, backend_id: str, checkpoint: Mapping[str, object]) -> object:
        """委派 ``instance.restore(checkpoint)``，返回实例侧新实例（toy
        模式，``dynamics/toy_rigid.py``；版本门在实例侧）。

        失败面（D7 fail-loud）：

        - 未知 id 或注册项声明 ``restorable == False`` →
          ``CheckpointError``（默认码 ``checkpoint_unavailable``）；
        - 实例侧异常 wrap ``CheckpointError``：版本类 →
          ``version_mismatch``，形态类 → ``schema_invalid``（判定面：实例
          异常文本含 ``version`` 词（casefold）= 版本门失败，其余 = 形态
          坏）；实例侧已抛 ``PersistenceError`` → 原样上抛（错误族单基类，
          D-P8-11）。
        """
        try:
            metadata, instance = self._backends[backend_id]
        except KeyError:
            raise CheckpointError(f"backend {backend_id!r} 未注册") from None
        if not metadata.restorable:
            raise CheckpointError(
                f"backend {backend_id!r} 声明 restorable=False（不可恢复）"
            )
        try:
            return instance.restore(checkpoint)
        except PersistenceError:
            raise
        except Exception as exc:
            # 实例侧异常族开放（D-P7 家族 DynamicsError 等），wrap 收口单错误族
            message = str(exc)
            code = "version_mismatch" if "version" in message.casefold() else "schema_invalid"
            raise CheckpointError(
                code=code,
                message=f"backend {backend_id!r} restore 失败：{message}",
            ) from exc

    def validate_refs(self, backend_refs: Sequence[BackendStateRef]) -> tuple[str, ...]:
        """交叉核对信封 ``backend_refs`` 面与注册面（报告面，不抛，SOT
        §3.5）。

        空 issues = 一致；issue 串闭集：

        - ref 的 ``backend_id`` 未注册 → issue 串（ref 悬空）；
        - ref ``checkpointable=True`` 而注册项 non-checkpointable → issue
          串（声明漂移显式）。
        """
        issues: list[str] = []
        for ref in backend_refs:
            entry = self._backends.get(ref.backend_id)
            if entry is None:
                issues.append(f"backend {ref.backend_id!r} ref 存在但未注册")
                continue
            metadata, _ = entry
            if ref.checkpointable and not metadata.checkpointable:
                issues.append(
                    f"backend {ref.backend_id!r} ref 声明 checkpointable=True，"
                    f"但注册项 non-checkpointable（声明漂移）"
                )
        return tuple(issues)
