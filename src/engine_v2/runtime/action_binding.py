"""Action/executor binding + action-side producer grants（Runtime Closure T6）。

冻结 API 面（contract §3/§4 T6 卡，签名逐字）：

    bind_actions(ir, spaces, *, domain_id="world", bundle=None)
        -> ActionBindingResult(action_registry / executors / producer_grants /
        diagnostics)

绑定语义（三个面，确定性顺序，全部输出经返回值，零副作用）：

1. **标准动作面**——复用 P9 冻结生产 API
   :func:`src.engine_v2.modules.actions.register_standard_actions`
   （幂等；执行器缺席 → spec ``tags`` 打 ``"p9.executor-missing"`` 标记，
   诊断不静默）。``executors`` 映射只绑 ``move`` =
   :class:`src.engine_v2.modules.actions.MoveExecutor`
   （构造面 ``MoveExecutor(space, domain)``，modules/actions.py:136 参数
   序）；talk / inspect / pickup / drop / wait 保留声明不绑执行器对象
   （执行面 ``executor_not_bound`` 诊断 = T2 职责，本轮零实现五个动作）。
2. **项目声明动作**——``ir.actions``（P5 content 侧 ``ActionSpec``：
   id/name/verb/requires_components/condition/success_probability/
   description）→ core 侧 ``ActionSpec``：

   - ``action_id`` = ``ActionTypeId(spec.id)``；
   - ``executor`` = ``"llmsim-project-actions.<id>"``（名字型，与 P9
     ``"llmsim-standard-actions.<id>"`` 同惯例）；
   - ``parameters`` = {}（content 侧无参数 schema = 开放 arguments，
     assumption 披露：运行时校验面 = executor 自持）；
   - ``duration_policy`` = ``DurationPolicy(kind="none")``（事件驱动）；
   - ``interruptible`` = True；``completion_trigger`` = None；
   - ``tags`` = ``["project", spec.verb]``。

   重 id（registry 已有键：标准面已注册，或前序 project 声明）→ error
   诊断 + 跳过（registry 键唯一，不静默覆盖）。**注册顺序 = 标准面先、
   project 面后**：若 project 先行，``register_standard_actions`` 的幂等
   覆盖语义会把同 id project 声明静默顶替为 standard spec（违「显式不
   静默」纪律）——标准先行则同 id 命中重 id 规则，error 显式落诊断。
3. **extension executors**——``bundle.action_executors`` 合并入
   ``executors`` 映射；id 与 standard/project 已绑 id 冲突 → extension
   覆盖 + warning 诊断（显式不静默）。

``producer_grants``（T6 不构造 AuthorityPolicy；合并归 T9）：

- ``bundle.producer_grants`` 透传，逐条验证 ``producer_id`` 词法
  （:data:`src.engine_v2.core.ids.PRODUCER_ID_PATTERN` fullmatch）：
  违例 → error 诊断 + 丢弃该条；
- **MoveExecutor 自产 grant**：``ProducerGrant(producer_id="actions.move",
  component_types=("spaces",), priority=50)``——producer =
  ``MoveExecutor.execute`` 成功面 effect 的 ``source`` 值（modules/
  actions.py ``_MOVE_PRODUCER = ProducerId("actions.move")``，L98 逐字）；
  组件类型名 = spaces 组件的实际 ``ComponentTypeId`` 名（core/space.py:447
  ``SPACES_COMPONENT = ComponentTypeId("spaces")``，运行期经 ``str()`` 取，
  防硬编码漂移）。

Import 纪律（contract §0/§3）：``runtime/extensions``（T3 并行开发中）
**零顶层 import**——注解经 ``from __future__ import annotations`` 字符串
化 + ``TYPE_CHECKING`` 引用；``ProducerGrant`` 构造经函数内 lazy import，
T3 模块缺席窗口以结构等价替代 :data:`_FallbackProducerGrant` 兜底（字段
形状 contract §3 逐字）；``bundle`` 消费为结构化 duck 检查
（``getattr``/``hasattr``，测试侧可传 stub 对象）。Diagnostic = P5
:class:`src.engine_v2.content.schemas.Diagnostic`（18 码闭集）；本模块选
码面：重 id = ``LLMSIM_DUPLICATE_ID`` / grant 词法违例 = ``LLMSIM_SCHEMA`` /
extension 覆盖 = ``LLMSIM_MODULE_CONFLICT``。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from src.engine_v2.content.schemas import (
    Diagnostic,
    DiagnosticSeverity,
    ProjectIR,
)
from src.engine_v2.core.action_registry import (
    ActionRegistry,
    ActionSpec,
    DurationPolicy,
)
from src.engine_v2.core.actions import ActionTypeId
from src.engine_v2.core.ids import PRODUCER_ID_PATTERN
from src.engine_v2.core.space import SPACES_COMPONENT, SpaceRegistry
from src.engine_v2.modules.actions import (
    ActionExecutor,
    MoveExecutor,
    register_standard_actions,
)

if TYPE_CHECKING:  # 仅类型引用（PEP 563 字符串化；零运行时 import）
    from src.engine_v2.runtime.extensions import ExtensionBundle, ProducerGrant

__all__ = ["ActionBindingResult", "bind_actions"]

#: MoveExecutor 成功面 effect ``source``（modules/actions.py:98 ``_MOVE_PRODUCER``
#: 逐字；producer 名字型词法合法 = PRODUCER_ID_PATTERN fullmatch 通过）。
_MOVE_PRODUCER_ID: Final[str] = "actions.move"

#: move grant 覆盖组件类型 = spaces 组件实际 ComponentTypeId 名（core/
#: space.py:447；运行期 ``str()`` 取值，不硬编码字面量）。
_MOVE_GRANT_COMPONENT_TYPES: Final[tuple[str, ...]] = (str(SPACES_COMPONENT),)

#: 标准 grant 缺省优先级（contract §3 ``ProducerGrant.priority`` 缺省值）。
_DEFAULT_GRANT_PRIORITY: Final[int] = 50


@dataclass(frozen=True)
class _FallbackProducerGrant:
    """``runtime.extensions.ProducerGrant`` 的结构等价替代（T3 缺席窗口）。

    字段形状 = contract §3 逐字（``producer_id`` / ``component_types`` /
    ``priority=50``）。仅当 :func:`_producer_grant_cls` 的 lazy import 落
    ``ImportError``（T3 模块未就位）时使用；T3 就位后 ``bind_actions``
    一律返回真 ``ProducerGrant`` 实例，本类不进入生产路径。
    """

    producer_id: str
    component_types: tuple[str, ...]
    priority: int = 50


def _producer_grant_cls() -> type:
    """解析 ProducerGrant 类（lazy import + 结构等价兜底）。

    T3（``runtime/extensions.py``）并行开发中：本模块零顶层 import。import
    成功 → 返回真类；``ImportError``（模块缺席）→ 返回
    :data:`_FallbackProducerGrant`（contract §3 形状逐字，T9 合并面对
    duck 对象同构可消费）。
    """
    try:
        from src.engine_v2.runtime.extensions import ProducerGrant
    except ImportError:
        return _FallbackProducerGrant
    return ProducerGrant


@dataclass(frozen=True)
class ActionBindingResult:
    """Action/executor 绑定结果（contract §3 T6 面；grant 合并归 T9）。

    - ``action_registry``：标准面（P9 ``register_standard_actions``）+
      项目声明 ``ActionSpec``（重 id 跳过，键唯一）；
    - ``executors``：action id → 执行器对象（本轮绑 ``move`` + extension
      供给；talk / inspect / pickup / drop / wait 刻意不绑 = 执行面
      ``executor_not_bound`` 诊断，T2 职责）；
    - ``producer_grants``：bundle 透传（词法验证后）+ MoveExecutor 自产
      grant；T9 合并入 ProducerRegistry / AuthorityPolicy；
    - ``diagnostics``：P5 :class:`Diagnostic`（18 码闭集，选码面见模块
      docstring）。
    """

    action_registry: ActionRegistry
    executors: dict[str, ActionExecutor]
    producer_grants: tuple[ProducerGrant, ...]
    diagnostics: tuple[Diagnostic, ...]


def bind_actions(
    ir: ProjectIR,
    spaces: SpaceRegistry,
    *,
    domain_id: str = "world",
    bundle: ExtensionBundle | None = None,
) -> ActionBindingResult:
    """绑定动作面 + 执行器对象 + action-side producer grants。

    语义 = 模块 docstring 三面 + grants 两条；关键不变量：

    - 确定性顺序：标准面 → project 面 → extension executors → grants；
      零随机 / 零墙钟 / 零推理消费（K5）；
    - registry 键唯一：project 重 id → error 诊断 + 跳过，不静默覆盖；
    - extension executor 冲突 → 覆盖 + warning 诊断（显式不静默）；
    - grant ``producer_id`` 词法违例 → error 诊断 + 丢弃该条；
    - 零副作用：``ir`` / ``spaces`` / ``bundle`` 只读，全部输出经返回值
      （K2 口径——本函数不写任何世界/注册表全局态；registry 实例为本
      函数新建）。
    """
    diagnostics: list[Diagnostic] = []
    registry = ActionRegistry()
    executors: dict[str, ActionExecutor] = {
        "move": MoveExecutor(spaces, domain_id),
    }

    # —— 1. 标准动作面（P9 冻结生产 API；幂等；缺席执行器打 p9 标记）——
    register_standard_actions(registry, spaces, executors)

    # —— 2. 项目声明动作（重 id = error + 跳过；registry 键唯一）——
    for spec in ir.actions:
        typed_id = ActionTypeId(spec.id)
        if typed_id in registry.specs:
            diagnostics.append(
                Diagnostic(
                    code="LLMSIM_DUPLICATE_ID",
                    severity=DiagnosticSeverity.ERROR,
                    path=spec.id,
                    message=(
                        f"project action id {spec.id!r} 已在 registry"
                        f"（standard 面或前序 project 声明），跳过"
                    ),
                )
            )
            continue
        registry.specs[typed_id] = ActionSpec(
            action_id=typed_id,
            executor=f"llmsim-project-actions.{spec.id}",
            parameters={},
            duration_policy=DurationPolicy(kind="none"),
            interruptible=True,
            completion_trigger=None,
            tags=["project", spec.verb],
        )

    # —— 3. extension executors（duck 检查；冲突 = 覆盖 + warning）——
    bundle_executors = (
        getattr(bundle, "action_executors", None) if bundle is not None else None
    )
    if bundle_executors:
        for action_id, executor in bundle_executors.items():
            if action_id in executors:
                diagnostics.append(
                    Diagnostic(
                        code="LLMSIM_MODULE_CONFLICT",
                        severity=DiagnosticSeverity.WARNING,
                        path=str(action_id),
                        message=(
                            f"extension executor {str(action_id)!r} 覆盖已有"
                            f"执行器绑定（standard/project），显式不静默"
                        ),
                    )
                )
            executors[action_id] = executor

    # —— 4. producer grants（bundle 透传 + 词法验证；MoveExecutor 自产）——
    grant_cls = _producer_grant_cls()
    grants: list[Any] = []
    bundle_grants = (
        getattr(bundle, "producer_grants", None) if bundle is not None else None
    )
    for grant in bundle_grants or ():
        producer_id = getattr(grant, "producer_id", None)
        if not isinstance(producer_id, str) or not PRODUCER_ID_PATTERN.fullmatch(
            producer_id
        ):
            diagnostics.append(
                Diagnostic(
                    code="LLMSIM_SCHEMA",
                    severity=DiagnosticSeverity.ERROR,
                    path=producer_id if isinstance(producer_id, str) and producer_id else "<invalid>",
                    message=(
                        f"producer grant producer_id 词法违例（须 fullmatch"
                        f" PRODUCER_ID_PATTERN）：{producer_id!r}，丢弃"
                    ),
                )
            )
            continue
        if isinstance(grant, grant_cls):
            grants.append(grant)  # 已为解析类实例 → 原样透传
        else:  # duck 对象 → 归一为解析类形状（字段 contract §3）
            grants.append(
                grant_cls(
                    producer_id=producer_id,
                    component_types=tuple(getattr(grant, "component_types", ()) or ()),
                    priority=getattr(grant, "priority", _DEFAULT_GRANT_PRIORITY),
                )
            )
    grants.append(
        grant_cls(
            producer_id=_MOVE_PRODUCER_ID,
            component_types=_MOVE_GRANT_COMPONENT_TYPES,
            priority=_DEFAULT_GRANT_PRIORITY,
        )
    )

    return ActionBindingResult(
        action_registry=registry,
        executors=executors,
        producer_grants=tuple(grants),
        diagnostics=tuple(diagnostics),
    )
