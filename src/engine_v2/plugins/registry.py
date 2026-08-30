"""engine_v2 plugins 层 P5 插件注册表（P5-T05/T06 / W5，设计文档 §3.10）。

依据 ``docs/v2/contracts/P5-project-format-module-plugin-dsl-design.md``（下称
"设计文档"，P5-DESIGN 冻结态）§3.10 字段级规格（7 导出）：

- **定位**：双路发现（本地 manifest + entry-point）+ 注册校验（G5-2/G5-3）。
  导入面 = ``schemas``（含 ``RawProject`` 类型）+ ``content/project_ir``（仅
  ``ProjectIR`` 类型）+ ``plugins.manifest`` + ``plugins.api`` +
  ``importlib.metadata`` + pydantic（仅 ``ValidationError``，EP 路构造违例
  捕获）+ stdlib（§3.1 导入纪律）；
- **机械面（G5-3 / 断言 #6）**：本文件与 ``content/loader.py`` 同属 AST 封闭
  模式扫描对象（封闭模式清单见设计文档 D-P5-07 / D-P5-08）：发现面仅走
  metadata / manifest 数据面，零动态模块加载；``importlib.metadata`` 使用面
  仅限本文件，**只读 metadata、零 import**（D-P5-08）——EP 对象只读
  ``.name`` / ``.value`` / ``.distribution``，零 load 方法调用；
  ``importlib.metadata.entry_points`` 一律运行时属性查找（不在 import 期绑定
  局部名，单测 monkeypatch 可拦截，断言 #5）；
- **ENGINE_VERSION 重导出**（D-P5-08 / ERR-P5-3 S-A）：单点权威 =
  ``schemas.ENGINE_VERSION``（值 ``"0.5.0"``），顶层重导出、入 ``__all__``、
  不另定义；
- **discover_local_plugins**（D-P5-07）：closed 模板
  ``plugins/<id>/plugin.yaml``（正则 ``^plugins/[^/]+/plugin\\.yaml$``）匹配
  ``raw.files`` 键，``sorted`` 序遍历（D-P5-15）→ ``parse_plugin_manifest``
  （``raw.files`` 值 = YAML 解析结果，直接传入，不重解析）；解析失败（
  manifest 为 None）→ 跳过该 manifest + 保留诊断；id 重复（跨本地 manifest）
  → 一条 LLMSIM_DUPLICATE_ID（path="plugins"，refs=[id, 首文件, 重文件]），
  后者胜出（sorted 键序）；无 manifest 的 ``plugins/<id>/`` 目录 = 无键 =
  零注册零诊断（静默忽略）；
- **discover_entry_point_plugins**（D-P5-08 metadata-only，零 import）：默认
  group = ``llmsim.plugins``；EP 按 ``(EP.name.casefold(), EP.name)`` 升序
  遍历；值文法违例 → LLMSIM_PLUGIN_ENTRY_INVALID（path=EP.value，refs=[
  distribution 名；distribution 为 None 时 refs=()]）；合法 →
  RegisteredPlugin(source=ENTRY_POINT，manifest version = distribution 版本
  或 ``"0.0.0"``，origin = distribution 名或 EP 名)；EP 重名（不同
  distribution 同名）→ 零诊断，sorted 序后者胜（构造期 casefold 唯一性由
  发现函数保证，§3.10 PluginRegistry 条款）；EP 接线披露：P5 仅由单测钉死
  （断言 #5，metadata-only 证明），管线接线归 P6+；
- **validate_plugins**（返回列表；步序 = 列表序）：① ``raw`` 非 None ∧
  ``raw.plugins_dir_present`` ∧ ``¬raw.pyproject_present`` → 恰好 1 条
  LLMSIM_PLUGIN_NO_PYPROJECT（path="pyproject.toml"，refs 逐字，D-P5-07）；
  ② ``registry.plugins`` 按 id casefold 升序：``manifest.engine_version`` 非
  空且不满足（比较目标 = ``engine_version`` 参数）→ LLMSIM_ENGINE_VERSION
  （path=manifest.id，refs=[constraint, engine_version]；比较文法 D-P5-06 /
  ERR-P5-2 F-6：``""``=任意 / ``>=V``=补 0 逐位 / 裸 ``V``=精确（补 0 元组
  相等））；③ ``ir.plugin_descriptors`` 声明序：id ∉ ``registry.plugins`` →
  LLMSIM_PLUGIN_ENTRY_UNRESOLVED（**warning**，path=descriptor.id，refs=[
  descriptor.source]；运行时或可由其他 distribution 提供，不阻塞 validate，
  D-P5-08）；
- **D-P5-15 确定性纪律**：sorted 遍历；无时间戳 / 指针 / 随机。

``__all__`` 7 名按设计文档 §8.2 导出台账逐名逐序。
"""

from __future__ import annotations

import importlib.metadata
import re
from enum import Enum
from typing import Final

from pydantic import ValidationError

from src.engine_v2.content.project_ir import ProjectIR
from src.engine_v2.content.schemas import (
    ENGINE_VERSION,
    _ContractModel,
    Diagnostic,
    RawProject,
)
from src.engine_v2.plugins.api import EntryPointSpec
from src.engine_v2.plugins.manifest import PluginManifest, parse_plugin_manifest

__all__ = [
    "ENGINE_VERSION",
    "PluginSourceKind",
    "RegisteredPlugin",
    "PluginRegistry",
    "discover_local_plugins",
    "discover_entry_point_plugins",
    "validate_plugins",
]

# —— 常量与私有工具 ——

#: 本地 manifest closed 模板（设计文档 §3.10 L501：``plugins/*/plugin.yaml``
#: 恰好两层；无 manifest = 无键 = 静默，D-P5-07）。
_LOCAL_MANIFEST_KEY_PATTERN: Final[str] = r"^plugins/[^/]+/plugin\.yaml$"


def _version_components(version: str) -> tuple[str, ...]:
    """版本文法字符串（裸 V）→ 点分组件串元组（纯字符串，零 int() 调用）。"""
    return tuple(version.split("."))


def _version_cmp(a: str, b: str) -> int:
    """点分版本纯字符串比较（-1 / 0 / 1）。

    机制（ERR-P5-14：CPython 3.12 int() 受 4300 位数字串上限约束，击穿
    never-raise 纪律，版本路径零 int() 调用）：两串按点分拆组件、组件数对齐
    （缺者补 "0"）；每组件去前导 0（去空则 "0"）；逐组件先比组件串长度（长
    者大）、再比字典序。口径等价性声明：结果与「数值补 0 逐位比较」
    （D-P5-06 口径）逐位一致——前导 0 不改变数值大小，等长纯数字串的字典
    序 = 数值序。
    """
    left = _version_components(a)
    right = _version_components(b)
    size = max(len(left), len(right))
    left = left + ("0",) * (size - len(left))
    right = right + ("0",) * (size - len(right))
    for la, ra in zip(left, right):
        la = la.lstrip("0") or "0"
        ra = ra.lstrip("0") or "0"
        if len(la) != len(ra):
            return -1 if len(la) < len(ra) else 1
        if la < ra:
            return -1
        if la > ra:
            return 1
    return 0


def _engine_version_satisfied(constraint: str, engine_version: str) -> bool:
    """``engine_version`` 约束比较文法（D-P5-06 / ERR-P5-2 F-6）：``""`` =
    任意；``>=V`` = 不小于（逐位比较，短者补 0）；裸 ``V`` = 精确（补 0
    元组相等）。比较走纯字符串机制，版本路径零 int() 调用（ERR-P5-14）。"""
    if constraint == "":
        return True
    if constraint.startswith(">="):
        return _version_cmp(engine_version, constraint[2:]) >= 0
    return _version_cmp(engine_version, constraint) == 0


# —— 公开面（§8.2 台账序）——


class PluginSourceKind(str, Enum):
    """插件来源种类（设计文档 §3.10 L498 逐字）。"""

    LOCAL_MANIFEST = "local_manifest"
    ENTRY_POINT = "entry_point"


class RegisteredPlugin(_ContractModel):
    """已注册插件（设计文档 §3.10 L499：frozen；``origin`` 本地 = 相对路径
    ``plugins/<id>/plugin.yaml``，entry-point = distribution 名或 EP 名）。"""

    manifest: PluginManifest
    source: PluginSourceKind
    origin: str


class PluginRegistry(_ContractModel):
    """插件注册表（设计文档 §3.10 L500：frozen；``plugins`` key =
    manifest.id，构造期 casefold 唯一性由发现函数保证）。"""

    plugins: dict[str, RegisteredPlugin]


def discover_local_plugins(
    raw: RawProject,
) -> tuple[PluginRegistry, tuple[Diagnostic, ...]]:
    """双路发现路 1：本地 ``plugins/<id>/plugin.yaml`` manifest（设计文档
    §3.10 L501 / D-P5-07）。

    - closed 模板 ``^plugins/[^/]+/plugin\\.yaml$`` 匹配 ``raw.files`` 键，
      ``sorted`` 序遍历（D-P5-15）；
    - 每命中 → ``parse_plugin_manifest(path_label=key, raw=raw.files[key])``
      （``raw.files`` 值 = YAML 解析结果，直接传入，不重解析）；解析失败
      （manifest 为 None）→ 跳过该 manifest + 保留诊断；
    - id 重复（跨本地 manifest）→ 一条 LLMSIM_DUPLICATE_ID（path="plugins"，
      refs=[id, 首文件, 重文件]），后者胜出（sorted 键序）；
    - 无 manifest 的 ``plugins/<id>/`` 目录 = 无键 = 零注册零诊断（静默）。
    """
    plugins: dict[str, RegisteredPlugin] = {}
    diagnostics: list[Diagnostic] = []
    first_file_by_id: dict[str, str] = {}
    for key in sorted(raw.files):
        if re.fullmatch(_LOCAL_MANIFEST_KEY_PATTERN, key) is None:
            continue
        result = parse_plugin_manifest(path_label=key, raw=raw.files[key])
        if result.manifest is None:
            diagnostics.extend(result.diagnostics)
            continue
        manifest = result.manifest
        casefolded_id = manifest.id.casefold()
        if casefolded_id in first_file_by_id:
            diagnostics.append(
                Diagnostic(
                    code="LLMSIM_DUPLICATE_ID",
                    severity="error",
                    path="plugins",
                    message=f"plugin id 重复：{manifest.id}",
                    refs=(manifest.id, first_file_by_id[casefolded_id], key),
                )
            )
        else:
            first_file_by_id[casefolded_id] = key
        plugins[manifest.id] = RegisteredPlugin(
            manifest=manifest,
            source=PluginSourceKind.LOCAL_MANIFEST,
            origin=key,
        )
    return PluginRegistry(plugins=plugins), tuple(diagnostics)


def discover_entry_point_plugins(
    group: str = "llmsim.plugins",
) -> tuple[PluginRegistry, tuple[Diagnostic, ...]]:
    """双路发现路 2：entry-point 组 metadata 枚举（设计文档 §3.10 L502 /
    D-P5-08：metadata-only，零 import；无网络、无磁盘读取授权）。

    - 运行时属性查找 ``importlib.metadata.entry_points(group=group)``
      （单测 monkeypatch 可拦截，断言 #5）；
    - EP 按 ``(EP.name.casefold(), EP.name)`` 升序遍历（D-P5-15 确定性）；
    - EP.value 空串 → LLMSIM_PLUGIN_ENTRY_INVALID（path=EP.name，
      refs=[EP.value]），跳过该 EP（ERR-P5-14）；
    - 值文法违例 → LLMSIM_PLUGIN_ENTRY_INVALID（path=EP.value，refs=[
      distribution 名；distribution 为 None 时 refs=()]）；
    - 值合法但构造期字段 pattern 违例（id 64 边界 / version 文法）→ 每条
      error 一条 LLMSIM_SCHEMA（path=distribution 名，distribution 为 None
      时 EP 名，refs=[loc 点分串, type]），该 EP 跳过不注册，继续后续 EP
      （never-raise；ERR-P5-14）；
    - 合法 → RegisteredPlugin(source=ENTRY_POINT，origin = distribution 名
      或 EP 名，manifest version = distribution 版本或 ``"0.0.0"``)；
    - EP 重名（不同 distribution 同名）→ 零诊断，sorted 序后者胜（casefold
      唯一性；同名覆盖，先入者被替换）。
    """
    eps = importlib.metadata.entry_points(group=group)
    plugins: dict[str, RegisteredPlugin] = {}
    diagnostics: list[Diagnostic] = []
    for ep in sorted(eps, key=lambda item: (item.name.casefold(), item.name)):
        if ep.value == "":
            diagnostics.append(
                Diagnostic(
                    code="LLMSIM_PLUGIN_ENTRY_INVALID",
                    severity="error",
                    path=ep.name,
                    message="plugin entrypoint 空值（entry-point 路）",
                    refs=(ep.value,),
                )
            )
            continue
        spec, _diag = EntryPointSpec.from_string(ep.value)
        if spec is None:
            dist_name = ep.distribution.name if ep.distribution is not None else None
            diagnostics.append(
                Diagnostic(
                    code="LLMSIM_PLUGIN_ENTRY_INVALID",
                    severity="error",
                    path=ep.value,
                    message="plugin entrypoint 文法违例（entry-point 路）",
                    refs=(dist_name,) if dist_name is not None else (),
                )
            )
            continue
        dist = ep.distribution
        if dist is not None and dist.version is not None:
            version = str(dist.version)
        else:
            version = "0.0.0"
        origin = dist.name if dist is not None else ep.name
        try:
            manifest = PluginManifest(
                id=ep.name, version=version, entrypoint=ep.value
            )
        except ValidationError as exc:
            path_label = dist.name if dist is not None else ep.name
            for err in exc.errors():
                loc = ".".join(str(part) for part in err["loc"])
                err_type = str(err["type"])
                diagnostics.append(
                    Diagnostic(
                        code="LLMSIM_SCHEMA",
                        severity="error",
                        path=path_label,
                        message=(
                            f"plugin entrypoint manifest field violation: "
                            f"{ep.name} {ep.value} {loc} {err_type}"
                        ),
                        refs=(loc, err_type),
                    )
                )
            continue
        for existing_id in plugins:
            if existing_id.casefold() == ep.name.casefold():
                del plugins[existing_id]
                break
        plugins[ep.name] = RegisteredPlugin(
            manifest=manifest,
            source=PluginSourceKind.ENTRY_POINT,
            origin=origin,
        )
    return PluginRegistry(plugins=plugins), tuple(diagnostics)


def validate_plugins(
    registry: PluginRegistry,
    ir: ProjectIR,
    raw: RawProject | None = None,
    engine_version: str = ENGINE_VERSION,
) -> list[Diagnostic]:
    """注册校验（设计文档 §3.10 L503-506；返回列表，步序 = 列表序）：

    1. ``raw`` 非 None ∧ ``raw.plugins_dir_present`` ∧ ``¬raw.pyproject_present``
       → 恰好 1 条 LLMSIM_PLUGIN_NO_PYPROJECT（path="pyproject.toml"，refs
       逐字，D-P5-07）；
    2. ``registry.plugins`` 按 id casefold 升序：``manifest.engine_version``
       非空且对照 ``engine_version`` 参数不满足（D-P5-06 比较文法）→
       LLMSIM_ENGINE_VERSION（path=manifest.id，refs=[constraint,
       engine_version]）；
    3. ``ir.plugin_descriptors`` 声明序：id ∉ ``registry.plugins`` →
       LLMSIM_PLUGIN_ENTRY_UNRESOLVED（**warning**，path=descriptor.id，
       refs=[descriptor.source]；不阻塞 validate，D-P5-08）。
    """
    diagnostics: list[Diagnostic] = []
    if raw is not None and raw.plugins_dir_present and not raw.pyproject_present:
        diagnostics.append(
            Diagnostic(
                code="LLMSIM_PLUGIN_NO_PYPROJECT",
                severity="error",
                path="pyproject.toml",
                message="plugins/ 目录存在但 pyproject.toml 缺失",
                refs=("plugins/ present but pyproject.toml missing",),
            )
        )
    for plugin_id in sorted(registry.plugins, key=str.casefold):
        manifest = registry.plugins[plugin_id].manifest
        constraint = manifest.engine_version
        if constraint != "" and not _engine_version_satisfied(
            constraint, engine_version
        ):
            diagnostics.append(
                Diagnostic(
                    code="LLMSIM_ENGINE_VERSION",
                    severity="error",
                    path=manifest.id,
                    message=f"engine version 约束不满足：{constraint}",
                    refs=(constraint, engine_version),
                )
            )
    for descriptor in ir.plugin_descriptors:
        if descriptor.id not in registry.plugins:
            diagnostics.append(
                Diagnostic(
                    code="LLMSIM_PLUGIN_ENTRY_UNRESOLVED",
                    severity="warning",
                    path=descriptor.id,
                    message="声明的插件未在注册表",
                    refs=(descriptor.source,),
                )
            )
    return diagnostics
