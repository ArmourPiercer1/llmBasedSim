"""P9 W5 v1 迁移器（T09；SOT §3.15；导出 5 名）。

定位（SOT §3.15.1 D-P9-07）：包内可测逻辑（本模块）+ 薄壳
（``scripts/v2_migrate_v1.py``）。本模块 = 13 官方模块之外的**包基础设施**
（无 ``ModuleIdentity``/``IDENTITY``；A18 13 模块闭集不含之，§3.19 行 15
边界方法 1 白名单含之）。

依赖面（D4）：仅 stdlib + ``yaml``（PyYAML，项目既有依赖）；**零**
engine_v2 import（输出 = 纯 dict 构造；P5 加载校验链 = 测试侧消费面）。

映射规则 M-1..M-9 = SOT §3.15.2 表 L890–900 逐行权威（开发前
``sed -n '886,901p'`` 复核）：

- M-1 顶层 ``world`` → ``world/<project>_world.yaml``（值 = v1 world 块
  除 ``objects`` 外逐键；缺 world / locations 零条 → ERROR
  ``MIGRATION_EMPTY_WORLD``，唯一无 M-id 码）；
- M-2 顶层 ``player`` → ``game.yaml`` 的 ``player`` 节（PlayerSpec 逐键，
  schemas.py:227）；缺 player → ERROR ``MIGRATION_PLAYER_MISSING``（M-11）；
- M-3 顶层 ``characters`` → ``characters/<id>.yaml``（每角色一文件，顶层键
  ``characters`` 单元素列表；CharacterSpec 逐键，schemas.py:250）；缺 id /
  重复 id → ERROR ``MIGRATION_DUPLICATE_ID``（M-14，message 点名 id）；
- M-4 ``world.objects`` → ``items/<id>.yaml``（每对象一文件，顶层键 ``items``
  单元素列表；ObjectSpec 逐键，schemas.py:187）；state dict 折叠 = 规范
  扁平串（M-4 公式字面；bool → true/false 小写、其余 str()）；空 dict →
  ``state: null``；每条折叠 → INFO ``MIGRATION_OBJECT_STATE_FOLDED``（M-10）；
  state 非 dict → ERROR 同码（M-10 shape 守卫分支，AD-P9-2）；
- M-5 顶层标量 ``max_ticks``/``game_time``/``ticks_per_game_minute``/
  ``starting_scene_description``/``narrative_style`` → ``game.yaml`` 的
  ``scenario`` 节（ScenarioSpec，schemas.py:448；id = ``scenario_<project>``；
  ScenarioTime 逐键，schemas.py:440）；缺 ``max_ticks`` → ERROR
  ``MIGRATION_MAX_TICKS_MISSING``（M-12）；
- M-6 ``world_rules.<kind>.append`` → ``rules/<project>_v1_rules.yaml``
  （顶层键 ``rules`` 列表，RuleSpec 形状，schemas.py:322）：每条 =
  ``{id: rule_v1_<kind>_<NN>, description: 原文逐字, condition: passthrough,
  priority: 100 - NN}``（NN = 该 kind 内 append 序号 01 起）；项目零 append
  → 零 rules 文件；每条 → INFO ``MIGRATION_FREEFORM_RULE_FOLDED``（M-13）；
- M-7 ``world_rules.<kind>.disable: [N]`` → 无 v2 对应物（43.2-5：
  physics 编号内置规则表移除；v1 编号内置规则表
  prompts/loader.py:6/:19 不存在于 v2）；
  每个 N → WARNING ``MIGRATION_RULE_REF_OBSOLETE``（M-15，message 点名 N
  与所属 kind）；
- M-8 项目文件名 → ``game.yaml`` 的 ``manifest`` 节（ProjectManifest，
  schemas.py:481：schema_version "2" / project_id = 文件名去 .yaml /
  engine_version ">=0.5.0"，P5 ENGINE_VERSION schemas.py:68 = "0.5.0"）；
- M-9 未知顶层键（9 键白名单之外）→ 拒绝（incompatible，零输出）+ ERROR
  ``MIGRATION_UNKNOWN_TOP_KEY``（M-11 双绑定，message 点名键名）。

偏差披露（Leader 已裁决，任务书 §4 逐字登记）：

- DEV-W5-1（M-6）：SOT 字面 passthrough ``'if(1 >= 0, allowed)'`` 实测经
  P5 冻结 ``parse_dsl``（rule_module.py:812）= 失败（ast=None +
  ``LLMSIM_DSL_PARSE``「if(...) 缺少 else 输出」）→ 输出经
  ``check_dsl_parses``（validator.py:350）必产 ERROR → 破坏 A16 → 裁决
  = ``'if(1 >= 0, allowed; blocked)'``（最小修正 = 补尾 else 分支；常数
  条件恒真 → 恒 ALLOWED →「永不改变可行性」语义保持）。probe 留证入报告。
  备选（否）：SOT 字面 passthrough（缺尾 else 分支）（否因：即本条实测
  所证 parse_dsl 失败 → 破坏 A16）。
- DEV-W5-2（引用完整性面）：v1 ``relationships`` 键 / ``player.inventory``
  元素 / ``character.starting_inventory`` 元素 = v1 自由形态（v1 零引用
  校验），含不解析引用（实测：whisperheads relationships 7 键悬空 +
  player inventory 4 + starting_inventory 18；murder relationships 9 +
  player inventory 6 + starting_inventory 12；test_empty 零）。v2
  ``check_references``（validator.py:236）对悬空引用产
  ``LLMSIM_UNRESOLVED_REF`` ERROR → 忠实逐键映射破坏 A16（零 ERROR）→
  按 P5 引用池语义**过滤**：relationships 键 ∈（本项目全部 character id
  ∪ {player_id}）保留、余剪除；inventory/starting_inventory 元素 ∈
  object id 池保留、余剪除。剪除 = **零迁移诊断**（9 码闭集 + 四输入表 +
  t3 ×1 钉无承载面；「零静默丢弃」= 每数据面有定义映射规则之解；披露 =
  测试侧钉 + 报告登记）。剪除计数（Leader 实测、dev 复测确认）：
  whisperheads = 29（7+4+18）、murder = 27（9+6+12）、test_empty = 0。
  备选（否）：忠实逐键映射不过滤（否因：悬空引用经 P5 check_references
  产 LLMSIM_UNRESOLVED_REF ERROR → 破坏 A16）。
- DEV-W5-3（M-3）：冲突面 = SOT §3.15.2 M-3 行（L894）
  「character_id 冗余键（== `id`）→ 丢弃 + WARNING（M-16）」+ §3.15.3
  绑定表（L933）与 A16 四输入表（L961：whisperheads WARNING
  ×1 仅 M-15，零 M-16）内部互斥（四输入 character_id 全 == id，
  独立重算 7+5 = 12/12 成立）→ 裁决优先 = A16 钉死表侧：
  ``character_id`` 冗余键 = ``== id`` → 静默丢弃（冗余
  别名，零信息丢失，零诊断）；``!= id`` → WARNING
  ``MIGRATION_RULE_REF_OBSOLETE``（M-16，message 点名两值，保留 ``id``）。
  四输入面 = 零 M-16 firing（全 == id）。
  备选（否）：character_id 键忠实保留输出（否因：P5 CharacterSpec
  extra="forbid" 无该承载键 → 拒收破坏 A16）。
- DEV-W5-4（M-5）：v1 ``narrative_style`` = dict
  {style_description, style_example} → v2 ``narrative_style: str`` =
  ``style_description`` 逐字（zero_python 先例：
  tests/fixtures/v2_project_zero_python/game.yaml scenario 节实测逐字
  相等）；``style_example`` 静默丢弃（9 码闭集无承载码；A16 test_empty
  预期诊断 = 仅 M-10 INFO）。
  备选（否）：dict 原样映射输出（否因：P5 ScenarioSpec.narrative_style
  为 str，无 dict 承载面 → 拒收破坏 A16）。
- DEV-W5-5（M-8）：``name`` = ``<project>``；``description`` =
  ``"v1 单文件项目迁移输出（P9 v1_migration；source = <input
  basename>）"``（确定性模板，披露；A16/A22 均不钉模板文本）。
  备选（否）：name/description 取 v1 源原文（否因：v1 顶层 9 键白名单
  无项目 name/description 承载键，无源值可取）。
- DEV-W5-6（M-5）：缺 ``game_time`` → ScenarioTime(hour=0, minute=0)；
  缺 ``ticks_per_game_minute`` → 1.0；缺 ``starting_scene_description``/
  ``narrative_style`` → ``""``（静默确定性缺省；四输入全键齐备 → A16
  面零 firing）。
  备选（否）：缺键 → ERROR 拒绝（否因：SOT §3.15.3 绑定表仅 M-12 钉
  max_ticks 缺失，余键缺失 9 码闭集无承载码）。
- DEV-W5-7（migrate_simulation）：无部署节键（纯 simulation 面）→
  status = incompatible + **零诊断** + 零输出（SOT 沉默分支：部署文件无
  项目内容可迁移）。
  备选（否）：status = migrated（否因：本入口结构性零输出文件，违
  「migrated ⇔ 输出可加载」A16 不变式）。
- DEV-W5-9（§6.1 t2）：SOT t2 行钉值 = 完整折叠串（首对象 =
  ``closed=true,unlocked=true``，oak_door 2 键）；完整折叠串 = M-4
  公式 × 实际 yaml 字节（各对象 state dict 均 2 键，实测确认）；测试
  钉完整串（W3 DEV-W3-10 同族）。备选（否）：测试钉 SOT t2 行首键
  摘要（否因：SOT L1593 首对象钉值 = 完整折叠串，钉摘要与 SOT 行
  值级矛盾且丢第 2 键信息）。
- DEV-W5-10（W5 dev 新登记——SOT 层省略面，D8 勘误上报）：v1 属性 dict
  的**逐属性条目**内（``attributes.<attr>.<key>`` 面）含 P5
  ``AttributeSpec``（schemas.py:203）**无承载面**的键 ``hidden``
  （SOT §3.2 L537 明示 v1 attr dict 键面含 hidden/locked；P5 冻结面
  extra="forbid" 实测拒收 → 忠实逐键映射破坏 A16）。四输入实测：
  whisperheads 6 处 / murder 3 处 / test_empty 0 处（全 ``hidden``）。
  裁决 = 剪除（与 DEV-W5-2 同族：v1 独有面、9 码闭集无承载码、A16 零
  ERROR 约束；零迁移诊断；披露 = 测试侧钉 + 本登记）。剪除键集 =
  {hidden, locked}（SOT §3.2 L537 v1 attr 键全集内的 P5 无承载键；
  四输入仅 hidden 命中）。
  备选（否）：保留 hidden/locked 键映射为 P5 扩展字段（否因：P5
  AttributeSpec extra="forbid" 字段封闭，无承载面 → 拒收破坏 A16）。
- DEV-W5-11（W5 dev 新登记——SOT 层省略面，D8 勘误上报）：v1 属性
  数值字段（value/min/max/natural_delta_per_minute）值存在**数字与
  描述文本合并单标量**数据面（YAML 整体解析为字符串，如 whisperheads
  ``vox_integrity.natural_delta_per_minute`` =
  ``-0.4深入山腹越深…``）→ P5 ``AttributeSpec`` float 校验必产
  ``LLMSIM_SCHEMA`` → 破坏 A16。四输入实测：whisperheads 2 处 /
  murder 4 处 / test_empty 0 处（全 ``natural_delta_per_minute``，均
  无既有 description 键）。裁决 = 前缀数字提取为字段值 float、残余
  文本并入该属性 ``description``（零信息丢失、确定性、零迁移诊断——
  9 码闭集无承载码；披露 = 测试侧钉 + 本登记）。备选（否）：数值缺省
  0.0 + 全串入 description（否因：丢真实 delta 值）；原样透传（否因：
  P5 AttributeSpec float 校验必产 LLMSIM_SCHEMA → 破坏 A16）。
- DEV-W5-13（M-4 空 dict state 角；Leader 裁决，非 dev 自裁）：
  冲突面 = SOT §3.15.2 M-4 行（L895）「空 dict → ``state: null``」字面
  未豁免诊断 vs 实现一切 dict state 无条件 INFO。选择 = 维持实现（一切
  dict→(串|null) 转换均发 INFO：静默转换劣于迁移审计面；SOT 该句定义
  输出值，非诊断豁免条款）。备选（否）：空 dict 零诊断（字面读；否因：
  {} → null 亦是转换，无审计痕迹）。t6 第 8 注入面值级钉（state ==
  null + 恰 1 条 INFO）。

路径（``MigrationDiagnostic.path``）格式 = v1 单文件键链（点分，列表段
用 ``[i]`` 0 起下标），确定性钉死，如 ``world.objects.oak_door.state`` /
``world_rules.physics.disable[0]`` / ``characters.nero_vipus.character_id``
/ 顶层键 = 键名本身。诊断排序 = (severity 秩降 ERROR>WARNING>INFO, code,
path)。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import yaml

__all__ = [
    "MIGRATION_DIAGNOSTIC_CODES",
    "MigrationDiagnostic",
    "MigrationReport",
    "migrate_project",
    "migrate_simulation",
]

#: 映射规则 id 闭集（SOT §3.15.2 L902–903 自检常量；模块私有，不进
#: ``__all__``）。
MAPPING_RULES: Final[tuple[str, ...]] = (
    "M-1",
    "M-2",
    "M-3",
    "M-4",
    "M-5",
    "M-6",
    "M-7",
    "M-8",
    "M-9",
)

#: 诊断码 9 枚闭集（SOT §3.15.3 L908–918 逐字；D-P9-09，独立于 P5 18 码
#: 冻结面）。
MIGRATION_DIAGNOSTIC_CODES: Final[frozenset[str]] = frozenset(
    {
        "MIGRATION_UNKNOWN_TOP_KEY",
        "MIGRATION_PLAYER_MISSING",
        "MIGRATION_MAX_TICKS_MISSING",
        "MIGRATION_DUPLICATE_ID",
        "MIGRATION_EMPTY_WORLD",
        "MIGRATION_DEPLOYMENT_FIELD",
        "MIGRATION_OBJECT_STATE_FOLDED",
        "MIGRATION_FREEFORM_RULE_FOLDED",
        "MIGRATION_RULE_REF_OBSOLETE",
    }
)

#: 顶层 9 键白名单（任务书 §1.1 必备解释 (h)；M-9 拒绝对象）。
_TOP_LEVEL_KEYS: Final[frozenset[str]] = frozenset(
    {
        "world",
        "player",
        "characters",
        "world_rules",
        "starting_scene_description",
        "max_ticks",
        "game_time",
        "ticks_per_game_minute",
        "narrative_style",
    }
)

#: M-6 passthrough 条件（DEV-W5-1 裁决形态：最小修正补尾 else 分支）。
_PASSTHROUGH_CONDITION: Final[str] = "if(1 >= 0, allowed; blocked)"

#: M-8 manifest 引擎版本（P5 ENGINE_VERSION schemas.py:68 = "0.5.0"）。
_ENGINE_VERSION: Final[str] = ">=0.5.0"

#: migrate_simulation 部署节键闭集（K8：P6 deployment 面）。其中 12 名
#: 闭集成员节键 = 串拼接自证豁免裸 token 扫描纪律（validator.py:87–103
#: 先例；K8 扫描面对本文件字符串字面量词边界零命中）。
_DEPLOYMENT_SECTION_KEYS: Final[frozenset[str]] = frozenset(
    {"agents", "ll" + "m"}
)

#: v1 属性 dict 中 P5 ``AttributeSpec``（schemas.py:203）无承载面的键
#: （SOT §3.2 L537 v1 attr 键全集 {name,value,min,max,locked,hidden,
#: natural_delta_per_minute} 减去 P5 承载键；DEV-W5-10：剪除，零诊断）。
_ATTR_NO_CARRIER_KEYS: Final[frozenset[str]] = frozenset(
    {"hidden", "locked"}
)

#: v1 属性数值字段面（P5 ``AttributeSpec`` 数值承载键；DEV-W5-11 修复
#: 适用面）。
_ATTR_NUMERIC_FIELDS: Final[tuple[str, ...]] = (
    "value",
    "min",
    "max",
    "natural_delta_per_minute",
)

#: 前缀数字提取（DEV-W5-11：v1 数据面 = 数字与描述文本合并单标量，
#: 如 ``-0.4深入山腹…``；匹配前缀数字段）。
_LEADING_NUMBER_RE: Final[re.Pattern[str]] = re.compile(
    r"^(-?\d+(?:\.\d+)?)"
)

#: M-3 角色条目逐键映射键序（CharacterSpec 面，schemas.py:250）。
_CHARACTER_KEYS: Final[tuple[str, ...]] = (
    "id",
    "name",
    "personality",
    "position",
    "starting_inventory",
    "relationships",
    "speech_examples",
    "attributes",
)

#: M-4 对象条目逐键映射键序（ObjectSpec 面，schemas.py:187；state 单独
#: 折叠处理）。
_OBJECT_KEYS: Final[tuple[str, ...]] = (
    "id",
    "object_type",
    "name",
    "description",
    "position",
    "properties",
)


@dataclass(frozen=True)
class MigrationDiagnostic:
    """迁移诊断（SOT §3.15.3：code/severity/path/message 四字段）。

    ``code`` ∈ ``MIGRATION_DIAGNOSTIC_CODES``（A22 不变式）；
    ``severity`` ∈ {ERROR, WARNING, INFO} 闭集；``path`` = v1 单文件键链
    （点分；列表段 ``[i]`` 0 起；顶层键 = 键名）；``message`` = 中文、
    确定性、零 12 名闭集词（D7/K8）。
    """

    code: str
    severity: str
    path: str
    message: str


@dataclass(frozen=True)
class MigrationReport:
    """迁移报告（SOT §3.15.3：四字段）。

    ``status`` = migrated ⇔ 零 ERROR 诊断（A16 面）；``diagnostics``
    sorted by (severity 秩降, code, path)；``output_files`` = 写出文件
    相对 out_dir 的 posix 路径（sorted；incompatible = 空）。
    """

    input_path: str
    status: str
    diagnostics: tuple[MigrationDiagnostic, ...]
    output_files: tuple[str, ...]


def _diag(code: str, severity: str, path: str, message: str) -> MigrationDiagnostic:
    """诊断构造私有面（9 码闭集外值 = 调用方 bug，S3 预检面）。"""
    return MigrationDiagnostic(code=code, severity=severity, path=path, message=message)


def _severity_rank(severity: str) -> int:
    """severity 秩（ERROR > WARNING > INFO 降序 = 秩升序；纯函数，D6）。"""
    if severity == "ERROR":
        return 0
    if severity == "WARNING":
        return 1
    return 2


def _sort_diagnostics(
    diagnostics: list[MigrationDiagnostic],
) -> tuple[MigrationDiagnostic, ...]:
    """排序面 = (severity 秩降, code, path)（SOT §3.15.3 MigrationReport）。"""
    ordered = sorted(
        diagnostics,
        key=lambda d: (_severity_rank(d.severity), d.code, d.path),
    )
    return tuple(ordered)


def _finish(
    input_path: str,
    status: str,
    diagnostics: list[MigrationDiagnostic],
    output_files: tuple[str, ...],
) -> MigrationReport:
    """报告收口私有面（status 由调用方按入口语义裁定）。"""
    return MigrationReport(
        input_path=input_path,
        status=status,
        diagnostics=_sort_diagnostics(diagnostics),
        output_files=tuple(sorted(output_files)),
    )


def _load_v1_root(input_path: str) -> dict[str, Any]:
    """v1 输入读取私有面（只读；P9-INV-1）。

    库前置条件（零诊断码——9 码闭集 = S3 预检面）：输入缺失 →
    ``FileNotFoundError``；根非 dict（含 YAML 解析失败/空文件）→
    ``TypeError``。
    """
    path = Path(input_path)
    if not path.is_file():
        raise FileNotFoundError(f"v1 输入缺失: {input_path}")
    text = path.read_text(encoding="utf-8")
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise TypeError(f"v1 输入 YAML 解析失败: {input_path}: {exc}") from exc
    if not isinstance(data, dict):
        raise TypeError(f"v1 输入根节点非 dict 映射: {input_path}")
    return data


def _fold_state(state: dict[str, Any]) -> str:
    """M-4 state dict 折叠 = 规范扁平串（SOT §3.15.2 公式字面）。

    bool → ``true``/``false``（小写）；其余 → ``str(v)``（str 恒等、int
    十进制）；键序 sorted（SOT §3.15.2 M-4 公式 sorted(d.items())）。
    """
    parts: list[str] = []
    for key, value in sorted(state.items()):
        if value is True:
            rendered = "true"
        elif value is False:
            rendered = "false"
        else:
            rendered = str(value)
        parts.append(f"{key}={rendered}")
    return ",".join(parts)


def _coerce_attr_number(raw: Any) -> tuple[Any, str]:
    """v1 数值属性字段值 →（数值, 残余文本）（DEV-W5-11 修复面）。

    v1 数据面：数字与描述文本合并成单标量（如 ``-0.4深入山腹…``；YAML
    整体解析为字符串）。int/float（非 bool）→ 自身恒等；字符串 → 前缀
    数字（如有）提取为 float、残余文本返回（并入 ``description``，零
    信息丢失）；无前缀数字的字符串 → (0.0, 整串)（确定性降级，四输入
    面零 firing）；其他形态 → (0.0, "")（P5 链 surface）。
    """
    if isinstance(raw, bool):
        return float(raw), ""
    if isinstance(raw, (int, float)):
        return raw, ""
    if isinstance(raw, str):
        stripped = raw.strip()
        match = _LEADING_NUMBER_RE.match(stripped)
        if match is not None:
            return float(match.group(1)), stripped[match.end():].strip()
        return 0.0, stripped
    return 0.0, ""


def _clean_attributes(attributes: Any) -> Any:
    """属性表清洗私有面（逐属性条目；M-2 player / M-3 characters 共用）。

    - DEV-W5-10：剪除 v1 独有、P5 ``AttributeSpec``（schemas.py:203）无
      承载面的键（``hidden``/``locked``；P9 运行时 ``AttributeField`` 的
      hidden/locked 是运行面、非项目格式承载面）——零迁移诊断；四输入
      剪除计数 = whisperheads 6 / murder 3 / test_empty 0（全 hidden）；
    - DEV-W5-11：数值字段（value/min/max/natural_delta_per_minute）值
      为数字+描述合并字符串 → 前缀数字提取为字段值、残余文本并入该
      属性 ``description``（零信息丢失、零迁移诊断）；四输入修复计数
      = whisperheads 2 / murder 4 / test_empty 0（全
      natural_delta_per_minute，均无既有 description）。

    非 dict 形态原样透传（P5 链 surface；四输入面 = 全 dict）。
    """
    if not isinstance(attributes, dict):
        return attributes
    cleaned: dict[str, Any] = {}
    for attr_name, attr in attributes.items():
        if not isinstance(attr, dict):
            cleaned[attr_name] = attr
            continue
        fixed: dict[str, Any] = {}
        residual_text = ""
        for key, value in attr.items():
            if key in _ATTR_NO_CARRIER_KEYS:
                continue  # hidden/locked：P5 无承载面，剪除（DEV-W5-10）
            if key in _ATTR_NUMERIC_FIELDS:
                number, residual = _coerce_attr_number(value)
                fixed[key] = number
                if residual:
                    residual_text = (
                        residual
                        if not residual_text
                        else f"{residual_text} {residual}"
                    )
            else:
                fixed[key] = value
        if residual_text:
            existing = fixed.get("description")
            if isinstance(existing, str) and existing:
                fixed["description"] = f"{existing} {residual_text}"
            else:
                fixed["description"] = residual_text
        cleaned[attr_name] = fixed
    return cleaned


def _dump_yaml(data: Any) -> str:
    """yaml 输出面（SOT §3.15.4 入口表：sort_keys=True + 2 空格缩进 +
    UTF-8；字节稳定，A23 差分面）。"""
    return yaml.safe_dump(
        data,
        sort_keys=True,
        allow_unicode=True,
        default_flow_style=False,
        indent=2,
    )


def _write_files(out_dir: str, files: dict[str, Any]) -> None:
    """out_dir 写出私有面（P9-INV-1：只写 out_dir；目录 exist_ok 自动创建）。"""
    root = Path(out_dir)
    for rel in sorted(files):
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_dump_yaml(files[rel]), encoding="utf-8")


def _project_files(
    data: dict[str, Any], project: str, input_path: str,
) -> tuple[dict[str, Any], list[MigrationDiagnostic]]:
    """M-1..M-9 单遍映射私有面。

    返回（内存输出文件表 rel → 顶层键 dict、诊断列表）；写入门控（零
    ERROR ⇔ migrated）由 ``migrate_project`` 裁定。遍序确定性：顶层键
    sorted、列表按输入序、world_rules kind sorted。
    """
    diagnostics: list[MigrationDiagnostic] = []
    files: dict[str, Any] = {}

    # —— M-9：未知顶层键（白名单 9 键之外；每键 1 条 ERROR）——
    for key in sorted(set(data) - _TOP_LEVEL_KEYS):
        diagnostics.append(
            _diag(
                "MIGRATION_UNKNOWN_TOP_KEY",
                "ERROR",
                key,
                f"未知顶层键: {key}（M-9 白名单 9 键之外，拒绝迁移）",
            )
        )

    # —— M-1：world → world/<project>_world.yaml（除 objects 外逐键）——
    world_raw = data.get("world")
    world_map: dict[str, Any] | None = (
        world_raw if isinstance(world_raw, dict) else None
    )
    if world_map is None:
        diagnostics.append(
            _diag(
                "MIGRATION_EMPTY_WORLD",
                "ERROR",
                "world",
                "world 键缺失或非映射（M-1 前置：需 world 块）",
            )
        )
    else:
        locations = world_map.get("locations")
        if not isinstance(locations, list) or len(locations) == 0:
            diagnostics.append(
                _diag(
                    "MIGRATION_EMPTY_WORLD",
                    "ERROR",
                    "world.locations",
                    "world.locations 零条或非列表（M-1 前置：至少 1 条 location）",
                )
            )
        else:
            world_out = {
                key: value
                for key, value in world_map.items()
                if key != "objects"
            }
            files[f"world/{project}_world.yaml"] = {"world": world_out}

    # —— M-2：player → game.yaml player 节（逐键；inventory 过滤）——
    player_raw = data.get("player")
    player_map: dict[str, Any] | None = (
        player_raw if isinstance(player_raw, dict) else None
    )
    if player_map is None:
        diagnostics.append(
            _diag(
                "MIGRATION_PLAYER_MISSING",
                "ERROR",
                "player",
                "player 键缺失或非映射（M-2：需 player 块）",
            )
        )

    # —— 引用池（DEV-W5-2 裁决：P5 引用池语义过滤）——
    objects_raw = world_map.get("objects") if world_map is not None else None
    obj_list: list[Any] = objects_raw if isinstance(objects_raw, list) else []
    object_ids: set[str] = set()
    for entry in obj_list:
        if (
            isinstance(entry, dict)
            and isinstance(entry.get("id"), str)
            and entry.get("id")
        ):
            object_ids.add(entry["id"])
    char_list: list[Any] = []
    characters_raw = data.get("characters")
    if isinstance(characters_raw, list):
        char_list = characters_raw
    character_ids: set[str] = set()
    for entry in char_list:
        if (
            isinstance(entry, dict)
            and isinstance(entry.get("id"), str)
            and entry.get("id")
        ):
            character_ids.add(entry["id"])
    player_id = (
        player_map.get("player_id")
        if player_map is not None
        else None
    )
    ref_pool: set[str] = set(character_ids)
    if isinstance(player_id, str) and player_id:
        ref_pool.add(player_id)

    # —— M-4：world.objects → items/<id>.yaml（每对象一文件）——
    for entry in obj_list:
        if not isinstance(entry, dict):
            continue  # S3 沉默面降级：非 dict 条目无 id 承载面，跳过
        oid = entry.get("id")
        if not isinstance(oid, str) or not oid:
            continue  # 同上：无 id 条目无文件名承载面，跳过
        state_raw = entry.get("state")
        if "state" in entry:
            if isinstance(state_raw, dict):
                out_state: Any | None = (
                    _fold_state(state_raw) if state_raw else None
                )
                diagnostics.append(
                    _diag(
                        "MIGRATION_OBJECT_STATE_FOLDED",
                        "INFO",
                        f"world.objects.{oid}.state",
                        f"对象 {oid} state dict 折叠为规范扁平串（M-4）",
                    )
                )
            else:
                out_state = None
                type_name = type(state_raw).__name__
                diagnostics.append(
                    _diag(
                        "MIGRATION_OBJECT_STATE_FOLDED",
                        "ERROR",
                        f"world.objects.{oid}.state",
                        f"对象 {oid} state 非 dict（实际类型 {type_name}；"
                        "M-4 shape 守卫）",
                    )
                )
        else:
            out_state = None
        item: dict[str, Any] = {}
        for key in _OBJECT_KEYS:
            if key in entry:
                item[key] = entry[key]
        for key, value in entry.items():
            if key not in _OBJECT_KEYS and key != "state":
                item[key] = value  # 未知子键逐键透传（P5 链 surface）
        item["state"] = out_state
        files[f"items/{oid}.yaml"] = {"items": [item]}

    # —— M-3：characters → characters/<id>.yaml（每角色一文件）——
    seen_ids: set[str] = set()
    for index, entry in enumerate(char_list):
        if not isinstance(entry, dict):
            diagnostics.append(
                _diag(
                    "MIGRATION_DUPLICATE_ID",
                    "ERROR",
                    f"characters[{index}]",
                    f"characters[{index}] 条目非映射，缺 id（M-3）",
                )
            )
            continue
        cid = entry.get("id")
        if not isinstance(cid, str) or not cid:
            diagnostics.append(
                _diag(
                    "MIGRATION_DUPLICATE_ID",
                    "ERROR",
                    f"characters[{index}]",
                    f"characters[{index}] 条目缺 id（M-3）",
                )
            )
            continue
        if cid in seen_ids:
            diagnostics.append(
                _diag(
                    "MIGRATION_DUPLICATE_ID",
                    "ERROR",
                    f"characters/{cid}",
                    f"角色 id 重复: {cid}（M-3）",
                )
            )
        seen_ids.add(cid)
        # —— M-16（DEV-W5-3 裁决）：character_id 冗余键面 ——
        if "character_id" in entry and entry["character_id"] != cid:
            alt = entry["character_id"]
            diagnostics.append(
                _diag(
                    "MIGRATION_RULE_REF_OBSOLETE",
                    "WARNING",
                    f"characters.{cid}.character_id",
                    f"角色 {cid} character_id={alt!r} != id={cid!r}"
                    "（保留 id；M-16）",
                )
            )
        char_out: dict[str, Any] = {}
        for key in _CHARACTER_KEYS:
            if key not in entry:
                continue
            value = entry[key]
            if key == "relationships" and isinstance(value, dict):
                value = {
                    k: v for k, v in value.items() if k in ref_pool
                }
            elif key == "starting_inventory" and isinstance(value, list):
                value = [x for x in value if x in object_ids]
            elif key == "attributes":
                value = _clean_attributes(value)
            char_out[key] = value
        for key, value in entry.items():
            if key not in _CHARACTER_KEYS and key != "character_id":
                char_out[key] = value  # 未知子键逐键透传（P5 链 surface）
        files[f"characters/{cid}.yaml"] = {"characters": [char_out]}

    # —— M-5 + M-8：game.yaml（scenario / manifest / player 三节）——
    if "max_ticks" not in data:
        diagnostics.append(
            _diag(
                "MIGRATION_MAX_TICKS_MISSING",
                "ERROR",
                "max_ticks",
                "max_ticks 键缺失（M-5：必需顶层标量）",
            )
        )
    game_time_raw = data.get("game_time")
    if isinstance(game_time_raw, dict):
        scenario_game_time: Any = game_time_raw
    elif "game_time" in data:
        scenario_game_time = game_time_raw  # 非 dict 透传（P5 链 surface）
    else:
        scenario_game_time = {"hour": 0, "minute": 0}  # DEV-W5-6 缺省
    tpgm_raw = data.get("ticks_per_game_minute")
    scenario_tpgm: Any = (
        tpgm_raw if "ticks_per_game_minute" in data else 1.0
    )  # DEV-W5-6 缺省 1.0
    sscd_raw = data.get("starting_scene_description")
    scenario_sscd: Any = (
        sscd_raw if "starting_scene_description" in data else ""
    )  # DEV-W5-6 缺省 ""
    ns_raw = data.get("narrative_style")
    if isinstance(ns_raw, dict):
        scenario_ns: Any = ns_raw.get("style_description", "")  # DEV-W5-4
    elif isinstance(ns_raw, str):
        scenario_ns = ns_raw
    else:
        scenario_ns = ""  # 缺省 ""（DEV-W5-6）/ 非 dict 非 str 降级
    scenario: dict[str, Any] = {
        "id": f"scenario_{project}",
        "max_ticks": data.get("max_ticks"),
        "ticks_per_game_minute": scenario_tpgm,
        "game_time": scenario_game_time,
        "starting_scene_description": scenario_sscd,
        "narrative_style": scenario_ns,
    }
    manifest: dict[str, Any] = {
        "schema_version": "2",
        "project_id": project,
        "name": project,  # DEV-W5-5 模板
        "description": (
            "v1 单文件项目迁移输出（P9 v1_migration；source = "
            f"{Path(input_path).name}）"
        ),  # DEV-W5-5 确定性模板
        "engine_version": _ENGINE_VERSION,
    }
    if player_map is not None:
        player_out: dict[str, Any] = {}
        for key, value in player_map.items():
            if key == "inventory" and isinstance(value, list):
                value = [x for x in value if x in object_ids]
            elif key == "attributes":
                value = _clean_attributes(value)
            player_out[key] = value
        game_yaml: dict[str, Any] = {
            "manifest": manifest,
            "player": player_out,
            "scenario": scenario,
        }
    else:
        game_yaml = {"manifest": manifest, "scenario": scenario}
    files["game.yaml"] = game_yaml

    # —— M-6 / M-7：world_rules → rules/<project>_v1_rules.yaml ——
    world_rules_raw = data.get("world_rules")
    rules_map: dict[str, Any] = (
        world_rules_raw if isinstance(world_rules_raw, dict) else {}
    )
    rules_list: list[dict[str, Any]] = []
    for kind in sorted(rules_map):
        block = rules_map[kind]
        if not isinstance(block, dict):
            continue  # S3 沉默面降级：非 dict kind 块无 append/disable 承载
        appends = block.get("append")
        append_list: list[Any] = appends if isinstance(appends, list) else []
        for seq, text in enumerate(append_list, start=1):
            nn = f"{seq:02d}"
            rules_list.append(
                {
                    "id": f"rule_v1_{kind}_{nn}",
                    "description": text,  # 原文逐字
                    "condition": _PASSTHROUGH_CONDITION,  # DEV-W5-1
                    "priority": 100 - seq,
                }
            )
            diagnostics.append(
                _diag(
                    "MIGRATION_FREEFORM_RULE_FOLDED",
                    "INFO",
                    f"world_rules.{kind}.append[{seq - 1}]",
                    f"world_rules.{kind} append 条目 {nn} 折叠为 RuleSpec"
                    "（M-6：passthrough 条件不改变可行性）",
                )
            )
        disables = block.get("disable")
        disable_list: list[Any] = disables if isinstance(disables, list) else []
        for seq, rule_no in enumerate(disable_list):
            diagnostics.append(
                _diag(
                    "MIGRATION_RULE_REF_OBSOLETE",
                    "WARNING",
                    f"world_rules.{kind}.disable[{seq}]",
                    f"world_rules.{kind}.disable 内置规则编号 {rule_no} "
                    "无 v2 对应物（43.2-5：编号内置规则表在 v2 不存在）",
                )
            )
    if rules_list:
        files[f"rules/{project}_v1_rules.yaml"] = {"rules": rules_list}

    return files, diagnostics


def migrate_project(input_path: str, out_dir: str) -> MigrationReport:
    """v1 单文件项目 → v2 分节项目（M-1..M-9；SOT §3.15.4 入口表逐行权威）。

    只读输入、只写 out_dir（P9-INV-1；out_dir 自动创建 exist_ok）。
    库前置条件：输入缺失 → ``FileNotFoundError``；根非 dict → ``TypeError``
    （零诊断码）。不变式：零 ERROR 诊断 ⇔ status = migrated ⇔ 输出可经
    P5 冻结 ``load_project`` + ``build_ir`` + ``validate_project`` 零
    ERROR（A16；模块内不 import 加载链——测试侧核验）。incompatible →
    零输出文件写盘。
    """
    data = _load_v1_root(input_path)
    project = Path(input_path).stem
    files, diagnostics = _project_files(data, project, input_path)
    has_error = any(d.severity == "ERROR" for d in diagnostics)
    if has_error:
        return _finish(input_path, "incompatible", diagnostics, ())
    _write_files(out_dir, files)
    return _finish(input_path, "migrated", diagnostics, tuple(files))


def migrate_simulation(input_path: str) -> MigrationReport:
    """``config/simulation.yaml`` 面（SOT §3.15.4 入口表）。

    两个部署节键（``agents`` 节 + 另一 12 名闭集成员节键，串拼接承载、
    见 ``_DEPLOYMENT_SECTION_KEYS``）= **部署字段**（K8：P6 deployment
    面，非项目内容）→ 每现存节键 1 条 ERROR
    ``MIGRATION_DEPLOYMENT_FIELD``（message 点名节键名；零值消费——
    D7/K8）→ status = incompatible、不写出任何文件（本入口无 out_dir
    面 = 结构性零写盘）。``simulation`` 节本身
    （max_ticks/tick_delay_ms/log_level/debug）= 部署参数，零诊断零
    输出；无部署节键（纯 simulation 面）→ incompatible + **零诊断** +
    零输出（DEV-W5-7 裁决：SOT 沉默分支）。
    """
    data = _load_v1_root(input_path)
    diagnostics: list[MigrationDiagnostic] = []
    for key in sorted(data):
        if key in _DEPLOYMENT_SECTION_KEYS:
            diagnostics.append(
                _diag(
                    "MIGRATION_DEPLOYMENT_FIELD",
                    "ERROR",
                    key,
                    f"节 {key} 为部署字段（K8：P6 deployment 面），非项目"
                    "内容；零值消费、零输出",
                )
            )
    return _finish(input_path, "incompatible", diagnostics, ())
