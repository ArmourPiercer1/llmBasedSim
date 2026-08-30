"""engine_v2 content 层 P5 项目加载器（P5-T03 / W2，设计文档 §3.3）。

依据 ``docs/v2/contracts/P5-project-format-module-plugin-dsl-design.md``（下称
"设计文档"，P5-DESIGN 冻结态）§3.3 字段级规格（6 导出）：

- **定位**：文件系统 + YAML 解析的 IO 边界。**只读**（P5-INV-2：零写操作，
  无 makedirs / 无 open 写模式）；封闭路径模板（D-P5-07：发现面 = 固定模板，
  非任意 walk；模板深度封闭，``plugins/*/plugin.yaml`` 恰好两层；全树零任意
  walk、零 .py 扫描）；
- **D-P5-04 零 v1 兼容**：``detect_v1_shape`` 判据公式 = 顶层 world/player 且
  无 manifest → 恰好 1 条 ``LLMSIM_PROJECT_FORMAT_V1``（refs 逐字）+ 停止
  （raw = None，不编译余下文件）；
- **D-P5-05 严格度基线**：缺可选节目录 = 合法空（零诊断）；
- **D-P5-11 K8 扫描面数据源**：loader 保留原文——``raw.texts``（各 YAML 原文）
  与 ``pyproject_text``（项目根 pyproject.toml 原文，不做 TOML 解析）；
- **D-P5-15 确定性纪律**：遍历序 = LAYOUT_OPTIONAL 声明序，每模板命中集
  ``sorted()``，诊断按 6 步显式步序追加。

``__all__`` 6 名按设计文档 §8.2 导出台账逐名逐序。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Final

import yaml

from src.engine_v2.content.schemas import (
    _ContractModel,
    Diagnostic,
    DiagnosticSeverity,
    RawProject,
)

__all__ = [
    "LAYOUT_REQUIRED",
    "LAYOUT_OPTIONAL",
    "ProjectLoadResult",
    "load_project",
    "read_yaml_file",
    "detect_v1_shape",
]

#: 必需文件封闭集（设计文档 §3.3 L317，逐字）。
LAYOUT_REQUIRED: Final[tuple[str, ...]] = ("game.yaml",)

#: 可选模板封闭集 (glob, 节名, 种类)——9 模板，声明序 = 遍历序
#: （设计文档 §3.3 L319，逐字；模板深度封闭，全树零 .py 扫描）。
LAYOUT_OPTIONAL: Final[tuple[tuple[str, str, str], ...]] = (
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


class ProjectLoadResult(_ContractModel):
    """load_project 产物（设计文档 §3.3：frozen；v1 形状拒绝时 ``raw`` =
    None，D-P5-04；root 不存在 / 非目录时 ``raw`` = None，步 1）。"""

    root: str
    raw: RawProject | None
    diagnostics: tuple[Diagnostic, ...]


# —— 私有工具 ——


def _parse_diagnostic(label: str, *, root_not_dict: bool) -> Diagnostic:
    """``LLMSIM_YAML_PARSE`` 诊断（path = label；根非 dict 形态加
    refs = ["root-not-dict"]，设计文档 §3.3 ``read_yaml_file`` 逐字口径）。"""
    if root_not_dict:
        return Diagnostic(
            code="LLMSIM_YAML_PARSE",
            severity=DiagnosticSeverity.ERROR,
            path=label,
            message="YAML 根节点不是 dict 映射",
            refs=("root-not-dict",),
        )
    return Diagnostic(
        code="LLMSIM_YAML_PARSE",
        severity=DiagnosticSeverity.ERROR,
        path=label,
        message="YAML 解析失败",
        refs=(),
    )


# —— 公开面（§8.2 台账序）——


def load_project(root: str | Path) -> ProjectLoadResult:
    """项目根 → RawProject（设计文档 §3.3 六步流程，步序即诊断追加序）。

    1. root 不存在 / 非目录 → (None, [LLMSIM_FILE_MISSING
       path=f"{root}/game.yaml"])；
    2. 读 ``game.yaml``：缺 → LLMSIM_FILE_MISSING；先取原文（该原文是
       ``raw.texts`` 的唯一来源），再走 ``read_yaml_file`` 解析面（解析失败
       → LLMSIM_YAML_PARSE path="game.yaml"）；成功 → ``raw.files`` /
       ``raw.texts`` 写入（build_ir 步 1 双保险与 D-P5-11 K8 扫描面的数据源）；
    3. ``detect_v1_shape(game_raw)`` → True → (None, [LLMSIM_PROJECT_FORMAT_V1
       path="game.yaml", refs=["no manifest", "v1 top-level world/player"]])，
       **停止**（不编译余下文件，D-P5-04）；
    4. 遍历 LAYOUT_OPTIONAL（模板序）：glob 命中集 ``sorted()``；逐文件
       ``read_yaml_file``；解析失败 → LLMSIM_YAML_PARSE（path=相对路径，
       **继续**下一文件，不中止）；成功 → files[rel] = 值、texts[rel] = 原文；
    5. ``pyproject_present`` = 根下 pyproject.toml 存在（存在时其原文读入
       ``pyproject_text``）；``plugins_dir_present`` = 根下 plugins/ 是目录；
    6. 返回 (RawProject, 诊断集)。

    只读（P5-INV-2）：零写操作；对文件内容 / 解析级错误不 raise（全部成诊断）。
    """
    root_path = Path(root).resolve()

    # —— 步 1：root 不存在 / 非目录 ——
    if not root_path.is_dir():
        return ProjectLoadResult(
            root=str(root_path),
            raw=None,
            diagnostics=(
                Diagnostic(
                    code="LLMSIM_FILE_MISSING",
                    severity=DiagnosticSeverity.ERROR,
                    path=f"{root}/game.yaml",
                    message="项目根不存在或不是目录",
                ),
            ),
        )

    diagnostics: list[Diagnostic] = []
    files: dict[str, Any] = {}
    texts: dict[str, str] = {}

    # —— 步 2：game.yaml（原文先取；解析失败不中止）——
    game_path = root_path / "game.yaml"
    game_raw: Any = None
    if not game_path.is_file():
        diagnostics.append(
            Diagnostic(
                code="LLMSIM_FILE_MISSING",
                severity=DiagnosticSeverity.ERROR,
                path="game.yaml",
                message="必需文件 game.yaml 缺失",
            )
        )
    else:
        try:
            game_text = game_path.read_text(encoding="utf-8")
        except OSError:
            game_text = None
        game_raw, parse_diags = read_yaml_file(game_path, "game.yaml")
        diagnostics.extend(parse_diags)
        if game_raw is not None and game_text is not None:
            files["game.yaml"] = game_raw
            texts["game.yaml"] = game_text

    # —— 步 3：v1 形状拒绝（恰好 1 条，停止，D-P5-04）——
    if detect_v1_shape(game_raw):
        return ProjectLoadResult(
            root=str(root_path),
            raw=None,
            diagnostics=(
                *diagnostics,
                Diagnostic(
                    code="LLMSIM_PROJECT_FORMAT_V1",
                    severity=DiagnosticSeverity.ERROR,
                    path="game.yaml",
                    message="检出 v1 项目形状（顶层 world/player 且无 manifest），零 v1 兼容",
                    refs=("no manifest", "v1 top-level world/player"),
                ),
            ),
        )

    # —— 步 4：可选模板（模板序 + 每模板命中集 sorted；解析失败继续）——
    for pattern, _section, _kind in LAYOUT_OPTIONAL:
        for hit in sorted(root_path.glob(pattern)):
            rel = hit.relative_to(root_path).as_posix()
            try:
                original_text = hit.read_text(encoding="utf-8")
            except OSError:
                original_text = None
            value, file_diags = read_yaml_file(hit, rel)
            diagnostics.extend(file_diags)
            if value is not None and original_text is not None:
                files[rel] = value
                texts[rel] = original_text

    # —— 步 5：pyproject.toml / plugins/ 存在性（K8 扫描面数据源）——
    pyproject_path = root_path / "pyproject.toml"
    pyproject_present = pyproject_path.is_file()
    pyproject_text: str | None = None
    if pyproject_present:
        try:
            pyproject_text = pyproject_path.read_text(encoding="utf-8")
        except OSError:
            pyproject_text = None
    plugins_dir_present = (root_path / "plugins").is_dir()

    # —— 步 6：返回 ——
    return ProjectLoadResult(
        root=str(root_path),
        raw=RawProject(
            root=str(root_path),
            files=files,
            texts=texts,
            pyproject_present=pyproject_present,
            pyproject_text=pyproject_text,
            plugins_dir_present=plugins_dir_present,
        ),
        diagnostics=tuple(diagnostics),
    )


def read_yaml_file(path: Path, label: str) -> tuple[Any | None, tuple[Diagnostic, ...]]:
    """读 + 解析一个 YAML 文件（设计文档 §3.3 纯 helper，测试直用）。

    - ``open(encoding="utf-8")`` + ``yaml.safe_load``；
    - ``YAMLError`` / ``OSError`` → (None, [LLMSIM_YAML_PARSE path=label])；
    - 根非 dict → (None, [LLMSIM_YAML_PARSE path=label, refs=["root-not-dict"]])。

    永不 raise。
    """
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return None, (_parse_diagnostic(label, root_not_dict=False),)
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        return None, (_parse_diagnostic(label, root_not_dict=False),)
    if not isinstance(data, dict):
        return None, (_parse_diagnostic(label, root_not_dict=True),)
    return data, ()


def detect_v1_shape(raw_game_yaml: Any) -> bool:
    """v1 项目形状判据（D-P5-04，设计文档 §3.3 判据公式逐字）。

    ``isinstance(dict) ∧ "manifest" not in raw ∧ ("world" in raw or "player"
    in raw)``——v1 判据：顶层 world/player 且无 manifest（test_empty.yaml
    L1-12/89/135/147-151 形状）；v2 game.yaml 亦含顶层 player，判据差异点 =
    manifest 存在性。
    """
    return (
        isinstance(raw_game_yaml, dict)
        and "manifest" not in raw_game_yaml
        and ("world" in raw_game_yaml or "player" in raw_game_yaml)
    )
