"""WorldInstance——authoritative runtime state + 已装配 runtime dependencies。

Runtime Closure 冻结 seam（contract §1，Leader-owned）：字段集逐字冻结，
T1 materialize / T2 engine / T4 context / T5 llm_binding / T9 assembly 全
部以本文件为唯一 import 面（``from src.engine_v2.runtime.world_instance import
WorldInstance``）。修改本文件 = Leader 专属（hot file 纪律）。

职责固定：authoritative runtime state + 已装配 runtime dependencies。
本 dataclass 无行为（零方法面；引擎行为 = ``runtime.engine.EngineInstance``）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # 仅类型引用（PEP 563：零运行时依赖，T8 模块就位前可 import）
    from src.engine_v2.content.schemas import ProjectIR
    from src.engine_v2.core.action_registry import ActionRegistry
    from src.engine_v2.core.authority import AuthorityPolicy, ProducerRegistry
    from src.engine_v2.core.behavior_policy import BehaviorPolicy
    from src.engine_v2.core.components import ComponentRegistry
    from src.engine_v2.core.space import SpaceRegistry
    from src.engine_v2.core.state import RuntimeState, WorldState
    from src.engine_v2.dynamics.backend import WorldDynamicsBackend
    from src.engine_v2.modules.actions import ActionExecutor
    from src.engine_v2.runtime.observability import RuntimeTraceSink


@dataclass
class WorldInstance:
    """装配后的权威世界 + runtime 依赖闭包（contract §1 字段冻结）。

    - ``world`` / ``runtime``：authoritative state 对（K1 唯一权威表示）；
      引擎相位推进 = 字段级替换（dataclass 非 frozen；写授权纪律在
      reducer/cascade 面，不在本容器面）；
    - ``spaces`` / ``action_registry`` / ``executors`` / ``policies`` /
      ``dynamics``：已装配 runtime dependencies（executor 按 action id
      查；policy 按 actor id 查；dynamics 每 tick 全部 simulate）；
    - ``component_registry``：组件 schema 注册（reducer 结构校验面）；
    - ``producer_registry`` / ``authority_policy``：写授权闭面
      （closed-by-default；仅 T6/T7/T3 明确产出的 ProducerGrant 合并）；
    - ``trace_sink``：runtime 可观测面（T8）。

    构造点唯一 = ``runtime.assembly.assemble_project``（T9）；测试可直
    接构造最小实例（字段全必填，无默认弱化）。
    """

    world_instance_id: str
    ir: ProjectIR
    world: WorldState
    runtime: RuntimeState
    spaces: SpaceRegistry
    action_registry: ActionRegistry
    executors: dict[str, ActionExecutor]
    policies: dict[str, BehaviorPolicy]
    dynamics: tuple[WorldDynamicsBackend, ...]
    component_registry: ComponentRegistry
    producer_registry: ProducerRegistry
    authority_policy: AuthorityPolicy
    trace_sink: RuntimeTraceSink
