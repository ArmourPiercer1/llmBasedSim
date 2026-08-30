"""P5-T05（W5）单元测试：本地插件 manifest 解析（设计文档 §3.8 / §6.1）。

覆盖 §6.1 ``plugins/test_manifest.py`` 用例族（逐条）；全部
用例 hermetic（零真实 distribution、零网络、零文件系统写）：

1. ``__all__`` 3 名台账（逐名逐序，§8.2）+ PluginManifest /
   PluginManifestParseResult frozen / extra="forbid" 面（硬不变量）;
2. ``parse_plugin_manifest`` 全字段（最小合法 + 全可选字段 /
   ``engine_version`` 约束文法面）;
3. id pattern 边界（64 字符合法 / 65 字符非法 → SCHEMA）;
4. entrypoint 文法（恰一个 ``:``）：a:b:c 非法（2 冒号）/ :X 非法 / a:
   非法 / mod:attr 合法 / My.Mod:Attr 合法（大写标识符）;
5. 缺 id / 缺 version / 缺 entrypoint 各 1 例（SCHEMA，refs = [loc, type]）;
   未知键 1 例（SCHEMA extra）; 非 dict raw → SCHEMA（refs=()）;
6. entrypoint 文法同值核验（manifest.py / api.py / conftest 正则常量同值 +
   两纯解析函数判定一致，设计文档 §3.9 共享口径条款）。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.engine_v2.plugins import api, manifest
from src.engine_v2.plugins.manifest import (
    PluginManifest,
    PluginManifestParseResult,
    parse_plugin_manifest,
)
from tests.engine_v2.plugins.conftest import PLUGIN_ENTRYPOINT_PATTERN, make_manifest_dict

#: 3 导出，设计文档 §8.2 导出台账逐名逐序（用例 1 台账基线）。
EXPECTED_ALL: tuple[str, ...] = (
    "PluginManifest",
    "PluginManifestParseResult",
    "parse_plugin_manifest",
)

_PATH_LABEL = "plugins/infection/plugin.yaml"


# —— 用例族 ——


def test_export_ledger_3_exact_order_and_frozen_models() -> None:
    """用例 1：``__all__`` 3 名台账逐名逐序（§8.2）+ 两模型 frozen /
    extra="forbid" 面（硬不变量 5 同源）。"""
    assert manifest.__all__ == list(EXPECTED_ALL)
    assert PluginManifest.model_config["frozen"] is True
    assert PluginManifest.model_config["extra"] == "forbid"
    assert PluginManifestParseResult.model_config["frozen"] is True
    assert PluginManifestParseResult.model_config["extra"] == "forbid"
    with pytest.raises(ValidationError):
        PluginManifest(id="infection", version="1.0", entrypoint="m:A", unexpected=1)


def test_parse_minimal_valid_manifest() -> None:
    """用例 2a：最小合法 manifest（id=infection / version=1.0 /
    entrypoint=my_game.systems.infection:InfectionSystem）→ (manifest, ())。"""
    result = parse_plugin_manifest(_PATH_LABEL, make_manifest_dict())
    assert result.diagnostics == ()
    assert result.manifest is not None
    m = result.manifest
    assert m.id == "infection"
    assert m.version == "1.0"
    assert m.entrypoint == "my_game.systems.infection:InfectionSystem"
    assert m.requires == ()
    assert m.optional == ()
    assert m.conflicts == ()
    assert m.engine_version == ""


def test_parse_full_fields_including_engine_version() -> None:
    """用例 2b：全字段（requires / optional / conflicts / engine_version 合法
    约束文法 ``>=V``）解析照录。"""
    raw = make_manifest_dict(
        requires=("core.rules",),
        optional=("extra",),
        conflicts=("other",),
        engine_version=">=0.5.0",
    )
    result = parse_plugin_manifest(_PATH_LABEL, raw)
    assert result.diagnostics == ()
    assert result.manifest is not None
    m = result.manifest
    assert m.requires == ("core.rules",)
    assert m.optional == ("extra",)
    assert m.conflicts == ("other",)
    assert m.engine_version == ">=0.5.0"


def test_id_pattern_boundary_64_valid_65_rejected() -> None:
    """用例 3：id pattern 边界——64 字符（a + z×63）合法；65 字符（a + z×64）
    → 恰好 1 条 LLMSIM_SCHEMA（refs = [loc, type]）。"""
    ok_id = "a" + "z" * 63
    result = parse_plugin_manifest(_PATH_LABEL, make_manifest_dict(id=ok_id))
    assert result.diagnostics == ()
    assert result.manifest is not None
    assert result.manifest.id == ok_id

    bad_id = "a" + "z" * 64
    result = parse_plugin_manifest(_PATH_LABEL, make_manifest_dict(id=bad_id))
    assert result.manifest is None
    assert len(result.diagnostics) == 1
    d = result.diagnostics[0]
    assert d.code == "LLMSIM_SCHEMA"
    assert d.path == _PATH_LABEL
    assert d.refs == ("id", "string_pattern_mismatch")


def test_entrypoint_grammar_battery_exactly_one_colon() -> None:
    """用例 4：entrypoint 文法（恰一个 ``:``）——a:b:c（2 冒号）/ :X（无
    module）/ a:（无 attribute）非法 → LLMSIM_PLUGIN_ENTRY_INVALID（refs=[
    原值]）；mod:attr / My.Mod:Attr（大写标识符）合法。"""
    cases: tuple[tuple[str, bool], ...] = (
        ("a:b:c", False),
        (":X", False),
        ("a:", False),
        ("mod:attr", True),
        ("My.Mod:Attr", True),
    )
    for value, valid in cases:
        result = parse_plugin_manifest(_PATH_LABEL, make_manifest_dict(entrypoint=value))
        if valid:
            assert result.manifest is not None, value
            assert result.diagnostics == (), value
            assert result.manifest.entrypoint == value
        else:
            assert result.manifest is None, value
            assert len(result.diagnostics) == 1, value
            d = result.diagnostics[0]
            assert d.code == "LLMSIM_PLUGIN_ENTRY_INVALID", value
            assert d.path == _PATH_LABEL
            assert d.refs == (value,)


def test_missing_required_fields_each_one_schema_diagnostic() -> None:
    """用例 5a：缺 id / 缺 version / 缺 entrypoint 各 1 例 → 恰好 1 条
    LLMSIM_SCHEMA（refs = [loc 点分串, type]，type = missing）。"""
    for missing in ("id", "version", "entrypoint"):
        raw = make_manifest_dict()
        del raw[missing]
        result = parse_plugin_manifest(_PATH_LABEL, raw)
        assert result.manifest is None, missing
        assert len(result.diagnostics) == 1, missing
        d = result.diagnostics[0]
        assert d.code == "LLMSIM_SCHEMA", missing
        assert d.path == _PATH_LABEL
        assert d.refs == (missing, "missing"), missing


def test_unknown_key_produces_schema_diagnostic() -> None:
    """用例 5b：未知键 1 例（extra="forbid" 命中）→ 恰好 1 条 LLMSIM_SCHEMA
    （refs = [键名, extra_forbidden]）。"""
    result = parse_plugin_manifest(_PATH_LABEL, make_manifest_dict(bogus=1))
    assert result.manifest is None
    assert len(result.diagnostics) == 1
    d = result.diagnostics[0]
    assert d.code == "LLMSIM_SCHEMA"
    assert d.path == _PATH_LABEL
    assert d.refs == ("bogus", "extra_forbidden")


def test_non_dict_raw_produces_schema_diagnostic_with_empty_refs() -> None:
    """用例 5c：非 dict raw（list 根）→ (None, [LLMSIM_SCHEMA path=path_label
    refs=()])（§3.8 L479 非 dict 分支；refs 默认空 tuple）。"""
    result = parse_plugin_manifest(_PATH_LABEL, [1, 2, 3])
    assert result.manifest is None
    assert len(result.diagnostics) == 1
    d = result.diagnostics[0]
    assert d.code == "LLMSIM_SCHEMA"
    assert d.path == _PATH_LABEL
    assert d.refs == ()


def test_entrypoint_pattern_same_value_and_parsers_agree() -> None:
    """用例 6：entrypoint 文法同值核验——manifest.py / api.py / conftest 三
    常量同值；两纯解析函数在测试电池上判定一致（None 或 (module,
    attribute) 逐对相等）。"""
    assert manifest._ENTRYPOINT_PATTERN == api._ENTRYPOINT_PATTERN
    assert manifest._ENTRYPOINT_PATTERN == PLUGIN_ENTRYPOINT_PATTERN
    battery = (
        "a:b:c",
        ":X",
        "a:",
        "mod:attr",
        "My.Mod:Attr",
        "my_game.systems.infection:InfectionSystem",
        "",
        "a b:c",
    )
    for value in battery:
        assert manifest._split_entrypoint(value) == api._split_entrypoint(value), value
