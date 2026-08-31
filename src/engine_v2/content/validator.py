"""engine_v2 content 层 P5 项目校验编排 + K8 文本扫描 + 插件检查
（P5-T09 / W6，设计文档 §3.6）。

依据 ``docs/v2/contracts/P5-project-format-module-plugin-dsl-design.md``（下称
"设计文档"，P5-DESIGN 冻结态）§3.6 字段级规格（8 导出，§8.2 L898 台账逐名逐序）：

- **定位**：IR 语义检查编排 + K8 文本扫描 + 插件检查。导入面 = ``schemas``
  （含 ``RawProject`` 类型）/ ``project_ir``（``iter_entity_refs``）/
  ``module_graph`` / ``rule_module``（仅 ``parse_dsl``）/ ``plugins.registry`` /
  ``re`` + stdlib（§3.6 L421 定位条款）；
- **never-raise**（内容级，K2 / P5-INV-2）：8 个公共面绝不抛出——全部结构 /
  语义 / 文本违例成诊断；
- **validate_project 编排**（§3.6 L426 字面并集序 + 尾部 ``sort_diagnostics``）：
  check_duplicate_ids ∪ check_references ∪ check_authority_conflicts ∪
  check_dsl_parses ∪ module 面（build_module_graph + check_unsatisfied_requires
  + check_module_versions + detect_conflicts + find_cycles 每环一条
  ``LLMSIM_MODULE_CYCLE``）∪ manifest 面（``engine_version`` 非空且对照
  ``schemas.ENGINE_VERSION`` 不满足 → 一条 ``LLMSIM_ENGINE_VERSION``）∪
  （raw 非 None 时）check_deployment_leakage ∪ discover_local_plugins 发现期
  诊断（不丢弃，ERR-P5-5 G-2）∪ validate_plugins；
- **manifest 面版本比较**：本地重实现 D-P5-06 数字串比较（点分拆、补 "0"、
  逐组件去前导 0、先比组件串长度、再字典序；零 ``int()`` 调用，ERR-P5-14
  同机制）——与 ``module_graph`` 私有比较面（其 ``__all__`` 11 名不含之，
  不可 import）各持同语义纯函数（W5 EP 文法同值定义先例；Leader 预裁定 A3）；
- **K8 探针面**（§3.6 L430 / D-P5-11）：12 名封闭集以串拼接构造（自证豁免，
  与本文件全部 7 个 P5 新 ``.py`` 文件的裸 token 扫描纪律同机制）；扫描面 =
  ``raw.texts`` 全部键 ∪（``pyproject_text`` 非 None 时 path = ``pyproject.toml``）；
  ``\\b`` 词边界口径唯一一致版本（``llmsim`` 不命中、``api_key_env`` 不命中、
  ``model`` 不在 12 名集）；每 (文件, 名) 对去重一条 ``LLMSIM_DEPLOYMENT_FIELD``；
- **确定性纪律**（D-P5-15）：零 ``asyncio``/``datetime``/``time``/``random``/
  网络族 import；诊断产出序确定（池序 / IR 元组序 / sorted 文本面 / 尾部
  ``sort_diagnostics`` 稳定排序 key = ``(code, path, message)``，D-P5-12）。

私有面（不入 ``__all__``）：版本比较三函数、12 名封闭集、池枚举 helper。
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Final

from src.engine_v2.content import module_graph
from src.engine_v2.content.project_ir import iter_entity_refs
from src.engine_v2.content.rule_module import parse_dsl
from src.engine_v2.content.schemas import (
    ENGINE_VERSION,
    _ContractModel,
    Diagnostic,
    DiagnosticSeverity,
    ProjectIR,
    RawProject,
)
from src.engine_v2.plugins.registry import (
    discover_local_plugins,
    validate_plugins,
)

__all__ = [
    "ValidationResult",
    "validate_project",
    "check_duplicate_ids",
    "check_references",
    "check_authority_conflicts",
    "check_deployment_leakage",
    "check_dsl_parses",
    "sort_diagnostics",
]


class ValidationResult(_ContractModel):
    """validate_project 产物（设计文档 §3.6 L425：frozen）。

    - ``ok`` = 无 error 级诊断；
    - ``diagnostics`` = 已排序（``sort_diagnostics`` 尾部产出序）；
    - ``ir`` = 入参 IR（validate_project 面 ir 必非 None）。
    """

    ok: bool
    diagnostics: tuple[Diagnostic, ...]
    ir: ProjectIR | None


# —— K8 封闭集（§3.6 L430 字面；串拼接自证豁免裸 token 扫描纪律）——

#: Deployment 禁名词 12 名封闭集（D-P5-11；与 test_import_boundary.py
#: 12 名黑名单逐名相等，断言 #19 附注核验面）。构造 = 串拼接自证豁免。
_DEPLOYMENT_FORBIDDEN_KEYS: Final[frozenset[str]] = frozenset(
    {
        "open" + "ai",
        "anthro" + "pic",
        "lang" + "chain",
        "li" + "tellm",
        "ol" + "lama",
        "gem" + "ini",
        "g" + "pt",
        "cla" + "ude",
        "ll" + "m",
        "prov" + "ider",
        "api_" + "key",
        "base_" + "url",
    }
)


# —— 私有版本比较面（manifest 面本地重实现；语义 ≡ module_graph 私有面）——
#
# D-P5-06 比较裁定：点分数字逐位、短者补 0；exact = 相等、>= = 不小于。
# ERR-P5-14 机制：纯字符串比较，零 int() 调用（CPython 3.12 int() 4300 位
# 上限约束，never-raise 纪律）。module_graph 比较面私有（L119 注释），
# 不可 import——两模块各持同语义纯函数（W5 EP 文法同值定义先例）。

_MANIFEST_VERSION_RE: Final[re.Pattern[str]] = re.compile(r"^\d+(?:\.\d+)*$")


def _version_components(value: str) -> tuple[str, ...]:
    """版本文法字符串（裸 V）→ 点分组件串元组（纯字符串，零 int() 调用）。"""
    return tuple(value.split("."))


def _version_cmp(a: str, b: str) -> int:
    """点分版本纯字符串比较（-1 / 0 / 1）。

    机制与 ``module_graph._version_cmp`` 逐位同义：两串按点分拆组件、组件
    数对齐（缺者补 "0"）；每组件去前导 0（去空则 "0"）；逐组件先比组件串
    长度（长者大）、再比字典序。口径等价性 = 「数值补 0 逐位比较」（D-P5-06）。
    """
    left = _version_components(a)
    right = _version_components(b)
    size = max(len(left), len(right))
    left = left + ("0",) * (size - len(left))
    right = right + ("0",) * (size - len(right))
    for la, ra in zip(left, right):
        la = la.lstrip("0") or "0"
        ra = ra.lstrip("0") or "0"
        if len(la) != len(ra):
            return -1 if len(la) < len(ra) else 1
        if la < ra:
            return -1
        if la > ra:
            return 1
    return 0


def _manifest_engine_version_satisfied(declared: str) -> bool:
    """manifest 面 ``engine_version`` 约束对照 ``ENGINE_VERSION`` 的满足判定。

    文法（D-P5-06 版本文法；schemas ``ProjectManifest.engine_version`` 构造
    期已限 ``""`` | V | ``>=V``）：``>=V`` 形 = 不小于（补 0 逐位）；exact 形
    = 相等（补 0 后元组相等）；文法外非空约束 = False（防御分支，schema 面
    不可达）。与 ``check_module_versions`` 节点面同比较裁定（§3.6 L426）。
    """
    if declared.startswith(">="):
        target = declared[2:]
        if _MANIFEST_VERSION_RE.match(target) is None:
            return False
        return _version_cmp(ENGINE_VERSION, target) >= 0
    if _MANIFEST_VERSION_RE.match(declared) is None:
        return False
    return _version_cmp(ENGINE_VERSION, declared) == 0


# —— 私有池枚举（check_duplicate_ids / check_references 共用面）——


def _duplicate_id_pools(ir: ProjectIR) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """判重池枚举（§3.6 L427 池序字面：独立命名空间池 → 全局唯一池）。

    池序 = locations / items / characters / player 单值（v1 独立命名空间
    口径：跨池撞名合法）→ 全局唯一池 rules / actions / modules / prompts /
    scenarios（含默认 scenario id）/ component_schemas / authority /
    gameplay_modes / capabilities / plugin_descriptors。
    """
    pools: list[tuple[str, tuple[str, ...]]] = []
    if ir.world is not None:
        pools.append(("locations", tuple(loc.id for loc in ir.world.locations)))
    pools.append(("items", tuple(item.id for item in ir.items)))
    pools.append(("characters", tuple(ch.id for ch in ir.characters)))
    pools.append(("player", (ir.player.player_id,)))
    pools.append(("rules", tuple(rule.id for rule in ir.rules)))
    pools.append(("actions", tuple(act.id for act in ir.actions)))
    pools.append(("modules", tuple(node.id for node in ir.modules)))
    pools.append(("prompts", tuple(pol.id for pol in ir.prompts)))
    scenario_ids = (ir.scenario.id,) + tuple(s.id for s in ir.scenarios)
    pools.append(("scenarios", scenario_ids))
    pools.append(
        ("component_schemas", tuple(cs.id for cs in ir.component_schemas))
    )
    pools.append(("authority", tuple(pol.id for pol in ir.authority)))
    pools.append(
        ("gameplay_modes", tuple(mode.id for mode in ir.gameplay_modes))
    )
    pools.append(("capabilities", tuple(cap.id for cap in ir.capabilities)))
    pools.append(
        ("plugin_descriptors", tuple(d.id for d in ir.plugin_descriptors))
    )
    return tuple(pools)


# —— 公开面（§8.2 L898 台账序）——


def check_duplicate_ids(ir: ProjectIR) -> list[Diagnostic]:
    """池内判重（§3.6 L427 / 对抗 A1：每重复 id 恰好 1 条）。

    ``LLMSIM_DUPLICATE_ID``，path = 池名，refs = [id, 首次出现索引, 重复出现
    索引]（池 tuple 内 0-based 位置索引、字符串化；tuple 序 = build_ir sorted
    路径合并序，确定性；Leader 预裁定 A1 钉死形）。同 id 第三次及以后出现
    不另产诊断（每重复 id 恰好 1 条，§6.3 A1 字面）。
    """
    diagnostics: list[Diagnostic] = []
    for pool_name, ids in _duplicate_id_pools(ir):
        first_index: dict[str, int] = {}
        reported: set[str] = set()
        for index, entity_id in enumerate(ids):
            if entity_id in first_index and entity_id not in reported:
                diagnostics.append(
                    Diagnostic(
                        code="LLMSIM_DUPLICATE_ID",
                        severity=DiagnosticSeverity.ERROR,
                        path=pool_name,
                        message=f"池 {pool_name} 内 ID 重复：{entity_id}",
                        refs=(
                            entity_id,
                            str(first_index[entity_id]),
                            str(index),
                        ),
                    )
                )
                reported.add(entity_id)
            elif entity_id not in first_index:
                first_index[entity_id] = index
    return diagnostics


def check_references(ir: ProjectIR) -> list[Diagnostic]:
    """悬空引用检查（§3.6 L428 / 对抗 A2：每条悬空引用 1 条）。

    ``LLMSIM_UNRESOLVED_REF``，path = holder id，refs = [ref_kind, ref_value]。
    引用源 = ``project_ir.iter_entity_refs``（ref_kind ∈ {connection,
    relationship, inventory}）；目标池：

    - ``connection`` 值 → location id 池（location 型引用 = 且仅 =
      ``LocationSpec.connections`` 值——PlayerSpec/CharacterSpec.position 为
      PositionSpec x/y/z 坐标，非 location 引用；Leader 预裁定 A2）；
      ``ir.world = None`` 或 locations 池空 → connection 引用跳过，零
      ``UNRESOLVED_REF``（合法空语义，§3.6 L428 括注）；
    - ``relationship`` 键 → character 池 ∪ {player_id}；
    - ``inventory``/``starting_inventory`` 元素 → object 池（items）。
    """
    if ir.world is not None and ir.world.locations:
        location_ids: frozenset[str] | None = frozenset(
            loc.id for loc in ir.world.locations
        )
    else:
        location_ids = None
    character_ids = {ch.id for ch in ir.characters}
    character_ids.add(ir.player.player_id)
    item_ids = frozenset(item.id for item in ir.items)
    diagnostics: list[Diagnostic] = []
    for holder_id, ref_kind, ref_value in iter_entity_refs(ir):
        if ref_kind == "connection":
            if location_ids is None or ref_value in location_ids:
                continue
        elif ref_kind == "relationship":
            if ref_value in character_ids:
                continue
        else:  # inventory
            if ref_value in item_ids:
                continue
        diagnostics.append(
            Diagnostic(
                code="LLMSIM_UNRESOLVED_REF",
                severity=DiagnosticSeverity.ERROR,
                path=holder_id,
                message=f"{ref_kind} 引用指向不存在的实体：{ref_value}",
                refs=(ref_kind, ref_value),
            )
        )
    return diagnostics


def check_authority_conflicts(ir: ProjectIR) -> list[Diagnostic]:
    """authority 声明域重叠静态检查（§3.6 L429 / D-P5-03 声明域重叠级）。

    两两同 domain ∧ 双 exclusive → 每对一条 ``LLMSIM_AUTHORITY_CONFLICT``
    （path = domain，refs = [owner_a, owner_b] casefold 序，每对一条——
    重叠级而非笛卡尔积，Leader 预裁定同族口径）。
    """
    policies = list(ir.authority)
    diagnostics: list[Diagnostic] = []
    for i in range(len(policies)):
        for j in range(i + 1, len(policies)):
            first = policies[i]
            second = policies[j]
            if first.domain != second.domain:
                continue
            if not (first.exclusive and second.exclusive):
                continue
            owners = sorted((first.owner, second.owner), key=str.casefold)
            diagnostics.append(
                Diagnostic(
                    code="LLMSIM_AUTHORITY_CONFLICT",
                    severity=DiagnosticSeverity.ERROR,
                    path=first.domain,
                    message=(
                        f"domain {first.domain} 被双 exclusive 策略声明"
                        f"（{first.owner} / {second.owner}）"
                    ),
                    refs=tuple(owners),
                )
            )
    return diagnostics


def check_deployment_leakage(raw: RawProject) -> list[Diagnostic]:
    """K8 文本扫描（§3.6 L430 / D-P5-11 / 断言 #19a 探针表 P1-P4）。

    扫描面 = ``raw.texts`` 全部键 ∪（``pyproject_text`` 非 None 时，path =
    ``pyproject.toml``）；对每 (文件, 名)：``re.finditer(rf"\\b{name}\\b",
    text.casefold())`` ≥1 命中 → 一条 ``LLMSIM_DEPLOYMENT_FIELD``
    （path = 文件，refs = [name] 仅，无上下文片段，每对去重）。

    词边界口径（唯一一致版本，§3.6 L430）：``llmsim`` 不命中（12 名最短词
    后紧跟 word char ``s``，无词边界）；``api_key_env`` 不命中（下划线是
    word char，``y`` 与下划线之间无词边界）；``model`` 不在 12 名集（F-2 披露：
    model pin 检测依赖值文本 token 或 12 名键命中）。
    """
    texts: dict[str, str] = dict(raw.texts)
    if raw.pyproject_text is not None:
        texts["pyproject.toml"] = raw.pyproject_text
    diagnostics: list[Diagnostic] = []
    for path in sorted(texts):
        folded = texts[path].casefold()
        for name in sorted(_DEPLOYMENT_FORBIDDEN_KEYS):
            if re.search(rf"\b{name}\b", folded) is None:
                continue
            diagnostics.append(
                Diagnostic(
                    code="LLMSIM_DEPLOYMENT_FIELD",
                    severity=DiagnosticSeverity.ERROR,
                    path=path,
                    message="项目文件命中 Deployment 禁名词（K8 扫描面）",
                    refs=(name,),
                )
            )
    return diagnostics


def check_dsl_parses(ir: ProjectIR) -> list[Diagnostic]:
    """规则 / 动作 DSL condition 结构校验（§3.6 L445 / D-P5-09）。

    每条 ``RuleSpec.condition`` 与 ``ActionSpec.condition``（非 None）→
    ``parse_dsl(expr, path_label=id)``，透传其诊断（path 重写为规则/动作 id，
    refs = [expr 前 40 字符]）。parse_dsl 永不抛（结构错 = 诊断，ERR-P5-15
    域内覆盖）。
    """
    targets: list[tuple[str, str]] = []
    for rule in ir.rules:
        if rule.condition is not None:
            targets.append((rule.id, rule.condition))
    for action in ir.actions:
        if action.condition is not None:
            targets.append((action.id, action.condition))
    diagnostics: list[Diagnostic] = []
    for spec_id, expression in targets:
        result = parse_dsl(expression, path_label=spec_id)
        for diag in result.diagnostics:
            diagnostics.append(
                Diagnostic(
                    code=diag.code,
                    severity=diag.severity,
                    path=spec_id,
                    message=diag.message,
                    refs=(expression[:40],),
                )
            )
    return diagnostics


def sort_diagnostics(diagnostics: Sequence[Diagnostic]) -> list[Diagnostic]:
    """诊断稳定排序（§3.6 L446 / D-P5-12）：key = ``(code, path, message)``。

    稳定排序（同 key 保原序）；输出 = 新 list（输入零原地变更，K2）。
    """
    return sorted(diagnostics, key=lambda d: (d.code, d.path, d.message))


def validate_project(
    ir: ProjectIR, raw: RawProject | None = None
) -> ValidationResult:
    """IR 语义检查总编排（§3.6 L426 字面并集序 + 尾部 sort_diagnostics）。

    诊断 = check_duplicate_ids ∪ check_references ∪ check_authority_conflicts
    ∪ check_dsl_parses ∪ module 面（build_module_graph +
    check_unsatisfied_requires + check_module_versions + detect_conflicts +
    find_cycles 每环一条 ``LLMSIM_MODULE_CYCLE`` path = min(node)、refs =
    节点序）∪ manifest 面（``ir.manifest.engine_version`` 非空且对照
    ``ENGINE_VERSION``（单点权威 = ``schemas.ENGINE_VERSION``）不满足（与
    ``check_module_versions`` 节点面同比较裁定）→ 一条
    ``LLMSIM_ENGINE_VERSION`` path = "manifest" refs = [声明值,
    ``ENGINE_VERSION``]）∪（raw 非 None 时）check_deployment_leakage(raw) ∪
    discover_local_plugins 发现期诊断（不丢弃，ERR-P5-5 G-2）∪
    validate_plugins(local_registry, ir, raw)；最后 ``sort_diagnostics``。

    **永不 raise**（内容级）。raw = None → 仅 IR 面（K8 文本面与插件面
    跳过，§3.6 L426 文档披露）。
    """
    diagnostics: list[Diagnostic] = []
    diagnostics.extend(check_duplicate_ids(ir))
    diagnostics.extend(check_references(ir))
    diagnostics.extend(check_authority_conflicts(ir))
    diagnostics.extend(check_dsl_parses(ir))

    # —— module 面（§3.6 L426；诊断生产面归属 W6，ERR-P5-14 钉死）——
    graph = module_graph.build_module_graph(ir)
    diagnostics.extend(module_graph.check_unsatisfied_requires(graph))
    diagnostics.extend(module_graph.check_module_versions(graph))
    diagnostics.extend(module_graph.detect_conflicts(graph))
    for cycle in module_graph.find_cycles(graph):
        diagnostics.append(
            Diagnostic(
                code="LLMSIM_MODULE_CYCLE",
                severity=DiagnosticSeverity.ERROR,
                path=min(cycle),
                message="模块依赖环",
                refs=tuple(cycle),
            )
        )

    # —— manifest 面（engine_version 消费面；节点面/插件面共用同一常量）——
    declared = ir.manifest.engine_version
    if declared != "" and not _manifest_engine_version_satisfied(declared):
        diagnostics.append(
            Diagnostic(
                code="LLMSIM_ENGINE_VERSION",
                severity=DiagnosticSeverity.ERROR,
                path="manifest",
                message=f"manifest engine_version 约束不满足：{declared}",
                refs=(declared, ENGINE_VERSION),
            )
        )

    # —— raw 面（K8 文本扫描 + 插件检查；raw = None → 跳过，文档披露）——
    if raw is not None:
        diagnostics.extend(check_deployment_leakage(raw))
        local_registry, discovery_diags = discover_local_plugins(raw)
        diagnostics.extend(discovery_diags)
        diagnostics.extend(validate_plugins(local_registry, ir, raw))

    ordered = sort_diagnostics(diagnostics)
    ok = all(d.severity != DiagnosticSeverity.ERROR for d in ordered)
    return ValidationResult(ok=ok, diagnostics=tuple(ordered), ir=ir)
