"""engine_v2 core 层 JSON 序列化与快照辅助基础设施（P1-T05）。

依据 ``docs/v2/contracts/P1-core-data-contracts.md``（下称"设计文档"）§6.1
（JSON round-trip 规则）与 §1.1 文件清单（serialization.py：JSON round-trip
编解码与 JSON-clean 断言工具，归属 P1-T05）：

- :func:`dump_json` —— ``model_dump(mode="json")`` + ``json.dumps(
  ensure_ascii=False)``；全部契约模型唯一的 JSON 出口；
- :func:`load_json` —— ``json.loads`` + ``model_validate``（``extra="forbid"``
  生效）；全部契约模型唯一的 JSON 入口；
- :func:`assert_json_clean` —— 递归断言仅含 JSON 原生类型（§0.2 铁律 1 的
  程序化守卫，T06 测试口径 J1 工具）；
- :func:`deep_copy_via_roundtrip` —— dump→load 深拷贝，保证深拷贝与类型重建
  （§6.2 决策 D-15 第 4 条：快照固化走本函数，Snapshot 内数据与运行时活数据
  **零别名**，T06 测试口径 J4 隔离用例）。

§6.1 规则逐条落位：

1. **唯一合法出入口**是 ``model_dump(mode="json")`` / ``model_validate``：
   本模块的全部公开函数只走这一条路径，禁止自定义 ``__dict__`` 直写；
2. **``ensure_ascii=False``**：UTF-8 中文内容一等公民（§0.2）；加载端
   ``json.loads`` 兼容任意合法 JSON（str 或 UTF-8 bytes）；
3. **dict 键一律 str**；typed ID 序列化后为纯字符串（§0.2 铁律 2），
   反序列化由 Pydantic 重建为子类实例（``ids.py`` / ``revision.py`` 的
   ``__get_pydantic_core_schema__``，§2.1 类型保持；T06 类型保持断言）；
4. **round-trip 不得改变任何 ID 值、revision 值、枚举字面量**（G1
   "public IDs stable" 的序列化侧表达）——:func:`deep_copy_via_roundtrip`
   产物与原模型值相等（``==``）且类型逐字段保持（T06 口径 R2/J 组）。

本模块只 import 标准库与 pydantic（§0.3 import 边界白名单），不触碰 v1。
"""

from __future__ import annotations

import json
import math
from typing import Any, TypeVar

from pydantic import BaseModel

__all__ = [
    "dump_json",
    "load_json",
    "assert_json_clean",
    "deep_copy_via_roundtrip",
]

_M = TypeVar("_M", bound=BaseModel)

#: 递归断言中使用的内部路径根标记（仅错误信息展示用）。
_ROOT_PATH = "$"


def dump_json(model: BaseModel) -> str:
    """契约模型 → JSON 文本（设计文档 §6.1 唯一合法出口）。

    机械规则：``model.model_dump(mode="json")`` 展开为 JSON 原生值
    （typed ID → 纯字符串、Revision → 纯整数、枚举 → 字符串字面量、
    datetime → ISO-8601 字符串），再 ``json.dumps(ensure_ascii=False)``。

    ``ensure_ascii=False`` 使中文内容以 UTF-8 字面量落盘（§0.2 铁律；
    T06 口径 J7 中文无损）。
    """
    return json.dumps(model.model_dump(mode="json"), ensure_ascii=False)


def load_json(cls: type[_M], text: str | bytes) -> _M:
    """JSON 文本（str 或 UTF-8 bytes）→ 契约模型实例（§6.1 唯一合法入口）。

    ``json.loads`` 解析任意合法 JSON 后交 ``model_validate`` 重建：

    - ``extra="forbid"`` 生效（:class:`~src.engine_v2.core.entity.ContractModel`
      基类约定）——未知字段立即 ``ValidationError``（T06 口径 J2，契约冻结
      的程序化守卫）；
    - typed ID / Revision / 枚举 / 嵌套模型由 Pydantic 重建为对应子类实例
      （含 dict 键，§2.1 类型保持，T06 口径 R2）；
    - 校验失败（类型不符/缺失必填/不变量违反）抛 ``ValidationError``。
    """
    return cls.model_validate(json.loads(text))


def assert_json_clean(value: Any) -> None:
    """递归断言值仅含 JSON 原生类型（设计文档 §0.2 铁律 1；T06 口径 J1）。

    允许的类型集合（且仅这些）：

    - ``None`` / ``str`` / ``int`` / ``bool`` / ``float``；
    - ``list``（元素递归）；
    - ``dict``（**键必须为 str**，值递归）。

    附加的 JSON 严格性守卫：``float`` 必须为**有限值**——``NaN`` /
    ``±inf`` 不是合法 JSON 字面量（严格 JSON 规范无对应词法；Python
    ``json`` 模块默认 ``allow_nan=True`` 会静默输出非严格 JSON token，
    破坏"加载端兼容任意合法 JSON"与跨语言互通），故在此显式拒绝。

    违反任一条件抛 :class:`AssertionError`，错误信息携带 JSONPath 风格的
    定位（如 ``$.entities.ent_x.components.space.position[0]``），便于
    在全部契约模型样本（J1）中精确定位污染点。
    """
    _assert_json_clean(value, _ROOT_PATH)


def _assert_json_clean(value: Any, path: str) -> None:
    """:func:`assert_json_clean` 的递归实现（带路径定位，私有）。"""
    if value is None or isinstance(value, (str, bool)):
        return
    if isinstance(value, int):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise AssertionError(
                f"非有限浮点数不是合法 JSON 值：{path} = {value!r}"
                "（NaN/±inf 无严格 JSON 字面量，见模块 docstring）"
            )
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _assert_json_clean(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise AssertionError(
                    f"dict 键必须为 str（§0.2 铁律 1）：{path} 的键 "
                    f"{key!r} 类型为 {type(key).__name__}"
                )
            _assert_json_clean(item, f"{path}.{key}")
        return
    raise AssertionError(
        f"非 JSON 原生类型：{path} 的值为 {type(value).__name__}"
        "（允许 None/str/int/float/bool/list/dict，dict 键必须为 str）"
    )


def deep_copy_via_roundtrip(model: _M) -> _M:
    """dump→load 深拷贝：保证深拷贝与类型重建（设计文档 §6.1 / §6.2 D-15）。

    实现即 ``load_json(type(model), dump_json(model))``——唯一合法出入口
    （规则 1）的复用，不引入第二条序列化路径：

    - **深拷贝 / 零别名**：产物与原模型不共享任何可变容器（dict/list），
      改动产物不波及原模型，反之亦然（T06 口径 J3/J4 隔离用例；§6.2 D-15
      第 4 条"快照固化走 deep_copy_via_roundtrip"）；
    - **类型重建**：typed ID / Revision / 枚举 / 嵌套模型 / dict 键全部
      重建为原类型（§2.1 / §6.1 规则 3）；
    - **值相等**：产物与 ``model`` 满足 ``==``（规则 4：round-trip 不得
      改变任何 ID 值、revision 值、枚举字面量）。
    """
    return load_json(type(model), dump_json(model))
