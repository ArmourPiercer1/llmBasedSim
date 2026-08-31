"""P6-W4 T05 前半（SOT §3.9）：game PromptPolicy → 模板文档加载 + 路径纪律。

模板 = ``.md`` 文本文件（P5 PromptPolicy 只读消费面，schemas.py:418-426；
scope 词表闭集 = ``game_policy`` / ``character_scene`` 2 值——P5 侧 scope 为
str 无 enum，闭集校验归 P6 运行时，SOT §3.9 步 1.5 / D-P6-18）。加载即校验
（SOT §3.9 L437-444，五步次序钉死）：

1. id 重复（casefold 比较，与已入 ``by_id`` 者比）→ DUPLICATE_POLICY
   （error，path=首个占位 id，refs=本条 id），该条跳过（first-wins）；
2. scope ∉ 闭集（casefold 比较）→ SCOPE_UNKNOWN（warning，refs=(scope,)），
   该条不进入 ``by_id``，后续步骤跳过（F-03 / D-P6-18 触发面）；
3. 路径逃逸（绝对 / ``..`` / realpath 前缀出界，symlink 天然拦截）→
   PATH_ESCAPE（error，path=template_ref）；
4. 文件缺失 / 目录 → TEMPLATE_MISSING（error，path=template_ref）；
5. strip 后为空 → TEMPLATE_EMPTY（warning，path=template_ref），跳过；
6. 成功 → TemplateDocument 入 ``by_id``（键 = policy.id 原大小写，policy 序）。

诊断序 = 按 (code, path, refs) 元组序排序（确定性，P5 D-P5-12 口径移植）。
scope 分派面不存在于本模块（归 assembler，SOT §3.9 L445 单一职责）。

模块纪律（SOT §3.9 L447）：读面 = pathlib + content.schemas（PromptPolicy）
+ prompts.diagnostic（RuntimeDiagnostic；severity 复用 P5 DiagnosticSeverity）；
零网络、零非确定根源、同步面。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict

from src.engine_v2.content.schemas import DiagnosticSeverity, PromptPolicy
from src.engine_v2.prompts.diagnostic import RuntimeDiagnostic

__all__ = [
    "TemplateDocument",
    "TemplateStore",
    "RenderResult",
    "render_template",
    "validate_template_ref",
]

#: ``{{token}}`` 模板 token 正则：token = 非空、非空白、不含花括号的串
#: （SOT §3.9 L431-435，单次线性扫描面）。
_TOKEN_RE: Final = re.compile(r"\{\{([^\s{}]+)\}\}")

#: scope 词表闭集（P5 PromptPolicy.scope 为 str 无 enum，schemas.py:418-426
#: 冻结面；闭集校验归 P6 运行时，SOT §3.9 步 1.5）。
_SCOPE_CLOSED_SET: Final[frozenset[str]] = frozenset({"game_policy", "character_scene"})

#: 诊断码常量（P6 21 码闭集之 PROMPT 族本模块发射面，SOT §8.1）。
_DUPLICATE_POLICY = "LLMSIM_PROMPT_DUPLICATE_POLICY"
_SCOPE_UNKNOWN = "LLMSIM_PROMPT_SCOPE_UNKNOWN"
_PATH_ESCAPE = "LLMSIM_PROMPT_PATH_ESCAPE"
_TEMPLATE_MISSING = "LLMSIM_PROMPT_TEMPLATE_MISSING"
_TEMPLATE_EMPTY = "LLMSIM_PROMPT_TEMPLATE_EMPTY"
_UNDECLARED_VARIABLE = "LLMSIM_PROMPT_UNDECLARED_VARIABLE"
_VARIABLE_MISSING = "LLMSIM_PROMPT_VARIABLE_MISSING"


class TemplateDocument(BaseModel):
    """模板文档（SOT §3.9 L426）。

    - ``policy_id`` / ``scope``：P5 PromptPolicy 原值；
    - ``template_ref``：原样相对路径（逃逸/缺失/空诊断的 path 归因对象 =
      此原值，K6 可追踪面）；
    - ``variables``：P5 声明序（渲染供给面）；
    - ``text``：文件内容本体（加载期空文件诊断触发时该条不入 ``by_id``）；
    - ``path``：解析后绝对路径（字符串类型，诊断面，SOT §3.9 逐字）。
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    policy_id: str
    scope: str
    template_ref: str
    variables: tuple[str, ...]
    text: str
    path: str


class RenderResult(BaseModel):
    """渲染结果（SOT §3.9 L436）：替换文本 + 诊断序列（按文中出现序，
    确定性）。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str
    diagnostics: tuple[RuntimeDiagnostic, ...] = ()


def validate_template_ref(template_ref: str, project_root: Path) -> tuple[Path, str | None]:
    """模板引用路径纪律（SOT §3.9 L427-430，Leader-A12：越界读 = 拒绝，
    不静默）。

    返回 ``(path, error)``：

    - 绝对路径 / 含 ``..`` 部件 → ``(原 Path, "path-escape")``；
    - realpath 解析后前缀 ∉ ``project_root/prompts/``（``.resolve()`` 走
      realpath，天然拦截 symlink 逃逸——AD-5 探针对）→
      ``(原 Path, "path-escape")``；
    - 合法 → ``(realpath, None)``。
    """
    p = Path(template_ref)
    if p.is_absolute() or ".." in p.parts:
        return p, "path-escape"
    resolved = (project_root / p).resolve()
    prompts_root = (project_root / "prompts").resolve()
    if resolved != prompts_root and not resolved.is_relative_to(prompts_root):
        return p, "path-escape"
    return resolved, None


def render_template(document: TemplateDocument, values: dict[str, str]) -> RenderResult:
    """``{{token}}`` 替换（**无 jinja2**——venv 白外面，Leader-A12 / D-P6-11）。

    单次线性扫描文中全部 ``{{token}}``（同 token 多次出现全部处理，替换
    文本不重扫，无嵌套求值，SOT §3.9 L431-435）：

    - token ∉ ``document.variables`` → UNDECLARED_VARIABLE（error，
      path=template_ref，refs=(token,)），**替换为原文 ``{{token}}``
      保留**——诊断不中断渲染；
    - token ∈ variables 但 ``values`` 缺 → VARIABLE_MISSING（error，
      path=template_ref，refs=(token,)），替换为 ``""``；
    - 其余 → 替换为 ``values[token]``。
    """
    diagnostics: list[RuntimeDiagnostic] = []

    def _sub(match: re.Match[str]) -> str:
        token = match.group(1)
        if token not in document.variables:
            diagnostics.append(
                RuntimeDiagnostic(
                    code=_UNDECLARED_VARIABLE,
                    severity=DiagnosticSeverity.ERROR,
                    path=document.template_ref,
                    message=f"模板变量未声明: {token}",
                    refs=(token,),
                )
            )
            return match.group(0)
        if token not in values:
            diagnostics.append(
                RuntimeDiagnostic(
                    code=_VARIABLE_MISSING,
                    severity=DiagnosticSeverity.ERROR,
                    path=document.template_ref,
                    message=f"声明变量缺值: {token}",
                    refs=(token,),
                )
            )
            return ""
        return values[token]

    text = _TOKEN_RE.sub(_sub, document.text)
    return RenderResult(text=text, diagnostics=tuple(diagnostics))


class TemplateStore:
    """模板存储（SOT §3.9 L437-445）：加载即校验，五步次序（见模块
    docstring）。

    实例属性：

    - ``by_id``：键 = policy.id 原大小写，按 policy 序入位（first-wins）；
    - ``diagnostics``：按 (code, path, refs) 元组序排序（确定性）。

    本模块无 ``for_scope``（scope 分派归 assembler，单一职责，
    SOT §3.9 L445）。
    """

    def __init__(self, *, project_root: Path, policies: tuple[PromptPolicy, ...]) -> None:
        self.by_id: dict[str, TemplateDocument] = {}
        self.diagnostics: tuple[RuntimeDiagnostic, ...] = ()
        collected: list[RuntimeDiagnostic] = []
        seen: dict[str, str] = {}  # casefold id → by_id 占位者原 id
        for policy in policies:
            key = policy.id.casefold()
            if key in seen:
                collected.append(
                    RuntimeDiagnostic(
                        code=_DUPLICATE_POLICY,
                        severity=DiagnosticSeverity.ERROR,
                        path=seen[key],
                        message=f"policy id 重复: {policy.id}",
                        refs=(policy.id,),
                    )
                )
                continue
            if policy.scope.casefold() not in _SCOPE_CLOSED_SET:
                collected.append(
                    RuntimeDiagnostic(
                        code=_SCOPE_UNKNOWN,
                        severity=DiagnosticSeverity.WARNING,
                        path=policy.id,
                        message=f"scope 不在闭集内: {policy.scope}",
                        refs=(policy.scope,),
                    )
                )
                continue
            resolved, error = validate_template_ref(policy.template_ref, project_root)
            if error is not None:
                collected.append(
                    RuntimeDiagnostic(
                        code=_PATH_ESCAPE,
                        severity=DiagnosticSeverity.ERROR,
                        path=policy.template_ref,
                        message=f"模板引用越界: {policy.template_ref}",
                        refs=(),
                    )
                )
                continue
            if not resolved.is_file():
                collected.append(
                    RuntimeDiagnostic(
                        code=_TEMPLATE_MISSING,
                        severity=DiagnosticSeverity.ERROR,
                        path=policy.template_ref,
                        message=f"模板文件缺失: {policy.template_ref}",
                        refs=(),
                    )
                )
                continue
            text = resolved.read_text(encoding="utf-8")
            if text.strip() == "":
                collected.append(
                    RuntimeDiagnostic(
                        code=_TEMPLATE_EMPTY,
                        severity=DiagnosticSeverity.WARNING,
                        path=policy.template_ref,
                        message=f"模板文件为空: {policy.template_ref}",
                        refs=(),
                    )
                )
                continue
            self.by_id[policy.id] = TemplateDocument(
                policy_id=policy.id,
                scope=policy.scope,
                template_ref=policy.template_ref,
                variables=policy.variables,
                text=text,
                path=str(resolved),
            )
            seen[key] = policy.id
        self.diagnostics = tuple(sorted(collected, key=lambda d: (d.code, d.path, d.refs)))
