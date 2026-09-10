"""0.1.0-alpha.1 发布前修复 P0-A：executor 只读门面机械探针。

审计《0.1.0-alpha.1 发布前修复 — LLM-native Playability Closure》§P0-A：
production 执行器面必须经 :func:`~src.engine_v2.core.reducer.guard` 深冻结
门面（K2 机械闭合）——裸 :class:`WorldState` 不入 executor，容器级原地
修改物理不可达。本测试以**探针执行器**（替换 ``WorldInstance.executors``
表项——测试面合法 seam，engine.py 装配面不改动）实证三件事：

1. 执行器收到的 ``world`` 是 ``GuardedWorldState`` 门面（类型名断言）；
2. 容器级写尝试（``world_variables`` 赋值 / 组件嵌套赋值）在门面下
   抛 ``TypeError``（探针捕获并回传失败面——pipeline 将其转写为 action
   failure 诊断，零世界变更）；
3. 权威状态零污染：probe 后权威世界与提交前 ``dump_json`` 字节相等、
   revision 不变、无 ``__probe__`` 键渗入。
"""

from __future__ import annotations

from pathlib import Path

from src.engine_v2.core.serialization import dump_json
from src.engine_v2.modules.actions import ExecutorResult
from src.engine_v2.runtime import assemble_project

REPO_ROOT = Path(__file__).resolve().parents[3]
ALPHA_ROOT = REPO_ROOT / "tests" / "fixtures" / "alpha_contract"

PLAYER = "ent_authoring_operator"
GAUGE = "ent_authoring_gauge"


class _ProbeExecutor:
    """探针执行器：记录门面类型 + 尝试两处容器级写（预期 TypeError）。"""

    def __init__(self) -> None:
        self.outcome: str | None = None

    def execute(self, proposal, world, tick) -> ExecutorResult:
        observed = type(world).__name__
        try:
            world.world_variables["__probe__"] = True
            var_result = "MUTATED"
        except TypeError:
            var_result = "TypeError"
        except Exception as exc:  # 门面语义面外的异常原样记录（不吞）
            var_result = f"other:{type(exc).__name__}"
        try:
            world.entities[GAUGE].components["item"]["__probe__"] = 1
            comp_result = "MUTATED"
        except TypeError:
            comp_result = "TypeError"
        except Exception as exc:
            comp_result = f"other:{type(exc).__name__}"
        self.outcome = f"{observed}|{var_result}|{comp_result}"
        return ExecutorResult(committed=(), failure=f"probe:{self.outcome}", duration_ticks=0)


def _assemble_and_probe():
    result = assemble_project(str(ALPHA_ROOT), trust_python=True)
    assert result.engine is not None
    inst = result.instance
    probe = _ProbeExecutor()
    inst.executors["adjust_reading"] = probe
    before = dump_json(inst.world)
    before_revision = int(inst.world.world_revision)
    step = result.engine.submit_action(PLAYER, "adjust_reading", {})
    return result.engine, inst, probe, before, before_revision, step


def test_p0a_executor_receives_guard_facade():
    """执行器面 = GuardedWorldState；容器级写在门面下物理不可达。"""
    _engine, _inst, probe, _before, _rev, step = _assemble_and_probe()
    # 探针的写尝试被门面拒绝（action 经 failure 面显式返回，不静默）
    assert step.ok is False
    assert probe.outcome == "GuardedWorldState|TypeError|TypeError", probe.outcome
    # failure 面进入诊断通道（显式，不静默）
    assert any("GuardedWorldState" in d and "TypeError" in d for d in step.diagnostics), (
        step.diagnostics
    )


def test_p0a_authoritative_state_unpolluted():
    """probe 后权威世界零污染：dump 字节相等 + revision 不变 + 无键渗入。"""
    engine, inst, _probe, before, before_revision, _step = _assemble_and_probe()
    after = dump_json(engine.instance.world)
    assert after == before
    assert int(inst.world.world_revision) == before_revision
    assert "__probe__" not in inst.world.world_variables
    assert "__probe__" not in inst.world.entities[GAUGE].components["item"]
