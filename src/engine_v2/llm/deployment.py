"""P6-W1 T03 前半（SOT §3.2）：用户侧部署配置加载 + credential env 名化。

部署文件 = 用户文件（不属于 Game Project，K8 项目扫描面之外，Spec:405）；
本模块是 P6 唯一读用户文件的位置。读面仅 os(env) + pathlib + yaml，零网络，
同步面。确定性：同输入同诊断集，诊断序 = 按 (code, path, refs) 排序（P5
D-P5-12 口径移植，SOT §3.2 L211）。诊断不中断原则全程有效：语义错（
MODEL_UNDECLARED）不置 profile=None，形状错才置 None（SOT §3.2 L207，resolve 期
二次拦截）。
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path
from typing import Annotated, Final

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    model_validator,
)

from src.engine_v2.content.schemas import DiagnosticSeverity
from src.engine_v2.llm.profiles import CAPABILITY_RE, ModelCapabilityProfile
from src.engine_v2.prompts.diagnostic import RuntimeDiagnostic

__all__ = [
    "DeploymentEntry",
    "DeploymentProfile",
    "DeploymentLoadResult",
    "DEPLOYMENT_ENV_POINTER",
    "resolve_deployment_path",
    "load_deployment",
    "load_deployment_auto",
    "resolve_api_key",
]

#: env 指针名（12 名扫描负例自检：casefold 后词边界探针不命中
#: llmsim_deployment——下划线/后随词字符口径，validator.py:324-327 同构）。
DEPLOYMENT_ENV_POINTER: Final[str] = "LLMSIM_DEPLOYMENT"

_DEPLOYMENT_MISSING = "LLMSIM_RESOLVER_DEPLOYMENT_MISSING"
_DEPLOYMENT_PARSE = "LLMSIM_RESOLVER_DEPLOYMENT_PARSE"
_MODEL_UNDECLARED = "LLMSIM_RESOLVER_MODEL_UNDECLARED"

#: pydantic 模型级 validator 违例的 loc 为空元组，refs 点分串以本哨兵记录。
_EMPTY_LOC_SENTINEL = "<root>"


class DeploymentEntry(BaseModel):
    """用户侧单能力位配置（Spec §5.4 形状扩展，DEV-5）。

    credential 字段仅持 env 变量**名**、永不持值（Leader-A5，None = 无需
    认证）；端点字段默认空串，调用期空 = 显式失败（§3.4），无静默默认端点；
    fallbacks 序 = 降级序（§3.3，ADR-004 L41 同能力池）。
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    base_url: str = ""
    api_key_env: str | None = Field(default=None, pattern="^[A-Z][A-Z0-9_]{0,127}$")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    timeout_seconds: float = Field(default=30.0, ge=0.1)
    fallbacks: tuple[Annotated[str, StringConstraints(min_length=1)], ...] = ()


class DeploymentProfile(BaseModel):
    """部署画像：两节（models + inference_profiles，Spec §5.4）。

    - ``models`` 键必须 == 对应内层 ``model_id``（不一致 → ValidationError）；
    - ``inference_profiles`` 键须匹配 capability 字符串约定（CAPABILITY_RE）。
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    models: dict[str, ModelCapabilityProfile] = {}
    inference_profiles: dict[str, DeploymentEntry] = {}

    @model_validator(mode="after")
    def _check_section_keys(self) -> "DeploymentProfile":
        for key, profile in self.models.items():
            if key != profile.model_id:
                raise ValueError(
                    f"models 键 {key!r} 必须等于内层 model_id {profile.model_id!r}"
                )
        for key in self.inference_profiles:
            if CAPABILITY_RE.fullmatch(key) is None:
                raise ValueError(f"inference_profiles 键 {key!r} 不匹配 capability 约定")
        return self


class DeploymentLoadResult(BaseModel):
    """加载结果：path + profile（文件缺失/解析失败/形状错 = None）+
    diagnostics（按 (code, path, refs) 排序的元组，SOT §3.2 L211）。"""

    model_config = ConfigDict(frozen=True)

    path: str
    profile: DeploymentProfile | None
    diagnostics: tuple[RuntimeDiagnostic, ...]


def _sorted_diagnostics(diagnostics: Iterable[RuntimeDiagnostic]) -> tuple[RuntimeDiagnostic, ...]:
    """诊断集按 (code, path, refs) 排序（P5 D-P5-12 口径移植，SOT §3.2 L211）。"""
    return tuple(sorted(diagnostics, key=lambda d: (d.code, d.path, d.refs)))


def resolve_deployment_path(explicit: str | Path | None = None) -> str | None:
    """指针解析（优先级钉死）：显式参数 > env 指针 > None。纯读 env，零 I/O。"""
    if explicit is not None:
        return str(explicit)
    return os.environ.get(DEPLOYMENT_ENV_POINTER)


def load_deployment(path: str | Path) -> DeploymentLoadResult:
    """加载部署文件（诊断不中断原则全程有效，SOT §3.2）。

    - 文件缺失 → ``LLMSIM_RESOLVER_DEPLOYMENT_MISSING``（error，profile=None）；
    - YAML 解析失败 / 根非 dict / pydantic 构造违例 →
      ``LLMSIM_RESOLVER_DEPLOYMENT_PARSE``（error，profile=None；pydantic 违例
      refs=[loc 点分串，空 loc 记 ``<root>``）；
    - 语义引用检查：entry.model 与 fallbacks 各项 ∈ models 键，违例每项一条
      ``LLMSIM_RESOLVER_MODEL_UNDECLARED``（error，path=capability 键，
      refs=[缺失 model 名]）；语义错不中断 → profile 仍非 None（SOT §3.2 L207）。
    """
    path_str = str(path)
    file = Path(path_str)
    if not file.is_file():
        return DeploymentLoadResult(
            path=path_str,
            profile=None,
            diagnostics=_sorted_diagnostics(
                (
                    RuntimeDiagnostic(
                        code=_DEPLOYMENT_MISSING,
                        severity=DiagnosticSeverity.ERROR,
                        path=path_str,
                        message="部署文件缺失",
                    ),
                )
            ),
        )
    try:
        raw = yaml.safe_load(file.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return DeploymentLoadResult(
            path=path_str,
            profile=None,
            diagnostics=_sorted_diagnostics(
                (
                    RuntimeDiagnostic(
                        code=_DEPLOYMENT_PARSE,
                        severity=DiagnosticSeverity.ERROR,
                        path=path_str,
                        message="YAML 解析失败",
                    ),
                )
            ),
        )
    if not isinstance(raw, dict):
        return DeploymentLoadResult(
            path=path_str,
            profile=None,
            diagnostics=_sorted_diagnostics(
                (
                    RuntimeDiagnostic(
                        code=_DEPLOYMENT_PARSE,
                        severity=DiagnosticSeverity.ERROR,
                        path=path_str,
                        message="YAML 根非 mapping（dict）",
                    ),
                )
            ),
        )
    try:
        profile = DeploymentProfile.model_validate(raw)
    except ValidationError as exc:
        diagnostics = [
            RuntimeDiagnostic(
                code=_DEPLOYMENT_PARSE,
                severity=DiagnosticSeverity.ERROR,
                path=path_str,
                message="部署配置形状违例（pydantic）",
                refs=(".".join(str(part) for part in err["loc"]) or _EMPTY_LOC_SENTINEL,),
            )
            for err in exc.errors()
        ]
        return DeploymentLoadResult(path=path_str, profile=None, diagnostics=_sorted_diagnostics(diagnostics))
    diagnostics = [
        RuntimeDiagnostic(
            code=_MODEL_UNDECLARED,
            severity=DiagnosticSeverity.ERROR,
            path=capability,
            message=f"capability {capability!r} 引用未声明 model {name!r}",
            refs=(name,),
        )
        for capability, entry in profile.inference_profiles.items()
        for name in (entry.model, *entry.fallbacks)
        if name not in profile.models
    ]
    return DeploymentLoadResult(
        path=path_str, profile=profile, diagnostics=_sorted_diagnostics(diagnostics)
    )


def load_deployment_auto(explicit: str | Path | None = None) -> DeploymentLoadResult:
    """自动解析加载：指针解析 = None → 单条
    ``LLMSIM_RESOLVER_DEPLOYMENT_MISSING``（path="``<none>``"，refs=[指针名]）；
    否则委托 :func:`load_deployment`。"""
    resolved = resolve_deployment_path(explicit)
    if resolved is None:
        return DeploymentLoadResult(
            path="<none>",
            profile=None,
            diagnostics=_sorted_diagnostics(
                (
                    RuntimeDiagnostic(
                        code=_DEPLOYMENT_MISSING,
                        severity=DiagnosticSeverity.ERROR,
                        path="<none>",
                        message="部署指针未设置（显式参数与 env 指针皆空）",
                        refs=(DEPLOYMENT_ENV_POINTER,),
                    ),
                )
            ),
        )
    return load_deployment(resolved)


def resolve_api_key(api_key_env: str | None) -> str | None:
    """credential env 值读取：None → None；env 缺失 → None（调用期转
    ``LLMSIM_INFERENCE_CREDENTIAL_MISSING``，§3.4）。

    返回值 = 值本身，仅存于调用方内存；本模块无任何把值写进数据结构/诊断/
    payload 的路径（Leader-A5 机械面）。
    """
    if api_key_env is None:
        return None
    return os.environ.get(api_key_env)
