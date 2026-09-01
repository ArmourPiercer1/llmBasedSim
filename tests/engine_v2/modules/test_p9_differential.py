"""P9 W7 差分测试（SOT §6.1 / §3.17；6 函数平铺）。

方法学 = §3.17 L1041–1061（D-P9-14 = v1 纯函数直引（非运行时回放）+ 镜像
同构）。v1 import 面（只读消费，W0 R5 预验零第三方 import；PYTHONPATH=.
直引）：``src/game/attributes.py`` / ``src/game/condition_eval.py``。

差分结论登记（§3.17 L1058–1061）：D-α..D-ζ 实测差预期 = 零差（D-ε 例外
= 实测完整差异集披露，见 t5 + DEV-W7-4）；非零差归因写入交付报告
deviations。

纪律：零 wall-clock / uuid / random / time / datetime 导入（t2 注入
「调用即抛」假 RNG 证明确定性子集零随机消费）；行宽 ≤ 100；本文件零裸
0x5C 0x62；K8 12 名黑名单字符串字面量域零命中。
"""

from __future__ import annotations

import hashlib
import importlib
import json
import tempfile
from pathlib import Path

from src.engine_v2.content.loader import load_project
from src.engine_v2.content.project_ir import build_ir
from src.engine_v2.content.rule_module import (
    DslContext,
    evaluate_condition as p5_evaluate_condition,
    parse_dsl,
)
from src.engine_v2.core.snapshot import snapshot
from src.engine_v2.modules.attributes import (
    AttributeField,
    LockedAttributeError,
    apply_delta,
    apply_new_value,
    clamp_value,
    compute_natural_deltas,
)
from src.engine_v2.modules.v1_migration import migrate_project
from src.engine_v2.persistence.snapshot import (
    check_persistence_versions,
    dump_persistence_snapshot,
    load_persistence_snapshot,
    to_persistence_snapshot,
)

# v1 纯函数直引（§3.17 非运行时回放）：importlib 动态直引而非静态
# ``from src.game... import``——冻结 P1 边界测试（锚文件 L1–2071 字节
# 冻结、纯追加纪律不可加 P9 例外）禁 tests/engine_v2/ 静态 v1 import；
# 动态直引仍调用真实 v1 代码（直引语义不变），零断言放宽（DEV-W7-6）。
_v1_attributes = importlib.import_module("src.game.attributes")
_v1_condition_eval = importlib.import_module("src.game.condition_eval")
_clamp = _v1_attributes._clamp
apply_attribute_changes = _v1_attributes.apply_attribute_changes
apply_natural_attribute_deltas = _v1_attributes.apply_natural_attribute_deltas
compute_attribute_deltas_diff = _v1_attributes.compute_attribute_deltas_diff
v1_evaluate_condition = _v1_condition_eval.evaluate_condition

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SANDBOX = "tests/fixtures/v2_project_sandbox"
_TEST_EMPTY = _REPO_ROOT / "public_start" / "test_empty.yaml"
_WHISPERHEADS = _REPO_ROOT / "public_start" / "whisperheads.yaml"
_MURDER = _REPO_ROOT / "public_start" / "murder.yaml"
_ZERO_PYTHON = _REPO_ROOT / "tests" / "fixtures" / "v2_project_zero_python"


class _NoRng:
    """调用即抛假 RNG：证明 D-β 确定性子集零随机消费（钉面）。"""

    def rand(self) -> float:
        raise AssertionError("rand 被消费（确定性子集不应触达随机源）")

    def uniform(self, lo: float, hi: float) -> float:
        raise AssertionError("uniform 被消费")

    def randint(self, lo: int, hi: int) -> int:
        raise AssertionError("randint 被消费")


def _v1_character() -> dict:
    """10 属性钉死夹具（整点值 10..100；min 0 max 100；a05 locked、
    a06 hidden）。"""
    attrs = {}
    for i in range(1, 11):
        key = f"a{i:02d}"
        attrs[key] = {
            "name": key,
            "value": float(10 * i),
            "min": 0.0,
            "max": 100.0,
            "locked": key == "a05",
            "hidden": key == "a06",
        }
    return {"name": "Char1", "attributes": attrs}


def _v2_fields() -> dict[str, AttributeField]:
    return {
        f"a{i:02d}": AttributeField(
            name=f"a{i:02d}",
            value=float(10 * i),
            min=0.0,
            max=100.0,
            locked=(i == 5),
            hidden=(i == 6),
        )
        for i in range(1, 11)
    }


def _changes() -> list[dict]:
    """3 变更 × 每 tick：delta a01 +5 / new_value a02 25（界内）/
    delta a05 +3（locked → 两侧同序拒绝）。"""
    return [
        {"entity_type": "character", "entity_id": "c1",
         "attribute_key": "a01", "delta": 5.0, "reason": "r"},
        {"entity_type": "character", "entity_id": "c1",
         "attribute_key": "a02", "new_value": 25.0, "reason": "r"},
        {"entity_type": "character", "entity_id": "c1",
         "attribute_key": "a05", "delta": 3.0, "reason": "r"},
    ]


def _v2_run(
    fields: dict[str, AttributeField],
) -> tuple[dict[str, AttributeField], list[tuple[int, int]]]:
    """v2 reducer 驱动器：镜像 v1 apply_attribute_changes 分派面；
    locked → 捕获 LockedAttributeError（= v1 静默跳过的同序拒绝），
    记录 (tick, 变更索引) 拒绝位。"""
    rejections: list[tuple[int, int]] = []
    for tick in (1, 2):
        for idx, change in enumerate(_changes()):
            key = change["attribute_key"]
            nv = change.get("new_value")
            try:
                if nv is not None:
                    fields, _ = apply_new_value(fields, "c1", key, float(nv), tick)
                else:
                    fields, _ = apply_delta(fields, "c1", key,
                                            float(change.get("delta") or 0.0), tick)
            except LockedAttributeError:
                rejections.append((tick, idx))
    return fields, rejections


def test_t1_attribute_parity() -> None:
    """D-α：v1 apply_attribute_changes:999 vs v2 apply_delta/
    apply_new_value 同输入（10 属性 × 3 变更 × 2 tick，零随机）→ 终值
    逐属性 ±0 精确浮点相等；locked 拒绝同序；_clamp:10 vs clamp_value
    同面逐值相等。"""
    player = {"player_id": "p", "name": "P", "attributes": {}}
    v1_chars = {"c1": _v1_character()}
    v1_player2, v1_chars2, _ = apply_attribute_changes(player, v1_chars, _changes())
    v1_player3, v1_chars3, _ = apply_attribute_changes(
        v1_player2, v1_chars2, _changes()
    )
    v1_final = v1_chars3["c1"]["attributes"]

    v2_final, rejections = _v2_run(_v2_fields())

    for key in sorted(v1_final):
        v1_val = float(v1_final[key]["value"])
        v2_val = v2_final[key].value
        assert v1_val == v2_val, f"D-α 终值差 {key}: v1={v1_val} v2={v2_val}"
    # locked a05 同序拒绝（两 tick × 第 3 变更）+ 终值未变：
    assert rejections == [(1, 2), (2, 2)]
    assert v2_final["a05"].value == 50.0
    assert float(v1_final["a05"]["value"]) == 50.0
    # 非锁定终值钉（防两侧同向漂移）：
    assert v2_final["a01"].value == 20.0 and v2_final["a02"].value == 25.0
    # _clamp:10 vs clamp_value 同面（逐属性 × 网格值）：
    for key in sorted(_v2_fields()):
        field = _v2_fields()[key]
        v1_attr = _v1_character()["attributes"][key]
        for probe in (-5.0, 0.0, 50.0, 100.0, 150.0):
            assert _clamp(probe, v1_attr) == clamp_value(probe, field), (
                f"D-α 钳制差 {key}@{probe}"
            )


def _dsl_ctx(ctx: dict) -> DslContext:
    return DslContext(
        player=ctx.get("player", {}),
        target=ctx.get("target", {}),
        variables={k: v for k, v in ctx.items() if k not in ("player", "target")},
    )


def _v1_context() -> dict:
    return {
        "player": {
            "attributes": {"sanity": {"value": 35}, "resolve": {"value": 70}},
            "physical_profile": {"strength": 2.0, "body_width_cm": 60},
            "capabilities": {"skill_levels": {"lockpicking": 0.4}},
        },
        "target": {"properties": {
            "weight_kg": 120, "lock_difficulty": 0.8, "width_cm": 80,
        }},
        "a": 3,
    }


def _dsl_cases() -> list[tuple[str, str, float | None]]:
    """8 条确定性条件（v1 测试夹具确定性子集，零 rand 族）+ 钉死期望
    （feasibility, probability）。"""
    return [
        ("if(player.sanity < 40, blocked; allowed)", "blocked", None),
        ("if(a < 1, blocked; a < 5, uncertain:0.4; allowed)", "uncertain", 0.4),
        ("if(player.strength * 50 >= target.weight, allowed; blocked)",
         "blocked", None),
        ("if((player.strength + 0.5) * 50 >= target.weight, allowed; blocked)",
         "allowed", None),
        ("if(min(player.sanity, player.resolve) < max(20, 30), blocked; allowed)",
         "allowed", None),
        ("if(player.lockpicking < target.lock_difficulty, uncertain:0.25; allowed)",
         "uncertain", 0.25),
        ("if(player.sanity < 40 and player.resolve > 60, blocked; allowed)",
         "blocked", None),
        ("if(a < 1 or a > 2, blocked; allowed)", "blocked", None),
    ]


def test_t2_dsl_parity() -> None:
    """D-β：v1 evaluate_condition（condition_eval.py def:35）vs P5 冻结
    evaluate_condition（rule_module.py:903）同 8 条件（文法逐字）→ 判定
    （allowed/uncertain/blocked + 概率）逐条相等；零 rand 消费（假 RNG
    调用即抛）。"""
    ctx = _v1_context()
    dsl_ctx = _dsl_ctx(ctx)
    for expr, exp_feas, exp_prob in _dsl_cases():
        v1_out = v1_evaluate_condition(expr, ctx)
        parsed = parse_dsl(expr, "t2")
        assert parsed.ast is not None, f"P5 解析失败: {expr!r}"
        assert not parsed.diagnostics, f"P5 解析诊断: {parsed.diagnostics}"
        p5_out = p5_evaluate_condition(parsed.ast, dsl_ctx, _NoRng())
        assert v1_out.feasibility == p5_out.feasibility.value, (
            f"D-β 判定差 {expr!r}: v1={v1_out.feasibility} "
            f"p5={p5_out.feasibility.value}"
        )
        assert v1_out.probability == p5_out.probability, (
            f"D-β 概率差 {expr!r}: v1={v1_out.probability} "
            f"p5={p5_out.probability}"
        )
        # 钉死期望（防两侧同向漂移）：
        assert v1_out.feasibility == exp_feas, f"期望漂移 {expr!r}"
        assert v1_out.probability == exp_prob, f"期望漂移 {expr!r}"


def test_t3_natural_delta_parity() -> None:
    """D-γ：v1 compute_attribute_deltas_diff:59（apply_natural_attribute_
    deltas 前后快照差）vs v2 compute_natural_deltas 同输入（10 属性 ×
    分钟增量，ticks=3，界内零钳制、零 locked）→ 逐属性 ±0 相等。"""
    per_minute = [0.5, 1.0, 0.0, -0.5, 2.0, -1.0, 0.25, 1.5, -2.0, 0.75]
    ticks = 3
    v1_attrs = {}
    v2_fields = {}
    for i, pm in enumerate(per_minute, start=1):
        key = f"a{i:02d}"
        v1_attrs[key] = {"name": key, "value": 50.0, "min": 0.0, "max": 100.0,
                         "natural_delta_per_minute": pm}
        v2_fields[key] = AttributeField(
            name=key, value=50.0, min=0.0, max=100.0,
            natural_delta_per_tick=pm,
        )
    player = {"player_id": "p", "name": "P", "attributes": {}}
    before = {"c1": {"name": "Char1", "attributes": dict(v1_attrs)}}
    after_player, after_chars, _ = apply_natural_attribute_deltas(
        player, before, tick_duration_minutes=float(ticks)
    )
    diffs = compute_attribute_deltas_diff(player, before, after_player, after_chars)
    v1_delta = {d["attribute_key"]: d["delta"]
                for d in diffs if d["entity_id"] == "c1"}
    v2_delta = dict(compute_natural_deltas(v2_fields, ticks))
    for key in sorted(set(v1_delta) | set(v2_delta)):
        v1_val = float(v1_delta.get(key, 0.0))
        v2_val = float(v2_delta.get(key, 0.0))
        assert v1_val == v2_val, (
            f"D-γ 自然差 {key}: v1={v1_val} v2={v2_val}"
        )
    # 非零增量项计数钉（零增量两侧均缺席）：
    assert len(v1_delta) == len(v2_delta) == sum(1 for pm in per_minute if pm != 0.0)


def _dir_fingerprints(root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            rel = path.relative_to(root).as_posix()
            out[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def test_t4_migration_byte_stable() -> None:
    """D-δ：migrate_project 双跑（test_empty / whisperheads / murder，
    tmp 输出）→ 输出目录逐文件 sha256 相等（零跨跑漂移）。"""
    for label, source in (
        ("test_empty", _TEST_EMPTY),
        ("whisperheads", _WHISPERHEADS),
        ("murder", _MURDER),
    ):
        with tempfile.TemporaryDirectory() as dir_a, \
                tempfile.TemporaryDirectory() as dir_b:
            rep_a = migrate_project(str(source), dir_a)
            rep_b = migrate_project(str(source), dir_b)
            assert rep_a.status == "migrated" and rep_b.status == "migrated"
            run_a = _dir_fingerprints(Path(dir_a))
            run_b = _dir_fingerprints(Path(dir_b))
        assert run_a == run_b, f"D-δ 双跑漂移 {label}: {run_a.keys() ^ run_b.keys()}"
        assert run_a, f"D-δ 零输出 {label}"


def _ir_of(root: Path):
    loaded = load_project(root)
    load_errs = [d for d in loaded.diagnostics if d.severity.value == "ERROR"]
    assert not load_errs, f"load 诊断 {root}: {load_errs}"
    built = build_ir(loaded.raw)
    build_errs = [d for d in built.diagnostics if d.severity.value == "ERROR"]
    assert not build_errs, f"build 诊断 {root}: {build_errs}"
    return built.ir


def test_t5_zero_python_isomorphism(tmp_path: Path) -> None:
    """A17 / D-ε：migrate_project(public_start/test_empty.yaml) 输出 vs
    tests/fixtures/v2_project_zero_python/（P5 手工镜像，冻结）：两项目
    load_project + build_ir 后 IR 面比较。

    **DEV-W7-4（D-ε SOT 前提证伪）**：SOT §3.17 断言「唯一允许差异 =
    items 节」；实测（IR 面）差异集 = manifest（project_id / name /
    description 三模板面）+ scenario.id + characters（0 vs 1）+ rules
    （0 vs 2）+ actions（0 vs 1）+ items（4 vs 0）；player / world IR
    逐字段相等。本函数**钉死完整实测差异集**（更严，非放宽——非静默吞
    差异），并把差异本身逐值断言；SOT items-only 前提由交付报告
    deviations 归因（P5 镜像含 test_empty 无的手工 characters/rules/
    actions；W5 迁移器模板面 = 合法面非移植错误）。
    """
    out = tmp_path / "p9_out"
    rep = migrate_project(str(_TEST_EMPTY), str(out))
    assert rep.status == "migrated"
    ir_p9 = _ir_of(out)
    ir_p5 = _ir_of(_ZERO_PYTHON)

    # player / world IR 逐字段相等（零差）：
    assert ir_p9.player.model_dump(mode="json") == ir_p5.player.model_dump(mode="json")
    assert ir_p9.world.model_dump(mode="json") == ir_p5.world.model_dump(mode="json")

    # manifest：三模板面差异钉（其余字段相等）：
    m9 = ir_p9.manifest.model_dump(mode="json")
    m5 = ir_p5.manifest.model_dump(mode="json")
    m_diff = {k for k in m9 if m9[k] != m5[k]}
    assert m_diff == {"project_id", "name", "description"}
    assert m9["project_id"] == "test_empty" and m5["project_id"] == "zero_python"

    # scenario：id 模板面差异钉（其余字段相等）：
    s9 = ir_p9.scenario.model_dump(mode="json")
    s5 = ir_p5.scenario.model_dump(mode="json")
    s_diff = {k for k in s9 if s9[k] != s5[k]}
    assert s_diff == {"id"}
    assert s9["id"] == "scenario_test_empty" and s5["id"] == "scenario_main"

    # characters / rules / actions：P9 输出空 vs P5 镜像手工非空（计数钉）：
    assert len(ir_p9.characters) == 0 and len(ir_p5.characters) == 1
    assert len(ir_p9.rules) == 0 and len(ir_p5.rules) == 2
    assert len(ir_p9.actions) == 0 and len(ir_p5.actions) == 1

    # items：P9 输出 4 条（state 折叠串逐值钉）vs P5 镜像 0 条（唯一允许
    # 差异节，DEV-P9-04 面）：
    assert len(ir_p5.items) == 0
    assert len(ir_p9.items) == 4
    item_states = {it.id: it.state for it in ir_p9.items}
    assert item_states == {
        "light_crystal": "glowing=true,temperature=warm",
        "oak_door": "closed=true,unlocked=true",
        "old_parchments": "aged=true,readable=true",
        "wooden_crates": "one_open=true,two_sealed=true",
    }


def test_t6_persistence_roundtrip(p9_host) -> None:
    """A24 / D-ζ：sandbox 样例终局 WorldState 经 P8 冻结面 to_
    persistence_snapshot:104 → dump_persistence_snapshot:133 →
    load_persistence_snapshot:143 → check_persistence_versions:176 →
    零版本冲突 + JSON-clean（json.dumps 零失败）+ 往返字节相等。"""
    host = p9_host(_SANDBOX)
    host.tick(5)
    core_snapshot = snapshot(
        host.world,
        host.runtime,
        "p9.differential",
        project_version=host.ir.manifest.project_id,
        module_versions={},
    )
    envelope = to_persistence_snapshot(core_snapshot)
    text = dump_persistence_snapshot(envelope)  # 内部断言 JSON-clean
    loaded = load_persistence_snapshot(text)    # 四道门 fail-loud
    issues = check_persistence_versions(loaded)
    assert issues == (), f"D-ζ 版本冲突: {issues}"
    # 往返字节相等（同信封双跑确定性）：
    assert dump_persistence_snapshot(loaded) == text
    # JSON-clean（json.dumps 零失败）：
    json.dumps(loaded.to_dict())
