"""P10 web 层测试 fixture（SOT §6.2；4 fixture + 宿主驱动；零测试函数）。

跨波共享面（SOT §6.4）：世界 / 事件 / 脚本消费 W1
``tests/engine_v2/presentation/conftest`` 冻结 fixture（本文件 re-export，
零改零重实现）：

- ``known_event_sequence``：3 commit 世界流（revision 0→3）+ runtime
  （logical_tick 3）+ 五面 trace 记录流（W5 inspector/workbench 数据
  源）；
- ``script_backend``：FakeInferenceBackend 脚本键预置（W5 workbench
  消费面；K5 脚本面，测试侧模型名 = fake-model-1 类）；
- ``make_p10_world``：fixture 世界构造器（字面量 id，零随机零时钟）。

本文件落盘面（SOT §6.2 逐字）：

- ``driver``：TickDriver 最小宿主实现（conftest 宿主循环：逻辑刻 +1
  世界侧投影 + world_revision +1 事务 commit 面等价；生产 = P1
  runtime 面（未来），§0.4 非范围）；
- ``manager`` / ``session``：SessionManager + create_session（注入
  driver + DeterministicImageBackend；**显式 session_id**，
  DEV-P10-05 纪律：uuid4 例外纪律 = 测试零缺省依赖）；
- ``trace_manager_session``：known_event_sequence 世界 + trace_records
  注入会话（inspector/workbench 数据源，W5 面）。

纪律（D5/D6/K8）：全部 id / 面值 = 字面量（零随机、零墙钟）；12 名
闭集零命中；世界面经 in-session WorldState + 冻结 core 函数（P10-INV-5
零直读因果链 = W5 面，本 conftest 宿主驱动 = 最小相位面）。
"""

from __future__ import annotations

from typing import Final

import pytest

from src.engine_v2.adapters.web.session import SessionManager
from src.engine_v2.core.state import WorldState
from src.engine_v2.presentation.image.backend import DeterministicImageBackend
from tests.engine_v2.presentation.conftest import (
    known_event_sequence,
    make_p10_world,
    script_backend,
)

__all__ = [
    "HostTickDriver",
    "driver",
    "manager",
    "session",
    "trace_manager_session",
]

#: 会话 id 字面量（显式钉，DEV-P10-05 纪律）。
_SESSION_ID_A: Final[str] = "sess_w4_a"
_SESSION_ID_TRACE: Final[str] = "sess_w4_trace"

#: 世界侧逻辑刻键（P1 D-6 单一单调计数；W1 view.py 同词表）。
_LOGICAL_TICK_KEY: Final[str] = "logical_tick"


class HostTickDriver:
    """TickDriver conftest 最小宿主（SOT §6.2；Leader 终审 Q6 裁定：
    Protocol only + conftest 最小宿主；P9 样例宿主先例语义参照）。

    - 持有权威世界引用（``world`` 槽）：WorldState = frozen 模型，
      revision 面不可原地推进，整体替换 = 唯一合法面（core
      state.py:333–367 私有缝隙，测试侧先例 test_view_t2 /
      test_image_backend_t2 同族）；
    - ``advance`` = 一次宿主相位 = 世界侧逻辑刻 + 1（world_variables
      投影，P1 D-6）+ world_revision + 1（事务 commit 面等价，最小
      宿主面）；
    - 生产 = P1 runtime 面（未来，§0.4 非范围）；零随机 / 零墙钟
      （D6）。
    """

    def __init__(self, world: WorldState | None = None) -> None:
        self._world = world

    @property
    def world(self) -> WorldState | None:
        """权威世界槽（未绑定时 = None；会话层回落面消费）。"""
        return self._world

    def advance(self, world: WorldState) -> None:
        """一次宿主相位（逻辑刻 + 1 + revision + 1；整体替换世界槽）。"""
        tick = int(world.world_variables.get(_LOGICAL_TICK_KEY) or 0) + 1
        advanced = world._with_world_variables(
            {**dict(world.world_variables), _LOGICAL_TICK_KEY: tick}
        )
        self._world = advanced._with_world_revision(advanced.world_revision.next())


@pytest.fixture
def driver() -> HostTickDriver:
    """TickDriver 最小宿主（未绑定世界槽；会话 create 时注入）。"""
    return HostTickDriver()


@pytest.fixture
def manager() -> SessionManager:
    """SessionManager（driver / image_backend 工厂注入；测试会话 =
    create_session 显式 driver，隔离面）。"""
    return SessionManager(
        driver_factory=lambda: HostTickDriver(),
        image_backend_factory=lambda: DeterministicImageBackend(),
    )


@pytest.fixture
def session(manager: SessionManager):
    """create_session（显式 session_id，DEV-P10-05 纪律）+ driver +
    DeterministicImageBackend 注入。"""
    world = make_p10_world()
    session_id = manager.create_session(
        world,
        session_id=_SESSION_ID_A,
        driver=HostTickDriver(world),
        image_backend=DeterministicImageBackend(),
    )
    return manager.get(session_id)


@pytest.fixture
def trace_manager_session(known_event_sequence):
    """known_event_sequence 世界 + trace_records 注入会话（SOT §6.2；
    W5 inspector/workbench 数据源面）。"""
    sequence = known_event_sequence
    local_manager = SessionManager(
        driver_factory=lambda: HostTickDriver(),
        image_backend_factory=lambda: DeterministicImageBackend(),
    )
    session_id = local_manager.create_session(
        sequence.world,
        session_id=_SESSION_ID_TRACE,
        driver=HostTickDriver(sequence.world),
        trace_records=sequence.trace_records,
    )
    return local_manager.get(session_id)
