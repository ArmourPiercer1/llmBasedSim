"""engine_v2 runtime 层 T3：explicit trusted Python extension activation
（Runtime Closure 冻结契约 §3；计划 T3 逐字面）。

职责（contract §3 冻结 API 全部在本文件；5 导出）：

- **声明 source 仅两种（不造第三种）**：
  1) ``project_root/plugins/<name>/plugin.yaml``——closed 模板两层目录（与
     ``plugins/registry.py`` ``discover_local_plugins`` 的目录约定同口径，
     本模块只确认布局、**不复用** registry 做任何 import）；raw 经
     ``content.loader.read_yaml_file`` 读 + 解析（assumption A3），manifest
     经 ``plugins.manifest.parse_plugin_manifest``（path_label = 相对路径键
     ``plugins/<name>/plugin.yaml``）；
  2) ``ProjectIR.plugin_descriptors`` 中 ``entrypoint`` 非 None 的项
     （id + entrypoint，声明序）。
  同 id 两 source 都有 → plugin.yaml 侧优先 + 恰 1 条 warning 诊断
  （``LLMSIM_DUPLICATE_ID``；确定性先声明者胜序 = local sorted 键序 →
  descriptor 声明序，assumption A5）。

- **trust_python=False（默认）= 零 import**：不触碰 importlib；每个已声明
  插件恰 1 条显式 error 诊断（code = ``LLMSIM_PLUGIN_ENTRY_UNRESOLVED``，
  message 显式说明需要 trust_python=True —— "RUNTIME_PYTHON_NOT_TRUSTED"
  类语义，assumption A1），``bundles = ()``；
- **trust_python=True = 唯一 import 路**：
  ``plugins.api.EntryPointSpec.from_string`` → ``importlib.import_module(
  spec.module)`` → ``getattr(module, spec.attribute)``；import 前
  ``sys.path.insert(0, str(Path(project_root).resolve()))``，finally 精确
  还原（saved list 回写；不删除已加载模块，assumption A2）；
- **entrypoint 对象验证（never-raise）**：必须 callable 且
  ``inspect.signature`` 恰好 1 个位置参数（POSITIONAL_ONLY /
  POSITIONAL_OR_KEYWORD；拒绝 *args / **kwargs / keyword-only；
  assumption A4）；调用 ``build_extension(ExtensionContext(project_root,
  ir))``；返回值必须 isinstance ExtensionBundle 且字段类型正确
  （action_executors = Mapping、dynamics_backends = tuple、policies =
  Mapping、producer_grants = tuple[ProducerGrant]）——任何违例 → 该插件
  恰 1 条显式诊断 + 不加载，其余插件不受影响；
- **零扫描**：未声明的 .py 文件（如项目根 rogue.py）绝不被 import /
  importlib 触碰；import_module 只碰声明的 module（其包 ``__init__.py``
  随 Python import 机制执行 = 合法）。

诊断码映射（assumption A1）：``content/schemas.py`` 的 ``Diagnostic.code``
构造期强制 18 码闭集（model_validator；零 P5 schema 扩展纪律下不可新增
RUNTIME_PYTHON_NOT_TRUSTED 独立码），故本模块复用闭集码 + 确定性 message
承载语义：

- entrypoint 解析/定位/签名失败（文法、import、属性、callable、arity）→
  ``LLMSIM_PLUGIN_ENTRY_INVALID``（error）；
- trust 门未开（声明了但不可装载）→ ``LLMSIM_PLUGIN_ENTRY_UNRESOLVED``
  （error；message 显式含 "trust_python=True"）；
- build 执行异常 / 返回类型 / 字段类型违例 → ``LLMSIM_SCHEMA``（error）；
- 同 id 重复声明 → ``LLMSIM_DUPLICATE_ID``（warning）。

导入面（冻结）：stdlib（importlib / inspect / sys / dataclasses / pathlib /
collections.abc / typing）+ ``content.loader``（read_yaml_file）+
``content.schemas``（Diagnostic / ProjectIR）+ ``plugins.api``
（EntryPointSpec）+ ``plugins.manifest``（parse_plugin_manifest）；
ActionExecutor / WorldDynamicsBackend / BehaviorPolicy 仅 TYPE_CHECKING
类型引用（house 模式，同 ``runtime/world_instance.py``，运行时零 import）。

禁止面（计划 T3）：scan .py / pip install / sandbox / hot reload / 修改
P5 PluginAPI。确定性纪律（D-P5-15 同款）：sorted 遍历、零时间戳 / 指针 /
随机、诊断文本确定性（异常面只落 ``type(exc).__name__``，不落 str(exc)）。

``__all__`` 5 名按 contract §3 API 冻结面。
"""

from __future__ import annotations

import importlib
import inspect
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

from src.engine_v2.content.loader import read_yaml_file
from src.engine_v2.content.schemas import Diagnostic, ProjectIR
from src.engine_v2.plugins.api import EntryPointSpec
from src.engine_v2.plugins.manifest import parse_plugin_manifest

if TYPE_CHECKING:  # 仅注解引用（house 模式；运行时零 import 这三个模块）
    from src.engine_v2.core.behavior_policy import BehaviorPolicy
    from src.engine_v2.dynamics.backend import WorldDynamicsBackend
    from src.engine_v2.modules.actions import ActionExecutor

__all__ = [
    "ProducerGrant",
    "ExtensionBundle",
    "ExtensionContext",
    "ExtensionLoadResult",
    "load_extensions",
]

# —— 诊断码（assumption A1：18 码闭集内复用，语义由 message 承载）——

_CODE_ENTRY_INVALID: Final[str] = "LLMSIM_PLUGIN_ENTRY_INVALID"
_CODE_ENTRY_UNRESOLVED: Final[str] = "LLMSIM_PLUGIN_ENTRY_UNRESOLVED"
_CODE_DUPLICATE_ID: Final[str] = "LLMSIM_DUPLICATE_ID"
_CODE_SCHEMA: Final[str] = "LLMSIM_SCHEMA"

#: 声明来源标签（warning 诊断 message/refs 面；确定性常量）。
_ORIGIN_LOCAL: Final[str] = "local_manifest"
_ORIGIN_DESCRIPTOR: Final[str] = "plugin_descriptor"

# —— 公开面（contract §3 冻结 API）——


@dataclass(frozen=True)
class ProducerGrant:
    """执行器自定义 producer 的显式写授权（contract §3）。

    closed-by-default 授权面的显式例外：dynamics backend 的 grant 由宿主
    （T9 assembly）从 ``metadata()`` 自动派生；executor 自定义 producer
    必须经本类型在 bundle 中显式声明。
    """

    producer_id: str
    component_types: tuple[str, ...]
    priority: int = 50


@dataclass(frozen=True)
class ExtensionBundle:
    """单个插件 entrypoint 的返回契约（contract §3 冻结面）。

    字段类型由 ``load_extensions`` 在 trust_python=True 路验证
    （action_executors = Mapping、dynamics_backends = tuple、policies =
    Mapping、producer_grants = tuple[ProducerGrant]）。
    """

    action_executors: Mapping[str, ActionExecutor]
    dynamics_backends: tuple[WorldDynamicsBackend, ...] = ()
    policies: Mapping[str, BehaviorPolicy] = ()
    producer_grants: tuple[ProducerGrant, ...] = ()


@dataclass(frozen=True)
class ExtensionContext:
    """``build_extension(context)`` 入参（contract §3 冻结面）。"""

    project_root: Path
    ir: ProjectIR


@dataclass(frozen=True)
class ExtensionLoadResult:
    """``load_extensions`` 产物（contract §3：bundles + diagnostics）。"""

    bundles: tuple[ExtensionBundle, ...]
    diagnostics: tuple[Diagnostic, ...]


# —— 私有面 ——


@dataclass(frozen=True)
class _PluginDeclaration:
    """一条已声明插件（source 二选一的纯数据记录；零 import）。"""

    plugin_id: str
    entrypoint: str
    origin: str
    path_label: str


def _discover_local_manifests(
    root: Path,
) -> tuple[list[_PluginDeclaration], list[Diagnostic]]:
    """source 1：``plugins/<name>/plugin.yaml`` closed 模板（sorted 键序，
    D-P5-15 同款确定性；无 manifest 的目录 = 静默跳过，与 registry 同口径）。

    零 .py 扫描：只列 plugins/ 直接子目录、只读固定名 plugin.yaml。
    """
    declarations: list[_PluginDeclaration] = []
    diagnostics: list[Diagnostic] = []
    plugins_dir = root / "plugins"
    if not plugins_dir.is_dir():
        return declarations, diagnostics
    for entry in sorted(plugins_dir.iterdir(), key=lambda p: p.name):
        manifest_path = entry / "plugin.yaml"
        if not entry.is_dir() or not manifest_path.is_file():
            continue
        rel_key = f"plugins/{entry.name}/plugin.yaml"
        raw, file_diags = read_yaml_file(manifest_path, rel_key)
        diagnostics.extend(file_diags)
        if raw is None:
            continue
        parsed = parse_plugin_manifest(rel_key, raw)
        diagnostics.extend(parsed.diagnostics)
        if parsed.manifest is None:
            continue
        declarations.append(
            _PluginDeclaration(
                plugin_id=parsed.manifest.id,
                entrypoint=parsed.manifest.entrypoint,
                origin=_ORIGIN_LOCAL,
                path_label=rel_key,
            )
        )
    return declarations, diagnostics


def _discover_descriptor_declarations(ir: ProjectIR) -> list[_PluginDeclaration]:
    """source 2：``ProjectIR.plugin_descriptors`` 中 entrypoint 非 None 项
    （声明序；entrypoint = None 的描述符 = 非可执行声明，静默跳过）。"""
    return [
        _PluginDeclaration(
            plugin_id=descriptor.id,
            entrypoint=descriptor.entrypoint,
            origin=_ORIGIN_DESCRIPTOR,
            path_label=descriptor.id,
        )
        for descriptor in ir.plugin_descriptors
        if descriptor.entrypoint is not None
    ]


def _dedupe_declarations(
    declarations: list[_PluginDeclaration],
) -> tuple[list[_PluginDeclaration], list[Diagnostic]]:
    """同 id 去重：先声明者胜（assumption A5 确定性序 = local sorted 键序 →
    descriptor 声明序 ⇒ 两 source 都有时 plugin.yaml 侧优先）；每重复恰 1 条
    warning（``LLMSIM_DUPLICATE_ID``，refs = 两侧 path_label 对）。"""
    kept: dict[str, _PluginDeclaration] = {}
    diagnostics: list[Diagnostic] = []
    for decl in declarations:
        first = kept.get(decl.plugin_id)
        if first is None:
            kept[decl.plugin_id] = decl
            continue
        diagnostics.append(
            Diagnostic(
                code=_CODE_DUPLICATE_ID,
                severity="warning",
                path=decl.plugin_id,
                message=(
                    f"plugin 声明重复：{decl.plugin_id}"
                    f"（{first.origin} 侧优先，{decl.origin} 侧忽略）"
                ),
                refs=(first.path_label, decl.path_label),
            )
        )
    return list(kept.values()), diagnostics


def _resolve_entrypoint_object(
    spec: EntryPointSpec, root: Path, decl: _PluginDeclaration
) -> tuple[object, Diagnostic | None]:
    """唯一 import 路（contract §3）：import 前临时 prepend 已 resolve 的
    project_root 到 sys.path，``importlib.import_module(spec.module)`` →
    ``getattr(module, spec.attribute)``；finally 精确还原 sys.path（saved
    list 回写，连带回退 import 期任何 sys.path 变动）。

    域披露（assumption A2）：不删除已加载模块（sys.modules 保留——Python
    import 机制的常规行为，卸载归宿主生命周期面）；import / getattr 任何
    异常 → (None, LLMSIM_PLUGIN_ENTRY_INVALID 显式诊断)，never-raise。
    """
    saved_path = list(sys.path)
    sys.path.insert(0, str(root))
    try:
        try:
            module = importlib.import_module(spec.module)
        except Exception as exc:  # never-raise：import 失败 = 显式诊断
            return None, Diagnostic(
                code=_CODE_ENTRY_INVALID,
                severity="error",
                path=decl.plugin_id,
                message=(
                    f"entrypoint 模块 import 失败："
                    f"{type(exc).__name__}"
                ),
                refs=(spec.module,),
            )
        try:
            return getattr(module, spec.attribute), None
        except AttributeError:
            return None, Diagnostic(
                code=_CODE_ENTRY_INVALID,
                severity="error",
                path=decl.plugin_id,
                message=f"entrypoint 属性缺失：{spec.attribute}",
                refs=(decl.entrypoint,),
            )
    finally:
        sys.path[:] = saved_path


def _check_build_signature(obj: object, decl: _PluginDeclaration) -> Diagnostic | None:
    """entrypoint 对象契约验证（assumption A4）：必须 callable 且
    ``inspect.signature`` 恰好 1 个位置参数（POSITIONAL_ONLY /
    POSITIONAL_OR_KEYWORD；拒绝 *args / **kwargs / keyword-only；带默认值
    的单一位置参数 = 仍「接受恰好 1 个位置参数」，放行）。"""
    if not callable(obj):
        return Diagnostic(
            code=_CODE_ENTRY_INVALID,
            severity="error",
            path=decl.plugin_id,
            message=f"entrypoint 对象不是 callable：{type(obj).__name__}",
            refs=(decl.entrypoint,),
        )
    try:
        params = list(inspect.signature(obj).parameters.values())
    except (TypeError, ValueError):
        return Diagnostic(
            code=_CODE_ENTRY_INVALID,
            severity="error",
            path=decl.plugin_id,
            message="entrypoint 签名不可解析（契约：接受恰好 1 个位置参数）",
            refs=(decl.entrypoint,),
        )
    if len(params) != 1 or params[0].kind not in (
        inspect.Parameter.POSITIONAL_ONLY,
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
    ):
        return Diagnostic(
            code=_CODE_ENTRY_INVALID,
            severity="error",
            path=decl.plugin_id,
            message="entrypoint 签名违例：必须接受恰好 1 个位置参数",
            refs=(decl.entrypoint,),
        )
    return None


def _bundle_field_diag(decl: _PluginDeclaration, detail: str) -> Diagnostic:
    """ExtensionBundle 字段类型违例 → LLMSIM_SCHEMA（error，path = 插件 id）。"""
    return Diagnostic(
        code=_CODE_SCHEMA,
        severity="error",
        path=decl.plugin_id,
        message=f"ExtensionBundle 字段类型违例：{detail}",
        refs=(decl.entrypoint,),
    )


def _check_bundle_fields(
    bundle: ExtensionBundle, decl: _PluginDeclaration
) -> Diagnostic | None:
    """bundle 字段类型检查（声明序；首个违例 → 恰 1 条诊断）。"""
    if not isinstance(bundle.action_executors, Mapping):
        return _bundle_field_diag(
            decl, "action_executors 必须是 Mapping[str, ActionExecutor]"
        )
    if not isinstance(bundle.dynamics_backends, tuple):
        return _bundle_field_diag(
            decl, "dynamics_backends 必须是 tuple[WorldDynamicsBackend, ...]"
        )
    if not isinstance(bundle.policies, Mapping):
        return _bundle_field_diag(
            decl, "policies 必须是 Mapping[str, BehaviorPolicy]"
        )
    if not isinstance(bundle.producer_grants, tuple) or any(
        not isinstance(grant, ProducerGrant) for grant in bundle.producer_grants
    ):
        return _bundle_field_diag(
            decl, "producer_grants 必须是 tuple[ProducerGrant]"
        )
    return None


def _build_and_validate_bundle(
    obj: object, context: ExtensionContext, decl: _PluginDeclaration
) -> tuple[ExtensionBundle | None, Diagnostic | None]:
    """调用 ``build_extension(context)`` + 返回类型/字段类型验证
    （never-raise：执行异常 → LLMSIM_SCHEMA 显式诊断，只落异常类名）。"""
    try:
        result = obj(context)
    except Exception as exc:  # never-raise：执行失败不牵连其余插件
        return None, Diagnostic(
            code=_CODE_SCHEMA,
            severity="error",
            path=decl.plugin_id,
            message=f"build_extension 执行失败：{type(exc).__name__}",
            refs=(decl.entrypoint,),
        )
    if not isinstance(result, ExtensionBundle):
        return None, Diagnostic(
            code=_CODE_SCHEMA,
            severity="error",
            path=decl.plugin_id,
            message=(
                "build_extension 返回类型违例：必须返回 ExtensionBundle，"
                f"得到 {type(result).__name__}"
            ),
            refs=(decl.entrypoint,),
        )
    field_diag = _check_bundle_fields(result, decl)
    if field_diag is not None:
        return None, field_diag
    return result, None


# —— 公开入口 ——


def load_extensions(
    project_root: str | Path,
    ir: ProjectIR,
    *,
    trust_python: bool = False,
) -> ExtensionLoadResult:
    """explicit trusted Python extension activation（contract §3 冻结语义）。

    步序（确定性；诊断按此序追加）：

    1. 声明发现：local ``plugins/<name>/plugin.yaml``（sorted 键序；yaml /
       manifest 解析诊断原样保留）→ ``ir.plugin_descriptors`` entrypoint
       非 None 项（声明序）；同 id 去重（先声明者胜 + 每重复 1 条 warning，
       plugin.yaml 侧优先）；
    2. ``trust_python=False``（默认）→ 零 import：每个已声明插件恰 1 条
       error 诊断（LLMSIM_PLUGIN_ENTRY_UNRESOLVED，message 显式说明需要
       trust_python=True），``bundles = ()``；
    3. ``trust_python=True`` → 每声明插件（声明序）：
       ``EntryPointSpec.from_string``（文法违例 → 该插件 1 条诊断，跳过）→
       唯一 import 路（import / 属性失败 → 1 条诊断，跳过）→ callable +
       恰好 1 位置参数验证（违例 → 1 条诊断，跳过）→ 调用
       ``build_extension(ExtensionContext)`` + ExtensionBundle 返回类型 /
       字段类型验证（违例 → 1 条诊断，不加载）→ 通过则 bundles 追加；
       单插件失败不影响其余插件；
    4. 返回 ``ExtensionLoadResult(bundles, diagnostics)``。

    零扫描：未声明的 .py 文件绝不被 import / importlib 触碰；本函数永不
    raise（声明发现 / 解析 / import / 验证全走显式诊断面）。
    """
    root = Path(project_root).resolve()
    diagnostics: list[Diagnostic] = []

    declarations: list[_PluginDeclaration] = []
    local_declarations, local_diagnostics = _discover_local_manifests(root)
    diagnostics.extend(local_diagnostics)
    declarations.extend(local_declarations)
    declarations.extend(_discover_descriptor_declarations(ir))
    declarations, dup_diagnostics = _dedupe_declarations(declarations)
    diagnostics.extend(dup_diagnostics)

    if not trust_python:
        for decl in declarations:
            diagnostics.append(
                Diagnostic(
                    code=_CODE_ENTRY_UNRESOLVED,
                    severity="error",
                    path=decl.plugin_id,
                    message=(
                        "python 插件未装载：trust_python=False"
                        "（需要 trust_python=True 才允许 import 声明的"
                        " entrypoint）"
                    ),
                    refs=(),
                )
            )
        return ExtensionLoadResult(bundles=(), diagnostics=tuple(diagnostics))

    context = ExtensionContext(project_root=root, ir=ir)
    bundles: list[ExtensionBundle] = []
    for decl in declarations:
        spec, parse_diag = EntryPointSpec.from_string(decl.entrypoint)
        if spec is None:
            diagnostics.append(parse_diag)
            continue
        obj, resolve_diag = _resolve_entrypoint_object(spec, root, decl)
        if resolve_diag is not None:
            diagnostics.append(resolve_diag)
            continue
        shape_diag = _check_build_signature(obj, decl)
        if shape_diag is not None:
            diagnostics.append(shape_diag)
            continue
        bundle, bundle_diag = _build_and_validate_bundle(obj, context, decl)
        if bundle is None:
            diagnostics.append(bundle_diag)
            continue
        bundles.append(bundle)
    return ExtensionLoadResult(bundles=tuple(bundles), diagnostics=tuple(diagnostics))
