"""P8 T06：devtools 开发干预面（DevelopmentCommand / 提交组装，零 IO）。

本模块是 ``src.engine_v2.devtools`` 包 intervention 面（P8 T06，SOT §3.7；
D-P8-07：P8 本地包裹而非 core 扩展——core 冻结面已备齐三重标记
``OriginKind.DEVELOPER`` + ``CauseKind.INTERVENTION`` +
``TraceKind.DEV_INTERVENTION``，P8 只做组装，零重定义）：

- :class:`DevelopmentCommand`——host 命令（``command_id`` host 给出；
  ``kind`` ∈ 6 种闭集；``payload`` ctor 时 ``assert_json_clean``）；
- :func:`to_intervention_effects`——世界变更型命令 → 冻结
  ``ProposedEffect`` 包裹（纯函数；``patch_state`` 映射到冻结结构效果
  ``core.set_world_variable`` / ``core.set_component``，不依赖测试侧语义
  handler）；
- :func:`apply_development_command`——devtools driver 自包含组装点（P7
  ``dynamics/host.py:86`` 模式同形）：合成 1 条 DEV_INTERVENTION trace
  记录 + 按 kind 分派——runtime 控制型只出 directive（devtools 不直写
  ``RuntimeState``）；实例级（``branch``）= T05 ``branch_world`` 的控制面
  标记；世界变更型经正常提交管道 ``CascadeExecutor.run``（K2 零旁路；
  K3 authority closed-by-default 天然适用）。

纪律：零 IO（D4）；零时钟 / 零随机（D5/D6——record_id 为 host 确定性
``trc_`` 字面量，K7 零 uuid4，D-P8-17）；零模块状态；文档面不出现推理侧
12 名独立词（D2）。
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from src.engine_v2.core import (
    CauseKind,
    CauseRef,
    CascadeExecutor,
    CascadeResult,
    ComponentTypeId,
    EFFECT_SET_COMPONENT,
    EFFECT_SET_WORLD_VARIABLE,
    EffectId,
    EffectTypeId,
    EntityId,
    EntityTarget,
    OriginKind,
    ProducerId,
    ProposedEffect,
    Provenance,
    Revision,
    StateDomainId,
    StateDomainTarget,
    TraceKind,
    TraceRecord,
    TraceRecordId,
    WorldState,
    assert_json_clean,
)
from src.engine_v2.persistence.base import PersistenceError

__all__ = (
    "DEVTOOLS_DEVELOPER_PRODUCER",
    "DEVELOPMENT_COMMAND_KINDS",
    "WORLD_MUTATING_KINDS",
    "RUNTIME_CONTROL_KINDS",
    "INSTANCE_LEVEL_KINDS",
    "DevelopmentCommand",
    "ExternalInterventionEffect",
    "InterventionResult",
    "InterventionError",
    "to_intervention_effects",
    "apply_development_command",
)

#: 干预 producer id（Spec §22；fullmatch 冻结 ``PRODUCER_ID_PATTERN``，
#: ``core/ids.py:77``；producer 注册 = host policy 面）。
DEVTOOLS_DEVELOPER_PRODUCER: Final[str] = "devtools.developer"

#: 开发命令 kind 6 种闭集（Spec §22 L1254–1259 逐字；P8-INV-5——"例如"非
#: 穷举 → 闭集 = P8 本地契约，D-P8-13；新增 kind = 波次决策）。
DEVELOPMENT_COMMAND_KINDS: Final[tuple[str, ...]] = (
    "pause",
    "step",
    "force_wake",
    "inject_event",
    "patch_state",
    "branch",
)

#: 世界变更型子集闭集：走正常提交管道（Spec §22 L1265–1267）。
WORLD_MUTATING_KINDS: Final[tuple[str, ...]] = ("inject_event", "patch_state")

#: runtime 控制型子集闭集：只出 runtime directive（§0.4.6：devtools 不直写
#: RuntimeState）。
RUNTIME_CONTROL_KINDS: Final[tuple[str, ...]] = ("pause", "step", "force_wake")

#: 实例级子集闭集：= T05 ``branch_world`` 的控制面标记（DEV-P8-3）。
INSTANCE_LEVEL_KINDS: Final[tuple[str, ...]] = ("branch",)

#: ``patch_state`` / ``inject_event`` payload 分支 key 闭集（SOT §3.7 逐字；
#: 缺 / 多 key → ``usage_error``）。
_PATCH_WORLD_VARIABLE_KEYS: Final[tuple[str, ...]] = ("target", "key", "value")
_PATCH_COMPONENT_KEYS: Final[tuple[str, ...]] = (
    "target",
    "entity_id",
    "key",
    "data",
)
_INJECT_ENTITY_KEYS: Final[tuple[str, ...]] = (
    "effect_id",
    "effect_type",
    "target_kind",
    "entity_id",
    "payload",
)
_INJECT_STATE_DOMAIN_KEYS: Final[tuple[str, ...]] = (
    "effect_id",
    "effect_type",
    "target_kind",
    "domain",
    "payload",
)

#: 前缀型 ID 正文词法（``core/ids.py:70`` 同形；record_id 门禁消费）。
_TRACE_RECORD_BODY: Final = re.compile(r"[a-z0-9_]+")


class InterventionError(PersistenceError):
    """T06 intervention 错误族（``PersistenceError`` 子类；D7 fail-loud；
    单错误族，D-P8-11）。

    默认码 ``intervention_rejected``（SOT §3.7）；``code=`` 可显式指定 P8
    错误码闭集另一成员（``schema_invalid``——payload / record_id 词法坏；
    ``usage_error``——kind / payload 闭集违规）。
    """

    def __init__(self, message: str, *, code: str = "intervention_rejected") -> None:
        super().__init__(code, message)


@dataclass(frozen=True)
class DevelopmentCommand:
    """host 开发命令（SOT §3.7；frozen dataclass）。

    ctor 校验（顺序 = 字段序）：

    - ``command_id``：host 给出；空串 / 纯空白 →
      ``InterventionError(schema_invalid)``；
    - ``kind``：∈ :data:`DEVELOPMENT_COMMAND_KINDS`，否则
      ``InterventionError(usage_error)``（A19 面）；
    - ``payload``：ctor 时 ``assert_json_clean``（非 JSON-clean →
      ``schema_invalid``）。
    """

    command_id: str
    kind: str
    payload: Mapping[str, object]

    def __post_init__(self) -> None:
        if not self.command_id.strip():
            raise InterventionError(
                code="schema_invalid",
                message="command_id 为空/纯空白（id 由 host 给出，须非空）",
            )
        if self.kind not in DEVELOPMENT_COMMAND_KINDS:
            raise InterventionError(
                code="usage_error",
                message=(
                    f"kind {self.kind!r} 不在开发命令 6 种闭集：{DEVELOPMENT_COMMAND_KINDS!r}"
                ),
            )
        try:
            assert_json_clean(dict(self.payload))
        except AssertionError as exc:
            raise InterventionError(
                code="schema_invalid",
                message=f"payload 非 JSON-clean：{exc}",
            ) from exc


@dataclass(frozen=True)
class ExternalInterventionEffect:
    """干预效果包裹（冻结 ``ProposedEffect`` 的 typed wrapper，D-P8-07）。

    - ``command_id``：宿主命令 id（因果锚点）；
    - ``effect``：冻结 ``ProposedEffect``（source = ``devtools.developer``；
      ``CauseRef(INTERVENTION)`` 因果引用）。
    """

    command_id: str
    effect: ProposedEffect

    def to_dict(self) -> dict[str, object]:
        """JSON-clean 全量面（D3）：命令 id + 效果（``model_dump``）。"""
        result: dict[str, object] = {
            "command_id": self.command_id,
            "effect": self.effect.model_dump(mode="json"),
        }
        assert_json_clean(result)
        return result


@dataclass(frozen=True)
class InterventionResult:
    """干预执行结果（SOT §3.7；frozen dataclass）。

    - ``world_state``：可能已变更（runtime 控制型 = 原状态同对象）；
    - ``changed``：世界是否变更（世界变更型 = True）；
    - ``runtime_directive``：如 ``("pause",)`` / ``("force_wake",
      "<entity_id>")``；世界变更型 = ``None``；
    - ``cascade_result``：非世界变更型 = ``None``；
    - ``trace_records``：含 1 条 ``DEV_INTERVENTION`` 记录 + 级联 trace。
    """

    world_state: WorldState
    changed: bool
    runtime_directive: tuple[str, ...] | None
    cascade_result: CascadeResult | None
    trace_records: tuple[TraceRecord, ...]

    def to_dict(self) -> dict[str, object]:
        """JSON-clean 全量面（D3）；``CascadeResult`` 无 ``to_dict``（冻结
        dataclass）→ 手工展开。"""
        result: dict[str, object] = {
            "world_state": self.world_state.model_dump(mode="json"),
            "changed": self.changed,
            "runtime_directive": (
                list(self.runtime_directive) if self.runtime_directive is not None else None
            ),
            "cascade_result": _cascade_result_to_dict(self.cascade_result),
            "trace_records": [
                record.model_dump(mode="json") for record in self.trace_records
            ],
        }
        assert_json_clean(result)
        return result


def _cascade_result_to_dict(cascade: CascadeResult | None) -> dict[str, object] | None:
    """``CascadeResult`` 手工展开（冻结 dataclass 无 ``to_dict``，D3）。"""
    if cascade is None:
        return None
    return {
        "final_state": cascade.final_state.model_dump(mode="json"),
        "transactions": [txn.model_dump(mode="json") for txn in cascade.transactions],
        "events": [event.model_dump(mode="json") for event in cascade.events],
        "trace_records": [
            record.model_dump(mode="json") for record in cascade.trace_records
        ],
        "deferred": [effect.model_dump(mode="json") for effect in cascade.deferred],
        "diagnostics": [
            {"kind": d.kind, "depth": d.depth, "detail": d.detail}
            for d in cascade.diagnostics
        ],
    }


def _check_record_id(intervention_record_id: str) -> None:
    """record_id 词法门禁（K7 零 uuid4：host 确定性 ``trc_`` 字面量）。

    空 / 非 ``trc_`` 前缀 / 正文空或非法（``[a-z0-9_]+``，
    ``core/ids.py:180–186`` 同族词法）→ ``schema_invalid``。
    """
    prefix = TraceRecordId.PREFIX
    if not intervention_record_id.startswith(prefix):
        raise InterventionError(
            code="schema_invalid",
            message=(
                f"intervention_record_id 词法非法（须 {prefix!r} 前缀）："
                f"{intervention_record_id!r}"
            ),
        )
    body = intervention_record_id[len(prefix):]
    if not _TRACE_RECORD_BODY.fullmatch(body):
        raise InterventionError(
            code="schema_invalid",
            message=(
                f"intervention_record_id 正文词法非法（须 [a-z0-9_]+）："
                f"{intervention_record_id!r}"
            ),
        )


def _closed_payload(command: DevelopmentCommand, expected: tuple[str, ...]) -> dict[str, object]:
    """payload 闭集 key 面核对（P8-INV-5）：key 集相等，否则 ``usage_error``。"""
    keys = set(command.payload)
    expected_set = set(expected)
    missing = sorted(expected_set - keys)
    extra = sorted(keys - expected_set)
    if missing or extra:
        raise InterventionError(
            code="usage_error",
            message=(
                f"{command.kind} payload key 集不符（闭集 {expected!r}）："
                f"missing={missing!r}, extra={extra!r}"
            ),
        )
    return dict(command.payload)


def _require_str(command: DevelopmentCommand, key: str, value: object) -> str:
    """payload 字段 str 词面核对（非 str → ``usage_error``）。"""
    if not isinstance(value, str):
        raise InterventionError(
            code="usage_error",
            message=(
                f"{command.kind} payload.{key} 须为 str，"
                f"得到 {type(value).__name__}"
            ),
        )
    return value


def _patch_effect_id(command_id: str) -> EffectId:
    """``patch_state`` 确定性 effect_id 派生（host 锚点 = ``command_id``）。

    payload 闭集无 effect_id 字段（SOT §3.7）→ P8 由 ``command_id`` 派生
    词法合法 ``EffectId``（正文词法 ``[a-z0-9_]+``，``core/ids.py:70`` 同
    形）：小写化 + 非字母数字/下划线 → 下划线。确定性（D6）；复用冻结
    ``EffectId`` 词法面，零新 id 概念。
    """
    body = "".join(
        ch if (ch.isascii() and (ch.isalnum() or ch == "_")) else "_"
        for ch in command_id.lower()
    )
    return EffectId(EffectId.PREFIX + body)


def _patch_state_effect(
    command: DevelopmentCommand,
    base_revision: Revision,
    intervention_record_id: str,
) -> ProposedEffect:
    """``patch_state`` → 冻结结构效果（``core/reducer.py:216–222`` 常量）。"""
    target = command.payload.get("target")
    cause = [CauseRef(kind=CauseKind.INTERVENTION, ref_id=intervention_record_id)]
    if target == "world_variable":
        data = _closed_payload(command, _PATCH_WORLD_VARIABLE_KEYS)
        key = _require_str(command, "key", data["key"])
        return ProposedEffect(
            effect_id=_patch_effect_id(command.command_id),
            effect_type=EFFECT_SET_WORLD_VARIABLE,
            source=ProducerId(DEVTOOLS_DEVELOPER_PRODUCER),
            target=StateDomainTarget(domain=StateDomainId("world_variables")),
            payload={"key": key, "value": data["value"]},
            base_revision=base_revision,
            cause_ids=cause,
        )
    if target == "component":
        data = _closed_payload(command, _PATCH_COMPONENT_KEYS)
        entity_id = _require_str(command, "entity_id", data["entity_id"])
        component_type = _require_str(command, "key", data["key"])
        component_data = data["data"]
        if not isinstance(component_data, Mapping):
            raise InterventionError(
                code="usage_error",
                message="patch_state payload.data 须为 Mapping（组件数据）",
            )
        return ProposedEffect(
            effect_id=_patch_effect_id(command.command_id),
            effect_type=EFFECT_SET_COMPONENT,
            source=ProducerId(DEVTOOLS_DEVELOPER_PRODUCER),
            target=EntityTarget(
                entity_id=EntityId(entity_id),
                component_type=ComponentTypeId(component_type),
            ),
            payload=dict(component_data),
            base_revision=base_revision,
            cause_ids=cause,
        )
    raise InterventionError(
        code="usage_error",
        message=(
            "patch_state payload.target 须为 'world_variable'/'component'，"
            f"得到 {target!r}"
        ),
    )


def _inject_event_effect(
    command: DevelopmentCommand,
    base_revision: Revision,
    intervention_record_id: str,
) -> ProposedEffect:
    """``inject_event`` → 通用 ``ProposedEffect`` 包裹（effect_type 原样——
    未注册语义型在正常管道 L1 即显式拒绝，P8 不特判）。"""
    target_kind = command.payload.get("target_kind")
    cause = [CauseRef(kind=CauseKind.INTERVENTION, ref_id=intervention_record_id)]
    if target_kind == "entity":
        data = _closed_payload(command, _INJECT_ENTITY_KEYS)
        entity_id = _require_str(command, "entity_id", data["entity_id"])
        target = EntityTarget(entity_id=EntityId(entity_id))
    elif target_kind == "state_domain":
        data = _closed_payload(command, _INJECT_STATE_DOMAIN_KEYS)
        domain = _require_str(command, "domain", data["domain"])
        target = StateDomainTarget(domain=StateDomainId(domain))
    else:
        raise InterventionError(
            code="usage_error",
            message=(
                "inject_event payload.target_kind 须为 'entity'/'state_domain'，"
                f"得到 {target_kind!r}"
            ),
        )
    inner_payload = data["payload"]
    if not isinstance(inner_payload, Mapping):
        raise InterventionError(
            code="usage_error",
            message="inject_event payload.payload 须为 Mapping（效果 payload）",
        )
    effect_id = _require_str(command, "effect_id", data["effect_id"])
    effect_type = _require_str(command, "effect_type", data["effect_type"])
    return ProposedEffect(
        effect_id=EffectId(effect_id),
        effect_type=EffectTypeId(effect_type),
        source=ProducerId(DEVTOOLS_DEVELOPER_PRODUCER),
        target=target,
        payload=dict(inner_payload),
        base_revision=base_revision,
        cause_ids=cause,
    )


def to_intervention_effects(
    command: DevelopmentCommand,
    *,
    base_revision: Revision,
    intervention_record_id: str,
) -> tuple[ExternalInterventionEffect, ...]:
    """世界变更型命令 → 冻结 ``ProposedEffect`` 包裹（纯函数）。

    - ``patch_state`` / ``inject_event``（:data:`WORLD_MUTATING_KINDS`）各
      产 1 效果；其他 3 kind → 空元组；
    - 统一面：``source = devtools.developer``；``base_revision`` = 参数；
      ``cause_ids = [CauseRef(INTERVENTION, intervention_record_id)]``
      （D-P8-17：ref_id = 该命令 DEV_INTERVENTION 记录 record_id）。
    """
    if command.kind not in WORLD_MUTATING_KINDS:
        return ()
    if command.kind == "patch_state":
        effect = _patch_state_effect(command, base_revision, intervention_record_id)
    else:
        effect = _inject_event_effect(command, base_revision, intervention_record_id)
    return (ExternalInterventionEffect(command.command_id, effect),)


def _runtime_control_directive(command: DevelopmentCommand) -> tuple[str, ...]:
    """runtime 控制型 directive（``force_wake`` 附 entity_id，缺 key →
    ``usage_error``）。"""
    if command.kind == "force_wake":
        entity_id = _require_str(command, "entity_id", command.payload.get("entity_id"))
        return ("force_wake", entity_id)
    return (command.kind,)


def apply_development_command(
    command: DevelopmentCommand,
    *,
    world_state: WorldState,
    executor: CascadeExecutor,
    logical_tick: int = 0,
    intervention_record_id: str,
) -> InterventionResult:
    """devtools driver 自包含组装点（SOT §3.7；P7 host 模式同形，D-P8-07）。

    步骤：

    1. record_id 词法（空 / 非 ``trc_`` → ``schema_invalid``）；
    2. 合成 1 条 ``DEV_INTERVENTION`` 记录（record_id host 给出，K7 零
       uuid4，D-P8-17；``world_revision`` = 干预时刻读数）；
    3. 分派：

       - :data:`RUNTIME_CONTROL_KINDS`：``changed=False``，只出
         ``runtime_directive``（devtools 不直写 RuntimeState），trace 仅
         dev 记录；
       - :data:`INSTANCE_LEVEL_KINDS`（``branch``）：``changed=False``，
         ``("branch",)`` 指令——实例级动作 = host 调 ``branch_world``
         （command_id 作为 causal 锚点，DEV-P8-3）；
       - :data:`WORLD_MUTATING_KINDS`：``to_intervention_effects`` →
         ``CascadeExecutor.run``（K2 零旁路）→ ``changed=True`` +
         ``cascade_result`` + 级联 trace。
    """
    _check_record_id(intervention_record_id)
    dev_record = TraceRecord(
        record_id=TraceRecordId(intervention_record_id),
        kind=TraceKind.DEV_INTERVENTION,
        world_revision=world_state.world_revision,
        logical_tick=logical_tick,
        producer_id=ProducerId(DEVTOOLS_DEVELOPER_PRODUCER),
        payload={
            "command": {
                "command_id": command.command_id,
                "kind": command.kind,
                "payload": dict(command.payload),
            }
        },
    )
    if command.kind in RUNTIME_CONTROL_KINDS:
        return InterventionResult(
            world_state=world_state,
            changed=False,
            runtime_directive=_runtime_control_directive(command),
            cascade_result=None,
            trace_records=(dev_record,),
        )
    if command.kind in INSTANCE_LEVEL_KINDS:
        return InterventionResult(
            world_state=world_state,
            changed=False,
            runtime_directive=(command.kind,),
            cascade_result=None,
            trace_records=(dev_record,),
        )
    effects = to_intervention_effects(
        command,
        base_revision=world_state.world_revision,
        intervention_record_id=intervention_record_id,
    )
    result = executor.run(
        tuple(effect.effect for effect in effects),
        world_state,
        causal_root_id=command.command_id,
        origin=Provenance(
            producer_id=ProducerId(DEVTOOLS_DEVELOPER_PRODUCER),
            origin=OriginKind.DEVELOPER,
        ),
    )
    return InterventionResult(
        world_state=result.final_state,
        changed=True,
        runtime_directive=None,
        cascade_result=result,
        trace_records=(dev_record, *result.trace_records),
    )
