"""P7-W1 conftest（SOT §6.2 夹具面；W1–W3 消费面）。

纪律（SOT §6.2/ERR-P7-10）：

- ``_det_entity_id`` / ``make_p7_world`` / ``make_p7_component_registry`` /
  ``gem_effect_handlers`` 为模块级函数夹具（非 pytest fixture、非依赖注入，
  场景内显式调用；先例 P4 conftest ``make_p4_world`` L472）；
- ``make_p7_producer_registry`` / ``make_p7_policy`` / ``make_p7_executor``
  三件对 W4 ``authority.py`` 符号（``build_dynamics_producers`` /
  ``default_dynamics_policy``）使用**函数体内惰性 import**——W1–W3 波次禁止
  模块顶层 import ``authority.py``（W4 交付前模块不存在）；W1 测试不请求
  这三件（W4 消费面）；
- pytest fixture 面（§6.2 表）：``stim_support_removed``（单例）/
  ``p7_deployment`` / ``p7_game`` / ``scripted_wire_response``——零命名冲突
  （与既有 conftest 无重名）。

fixture 文件根 = ``tests/fixtures/``（§6.4 钉死面：``v2_deployment_p7`` /
``v2_project_p7``）。夹具只装配，不断言。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from src.engine_v2.content.loader import load_project
from src.engine_v2.core.cascade import CascadeExecutor
from src.engine_v2.core.components import (
    ComponentRegistry,
    ComponentSchema,
    ComponentTypeId,
)
from src.engine_v2.core.entity import EntityRecord
from src.engine_v2.core.effects import EntityTarget, ProposedEffect
from src.engine_v2.core.ids import EntityId
from src.engine_v2.core.reducer import EffectHandlerRegistry, default_handler_registry
from src.engine_v2.core.state import WorldState
from src.engine_v2.dynamics.backend import Stimulus
from src.engine_v2.dynamics.toy_rigid import RIGID_COMPONENT
from src.engine_v2.llm.deployment import DeploymentProfile, load_deployment

_FIXTURE_ROOT = Path(__file__).resolve().parents[3] / "tests" / "fixtures"


def _det_entity_id(name: str) -> EntityId:
    """确定性实体 ID（SOT §5.1/§6.2）：``"ent_" + sha256(name)[:32]``。"""
    return EntityId("ent_" + hashlib.sha256(name.encode()).hexdigest()[:32])


def make_p7_world() -> WorldState:
    """§5.1 世界夹具（S1–S8 共用）：gem 实体 + world_variables。

    - 实体 ``gem``（``_det_entity_id("gem")``）：组件 ``rigid`` =
      ``{"pos": 0.0, "vel": 0.0, "acc": 0.0}``；``gem_state`` =
      ``{"moved": False}``；
    - world_variables：``{"gravity": 9.8, "support": "present"}``。
    """
    gem = _det_entity_id("gem")
    return WorldState(
        entities={
            gem: EntityRecord(
                entity_id=gem,
                components={
                    RIGID_COMPONENT: {"pos": 0.0, "vel": 0.0, "acc": 0.0},
                    ComponentTypeId("gem_state"): {"moved": False},
                },
            ),
        },
        world_variables={"gravity": 9.8, "support": "present"},
    )


def make_p7_component_registry() -> ComponentRegistry:
    """测试侧 ComponentRegistry（§5.1 组件注册钉死面）。

    ``rigid`` schema ``{pos:number, vel:number, acc:number}``；``gem_state``
    schema ``{moved:boolean}``（描述性口径；payload_model=None = 不透明
    JSON dict 存储，决策 D-8）。
    """
    registry = ComponentRegistry()
    registry.register(
        ComponentSchema(
            component_type=RIGID_COMPONENT,
            description="rigid {pos:number, vel:number, acc:number}",
        )
    )
    registry.register(
        ComponentSchema(
            component_type=ComponentTypeId("gem_state"),
            description="gem_state {moved:boolean}",
        )
    )
    return registry


def _set_gem_moved(state: WorldState, effect: ProposedEffect) -> WorldState:
    """语义 handler 钉死落点：对目标实体 set ``gem_state`` ``{"moved": True}``。

    handler = 纯函数（reducer.py L609 签名 ``(WorldState, ProposedEffect) ->
    WorldState``）；``_with_components`` 为 EntityRecord 唯一变更缝隙
    （entity.py 文档明示"供测试与未来 P2 reducer 使用"）。
    """
    target = effect.target
    if not isinstance(target, EntityTarget) or target.entity_id is None:
        return state
    record = state.entities.get(target.entity_id)
    if record is None:
        return state
    components = dict(record.components)
    components[ComponentTypeId("gem_state")] = {"moved": True}
    return state.model_copy(
        update={
            "entities": {
                **state.entities,
                target.entity_id: record._with_components(components),
            }
        }
    )


def gem_effect_handlers() -> EffectHandlerRegistry:
    """注册语义 handler（测试侧，D-P7-13）：default + 语义扩展。

    **钉死**：``gem.moved`` → set gem_state {moved:true}；``gem.fell`` →
    set gem_state {moved:true}——两 handler 同落点，区分靠 effect_type
    溯源（Case B 中 ``gem.fell`` 被 REJECT 时其 handler 永不执行——A9 断言
    moved 仍为 False 的正反面由此成立）。
    """
    registry = default_handler_registry()
    registry.register("gem.moved", _set_gem_moved)
    registry.register("gem.fell", _set_gem_moved)
    return registry


def make_p7_producer_registry() -> Any:
    """W4 消费面：``build_dynamics_producers()``（§3.7 缺省 priority）。

    函数体内惰性 import（ERR-P7-10）；W1–W3 测试不请求本夹具。
    """
    from src.engine_v2.dynamics.authority import build_dynamics_producers

    return build_dynamics_producers()


def make_p7_policy() -> Any:
    """W4 消费面：``default_dynamics_policy(component_types=("rigid", "gem_state"))``。

    函数体内惰性 import（ERR-P7-10）；W1–W3 测试不请求本夹具。
    """
    from src.engine_v2.dynamics.authority import default_dynamics_policy

    return default_dynamics_policy(component_types=("rigid", "gem_state"))


def make_p7_executor() -> Any:
    """W4 消费面：CascadeExecutor 全装配（SOT §6.2 逐参钉死）。

    ``policy=make_p7_policy()`` / ``component_registry=make_p7_component_
    registry()`` / ``producer_registry=make_p7_producer_registry()`` /
    ``handlers=<default_handler_registry() + gem_effect_handlers()>``。
    函数体内惰性 import（ERR-P7-10）；W1–W3 测试不请求本夹具。
    """
    return CascadeExecutor(
        policy=make_p7_policy(),
        component_registry=make_p7_component_registry(),
        producer_registry=make_p7_producer_registry(),
        handlers=gem_effect_handlers(),
    )


@pytest.fixture(scope="session")
def stim_support_removed() -> Stimulus:
    """§5.1 刺激常量（单例；anvil 场景"支撑被移除"= external 刺激）。"""
    return Stimulus(
        stimulus_id="stim_support_removed",
        kind="external",
        source="anvil",
        entity_id=_det_entity_id("gem"),
        payload={"support": "removed"},
    )


@pytest.fixture
def p7_deployment() -> DeploymentProfile:
    """tests/fixtures/v2_deployment_p7/deployment.yaml 装载结果（SOT §6.2）。

    钉死形状（§6.4）：models model_high(tier 3)/model_alt(tier 2)；
    inference_profiles.world_dynamics → model_high。
    """
    result = load_deployment(_FIXTURE_ROOT / "v2_deployment_p7" / "deployment.yaml")
    assert result.profile is not None, f"deployment 装载失败：{result.diagnostics}"
    return result.profile


@pytest.fixture
def p7_game() -> object:
    """tests/fixtures/v2_project_p7/game.yaml 装载结果（SOT §6.2，validate 零诊断）。"""
    result = load_project(_FIXTURE_ROOT / "v2_project_p7")
    assert result.diagnostics == (), f"project 装载带诊断：{result.diagnostics}"
    return result


@pytest.fixture
def scripted_wire_response() -> str:
    """§5.1 S3 wire JSON 串（scripted fake 脚本首答；``<gem>`` 已代入）。"""
    wire = {
        "effects": [
            {
                "effect_type": "gem.moved",
                "entity_id": str(_det_entity_id("gem")),
                "payload": {},
            }
        ],
        "reasoning": "support removed",
    }
    return json.dumps(wire, ensure_ascii=False, separators=(",", ":"))
