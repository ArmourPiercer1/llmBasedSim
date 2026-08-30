"""P5-T05/T06（W5）共享构造器 + 假件（设计文档 §3.8 / §3.9 / §3.10）。

模块级名（扁平测试直接 import，fixture 可省）：

- ``PLUGIN_ENTRYPOINT_PATTERN``：entrypoint 文法同值正则常量（测试交叉核验
  用：必须等于 ``src/engine_v2/plugins/manifest.py`` 与 ``api.py`` 各自持有
  的同值常量，设计文档 §3.9 共享口径条款）；
- ``FakeDistribution``：distribution metadata 假件（registry 发现面只读
  ``name`` / ``version`` 属性，D-P5-08 metadata-only）；
- ``FakeEntryPoint``：entry-point 对象假件（registry 发现面只读 ``name`` /
  ``value`` / ``distribution`` 属性；``distribution`` = 带 version 属性的
  假对象或 None；hermetic：零真实 distribution、零网络、零文件系统写）；
- ``make_manifest_dict(**overrides)``：最小合法 plugin manifest dict
  （基线：id=infection / version=1.0 / entrypoint=
  my_game.systems.infection:InfectionSystem，Spec §28.1 例面）。
"""

from __future__ import annotations

from typing import Any

#: entrypoint 文法同值正则常量（测试交叉核验用；与 manifest.py / api.py
#: 常量同值，设计文档 §3.9 共享口径条款）。
PLUGIN_ENTRYPOINT_PATTERN: str = (
    r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*:[A-Za-z_][A-Za-z0-9_]*$"
)


class FakeDistribution:
    """distribution metadata 假件（仅 ``name`` / ``version`` 属性被 registry
    发现面消费；``version`` 可为 None——发现面回退 ``"0.0.0"``）。"""

    def __init__(self, name: str, version: str | None) -> None:
        self.name = name
        self.version = version


class FakeEntryPoint:
    """entry-point 对象假件（仅 ``name`` / ``value`` / ``distribution`` 属性
    被 registry 发现面消费；``distribution`` 可为 None）。"""

    def __init__(
        self,
        name: str,
        value: str,
        distribution: FakeDistribution | None = None,
    ) -> None:
        self.name = name
        self.value = value
        self.distribution = distribution


def make_manifest_dict(**overrides: Any) -> dict[str, Any]:
    """最小合法 plugin manifest dict（overrides 可替换任意
    字段）。"""
    data: dict[str, Any] = {
        "id": "infection",
        "version": "1.0",
        "entrypoint": "my_game.systems.infection:InfectionSystem",
    }
    data.update(overrides)
    return data
