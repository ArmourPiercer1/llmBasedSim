"""P9 W7 模块门面测试（SOT §6.1 / §8.2；7 函数平铺）。

门面判据 = SOT §5.2 A21 + §3.1.2（模块身份面）：

- t1 身份在场：13 官方模块 ``IDENTITY`` 常量在场且 = base
  ``OFFICIAL_MODULE_IDS`` 序逐字（module_id / version / requires 三面）；
- t2 id 闭集：13 个 IDENTITY.module_id 集合 = OFFICIAL_MODULE_IDS（零缺
  零多）+ 文法面（parse_module_id 逐字通过）；
- t3 版本文法：全版本满足 P5 版本文法锚（``^\\d+(\\.\\d+)*$``，
  schemas.py:83 _VERSION_PATTERN 同源正则）且 = OFFICIAL_MODULE_VERSION；
- t4 requires 无环：13 节点 × requires 边 → P5 冻结面
  ``module_graph.find_cycles``（:296）零 SCC（别名点分映射面 + 合成环
  阳性对照钉检测器活性）；
- t5 导出台账：15 文件 ``__all__`` == §8.2 P9_EXPORT_LEDGER（71 名，逐字
  按序）；
- t6 源码树白名单：src/engine_v2/modules/ 文件集 = 15 模块 + 占位
  __init__（§2.9 字节冻结归锚文件面）；scripts/v2_migrate_v1.py 在场；
- t7 无推理名：15 P9 src 文件字符串字面量域（ast.Constant str 含
  docstring；casefold + 词边界）K8 12 名闭集零命中（锚文件方法 3 同
  口径；拼接探针构造自豁免 + ERR-P7-14 自检 + 负例锚）。

纪律：词边界转义经 ``chr(92) + "b"`` 运行时构造（本文件零裸 0x5C 0x62，
D3 同源纪律）。
"""

from __future__ import annotations

import ast
import importlib
import re
from pathlib import Path

from src.engine_v2.content.module_graph import (
    ModuleEdge,
    ModuleGraph,
    RequirementKind,
    find_cycles,
)
from src.engine_v2.content.schemas import ModuleGraphNode
from src.engine_v2.modules import base

_REPO_ROOT = Path(__file__).resolve().parents[3]
_MODULES_DIR = _REPO_ROOT / "src" / "engine_v2" / "modules"

#: 13 官方模块 stem（= 文件名；与 OFFICIAL_MODULE_IDS 尾段一一对应）。
_MODULE_STEMS: tuple[str, ...] = (
    "attributes",
    "inventory",
    "character",
    "knowledge",
    "perception",
    "relationships",
    "space",
    "actions",
    "scenario",
    "dialogue",
    "tactical",
    "dynamics",
    "narration",
)

#: §8.2 P9_EXPORT_LEDGER（15 文件 71 名；__all__ 逐字按序）。
_EXPORT_LEDGER: dict[str, tuple[str, ...]] = {
    "base": (
        "ModuleIdentity",
        "OFFICIAL_MODULE_IDS",
        "OFFICIAL_MODULE_VERSION",
        "parse_module_id",
        "UnknownModuleIdError",
    ),
    "attributes": (
        "AttributeField",
        "AttributeEvent",
        "LockedAttributeError",
        "clamp_value",
        "apply_delta",
        "apply_new_value",
        "compute_natural_deltas",
        "evaluate_lock_condition",
        "take_attribute_snapshot",
        "summarize_attributes_for_prompt",
        "derive_attributes",
    ),
    "inventory": (
        "ItemState",
        "CarryLimit",
        "CarryCheck",
        "can_carry",
        "apply_pickup",
        "apply_drop",
        "item_summary",
    ),
    "relationships": (
        "RelationshipState",
        "RelationshipEvent",
        "init_relationships",
        "adjust_relationship",
        "relationship_summary",
    ),
    "character": (
        "CharacterRecord",
        "PolicyPromptContext",
        "NpcBehaviorPolicy",
        "build_character_record",
        "build_npc_policy",
    ),
    "perception": (
        "PerceptionRange",
        "ObservationSource",
        "PerceptionResult",
        "build_observations",
    ),
    "knowledge": (
        "BeliefEvent",
        "apply_observations",
        "memory_append",
        "knowledge_summary",
    ),
    "scenario": (
        "ScenarioTrigger",
        "TriggerFiring",
        "check_triggers",
    ),
    "actions": (
        "STANDARD_ACTION_IDS",
        "ActionExecutor",
        "ExecutorResult",
        "MoveExecutor",
        "register_standard_actions",
    ),
    "dialogue": (
        "DialogueResult",
        "dialogue_relationship_delta",
        "run_dialogue",
    ),
    "space": (
        "HexGrid",
        "hex_adjacency",
        "distance_between",
        "register_standard_space",
    ),
    "tactical": (
        "TACTICAL_ACTION_IDS",
        "TacticalOverlaySpec",
        "build_tactical_overlay",
        "TacticalModePolicy",
    ),
    "dynamics": (
        "DynamicsBinding",
        "build_standard_dynamics",
    ),
    "narration": (
        "NarrativeFrame",
        "NarrativeStyle",
        "NarrativeView",
        "render_narrative_view",
    ),
    "v1_migration": (
        "MIGRATION_DIAGNOSTIC_CODES",
        "MigrationDiagnostic",
        "MigrationReport",
        "migrate_project",
        "migrate_simulation",
    ),
}

#: K8 12 名闭集（锚文件 P4_LLM_PROVIDER_BLACKLIST L225–240 同源值镜像；
#: 本文件拼接构造自豁免——锚文件方法 3 同构）。
_K8_JOINED: tuple[str, ...] = (
    "open" + "ai",
    "anthr" + "opic",
    "lang" + "chain",
    "lite" + "llm",
    "oll" + "ama",
    "gem" + "ini",
    "g" + "pt",
    "cla" + "ude",
    "l" + "lm",
    "prov" + "ider",
    "api_" + "key",
    "base_" + "url",
)

#: 词边界转义运行时构造（本文件零裸 0x5C 0x62，D3 纪律）。
_WB = chr(92) + "b"

#: P5 版本文法锚（content/schemas.py:83 _VERSION_PATTERN：对端带前导
# ^、本常量无——fullmatch 语义下等价，文本非同文，R3 注释修正）。
_VERSION_RE = re.compile(r"\d+(\.\d+)*$")


def _load(stem: str):
    return importlib.import_module("src.engine_v2.modules." + stem)


def _alias(module_id: str) -> str:
    """官方 id → P5 点分词法别名（_MODULE_ID_PATTERN 兼容；双射保环）。"""
    return "std." + module_id.removeprefix("llmsim-standard-")


def test_t1_identities_present() -> None:
    """t1（A21 邻面）：13 IDENTITY 在场且逐字 = base OFFICIAL_MODULE_IDS
    序（module_id / version / requires 三面；requires 钉 = SOT §3.1.2
    MODULE_REQUIRES 表实测值）。"""
    assert len(base.OFFICIAL_MODULE_IDS) == 13
    expected_requires: dict[str, tuple[str, ...]] = {
        "llmsim-standard-attributes": (),
        "llmsim-standard-inventory": ("llmsim-standard-attributes",),
        "llmsim-standard-character": ("llmsim-standard-attributes",),
        "llmsim-standard-knowledge": ("llmsim-standard-perception",),
        "llmsim-standard-perception": ("llmsim-standard-space",),
        "llmsim-standard-relationships": (),
        "llmsim-standard-space": (),
        "llmsim-standard-actions": (
            "llmsim-standard-space",
            "llmsim-standard-inventory",
        ),
        "llmsim-standard-scenario": ("llmsim-standard-actions",),
        "llmsim-standard-dialogue": (
            "llmsim-standard-character",
            "llmsim-standard-relationships",
        ),
        "llmsim-standard-tactical": (
            "llmsim-standard-actions",
            "llmsim-standard-space",
        ),
        "llmsim-standard-dynamics": (),
        "llmsim-standard-narration": (),
    }
    for module_id in base.OFFICIAL_MODULE_IDS:
        stem = module_id.removeprefix("llmsim-standard-")
        module = _load(stem)
        identity = getattr(module, "IDENTITY", None)
        assert isinstance(identity, base.ModuleIdentity), f"{stem} IDENTITY 缺席"
        assert identity.module_id == module_id
        assert identity.version == base.OFFICIAL_MODULE_VERSION
        assert identity.requires == expected_requires[module_id]


def test_t2_ids_closed() -> None:
    """t2：13 IDENTITY.module_id 集合 = OFFICIAL_MODULE_IDS（零缺零多）+
    文法面（parse_module_id 逐字通过；UnknownModuleIdError 负例钉）。"""
    actual = tuple(
        _load(stem).IDENTITY.module_id for stem in _MODULE_STEMS
    )
    assert len(actual) == 13
    assert set(actual) == set(base.OFFICIAL_MODULE_IDS)
    # 序钉（R2 F4-1 补充）：_MODULE_STEMS 按 Spec §40 逐字序排定 →
    # IDENTITY 序 == OFFICIAL_MODULE_IDS 序（重排 13 名元组 = 红）。
    assert actual == base.OFFICIAL_MODULE_IDS, (
        f"IDENTITY 序 ≠ OFFICIAL_MODULE_IDS 序（Spec §40 逐字序面）: {actual}"
    )
    assert len(set(actual)) == 13, "IDENTITY 重复 id"
    for module_id in base.OFFICIAL_MODULE_IDS:
        assert base.parse_module_id(module_id) == module_id
    for bad in (
        "LLMSIM-STANDARD-attributes",  # 大写拒（AD-P9-3 例 1）
        "llmsim-standard-",  # 空尾拒（AD-P9-3 例 2）
        "standard-x",  # 前缀缺拒（AD-P9-3 例 3；R1 S-2 补充钉）
        "",  # 空串拒（加强钉）
    ):
        try:
            base.parse_module_id(bad)
        except base.UnknownModuleIdError:
            pass
        else:
            raise AssertionError(f"负例应拒: {bad!r}")


def test_t3_version_grammar() -> None:
    """t3：全版本满足 P5 版本文法锚（点分数字串 1+ 分量）且 = "1"
    （OFFICIAL_MODULE_VERSION 统一初始版本面）。"""
    for stem in _MODULE_STEMS:
        version = _load(stem).IDENTITY.version
        assert _VERSION_RE.fullmatch(version), f"{stem} 版本文法违例: {version!r}"
        assert version == "1"
    assert base.OFFICIAL_MODULE_VERSION == "1"
    assert _VERSION_RE.fullmatch(base.OFFICIAL_MODULE_VERSION)


def test_t4_requires_acyclic() -> None:
    """t4：requires 依赖图无环（P5 冻结面 find_cycles 零 SCC）；别名点
    分映射（llmsim-standard-X → std.X，_MODULE_ID_PATTERN 兼容，双射
    保环性）；阳性对照 = 合成 fa→fb→fa 双环 → 检测器非空（活性钉，
    零空转）。"""
    identities = {
        _load(stem).IDENTITY.module_id: _load(stem).IDENTITY
        for stem in _MODULE_STEMS
    }
    nodes = {
        _alias(module_id): ModuleGraphNode(
            id=_alias(module_id),
            version=identity.version,
            requires=tuple(_alias(req) for req in identity.requires),
        )
        for module_id, identity in identities.items()
    }
    edges = tuple(
        ModuleEdge(
            source=_alias(module_id),
            target=_alias(req),
            kind=RequirementKind.REQUIRED,
        )
        for module_id in sorted(identities, key=lambda m: m.casefold())
        for req in identities[module_id].requires
    )
    graph = ModuleGraph(nodes=nodes, edges=edges)
    assert find_cycles(graph) == [], "requires 依赖图存在环（P9 必须 DAG）"
    # 阳性对照：fa→fb→fa 合成环（检测器活性钉）：
    cycle_nodes = dict(nodes)
    cycle_nodes["std.fa"] = ModuleGraphNode(id="std.fa", version="1", requires=("std.fb",))
    cycle_nodes["std.fb"] = ModuleGraphNode(id="std.fb", version="1", requires=("std.fa",))
    cycle_edges = tuple(edges) + (
        ModuleEdge(source="std.fa", target="std.fb", kind=RequirementKind.REQUIRED),
        ModuleEdge(source="std.fb", target="std.fa", kind=RequirementKind.REQUIRED),
    )
    assert find_cycles(ModuleGraph(nodes=cycle_nodes, edges=cycle_edges)) != []


def test_t5_export_ledger() -> None:
    """t5（A21）：15 文件 ``__all__`` == §8.2 台账（71 名；逐字按序双
    等 + 计数恒等 5+11+7+5+5+4+4+3+5+3+4+4+2+4+5 = 71）。"""
    total = 0
    for stem in ("base", *_MODULE_STEMS, "v1_migration"):
        module = _load(stem)
        expected = _EXPORT_LEDGER[stem]
        assert tuple(module.__all__) == expected, (
            f"{stem} __all__ 与 §8.2 台账不符："
            f"实得 {tuple(module.__all__)}"
        )
        for name in expected:
            assert hasattr(module, name), f"{stem}.{name} 缺席"
        total += len(expected)
    assert total == 71
    assert sum(len(v) for v in _EXPORT_LEDGER.values()) == 71


def test_t6_src_tree_whitelist() -> None:
    """t6：src/engine_v2/modules/ 文件集 = 15 模块 + 占位 __init__（共
    16）；零越白文件；scripts/v2_migrate_v1.py 在场（§3.19 行 46）。"""
    actual = {path.name for path in _MODULES_DIR.iterdir() if path.is_file()}
    expected = {"__init__.py", "base.py", "v1_migration.py"} | {
        stem + ".py" for stem in _MODULE_STEMS
    }
    assert actual == expected, f"modules/ 文件集越白：{actual ^ expected}"
    assert len(actual) == 16
    script = _REPO_ROOT / "scripts" / "v2_migrate_v1.py"
    assert script.is_file()


def test_t7_no_inference_names() -> None:
    """t7（K8 面）：15 P9 src 文件字符串字面量域（ast.Constant str 含
    docstring；casefold + 词边界）12 名闭集零命中；探针拼接构造自豁免 +
    ERR-P7-14 自检 + 负例锚（llmsim / api_key_env 不命中）；
    llmsim-standard-* 官方 id 豁免自证（词边界不命中内嵌子串）。"""
    assert len(_K8_JOINED) == 12
    for word in _K8_JOINED:
        _pat = re.compile(_WB + re.escape(word) + _WB)
        assert _pat.search(" " + word + " "), f"K8 自检失守: {word!r}"
    probe = re.compile(_WB + "(?:" + "|".join(_K8_JOINED) + ")" + _WB)
    assert not probe.search("llmsim"), "负例锚失守：llmsim 不应命中"
    assert not probe.search("api_key_env"), "负例锚失守：api_key_env 不应命中"
    assert not probe.search("llmsim-standard-dynamics"), "官方 id 豁免失守"
    hits: dict[str, list[str]] = {}
    for stem in ("base", *_MODULE_STEMS, "v1_migration"):
        path = _MODULES_DIR / (stem + ".py")
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        matched: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                text = node.value.casefold()
                matched.update(
                    word
                    for word in _K8_JOINED
                    if re.search(_WB + re.escape(word) + _WB, text)
                )
        if matched:
            hits[stem] = sorted(matched)
    assert not hits, f"P9 src 命中 K8 12 名黑名单字符串字面量域：{hits}"
