"""engine_v2 runtime 层 T9：GameProject → EngineInstance 单入口（assembly）。

依据 ``docs/plans/runtime_closure_contract.md``（contract §0 纪律 / §1
WorldInstance 字段冻结 / §4 T9 卡；计划 T9 卡逐字面）。本模块是
:class:`WorldInstance` 的**唯一生产构造点**（world_instance.py 冻结：构造
点唯一 = ``runtime.assembly.assemble_project``），也是磁盘上的 GameProject
（P5 布局）到可运行 :class:`EngineInstance` 的单入口。

固定装配序（每步失败面 = 显式诊断；前 3 步的 error 级诊断 → 早退
engine=None / instance=None，assumption A1）：

1. ``content.loader.load_project``（``raw is None`` → 早退）；
2. ``content.project_ir.build_ir``（``ir is None`` → 早退）；
3. ``content.validator.validate_project``（任一 ERROR 级诊断 → 早退；
   warning 继续）；
4. ``runtime.materialize.materialize_world``（``world_instance_id =
   f"ws_{ir.manifest.project_id}"`` / ``domain_id="world"``，T1）；
5. ``runtime.extensions.load_extensions``（trust 门语义由 T3 诊断承载，
   **不**早退装配——trust gate error = 零 bundle 继续的合法路径，Gate 2
   钉面；T3）；
6. **bundle 合并**：多个 :class:`ExtensionBundle` → 单个（T3 dataclass）：
   ``action_executors`` 按声明序 union（同 id 先声明者胜 + 每冲突 1 条
   warning 诊断）/ ``dynamics_backends`` 按声明序拼接 / ``policies`` 按
   声明序 union（同 id 先声明者胜 + 每冲突 1 条 warning，assumption A2）/
   ``producer_grants`` 按声明序拼接；零 bundle → None（单 bundle 原样
   透传，零拷贝）；
7. ``runtime.action_binding.bind_actions``（``bundle=`` 合并后，T6）；
8. ``runtime.dynamics_binding.bind_dynamics``（``bundle=`` 合并后，T7）；
9. **ProducerRegistry + AuthorityPolicy**（本函数唯一推导步，规则 Leader
   已裁决，assumptions A3/A4/A5/A7/A8）：注册 (T6 grants + T7 grants) 全部
   producer_id + "engine"（SYSTEM）+ "player"（DEVELOPER）；rules = 每
   grant × 每 component_type 一条（IR 层 authority 声明不进合并——计划
   明令：仅 T6/T7/T3 显式 grant）；
10. ``runtime.observability.InMemoryTraceSink``（T8）；
11. ``runtime.llm_binding.bind_llm_policies``（``deployment`` /
    ``inference_backend`` 均 None = headless 合法，warning 由其诊断承载，
    T5）；
12. policies = ``{**lb.policies, **merged.policies}``（extension policy
    覆盖 LLM 默认；无 merged → 原样），再按 ERR-C-02 键空间重映射为
    世界实体 id 键（``ent_authoring_<slug>``；T2 engine 契约），全部经
    :class:`JsonCleanContextPolicyAdapter` 包裹（ERR-C-03）；
13. :class:`WorldInstance` 构造（contract §1 字段序，全 keyword 传参）；
14. :class:`EngineInstance`（**不传** ``context_builder``——缺省 lazy 路径
    = T4 生产面，T2）；
15. diagnostics = 全链按步序拼接（不重排序，assumption A6）。

Glue 纯度：本模块零自写 router / executor / dynamics / authority 求值
逻辑——步 6/9 之外全部是对 T1/T3/T5/T6/T7/T8 公开面的直接调用；步 6 合并
与步 9 注册/规则构造 = 计划卡逐字钉面的胶水。

Assumptions（T9 冻结面披露，Leader 可 follow-up 收编）：

1. **早退面 = 步 1–3 的 error 级诊断**（raw 缺失 / IR 编译失败 / 校验
   ERROR）。步 4 之后的显式 error 诊断（如 trust gate 的
   ``LLMSIM_PLUGIN_ENTRY_UNRESOLVED``、扩展加载失败）**不**早退——装配
   以零 bundle / 缺位面继续并把诊断汇入结果（Gate 2 钉面：trust_python=
   False 时 engine 非 None）。
2. **policies 合并冲突口径 = 同 action_executors**：先声明者胜 + 每冲突
   1 条 warning（``LLMSIM_DUPLICATE_ID``）——「union」按显式不静默纪律
   解读（后写静默覆盖被禁止）。
3. **producer origin 分类**（分类为 producer_id 的纯函数，确定性）：
   该 producer 出现在 T7 侧 grants（``metadata()`` 派生）→
   ``DYNAMICS_BACKEND``（两侧皆现时 dynamics 分类胜——其运行时 effect
   来源 = 相位 3 dynamics）；否则出现在合并 bundle 的 ``producer_grants``
   （可区分：T9 持有合并后 bundle）→ ``SCRIPT``（extension 动作 grant）；
   否则 → ``SYSTEM``（T6 自身 executor 族，如 ``actions.move``）。
4. **规则去重**：按 ``(producer_id, component_type)`` 首现胜 + 每重复 1
   条 warning（``LLMSIM_DUPLICATE_ID``）——卡面 rule_id 公式
   ``rtclosure.<pid>.<ct>`` 自身即蕴含该唯一性（重复 = 同 rule_id 两条
   规则，审计混淆）。
5. **ProducerInfo 构造面 = 卡面三字段**（``producer_id`` / ``origin`` /
   ``description``）；``priority`` 取缺省 0（冲突解析输入归 grant 侧
   authority 规则 priority，不在注册面复述）。
6. **diagnostics 全链按步序拼接，不重排序**（与 T5 的 (code, path, refs)
   排序面不同——本层保留装配步序可追溯性；卡面 step 15 钉死）。
7. **IR 层 authority 声明（``ir.authority``）零消费**：写授权只来自 T6 /
   T7 / T3 显式 grant（计划明令；K4 同向：声明不定义权限的纪律在
   content 侧已由 validator 独立检查，本层不复读）。
8. **grant 迭代序 = T7 侧先、T6 侧后**（``(*db.producer_grants,
   *ab.producer_grants)``，注册与规则构造共用）。卡面未钉规则迭代序；
   求值面 = 同 priority / 同 specificity 时**注册序** tiebreak + 首条
   匹配拍板不 fall-through（P2 冻结语义），故两 producer 同 claim 一个
   component_type 时迭代序决定谁可写。Gate 3 钉面（dynamics 的
   temperature 提交必须成功 = K2 管道实证）要求 dynamics 侧 grant 先行；
   样例 T10 的 executor/dynamics 双 producer 同 claim machine+temperature
   时，动作侧在同 ct 上被 closed-by-default 拒（样例 grant 设计问题，
   follow-up 面，非本层可扩面）。

导入纪律（contract §0）：stdlib + ``content.*`` / ``core.*`` /
``llm.adapter`` / ``llm.deployment`` / ``runtime.*`` 冻结面（DAG 向下，
零环）；零测试包 import；零项目树 walk / 零任意文件读（文件 IO 全归
``load_project`` / ``load_extensions`` 面）；诊断码仅取 18 码闭集成员
（``LLMSIM_DUPLICATE_ID``），构造期 model_validator 机械强制。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

from src.engine_v2.content.loader import load_project
from src.engine_v2.content.project_ir import build_ir
from src.engine_v2.content.schemas import Diagnostic, DiagnosticSeverity
from src.engine_v2.content.validator import validate_project
from src.engine_v2.core.authority import (
    AuthorityDecision,
    AuthorityPolicy,
    AuthorityRule,
    AuthoritySelector,
    ProducerInfo,
    ProducerRegistry,
)
from src.engine_v2.core.components import ComponentTypeId
from src.engine_v2.core.ids import ProducerId
from src.engine_v2.core.provenance import OriginKind
from src.engine_v2.llm.adapter import InferenceBackend
from src.engine_v2.llm.deployment import DeploymentProfile
from src.engine_v2.runtime.action_binding import bind_actions
from src.engine_v2.runtime.dynamics_binding import bind_dynamics
from src.engine_v2.runtime.engine import EngineInstance
from src.engine_v2.runtime.extensions import (
    ExtensionBundle,
    ProducerGrant,
    load_extensions,
)
from src.engine_v2.runtime.llm_binding import JsonCleanContextPolicyAdapter, bind_llm_policies
from src.engine_v2.runtime.materialize import materialize_world
from src.engine_v2.runtime.observability import InMemoryTraceSink
from src.engine_v2.runtime.world_instance import WorldInstance

if TYPE_CHECKING:  # 仅注解引用（house 模式；运行时零 import 这三个模块）
    from src.engine_v2.core.behavior_policy import BehaviorPolicy
    from src.engine_v2.dynamics.backend import WorldDynamicsBackend
    from src.engine_v2.modules.actions import ActionExecutor

__all__ = ["AssemblyResult", "assemble_project"]

# —— 常量（确定性文本 / 固定身份；零模块级可变状态）——

#: 重复面诊断码（18 码闭集成员；合并冲突 / 规则去重共用）。
_CODE_DUPLICATE_ID: Final[str] = "LLMSIM_DUPLICATE_ID"

#: 固定空间域名（卡面 step 4/7 钉死 ``"world"``）。
_DOMAIN_ID: Final[str] = "world"

#: WorldInstance 身份前缀（卡面 step 4：``f"ws_{project_id}"``）。
_INSTANCE_ID_PREFIX: Final[str] = "ws_"

#: 引擎级事务装配者 producer（T2 assumption 7 钉：K2 管道事务 provenance；
#: 必须注册，否则 cascade provenance 校验可能拒）。
_ENGINE_PRODUCER_ID: Final[str] = "engine"

#: 玩家提交面 producer（T2 assumption 7 钉：submit_action provenance；
#: 必须注册，理由同上）。
_PLAYER_PRODUCER_ID: Final[str] = "player"

#: authority 规则统一描述（卡面 step 9 钉字面）。
_GRANT_RULE_DESCRIPTION: Final[str] = "runtime-closure grant"


# —— 公开面（contract 冻结 API）——


@dataclass(frozen=True)
class AssemblyResult:
    """``assemble_project`` 产物（显式失败面：致命诊断 = None 对）。

    - ``engine``：装配完成 = 可运行 :class:`EngineInstance`；致命诊断
      （步 1–3 error 级，assumption A1）= ``None``；
    - ``instance``：engine 持有的 :class:`WorldInstance`（engine 非 None
      时恒 ``engine.instance is instance``）；
    - ``diagnostics``：load + build + validate + materialize + extensions
      + bundle 合并 + action/dynamics binding + authority 推导 + llm
      binding 全链诊断，按装配步序拼接（assumption A6，不重排序）。
    """

    engine: EngineInstance | None
    instance: WorldInstance | None
    diagnostics: tuple[Diagnostic, ...]


# —— 私有 glue 面（步 6 / 9；零新语义）——


def _conflict_warning(path: str, message: str, refs: tuple[str, ...]) -> Diagnostic:
    """合并/去重冲突 warning（``LLMSIM_DUPLICATE_ID``，确定性文本）。"""
    return Diagnostic(
        code=_CODE_DUPLICATE_ID,
        severity=DiagnosticSeverity.WARNING,
        path=path,
        message=message,
        refs=refs,
    )


def _merge_bundles(
    bundles: tuple[ExtensionBundle, ...],
) -> tuple[ExtensionBundle | None, list[Diagnostic]]:
    """步 6：多 bundle → 单个 ExtensionBundle（卡面钉死合并口径）。

    - 零 bundle → ``(None, [])``；单 bundle → 原样透传（零拷贝零诊断）；
    - ``action_executors`` / ``policies``：声明序 union，同 id 先声明者
      胜 + 每冲突 1 条 warning（assumption A2）；
    - ``dynamics_backends`` / ``producer_grants``：声明序拼接（零冲突
      面——序列语义）。
    """
    if not bundles:
        return None, []
    if len(bundles) == 1:
        return bundles[0], []

    diagnostics: list[Diagnostic] = []
    executors: dict[str, ActionExecutor] = {}
    for index, bundle in enumerate(bundles):
        for action_id, executor in bundle.action_executors.items():
            if action_id in executors:
                diagnostics.append(
                    _conflict_warning(
                        str(action_id),
                        f"bundle 合并：action executor {action_id!r} 重复声明"
                        f"（bundle#{index} 声明被忽略，先声明者胜）",
                        (str(index),),
                    )
                )
                continue
            executors[action_id] = executor

    dynamics: list[WorldDynamicsBackend] = []
    for bundle in bundles:
        dynamics.extend(bundle.dynamics_backends)

    policies: dict[str, BehaviorPolicy] = {}
    for index, bundle in enumerate(bundles):
        for actor_id, policy in bundle.policies.items():
            if actor_id in policies:
                diagnostics.append(
                    _conflict_warning(
                        str(actor_id),
                        f"bundle 合并：policy {actor_id!r} 重复声明"
                        f"（bundle#{index} 声明被忽略，先声明者胜）",
                        (str(index),),
                    )
                )
                continue
            policies[actor_id] = policy

    grants: list[ProducerGrant] = []
    for bundle in bundles:
        grants.extend(bundle.producer_grants)

    merged = ExtensionBundle(
        action_executors=executors,
        dynamics_backends=tuple(dynamics),
        policies=policies,
        producer_grants=tuple(grants),
    )
    return merged, diagnostics


def _classify_origin(
    producer_id: str,
    dynamics_producers: frozenset[str],
    extension_producers: frozenset[str],
) -> tuple[OriginKind, str]:
    """步 9：producer → (origin, description)（assumption A3 纯函数）。"""
    if producer_id in dynamics_producers:
        return (
            OriginKind.DYNAMICS_BACKEND,
            "T7 dynamics grant（backend metadata() 自动派生）",
        )
    if producer_id in extension_producers:
        return (
            OriginKind.SCRIPT,
            "extension 动作 grant（bundle 显式声明；T9 持有合并后 bundle，可区分）",
        )
    return OriginKind.SYSTEM, "T6 动作绑定 executor 族 grant（标准执行器自产）"


def _build_write_grants(
    action_grants: tuple[ProducerGrant, ...],
    dynamics_grants: tuple[ProducerGrant, ...],
    merged: ExtensionBundle | None,
) -> tuple[ProducerRegistry, AuthorityPolicy, list[Diagnostic]]:
    """步 9：ProducerRegistry + AuthorityPolicy（卡面唯一推导步）。

    - grant 迭代序 = **T7 侧先、T6 侧后**（assumption A8：Gate 3 的
      dynamics 提交钉面 + P2 首条匹配拍板语义）；
    - 注册序（确定性首现序）：上述 grant 序逐条 producer（每 producer
      只注册一次）→ "engine" → "player"；
    - "engine" / "player" 若已被 grant 占用 → 跳过注册 + 1 条 warning
      （显式不静默；注册冲突不 raise，assumption A3 同向）；
    - rules：每 grant × 每 component_type 一条（grant 序 = 同上注册序；
      ``rule_id = f"rtclosure.<pid>.<ct>"``；卡面钉字面），按
      ``(pid, ct)`` 去重首现胜 + 每重复 1 条 warning（assumption A4）；
    - IR 层 authority 声明零消费（assumption A7）。
    """
    diagnostics: list[Diagnostic] = []
    dynamics_producers = frozenset(
        grant.producer_id for grant in dynamics_grants
    )
    extension_producers = frozenset(
        (grant.producer_id for grant in merged.producer_grants)
        if merged is not None
        else ()
    )

    all_grants = (*dynamics_grants, *action_grants)

    registry = ProducerRegistry()
    registered: set[str] = set()
    for grant in all_grants:
        producer_id = grant.producer_id
        if producer_id in registered:
            continue
        registered.add(producer_id)
        origin, description = _classify_origin(
            producer_id, dynamics_producers, extension_producers
        )
        registry.register(
            ProducerInfo(
                producer_id=ProducerId(producer_id),
                origin=origin,
                description=description,
            )
        )

    for reserved_id, origin, description in (
        (
            _ENGINE_PRODUCER_ID,
            OriginKind.SYSTEM,
            "K2 管道事务 provenance（引擎级事务装配者，T2 assumption 7）",
        ),
        (
            _PLAYER_PRODUCER_ID,
            OriginKind.DEVELOPER,
            "玩家提交面 provenance（submit_action，T2 assumption 7）",
        ),
    ):
        if reserved_id in registered:
            diagnostics.append(
                _conflict_warning(
                    reserved_id,
                    f"producer {reserved_id!r} 已被 grant 占用（origin 由 grant "
                    f"分类决定），保留 grant 注册，跳过内置注册",
                    (reserved_id,),
                )
            )
            continue
        registry.register(
            ProducerInfo(
                producer_id=ProducerId(reserved_id),
                origin=origin,
                description=description,
            )
        )

    rules: list[AuthorityRule] = []
    seen: set[tuple[str, str]] = set()
    for grant in all_grants:
        for component_type in grant.component_types:
            key = (grant.producer_id, component_type)
            if key in seen:
                diagnostics.append(
                    _conflict_warning(
                        grant.producer_id,
                        f"producer grant 重复授权面（producer={grant.producer_id!r}, "
                        f"component_type={component_type!r}）：保留首条规则，跳过重复",
                        (grant.producer_id, component_type),
                    )
                )
                continue
            seen.add(key)
            rules.append(
                AuthorityRule(
                    selector=AuthoritySelector(
                        component_type=ComponentTypeId(component_type)
                    ),
                    allowed_writers=[ProducerId(grant.producer_id)],
                    priority=grant.priority,
                    description=_GRANT_RULE_DESCRIPTION,
                    rule_id=f"rtclosure.{grant.producer_id}.{component_type}",
                )
            )

    policy = AuthorityPolicy(
        rules=rules,
        default_decision=AuthorityDecision.DENY,  # closed-by-default（卡面钉死）
    )
    return registry, policy, diagnostics


# —— 公开入口（卡面冻结签名）——


def assemble_project(
    project_root: str | Path,
    *,
    deployment: DeploymentProfile | None = None,
    inference_backend: InferenceBackend | None = None,
    trust_python: bool = False,
) -> AssemblyResult:
    """GameProject → EngineInstance 单入口（contract §4 T9 卡；装配序逐字）。

    Args:
        project_root: P5 项目根（含 ``game.yaml``）。
        deployment: 部署画像（``llm.deployment.DeploymentProfile``）；None =
            headless（LLM 绑定 disabled 短路，warning 诊断，不抛异常）。
        inference_backend: 推理后端（``llm.adapter.InferenceBackend``）；
            None = headless（同上）。
        trust_python: Python 扩展 trust 门（T3）；False（默认）= 已声明插件
            各 1 条 error 诊断 + 零 bundle（engine 仍产出，Gate 2 钉面）。

    Returns:
        :class:`AssemblyResult`——致命诊断（步 1–3 error 级）=
        ``engine=None / instance=None`` + 诊断；否则 engine + instance +
        全链诊断（按步序拼接，assumption A6）。

    本函数不 raise 内容级异常：文件 / YAML / 编译 / 校验 / 扩展 / 绑定
    失败全部成显式诊断（never-raise 纪律经各下层模块透传）。
    """
    root = Path(project_root).resolve()
    diagnostics: list[Diagnostic] = []

    # —— 1. load（raw is None → 早退）——
    load = load_project(root)
    diagnostics.extend(load.diagnostics)
    if load.raw is None:
        return AssemblyResult(engine=None, instance=None, diagnostics=tuple(diagnostics))

    # —— 2. build_ir（ir is None → 早退）——
    ir_result = build_ir(load.raw)
    diagnostics.extend(ir_result.diagnostics)
    if ir_result.ir is None:
        return AssemblyResult(engine=None, instance=None, diagnostics=tuple(diagnostics))
    ir = ir_result.ir

    # —— 3. validate（ERROR 级 → 早退；warning 继续）——
    validation = validate_project(ir, load.raw)
    diagnostics.extend(validation.diagnostics)
    if any(d.severity == DiagnosticSeverity.ERROR for d in validation.diagnostics):
        return AssemblyResult(engine=None, instance=None, diagnostics=tuple(diagnostics))

    # —— 4. materialize（T1）——
    world_instance_id = f"{_INSTANCE_ID_PREFIX}{ir.manifest.project_id}"
    mat = materialize_world(
        ir, world_instance_id=world_instance_id, domain_id=_DOMAIN_ID
    )
    diagnostics.extend(mat.diagnostics)

    # —— 5. extensions（T3；trust 门诊断不早退，assumption A1）——
    ext = load_extensions(root, ir, trust_python=trust_python)
    diagnostics.extend(ext.diagnostics)

    # —— 6. bundle 合并（零 bundle → None）——
    merged, merge_diagnostics = _merge_bundles(ext.bundles)
    diagnostics.extend(merge_diagnostics)

    # —— 7. action binding（T6）——
    ab = bind_actions(ir, mat.spaces, domain_id=_DOMAIN_ID, bundle=merged)
    diagnostics.extend(ab.diagnostics)

    # —— 8. dynamics binding（T7）——
    db = bind_dynamics(ir, bundle=merged)
    diagnostics.extend(db.diagnostics)

    # —— 9. ProducerRegistry + AuthorityPolicy（唯一推导步）——
    producer_registry, authority_policy, grant_diagnostics = _build_write_grants(
        ab.producer_grants, db.producer_grants, merged
    )
    diagnostics.extend(grant_diagnostics)

    # —— 10. trace sink（T8）——
    sink = InMemoryTraceSink()

    # —— 11. llm binding（T5；headless 合法）——
    llm = bind_llm_policies(
        root,
        ir,
        deployment=deployment,
        backend=inference_backend,
        sink=sink,
    )
    diagnostics.extend(llm.diagnostics)

    # —— 12. policies（extension 覆盖 LLM 默认；ERR-C-02 键空间重映射 +
    #    ERR-C-03 JSON-clean 适配）——
    # 键空间 = 世界实体 id（T2 engine 契约：``policies.get(str(actor_id))``；
    # test_engine gate3 同款）。LLM 绑定面以 authoring slug（``character.id``）
    # 为键（T5 冻结面，不改）→ 经内容侧确定性命名
    # ``ent_authoring_<slug>``（ids.py:68 约定；T4 ``_AUTHORING_ENTITY_PREFIX``
    # 同款）映射；extension policy 键直通（作者以实体 id 直键），若恰为
    # character slug 则同一重映射（双口径兼容，不猜）。全部 policy（LLM /
    # extension 双源）经 :class:`JsonCleanContextPolicyAdapter` 包裹（P4 富
    # 类型 context → P5 assembler JSON-clean 边界；T11 G2 修复位）。
    _slug_to_entity = {
        character.id: f"ent_authoring_{character.id}" for character in ir.characters
    }
    policies = {**llm.policies}
    if merged is not None:
        policies.update(merged.policies)
    policies = {
        _slug_to_entity.get(actor_key, actor_key): JsonCleanContextPolicyAdapter(policy)
        for actor_key, policy in policies.items()
    }

    # —— 13. WorldInstance（contract §1 字段序，全 keyword）——
    instance = WorldInstance(
        world_instance_id=world_instance_id,
        ir=ir,
        world=mat.world,
        runtime=mat.runtime,
        spaces=mat.spaces,
        action_registry=ab.action_registry,
        executors=ab.executors,
        policies=policies,
        dynamics=db.dynamics,
        component_registry=mat.component_registry,
        producer_registry=producer_registry,
        authority_policy=authority_policy,
        trace_sink=sink,
    )

    # —— 14. EngineInstance（不传 context_builder：T4 lazy 生产面）——
    engine = EngineInstance(instance)

    # —— 15. 全链诊断按步序（不重排序，assumption A6）——
    return AssemblyResult(
        engine=engine, instance=instance, diagnostics=tuple(diagnostics)
    )
