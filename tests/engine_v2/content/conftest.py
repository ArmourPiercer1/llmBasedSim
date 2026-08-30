"""P5-T02b / P5-T03（W2）共享 fixture + 构造器 helper（设计文档 §3.2 / §3.3 / §3.5 L364）。

- ``seeded_rng`` fixture：零参工厂函数，每次调用 = 新确定性实例（默认种子 0，
  支持显式种子参数）；实例类 :class:`SeededRng` 实现 DslRng 协议三方法口径
  （``rand()`` → [0,1) float；``uniform(lo, hi)`` → float；``randint(lo, hi)``
  → 闭区间 int），底层 stdlib ``random.Random``（测试代码允许 import random，
  src 不允许，D-P5-15）；W4 将把其实例注入 rule_module 的 DslRng 型参；
- ``zero_python_project`` / ``broken_project`` / ``plugin_project`` fixture：
  返回 W6 交付物目录的 ``Path`` 常量（相对仓库根解析）；这 3 个目录 W2 期
  不存在——W2 测试不消费、不 asserting 其存在；
- 模块级构造器 helper（**非 fixture**）：``make_*`` 族 + ``make_raw_project`` /
  ``make_ir`` / ``make_diagnostic``；W4 / W6 经
  ``from tests.engine_v2.content.conftest import 名`` 复用。
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any

import pytest

from src.engine_v2.content.schemas import (
    ActionSpec,
    AuthorityPolicy,
    CharacterSpec,
    ComponentField,
    ComponentSchema,
    ComponentType,
    Diagnostic,
    GameplayModeSpec,
    InferenceCapabilityProfile,
    LocationSpec,
    ModuleGraphNode,
    ObjectSpec,
    PlayerSpec,
    PluginDescriptor,
    ProjectIR,
    ProjectManifest,
    PromptPolicy,
    RawProject,
    RuleSpec,
    ScenarioSpec,
    ScenarioTime,
    WorldSpec,
)

__all__ = [
    "SeededRng",
    "seeded_rng",
    "zero_python_project",
    "broken_project",
    "plugin_project",
    "make_diagnostic",
    "make_manifest",
    "make_scenario",
    "make_player",
    "make_location",
    "make_world",
    "make_item",
    "make_character",
    "make_rule_spec",
    "make_action_spec",
    "make_component_schema",
    "make_authority_policy",
    "make_module_node",
    "make_gameplay_mode",
    "make_capability",
    "make_prompt_policy",
    "make_plugin_descriptor",
    "make_raw_project",
    "make_ir",
]

#: 仓库根（本文件位于 tests/engine_v2/content/ 下，上溯 3 级）。
_REPO_ROOT: Path = Path(__file__).resolve().parents[3]


class SeededRng:
    """确定性随机源（仅测试侧使用；W4 注入 rule_module 的 DslRng 型参）。

    实现 DslRng 协议三方法口径（设计文档 §3.5 L364）：

    - ``rand()`` → [0, 1) float；
    - ``uniform(lo, hi)`` → float；
    - ``randint(lo, hi)`` → 闭区间 int。

    底层 stdlib ``random.Random``（测试代码允许 import random，src 不允许，
    D-P5-15 确定性纪律的测试侧注脚）。普通类：方法签名与 Protocol 一致即可，
    实例可直接注入 DslRng 型参（结构化子类型）。
    """

    def __init__(self, seed: int = 0) -> None:
        self._random = random.Random(seed)

    def rand(self) -> float:
        return self._random.random()

    def uniform(self, lo: float, hi: float) -> float:
        return self._random.uniform(lo, hi)

    def randint(self, lo: int, hi: int) -> int:
        return self._random.randint(lo, hi)


@pytest.fixture
def seeded_rng():
    """零参工厂函数（Leader 预裁定 W2-A5）：每次调用 = 新确定性实例，默认种子 0，
    支持显式种子参数。"""

    def _factory(seed: int = 0) -> SeededRng:
        return SeededRng(seed)

    return _factory


@pytest.fixture
def zero_python_project() -> Path:
    """W6 交付物目录常量（相对仓库根解析；W2 期不存在，测试不消费不 asserting）。"""
    return _REPO_ROOT / "tests" / "fixtures" / "v2_project_zero_python"


@pytest.fixture
def broken_project() -> Path:
    """W6 交付物目录常量（相对仓库根解析；W2 期不存在，测试不消费不 asserting）。"""
    return _REPO_ROOT / "tests" / "fixtures" / "v2_project_broken"


@pytest.fixture
def plugin_project() -> Path:
    """W6 交付物目录常量（相对仓库根解析；W2 期不存在，测试不消费不 asserting）。"""
    return _REPO_ROOT / "tests" / "fixtures" / "v2_plugin_local"


# —— 构造器 helper（模块级函数，非 fixture；W4 / W6 复用）——


def make_diagnostic(
    code: str,
    path: str,
    message: str,
    refs: tuple[str, ...] = (),
    severity: str = "error",
) -> Diagnostic:
    """Diagnostic 构造器（测试断言以 (code, path, refs) 三元组为主，message 为
    实现侧确定性文本，不逐字锁定）。"""
    return Diagnostic(code=code, severity=severity, path=path, message=message, refs=refs)


def make_manifest(**overrides: Any) -> ProjectManifest:
    """ProjectManifest 构造器（默认 = 最小合法面）。"""
    kwargs: dict[str, Any] = {"schema_version": "2", "project_id": "proj_g1", "name": "V2 Project"}
    kwargs.update(overrides)
    return ProjectManifest(**kwargs)


def make_scenario(**overrides: Any) -> ScenarioSpec:
    """ScenarioSpec 构造器（默认 = 最小合法面）。"""
    kwargs: dict[str, Any] = {
        "id": "scenario_main",
        "max_ticks": 20,
        "ticks_per_game_minute": 1.0,
        "game_time": ScenarioTime(hour=9, minute=30),
    }
    kwargs.update(overrides)
    return ScenarioSpec(**kwargs)


def make_player(**overrides: Any) -> PlayerSpec:
    """PlayerSpec 构造器（默认 = 最小合法面）。"""
    kwargs: dict[str, Any] = {"player_id": "player_1", "name": "Wanderer"}
    kwargs.update(overrides)
    return PlayerSpec(**kwargs)


def make_location(**overrides: Any) -> LocationSpec:
    """LocationSpec 构造器（默认 = 最小合法面）。"""
    kwargs: dict[str, Any] = {"id": "loc_one", "name": "Location"}
    kwargs.update(overrides)
    return LocationSpec(**kwargs)


def make_world(**overrides: Any) -> WorldSpec:
    """WorldSpec 构造器（默认 = 最小合法面）。"""
    kwargs: dict[str, Any] = {"name": "World"}
    kwargs.update(overrides)
    return WorldSpec(**kwargs)


def make_item(**overrides: Any) -> ObjectSpec:
    """ObjectSpec 构造器（默认 = 最小合法面）。"""
    kwargs: dict[str, Any] = {"id": "item_one", "name": "Item"}
    kwargs.update(overrides)
    return ObjectSpec(**kwargs)


def make_character(**overrides: Any) -> CharacterSpec:
    """CharacterSpec 构造器（默认 = 最小合法面）。"""
    kwargs: dict[str, Any] = {"id": "npc_one", "name": "NPC"}
    kwargs.update(overrides)
    return CharacterSpec(**kwargs)


def make_rule_spec(**overrides: Any) -> RuleSpec:
    """RuleSpec 构造器（默认 = 最小合法面；W4 / W6 规则 DSL 面复用）。"""
    kwargs: dict[str, Any] = {"id": "rule_one"}
    kwargs.update(overrides)
    return RuleSpec(**kwargs)


def make_action_spec(**overrides: Any) -> ActionSpec:
    """ActionSpec 构造器（默认 = 最小合法面）。"""
    kwargs: dict[str, Any] = {"id": "act_one", "name": "Act"}
    kwargs.update(overrides)
    return ActionSpec(**kwargs)


def make_component_schema(**overrides: Any) -> ComponentSchema:
    """ComponentSchema 构造器（默认 = 最小合法面：1 个 number 字段）。"""
    kwargs: dict[str, Any] = {
        "id": "world.location",
        "fields": (ComponentField(name="x", type=ComponentType.NUMBER),),
    }
    kwargs.update(overrides)
    return ComponentSchema(**kwargs)


def make_authority_policy(**overrides: Any) -> AuthorityPolicy:
    """AuthorityPolicy 构造器（默认 = 最小合法面）。"""
    kwargs: dict[str, Any] = {
        "id": "auth_one",
        "domain": "attributes.sanity",
        "owner": "core.sanity",
    }
    kwargs.update(overrides)
    return AuthorityPolicy(**kwargs)


def make_module_node(**overrides: Any) -> ModuleGraphNode:
    """ModuleGraphNode 构造器（默认 = 最小合法面）。"""
    kwargs: dict[str, Any] = {"id": "core.module", "version": "1.0.0"}
    kwargs.update(overrides)
    return ModuleGraphNode(**kwargs)


def make_gameplay_mode(**overrides: Any) -> GameplayModeSpec:
    """GameplayModeSpec 构造器（默认 = 最小合法面）。"""
    kwargs: dict[str, Any] = {"id": "mode_one", "mode_type": "survival"}
    kwargs.update(overrides)
    return GameplayModeSpec(**kwargs)


def make_capability(**overrides: Any) -> InferenceCapabilityProfile:
    """InferenceCapabilityProfile 构造器（默认 = 最小合法面；字段封闭，K8 面）。"""
    kwargs: dict[str, Any] = {"id": "cap_one", "capability": "structured_output"}
    kwargs.update(overrides)
    return InferenceCapabilityProfile(**kwargs)


def make_prompt_policy(**overrides: Any) -> PromptPolicy:
    """PromptPolicy 构造器（默认 = 最小合法面；字段封闭，K4 面）。"""
    kwargs: dict[str, Any] = {
        "id": "prompt_one",
        "scope": "narration",
        "template_ref": "prompts/narrate.yaml",
    }
    kwargs.update(overrides)
    return PromptPolicy(**kwargs)


def make_plugin_descriptor(**overrides: Any) -> PluginDescriptor:
    """PluginDescriptor 构造器（默认 = 最小合法面）。"""
    kwargs: dict[str, Any] = {"id": "plugin_one", "source": "local"}
    kwargs.update(overrides)
    return PluginDescriptor(**kwargs)


def make_raw_project(
    files: dict[str, Any],
    texts: dict[str, str] | None = None,
    root: str = "/proj",
    pyproject_present: bool = False,
    pyproject_text: str | None = None,
    plugins_dir_present: bool = False,
) -> RawProject:
    """RawProject 构造器（内存，全 hermetic）；``texts`` 缺省 = 各键空串。"""
    return RawProject(
        root=root,
        files=files,
        texts=dict.fromkeys(files, "") if texts is None else texts,
        pyproject_present=pyproject_present,
        pyproject_text=pyproject_text,
        plugins_dir_present=plugins_dir_present,
    )


def make_ir(**overrides: Any) -> ProjectIR:
    """ProjectIR 构造器（默认 = 最小必需面：manifest / scenario / player，
    world = None，12 个元组字段全空；overrides 可覆盖任意 16 字段）。"""
    kwargs: dict[str, Any] = {
        "manifest": make_manifest(),
        "scenario": make_scenario(),
        "world": None,
        "player": make_player(),
        "items": (),
        "characters": (),
        "component_schemas": (),
        "actions": (),
        "rules": (),
        "authority": (),
        "modules": (),
        "gameplay_modes": (),
        "capabilities": (),
        "prompts": (),
        "plugin_descriptors": (),
        "scenarios": (),
    }
    kwargs.update(overrides)
    return ProjectIR(**kwargs)
