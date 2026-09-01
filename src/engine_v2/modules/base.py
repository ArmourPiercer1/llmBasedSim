"""P9 W1 模块公共面（T02 base）：官方模块身份 / id 闭集 / id 文法。

设计依据 = SOT ``docs/v2/contracts/P9-official-modules-migration-design.md``
§3.1（模块公共面；导出 5 名，``__all__`` 逐字按序）。base.py 本身不是
官方模块（模块公共面），不设 IDENTITY 常量。

导入闭集（SOT §3.0）：仅 stdlib（re / dataclasses / typing）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

__all__ = [
    "ModuleIdentity",
    "OFFICIAL_MODULE_IDS",
    "OFFICIAL_MODULE_VERSION",
    "parse_module_id",
    "UnknownModuleIdError",
]


class UnknownModuleIdError(ValueError):
    """非官方 id / 文法违例（官方模块 id 文法校验失败）。"""


@dataclass(frozen=True)
class ModuleIdentity:
    """官方模块身份三元组；每官方模块以模块级常量
    ``IDENTITY: Final[ModuleIdentity]`` 持有（SOT §3.1.2 表行 1）。"""

    module_id: str
    version: str
    requires: tuple[str, ...]


#: 官方模块 id 闭集（P9-INV-5）；13 名按 Spec §40（L1951–1963）逐字序
#: （SOT §3.1.2 表行 2）。
OFFICIAL_MODULE_IDS: Final[tuple[str, ...]] = (
    "llmsim-standard-attributes",
    "llmsim-standard-inventory",
    "llmsim-standard-character",
    "llmsim-standard-knowledge",
    "llmsim-standard-perception",
    "llmsim-standard-relationships",
    "llmsim-standard-space",
    "llmsim-standard-actions",
    "llmsim-standard-scenario",
    "llmsim-standard-dialogue",
    "llmsim-standard-tactical",
    "llmsim-standard-dynamics",
    "llmsim-standard-narration",
)

#: 统一初始版本；满足 P5 版本文法 ``^\d+(\.\d+)*$``（P5 D-P5-06）。
OFFICIAL_MODULE_VERSION: Final[str] = "1"

# id 文法 = ``llmsim-standard-`` 前缀 + 小写蛇形尾段（字符类
# ``[a-z][a-z0-9_]*``，fullmatch 校验；零裸词界转义，D3）。
_MODULE_ID_RE: Final[re.Pattern[str]] = re.compile(
    r"llmsim-standard-[a-z][a-z0-9_]*",
)


def parse_module_id(text: str) -> str:
    """校验官方模块 id 文法；通过原样返回，失败抛 ``UnknownModuleIdError``。

    文法（SOT §3.1.2 表行 4）= ``llmsim-standard-`` 前缀 + 小写蛇形尾段
    （字符类 ``[a-z][a-z0-9_]*``，fullmatch 校验）。本函数只校验文法面，
    不校验闭集成员（AD-P9-3 边缘面：大写 / 空尾段 / 前缀缺失全拒）；
    闭集 = ``OFFICIAL_MODULE_IDS``，成员校验面归宿主。
    """
    if _MODULE_ID_RE.fullmatch(text) is None:
        raise UnknownModuleIdError(f"官方模块 id 文法违例: {text!r}")
    return text
