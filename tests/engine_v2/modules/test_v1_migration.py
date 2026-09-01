"""P9 W5 v1_migration 模块单测（SOT §6.1：t1–t7 共 7 函数；T09）。

设计依据 = ``docs/v2/contracts/P9-official-modules-migration-design.md``
§3.15（映射规则 M-1..M-9 / 诊断 9 码闭集 / 入口 + 四输入表 L950–963）
+ §6.1（测试表 L1590–1598）+ A16/A22（L1458/L1464）+ AD-P9-2（L1663）。

零 fixture 纪律（任务书 §0/§1.3）：4 输入 = 仓库既有 v1 源
（``public_start/*.yaml`` / ``config/simulation.yaml``，只读，路径常量
相对 repo root）+ ``tmp_path`` 输出目录；t6 敌对夹具 = 测试内 yaml
字符串字面量 + ``tmp_path`` 写盘。**不改** ``conftest.py``（p9_host /
p9_world_builder = W6 落盘面，§6.2）。

A16 链面（W4 先例 ``tests/engine_v2/content/test_p5_integration.py:45–52``
``_chain`` 同形）：``load_project`` → ``build_ir`` →
``validate_project``；raw/ir 非 None + 三阶段零 error 级诊断 +
``result.ok``。

偏差披露（Leader 已裁决 / W5 dev 登记，任务书 §4 逐字面）：

- DEV-W5-2（引用完整性面）：v1 ``relationships`` 键 /
  ``player.inventory`` 元素 / ``character.starting_inventory`` 元素 =
  v1 自由形态（v1 零引用校验），含不解析引用 → P5
  ``check_references``（validator.py:236）对悬空引用产
  ``LLMSIM_UNRESOLVED_REF`` ERROR → 忠实逐键映射破坏 A16 → 按 P5
  引用池语义过滤（relationships 键 ∈ 本项目全部 character id ∪
  {player_id} 保留、余剪除；inventory/starting_inventory 元素 ∈
  object id 池保留、余剪除）。剪除 = 零迁移诊断（9 码闭集无承载面）；
  剪除计数 = whisperheads 29（7+4+18）/ murder 27（9+6+12）/
  test_empty 0（Leader 实测、W5 dev 复测确认）。备选（否）：忠实逐键
  映射不过滤（否因：悬空引用经 P5 check_references 产
  LLMSIM_UNRESOLVED_REF ERROR → 破坏 A16）。
- DEV-W5-1（M-6 passthrough）：SOT 字面 ``'if(1 >= 0, allowed)'`` 实测
  经 P5 冻结 ``parse_dsl``（rule_module.py:812）失败（ast=None +
  ``LLMSIM_DSL_PARSE``「if(...) 缺少 else 输出」）→ 裁决最小修正
  ``'if(1 >= 0, allowed; blocked)'``（t4 钉）。备选（否）：SOT 字面
  passthrough（否因：即本条实测所证 parse_dsl 失败 → 破坏 A16）。
- DEV-W5-9（§6.1 t2 锚漂移）：SOT t2 行钉值 = 完整折叠串（首对象 =
  ``closed=true,unlocked=true``，oak_door 2 键）；完整折叠串 = M-4
  公式 × 实际 yaml 字节（各对象 state dict 均 2 键，实测确认）→ 本文件
  钉**完整串**（W3 DEV-W3-10 同族）。备选（否）：测试钉 SOT t2 行
  首键摘要（否因：SOT L1593 首对象钉值 = 完整折叠串，钉摘要与 SOT 行
  值级矛盾且丢第 2 键信息）。
- DEV-W5-10（W5 dev 登记）：v1 属性逐条目内 ``hidden`` 键（P5
  ``AttributeSpec`` 无承载面，extra="forbid" 实测拒收）→ 剪除，零诊断；
  四输入 = whisperheads 6 / murder 3 / test_empty 0。备选（否）：保留
  hidden/locked 键映射为 P5 扩展字段（否因：P5 AttributeSpec
  extra="forbid" 字段封闭，无承载面 → 拒收破坏 A16）。
- DEV-W5-11（W5 dev 登记）：v1 属性 ``natural_delta_per_minute`` 数字+
  描述合并单标量面 → 前缀数字提取 + 残余文本并入 description，零诊断；
  四输入 = whisperheads 2 / murder 4 / test_empty 0。备选（否）：数值
  缺省 0.0 + 全串入 description（否因：丢真实 delta 值）；原样透传
  （否因：P5 AttributeSpec float 校验必产 LLMSIM_SCHEMA → 破坏 A16）。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import src.engine_v2.modules.v1_migration as v1m
from src.engine_v2.content.loader import load_project
from src.engine_v2.content.project_ir import build_ir
from src.engine_v2.content.validator import validate_project
from src.engine_v2.modules.v1_migration import (
    MIGRATION_DIAGNOSTIC_CODES,
    migrate_project,
    migrate_simulation,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_TEST_EMPTY = _REPO_ROOT / "public_start" / "test_empty.yaml"
_WHISPERHEADS = _REPO_ROOT / "public_start" / "whisperheads.yaml"
_MURDER = _REPO_ROOT / "public_start" / "murder.yaml"
_SIMULATION = _REPO_ROOT / "config" / "simulation.yaml"

#: K8 12 名闭集成员节键（串拼接自证豁免；validator.py:87–103 先例；
#: 测试侧非扫描面但同源纪律保持）。
_SIM_LLM_SECTION = "ll" + "m"

#: t1 钉面：test_empty 输出 6 文件（sorted 逐字；SOT §3.15.3
#: output_files = sorted）。DEV-W5-12 披露：任务书 §1.3 t1 钉元组将
#: ``items/old_parchments.yaml`` 置于 ``items/oak_door.yaml`` 之前 =
#: 非 sorted 序（Python ``sorted`` 面 ``oak`` < ``old``，'a' < 'l'）→
#: 按 SOT「sorted」落位（任务书与 SOT 冲突以 SOT 为准并上报）。
#: 备选（否）：保留任务书 §1.3 t1 钉元组原序（否因：非 sorted 序，
#: 与 SOT §3.15.3 output_files = sorted 矛盾）。
_TEST_EMPTY_OUTPUT_FILES = (
    "game.yaml",
    "items/light_crystal.yaml",
    "items/oak_door.yaml",
    "items/old_parchments.yaml",
    "items/wooden_crates.yaml",
    "world/test_empty_world.yaml",
)

#: t1 钉面：whisperheads 输出 19 文件（sorted 逐字）。
_WHISPERHEADS_OUTPUT_FILES = (
    "characters/euphrati_keeler.yaml",
    "characters/ignace_karkasy.yaml",
    "characters/kyril_sindermann.yaml",
    "characters/maloghurst.yaml",
    "characters/nero_vipus.yaml",
    "characters/rassek.yaml",
    "characters/xavyer_jubal.yaml",
    "game.yaml",
    "items/ancient_stele.yaml",
    "items/jubal_chainsword.yaml",
    "items/keeler_picter.yaml",
    "items/loken_oath_papers.yaml",
    "items/mountain_shrine.yaml",
    "items/rebel_ammo_cache.yaml",
    "items/sentry_gun.yaml",
    "items/stormbird_landed.yaml",
    "items/terminus_armor_rassek.yaml",
    "rules/whisperheads_v1_rules.yaml",
    "world/whisperheads_world.yaml",
)

#: t1 钉面：murder 输出 20 文件（sorted 逐字）。
_MURDER_OUTPUT_FILES = (
    "characters/blood_angel_survivor.yaml",
    "characters/bulle.yaml",
    "characters/lord_eidolon.yaml",
    "characters/lucius.yaml",
    "characters/sakian.yaml",
    "game.yaml",
    "items/blood_angel_helm.yaml",
    "items/drop_pod_13.yaml",
    "items/eidolon_command_pod.yaml",
    "items/explosive_cache.yaml",
    "items/frome_last_transmission_relay.yaml",
    "items/gene_seed_extraction_device.yaml",
    "items/lucius_sword.yaml",
    "items/megarachnid_blade_limb.yaml",
    "items/megarachnid_warrior_corpse.yaml",
    "items/tarik_torgaddon_beacon.yaml",
    "items/thorn_tree_first.yaml",
    "items/wounded_brother_sakian.yaml",
    "rules/murder_v1_rules.yaml",
    "world/murder_world.yaml",
)

#: t2 钉面：test_empty 4 对象 M-4 折叠完整串（DEV-W5-9：SOT t2 行
#: 钉值 = 完整折叠串，本钉 = 公式 × 实际 yaml 字节）。
_TEST_EMPTY_STATE_PINS = {
    "oak_door": "closed=true,unlocked=true",
    "light_crystal": "glowing=true,temperature=warm",
    "old_parchments": "aged=true,readable=true",
    "wooden_crates": "one_open=true,two_sealed=true",
}

#: t4 钉面：murder 10 条 append 原文逐字（v1 源 :787–791/:795–799；
#: 键序 = rules 文件写序 = kind sorted：attribute 01–05 →
#: physics 01–05）。
_MURDER_RULE_DESCRIPTIONS = {
    "rule_v1_attribute_01": (
        "在巨蛛族幼虫区域停留时：lucidity每tick下降1-2点"
        "（持续的低频嘶嘶声对被基因强化的阿斯塔特感官有不可解释的干扰效应）。"
    ),
    "rule_v1_attribute_02": (
        "摧毁一棵棘刺树时：所有在场角色的resolve恢复5-10点，"
        "小队凝聚力上升3-5点（破坏异形结构的象征性胜利）。"
    ),
    "rule_v1_attribute_03": (
        "在地下巢穴（underground_nest_entrance、brood_chamber）中时："
        "storm_tolerance每tick下降1-3点"
        "（因暴露于浓缩的生物毒素和高强度电离辐射中）。"
    ),
    "rule_v1_attribute_04": (
        "每当回收一具阿斯塔特遗体的基因种子时：gene_seed_samples上升"
        "1-3点，honor_integrity上升1-2点；如果放弃回收可能的情况则"
        "honor_integrity下降5-10点。"
    ),
    "rule_v1_attribute_05": (
        "每有一位战友在战斗中阵亡：squad_cohesion下降3-5点，"
        "resolve下降1-2点；如果阵亡是艾多伦的错误命令导致，"
        "全员对艾多伦的好感下降0.05-0.1。"
    ),
    "rule_v1_physics_01": (
        "11. **离子风暴干扰**：谋杀星的电离风暴对所有电子设备和通讯"
        "造成持续性干扰。远距离（超过1公里）的无线电通讯自动失效，"
        "除非在风暴暂停区域（棘刺树被摧毁后形成的风眼）内。"
    ),
    "rule_v1_physics_02": (
        "12. **棘刺树与天气关联**：白石化棘刺巨树是巨蛛族控制天气的"
        "生物发生器。摧毁一棵或一群棘刺树会导致该区域内风暴暂停，"
        "天空暂时放晴，为轨道通讯和空降提供窗口。"
    ),
    "rule_v1_physics_03": (
        "13. **巨蛛族幼虫预警系统**：当巨蛛族战士形态靠近时，"
        "附着在草茎根部的黑色幼虫囊会突然停止嘶嘶声，"
        "同时巨草茎开始快速高频颤栗。这是一种提前预警信号——"
        "但只给5到10秒的反应时间。"
    ),
    "rule_v1_physics_04": (
        "14. **巨蛛族尸体回收**：巨蛛族会迅速回收战场上同类的尸体"
        "和断肢。任何被留在战场上的巨蛛族尸体（超过30分钟未被回收）"
        "要么意味着该区域被它们放弃，要么意味着有某种更强的力量"
        "阻止了它们——两种情况都值得调查。"
    ),
    "rule_v1_physics_05": (
        "15. **胶结物腐蚀性**：巨蛛族工蚁形态分泌的乳白色胶结物"
        "在新鲜状态下具有强腐蚀性——接触未凝固的胶结物会导致"
        "动力甲陶瓷层被缓慢侵蚀。完全凝固后则形成接近钻石硬度的"
        "惰性物质。"
    ),
}

#: S1 同键自证用 severity 秩（SOT §3.15.3 L942 排序 = severity 降秩
#: ERROR>WARNING>INFO, code, path → 键取负秩升序）。
_SEVERITY_RANK = {"ERROR": 2, "WARNING": 1, "INFO": 0}

#: t1 钉面（S1）：whisperheads 迁移报告诊断 (severity, code, path)
#: 有序元组逐字（WARNING ×1 在首 = M-15 physics.disable [8]；其后
#: M-13 INFO ×8（kind sorted：attribute 01–03 → physics 01–05）+
#: M-10 INFO ×9（path sorted）；共 18 条）。
_WH_DIAG_ORDER = (
    ("WARNING", "MIGRATION_RULE_REF_OBSOLETE", "world_rules.physics.disable[0]"),
    ("INFO", "MIGRATION_FREEFORM_RULE_FOLDED", "world_rules.attribute.append[0]"),
    ("INFO", "MIGRATION_FREEFORM_RULE_FOLDED", "world_rules.attribute.append[1]"),
    ("INFO", "MIGRATION_FREEFORM_RULE_FOLDED", "world_rules.attribute.append[2]"),
    ("INFO", "MIGRATION_FREEFORM_RULE_FOLDED", "world_rules.physics.append[0]"),
    ("INFO", "MIGRATION_FREEFORM_RULE_FOLDED", "world_rules.physics.append[1]"),
    ("INFO", "MIGRATION_FREEFORM_RULE_FOLDED", "world_rules.physics.append[2]"),
    ("INFO", "MIGRATION_FREEFORM_RULE_FOLDED", "world_rules.physics.append[3]"),
    ("INFO", "MIGRATION_FREEFORM_RULE_FOLDED", "world_rules.physics.append[4]"),
    ("INFO", "MIGRATION_OBJECT_STATE_FOLDED", "world.objects.ancient_stele.state"),
    ("INFO", "MIGRATION_OBJECT_STATE_FOLDED", "world.objects.jubal_chainsword.state"),
    ("INFO", "MIGRATION_OBJECT_STATE_FOLDED", "world.objects.keeler_picter.state"),
    ("INFO", "MIGRATION_OBJECT_STATE_FOLDED", "world.objects.loken_oath_papers.state"),
    ("INFO", "MIGRATION_OBJECT_STATE_FOLDED", "world.objects.mountain_shrine.state"),
    ("INFO", "MIGRATION_OBJECT_STATE_FOLDED", "world.objects.rebel_ammo_cache.state"),
    ("INFO", "MIGRATION_OBJECT_STATE_FOLDED", "world.objects.sentry_gun.state"),
    ("INFO", "MIGRATION_OBJECT_STATE_FOLDED", "world.objects.stormbird_landed.state"),
    ("INFO", "MIGRATION_OBJECT_STATE_FOLDED", "world.objects.terminus_armor_rassek.state"),
)

#: t1 钉面（S1）：murder 迁移报告诊断 (severity, code, path) 有序元组
#: 逐字（零 WARNING；M-13 INFO ×10（attribute 01–05 → physics 01–05）
#: + M-10 INFO ×12（path sorted）；共 22 条）。
_MU_DIAG_ORDER = (
    ("INFO", "MIGRATION_FREEFORM_RULE_FOLDED", "world_rules.attribute.append[0]"),
    ("INFO", "MIGRATION_FREEFORM_RULE_FOLDED", "world_rules.attribute.append[1]"),
    ("INFO", "MIGRATION_FREEFORM_RULE_FOLDED", "world_rules.attribute.append[2]"),
    ("INFO", "MIGRATION_FREEFORM_RULE_FOLDED", "world_rules.attribute.append[3]"),
    ("INFO", "MIGRATION_FREEFORM_RULE_FOLDED", "world_rules.attribute.append[4]"),
    ("INFO", "MIGRATION_FREEFORM_RULE_FOLDED", "world_rules.physics.append[0]"),
    ("INFO", "MIGRATION_FREEFORM_RULE_FOLDED", "world_rules.physics.append[1]"),
    ("INFO", "MIGRATION_FREEFORM_RULE_FOLDED", "world_rules.physics.append[2]"),
    ("INFO", "MIGRATION_FREEFORM_RULE_FOLDED", "world_rules.physics.append[3]"),
    ("INFO", "MIGRATION_FREEFORM_RULE_FOLDED", "world_rules.physics.append[4]"),
    ("INFO", "MIGRATION_OBJECT_STATE_FOLDED", "world.objects.blood_angel_helm.state"),
    ("INFO", "MIGRATION_OBJECT_STATE_FOLDED", "world.objects.drop_pod_13.state"),
    ("INFO", "MIGRATION_OBJECT_STATE_FOLDED", "world.objects.eidolon_command_pod.state"),
    ("INFO", "MIGRATION_OBJECT_STATE_FOLDED", "world.objects.explosive_cache.state"),
    ("INFO", "MIGRATION_OBJECT_STATE_FOLDED", "world.objects.frome_last_transmission_relay.state"),
    ("INFO", "MIGRATION_OBJECT_STATE_FOLDED", "world.objects.gene_seed_extraction_device.state"),
    ("INFO", "MIGRATION_OBJECT_STATE_FOLDED", "world.objects.lucius_sword.state"),
    ("INFO", "MIGRATION_OBJECT_STATE_FOLDED", "world.objects.megarachnid_blade_limb.state"),
    ("INFO", "MIGRATION_OBJECT_STATE_FOLDED", "world.objects.megarachnid_warrior_corpse.state"),
    ("INFO", "MIGRATION_OBJECT_STATE_FOLDED", "world.objects.tarik_torgaddon_beacon.state"),
    ("INFO", "MIGRATION_OBJECT_STATE_FOLDED", "world.objects.thorn_tree_first.state"),
    ("INFO", "MIGRATION_OBJECT_STATE_FOLDED", "world.objects.wounded_brother_sakian.state"),
)

#: t3 钉面（S2/DEV-W5-2）：whisperheads 7 角色逐角色 relationships
#: 保留键集（源键集 ∩ (项目角色 id ∪ {player_id})；键序 = 输出钉序 =
#: sorted——sort_keys=True dump 面）。每角色剪除 1 悬空键
#: （garviel_loken ∉ 引用池）→ 各留 6；全项目保留总数 = 42
#: （源 7 角色 × 7 键 − 7 剪除；开发期自 v1 源实算）。
_WH_RETAINED_RELATIONSHIPS = {
    "euphrati_keeler": (
        "ignace_karkasy", "kyril_sindermann", "maloghurst",
        "nero_vipus", "rassek", "xavyer_jubal",
    ),
    "ignace_karkasy": (
        "euphrati_keeler", "kyril_sindermann", "maloghurst",
        "nero_vipus", "rassek", "xavyer_jubal",
    ),
    "kyril_sindermann": (
        "euphrati_keeler", "ignace_karkasy", "maloghurst",
        "nero_vipus", "rassek", "xavyer_jubal",
    ),
    "maloghurst": (
        "euphrati_keeler", "ignace_karkasy", "kyril_sindermann",
        "nero_vipus", "rassek", "xavyer_jubal",
    ),
    "nero_vipus": (
        "euphrati_keeler", "ignace_karkasy", "kyril_sindermann",
        "maloghurst", "rassek", "xavyer_jubal",
    ),
    "rassek": (
        "euphrati_keeler", "ignace_karkasy", "kyril_sindermann",
        "maloghurst", "nero_vipus", "xavyer_jubal",
    ),
    "xavyer_jubal": (
        "euphrati_keeler", "ignace_karkasy", "kyril_sindermann",
        "maloghurst", "nero_vipus", "rassek",
    ),
}

#: t1 钉面（S3/DEV-W5-11）：数字+描述合并标量命中属性逐字段钉
#: （whisperheads 2 + murder 4 = 6；全 natural_delta_per_minute 命中、
#: 均无既有 description 键 → description = 残余文本逐字；value/min/max
#: = 源值逐值；开发期实算）。键 = (项目, 属主 id, 属性名)。
_S3_ATTR_PINS = {
    ("whisperheads", "player", "vox_integrity"): {
        "value": 60.0,
        "min": 0.0,
        "max": 100.0,
        "natural_delta_per_minute": -0.4,
        "description": (
            "深入山腹越深，Samus的低语越强，通讯越不稳定；返回开阔地带或重启设备可恢复。"
        ),
    },
    ("whisperheads", "xavyer_jubal", "corruption_level"): {
        "value": 30.0,
        "min": 0.0,
        "max": 100.0,
        "natural_delta_per_minute": 0.6,
        "description": (
            "每tick自然增长3点。达到100时朱巴尔将彻底失控屠杀战友，尸体随后复生为混沌怪物。"
            "这是整个场景的核心叙事驱动。"
        ),
    },
    ("murder", "lucius", "narcissism"): {
        "value": 78.0,
        "min": 0.0,
        "max": 100.0,
        "natural_delta_per_minute": 0.04,
        "description": (
            "每次战斗胜利、被称赞或完成华丽击杀时上升。超过85时他会为了美感而非效率作战；"
            "超过95时他可能背弃战友以追求个人荣耀。"
        ),
    },
    ("murder", "lucius", "corruption_risk"): {
        "value": 15.0,
        "min": 0.0,
        "max": 100.0,
        "natural_delta_per_minute": 0.02,
        "description": (
            "使用异形武器、沉迷战斗快感或独自探索巨蛛族结构时上升。隐藏属性。"
            "达到100时他可能走上不可逆转的道路。"
        ),
    },
    ("murder", "sakian", "injury_severity"): {
        "value": 55.0,
        "min": 0.0,
        "max": 100.0,
        "natural_delta_per_minute": -0.4,
        "description": (
            "每tick自然恢复2点（基因强化愈合）。高于60时严重限制战斗能力；低于20时完全恢复。"
        ),
    },
    ("murder", "blood_angel_survivor", "physical_condition"): {
        "value": 25.0,
        "min": 0.0,
        "max": 100.0,
        "natural_delta_per_minute": -0.06,
        "description": "被断开连接后会缓慢恢复。低于10可能导致器官衰竭。",
    },
}


def _chain(root: Path) -> tuple[object, object, object, object]:
    """``load_project`` → ``build_ir`` → ``validate_project``（W4 先例
    test_p5_integration.py:45–52 同形；raw/ir 非 None 断言内置）。"""
    loaded = load_project(root)
    assert loaded.raw is not None, f"raw is None: {loaded.diagnostics}"
    built = build_ir(loaded.raw)
    assert built.ir is not None, f"ir is None: {built.diagnostics}"
    result = validate_project(built.ir, loaded.raw)
    return loaded, built, built.ir, result


def _assert_chain_clean(root: Path) -> None:
    """A16 链零 ERROR 面：三阶段零 error 级诊断 + ``result.ok``。"""
    loaded, built, _ir, result = _chain(root)
    for stage, diags in (
        ("load_project", loaded.diagnostics),
        ("build_ir", built.diagnostics),
        ("validate_project", result.diagnostics),
    ):
        errors = [d for d in diags if d.severity == "error"]
        assert not errors, f"{stage} error 级诊断: {errors}"
    assert result.ok is True, f"result.ok 非 True: {result.diagnostics}"


def _error_count(diagnostics) -> int:
    """error 级诊断计数（P5 DiagnosticSeverity str-Enum，字符串比较）。"""
    return sum(1 for d in diagnostics if d.severity == "error")


def test_t1_gate_migration_clause(tmp_path: Path) -> None:
    """A16（SOT §3.15.4 四输入表 L958–963）：四输入逐输入断言。

    钉面：test_empty → migrated + 恰 4 INFO（M-10）+ 6 文件逐字 +
    全链零 ERROR；whisperheads → migrated + 恰 1 WARNING（M-15 点名 8
    与 physics）+ 恰 17 INFO（M-13 ×8 + M-10 ×9）+ 19 文件逐字 +
    全链零 ERROR；murder → migrated + 零 WARNING + 恰 22 INFO
    （M-13 ×10 + M-10 ×12）+ 20 文件逐字 + 全链零 ERROR；
    simulation.yaml（migrate_simulation）→ incompatible + ≥1 ERROR
    MIGRATION_DEPLOYMENT_FIELD（12 名闭集成员节键与 agents 两节键均被
    点名）+
    ``output_files == ()``。补充钉面（R1 修正 S1/S3）：whisperheads/
    murder 诊断 (severity, code, path) 有序元组逐字 + 同键自证；
    DEV-W5-11 命中属性 6 处逐字段值级钉（提取 float + 残余文本并入
    description 逐字 + value/min/max 源值）。
    """
    # —— 输入 1：test_empty（154 行）——
    out_te = tmp_path / "te"
    rep_te = migrate_project(str(_TEST_EMPTY), str(out_te))
    assert rep_te.status == "migrated"
    assert len(rep_te.diagnostics) == 4
    assert all(d.severity == "INFO" for d in rep_te.diagnostics)
    assert all(
        d.code == "MIGRATION_OBJECT_STATE_FOLDED"
        for d in rep_te.diagnostics
    ), [d.code for d in rep_te.diagnostics]
    assert rep_te.output_files == _TEST_EMPTY_OUTPUT_FILES
    _assert_chain_clean(out_te)

    # —— 输入 2：whisperheads（897 行）——
    out_wh = tmp_path / "wh"
    rep_wh = migrate_project(str(_WHISPERHEADS), str(out_wh))
    assert rep_wh.status == "migrated"
    warns_wh = [d for d in rep_wh.diagnostics if d.severity == "WARNING"]
    infos_wh = [d for d in rep_wh.diagnostics if d.severity == "INFO"]
    assert len(warns_wh) == 1, [d.message for d in warns_wh]
    assert warns_wh[0].code == "MIGRATION_RULE_REF_OBSOLETE"
    assert "8" in warns_wh[0].message
    assert "physics" in warns_wh[0].message
    assert len(infos_wh) == 17, [d.code for d in infos_wh]
    assert (
        sum(
            1
            for d in infos_wh
            if d.code == "MIGRATION_FREEFORM_RULE_FOLDED"
        )
        == 8
    )
    assert (
        sum(
            1
            for d in infos_wh
            if d.code == "MIGRATION_OBJECT_STATE_FOLDED"
        )
        == 9
    )
    assert rep_wh.output_files == _WHISPERHEADS_OUTPUT_FILES
    # —— S1：whisperheads 诊断排序钉（SOT §3.15.3 L942：severity 降秩,
    # code, path）+ 同键自证 ——
    assert [
        (d.severity, d.code, d.path) for d in rep_wh.diagnostics
    ] == list(_WH_DIAG_ORDER), [(d.code, d.path) for d in rep_wh.diagnostics]
    assert rep_wh.diagnostics == tuple(
        sorted(
            rep_wh.diagnostics,
            key=lambda d: (-_SEVERITY_RANK[d.severity], d.code, d.path),
        )
    )
    _assert_chain_clean(out_wh)

    # —— 输入 3：murder（802 行）——
    out_mu = tmp_path / "mu"
    rep_mu = migrate_project(str(_MURDER), str(out_mu))
    assert rep_mu.status == "migrated"
    assert (
        sum(1 for d in rep_mu.diagnostics if d.severity == "WARNING") == 0
    )
    infos_mu = [d for d in rep_mu.diagnostics if d.severity == "INFO"]
    assert len(infos_mu) == 22, [d.code for d in infos_mu]
    assert (
        sum(
            1
            for d in infos_mu
            if d.code == "MIGRATION_FREEFORM_RULE_FOLDED"
        )
        == 10
    )
    assert (
        sum(
            1
            for d in infos_mu
            if d.code == "MIGRATION_OBJECT_STATE_FOLDED"
        )
        == 12
    )
    assert rep_mu.output_files == _MURDER_OUTPUT_FILES
    # —— S1：murder 诊断排序钉（同 SOT §3.15.3 L942 键）+ 同键自证 ——
    assert [
        (d.severity, d.code, d.path) for d in rep_mu.diagnostics
    ] == list(_MU_DIAG_ORDER), [(d.code, d.path) for d in rep_mu.diagnostics]
    assert rep_mu.diagnostics == tuple(
        sorted(
            rep_mu.diagnostics,
            key=lambda d: (-_SEVERITY_RANK[d.severity], d.code, d.path),
        )
    )
    _assert_chain_clean(out_mu)

    # —— S3（DEV-W5-11）：数字+描述合并标量命中属性逐字段值级钉 ——
    _loaded_wh, _built_wh, ir_wh, _result_wh = _chain(out_wh)
    _loaded_mu, _built_mu, ir_mu, _result_mu = _chain(out_mu)
    attrs_wh = {
        "player": ir_wh.player.attributes,
        **{c.id: c.attributes for c in ir_wh.characters},
    }
    attrs_mu = {
        "player": ir_mu.player.attributes,
        **{c.id: c.attributes for c in ir_mu.characters},
    }
    for (project, owner, aname), pin in _S3_ATTR_PINS.items():
        attrs = attrs_wh if project == "whisperheads" else attrs_mu
        attr = attrs[owner][aname]
        assert attr.value == pin["value"], (owner, aname, attr.value)
        assert attr.min == pin["min"], (owner, aname, attr.min)
        assert attr.max == pin["max"], (owner, aname, attr.max)
        assert (
            attr.natural_delta_per_minute
            == pin["natural_delta_per_minute"]
        ), (owner, aname)
        assert attr.description == pin["description"], (owner, aname)

    # —— 输入 4：config/simulation.yaml（23 行；migrate_simulation 面）——
    rep_sim = migrate_simulation(str(_SIMULATION))
    assert rep_sim.status == "incompatible"
    errs_sim = [
        d
        for d in rep_sim.diagnostics
        if d.severity == "ERROR"
        and d.code == "MIGRATION_DEPLOYMENT_FIELD"
    ]
    assert len(errs_sim) >= 1
    joined_sim = "\n".join(d.message for d in errs_sim)
    assert _SIM_LLM_SECTION in joined_sim
    assert "agents" in joined_sim
    assert rep_sim.output_files == ()


def test_t2_object_state_folded(tmp_path: Path) -> None:
    """M-4 折叠规范串逐值钉（test_empty 4 对象；DEV-W5-9 完整串面）。

    同钉：items 文件顶层键 = ``items``；ObjectSpec 面
    （id/object_type/name/description/position/properties 逐键透传）。
    """
    out = tmp_path / "te"
    migrate_project(str(_TEST_EMPTY), str(out))
    _loaded, _built, ir, _result = _chain(out)
    states = {obj.id: obj.state for obj in ir.items}
    assert states == _TEST_EMPTY_STATE_PINS, states

    text = (out / "items" / "oak_door.yaml").read_text(encoding="utf-8")
    assert text.startswith("items:\n")
    for line in (
        "id: oak_door",
        "object_type: decoration",
        "name: 橡木门",
        "description:",
        "position:",
        "x: 5",
        "y: 0",
        "z: 0",
        "state: closed=true,unlocked=true",
        "properties:",
        "material: oak_and_iron",
        "weight: heavy",
    ):
        assert line in text, f"缺行: {line!r}"


def test_t3_whisperheads_rule_ref_warning(tmp_path: Path) -> None:
    """whisperheads：恰 1 WARNING（physics.disable [8]，M-15 点名 8）
    + 输出可加载（A16 链零 ERROR）。

    补充钉面（R1 修正 S2/DEV-W5-2 保留分支）：7 角色逐角色
    relationships 保留键集值级钉（= 源键集 ∩ (角色 id ∪ {player_id})，
    全项目保留 42）；inventory 面 whisperheads 源数据全悬空 → 全剪除
    值级钉 + tmp 夹具保留分支正钉（1 在池 + 1 池外 → 仅留在池者）。
    """
    out = tmp_path / "wh"
    rep = migrate_project(str(_WHISPERHEADS), str(out))
    warns = [d for d in rep.diagnostics if d.severity == "WARNING"]
    assert len(warns) == 1, [d.message for d in warns]
    assert warns[0].code == "MIGRATION_RULE_REF_OBSOLETE"
    assert "8" in warns[0].message
    assert "physics" in warns[0].message
    _assert_chain_clean(out)

    # —— S2（DEV-W5-2）：引用池「保留」分支值级钉 ——
    _loaded, _built, ir, _result = _chain(out)
    by_id = {c.id: c for c in ir.characters}
    assert set(by_id) == set(_WH_RETAINED_RELATIONSHIPS), sorted(by_id)
    for cid, keys in _WH_RETAINED_RELATIONSHIPS.items():
        assert tuple(by_id[cid].relationships.keys()) == keys, cid
    assert sum(len(c.relationships) for c in ir.characters) == 42, [
        (c.id, len(c.relationships)) for c in ir.characters
    ]
    # inventory 面：whisperheads 源 player inventory / 全角色
    # starting_inventory 元素均 ∉ object id 池（全悬空）→ 全剪除
    # （值级钉，防过度保留；剪除全空 = [] 与正确集逐值相等）。
    assert ir.player.inventory == [], ir.player.inventory
    for c in ir.characters:
        assert c.starting_inventory == [], c.id
    # inventory 保留分支正钉（tmp 夹具：1 在池 + 1 池外 → 仅留在池者）
    inv_fix = tmp_path / "t3_inventory.yaml"
    inv_fix.write_text(
        """world:
  name: t3世界
  locations:
  - id: loc_a
    name: 位置甲
  objects:
  - id: obj_in
    object_type: decoration
    name: 池内物
player:
  player_id: player_1
  name: 测试者
  inventory:
  - obj_in
  - ghost_item
characters:
- id: char_a
  name: 甲
  starting_inventory:
  - ghost_item
  - obj_in
max_ticks: 1
""",
        encoding="utf-8",
    )
    inv_out = tmp_path / "out_t3_inventory"
    rep_inv = migrate_project(str(inv_fix), str(inv_out))
    assert rep_inv.status == "migrated", rep_inv.status
    _l, _b, ir_inv, _r = _chain(inv_out)
    assert list(ir_inv.player.inventory) == ["obj_in"], (
        ir_inv.player.inventory
    )
    ca = next(c for c in ir_inv.characters if c.id == "char_a")
    assert list(ca.starting_inventory) == ["obj_in"], (
        ca.starting_inventory
    )


def test_t4_murder_append_folded(tmp_path: Path) -> None:
    """murder：append 10 条 → rules 文件 10 条 passthrough 逐条钉。

    钉面：``id = rule_v1_<kind>_<NN>``（NN = 该 kind 内 01 起）/
    ``description`` = v1 append 条目原文逐字 / ``condition =
    'if(1 >= 0, allowed; blocked)'``（DEV-W5-1 披露：SOT §3.15.2 M-6
    字面 ``'if(1 >= 0, allowed)'`` 实测经 P5 冻结 parse_dsl
    （rule_module.py:812）= 失败（ast=None + LLMSIM_DSL_PARSE「if(...)
    缺少 else 输出」）→ 输出经 check_dsl_parses（validator.py:350）
    必产 ERROR → 破坏 A16 → 裁决最小修正补尾 else 分支：常数条件
    恒真 → 恒 ALLOWED →「永不改变可行性」语义保持）/
    ``priority = 100 - NN``；顶层键 = ``rules``。
    """
    out = tmp_path / "mu"
    migrate_project(str(_MURDER), str(out))
    _loaded, _built, ir, _result = _chain(out)
    rules = list(ir.rules)
    assert len(rules) == 10, [r.id for r in rules]
    expected_ids = (
        [f"rule_v1_attribute_{i:02d}" for i in range(1, 6)]
        + [f"rule_v1_physics_{i:02d}" for i in range(1, 6)]
    )
    assert [r.id for r in rules] == expected_ids
    for rule in rules:
        nn = int(rule.id.rsplit("_", 1)[1])
        assert rule.condition == "if(1 >= 0, allowed; blocked)", rule.id
        assert rule.priority == 100 - nn, rule.id
        assert rule.description == _MURDER_RULE_DESCRIPTIONS[rule.id], (
            rule.id
        )
    text = (
        out / "rules" / "murder_v1_rules.yaml"
    ).read_text(encoding="utf-8")
    assert text.startswith("rules:\n")


def test_t5_simulation_incompatible(tmp_path: Path) -> None:
    """simulation.yaml：incompatible + MIGRATION_DEPLOYMENT_FIELD ERROR
    点名 12 名闭集成员节键与 agents（两节键并集覆盖）+
    ``output_files == ()``（零输出文件写盘——tmp out 面核验）。

    补充钉面（R1 修正 S5）：薄壳 scripts/v2_migrate_v1.py exit 码钉
    （importlib 加载 shell 模块进程内调 main()，stdout/stderr 零断言；
    B3 边界禁 subprocess import，手段偏差登记报告）：仿真
    incompatible → 2 / migrated 输入 → 0 / --help → 0 / 互斥参数 → 1
    / 输入不存在 → 1。
    """
    out = tmp_path / "out"
    out.mkdir()
    rep = migrate_simulation(str(_SIMULATION))
    assert rep.status == "incompatible"
    errs = [
        d
        for d in rep.diagnostics
        if d.severity == "ERROR"
        and d.code == "MIGRATION_DEPLOYMENT_FIELD"
    ]
    assert len(errs) >= 1
    joined = "\n".join(d.message for d in errs)
    assert _SIM_LLM_SECTION in joined
    assert "agents" in joined
    assert rep.output_files == ()
    # tmp out 面核验：本入口无 out_dir 参数（SOT §3.15.4 入口表）=
    # 结构性零写盘；tmp 目录保持空。
    assert not any(out.iterdir())

    # —— S5：薄壳 exit 码钉（R1 修正；手段偏差已登记报告）——
    # 边界测试 B3（tests/engine_v2/core/test_import_boundary.py，W4 交付
    # 物，禁改）禁止测试树 subprocess import（两豁免面 P5/P6 不含本文件）
    # → 任务书 subprocess 消费手段不可行；改 importlib 加载 shell 模块、
    # 进程内调 main() 钉 exit 码语义：main() 返回值的唯一消费面 = shell
    # ``sys.exit(main(sys.argv[1:]))``（v2_migrate_v1.py:124）；用法错误
    # 族经 argparse parser.exit/error → SystemExit(code)。路径自
    # ``__file__`` 解析；stdout/stderr 零断言，只钉码。
    shell = _REPO_ROOT / "scripts" / "v2_migrate_v1.py"
    spec = importlib.util.spec_from_file_location("w5_shell_under_test", shell)
    assert spec is not None and spec.loader is not None
    shell_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(shell_mod)

    def _exit_code(*args: str) -> int:
        try:
            return int(shell_mod.main(list(args)))
        except SystemExit as exc:
            return int(exc.code)

    # 1. 仿真面（config/simulation.yaml → incompatible）→ 2
    assert _exit_code("--simulation", str(_SIMULATION)) == 2
    # 2. migrated 输入（test_empty 项目模式）→ 0
    assert _exit_code(str(_TEST_EMPTY), str(tmp_path / "t5_out0")) == 0
    # 3. --help → 0
    assert _exit_code("--help") == 0
    # 4. 互斥参数（--simulation + 项目模式位置参）→ 1
    assert _exit_code(
        str(_TEST_EMPTY), str(tmp_path / "t5_out4"),
        "--simulation", str(_SIMULATION),
    ) == 1
    # 5. 输入不存在（前置 FileNotFoundError 族）→ 1
    assert _exit_code(
        str(tmp_path / "no_such.yaml"), str(tmp_path / "t5_out5"),
    ) == 1


def test_t6_adversarial_injection_rejected(tmp_path: Path) -> None:
    """AD-P9-2（SOT L1663）：8 项注入面（tmp 夹具 = 测试内 yaml 字符串
    字面量 + ``tmp_path`` 写盘；既有 4 项保留 + R1 修正 S4 增 3 项
    缺失分支 firing + S7 增空 dict state 角）。

    分支钉：第 3 项选「``world`` 缺失」具体分支并兼覆「locations 零条」
    子分支（两支均 → ``MIGRATION_EMPTY_WORLD``）；第 4 项选「state 为
    list」具体分支（``MIGRATION_OBJECT_STATE_FOLDED`` M-10 shape 守卫
    分支）。第 1–7 项：``output_files == ()`` + 零输出文件写盘。
    S4 增项（M-11 L927 / M-12 L929 / M-14 L931 绑定表）：顶层
    ``player`` 缺失 / 顶层 ``max_ticks`` 缺失 / 角色 ``id`` 缺失 → 各
    恰 1 条目标 ERROR（全字段值级钉）+ 全报告 code ∈ 9 码闭集。
    S7 增项（DEV-W5-13 裁决面）：对象 ``state: {}`` 空 dict →
    status = migrated + ObjectSpec ``state == None`` + 恰 1 条
    ``MIGRATION_OBJECT_STATE_FOLDED``（INFO，指向该对象）。
    """
    base = """world:
  name: t6世界
  locations:
  - id: loc_a
    name: 位置甲
player:
  player_id: player_1
  name: 测试者
max_ticks: 1
"""

    def _run_case(
        tag: str,
        text: str,
        code: str,
        named: str,
    ) -> None:
        src = tmp_path / f"{tag}.yaml"
        src.write_text(text, encoding="utf-8")
        out = tmp_path / f"out_{tag}"
        rep = migrate_project(str(src), str(out))
        assert rep.status == "incompatible", tag
        assert rep.output_files == (), tag
        assert not out.exists() or not any(out.iterdir()), tag
        errs = [
            d
            for d in rep.diagnostics
            if d.severity == "ERROR" and d.code == code
        ]
        assert errs, (tag, [d.code for d in rep.diagnostics])
        for d in errs:
            assert named in d.message, (tag, d.message)

    # 1. 未知顶层键（foo: 1 + 最小合法项目）→ MIGRATION_UNKNOWN_TOP_KEY
    _run_case(
        "t6_unknown",
        base + "foo: 1\n",
        "MIGRATION_UNKNOWN_TOP_KEY",
        "foo",
    )
    # 2. 角色 id 重复 → MIGRATION_DUPLICATE_ID（点名 id）
    _run_case(
        "t6_dup_id",
        base
        + "characters:\n"
        + "- id: dup_id\n"
        + "  name: 甲\n"
        + "- id: dup_id\n"
        + "  name: 乙\n",
        "MIGRATION_DUPLICATE_ID",
        "dup_id",
    )
    # 3a. world 缺失（所选具体分支）→ MIGRATION_EMPTY_WORLD
    _run_case(
        "t6_no_world",
        """player:
  player_id: player_1
  name: 测试者
max_ticks: 1
""",
        "MIGRATION_EMPTY_WORLD",
        "world",
    )
    # 3b. locations 零条（兼覆子分支）→ MIGRATION_EMPTY_WORLD
    _run_case(
        "t6_zero_locs",
        """world:
  name: t6世界
  locations: []
player:
  player_id: player_1
  name: 测试者
max_ticks: 1
""",
        "MIGRATION_EMPTY_WORLD",
        "locations",
    )
    # 4. 对象 state 非 dict（list 具体分支）→ M-10 shape 守卫 ERROR
    _run_case(
        "t6_bad_state",
        """world:
  name: t6世界
  locations:
  - id: loc_a
    name: 位置甲
  objects:
  - id: bad_state
    object_type: decoration
    name: 坏状态
    state:
    - 1
    - 2
player:
  player_id: player_1
  name: 测试者
max_ticks: 1
""",
        "MIGRATION_OBJECT_STATE_FOLDED",
        "bad_state",
    )

    # —— S4：三缺失分支 firing（绑定表 M-11 L927 / M-12 L929 /
    # M-14 L931；每注入 = 恰 1 条目标码，全字段值级钉，防重复发码）——
    def _run_single(tag: str, text: str, expected: tuple) -> None:
        src = tmp_path / f"s4_{tag}.yaml"
        src.write_text(text, encoding="utf-8")
        out = tmp_path / f"out_s4_{tag}"
        rep = migrate_project(str(src), str(out))
        assert rep.status == "incompatible", tag
        assert rep.output_files == (), tag
        assert not out.exists() or not any(out.iterdir()), tag
        got = [
            (d.severity, d.code, d.path, d.message)
            for d in rep.diagnostics
        ]
        assert got == [expected], (tag, got)
        assert all(
            d.code in MIGRATION_DIAGNOSTIC_CODES for d in rep.diagnostics
        ), tag

    # 5. 顶层 player 缺失 → M-11 MIGRATION_PLAYER_MISSING（ERROR）
    _run_single(
        "no_player",
        """world:
  name: s4世界
  locations:
  - id: loc_a
    name: 位置甲
max_ticks: 1
""",
        (
            "ERROR", "MIGRATION_PLAYER_MISSING", "player",
            "player 键缺失或非映射（M-2：需 player 块）",
        ),
    )
    # 6. 顶层 max_ticks 缺失 → M-12 MIGRATION_MAX_TICKS_MISSING（ERROR）
    _run_single(
        "no_max_ticks",
        """world:
  name: s4世界
  locations:
  - id: loc_a
    name: 位置甲
player:
  player_id: player_1
  name: 测试者
""",
        (
            "ERROR", "MIGRATION_MAX_TICKS_MISSING", "max_ticks",
            "max_ticks 键缺失（M-5：必需顶层标量）",
        ),
    )
    # 7. 角色 id 缺失 → M-14 MIGRATION_DUPLICATE_ID（ERROR；绑定表
    # 「角色 id 缺失 / 重复」双触发面之缺失支，点名 characters[0]）
    _run_single(
        "char_no_id",
        base
        + "characters:\n"
        + "- name: 无名\n",
        (
            "ERROR", "MIGRATION_DUPLICATE_ID", "characters[0]",
            "characters[0] 条目缺 id（M-3）",
        ),
    )

    # —— S7（DEV-W5-13 裁决面）：对象 state = 空 dict 角 →
    # migrated + state null + 恰 1 条 M-10 INFO（指向该对象）——
    src7 = tmp_path / "t6_empty_state.yaml"
    src7.write_text(
        """world:
  name: s7世界
  locations:
  - id: loc_a
    name: 位置甲
  objects:
  - id: empty_state
    object_type: decoration
    name: 空状态
    state: {}
player:
  player_id: player_1
  name: 测试者
max_ticks: 1
""",
        encoding="utf-8",
    )
    out7 = tmp_path / "out_t6_empty_state"
    rep7 = migrate_project(str(src7), str(out7))
    assert rep7.status == "migrated", rep7.status
    assert [
        (d.severity, d.code, d.path) for d in rep7.diagnostics
    ] == [
        ("INFO", "MIGRATION_OBJECT_STATE_FOLDED",
         "world.objects.empty_state.state")
    ], rep7.diagnostics
    _l7, _b7, ir7, _r7 = _chain(out7)
    states7 = {obj.id: obj.state for obj in ir7.items}
    assert states7 == {"empty_state": None}, states7


def test_t7_codes_closed(tmp_path: Path) -> None:
    """A22（SOT L1464）：四输入（migrate_project ×3 + migrate_simulation
    ×1）全部诊断 code ∈ 9 码闭集 + severity ∈ {ERROR, WARNING, INFO}
    闭集 + ``MIGRATION_DIAGNOSTIC_CODES`` 9 名逐字 + ``MAPPING_RULES``
    （模块私有，getattr 面）9 名逐字。

    补充钉面（R1 修正 S6）：``__all__`` 5 名逐字序（SOT §3.15
    L861–869）。
    """
    reports = (
        migrate_project(str(_TEST_EMPTY), str(tmp_path / "t7_a")),
        migrate_project(str(_WHISPERHEADS), str(tmp_path / "t7_b")),
        migrate_project(str(_MURDER), str(tmp_path / "t7_c")),
        migrate_simulation(str(_SIMULATION)),
    )
    all_diags = [d for rep in reports for d in rep.diagnostics]
    assert all_diags, "四输入诊断集为空（A22 覆盖面异常）"
    for d in all_diags:
        assert d.code in MIGRATION_DIAGNOSTIC_CODES, d.code
        assert d.severity in {"ERROR", "WARNING", "INFO"}, d.severity
    assert MIGRATION_DIAGNOSTIC_CODES == frozenset(
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
    assert getattr(v1m, "MAPPING_RULES") == (
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
    # S6：__all__ 5 名逐字序钉（序 = SOT §3.15 L861–869 字面）。实测
    # __all__ = list（SOT L862–868 本身为列表字面量，任务书元组形为
    # 简写）→ 经 tuple() 序列等值钉 5 名与序，零实现改动（报告登记）。
    assert tuple(v1m.__all__) == (
        "MIGRATION_DIAGNOSTIC_CODES",
        "MigrationDiagnostic",
        "MigrationReport",
        "migrate_project",
        "migrate_simulation",
    )
