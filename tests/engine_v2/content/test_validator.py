"""P5-T09（W6）``content/validator.py`` 单测（设计文档 §6.1 L745 / §3.6）。

用例族（§6.1 L745 行逐条落地）：

- **18 码路径覆盖矩阵**：``DIAGNOSTIC_CODES`` 18 枚逐码 ≥1 触发例 +
  ≥1 不触发例（触发/不触发场景各自独立构造；``LLMSIM_ENGINE_VERSION``
  触发例 = manifest 面，node 面交叉核验见 ``test_manifest_engine_version_cross_verify``）；
- **sort_diagnostics 排序器锁定**：key = ``(code, path, message)`` 稳定序 +
  幂等（D-P5-12）；
- **authority 声明域重叠**：同 domain ∧ 双 exclusive → 每对恰好 1 条
  ``LLMSIM_AUTHORITY_CONFLICT``（非笛卡尔积；3 政策 = 3 对 = 3 条）；
- **K8 探针表**（§3.6 L430 字面表，断言 #19a）：正例 P1-P4 命中 +
  负例 N1-N3 不命中（12 名封闭集以串拼接构造，自证豁免裸 token 扫描纪律）；
- **字段集内省**（断言 #19b / K4 / P5-INV-4）：``InferenceCapabilityProfile``
  与 ``PromptPolicy`` 封闭字段集（无部署 pinning / authority 字段）。

全部用例 hermetic、无网络、无大模型调用（测试侧 import 纪律 = SOT §3.11）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from src.engine_v2.content import validator as validator_module
from src.engine_v2.content.loader import load_project
from src.engine_v2.content.project_ir import build_ir
from src.engine_v2.content.validator import (
    check_authority_conflicts,
    check_deployment_leakage,
    check_dsl_parses,
    check_duplicate_ids,
    check_references,
    sort_diagnostics,
    validate_project,
)
from src.engine_v2.content.schemas import (
    DIAGNOSTIC_CODES,
    ENGINE_VERSION,
    Diagnostic,
    InferenceCapabilityProfile,
    PromptPolicy,
)
from tests.engine_v2.content.conftest import (
    make_authority_policy,
    make_character,
    make_diagnostic,
    make_ir,
    make_location,
    make_manifest,
    make_module_node,
    make_plugin_descriptor,
    make_raw_project,
    make_rule_spec,
    make_world,
)

#: 仓库根（本文件位于 tests/engine_v2/content/ 下，上溯 3 级）。
_REPO_ROOT = Path(__file__).resolve().parents[3]

#: K8 12 名封闭集探针名（串拼接自证豁免；D-P5-11 裸 token 纪律）。
_API_KEY = "api_" + "key"
_PROVIDER = "prov" + "ider"
_BASE_URL = "base_" + "url"
_OPEN_AI = "open" + "ai"


# —— 私有 helper ——


def _chain_diags(root: Path) -> tuple[Diagnostic, ...]:
    """fixture 目录 → 全链诊断（loader → build_ir → validate_project）。"""
    loaded = load_project(root)
    if loaded.raw is None:
        return loaded.diagnostics
    built = build_ir(loaded.raw)
    if built.ir is None:
        return built.diagnostics
    return validate_project(built.ir, loaded.raw).diagnostics


def _minimal_game_yaml() -> dict[str, Any]:
    """最小合法 game.yaml dict（manifest / scenario / player 三必需节）。"""
    return {
        "manifest": {"schema_version": "2", "project_id": "mini", "name": "Mini"},
        "scenario": {
            "id": "scenario_main",
            "max_ticks": 20,
            "ticks_per_game_minute": 1,
            "game_time": {"hour": 9, "minute": 30},
        },
        "player": {"player_id": "player_1", "name": "P"},
    }


def _matrix_trigger(code: str, tmp_path: Path) -> tuple[Diagnostic, ...]:
    """18 码逐码触发场景（§6.1 L745 矩阵触发面；每码 ≥1 命中）。"""
    if code == "LLMSIM_FILE_MISSING":
        empty = tmp_path / "empty"
        empty.mkdir()
        return load_project(empty).diagnostics
    if code == "LLMSIM_YAML_PARSE":
        root = tmp_path / "bad"
        root.mkdir()
        (root / "game.yaml").write_text("- 1\n- 2\n", encoding="utf-8")
        return load_project(root).diagnostics
    if code == "LLMSIM_PROJECT_FORMAT_V1":
        root = tmp_path / "v1"
        root.mkdir()
        v1_text = (_REPO_ROOT / "public_start" / "test_empty.yaml").read_text(
            encoding="utf-8"
        )
        (root / "game.yaml").write_text(v1_text, encoding="utf-8")
        return load_project(root).diagnostics
    if code == "LLMSIM_SCHEMA":
        # manifest 必需节缺失 → build_ir 步 2 → 1 条 LLMSIM_SCHEMA
        game = _minimal_game_yaml()
        game.pop("manifest")
        raw = make_raw_project(files={"game.yaml": game})
        return build_ir(raw).diagnostics
    if code == "LLMSIM_UNKNOWN_KEY":
        game = _minimal_game_yaml()
        game["bogus"] = 1
        raw = make_raw_project(files={"game.yaml": game})
        return build_ir(raw).diagnostics
    if code == "LLMSIM_DUPLICATE_ID":
        ir = make_ir(
            characters=(make_character(id="npc_x"), make_character(id="npc_x"))
        )
        return tuple(check_duplicate_ids(ir))
    if code == "LLMSIM_UNRESOLVED_REF":
        world = make_world(
            locations=(
                make_location(id="loc_a", connections={"east": "loc_missing"}),
                make_location(id="loc_b"),
            )
        )
        ir = make_ir(world=world)
        return tuple(check_references(ir))
    if code == "LLMSIM_MODULE_REQUIRES_MISSING":
        ir = make_ir(modules=(make_module_node(id="a.x", requires=("b.y",)),))
        return validate_project(ir).diagnostics
    if code == "LLMSIM_MODULE_VERSION":
        ir = make_ir(
            modules=(
                make_module_node(id="a.x", version="1.0.0", requires=("b.y >= 2",)),
                make_module_node(id="b.y", version="1.0.0"),
            )
        )
        return validate_project(ir).diagnostics
    if code == "LLMSIM_MODULE_CYCLE":
        ir = make_ir(
            modules=(
                make_module_node(id="a", requires=("b",)),
                make_module_node(id="b", requires=("c",)),
                make_module_node(id="c", requires=("a",)),
            )
        )
        return validate_project(ir).diagnostics
    if code == "LLMSIM_MODULE_CONFLICT":
        ir = make_ir(
            modules=(
                make_module_node(id="a.x", conflicts=("b.y",)),
                make_module_node(id="b.y"),
            )
        )
        return validate_project(ir).diagnostics
    if code == "LLMSIM_AUTHORITY_CONFLICT":
        ir = make_ir(
            authority=(
                make_authority_policy(id="p1", domain="d.x", owner="owner_a"),
                make_authority_policy(id="p2", domain="d.x", owner="owner_b"),
            )
        )
        return tuple(check_authority_conflicts(ir))
    if code == "LLMSIM_DEPLOYMENT_FIELD":
        raw = make_raw_project(files={"game.yaml": {}}, texts={
            "game.yaml": f"capabilities:\n  {_API_KEY}: x\n",
        })
        return tuple(check_deployment_leakage(raw))
    if code == "LLMSIM_DSL_PARSE":
        ir = make_ir(rules=(make_rule_spec(id="r1", condition="while(x > 1, allowed)"),))
        return tuple(check_dsl_parses(ir))
    if code == "LLMSIM_PLUGIN_ENTRY_INVALID":
        raw = make_raw_project(
            files={
                "plugins/rogue/plugin.yaml": {
                    "id": "rogue",
                    "version": "1.0",
                    "entrypoint": "no-colon-here",
                },
            },
            plugins_dir_present=True,
        )
        return validate_project(make_ir(), raw).diagnostics
    if code == "LLMSIM_PLUGIN_NO_PYPROJECT":
        # plugins/ 存在（present=True）且 pyproject 缺失 → 恰好 1 条（D-P5-07）
        raw = make_raw_project(files={}, plugins_dir_present=True)
        return validate_project(make_ir(), raw).diagnostics
    if code == "LLMSIM_ENGINE_VERSION":
        ir = make_ir(manifest=make_manifest(engine_version="0.4.9"))
        return validate_project(ir).diagnostics
    if code == "LLMSIM_PLUGIN_ENTRY_UNRESOLVED":
        ir = make_ir(plugin_descriptors=(make_plugin_descriptor(id="ghost"),))
        raw = make_raw_project(files={})
        return validate_project(ir, raw).diagnostics
    raise AssertionError(f"矩阵未覆盖码：{code}")  # pragma: no cover


def _matrix_nontrigger(code: str) -> tuple[Diagnostic, ...]:
    """18 码逐码不触发场景（§6.1 L745 矩阵不触发面；每码 0 命中）。

    加载族码（FILE_MISSING / YAML_PARSE / PROJECT_FORMAT_V1 / SCHEMA /
    UNKNOWN_KEY）共用 zero_python 参考项目全链（诊断集 = ∅，天然全码不触发）；
    其余码各自构造近失场景。
    """
    if code in {
        "LLMSIM_FILE_MISSING",
        "LLMSIM_YAML_PARSE",
        "LLMSIM_PROJECT_FORMAT_V1",
        "LLMSIM_SCHEMA",
        "LLMSIM_UNKNOWN_KEY",
    }:
        return _chain_diags(_REPO_ROOT / "tests" / "fixtures" / "v2_project_zero_python")
    if code == "LLMSIM_DUPLICATE_ID":
        ir = make_ir(
            characters=(make_character(id="npc_a"), make_character(id="npc_b"))
        )
        return tuple(check_duplicate_ids(ir))
    if code == "LLMSIM_UNRESOLVED_REF":
        world = make_world(
            locations=(
                make_location(id="loc_a", connections={"east": "loc_b"}),
                make_location(id="loc_b"),
            )
        )
        ir = make_ir(world=world)
        return tuple(check_references(ir))
    if code == "LLMSIM_MODULE_REQUIRES_MISSING":
        ir = make_ir(
            modules=(
                make_module_node(id="a.x", requires=("b.y",)),
                make_module_node(id="b.y"),
            )
        )
        return validate_project(ir).diagnostics
    if code == "LLMSIM_MODULE_VERSION":
        ir = make_ir(
            modules=(
                make_module_node(id="a.x", version="1.0.0", requires=("b.y >= 1",)),
                make_module_node(id="b.y", version="1.0.0"),
            )
        )
        return validate_project(ir).diagnostics
    if code == "LLMSIM_MODULE_CYCLE":
        ir = make_ir(
            modules=(
                make_module_node(id="a", requires=("b",)),
                make_module_node(id="b", requires=("c",)),
                make_module_node(id="c"),
            )
        )
        return validate_project(ir).diagnostics
    if code == "LLMSIM_MODULE_CONFLICT":
        # conflicts 目标缺失 = 零诊断（module_graph 披露口径）
        ir = make_ir(
            modules=(
                make_module_node(id="a.x", conflicts=("missing.z",)),
                make_module_node(id="b.y"),
            )
        )
        return validate_project(ir).diagnostics
    if code == "LLMSIM_AUTHORITY_CONFLICT":
        ir = make_ir(
            authority=(
                make_authority_policy(id="p1", domain="d.x", owner="owner_a"),
                make_authority_policy(
                    id="p2", domain="d.x", owner="owner_b", exclusive=False
                ),
            )
        )
        return tuple(check_authority_conflicts(ir))
    if code == "LLMSIM_DEPLOYMENT_FIELD":
        # N1 负例口径：model 不在 12 名集
        raw = make_raw_project(files={"game.yaml": {}}, texts={
            "game.yaml": "capabilities:\n  model: x\n",
        })
        return tuple(check_deployment_leakage(raw))
    if code == "LLMSIM_DSL_PARSE":
        ir = make_ir(
            rules=(make_rule_spec(id="r1", condition="if(x > 1, allowed; blocked)"),)
        )
        return tuple(check_dsl_parses(ir))
    if code == "LLMSIM_PLUGIN_ENTRY_INVALID":
        return _chain_diags(_REPO_ROOT / "tests" / "fixtures" / "v2_plugin_local")
    if code == "LLMSIM_PLUGIN_NO_PYPROJECT":
        raw = make_raw_project(files={})
        return validate_project(make_ir(), raw).diagnostics
    if code == "LLMSIM_ENGINE_VERSION":
        ir = make_ir(manifest=make_manifest(engine_version=">=0.5.0"))
        return validate_project(ir).diagnostics
    if code == "LLMSIM_PLUGIN_ENTRY_UNRESOLVED":
        return _chain_diags(_REPO_ROOT / "tests" / "fixtures" / "v2_plugin_local")
    raise AssertionError(f"矩阵未覆盖码：{code}")  # pragma: no cover


# —— 公共面（扁平测试函数，零测试类）——


def test_validator_all_ledger_order() -> None:
    """__all__ = 8 名，§8.2 L898 台账逐名逐序（W6 交付物面钉死）。"""
    assert validator_module.__all__ == [
        "ValidationResult",
        "validate_project",
        "check_duplicate_ids",
        "check_references",
        "check_authority_conflicts",
        "check_deployment_leakage",
        "check_dsl_parses",
        "sort_diagnostics",
    ]


@pytest.mark.parametrize("code", sorted(DIAGNOSTIC_CODES))
def test_matrix_code_trigger(code: str, tmp_path: Path) -> None:
    """18 码矩阵触发面：逐码 ≥1 命中（§6.1 L745）。"""
    diags = _matrix_trigger(code, tmp_path)
    hits = [d for d in diags if d.code == code]
    assert hits, f"{code}：触发场景必须产出 ≥1 条"


@pytest.mark.parametrize("code", sorted(DIAGNOSTIC_CODES))
def test_matrix_code_nontrigger(code: str) -> None:
    """18 码矩阵不触发面：逐码 0 命中（§6.1 L745）。"""
    diags = _matrix_nontrigger(code)
    hits = [d for d in diags if d.code == code]
    assert not hits, f"{code}：不触发场景产出 {len(hits)} 条"


def test_engine_version_trigger_manifest_face() -> None:
    """LLMSIM_ENGINE_VERSION 触发例 = manifest 面（§6.1 L745 括注）。

    声明 "0.4.9"（exact 不满足 0.5.0）→ 1 条，path="manifest"，
    refs=(声明值, ENGINE_VERSION)。
    """
    ir = make_ir(manifest=make_manifest(engine_version="0.4.9"))
    diags = validate_project(ir).diagnostics
    hits = [d for d in diags if d.code == "LLMSIM_ENGINE_VERSION"]
    assert len(hits) == 1
    assert hits[0].path == "manifest"
    assert hits[0].refs == ("0.4.9", ENGINE_VERSION)


def test_manifest_engine_version_cross_verify() -> None:
    """A3 交叉核验：manifest 面 vs check_module_versions 节点面同判（≥6 值）。

    Leader 预裁定 A3：validator 本地重实现版本比较（D-P5-06 数字串比较）
    与 module_graph 私有比较面同语义——6 值矩阵上两面对照 ENGINE_VERSION
    的满足判定必须逐值相等；期望真值向量按 D-P5-06 裁定字面计算
    （ENGINE_VERSION = 0.5.0）。
    """
    values = [">=0.5.0", "0.5.0", "2.0.0", ">=1.0.0", "0.4.9", ">=0.5.1"]
    expected = [False, False, True, True, True, True]
    for value, want_diagnostic in zip(values, expected):
        manifest_face_ir = make_ir(manifest=make_manifest(engine_version=value))
        manifest_hit = any(
            d.code == "LLMSIM_ENGINE_VERSION" and d.path == "manifest"
            for d in validate_project(manifest_face_ir).diagnostics
        )
        node_face_ir = make_ir(
            modules=(
                make_module_node(id="m.x", version="1.0.0", engine_version=value),
            )
        )
        node_hit = any(
            d.code == "LLMSIM_ENGINE_VERSION" and d.path == "m.x"
            for d in validate_project(node_face_ir).diagnostics
        )
        assert manifest_hit == node_hit, (
            f"双面对 {value!r} 判定分歧：manifest 面={manifest_hit}, 节点面={node_hit}"
        )
        assert manifest_hit == want_diagnostic, (
            f"{value!r} 期望诊断={want_diagnostic}，实际={manifest_hit}"
        )


def test_sort_diagnostics_locked_order() -> None:
    """sort_diagnostics 排序器锁定：key=(code, path, message) 稳定 + 幂等（D-P5-12）。"""
    x1 = make_diagnostic("LLMSIM_SCHEMA", "b.yaml", "m")
    x2 = make_diagnostic("LLMSIM_SCHEMA", "a.yaml", "m")
    x3 = make_diagnostic("LLMSIM_DUPLICATE_ID", "z.yaml", "m")
    x4 = make_diagnostic("LLMSIM_SCHEMA", "a.yaml", "m")  # 与 x2 同键 → 稳定序 x2 先
    result = sort_diagnostics([x1, x2, x3, x4])
    assert result == [x3, x2, x4, x1]
    assert sort_diagnostics(result) == result  # 幂等
    assert isinstance(result, list)


def test_authority_conflict_one_per_pair_not_cartesian() -> None:
    """authority 声明域重叠：每对恰好 1 条（非笛卡尔积；D-P5-03 声明域重叠级）。"""
    two = make_ir(
        authority=(
            make_authority_policy(id="p1", domain="d.x", owner="owner_b"),
            make_authority_policy(id="p2", domain="d.x", owner="owner_a"),
        )
    )
    diags_two = check_authority_conflicts(two)
    assert len(diags_two) == 1
    assert diags_two[0].path == "d.x"
    # refs = 双方 owner 的 casefold 序
    assert diags_two[0].refs == ("owner_a", "owner_b")

    three = make_ir(
        authority=(
            make_authority_policy(id="p1", domain="d.y", owner="o1"),
            make_authority_policy(id="p2", domain="d.y", owner="o2"),
            make_authority_policy(id="p3", domain="d.y", owner="o3"),
        )
    )
    diags_three = check_authority_conflicts(three)
    # 3 政策同 domain 双 exclusive = C(3,2) = 3 对 → 3 条（非 6 条笛卡尔积）
    assert len(diags_three) == 3
    assert all(d.path == "d.y" for d in diags_three)
    pair_refs = sorted(d.refs for d in diags_three)
    assert pair_refs == [
        ("o1", "o2"),
        ("o1", "o3"),
        ("o2", "o3"),
    ]

    different_domains = make_ir(
        authority=(
            make_authority_policy(id="p1", domain="d.a", owner="o1"),
            make_authority_policy(id="p2", domain="d.b", owner="o2"),
        )
    )
    assert check_authority_conflicts(different_domains) == []


def test_k8_probe_table_p1_p4() -> None:
    """K8 探针表正例 P1-P4（§3.6 L430 字面表，断言 #19a）。"""
    # P1：P1 探针名键名（开放 dict 语境）→ 命中，refs 含该探针名
    raw_p1 = make_raw_project(files={"game.yaml": {}}, texts={
        "game.yaml": "capabilities:\n  " + _API_KEY + ": whatever\n",
    })
    diags_p1 = check_deployment_leakage(raw_p1)
    assert [d.refs for d in diags_p1] == [(_API_KEY,)]

    # P2：P2 探针名键名 → 命中（同码），refs 含该探针名
    raw_p2 = make_raw_project(files={"game.yaml": {}}, texts={
        "game.yaml": "capabilities:\n  " + _PROVIDER + ": whatever\n",
    })
    diags_p2 = check_deployment_leakage(raw_p2)
    assert [d.refs for d in diags_p2] == [(_PROVIDER,)]

    # P3：P3 探针字段值文本含 P4 探针词（URL）→ (文件, P3 名) 与
    # (文件, P4 名) 两对各自去重各 1 条
    raw_p3 = make_raw_project(files={"game.yaml": {}}, texts={
        "game.yaml": (
            "capabilities:\n  " + _BASE_URL + ': "https://' + _OPEN_AI
            + '.example.local/v1"\n'
        ),
    })
    diags_p3 = check_deployment_leakage(raw_p3)
    assert sorted(d.refs[0] for d in diags_p3) == sorted([_BASE_URL, _OPEN_AI])
    assert all(d.path == "game.yaml" for d in diags_p3)

    # P4：pyproject.toml 文本依赖行含 P2 探针词 → 命中，path=pyproject.toml
    raw_p4 = make_raw_project(
        files={},
        pyproject_present=True,
        pyproject_text='dependencies = ["' + _PROVIDER + '-sdk"]\n',
    )
    diags_p4 = check_deployment_leakage(raw_p4)
    assert len(diags_p4) == 1
    assert diags_p4[0].path == "pyproject.toml"
    assert diags_p4[0].refs == (_PROVIDER,)


def test_k8_probe_table_n1_n3() -> None:
    """K8 探针表负例 N1-N3（§3.6 L430 字面表；\\b 词边界口径唯一一致版本）。"""
    # N1：model 不在 12 名集 → NO hit
    raw_n1 = make_raw_project(files={"game.yaml": {}}, texts={
        "game.yaml": "capabilities:\n  model: x\n",
    })
    assert check_deployment_leakage(raw_n1) == []

    # N2：api_key_env（下划线是 word char；y 与下划线间无词边界）→ NO hit
    raw_n2 = make_raw_project(files={"game.yaml": {}}, texts={
        "game.yaml": "capabilities:\n  " + _API_KEY + "_env: x\n",
    })
    assert check_deployment_leakage(raw_n2) == []

    # N3：llmsim（12 名最短词后紧跟 word char s，无词边界）→ NO hit
    raw_n3 = make_raw_project(files={"game.yaml": {}}, texts={
        "game.yaml": "capabilities:\n  llmsim: x\n",
    })
    assert check_deployment_leakage(raw_n3) == []


def test_capability_prompt_field_introspection() -> None:
    """字段集内省（断言 #19b / K4 / P5-INV-4）：封闭字段集 + 无禁字段名。"""
    cap_fields = set(InferenceCapabilityProfile.model_fields)
    prompt_fields = set(PromptPolicy.model_fields)
    # 封闭字段集逐字（schemas §3.1 字段表）
    assert cap_fields == {"id", "capability", "min_tier", "ideal_tier", "notes"}
    assert prompt_fields == {"id", "scope", "template_ref", "variables"}
    # 禁字段名零交集（K8 部署 pinning + K4 authority/permission）
    banned = {
        _PROVIDER,
        "model",
        _BASE_URL,
        _API_KEY,
        "endpoint",
        "credential",
        "authority",
        "permission",
    }
    assert not (cap_fields | prompt_fields) & banned


def test_check_dsl_parses_path_rewrite_and_refs() -> None:
    """check_dsl_parses：path 重写为规则/动作 id，refs = 表达式前 40 字符（§3.6 L445）。"""
    # outcome 关键字非法（maybe ∉ {allowed, blocked, uncertain}）→ 单条 DSL_PARSE；
    # 表达式长于 40 字符 → refs 截断面可观察
    long_condition = "if(" + "a" * 60 + " > 1, maybe)"
    ir = make_ir(rules=(make_rule_spec(id="rule_long", condition=long_condition),))
    diags = check_dsl_parses(ir)
    assert len(diags) == 1
    assert diags[0].code == "LLMSIM_DSL_PARSE"
    assert diags[0].path == "rule_long"
    assert diags[0].refs == (long_condition[:40],)


def test_validate_project_raw_none_only_ir_face() -> None:
    """raw=None → 仅 IR 面（K8 文本面与插件面跳过，§3.6 L426 披露）。"""
    ir = make_ir(
        plugin_descriptors=(make_plugin_descriptor(id="ghost"),),
    )
    result = validate_project(ir)  # raw 缺省 None
    codes = [d.code for d in result.diagnostics]
    assert "LLMSIM_DEPLOYMENT_FIELD" not in codes
    assert "LLMSIM_PLUGIN_ENTRY_UNRESOLVED" not in codes
    assert "LLMSIM_PLUGIN_NO_PYPROJECT" not in codes
    assert result.ir is ir


def test_validate_project_ok_semantics_and_sorted_output() -> None:
    """ValidationResult.ok = 无 error 级诊断；diagnostics 尾部已排序（D-P5-12）。"""
    # error 面：DUPLICATE_ID → ok=False
    ir_error = make_ir(
        characters=(make_character(id="npc_x"), make_character(id="npc_x"))
    )
    result_error = validate_project(ir_error)
    assert result_error.ok is False
    assert result_error.ir is ir_error

    # 仅 warning 面：未注册插件描述符 → ok=True（warning 不阻塞，D-P5-08）
    ir_warning = make_ir(plugin_descriptors=(make_plugin_descriptor(id="ghost"),))
    result_warning = validate_project(ir_warning, make_raw_project(files={}))
    assert result_warning.ok is True
    assert [d.code for d in result_warning.diagnostics] == [
        "LLMSIM_PLUGIN_ENTRY_UNRESOLVED"
    ]

    # 排序性：输出序 = (code, path, message) 序
    keys = [(d.code, d.path, d.message) for d in result_error.diagnostics]
    assert keys == sorted(keys)


def test_gameplay_mode_invalid_field_schema_diagnostic() -> None:
    """A7（§6.3 对抗表 L779）：gameplay_modes 非法合并字段 → LLMSIM_SCHEMA。

    落点 = 本文件（SOT A7 行测试列：test_rule_module 外置 → test_validator）；
    违例在 pydantic 层（GameplayModeSpec 封闭字段，mode_type 必填缺失）→
    build_ir 步 2 每 ValidationError 条目 1 条 LLMSIM_SCHEMA，ir = None。
    """
    game = _minimal_game_yaml()
    game["gameplay_modes"] = [{"id": "mode_bad"}]  # mode_type 缺失
    raw = make_raw_project(files={"game.yaml": game})
    built = build_ir(raw)
    assert built.ir is None
    assert len(built.diagnostics) == 1
    diag = built.diagnostics[0]
    assert diag.code == "LLMSIM_SCHEMA"
    assert diag.path == "game.yaml"
    assert diag.severity == "error"
