"""P5-T03（W2）单元测试：项目加载器（设计文档 §3.3 / §6.1）。

覆盖 §6.1 ``content/test_loader.py`` 用例族（逐条）；全部用例 hermetic
（tmp_path 目录树构造，零网络、零 W6 fixture 依赖）：

1. ``__all__`` 6 名台账（逐名逐序，§8.2）+ ProjectLoadResult frozen /
   extra=forbid 面（硬不变量 5）;
2. ``LAYOUT_REQUIRED`` / ``LAYOUT_OPTIONAL`` 封闭集（§3.3 L317/L319 逐字，
   9 模板声明序 = 遍历序）;
3. ``load_project`` 6 步流程：步 1 root 不存在 / 非目录 → raw = None +
   FILE_MISSING（path = f"{root}/game.yaml" 原参口径）；步 2 game.yaml 缺失
   → FILE_MISSING 且 raw 继续构建（双保险口径）/ 解析失败 → YAML_PARSE
   （path="game.yaml"）且继续；步 3 v1 形状拒绝（恰好 1 条
   LLMSIM_PROJECT_FORMAT_V1，refs 逐字，raw = None，停止）；步 4 可选模板
   命中集 sorted + 逐文件解析失败继续；步 5 pyproject.toml / plugins/
   存在性（K8 扫描面数据源：raw.texts 与 pyproject_text 保留原文）;
4. ``read_yaml_file`` 纯 helper 直接调用面（dict 成功 / list / str 根非 dict
   → refs = ["root-not-dict"] / YAML 语法错 / 文件缺失 OSError → 全成诊断，
   永不 raise）;
5. ``detect_v1_shape`` 判据真值表（D-P5-04 公式逐字）。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from src.engine_v2.content import loader
from src.engine_v2.content.loader import (
    LAYOUT_OPTIONAL,
    LAYOUT_REQUIRED,
    ProjectLoadResult,
    detect_v1_shape,
    load_project,
    read_yaml_file,
)
from src.engine_v2.content.schemas import DiagnosticSeverity

#: 6 导出，设计文档 §8.2 导出台账逐名逐序（用例 1 台账基线）。
EXPECTED_ALL: tuple[str, ...] = (
    "LAYOUT_REQUIRED",
    "LAYOUT_OPTIONAL",
    "ProjectLoadResult",
    "load_project",
    "read_yaml_file",
    "detect_v1_shape",
)

#: LAYOUT_OPTIONAL 9 模板（设计文档 §3.3 L319 逐字，声明序 = 遍历序）。
EXPECTED_LAYOUT_OPTIONAL: tuple[tuple[str, str, str], ...] = (
    ("world/*.yaml", "world", "world"),
    ("characters/*.yaml", "characters", "characters"),
    ("items/*.yaml", "items", "items"),
    ("rules/*.yaml", "rules", "rules"),
    ("actions/*.yaml", "actions", "actions"),
    ("prompts/*.yaml", "prompts", "prompts"),
    ("scenarios/*.yaml", "scenarios", "scenarios"),
    ("modules/*.yaml", "modules", "modules"),
    ("plugins/*/plugin.yaml", "plugins", "plugin_manifest"),
)

#: 最小合法 v2 game.yaml 文本（loader 不做 schema 校验，仅需可解析的 v2 形状）。
_V2_GAME_TEXT = """\
manifest:
  schema_version: "2"
  project_id: proj_g1
  name: V2 Project
scenario:
  id: scenario_main
  max_ticks: 20
  ticks_per_game_minute: 1.0
  game_time:
    hour: 9
    minute: 30
player:
  player_id: player_1
  name: Wanderer
"""


def _write_v2_game(root: Path) -> None:
    """在 root 写入最小合法 v2 game.yaml。"""
    root.joinpath("game.yaml").write_text(_V2_GAME_TEXT, encoding="utf-8")


# —— 用例族 ——


def test_export_ledger_6_exact_order_and_frozen_result_model() -> None:
    """用例 1：``__all__`` 6 名台账逐名逐序（§8.2）+ ProjectLoadResult frozen /
    extra="forbid" 面（硬不变量 5）。"""
    assert loader.__all__ == list(EXPECTED_ALL)
    assert loader.ProjectLoadResult.model_config["frozen"] is True
    assert loader.ProjectLoadResult.model_config["extra"] == "forbid"
    with pytest.raises(ValidationError):
        ProjectLoadResult(root="/p", raw=None, diagnostics=(), unexpected=1)
    result = ProjectLoadResult(root="/p", raw=None, diagnostics=())
    with pytest.raises(ValidationError):
        result.diagnostics = ()  # type: ignore[misc]  # frozen：字段再赋值拒绝


def test_layout_required_closed_set() -> None:
    """用例 2：LAYOUT_REQUIRED 封闭集（§3.3 L317 逐字：仅 game.yaml）。"""
    assert LAYOUT_REQUIRED == ("game.yaml",)


def test_layout_optional_9_templates_verbatim_and_order() -> None:
    """用例 3：LAYOUT_OPTIONAL 9 模板逐字 + 声明序 = 遍历序（§3.3 L319 逐字；
   深度封闭：plugins/*/plugin.yaml 恰好两层）。"""
    assert len(LAYOUT_OPTIONAL) == 9
    assert LAYOUT_OPTIONAL == EXPECTED_LAYOUT_OPTIONAL


def test_load_project_root_missing_or_not_dir_returns_file_missing(tmp_path: Path) -> None:
    """用例 4：步 1——root 不存在 / 是普通文件（非目录）→ raw = None + 恰好
   1 条 LLMSIM_FILE_MISSING（path = f"{root}/game.yaml"，**原参**口径，非
   resolve 后路径），result.root = resolve 后路径。"""
    missing_root = tmp_path / "does_not_exist"
    result = load_project(missing_root)
    assert result.raw is None
    assert len(result.diagnostics) == 1
    d = result.diagnostics[0]
    assert (d.code, d.path, d.refs) == (
        "LLMSIM_FILE_MISSING",
        f"{missing_root}/game.yaml",
        (),
    )
    assert d.severity == DiagnosticSeverity.ERROR
    assert result.root == str(missing_root.resolve())

    # 普通文件作为 root（非目录）同口径
    plain_file = tmp_path / "afile.txt"
    plain_file.write_text("x", encoding="utf-8")
    result2 = load_project(plain_file)
    assert result2.raw is None
    assert [(d.code, d.path) for d in result2.diagnostics] == [
        ("LLMSIM_FILE_MISSING", f"{plain_file}/game.yaml"),
    ]


def test_load_project_game_yaml_missing_file_missing_raw_continues(tmp_path: Path) -> None:
    """用例 5：步 2——game.yaml 缺失 → 恰好 1 条 LLMSIM_FILE_MISSING
   （path = "game.yaml" 相对口径），**不中止**：raw 继续构建（空 files /
   texts），步 5 存在性字段为 False。"""
    result = load_project(tmp_path)
    assert result.raw is not None
    assert len(result.diagnostics) == 1
    d = result.diagnostics[0]
    assert (d.code, d.path, d.refs) == ("LLMSIM_FILE_MISSING", "game.yaml", ())
    raw = result.raw
    assert raw.files == {}
    assert raw.texts == {}
    assert raw.root == str(tmp_path.resolve())
    assert raw.pyproject_present is False
    assert raw.pyproject_text is None
    assert raw.plugins_dir_present is False


def test_load_project_game_yaml_parse_failure_yaml_parse_and_continue(tmp_path: Path) -> None:
    """用例 6：步 2——game.yaml YAML 语法错误 → 恰好 1 条 LLMSIM_YAML_PARSE
   （path = "game.yaml"，refs = ()），不中止：余下可选文件照常读入；
   game.yaml 不入 raw.files / raw.texts（build_ir 步 1 双保险口径的数据源）。"""
    (tmp_path / "game.yaml").write_text("manifest: [unclosed\n", encoding="utf-8")
    items_dir = tmp_path / "items"
    items_dir.mkdir()
    (items_dir / "good.yaml").write_text("items: []\n", encoding="utf-8")
    result = load_project(tmp_path)
    assert result.raw is not None
    assert [(d.code, d.path, d.refs) for d in result.diagnostics] == [
        ("LLMSIM_YAML_PARSE", "game.yaml", ()),
    ]
    assert "game.yaml" not in result.raw.files
    assert "game.yaml" not in result.raw.texts
    assert result.raw.files["items/good.yaml"] == {"items": []}


def test_load_project_v1_shape_rejected_stops_and_refs_verbatim(tmp_path: Path) -> None:
    """用例 7：步 3——v1 形状（顶层 world/player 且无 manifest）→ 恰好 1 条
   LLMSIM_PROJECT_FORMAT_V1（path = "game.yaml"，refs 逐字 §3.3），raw = None，
   **停止**（可选文件不再读入，无后续诊断）。"""
    (tmp_path / "game.yaml").write_text(
        "world:\n  name: v1 world\nplayer:\n  name: hero\n", encoding="utf-8"
    )
    world_dir = tmp_path / "world"
    world_dir.mkdir()
    (world_dir / "w.yaml").write_text("world:\n  name: x\n  locations: []\n", encoding="utf-8")
    result = load_project(tmp_path)
    assert result.raw is None
    assert len(result.diagnostics) == 1
    d = result.diagnostics[0]
    assert (d.code, d.path) == ("LLMSIM_PROJECT_FORMAT_V1", "game.yaml")
    assert d.refs == ("no manifest", "v1 top-level world/player")
    assert d.severity == DiagnosticSeverity.ERROR


def test_load_project_optional_dirs_absent_zero_diagnostics(tmp_path: Path) -> None:
    """用例 8：合法 v2 最小项目（仅 game.yaml，8 可选节目录全缺席）→ 零诊断
   （D-P5-05：缺可选节目录 = 合法空），raw.files / texts 键面 = {"game.yaml"}。"""
    _write_v2_game(tmp_path)
    result = load_project(tmp_path)
    assert result.diagnostics == ()
    assert result.raw is not None
    assert set(result.raw.files) == {"game.yaml"}
    assert set(result.raw.texts) == {"game.yaml"}
    assert result.raw.pyproject_present is False
    assert result.raw.plugins_dir_present is False


def test_load_project_section_files_read_and_parse_failure_continues(tmp_path: Path) -> None:
    """用例 9：步 4——可选模板命中集 sorted + 逐文件 read_yaml_file；解析失败
   → LLMSIM_YAML_PARSE（path = 相对路径，POSIX 分隔）且**继续**下一文件；
   成功文件按 模板序 + sorted 序 入 raw.files / texts。"""
    _write_v2_game(tmp_path)
    items_dir = tmp_path / "items"
    items_dir.mkdir()
    (items_dir / "a_good.yaml").write_text("items: []\n", encoding="utf-8")
    (items_dir / "b_bad.yaml").write_text("items: [broken\n", encoding="utf-8")
    (items_dir / "c_good.yaml").write_text(
        "items:\n  - {id: key_c, name: Key}\n", encoding="utf-8"
    )
    world_dir = tmp_path / "world"
    world_dir.mkdir()
    (world_dir / "main.yaml").write_text(
        "world:\n  name: W\n  locations: []\n", encoding="utf-8"
    )
    result = load_project(tmp_path)
    assert result.raw is not None
    assert [(d.code, d.path, d.refs) for d in result.diagnostics] == [
        ("LLMSIM_YAML_PARSE", "items/b_bad.yaml", ()),
    ]
    assert set(result.raw.files) == {
        "game.yaml",
        "world/main.yaml",
        "items/a_good.yaml",
        "items/c_good.yaml",
    }
    assert result.raw.files["items/c_good.yaml"] == {"items": [{"id": "key_c", "name": "Key"}]}
    assert result.raw.files["world/main.yaml"] == {"world": {"name": "W", "locations": []}}


def test_raw_project_texts_preserve_original_and_pyproject_and_plugins(tmp_path: Path) -> None:
    """用例 10：D-P5-11 K8 扫描面数据源——raw.texts 保留各 YAML **原文**
   （含注释 / 中文，UTF-8 逐字）；pyproject.toml 存在 → pyproject_present +
   pyproject_text 原文（不做 TOML 解析）；plugins/<name>/plugin.yaml 命中
   → plugins_dir_present + 入 raw.files / texts。"""
    game_text = (
        "# 项目注释行\n"
        "manifest:\n"
        '  schema_version: "2"\n'
        "  project_id: proj_cn\n"
        "  name: 中文项目\n"
        "player:\n"
        "  player_id: player_1\n"
        "  name: Wanderer\n"
    )
    (tmp_path / "game.yaml").write_text(game_text, encoding="utf-8")
    pyproject_text = '[project]\nname = "v2-project"\n'
    (tmp_path / "pyproject.toml").write_text(pyproject_text, encoding="utf-8")
    plugin_dir = tmp_path / "plugins" / "myplug"
    plugin_dir.mkdir(parents=True)
    plugin_text = "id: myplug\nsource: local\n"
    (plugin_dir / "plugin.yaml").write_text(plugin_text, encoding="utf-8")

    result = load_project(tmp_path)
    assert result.diagnostics == ()
    raw = result.raw
    assert raw is not None
    assert raw.texts["game.yaml"] == game_text
    assert "中文项目" in raw.texts["game.yaml"]
    assert raw.pyproject_present is True
    assert raw.pyproject_text == pyproject_text
    assert raw.plugins_dir_present is True
    assert raw.files["plugins/myplug/plugin.yaml"] == {"id": "myplug", "source": "local"}
    assert raw.texts["plugins/myplug/plugin.yaml"] == plugin_text


def test_read_yaml_file_direct_dict_list_str_syntax_error_and_oserror(tmp_path: Path) -> None:
    """用例 11：read_yaml_file 纯 helper 直接调用面（永不 raise）——
   dict 根成功；list / str 根 → refs = ["root-not-dict"]；YAML 语法错 /
   文件缺失（OSError）→ refs = ()；path 恒为 label 参数口径。"""
    good = tmp_path / "good.yaml"
    good.write_text("a: 1\nb:\n  - x\n", encoding="utf-8")
    value, diags = read_yaml_file(good, "good.yaml")
    assert value == {"a": 1, "b": ["x"]}
    assert diags == ()

    list_file = tmp_path / "list.yaml"
    list_file.write_text("- 1\n- 2\n", encoding="utf-8")
    value, diags = read_yaml_file(list_file, "list.yaml")
    assert value is None
    assert [(d.code, d.path, d.refs) for d in diags] == [
        ("LLMSIM_YAML_PARSE", "list.yaml", ("root-not-dict",)),
    ]

    str_file = tmp_path / "str.yaml"
    str_file.write_text("just a string\n", encoding="utf-8")
    value, diags = read_yaml_file(str_file, "str.yaml")
    assert value is None
    assert [(d.code, d.path, d.refs) for d in diags] == [
        ("LLMSIM_YAML_PARSE", "str.yaml", ("root-not-dict",)),
    ]

    bad = tmp_path / "bad.yaml"
    bad.write_text("a: [1,\n", encoding="utf-8")
    value, diags = read_yaml_file(bad, "bad.yaml")
    assert value is None
    assert [(d.code, d.path, d.refs) for d in diags] == [
        ("LLMSIM_YAML_PARSE", "bad.yaml", ()),
    ]

    missing = tmp_path / "missing.yaml"
    value, diags = read_yaml_file(missing, "missing.yaml")
    assert value is None
    assert [(d.code, d.path, d.refs) for d in diags] == [
        ("LLMSIM_YAML_PARSE", "missing.yaml", ()),
    ]


def test_detect_v1_shape_truth_table() -> None:
    """用例 12：detect_v1_shape 判据真值表（D-P5-04 公式逐字：dict ∧ 无
   manifest ∧ (有 world ∨ 有 player)）。"""
    assert detect_v1_shape({"world": {}, "player": {}}) is True
    assert detect_v1_shape({"world": {}}) is True
    assert detect_v1_shape({"player": {}}) is True
    assert detect_v1_shape({"manifest": {}, "player": {}}) is False
    assert detect_v1_shape({"manifest": {}}) is False
    assert detect_v1_shape({}) is False
    assert detect_v1_shape(["world"]) is False
    assert detect_v1_shape("world") is False
    assert detect_v1_shape(None) is False
