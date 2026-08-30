"""engine_v2 plugins 层 P5 插件 API 契约面（P5-T06 / W5，设计文档 §3.9）。

依据 ``docs/v2/contracts/P5-project-format-module-plugin-dsl-design.md``（下称
"设计文档"，P5-DESIGN 冻结态）§3.9 字段级规格（3 导出）：

- **定位**：插件 API 契约面（Protocol 缝，执行归 P6+；P5 **永不 import 插件
  模块**——G5-3）。导入面 = 仅 stdlib + pydantic + ``schemas``（仅
  ``Diagnostic`` 类型；与 L122 DAG 一致）；
- **PLUGIN_API_VERSION**（``Final[str]``）：契约版本标记 ``"1"``（未来不兼容
  演进递增，§3.9 L487 逐字）；
- **EntryPointSpec**（frozen）：``module``（点分标识符）/ ``attribute``
  （标识符）；``from_string(s)`` = 纯解析——合法 → (spec, None)，非法 →
  (None, LLMSIM_PLUGIN_ENTRY_INVALID path=s refs=())。entrypoint 文法正则
  常量在本模块与 ``plugins/manifest.py`` 各自同值定义，禁止互导（设计文档
  §3.9 共享口径条款；测试同值核验）；
- **PluginAPI**（``@runtime_checkable`` Protocol）：仅属性声明 ``id`` /
  ``version`` / ``capabilities``（P5 = 形状声明；任何对实例的方法调用 = P6+
  runtime 行为，P5 测试仅做 isinstance 形状断言，§3.9 L489 逐字）；
- **D-P5-15 确定性纪律**：零时间戳 / 指针 / 随机；诊断文本确定性。

``__all__`` 3 名按设计文档 §8.2 导出台账逐名逐序。
"""

from __future__ import annotations

import re
from typing import Final, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

from src.engine_v2.content.schemas import Diagnostic

__all__ = [
    "PLUGIN_API_VERSION",
    "EntryPointSpec",
    "PluginAPI",
]

#: 插件 API 契约版本标记（设计文档 §3.9 L487 逐字；未来不兼容演进递增）。
PLUGIN_API_VERSION: Final[str] = "1"

#: entrypoint 文法（与 ``plugins/manifest.py`` 同值常量，禁止互导）：
#: ``module:Attribute`` 恰一个冒号（正则结构性保证）；module = 点分 Python
#: 标识符，attribute = Python 标识符（大写允许）。
_ENTRYPOINT_PATTERN: Final[str] = (
    r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*:[A-Za-z_][A-Za-z0-9_]*$"
)


def _split_entrypoint(value: str) -> tuple[str, str] | None:
    """entrypoint 纯解析函数（本模块自持，与 ``plugins/manifest.py`` 不互导）：
    文法命中 → ``(module, attribute)``；否则 None（正则结构性保证恰一个冒号，
    ``split(":", 1)`` 安全）。"""
    if re.fullmatch(_ENTRYPOINT_PATTERN, value) is None:
        return None
    module, attribute = value.split(":", 1)
    return module, attribute


# —— 公开面（§8.2 台账序）——


class EntryPointSpec(BaseModel):
    """entry-point 静态规格（设计文档 §3.9 L488：frozen；``module`` = 点分
    标识符，``attribute`` = 标识符）。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    module: str
    attribute: str

    @classmethod
    def from_string(cls, s: str) -> tuple[EntryPointSpec | None, Diagnostic | None]:
        """``module:Attribute`` 纯解析（设计文档 §3.9 L488）：合法 →
        (spec, None)；非法 → (None, LLMSIM_PLUGIN_ENTRY_INVALID path=s
        refs=())。域披露：s 空串 = 域外（调用方契约：registry 路在调用本
        函数前将空值短路为 ENTRY_INVALID；Diagnostic.path 非空约束，SOT
        §3.1 L167）。"""
        parsed = _split_entrypoint(s)
        if parsed is None:
            return None, Diagnostic(
                code="LLMSIM_PLUGIN_ENTRY_INVALID",
                severity="error",
                path=s,
                message=f"plugin entrypoint 文法违例：{s}",
                refs=(),
            )
        module, attribute = parsed
        return cls(module=module, attribute=attribute), None


@runtime_checkable
class PluginAPI(Protocol):
    """插件 API 契约形状（设计文档 §3.9 L489：P5 = 形状声明，
    runtime_checkable；执行归 P6+）。

    仅属性声明：任何对 ``PluginAPI`` 实例的方法调用 = P6+ runtime 行为
    （P5 测试仅做 isinstance 形状断言，零方法调用）。
    """

    id: str
    version: str
    capabilities: tuple[str, ...]
