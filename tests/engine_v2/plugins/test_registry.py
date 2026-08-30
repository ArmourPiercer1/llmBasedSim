"""P5-T05/T06（W5）单元测试：插件注册表（设计文档 §3.10 / §6.1）。

覆盖 §6.1 ``plugins/test_registry.py`` 用例族（逐条）；全部
用例 hermetic（零真实 distribution、零网络、零文件系统写；EP 面 monkeypatch
``importlib.metadata.entry_points`` 运行时属性）：

1. ``__all__`` 7 名台账（逐名逐序，§8.2）+ ENGINE_VERSION 重导出恒等（单点
   权威 = schemas.ENGINE_VERSION，ERR-P5-3 S-A）+ 模型 frozen / enum 值面;
2. ``discover_local_plugins``：合法（1 manifest → 1 RegisteredPlugin
   source=LOCAL_MANIFEST origin=plugins/<id>/plugin.yaml）/ 无 manifest 键
   静默（零注册零诊断）/ 非法 manifest 跳过（1 注册 + 1 ENTRY_INVALID）/
   重复 id（1 DUPLICATE_ID + sorted 键序后者胜）;
3. ``discover_entry_point_plugins`` monkeypatch（2 Fake：合法值
   fake_mod:Inst / 非法值 no-colon → 1 注册 source=ENTRY_POINT + 1
   ENTRY_INVALID + ``fake_mod`` 不在 sys.modules = 断言 #5 metadata-only
   证明）；EP 重名（不同 distribution 同名）→ 零诊断 sorted 序后者胜；
   字段 pattern 违例（EP 名违 id pattern / dist 版本违 version 文法）→
   每条 error 一条 LLMSIM_SCHEMA（path=distribution 名，refs=[loc 点分
   串, type]），该 EP 跳过不注册（never-raise，ERR-P5-14）;
4. ``validate_plugins``：LLMSIM_PLUGIN_NO_PYPROJECT（#8 恰好 1 条，
   path=pyproject.toml）/ LLMSIM_ENGINE_VERSION（manifest 约束 >=9.0.0 → 1
   条）/ LLMSIM_PLUGIN_ENTRY_UNRESOLVED（id=ghost → 1 条，warning 级断言）
   / 5000 位超长版本串比较零异常（ERR-P5-14 纯字符串比较，never-raise 契约）。
"""

from __future__ import annotations

import sys

import pytest

from src.engine_v2.content.schemas import (
    ENGINE_VERSION,
    DiagnosticSeverity,
    PluginDescriptor,
)
from src.engine_v2.plugins import registry
from src.engine_v2.plugins.registry import (
    PluginRegistry,
    PluginSourceKind,
    RegisteredPlugin,
    discover_entry_point_plugins,
    discover_local_plugins,
    validate_plugins,
)
from tests.engine_v2.content.conftest import make_ir, make_raw_project
from tests.engine_v2.plugins.conftest import (
    FakeDistribution,
    FakeEntryPoint,
    make_manifest_dict,
)

#: 7 导出，设计文档 §8.2 导出台账逐名逐序（用例 1 台账基线）。
EXPECTED_ALL: tuple[str, ...] = (
    "ENGINE_VERSION",
    "PluginSourceKind",
    "RegisteredPlugin",
    "PluginRegistry",
    "discover_local_plugins",
    "discover_entry_point_plugins",
    "validate_plugins",
)


# —— 用例族 ——


def test_export_ledger_7_exact_order_and_engine_version_reexport() -> None:
    """用例 1：``__all__`` 7 名台账逐名逐序（§8.2）+ ENGINE_VERSION 重导出
    恒等（不另定义，单点权威 = schemas.ENGINE_VERSION，ERR-P5-3 S-A）+ enum 值面。"""
    assert registry.__all__ == list(EXPECTED_ALL)
    assert registry.ENGINE_VERSION is ENGINE_VERSION
    assert registry.ENGINE_VERSION == "0.5.0"
    assert PluginSourceKind.LOCAL_MANIFEST == "local_manifest"
    assert PluginSourceKind.ENTRY_POINT == "entry_point"
    assert RegisteredPlugin.model_config["frozen"] is True
    assert PluginRegistry.model_config["frozen"] is True


def test_discover_local_valid_single_manifest() -> None:
    """用例 2a：本地合法——1 manifest → 1 RegisteredPlugin
    （source=LOCAL_MANIFEST，origin=plugins/infection/plugin.yaml），零诊断。"""
    raw = make_raw_project(
        files={"plugins/infection/plugin.yaml": make_manifest_dict()},
        plugins_dir_present=True,
    )
    reg, diagnostics = discover_local_plugins(raw)
    assert diagnostics == ()
    assert list(reg.plugins) == ["infection"]
    p = reg.plugins["infection"]
    assert p.source == PluginSourceKind.LOCAL_MANIFEST
    assert p.origin == "plugins/infection/plugin.yaml"
    assert p.manifest.id == "infection"
    assert p.manifest.version == "1.0"


def test_discover_local_no_manifest_key_silent() -> None:
    """用例 2b：无 manifest 的 plugins/<id>/ 目录 = 无键 = 零注册零诊断
    （静默忽略，D-P5-07）——非模板键（.py）不进发现面。"""
    raw = make_raw_project(
        files={"plugins/rogue/plugin_impl.py": {"id": "rogue"}},
        plugins_dir_present=True,
    )
    reg, diagnostics = discover_local_plugins(raw)
    assert reg.plugins == {}
    assert diagnostics == ()


def test_discover_local_invalid_manifest_skipped_diagnostic_kept() -> None:
    """用例 2c：非法 manifest 跳过——2 manifest 其一 entrypoint=bad（无冒号）
    → 1 注册 + 恰好 1 条 LLMSIM_PLUGIN_ENTRY_INVALID（refs=[原值]）。"""
    raw = make_raw_project(
        files={
            "plugins/broken/plugin.yaml": make_manifest_dict(id="broken", entrypoint="bad"),
            "plugins/infection/plugin.yaml": make_manifest_dict(),
        },
        plugins_dir_present=True,
    )
    reg, diagnostics = discover_local_plugins(raw)
    assert list(reg.plugins) == ["infection"]
    assert len(diagnostics) == 1
    d = diagnostics[0]
    assert d.code == "LLMSIM_PLUGIN_ENTRY_INVALID"
    assert d.path == "plugins/broken/plugin.yaml"
    assert d.refs == ("bad",)


def test_discover_local_duplicate_id_one_diagnostic_later_wins() -> None:
    """用例 2d：重复 id——同 id 两键 → 恰好 1 条 LLMSIM_DUPLICATE_ID
    （path="plugins"，refs=[id, 首文件, 重文件]）+ registry 保留 sorted 键序
    后者（version=2.0 / origin=plugins/zzz/plugin.yaml）。"""
    raw = make_raw_project(
        files={
            "plugins/aaa/plugin.yaml": make_manifest_dict(id="dup", version="1.0"),
            "plugins/zzz/plugin.yaml": make_manifest_dict(id="dup", version="2.0"),
        },
        plugins_dir_present=True,
    )
    reg, diagnostics = discover_local_plugins(raw)
    assert len(reg.plugins) == 1
    assert reg.plugins["dup"].manifest.version == "2.0"
    assert reg.plugins["dup"].origin == "plugins/zzz/plugin.yaml"
    assert len(diagnostics) == 1
    d = diagnostics[0]
    assert d.code == "LLMSIM_DUPLICATE_ID"
    assert d.path == "plugins"
    assert d.refs == ("dup", "plugins/aaa/plugin.yaml", "plugins/zzz/plugin.yaml")


def test_discover_entry_point_plugins_metadata_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """用例 3a（断言 #5，metadata-only 证明）：monkeypatch 2 Fake——合法值
    fake_mod:Inst → 1 注册 source=ENTRY_POINT（origin/版本取自假
    distribution）；非法值 no-colon → 恰好 1 条 LLMSIM_PLUGIN_ENTRY_INVALID
    （refs=[distribution 名]）；``fake_mod`` 不在 sys.modules（零动态加载）。"""
    fakes = [
        FakeEntryPoint("infection", "fake_mod:Inst", FakeDistribution("infection-dist", "1.2.3")),
        FakeEntryPoint("broken", "no-colon", FakeDistribution("broken-dist", "0.1.0")),
    ]
    seen_groups: list[str] = []

    def fake_entry_points(group: str = "llmsim.plugins") -> list[FakeEntryPoint]:
        seen_groups.append(group)
        return list(fakes)

    monkeypatch.setattr("importlib.metadata.entry_points", fake_entry_points)
    reg, diagnostics = discover_entry_point_plugins()
    assert seen_groups == ["llmsim.plugins"]
    assert list(reg.plugins) == ["infection"]
    p = reg.plugins["infection"]
    assert p.source == PluginSourceKind.ENTRY_POINT
    assert p.origin == "infection-dist"
    assert p.manifest.id == "infection"
    assert p.manifest.version == "1.2.3"
    assert p.manifest.entrypoint == "fake_mod:Inst"
    assert len(diagnostics) == 1
    d = diagnostics[0]
    assert d.code == "LLMSIM_PLUGIN_ENTRY_INVALID"
    assert d.path == "no-colon"
    assert d.refs == ("broken-dist",)
    assert d.severity == DiagnosticSeverity.ERROR
    assert "fake_mod" not in sys.modules


def test_discover_entry_point_plugins_duplicate_name_later_wins_zero_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """用例 3b：EP 重名（不同 distribution 同名）→ 零诊断，sorted 序后者胜
    （§3.10 docstring 披露口径：同名覆盖，先入者被替换）。"""
    fakes = [
        FakeEntryPoint("infection", "mod_a:A", FakeDistribution("dist-a", "1.0.0")),
        FakeEntryPoint("infection", "mod_b:B", FakeDistribution("dist-b", "2.0.0")),
    ]

    def fake_entry_points(group: str = "llmsim.plugins") -> list[FakeEntryPoint]:
        return list(fakes)

    monkeypatch.setattr("importlib.metadata.entry_points", fake_entry_points)
    reg, diagnostics = discover_entry_point_plugins()
    assert diagnostics == ()
    assert list(reg.plugins) == ["infection"]
    p = reg.plugins["infection"]
    assert p.origin == "dist-b"
    assert p.manifest.version == "2.0.0"
    assert p.manifest.entrypoint == "mod_b:B"


def test_discover_entry_point_id_pattern_violation_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """用例 3c（ERR-P5-14，never-raise）：EP 名违 id pattern（My-Plugin，值
    合法、dist 版本 1.0.0）+ 1 合法（beta，值 mod_b:Inst，dist 版本 1.0）
    → 恰好 1 条 LLMSIM_SCHEMA（severity=ERROR，path=违例 EP 的
    distribution 名，refs=[loc 点分串, type]）+ 恰好 1 注册（beta，
    source=ENTRY_POINT）+ 违例 EP 未注册；构造期异常被捕获转写，零传播。"""
    fakes = [
        FakeEntryPoint("My-Plugin", "mod_x:Inst", FakeDistribution("dist-x", "1.0.0")),
        FakeEntryPoint("beta", "mod_b:Inst", FakeDistribution("dist-b", "1.0")),
    ]

    def fake_entry_points(group: str = "llmsim.plugins") -> list[FakeEntryPoint]:
        return list(fakes)

    monkeypatch.setattr("importlib.metadata.entry_points", fake_entry_points)
    reg, diagnostics = discover_entry_point_plugins()
    assert len(diagnostics) == 1
    d = diagnostics[0]
    assert d.code == "LLMSIM_SCHEMA"
    assert d.severity == DiagnosticSeverity.ERROR
    assert d.path == "dist-x"
    assert d.refs == ("id", "string_pattern_mismatch")
    assert "My-Plugin" in d.message
    assert "mod_x:Inst" in d.message
    assert list(reg.plugins) == ["beta"]
    p = reg.plugins["beta"]
    assert p.source == PluginSourceKind.ENTRY_POINT
    assert p.origin == "dist-b"
    assert p.manifest.version == "1.0"
    assert "My-Plugin" not in reg.plugins


def test_discover_entry_point_version_pattern_violation_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """用例 3d（ERR-P5-14，never-raise）：EP 名与值合法、dist 版本违 version
    文法（PEP 440 预发布形 1.0a1）→ 恰好 1 条 LLMSIM_SCHEMA（refs 含
    version 与 type），零注册该 EP；构造期异常被捕获转写，零传播。"""
    fakes = [
        FakeEntryPoint("alpha", "mod_a:Inst", FakeDistribution("dist-a", "1.0a1")),
    ]

    def fake_entry_points(group: str = "llmsim.plugins") -> list[FakeEntryPoint]:
        return list(fakes)

    monkeypatch.setattr("importlib.metadata.entry_points", fake_entry_points)
    reg, diagnostics = discover_entry_point_plugins()
    assert reg.plugins == {}
    assert len(diagnostics) == 1
    d = diagnostics[0]
    assert d.code == "LLMSIM_SCHEMA"
    assert d.severity == DiagnosticSeverity.ERROR
    assert d.path == "dist-a"
    assert d.refs == ("version", "string_pattern_mismatch")
    assert "alpha" in d.message
    assert "mod_a:Inst" in d.message


def test_discover_entry_point_empty_value_short_circuit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """用例 3e（ERR-P5-14 钉死，SOT §3.10 首条款）：EP.value 空串 → 调用
    EntryPointSpec.from_string 前短路，零异常；恰好 1 条
    LLMSIM_PLUGIN_ENTRY_INVALID（path=EP.name=emptyval，refs=含空串的 1 元
    tuple）+ registry.plugins 空。"""
    fakes = [
        FakeEntryPoint("emptyval", "", FakeDistribution("emptyval-dist", "0.1.0")),
    ]

    def fake_entry_points(group: str = "llmsim.plugins") -> list[FakeEntryPoint]:
        return list(fakes)

    monkeypatch.setattr("importlib.metadata.entry_points", fake_entry_points)
    reg, diagnostics = discover_entry_point_plugins()
    assert reg.plugins == {}
    assert len(diagnostics) == 1
    d = diagnostics[0]
    assert d.code == "LLMSIM_PLUGIN_ENTRY_INVALID"
    assert d.severity == DiagnosticSeverity.ERROR
    assert d.path == "emptyval"
    assert d.refs == ("",)


def test_validate_plugins_no_pyproject_exactly_one() -> None:
    """用例 4a（断言 #8）：plugins_dir_present ∧ ¬pyproject_present → 恰好 1
    条 LLMSIM_PLUGIN_NO_PYPROJECT（path="pyproject.toml"，refs 逐字）；
    负例：pyproject 存在 / raw=None → 零该码。"""
    raw = make_raw_project(
        files={"plugins/infection/plugin.yaml": make_manifest_dict()},
        plugins_dir_present=True,
        pyproject_present=False,
    )
    reg, discovery_diags = discover_local_plugins(raw)
    assert discovery_diags == ()
    diagnostics = validate_plugins(reg, make_ir(), raw=raw)
    assert len(diagnostics) == 1
    d = diagnostics[0]
    assert d.code == "LLMSIM_PLUGIN_NO_PYPROJECT"
    assert d.path == "pyproject.toml"
    assert d.refs == ("plugins/ present but pyproject.toml missing",)
    assert d.severity == DiagnosticSeverity.ERROR

    raw_ok = make_raw_project(
        files={"plugins/infection/plugin.yaml": make_manifest_dict()},
        plugins_dir_present=True,
        pyproject_present=True,
    )
    reg_ok, _ = discover_local_plugins(raw_ok)
    assert validate_plugins(reg_ok, make_ir(), raw=raw_ok) == []
    assert validate_plugins(reg, make_ir()) == []


def test_validate_plugins_engine_version_constraint() -> None:
    """用例 4b：manifest engine_version=>=9.0.0（引擎 0.5.0）→ 恰好 1 条
    LLMSIM_ENGINE_VERSION（path=manifest.id，refs=[constraint,
    engine_version]）；满足面（"" / >=0.5.0 / 0.5 / 0.5.0）→ 零诊断（D-P5-06
    补 0 比较口径）。"""
    raw = make_raw_project(
        files={
            "plugins/strict/plugin.yaml": make_manifest_dict(
                id="strict", engine_version=">=9.0.0"
            )
        },
        plugins_dir_present=True,
    )
    reg, discovery_diags = discover_local_plugins(raw)
    assert discovery_diags == ()
    diagnostics = validate_plugins(reg, make_ir())
    assert len(diagnostics) == 1
    d = diagnostics[0]
    assert d.code == "LLMSIM_ENGINE_VERSION"
    assert d.path == "strict"
    assert d.refs == (">=9.0.0", "0.5.0")
    assert d.severity == DiagnosticSeverity.ERROR

    for ok_constraint in ("", ">=0.5.0", "0.5", "0.5.0"):
        raw_ok = make_raw_project(
            files={
                "plugins/ok/plugin.yaml": make_manifest_dict(
                    id="ok", engine_version=ok_constraint
                )
            },
            plugins_dir_present=True,
        )
        reg_ok, _ = discover_local_plugins(raw_ok)
        assert validate_plugins(reg_ok, make_ir()) == [], ok_constraint


def test_validate_plugins_engine_version_long_digit_strings() -> None:
    """用例 4b-补（F-2，ERR-P5-14 同族，never-raise）：版本比较纯字符串
    机制（版本路径零 int() 调用）——(a) engine_version 参数 = 5000 个 1 的
    串、manifest 约束 >=1 → 零异常且满足（零诊断）；(b) 约束形式合法但
    比较目标超长不满足（约束 >= 5000 个 2 串 对 目标 1）→ 恰好 1 条
    LLMSIM_ENGINE_VERSION 零异常；(c) 约束 >=2 对 目标 1（W3 同口径对）
    → 恰好 1 条零异常。"""
    big_one = "1" * 5000
    raw = make_raw_project(
        files={
            "plugins/strict/plugin.yaml": make_manifest_dict(
                id="strict", engine_version=">=1"
            )
        },
        plugins_dir_present=True,
    )
    reg, discovery_diags = discover_local_plugins(raw)
    assert discovery_diags == ()
    assert validate_plugins(reg, make_ir(), engine_version=big_one) == []

    for constraint in (">=" + "2" * 5000, ">=2"):
        raw_bad = make_raw_project(
            files={
                "plugins/strict/plugin.yaml": make_manifest_dict(
                    id="strict", engine_version=constraint
                )
            },
            plugins_dir_present=True,
        )
        reg_bad, _ = discover_local_plugins(raw_bad)
        diagnostics = validate_plugins(reg_bad, make_ir(), engine_version="1")
        assert len(diagnostics) == 1
        d = diagnostics[0]
        assert d.code == "LLMSIM_ENGINE_VERSION"
        assert d.severity == DiagnosticSeverity.ERROR
        assert d.path == "strict"
        assert d.refs == (constraint, "1")


def test_validate_plugins_unresolved_descriptor_warning() -> None:
    """用例 4c：ir.plugin_descriptors 声明序——id=ghost 不在注册表 → 恰好 1
    条 LLMSIM_PLUGIN_ENTRY_UNRESOLVED（severity=WARNING 断言，path=descriptor.id，
    refs=[descriptor.source]）；已注册 id（infection）不触发。"""
    raw = make_raw_project(
        files={"plugins/infection/plugin.yaml": make_manifest_dict()},
        plugins_dir_present=True,
    )
    reg, _ = discover_local_plugins(raw)
    ir = make_ir(
        plugin_descriptors=(
            PluginDescriptor(id="ghost"),
            PluginDescriptor(id="infection"),
        )
    )
    diagnostics = validate_plugins(reg, ir)
    assert len(diagnostics) == 1
    d = diagnostics[0]
    assert d.code == "LLMSIM_PLUGIN_ENTRY_UNRESOLVED"
    assert d.severity == DiagnosticSeverity.WARNING
    assert d.path == "ghost"
    assert d.refs == ("local",)
