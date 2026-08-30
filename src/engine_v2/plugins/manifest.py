"""engine_v2 plugins 层 P5 本地插件 manifest 解析（P5-T05 / W5，设计文档 §3.8）。

依据 ``docs/v2/contracts/P5-project-format-module-plugin-dsl-design.md``（下称
"设计文档"，P5-DESIGN 冻结态）§3.8 字段级规格（3 导出）：

- **定位**：本地项目插件 manifest（Spec §28.1 "必须显式 manifest" L1520-1521；
  禁隐式扫描 L1528）的解析。P5 跨模块导入面 = ``schemas``（``Diagnostic`` /
  ``_ContractModel``）+ stdlib + pydantic（字段 pattern 约束，§3.1 导入纪律
  全局白名单）；plugins 包内零互导（与 L122 DAG 一致——``api.py`` 与本模块
  各自持有 entrypoint 文法同值实现，禁止互导）；
- **PluginManifest**（frozen / extra="forbid"，K2 / D-P5-05）：``id``（1-64
  小写 id 词法）/ ``version``（点分数字串）/ ``entrypoint``（``module:
  Attribute``）/ ``requires`` / ``optional`` / ``conflicts``（tuple，默认
  ``()``）/ ``engine_version``（默认 ``""``，文法同 ``ProjectManifest``，
  D-P5-06）——§3.8 字段表逐字；
- **entrypoint 文法**（恰一个冒号；module = 点分 Python 标识符，attribute =
  Python 标识符，大写允许）：本模块持有正则常量 ``_ENTRYPOINT_PATTERN`` 与
  纯解析函数 ``_split_entrypoint``；``plugins/api.py`` 各自持有同值常量 +
  纯解析函数，测试含同值核验用例（设计文档 §3.9 共享口径条款）；
- **parse_plugin_manifest 永不 raise**（K2 / P5-INV-2 纯产新值）：非 dict
  raw → ``LLMSIM_SCHEMA``（path=path_label，refs=()）；字段违例（pydantic
  ``ValidationError``）→ 每条 error 一条 ``LLMSIM_SCHEMA``（refs = [loc 点分
  串, type]，pydantic errors() 产出序）并立即返回（不再做 entrypoint 文法
  检查）；entrypoint 文法违例 → ``LLMSIM_PLUGIN_ENTRY_INVALID``（path=
  path_label，refs = [entrypoint 原值]）；全过 → (manifest, ())；
- **D-P5-15 确定性纪律**：零时间戳 / 指针 / 随机；诊断文本确定性。

``__all__`` 3 名按设计文档 §8.2 导出台账逐名逐序。
"""

from __future__ import annotations

import re
from typing import Any, Final

from pydantic import Field, ValidationError

from src.engine_v2.content.schemas import (
    _ContractModel,
    Diagnostic,
)

__all__ = [
    "PluginManifest",
    "PluginManifestParseResult",
    "parse_plugin_manifest",
]

# —— 词法规则（设计文档 §3.8 字段表约束列，逐字；D-P5-06 版本/版本约束文法族）——

#: 插件 id 词法（§3.8 L470 逐字：1-64 字符，小写字母开头）。
_PLUGIN_ID_PATTERN: Final[str] = r"^[a-z][a-z0-9_]{0,63}$"

#: 版本文法（D-P5-06：点分数字串 1+ 分量，``\d+(\.\d+)*``）。
_PLUGIN_VERSION_PATTERN: Final[str] = r"^\d+(\.\d+)*$"

#: ``engine_version`` 约束文法（§3.8 L476 "文法同 ProjectManifest"，D-P5-06）：
#: ``""``（= 任意）| V | ``>=V``（V = 点分数字串 1+ 分量）。
_ENGINE_VERSION_CONSTRAINT_PATTERN: Final[str] = (
    r"^(?:\d+(?:\.\d+)*|>=\d+(?:\.\d+)*)?$"
)

#: entrypoint 文法（§3.8 L472）：``module:Attribute`` 恰一个冒号（正则结构性
#: 保证）；module = 点分 Python 标识符，attribute = Python 标识符（大写允许）。
#: 同值常量由 ``plugins/api.py`` 各自持有（禁止互导；测试同值核验）。
_ENTRYPOINT_PATTERN: Final[str] = (
    r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*:[A-Za-z_][A-Za-z0-9_]*$"
)


def _split_entrypoint(entrypoint: str) -> tuple[str, str] | None:
    """entrypoint 纯解析函数（本模块自持，与 ``plugins/api.py`` 不互导）：
    文法命中 → ``(module, attribute)``；否则 None（正则结构性保证恰一个冒号，
    ``split(":", 1)`` 安全）。"""
    if re.fullmatch(_ENTRYPOINT_PATTERN, entrypoint) is None:
        return None
    module, attribute = entrypoint.split(":", 1)
    return module, attribute


def _schema_diagnostic(path_label: str, err: dict[str, Any]) -> Diagnostic:
    """单条 pydantic error → ``LLMSIM_SCHEMA``（§3.8 L479 逐字口径：refs =
    [loc 点分串, type]；确定性 message）。"""
    loc = ".".join(str(part) for part in err["loc"])
    err_type = str(err["type"])
    return Diagnostic(
        code="LLMSIM_SCHEMA",
        severity="error",
        path=path_label,
        message=f"plugin manifest 字段违例：{loc} {err_type}",
        refs=(loc, err_type),
    )


# —— 公开面（§8.2 台账序）——


class PluginManifest(_ContractModel):
    """本地项目插件 manifest（设计文档 §3.8 字段表逐字；Spec §28.1 例
    ``infection`` / ``my_game.systems.infection:InfectionSystem``）。"""

    id: str = Field(pattern=_PLUGIN_ID_PATTERN)
    version: str = Field(pattern=_PLUGIN_VERSION_PATTERN)
    entrypoint: str
    requires: tuple[str, ...] = ()
    optional: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    engine_version: str = Field(default="", pattern=_ENGINE_VERSION_CONSTRAINT_PATTERN)


class PluginManifestParseResult(_ContractModel):
    """``parse_plugin_manifest`` 产物（设计文档 §3.8 L478：frozen；解析失败 →
    ``manifest`` = None + 诊断集）。"""

    manifest: PluginManifest | None
    diagnostics: tuple[Diagnostic, ...]


def parse_plugin_manifest(path_label: str, raw: Any) -> PluginManifestParseResult:
    """解析单个本地插件 manifest（设计文档 §3.8 L479 三段流程，永不 raise）：

    域披露：path_label = 非空文件键（调用方契约：discover_local_plugins
    输入即文件键）。

    1. 非 dict raw → (None, [LLMSIM_SCHEMA path=path_label refs=()])；
    2. 字段违例（pydantic ``ValidationError``）→ 每条 error 一条 LLMSIM_SCHEMA
       （refs = [loc 点分串, type]，pydantic errors() 产出序），立即返回
       （不再做 entrypoint 文法检查）；
    3. entrypoint 文法违例 → (None, [LLMSIM_PLUGIN_ENTRY_INVALID
       path=path_label refs=[entrypoint 原值]])；全过 → (manifest, ())。
    """
    if not isinstance(raw, dict):
        return PluginManifestParseResult(
            manifest=None,
            diagnostics=(
                Diagnostic(
                    code="LLMSIM_SCHEMA",
                    severity="error",
                    path=path_label,
                    message="plugin manifest 根不是 dict 映射",
                    refs=(),
                ),
            ),
        )
    try:
        manifest = PluginManifest.model_validate(raw)
    except ValidationError as exc:
        return PluginManifestParseResult(
            manifest=None,
            diagnostics=tuple(
                _schema_diagnostic(path_label, err) for err in exc.errors()
            ),
        )
    if _split_entrypoint(manifest.entrypoint) is None:
        return PluginManifestParseResult(
            manifest=None,
            diagnostics=(
                Diagnostic(
                    code="LLMSIM_PLUGIN_ENTRY_INVALID",
                    severity="error",
                    path=path_label,
                    message=f"plugin entrypoint 文法违例：{manifest.entrypoint}",
                    refs=(manifest.entrypoint,),
                ),
            ),
        )
    return PluginManifestParseResult(manifest=manifest, diagnostics=())
