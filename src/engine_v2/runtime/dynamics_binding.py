"""Runtime Closure T7 — dynamics binding + dynamics-side grants（contract §3/§4）。

接线面（计划 T7「只接」）：

    IR rules + ExtensionBundle.dynamics_backends
    → runtime dynamics 元组 + producer grants + diagnostics

语义（Leader 已裁决，逐字执行）：

- **project rules 路径**：content 侧 ``RuleSpec``（id / description / match /
  condition DSL 串 / feasibility / probability / priority / disabled）与
  dynamics 侧 ``WorldRule``（rule_id / when 结构化操作子 map /
  emit_effect_type / emit_target_entity / emit_component_type /
  emit_field_path / emit_payload）形状异构、**不可直接投影**（Leader 已核验）
  → 每条 ``ir.rules`` 一条诊断 + 跳过（Leader 勘误定码：code =
  ``LLMSIM_SCHEMA``、severity=warning、message 显式说明 shape mismatch、
  refs=(rule.id, "world_rule")）；**禁止解析 DSL**（parse_dsl 归 validator
  面）；``RuleDynamics`` 本轮不产出；IR 无 rules = 零诊断零 backend；
- **extension dynamics**：``bundle.dynamics_backends`` 原样透传（tuple 保序
  = bundle 声明序 = 输出序）；``bundle`` 经 ``hasattr(bundle,
  "dynamics_backends")`` 鸭子检查（T3 模块并行开发中，零顶层运行时 import）；
  畸形形状（缺属性 / 非 tuple = entrypoint 产物错型）= 显式 error 诊断 +
  跳过（不静默）；
- **grant 自动派生**（contract §3：dynamics grant SHOULD 从 metadata 派生）：
  对最终 dynamics 元组中每个 backend 调 ``backend.metadata()`` →
  ``ProducerGrant(producer_id=meta.producer_id, component_types=meta.domains,
  priority=50)``；``metadata()`` 抛异常（实现缺陷）→ error 诊断 + **该
  backend 保留在 dynamics**（simulate 面仍会暴露）但无 grant
  （closed-by-default 会拒其 effect——显式诊断说明）。

诊断载体（Leader 勘误）：**复用 P5 ``content.schemas.Diagnostic``**（18 码
闭集 ``DIAGNOSTIC_CODES``，构造期 ``model_validator`` 强制——不可新增码）。
本模块用码（闭集成员）：

- 规则不可投影 / ``metadata()`` 失败 → ``LLMSIM_SCHEMA``（形状/契约违规面；
  前者 severity=warning（Leader 勘误钉死），后者 severity=error）；
- bundle 畸形（entrypoint 产物错型，同 T3 gate"entrypoint 错型 → 明确
  诊断"口径）→ ``LLMSIM_PLUGIN_ENTRY_INVALID``（severity=error）。

并行 import 策略（镜像 Leader-owned ``runtime/world_instance.py`` 的
TYPE_CHECKING 纪律——"零运行时依赖，并行模块就位前可 import"）：

- ``ExtensionBundle`` / ``ProducerGrant`` 规范宿主 =
  ``runtime/extensions.py``（T3，并行开发中）：仅 TYPE_CHECKING 类型引用，
  零顶层运行时 import；
- ``ProducerGrant`` 构造 = 调用时懒 import T3 规范类；T3 未就位时回落本文件
  同构孪生（形状按 contract §3 逐字冻结）——任一进程内至多存在一个 grant
  载体类，规避装配后 isinstance / 相等性分裂。

纪律：K2 零 WorldState 写（binding 只产纯数据）；零 DSL 解析；零 metadata
二次校验（``metadata()`` 输出受信任，词表校验归 P7 构造期）；K7 零 asyncio /
零 random / 零墙钟 / 零模块级可变状态；src 零 ``import tests``。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from src.engine_v2.content.schemas import (
    Diagnostic,
    DiagnosticSeverity,
    ProjectIR,
)
from src.engine_v2.dynamics.backend import WorldDynamicsBackend

if TYPE_CHECKING:  # 并行模块（T3）——仅类型引用，零运行时依赖
    from src.engine_v2.runtime.extensions import ExtensionBundle, ProducerGrant

__all__ = ["DynamicsBindingResult", "bind_dynamics"]

# —— 本模块诊断码（P5 18 码闭集成员；闭集外码构造期即 ValidationError）——

#: 形状/契约违规码（规则不可投影 warning / metadata() 失败 error 共用）。
_CODE_SCHEMA: Final[str] = "LLMSIM_SCHEMA"

#: entrypoint 产物错型码（bundle 畸形 error）。
_CODE_PLUGIN_ENTRY_INVALID: Final[str] = "LLMSIM_PLUGIN_ENTRY_INVALID"

#: 自动派生 grant 的缺省 priority（contract §3 ``ProducerGrant`` 缺省值；
#: 计划 T7 卡逐字钉死 ``priority=50``）。
_DERIVED_GRANT_PRIORITY: Final[int] = 50


@dataclass(frozen=True)
class _ProducerGrantTwin:
    """并行开发回落孪生：contract §3 ``ProducerGrant`` 形状逐字冻结。

    仅当 ``runtime/extensions.py``（T3，规范宿主）未就位或不可 import 时由
    :func:`_producer_grant_class` 回落使用；字段集与缺省值与规范类逐字一致
    （frozen dataclass，构造期零校验——词法校验归 T3 规范面）。
    """

    producer_id: str
    component_types: tuple[str, ...]
    priority: int = _DERIVED_GRANT_PRIORITY


def _producer_grant_class() -> type:
    """解析 ``ProducerGrant`` 载体类：优先 T3 规范 import，未就位时回落孪生。

    懒 import（函数内，非顶层）：T3 模块就位前本模块可 import、可调用；
    T3 就位后所有构造走规范类（进程内单一载体类）。仅捕获
    :class:`ImportError`（模块缺失 / 名字缺失 = 并行开发中间态）；T3 模块
    自身语法错误等硬故障不吞——全仓回归面会显式暴露。
    """
    try:
        from src.engine_v2.runtime.extensions import ProducerGrant
    except ImportError:
        return _ProducerGrantTwin
    return ProducerGrant


@dataclass(frozen=True)
class DynamicsBindingResult:
    """T7 binding 输出（contract 冻结形状）。

    - ``dynamics``：最终 dynamics 元组 = extension backends 按 bundle 声明序
      原样透传（``RuleDynamics`` 本轮不产出）；``metadata()`` 失败的 backend
      **保留**在元组内（simulate 面仍会暴露，仅无 grant）；
    - ``producer_grants``：自动派生 grants（与 ``dynamics`` 同源同序；
      ``metadata()`` 失败者缺席）；
    - ``diagnostics``：P5 ``content.schemas.Diagnostic``（18 码闭集）——
      规则路径 warning（IR 序）+ bundle 畸形 error + metadata 失败 error
      （dynamics 序）。
    """

    dynamics: tuple[WorldDynamicsBackend, ...]
    producer_grants: tuple[ProducerGrant, ...]
    diagnostics: tuple[Diagnostic, ...]


def _rule_not_projectable(rule_id: str) -> Diagnostic:
    """单条 P5 规则的不可投影诊断（Leader 勘误定码定形，确定性文本）。

    code = ``LLMSIM_SCHEMA``（18 码闭集成员；P5 gameplay DSL 规则与 P7
    声明式 WorldRule 形状异构 = 形状面违规）；severity=warning；path =
    规则 id（P5 Diagnostic path 口径"实体/规则 ID"）；refs =
    ``(rule.id, "world_rule")``。
    """
    return Diagnostic(
        code=_CODE_SCHEMA,
        severity=DiagnosticSeverity.WARNING,
        path=rule_id,
        message=(
            "P5 gameplay DSL rule 不可投影为 P7 WorldRule（shape mismatch）；"
            "本 binding 不解析 DSL，该规则跳过；承接面 = 后续显式规则翻译器。"
        ),
        refs=(rule_id, "world_rule"),
    )


def bind_dynamics(
    ir: ProjectIR, *, bundle: ExtensionBundle | None = None
) -> DynamicsBindingResult:
    """dynamics binding + dynamics-side grants（计划 T7 卡"只接"面）。

    纯数据函数于输入（K2 零世界写）；确定性：同输入双跑 → 输出相等（K7 零
    墙钟 / 零随机）。步骤（诊断序 = 规则 warning → bundle 畸形 → metadata
    失败）：

    1. **project rules 路径**：逐条 ``ir.rules``（IR 序）产
       ``LLMSIM_SCHEMA`` warning（Leader 勘误定码定形）+ 跳过——零 DSL
       解析、零 ``RuleDynamics`` 产出（形状异构裁决，见模块 docstring）；
    2. **extension dynamics**：``bundle is None`` → 无 backend；否则鸭子检查
       ``hasattr(bundle, "dynamics_backends")``，缺失或属性非 tuple →
       ``LLMSIM_PLUGIN_ENTRY_INVALID`` error + 跳过；合法 → 原样透传
       （声明序保序）；
    3. **grant 自动派生**：对最终 dynamics 元组逐 backend 调
       ``metadata()`` → ``ProducerGrant(producer_id=meta.producer_id,
       component_types=meta.domains, priority=50)``；调用抛任何异常
       （实现缺陷）→ ``LLMSIM_SCHEMA`` error + backend 保留、无 grant
       （closed-by-default 拒 effect，诊断内显式说明）。
    """
    diagnostics: list[Diagnostic] = []

    # 1) project rules：逐条 warning + 跳过（不读 condition 串——零 DSL 解析）
    for rule in ir.rules:
        diagnostics.append(_rule_not_projectable(rule.id))

    # 2) extension dynamics：鸭子检查 + 原样透传（tuple 保序）
    dynamics: list[WorldDynamicsBackend] = []
    if bundle is not None:
        if not hasattr(bundle, "dynamics_backends"):
            diagnostics.append(
                Diagnostic(
                    code=_CODE_PLUGIN_ENTRY_INVALID,
                    severity=DiagnosticSeverity.ERROR,
                    path="extension_bundle",
                    message=(
                        "ExtensionBundle 鸭子检查失败：实例缺 dynamics_backends "
                        "属性（contract §3）；extension dynamics 路径跳过。"
                    ),
                )
            )
        else:
            backends = bundle.dynamics_backends
            if not isinstance(backends, tuple):
                diagnostics.append(
                    Diagnostic(
                        code=_CODE_PLUGIN_ENTRY_INVALID,
                        severity=DiagnosticSeverity.ERROR,
                        path="extension_bundle",
                        message=(
                            "bundle.dynamics_backends 必须为 tuple"
                            "（contract §3），得到 "
                            f"{type(backends).__name__}；extension dynamics "
                            "路径跳过。"
                        ),
                    )
                )
            else:
                dynamics = list(backends)

    # 3) grant 自动派生（contract §3：SHOULD 从 metadata 派生）
    grant_cls = _producer_grant_class()
    grants: list[ProducerGrant] = []
    for index, backend in enumerate(dynamics):
        try:
            meta = backend.metadata()
        except Exception as exc:  # 实现缺陷：保留 backend，无 grant（不静默）
            diagnostics.append(
                Diagnostic(
                    code=_CODE_SCHEMA,
                    severity=DiagnosticSeverity.ERROR,
                    path=f"dynamics[{index}]",
                    message=(
                        f"backend {type(backend).__name__}（dynamics[{index}]）"
                        f"metadata() 调用抛 {type(exc).__name__}：{exc}；"
                        "该 backend 保留在 dynamics（simulate 面仍会暴露），"
                        "但未自动派生 producer grant——closed-by-default 权限"
                        "面会拒其 effect。"
                    ),
                    refs=(type(backend).__name__,),
                )
            )
            continue
        grants.append(
            grant_cls(
                producer_id=meta.producer_id,
                component_types=meta.domains,
                priority=_DERIVED_GRANT_PRIORITY,
            )
        )

    return DynamicsBindingResult(
        dynamics=tuple(dynamics),
        producer_grants=tuple(grants),
        diagnostics=tuple(diagnostics),
    )
