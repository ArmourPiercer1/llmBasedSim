"""runtime 层：production game path 装配与运行（12h closure，2026-09-04）。

GameProject → WorldInstance → EngineInstance 的生产组合面。模块台账
（导出 = 本文件）见 `README.md`；单入口 = :func:`assemble_project`。

导入纪律：本包零 tests.* import、零第三方依赖、零新框架（contract §0）。
"""

from src.engine_v2.runtime.action_binding import ActionBindingResult, bind_actions
from src.engine_v2.runtime.assembly import AssemblyResult, assemble_project
from src.engine_v2.runtime.context import (
    build_actor_context,
    build_actor_context_for_wakeup,
)
from src.engine_v2.runtime.dynamics_binding import DynamicsBindingResult, bind_dynamics
from src.engine_v2.runtime.engine import EngineInstance, StepResult
from src.engine_v2.runtime.extensions import (
    ExtensionBundle,
    ExtensionContext,
    ExtensionLoadResult,
    ProducerGrant,
    load_extensions,
)
from src.engine_v2.runtime.llm_binding import LLMBindingResult, bind_llm_policies
from src.engine_v2.runtime.materialize import (
    CHARACTER_PROFILE_COMPONENT,
    WorldMaterialization,
    materialize_world,
)
from src.engine_v2.runtime.observability import (
    InMemoryTraceSink,
    RuntimeTraceSink,
    TraceEvent,
)
from src.engine_v2.runtime.world_instance import WorldInstance

__all__ = [
    "ActionBindingResult",
    "AssemblyResult",
    "CHARACTER_PROFILE_COMPONENT",
    "DynamicsBindingResult",
    "EngineInstance",
    "ExtensionBundle",
    "ExtensionContext",
    "ExtensionLoadResult",
    "InMemoryTraceSink",
    "LLMBindingResult",
    "ProducerGrant",
    "RuntimeTraceSink",
    "StepResult",
    "TraceEvent",
    "WorldInstance",
    "WorldMaterialization",
    "assemble_project",
    "bind_actions",
    "bind_dynamics",
    "bind_llm_policies",
    "build_actor_context",
    "build_actor_context_for_wakeup",
    "load_extensions",
    "materialize_world",
]
