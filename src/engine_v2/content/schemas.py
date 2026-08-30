"""engine_v2 content 层 P5 项目格式数据 schemas（P5-T02a / W1，设计文档 §3.1）。

依据 ``docs/v2/contracts/P5-project-format-module-plugin-dsl-design.md``（下称
"设计文档"，P5-DESIGN 冻结态）§3.1 字段级规格（25 导出）：

- **定位**：ProjectIR 十二类（Spec:460-474）+ 诊断 schema + ``RawProject`` 的
  **纯数据**定义。Pydantic v2，全部模型 ``frozen=True``（K2 / P5-INV-2：输入
  对象零原地变更）+ ``extra="forbid"``（D-P5-05 严格度基线：未知键 = error）；
- **零逻辑**（除 ``model_validator`` 形状校验）、零 I/O、零 core import
  （P5 自包含，D-P5-01）；import 面 = 仅 stdlib + pydantic（§3 导入纪律）；
- **错误族**：模型构造期形状违例 = pydantic ``ValidationError``（由
  ``project_ir.build_ir`` 捕获转 ``LLMSIM_SCHEMA``；本模块不直接产诊断，
  除 ``Diagnostic`` 自身 code 校验——该校验亦为构造期拒绝，非产诊断）；
- **ENGINE_VERSION**（``Final[str]``，值 ``"0.5.0"``）：模块级私有常量，不入
  ``__all__``（25 导出不含之）；单点权威——``module_graph`` 自本模块导入、
  ``plugins/registry.py`` 重导出，节点面 / manifest 面 / 插件面比较基准统一
  为同一常量（D-P5-08、ERR-P5-3 S-A）；
- **D-P5-15 确定性纪律**：零 ``asyncio``/``datetime``/``time``/``random``/
  网络族 import；数据形状 JSON-clean（K7 / P5-INV-7：字段类型集仅
  str/int/float/bool/Literal/str-Enum/tuple/list/dict/None）；
- **K8 / P5-INV-8**：``InferenceCapabilityProfile`` / ``PromptPolicy`` 字段
  封闭集不含任何部署 pinning 字段（断言 #19b 内省面）；K4 / P5-INV-4：
  ``PromptPolicy`` 无 authority/permission 类字段。

``__all__`` 25 名按设计文档 §8.2 导出台账逐名逐序。私有面（不入 ``__all__``）：
``ENGINE_VERSION`` 常量、``ComponentType`` 枚举、``ScenarioTime`` 模型。
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = [
    "DIAGNOSTIC_CODES",
    "RawProject",
    "ProjectManifest",
    "ProjectIR",
    "WorldSpec",
    "EnvironmentSpec",
    "LocationSpec",
    "ObjectSpec",
    "PositionSpec",
    "AttributeSpec",
    "PlayerSpec",
    "CharacterSpec",
    "ComponentSchema",
    "ComponentField",
    "ActionSpec",
    "RuleSpec",
    "AuthorityPolicy",
    "ModuleGraphNode",
    "GameplayModeSpec",
    "InferenceCapabilityProfile",
    "PromptPolicy",
    "PluginDescriptor",
    "ScenarioSpec",
    "Diagnostic",
    "DiagnosticSeverity",
]

#: 单点权威引擎版本常量（D-P5-08、ERR-P5-3 S-A）：值 ``"0.5.0"``；
#: ``module_graph`` 自本模块导入（不另定义、不入 ``__all__``），
#: ``plugins/registry.py`` 重导出（其 ``__all__`` 7 名不变）；节点面 /
#: manifest 面 / 插件面 ``engine_version`` 比较基准统一为同一常量。
ENGINE_VERSION: Final[str] = "0.5.0"

# —— 词法规则（设计文档 §3.1 字段表约束列，逐字；D-P5-06 版本文法族）——

#: 实体基础 id 词法：``project_id`` / ``LocationSpec.id`` / ``ObjectSpec.id`` /
#: ``player_id`` / ``CharacterSpec.id`` / ``RuleSpec.id`` / ``ScenarioSpec.id``
#: （设计文档「pattern 同上」族所指）。
_ID_PATTERN: Final[str] = r"^[a-z][a-z0-9_]{0,63}$"

#: 点分 id 词法：``ModuleGraphNode.id``（族.模块，Spec §40/§41 形态）/
#: ``ComponentSchema.id``（如 ``world.location``）。
_MODULE_ID_PATTERN: Final[str] = r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$"

#: 版本文法（D-P5-06）：点分数字串 1+ 分量；padding 比较
#: ``2 < 2.1 < 2.1.0``。
_VERSION_PATTERN: Final[str] = r"^\d+(\.\d+)*$"

#: ``ProjectManifest.engine_version`` 文法（D-P5-06 版本文法）：
#: ``""``（= 任意）| V | ``>=V``（V = 上述点分数字串）。
_ENGINE_VERSION_PATTERN: Final[str] = r"^(?:\d+(?:\.\d+)*|>=\d+(?:\.\d+)*)?$"


class _ContractModel(BaseModel):
    """P5 全部项目格式数据模型的基类（设计文档 §3.1 定位条款的内联）。

    - ``frozen=True``：字段不可再赋值（K2 / P5-INV-2 全部数据模型 frozen）；
    - ``extra="forbid"``：未知字段构造期拒绝（D-P5-05 严格度基线，未知键 =
      ``LLMSIM_UNKNOWN_KEY`` 错误族；5 个开放 dict 豁免见各模型注）；
    - JSON-clean（K7 / P5-INV-7）：字段类型集封闭于 JSON 原生类型。
    """

    model_config = ConfigDict(frozen=True, extra="forbid")


class DiagnosticSeverity(str, Enum):
    """诊断严重度词表（设计文档 §3.1：``ERROR="error"`` / ``WARNING="warning"``；
    str-Enum 保证 JSON/比较透明）。"""

    ERROR = "error"
    WARNING = "warning"


#: 诊断码 18 枚闭集（设计文档 §3.1 表，逐字；D-P5-12 machine-readable
#: 诊断闭集面，断言 #17 形状校验的消费方）。
DIAGNOSTIC_CODES: Final[frozenset[str]] = frozenset(
    {
        "LLMSIM_FILE_MISSING",
        "LLMSIM_YAML_PARSE",
        "LLMSIM_PROJECT_FORMAT_V1",
        "LLMSIM_SCHEMA",
        "LLMSIM_UNKNOWN_KEY",
        "LLMSIM_DUPLICATE_ID",
        "LLMSIM_UNRESOLVED_REF",
        "LLMSIM_MODULE_REQUIRES_MISSING",
        "LLMSIM_MODULE_VERSION",
        "LLMSIM_MODULE_CYCLE",
        "LLMSIM_MODULE_CONFLICT",
        "LLMSIM_AUTHORITY_CONFLICT",
        "LLMSIM_DEPLOYMENT_FIELD",
        "LLMSIM_DSL_PARSE",
        "LLMSIM_PLUGIN_ENTRY_INVALID",
        "LLMSIM_PLUGIN_NO_PYPROJECT",
        "LLMSIM_ENGINE_VERSION",
        "LLMSIM_PLUGIN_ENTRY_UNRESOLVED",
    }
)


class PositionSpec(_ContractModel):
    """三维坐标（设计文档 §3.1：``x: float``, ``y: float``, ``z: float = 0.0``）。"""

    x: float
    y: float
    z: float = 0.0


class EnvironmentSpec(_ContractModel):
    """环境描述（设计文档 §3.1：v1 形状对照 test_empty.yaml L4-7）。"""

    time_of_day: str = ""
    weather: str = ""
    temperature_c: float | None = None


class LocationSpec(_ContractModel):
    """位置池条目（设计文档 §3.1 字段表）。

    ``connections``：key = 方向名（``east`` 等，v1 test_empty.yaml L12-28
    形状），value = 目标 location id（check_references 面）。
    ``properties`` 为开放 dict（5 豁免处之一，D-P5-05）：JSON-clean 即可。
    """

    id: str = Field(pattern=_ID_PATTERN)
    name: str = Field(min_length=1)
    description: str = ""
    connections: dict[str, str] = {}
    ambient_light: str | None = None
    ambient_sound: str | None = None
    properties: dict[str, Any] = {}


class WorldSpec(_ContractModel):
    """world 节单值（设计文档 §3.1：至多 1 文件——0 文件 →
    ``ProjectIR.world = None`` 合法空（D-P5-05）；恰好 1 → 本模型（该文件
    顶层键必为 ``world``）；≥2 → 取 sorted 路径序首文件 + 每余文件一条
    ``LLMSIM_SCHEMA``，该处置属 ``build_ir`` 面，本模块只承载形状）。

    v1 ``world.objects`` 不属本模型（映射至 v2 顶层 ``items`` 分节，
    §3.1 依据行）；v1 项目顶层键 ``max_ticks`` / ``game_time`` /
    ``ticks_per_game_minute`` / ``narrative_style`` 属 ``ScenarioSpec``，
    不属本模型。
    """

    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    environment: EnvironmentSpec = Field(default_factory=EnvironmentSpec)
    locations: tuple[LocationSpec, ...] = ()


class ObjectSpec(_ContractModel):
    """物件事件对象（设计文档 §3.1：v1 state dict {closed, unlocked} 等 →
    v2 扁平化 str，形状简化披露）。

    ``properties`` 为开放 dict（5 豁免处之一，D-P5-05）。
    """

    id: str = Field(pattern=_ID_PATTERN)
    object_type: str = ""
    name: str
    description: str = ""
    position: PositionSpec | None = None
    state: str | None = None
    properties: dict[str, Any] = {}


class AttributeSpec(_ContractModel):
    """属性值 + 界（设计文档 §3.1：v1 attributes 形状对照 test_empty.yaml
    player.attributes）。

    构造期不变量：``min <= value <= max``（``model_validator``）。
    """

    name: str
    value: float
    min: float
    max: float
    natural_delta_per_minute: float = 0.0
    description: str = ""

    @model_validator(mode="after")
    def _check_value_within_bounds(self) -> "AttributeSpec":
        if not self.min <= self.value <= self.max:
            raise ValueError(
                f"AttributeSpec.value 必须在 [min, max] 内：value={self.value!r}, "
                f"min={self.min!r}, max={self.max!r}"
            )
        return self


class PlayerSpec(_ContractModel):
    """玩家（设计文档 §3.1 字段表；v1 形状对照 test_empty.yaml player 块）。

    ``capabilities`` / ``physical_profile`` 为开放 dict（5 豁免处之二，
    D-P5-05）：JSON-clean 即可；规范键为消费方约定（``skill_levels`` /
    ``blocked_common_actions`` / ``allowed_extraordinary_actions``；
    ``height_cm`` / ``weight_kg`` / ``body_width_cm`` / ``movement_mode`` /
    ``strength``）。
    """

    player_id: str = Field(pattern=_ID_PATTERN)
    name: str = Field(min_length=1)
    persona: str = ""
    position: PositionSpec | None = None
    capabilities: dict[str, Any] = {}
    physical_profile: dict[str, Any] = {}
    attributes: dict[str, AttributeSpec] = {}
    inventory: list[str] = []
    subconscious_rules: list[str] = []
    subconscious_memory: list[str] = []
    speech_examples: list[str] = []


class CharacterSpec(_ContractModel):
    """角色（设计文档 §3.1：``personality`` 开放 dict，5 豁免处之一，
    D-P5-05，规范键 ``traits``/``motivations``/``speech_style``/
    ``background``——v1 whisperheads.yaml 形状；``relationships`` key =
    character id 或 player_id，check_references 面）。"""

    id: str = Field(pattern=_ID_PATTERN)
    name: str
    personality: dict[str, Any] = {}
    position: PositionSpec | None = None
    starting_inventory: list[str] = []
    relationships: dict[str, float] = {}
    speech_examples: list[str] = []
    attributes: dict[str, AttributeSpec] = {}


class ComponentType(str, Enum):
    """组件字段类型词表（设计文档 §3.1 ``ComponentField.type``，私有枚举，
    不进 ``__all__``；str-Enum 保证 JSON/比较透明）。"""

    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    LIST = "list"
    MAP = "map"
    OBJECT = "object"


class ComponentField(_ContractModel):
    """组件 schema 字段（设计文档 §3.1：``type`` = 私有 :class:`ComponentType`）。"""

    name: str
    type: ComponentType
    required: bool = False
    default: Any | None = None
    description: str = ""


class ComponentSchema(_ContractModel):
    """组件 schema（设计文档 §3.1：id 点分词法，如 ``world.location``）。

    构造期不变量：``fields`` 非空且 ``name`` 唯一（``model_validator``）。
    """

    id: str = Field(pattern=_MODULE_ID_PATTERN)
    fields: tuple[ComponentField, ...]
    description: str = ""

    @model_validator(mode="after")
    def _check_fields_nonempty_unique(self) -> "ComponentSchema":
        names = [field.name for field in self.fields]
        if not names:
            raise ValueError("ComponentSchema.fields 必须非空")
        if len(names) != len(set(names)):
            raise ValueError(f"ComponentSchema.fields name 必须唯一：{names!r}")
        return self


class ActionSpec(_ContractModel):
    """动作注册表条目（设计文档 §3.1：P5 结构，运行时 P6；``condition`` =
    DSL 字符串（D-P5-09），validate 期 parse_dsl 校验；
    ``success_probability`` 约束 0 < p < 1）。"""

    id: str
    name: str
    verb: str = "interact"
    requires_components: tuple[str, ...] = ()
    condition: str | None = None
    success_probability: float | None = Field(default=None, gt=0, lt=1)
    description: str = ""


class RuleSpec(_ContractModel):
    """规则注册表条目（设计文档 §3.1 字段表，v1 DeterministicRule 对照；
    同 priority 按 id.casefold 序——casefold 平手约定与 D-P5-06 同族，
    字段表行公式为准）。

    构造期不变量：``probability`` 非 None 时必须 0 < p < 1；
    ``feasibility == "uncertain"`` 时 ``probability`` 必需
    （v1 deterministic_rules.py:152-154 必需逻辑 + :160-162 范围检查）。
    """

    id: str = Field(pattern=_ID_PATTERN)
    description: str = ""
    match: str | None = None
    condition: str | None = None
    feasibility: Literal["allowed", "blocked", "uncertain"] | None = None
    probability: float | None = None
    priority: int = 100
    disabled: bool = False

    @model_validator(mode="after")
    def _check_probability(self) -> "RuleSpec":
        if self.probability is not None and not 0.0 < self.probability < 1.0:
            raise ValueError(
                f"RuleSpec.probability 必须满足 0 < p < 1：{self.probability!r}"
            )
        if self.feasibility == "uncertain" and self.probability is None:
            raise ValueError(
                "RuleSpec.feasibility='uncertain' 时 probability 必需（0 < p < 1）"
            )
        return self


class AuthorityPolicy(_ContractModel):
    """权威声明（设计文档 §3.1：P5 = 结构 + 声明域重叠静态检查（D-P5-03），
    运行时语义 P6；无 mutation API 面，K3 / P5-INV-3）。"""

    id: str
    domain: str = Field(min_length=1)
    owner: str
    exclusive: bool = True
    description: str = ""


class ModuleGraphNode(_ContractModel):
    """模块图节点（设计文档 §3.1：§28.3 四字段齐；id 点分词法（族.模块，
    Spec §40/§41 形态）；``version`` = D-P5-06 版本文法）。

    ``requires``/``optional``/``conflicts`` 元素形 = ``"id"`` 或
    ``"id >= X.Y"``（目标 id 同点分词法，Spec §41:1974-1982 形状）——
    需求串解析面属 ``module_graph.parse_requirement``（W3），本模块不校验
    需求串文法。``engine_version`` 由 ``check_module_versions`` 节点面与
    ``validate_project`` manifest 面消费（非死字段）。
    """

    id: str = Field(pattern=_MODULE_ID_PATTERN)
    version: str = Field(pattern=_VERSION_PATTERN)
    entrypoint: str | None = None
    requires: tuple[str, ...] = ()
    optional: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    engine_version: str = ""
    description: str = ""


class GameplayModeSpec(_ContractModel):
    """玩法模式定义（设计文档 §3.1：P5 结构面）。"""

    id: str
    mode_type: str
    params: dict[str, Any] = {}
    description: str = ""


class InferenceCapabilityProfile(_ContractModel):
    """推理能力需求画像（设计文档 §3.1：**字段封闭**——不得出现任何部署
    pinning 字段（K8 / P5-INV-8，断言 #19b 内省面））。

    构造期不变量：``ideal_tier >= min_tier``（``model_validator``）。
    """

    id: str
    capability: str = Field(min_length=1)
    min_tier: int = Field(default=0, ge=0)
    ideal_tier: int = Field(default=0, ge=0)
    notes: str = ""

    @model_validator(mode="after")
    def _check_tiers(self) -> "InferenceCapabilityProfile":
        if self.ideal_tier < self.min_tier:
            raise ValueError(
                "InferenceCapabilityProfile.ideal_tier 必须 >= min_tier："
                f"ideal_tier={self.ideal_tier!r} < min_tier={self.min_tier!r}"
            )
        return self


class PromptPolicy(_ContractModel):
    """提示策略（设计文档 §3.1：**字段封闭**——无 authority/permission 类
    字段（K4 / P5-INV-4，断言 #19b）；字段集 = {id, scope, template_ref,
    variables}）。"""

    id: str
    scope: str
    template_ref: str
    variables: tuple[str, ...] = ()


class PluginDescriptor(_ContractModel):
    """插件描述符（设计文档 §3.1：``entrypoint`` = ``module:Attribute``
    形式，Spec §28.1:1525 形状；文法校验属 ``plugins/registry.py`` 面，
    非法 → ``LLMSIM_PLUGIN_ENTRY_INVALID``）。"""

    id: str
    source: Literal["local", "entrypoint"] = "local"
    entrypoint: str | None = None
    description: str = ""


class ScenarioTime(_ContractModel):
    """场景起始时刻（设计文档 §3.1，**私有**模型，不进 ``__all__``；
    v1 对照 test_empty.yaml :148-150 ``{hour, minute}``）。"""

    hour: int = Field(ge=0, le=23)
    minute: int = Field(ge=0, le=59)


class ScenarioSpec(_ContractModel):
    """场景定义（设计文档 §3.1 字段表：默认场景来自 game.yaml 顶层，追加
    场景 = scenarios/*.yaml；v1 顶层标量 max_ticks / game_time /
    ticks_per_game_minute / narrative_style 归属本类，不属 WorldSpec）。"""

    id: str = Field(pattern=_ID_PATTERN)
    max_ticks: int = Field(ge=1)
    ticks_per_game_minute: float = Field(gt=0)
    game_time: ScenarioTime
    starting_scene_description: str = ""
    narrative_style: str = ""


class RawProject(_ContractModel):
    """项目原始读取面（设计文档 §3.1：loader 产出，本模块只承载形状）。

    - ``files``：key = 相对 posix 路径（如 ``game.yaml``、
      ``world/main_world.yaml``），value = YAML 解析结果（JSON-clean
      可断言）；
    - ``texts``：同 key 集的**原始文本**（K8 扫描面，D-P5-11；loader 保留
      原文，不丢信息）；
    - ``pyproject_text``：项目根 ``pyproject.toml`` 原文（K8 扫描面，
      D-P5-11；loader 读原文，不做 TOML 解析；默认 None）。
    """

    root: str
    files: dict[str, Any]
    texts: dict[str, str]
    pyproject_present: bool
    pyproject_text: str | None = None
    plugins_dir_present: bool


class ProjectManifest(_ContractModel):
    """项目 manifest（设计文档 §3.1 字段表）。

    - ``schema_version`` 必为 ``"2"``（v1 拒绝的机械判据之一，D-P5-04）；
    - ``engine_version`` 文法（D-P5-06 版本文法）：``""``（= 任意）| V |
      ``>=V``（V = 点分数字串 1+ 分量）。
    """

    schema_version: Literal["2"]
    project_id: str = Field(pattern=_ID_PATTERN)
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    engine_version: str = Field(default="", pattern=_ENGINE_VERSION_PATTERN)


class ProjectIR(_ContractModel):
    """ProjectIR 根聚合（设计文档 §3.1：**16 字段** ↔ Spec 十二类映射，
    Spec:460-474；K1 / P5-INV-1：项目源在 validate 期的唯一结构化投影）。

    ``world`` 单值语义（ERR-P5-7 H-1 / D-P5-05）：world 节文件缺失 = 合法
    空 → ``None``；恰好 1 → ``WorldSpec``；≥2 → 取 sorted 路径序首文件 +
    每余文件一条 ``LLMSIM_SCHEMA``（``build_ir`` 步 3 面，构造期不 raise）。
    """

    manifest: ProjectManifest
    scenario: ScenarioSpec
    world: WorldSpec | None = None
    player: PlayerSpec
    items: tuple[ObjectSpec, ...] = ()
    characters: tuple[CharacterSpec, ...] = ()
    component_schemas: tuple[ComponentSchema, ...] = ()
    actions: tuple[ActionSpec, ...] = ()
    rules: tuple[RuleSpec, ...] = ()
    authority: tuple[AuthorityPolicy, ...] = ()
    modules: tuple[ModuleGraphNode, ...] = ()
    gameplay_modes: tuple[GameplayModeSpec, ...] = ()
    capabilities: tuple[InferenceCapabilityProfile, ...] = ()
    prompts: tuple[PromptPolicy, ...] = ()
    plugin_descriptors: tuple[PluginDescriptor, ...] = ()
    scenarios: tuple[ScenarioSpec, ...] = ()


class Diagnostic(_ContractModel):
    """诊断（设计文档 §3.1 + D-P5-12：machine-readable 诊断）。

    - ``code`` ∈ ``DIAGNOSTIC_CODES``（18 枚闭集，构造期 ``model_validator``
      ——错误族「本模块不直接产诊断」的唯一例外面，违例 = 构造期
      ``ValidationError``）；
    - ``severity`` ∈ {error, warning}；
    - ``path`` 非空（文件相对路径 posix 或实体/规则 ID，K6 / P5-INV-6）；
    - ``message`` 非空且为**确定性文本**（无时间戳/无指针/无随机，
      D-P5-15）；
    - ``refs`` 证据引用（环节点序、重复 ID 对等），构造时定序。
    """

    code: str
    severity: DiagnosticSeverity
    path: str = Field(min_length=1)
    message: str = Field(min_length=1)
    refs: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _check_code_in_closed_set(self) -> "Diagnostic":
        if self.code not in DIAGNOSTIC_CODES:
            raise ValueError(
                f"Diagnostic.code 必须属于 18 码闭集 DIAGNOSTIC_CODES：{self.code!r}"
            )
        return self
