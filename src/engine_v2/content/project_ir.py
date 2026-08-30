"""engine_v2 content 层 P5 raw → IR 编译器 + round-trip 面（P5-T02b / W2，设计文档 §3.2）。

依据 ``docs/v2/contracts/P5-project-format-module-plugin-dsl-design.md``（下称
"设计文档"，P5-DESIGN 冻结态）§3.2 字段级规格（6 导出）：

- **定位**：raw → IR 编译器 + IR → 数据/YAML 的 round-trip 面。导入面 = stdlib
  + ``schemas`` + ``pydantic`` + ``yaml`` + ``core.serialization``（仅
  ``assert_json_clean``，K7 / P5-INV-7 尾部机械钩子）；content/* 模块间零互导
  （本模块只导 schemas）；
- **build_ir 永不 raise** 内容级异常（K2 / P5-INV-2 纯产新值）：失败 =
  (None, 诊断集)；pydantic ``ValidationError`` 按条目转写——
  ``type == "extra_forbidden"`` → ``LLMSIM_UNKNOWN_KEY``（refs = [键名，取
  error loc 末元 / ctx]），其余条目 → ``LLMSIM_SCHEMA``（refs = [loc 点分串,
  type]），每条 error 一条诊断，按 loc 序追加；
- **节文件顶层键处置**：期望键缺失 → 1 条 ``LLMSIM_SCHEMA``（refs = [期望键名,
  "missing"]）；实际顶层出现其他键 → 每键 1 条 ``LLMSIM_UNKNOWN_KEY``（refs =
  [键名]）；两族可同时出，该文件即停（不再做内层校验）；
- **D-P5-15 确定性纪律**：零非确定根源——节文件命中集 ``sorted()``、诊断按显式
  步序追加、不得以 dict/set 迭代序决定对外顺序；
- **D-P5-14 round-trip**：``ir_to_data`` = ``model_dump(mode="json")`` 嵌套展开
  + 尾部 ``assert_json_clean``；``canonical_yaml`` = ``yaml.safe_dump(
  sort_keys=True, allow_unicode=True, default_flow_style=False, width=100)``，
  纯函数，双 dump 字节稳定（断言 #20 同源）。

``__all__`` 6 名按设计文档 §8.2 导出台账逐名逐序。
"""

from __future__ import annotations

from typing import Any, Final, Iterator

import yaml
from pydantic import TypeAdapter, ValidationError

from src.engine_v2.content.schemas import (
    _ContractModel,
    ActionSpec,
    AuthorityPolicy,
    CharacterSpec,
    ComponentSchema,
    Diagnostic,
    DiagnosticSeverity,
    GameplayModeSpec,
    InferenceCapabilityProfile,
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
    WorldSpec,
)
from src.engine_v2.core.serialization import assert_json_clean

__all__ = [
    "IRBuildResult",
    "build_ir",
    "flatten_entities",
    "iter_entity_refs",
    "ir_to_data",
    "canonical_yaml",
]


# —— 节 → 类型映射（设计文档 §3.2 步 2/3 逐字；显式元组序 = 遍历序）——


#: game.yaml 顶层键封闭集（8 键，设计文档 §3.2 步 2）：(节名, 校验器)。
#: 单值节 = Spec 类；元组节 = tuple[Spec, ...]（节文件缺 = 合法空，D-P5-05）。
_GAME_SECTIONS: Final[tuple[tuple[str, TypeAdapter[Any]], ...]] = (
    ("manifest", TypeAdapter(ProjectManifest)),
    ("scenario", TypeAdapter(ScenarioSpec)),
    ("player", TypeAdapter(PlayerSpec)),
    ("component_schemas", TypeAdapter(tuple[ComponentSchema, ...])),
    ("authority", TypeAdapter(tuple[AuthorityPolicy, ...])),
    ("gameplay_modes", TypeAdapter(tuple[GameplayModeSpec, ...])),
    ("capabilities", TypeAdapter(tuple[InferenceCapabilityProfile, ...])),
    ("plugin_descriptors", TypeAdapter(tuple[PluginDescriptor, ...])),
)

#: 8 键封闭集成员面（仅成员判断，不参与排序）。
_GAME_SECTION_NAMES: Final[frozenset[str]] = frozenset(name for name, _ in _GAME_SECTIONS)

#: game.yaml 缺失即无法构造 ProjectIR 的节（ProjectIR 必需字段）。
_REQUIRED_GAME_SECTIONS: Final[tuple[str, ...]] = ("manifest", "scenario", "player")

#: 节文件面：(节名, 顶层必为键, 校验器, IR 字段名)——声明序 = 设计文档 §3.3
#: LAYOUT_OPTIONAL 模板序（world → characters → items → rules → actions →
#: prompts → scenarios → modules）。plugins/*/plugin.yaml 由 plugins 面消费，
#: build_ir 不解析（§3.2 步 3）。
_SECTION_FILES: Final[tuple[tuple[str, str, TypeAdapter[Any], str], ...]] = (
    ("world", "world", TypeAdapter(WorldSpec), "world"),
    ("characters", "characters", TypeAdapter(tuple[CharacterSpec, ...]), "characters"),
    ("items", "items", TypeAdapter(tuple[ObjectSpec, ...]), "items"),
    ("rules", "rules", TypeAdapter(tuple[RuleSpec, ...]), "rules"),
    ("actions", "actions", TypeAdapter(tuple[ActionSpec, ...]), "actions"),
    ("prompts", "prompts", TypeAdapter(tuple[PromptPolicy, ...]), "prompts"),
    ("scenarios", "scenarios", TypeAdapter(tuple[ScenarioSpec, ...]), "scenarios"),
    ("modules", "modules", TypeAdapter(tuple[ModuleGraphNode, ...]), "modules"),
)

#: world 节单值语义多余文件 refs（设计文档 §3.2 L304 逐字）。
_WORLD_EXTRA_FILE_REF: Final[str] = "world 节为单值 WorldSpec，多余文件不合并"


class IRBuildResult(_ContractModel):
    """build_ir 产物（设计文档 §3.2：frozen；``ir`` = None 即编译失败，全部
    失败信息在 ``diagnostics``；永不 raise，K2 / P5-INV-2）。"""

    ir: ProjectIR | None
    diagnostics: tuple[Diagnostic, ...]


# —— 私有工具（确定性：sorted 命中集 / 显式步序追加 / 零 dict 序外溢）——


def _section_file_keys(raw: RawProject, section: str) -> tuple[str, ...]:
    """节目录模板 ``<section>/*.yaml``（恰好一层）命中集，``sorted()`` 升序
    （D-P5-15 确定性纪律；深度封闭，与 loader LAYOUT_OPTIONAL 模板同面）。"""
    prefix = section + "/"
    return tuple(
        sorted(
            key
            for key in raw.files
            if key.count("/") == 1 and key.startswith(prefix) and key.endswith(".yaml")
        )
    )


def _diagnostic_from_error(entry: dict[str, Any], path: str) -> Diagnostic:
    """1 条 pydantic error 条目 → 1 条诊断（设计文档 §3.2 步 2 转写规则）。

    - ``type == "extra_forbidden"`` → ``LLMSIM_UNKNOWN_KEY``（refs = [键名，
      取 error loc 末元 / ctx]）；
    - 其余条目 → ``LLMSIM_SCHEMA``（refs = [loc 点分串, type]）。
    """
    error_type = str(entry.get("type", ""))
    loc = tuple(entry.get("loc", ()))
    loc_str = ".".join(str(part) for part in loc)
    if error_type == "extra_forbidden":
        if loc:
            key = str(loc[-1])
        else:
            ctx = entry.get("ctx") or {}
            key = str(ctx.get("key", ctx.get("field", "")))
        return Diagnostic(
            code="LLMSIM_UNKNOWN_KEY",
            severity=DiagnosticSeverity.ERROR,
            path=path,
            message=f"未知字段: {key}",
            refs=(key,),
        )
    return Diagnostic(
        code="LLMSIM_SCHEMA",
        severity=DiagnosticSeverity.ERROR,
        path=path,
        message=f"schema 违例: {entry.get('msg', '')}",
        refs=(loc_str, error_type),
    )


def _validate_section(
    adapter: TypeAdapter[Any], value: Any, path: str
) -> tuple[Any, tuple[Diagnostic, ...]]:
    """校验一个节值：成功 → (值, ())；``ValidationError`` → (None, 按 loc 序
    追加的每条目一条诊断)；永不 raise。"""
    try:
        return adapter.validate_python(value), ()
    except ValidationError as err:
        return None, tuple(_diagnostic_from_error(entry, path) for entry in err.errors())


def _yaml_root_not_dict_diagnostic(path: str) -> Diagnostic:
    """``LLMSIM_YAML_PARSE``（根非 dict 形态，refs = ["root-not-dict"]，与
    loader ``read_yaml_file`` 同码同 refs 口径）。"""
    return Diagnostic(
        code="LLMSIM_YAML_PARSE",
        severity=DiagnosticSeverity.ERROR,
        path=path,
        message="YAML 根节点不是 dict 映射",
        refs=("root-not-dict",),
    )


def _world_extra_diagnostic(rel: str) -> Diagnostic:
    """world 节单值语义：sorted 序余文件各 1 条 ``LLMSIM_SCHEMA``（refs 逐字）。"""
    return Diagnostic(
        code="LLMSIM_SCHEMA",
        severity=DiagnosticSeverity.ERROR,
        path=rel,
        message="world 节为单值 WorldSpec，多余文件不合并",
        refs=(_WORLD_EXTRA_FILE_REF,),
    )


def _validate_section_file(
    raw: RawProject, rel: str, top_key: str, adapter: TypeAdapter[Any]
) -> tuple[Any, tuple[Diagnostic, ...]]:
    """校验一个节文件：顶层键闭包检查 + 内层 ``model_validate``。

    顶层键处置（设计文档 §3.1 L216-224 各节"顶层必为对应键" + §3.2 步 3）：
    期望键缺失 → 1 条 ``LLMSIM_SCHEMA``（refs = [期望键名, "missing"]）；其他
    键 → 每键 1 条 ``LLMSIM_UNKNOWN_KEY``（refs = [键名]，sorted 序）；两族可
    同时出，该文件即停（不再做内层校验）。
    """
    data = raw.files[rel]
    if not isinstance(data, dict):
        return None, (_yaml_root_not_dict_diagnostic(rel),)
    diags: list[Diagnostic] = []
    missing_top = top_key not in data
    if missing_top:
        diags.append(
            Diagnostic(
                code="LLMSIM_SCHEMA",
                severity=DiagnosticSeverity.ERROR,
                path=rel,
                message=f"节文件顶层键缺失: {top_key}",
                refs=(top_key, "missing"),
            )
        )
    extra_keys = sorted(key for key in data if key != top_key)
    for key in extra_keys:
        diags.append(
            Diagnostic(
                code="LLMSIM_UNKNOWN_KEY",
                severity=DiagnosticSeverity.ERROR,
                path=rel,
                message=f"未知顶层键: {key}",
                refs=(key,),
            )
        )
    if missing_top or extra_keys:
        return None, tuple(diags)
    value, inner = _validate_section(adapter, data[top_key], rel)
    return value, tuple(diags) + inner


# —— 公开面（§8.2 台账序）——


def build_ir(raw: RawProject) -> IRBuildResult:
    """raw → ProjectIR 编译器（设计文档 §3.2 四步流程，步序即诊断追加序）。

    1. ``game.yaml`` 缺失（raw.files 无该键；loader 已报 FILE_MISSING）→
       (None, [LLMSIM_FILE_MISSING path="game.yaml"])（双保险）；
    2. game.yaml 顶层键封闭集（8 键）：逐节 ``model_validate``（``extra="forbid"``），
       pydantic ``ValidationError`` 每条目 → ``LLMSIM_SCHEMA`` /
       ``LLMSIM_UNKNOWN_KEY``（按 loc 序追加）；必需节（manifest / scenario /
       player）缺失 → 1 条 ``LLMSIM_SCHEMA``（refs = [节名, "missing"]）；
       顶层多余键 → 每键 1 条 ``LLMSIM_UNKNOWN_KEY``（sorted 序）；
    3. 各节文件（8 节目录，LAYOUT_OPTIONAL 模板序；顶层键闭包检查见
       ``_validate_section_file``）；world 节单值语义：0 文件 → ir.world =
       None；恰好 1 → WorldSpec；≥2 → sorted 路径序首文件 + 每余文件 1 条
       ``LLMSIM_SCHEMA``（refs 逐字，§3.2 L304）；
    4. 成功 → IR（各节文件按 sorted 路径序合并进对应 tuple）；失败 →
       (None, 诊断集)。**永不 raise** 内容级异常（K2 / P5-INV-2 纯产新值）。
    """
    diagnostics: list[Diagnostic] = []

    # —— 步 1：game.yaml 双保险 ——
    game = raw.files.get("game.yaml")
    if game is None:
        diagnostics.append(
            Diagnostic(
                code="LLMSIM_FILE_MISSING",
                severity=DiagnosticSeverity.ERROR,
                path="game.yaml",
                message="必需文件 game.yaml 缺失（双保险，loader 已报 FILE_MISSING）",
            )
        )
        return IRBuildResult(ir=None, diagnostics=tuple(diagnostics))
    if not isinstance(game, dict):
        return IRBuildResult(
            ir=None, diagnostics=(_yaml_root_not_dict_diagnostic("game.yaml"),)
        )

    # —— 步 2：game.yaml 8 键封闭集，逐节 model_validate（显式节序）——
    game_values: dict[str, Any] = {}
    for section, adapter in _GAME_SECTIONS:
        if section not in game:
            if section in _REQUIRED_GAME_SECTIONS:
                diagnostics.append(
                    Diagnostic(
                        code="LLMSIM_SCHEMA",
                        severity=DiagnosticSeverity.ERROR,
                        path="game.yaml",
                        message=f"game.yaml 缺失必需节: {section}",
                        refs=(section, "missing"),
                    )
                )
            continue
        value, section_diags = _validate_section(adapter, game[section], "game.yaml")
        diagnostics.extend(section_diags)
        if value is not None:
            game_values[section] = value
    for key in sorted(name for name in game if name not in _GAME_SECTION_NAMES):
        diagnostics.append(
            Diagnostic(
                code="LLMSIM_UNKNOWN_KEY",
                severity=DiagnosticSeverity.ERROR,
                path="game.yaml",
                message=f"未知顶层键: {key}",
                refs=(key,),
            )
        )

    # —— 步 3：各节文件（LAYOUT_OPTIONAL 模板序）+ world 单值语义 ——
    world_spec: WorldSpec | None = None
    tuple_values: dict[str, list[Any]] = {
        "characters": [],
        "items": [],
        "rules": [],
        "actions": [],
        "prompts": [],
        "scenarios": [],
        "modules": [],
    }
    for section, top_key, adapter, ir_field in _SECTION_FILES:
        rels = _section_file_keys(raw, section)
        if section == "world":
            # 单值字段：sorted 首文件为准，每余文件 1 条 LLMSIM_SCHEMA（不 raise）
            if rels:
                value, file_diags = _validate_section_file(raw, rels[0], top_key, adapter)
                diagnostics.extend(file_diags)
                if value is not None:
                    world_spec = value
            for rel in rels[1:]:
                diagnostics.append(_world_extra_diagnostic(rel))
            continue
        for rel in rels:
            value, file_diags = _validate_section_file(raw, rel, top_key, adapter)
            diagnostics.extend(file_diags)
            if value is not None:
                tuple_values[ir_field].extend(value)

    # —— 步 4：失败 → (None, 诊断集)；成功 → IR（永不 raise）——
    if diagnostics:
        return IRBuildResult(ir=None, diagnostics=tuple(diagnostics))
    ir = ProjectIR(
        manifest=game_values["manifest"],
        scenario=game_values["scenario"],
        world=world_spec,
        player=game_values["player"],
        items=tuple(tuple_values["items"]),
        characters=tuple(tuple_values["characters"]),
        # 5 个可选节缺席 = 合法空（D-P5-05）；必需 3 节缺席已在步 2 成诊断早退
        component_schemas=tuple(game_values.get("component_schemas", ())),
        actions=tuple(tuple_values["actions"]),
        rules=tuple(tuple_values["rules"]),
        authority=tuple(game_values.get("authority", ())),
        modules=tuple(tuple_values["modules"]),
        gameplay_modes=tuple(game_values.get("gameplay_modes", ())),
        capabilities=tuple(game_values.get("capabilities", ())),
        prompts=tuple(tuple_values["prompts"]),
        plugin_descriptors=tuple(game_values.get("plugin_descriptors", ())),
        scenarios=tuple(tuple_values["scenarios"]),
    )
    return IRBuildResult(ir=ir, diagnostics=())


def flatten_entities(ir: ProjectIR) -> dict[str, Any]:
    """ID → 实体 spec 映射（设计文档 §3.2：locations ∪ items ∪ characters ∪
    player by player_id）。

    合并序 = locations → items → characters → player，重复键后者覆盖（重复
    本身由 check_duplicate_ids 诊断，本函数不判重）；返回 dict 键序 = 按
    ``(id.casefold(), id)`` 升序（完全确定，D-P5-15 / §6.1 casefold 稳定口径）。
    """
    merged: dict[str, Any] = {}
    if ir.world is not None:
        for location in ir.world.locations:
            merged[location.id] = location
    for item in ir.items:
        merged[item.id] = item
    for character in ir.characters:
        merged[character.id] = character
    merged[ir.player.player_id] = ir.player
    return {key: merged[key] for key in sorted(merged, key=lambda k: (k.casefold(), k))}


def iter_entity_refs(ir: ProjectIR) -> Iterator[tuple[str, str, str]]:
    """引用三元组迭代器：`(holder_id, ref_kind, ref_value)`（设计文档 §3.2）。

    ``ref_kind`` ∈ {``connection``, ``relationship``, ``inventory``}；遍历序 =
    IR 元组序（locations 全体 → characters 全体 → player）；holder 内序 =
    connection（connections dict 插入序，ref = 目标 location id）→
    relationship（relationships dict 插入序，ref = 键）→ inventory（list 序；
    player 取 ``inventory`` 字段、character 取 ``starting_inventory`` 字段，
    ref = 元素）。
    """
    if ir.world is not None:
        for location in ir.world.locations:
            for _direction, target in location.connections.items():
                yield location.id, "connection", target
    for character in ir.characters:
        for other_id, _weight in character.relationships.items():
            yield character.id, "relationship", other_id
        for item_id in character.starting_inventory:
            yield character.id, "inventory", item_id
    for item_id in ir.player.inventory:
        yield ir.player.player_id, "inventory", item_id


def ir_to_data(ir: ProjectIR) -> dict[str, Any]:
    """IR → JSON-clean dict（设计文档 §3.2：``model_dump(mode="json")`` 嵌套
    展开 + 尾部 ``assert_json_clean``（serialization.py:82）机械钩子，
    K7 / P5-INV-7）。纯函数。"""
    data: dict[str, Any] = ir.model_dump(mode="json")
    assert_json_clean(data)
    return data


def canonical_yaml(ir: ProjectIR) -> str:
    """IR → 规范 YAML 文本（D-P5-14：``yaml.safe_dump`` 精确 kwargs =
    ``sort_keys=True, allow_unicode=True, default_flow_style=False, width=100``）。

    纯函数；双 dump 字节稳定（断言 #20 同源：数据级恒等由 model_validate
    复合 safe_load 再验证，本函数保证序列化面自漂移零容忍）。
    """
    return yaml.safe_dump(
        ir_to_data(ir),
        sort_keys=True,
        allow_unicode=True,
        default_flow_style=False,
        width=100,
    )
