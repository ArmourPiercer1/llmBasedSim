# P1 Core Data Contracts — Phase 1 数据契约字段级设计规范（Spec A）

- **任务**: P1-DESIGN（Phase 1 Contract Owner 交付，计划 §36：QMax 任 P1 Contract owner）
- **文档地位**: 等价于 Spec §50「Spec A — Core Data Contracts」的字段级实现规范。Q27 按本文档可"纯执行"实现 P1-T01/T03/T05/T06；QMax 实现 P1-T02/T04 时无需再做架构判断。
- **分支**: `architecture-v2`
- **权威输入**:
  - `docs/plans/llmBasedSim_Engine_Architecture_v2_Spec.md`（下称 **Spec**）§4、§7、§8、§9、§10、§11、§16、§17、§18、§19、§20、§21、§22、§23、§25、§30、§31.3、§43、§44、§46、§47、§50
  - `docs/plans/llmBasedSim_Architecture_v2_Refactor_Development_Plan.md`（下称 **Plan**）§8、§10、§22.2、§22.3、§24、§36
  - `docs/architecture/adr/ADR-001-authority-mediated-commit-pipeline.md`、`docs/architecture/adr/ADR-003-separate-state-models-deprecate-monolithic-gamestate.md`
  - `docs/v2/reports/P0-T01-repo-inventory.md`、`docs/v2/reports/P0-T03-characterization-report.md`
  - `src/engine_v2/README.md`（骨架布局与冻结规则）
- **本任务边界**: 只定义**数据契约**（schema、类型、序列化规则、模块布局）。不实现 authority/validation/conflict/reducer/scheduler 行为逻辑（Plan P2/P3 职责），但契约必须为其预留（见 §11）。

> **Phase 编号口径说明**：Plan 的 Phase 编号与 Spec §47 不完全一致——Plan 将 Spec §47 的
> "Phase 1 — Core State / Effect Kernel" 细化为 **Plan P1（数据契约）+ Plan P2（Effect/Authority/Transaction Kernel）**，
> 其后整体顺移（Spec §47 "Phase 2 — Scheduler / Action" = **Plan P3**，"Phase 3 — Actor / Context" = Plan P4，
> Persistence/Replay = Plan P8，Presentation = Plan P10）。本文档一律使用 **Plan 编号**（P1–P11）。

---

## 0. 全局设计约定（适用于全部契约文件）

### 0.1 Schema 技术选型：Pydantic v2（决策 D-0）

**决策**：所有持久化契约类型使用 Pydantic v2 `BaseModel`；纯运行时辅助结构（registry、read view）可用
`@dataclass(frozen=True)`。

**理由**：
1. Spec §50 明确 Spec A "包括 Pydantic/dataclass schema"；pydantic `>=2.0` 已是项目既有依赖（v1 全部数据模型即 Pydantic，见 P0-T01 §7），不引入新依赖（不触发 Plan S4）；
2. G1 要求"所有 schema 可 round-trip"且 T06 要测"非法引用/非法字段拒绝"——Pydantic 的 `model_dump(mode="json")` / `model_validate` 与 `extra="forbid"` 直接满足；
3. migration-constraints §4.1「强烈保留的思想」第一条即 "Pydantic boundary validation"。

**统一模型基类约定**：

```python
class ContractModel(BaseModel):
    """P1 全部数据契约模型的基类（core/_base.py 或各文件内联）。"""
    model_config = ConfigDict(
        frozen=True,        # 字段不可再赋值（浅冻结；深层不变量见 §7.2）
        extra="forbid",     # 未知字段立即报错——G1「Contract 冻结」的数据表达
        validate_assignment=True,
    )
```

- `extra="forbid"` 的取舍：对**存档的前向兼容**（P8 加载旧/新存档）由迁移层（Spec §44 `content/migrations.py`，Plan P8）负责版本转换，契约模型本身**不**静默吞掉未知字段——否则违背 Plan S3（不得 silently drop 字段）精神。
- 枚举一律 `class Xxx(str, Enum)`，JSON 值为字符串字面量。
- `payload` / `arguments` / `metadata` 等开放字段一律标注 `dict[str, JsonValue]`（`pydantic.JsonValue`），保证 JSON 原生。

### 0.2 JSON-friendly 铁律

1. 序列化输出只允许 `str | int | float | bool | None | list | dict`（dict 键必须为 str）；
2. typed ID 序列化为**纯字符串**（带前缀，见 §3），不产生对象包装；`Revision` 序列化为纯整数；
3. 时间戳：权威序用整型（`logical_tick` / `world_revision`），墙钟时间仅诊断用、ISO-8601（Pydantic `datetime` 字段 `mode="json"` 自动转 ISO 字符串）；
4. 任何契约不得依赖 Python 对象内存地址（Spec §10.1 对 EntityId 的要求推广到全部 ID；对应 Plan §10 强制约束"不允许让 Entity ID 依赖 Python object"）；
5. round-trip 判据：`Cls.model_validate(obj.model_dump(mode="json")) == obj`（值相等；T06 同时断言 ID 字段的类型保持，见 §8.1）。

### 0.3 Import 边界声明（G1 门禁的数据层表达）

`src/engine_v2/core/` 的**允许 import 清单（白名单）**：

| 允许 | 说明 |
|---|---|
| Python 标准库 | `typing`、`enum`、`uuid`、`dataclasses`、`datetime`、`re`、`collections.abc` 等 |
| `pydantic`（>=2.0） | 唯一允许的第三方依赖；仅用其 schema/校验能力 |

**禁止 import（黑名单，与 `tests/test_engine_v2_skeleton.py` 的静态扫描口径一致并加严）**：

- `langgraph`、`langchain`、`langchain_core`、`langchain_openai`、`openai` 及任何 provider SDK（Spec §47 Phase 1"此阶段完全不接 LLM"；`src/engine_v2/README.md` 冻结规则 3）；
- 一切 v1 包：`src.graph`、`src.game`、`src.agents`、`src.web`、`src.llm`、`src.prompts`、`src.config`、`src.models`、`src.ui`（README 冻结规则 1）；
- 网络/进程 IO 库（`requests`、`httpx`、`socket`、`subprocess` 等）——Kernel 必须在无网络环境单测（Spec §47 Phase 1 验收、Plan §22.2）。

provider/model 相关数据（InferenceProfile 等）属于 Plan P6 的 `engine_v2/llm/`，**不得**出现在 P1 契约（Plan §10 强制约束"不允许加入 provider/model"）。LLM 调用在 trace 中的记录字段预留见 §5.4（只留 JSON 占位，不引入任何 provider 类型）。

### 0.4 命名与词法约定

- 文件名、类型名采用 Spec §44 已有命名（`entity.py`、`components.py`、`state.py`、`revision.py`、`actions.py`、`effects.py`、`events.py`、`transaction.py`），新增文件 `ids.py`、`provenance.py`、`trace.py`、`serialization.py`、`snapshot.py`、`clock.py`；
- ID 字符串前缀见 §3.2；类型标识符（component/action/effect/event type）为**名字型**小写点分字符串（如 `unlock`、`space.position`），与 Spec §11.2 action registry 示例一致；
- 所有契约类型的模块导出集中在 `core/__init__.py` re-export（骨架期 `__init__.py` 仅 docstring 的纪律在 Phase 1 填充时解除，`tests/test_engine_v2_skeleton.py::test_engine_v2_init_files_are_docstring_only` 需由 P1-T06 同步修订为允许 re-export 语句——这是骨架纪律的自然收尾，不属于破坏性变更）。

---

## 1. 模块布局与任务切分

### 1.1 `src/engine_v2/core/` 文件清单

| 文件 | 职责 | 包含的主要类型 | 归属任务包 |
|---|---|---|---|
| `ids.py` | 全部实体级 ID 原语：类型、前缀、生成、解析校验 | `EntityId` `EffectId` `EventId` `TransactionId` `ProducerId` `CascadeId` `ObservationId` `ActionInstanceId` `ScheduledEntryId` `TraceRecordId`；`new_*_id()` 工厂；`parse_id()` | **P1-T01** |
| `revision.py` | Revision 原语与陈旧性纯函数 | `Revision`、`INITIAL_WORLD_REVISION`、`next_revision()`、`is_stale()`、`RevalidationOutcome`（ACCEPT/REBASE/REPAIR/REJECT，Spec §9） | **P1-T01** |
| `provenance.py` | 跨契约共享的因果/来源小件 | `OriginKind`、`Provenance`、`CauseKind`、`CauseRef`、`CascadeContext` | **P1-T04**（先行件，供 effects/actions/events/transaction 引用） |
| `components.py` | typed component 的 schema 注册机制 | `ComponentTypeId`、`ComponentSchema`、`ComponentRegistry`、`ComponentData`（别名 `dict[str, JsonValue]`） | **P1-T03** |
| `entity.py` | Entity 身份记录 + 只读逻辑门面（不绑定真实 ECS，Spec §10.3） | `EntityRecord`、`EntityRef`、`EntityView` | **P1-T03** |
| `effects.py` | Effect 契约 | `EffectTypeId`、`StateDomainId`、`EntityTarget`、`StateDomainTarget`、`EffectTarget`（tagged union）、`ProposedEffect`、`CommittedEffect` | **P1-T04** |
| `actions.py` | Action 契约 | `ActionTypeId`、`ActionLifecycleStatus`（Spec §11.4）、`ActionTiming`、`FallbackSpec`、`ActionProposal`（§11.3 + §9 字段）、`ActiveAction`（§23.4 字段） | **P1-T04** |
| `events.py` | Event 契约 | `EventTypeId`、`DomainEvent`（§21.1 字段 + cause/provenance + cascade context） | **P1-T04** |
| `transaction.py` | Transaction 原子提交的数据表达 | `TransactionStatus`、`Transaction` | **P1-T04** |
| `state.py` | 状态容器 | `WorldState`、`ScenarioState`、`RuntimeState`、`RuntimeLifecycle`、`RngState`、`ScheduledEvent`（占位）、`ActorWakeup`（占位）、`BackendStateRef` | **P1-T02** |
| `trace.py` | Trace 记录契约 | `TraceKind`、`TraceRecord`（§8.4 内容逐项落位） | **P1-T02** |
| `serialization.py` | JSON round-trip 编解码与 JSON-clean 断言工具 | `dump_json()`、`load_json()`、`assert_json_clean()`、`deep_copy_via_roundtrip()` | **P1-T05** |
| `snapshot.py` | 快照信封、版本标记、immutable read view | `CONTRACT_SCHEMA_VERSION`、`SNAPSHOT_FORMAT_VERSION`、`Snapshot`、`freeze_view()`、`snapshot()`、`restore_snapshot()` | **P1-T05** |

> Spec §44 中 `core/` 还列有 `authority.py`、`validation.py`、`conflicts.py`、`reducer.py`、`commands.py`——
> 这些属于 **Plan P2**（authority/validation/conflict/reducer 行为）与开发命令（Spec §22），**P1 不创建**，
> 文件名予以保留，P2 直接沿用。`clock.py` 若 P3 需要逻辑时钟类型可在 `runtime/` 建立，P1 仅在 `state.py` 内以 `logical_tick: int` 表达（§4.3 决策 D-6）。

### 1.2 实现依赖顺序（任务切分与执行次序）

依赖图（箭头 = "依赖于"）：

```text
ids.py ─┬─ revision.py ─┬─ provenance.py ─┬─ effects.py ──┐
        │               │                 ├─ actions.py ──┼─ transaction.py
        └─ components.py ─ entity.py ─────┘               │
                                                           ├─ state.py（引用 entity/components/actions）
                        trace.py（仅依赖 ids/revision） ───┤
                                                           └─ serialization.py / snapshot.py（依赖全部）
```

**执行次序**（与 Plan §10 任务表的映射）：

1. **P1-T01**：`ids.py`、`revision.py`（无内部依赖，最先落地）；
2. **P1-T03**：`components.py`、`entity.py`（依赖 T01）；可与第 3 步中的 `provenance.py` 并行；
3. **P1-T04**：`provenance.py` → `effects.py`、`actions.py`、`events.py` → `transaction.py`（依赖 T01/T03 的 `EntityRef`/`ComponentTypeId`）；
4. **P1-T02**：`state.py`、`trace.py`（依赖 T01/T03/T04——`RuntimeState` 引用 `ActiveAction`、`ActionProposal`，`WorldState` 引用 `EntityRecord`；因此 **T02 必须在 T03/T04 之后**，与任务表列出顺序不同，属依赖使然；T02/T04 同为 QMax 串行执行，无冲突）；
5. **P1-T05**：`serialization.py`、`snapshot.py`（依赖全部 schema）；
6. **P1-T06**：测试（§8 给出验收口径；同时修订骨架 `__init__.py` 纪律测试，见 §0.4）。

**单 Owner 提醒**（migration-constraints §2）：Core ID/Revision、WorldState/RuntimeState、ProposedEffect、Transaction/Reducer、DomainEvent 均为单 Owner 契约。P1 内 T01/T03/T05/T06 由 Q27 执行、T02/T04 由 QMax 执行，文件归属互不重叠（见 §1.1 表），可并行，但**任何跨文件的契约字段改动必须回到本文档修订并经 Gate review**（Plan §10"public contract 修改必须经 Gate review"）。

---

## 2. ID 与 Revision 原语（P1-T01）

### 2.1 新类型 vs str 包装的取舍（决策 D-1）

候选方案：

| 方案 | 运行时开销 | 运行时类型检查 | JSON round-trip | 静态检查 |
|---|---|---|---|---|
| A. `NewType("EntityId", str)` | 零 | ❌（运行时即 str，isinstance 无效） | 天然 | ✅ |
| B. **typed `str` 子类**（本设计） | 近零 | ✅（isinstance 可用，P2 写屏障/校验可运行时断言） | 天然（序列化即纯字符串） | ✅ |
| C. 包装对象（`class EntityId(BaseModel): value: str`） | 高 | ✅ | 需自定义 serializer，JSON 中出现嵌套对象 | ✅ |

**决策（D-1）**：ID 族采用**方案 B（typed str 子类）**。理由：
1. Spec §10.1 要求 ID 可序列化、可追踪、不依赖对象地址——纯字符串值天然满足，且 JSON 中保持扁平字符串（trace/快照可读性最好）；
2. P2 的 validation/authority 管道需要**运行时**区分 ID 种类（如拒绝把 EffectId 当 EntityId 传入 target），`NewType` 无法支持；
3. 方案 C 使所有引用字段在 JSON 中变成嵌套对象，膨胀 trace 且无额外安全性。

**决策（D-2）**：`Revision` 采用 **typed `int` 子类**。理由：revision 需要算术（commit +1，Spec §9）与比较（staleness 判定），JSON 中必须是数字；与 ID 族保持同构的"子类化原生类型"模式。

**统一基类形态**（示意，T01 实现）：

```python
class EntityId(str):
    """WorldInstance 内唯一的实体标识（Spec §10.1）。值一旦签发即稳定（G1: public IDs stable）。"""
    __slots__ = ()
    PREFIX = "ent_"

class Revision(int):
    """WorldState 权威版本号：每次 transaction commit 成功 +1（Spec §9）。"""
    __slots__ = ()
    def next(self) -> "Revision":
        return Revision(self + 1)
```

Pydantic 兼容性：v2 对 `str`/`int` 子类注解会接受原生值并重建为子类实例；T06 round-trip 用例须同时断言**值相等**与**类型保持**（`type(x) is EntityId`），若所用 pydantic 版本对某子类不能保持类型，T01 须提供 `Annotated[EntityId, BeforeValidator(...)]` 兜底（契约语义不变）。

### 2.2 ID 族定义、前缀、生成与唯一性范围

| 类型 | 前缀 | 生成规则 | 唯一性范围 | 说明 |
|---|---|---|---|---|
| `EntityId` | `ent_` | `ent_` + uuid4 hex（32 位小写） | **WorldInstance 内唯一**（Spec §10.1） | 也允许内容侧使用确定性命名 ID（如 `ent_authoring_<slug>`）由 project loader（P5）保证不冲突；Kernel 只要求值稳定、可序列化 |
| `EffectId` | `eff_` | uuid4 hex | WorldInstance 内唯一 | 每个 ProposedEffect 一个；去重依据（规避 v1 KBC-2 重复累加，见 §10） |
| `EventId` | `evt_` | uuid4 hex | WorldInstance 内唯一 | Branch（Spec §30.5）后各世界线共享祖先事件 ID 空间，uuid4 生成天然避免跨分支碰撞 |
| `TransactionId` | `txn_` | uuid4 hex | WorldInstance 内唯一 | |
| `CascadeId` | `csc_` | uuid4 hex | WorldInstance 内唯一 | Spec §21.3 cascade 根创建时签发 |
| `ObservationId` | `obs_` | 由 ContextProvider（Plan P4）签发；P1 只定义类型与格式 | WorldInstance 内唯一 | Spec §9 示例 `obs_991`；异步结果回引其决策所基于的观察 |
| `ActionInstanceId` | `act_` | uuid4 hex | WorldInstance 内唯一 | **决策 D-3**：proposal 创建时签发，同一实例 ID 贯穿 `ActionProposal → ActiveAction`（调度、中断、trace 全链路可追踪，Spec K6/K7）；同一 actor 重复发起同 `action_id` 产生不同实例 |
| `ScheduledEntryId` | `sch_` | uuid4 hex | WorldInstance 内唯一 | 供 `RuntimeState.scheduler_queue` 占位结构（P3 语义）；K7 要求调度状态可检查 → 队列条目必须有身份 |
| `TraceRecordId` | `trc_` | uuid4 hex（或单调计数器+随机段） | trace 流内唯一 | §5.4 |
| `ProducerId` | 无随机段 | **名字型**：`[a-z0-9_]+(\.[a-z0-9_]+)*`，如 `policy.alice`、`dynamics.rigid_body`、`rule.lock_system`、`dev.console` | WorldInstance 运行时内唯一（producer 注册表，Plan P2 落位） | **决策 D-4**：Spec §17.1 authority 配置以名字引用 writer（`interaction.lock_system`、`llm_world_dynamics`），故 ProducerId 必须是确定性可读名字而非随机 ID |

**类型标识符族**（名字型 typed str，随各自 registry 定义，不属于 T01 而属 T03/T04，但词法统一在此规定）：
`ComponentTypeId`、`ActionTypeId`、`EffectTypeId`、`EventTypeId`、`StateDomainId` —— 均为小写点分字符串
（正则 `[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*`）。Kernel **不**预置任何 RPG 语义取值（Plan §10 强制约束）。

**通用规则**：
- 工厂函数 `new_entity_id()` 等集中于 `ids.py`，内部 `uuid.uuid4()`；测试可用确定性构造（直接 `EntityId("ent_test_1")`）；
- `parse_id(text) -> (kind, value)`：校验前缀与词法，非法即抛 `ValueError`（T06 用例）；
- **稳定性（G1 "public IDs stable"）**：双重含义——(a) ID 值一经签发不得变更/重新生成（round-trip 不得改写）；(b) ID **类型名与前缀**属 public contract，冻结后变更须走 Gate review。

### 2.3 Revision 语义（强制设计约束落位）

```python
INITIAL_WORLD_REVISION = Revision(0)

def next_revision(rev: Revision) -> Revision: ...          # rev + 1
def is_stale(base: Revision, current: Revision,
             valid_until: Revision | None = None) -> bool:
    """base < current 即陈旧；valid_until 非 None 时 current > valid_until 亦陈旧（Spec §9）。
    纯函数，不做任何状态访问；revalidation 决策（ACCEPT/REBASE/REPAIR/REJECT）属 P2 行为。"""
```

- `world_revision` **只**因 COMMITTED transaction 递增（Spec §9、§20.1"produce one world revision"）；调度簿记、trace 追加、view 派生**不**推进它（决策 D-5，见 §4.2）；
- 一切异步结果必须能携带 `base_world_revision`（ActionProposal/ProposedEffect 均为必填字段，§6.1/§6.3），提交前 revalidation 是 P2 强制行为，数据契约保证字段在场。

---

## 3. Entity + typed component 逻辑门面（P1-T03）

### 3.1 Entity 身份：`EntityRecord`（存于 WorldState 内）

```python
class EntityRecord(ContractModel):
    entity_id: EntityId
    entity_class: str | None = None        # authority selector 的 entity class 维度（Spec §17.2）
    tags: list[str] = Field(default_factory=list)   # authority selector 的 entity tag 维度（Spec §17.2）
    created_revision: Revision = INITIAL_WORLD_REVISION
    components: dict[ComponentTypeId, ComponentData] = Field(default_factory=dict)
```

- Entity 是**稳定 identity + 其组件的归属点**（Spec §10.1/§10.2）。`EntityRecord` 是数据记录，不是"活的"运行时对象——禁止任何代码持有跨 revision 的 entity 对象引用作为权威来源（规避 v1 KBC-3：NPC dict 内坐标永不更新、陈旧数据进 prompt）；
- `entity_class`/`tags` 为 P2 authority selector 预留（Spec §17.2 明确 selector 可用 entity class/tag）；Kernel 不定义其取值词表；
- 组件数据嵌入 EntityRecord（决策 D-7，§3.4）。

### 3.2 引用与只读门面：`EntityRef` 与 `EntityView`

```python
class EntityRef(ContractModel):
    """对 entity（及其可选的组件/字段）的引用。Spec §16.1 target 的 entity 分支。"""
    entity_id: EntityId
    component_type: ComponentTypeId | None = None
    field_path: str | None = None   # 字段级定位；Spec §17.2 警示脆弱裸路径——field_path 仅供
                                    # schema 已注册的组件使用，P2 validation 按 schema 校验其合法性

@dataclass(frozen=True)
class EntityView:
    """只读逻辑门面（Spec §10.3：公共 API 只承诺 Entity + typed components）。
    由 WorldState 查询方法构造；内部持有 MappingProxyType 深冻结视图；不持有 WorldState 引用。"""
    entity_id: EntityId
    entity_class: str | None
    tags: tuple[str, ...]
    revision: Revision                      # 构造时的 world_revision（视图有效性判据）
    def component_types(self) -> tuple[ComponentTypeId, ...]: ...
    def get_component(self, ct: ComponentTypeId) -> Mapping[str, JsonValue] | None: ...
```

- `WorldState` 提供的门面方法（全部只读，见 §4.1）：`entity_view()`、`component_view()`、`entities_with_component()`、`has_entity()`；
- **不绑定真实 ECS**（Spec §10.3）：公共 API 形态与底层存储（dict/table/ECS）解耦；P1 底层为 dict（§3.4），未来替换 ECS 不破坏本门面签名；
- 门面**不提供**任何写方法。reducer-only 写入的预留见 §3.5。

### 3.3 组件 schema 注册：`ComponentSchema` / `ComponentRegistry`

```python
@dataclass(frozen=True)
class ComponentSchema:
    component_type: ComponentTypeId          # 如 "space.position"（由模块/项目注册，Kernel 无内置）
    version: int = 1
    description: str = ""
    payload_model: type[BaseModel] | None = None    # None = 该组件按不透明 JSON dict 存储
    authority_domain: StateDomainId | None = None   # P2 authority selector 的 domain tag 维度（Spec §17.2）预留

class ComponentRegistry:
    def register(self, schema: ComponentSchema) -> None:
        """同类型重复注册：schema 完全相同 → 幂等返回；否则抛 ComponentConflictError。"""
    def get(self, ct: ComponentTypeId) -> ComponentSchema | None: ...
    def validate_payload(self, ct: ComponentTypeId, data: ComponentData) -> None:
        """有 payload_model 时做 schema 校验；无注册或无 model 时放行（§3.3 决策 D-8）。"""
```

**决策 D-8（未知组件类型的边界策略）**：`WorldState` 接受**未注册**组件类型的数据（按不透明 JSON dict 存储），校验发生在 (a) 注册时、(b) P2 reducer 应用 effect 时若 registry 有 schema 则校验。理由：
1. 存档加载（P8）可能先于全部模块加载（Spec §30.5 branch 要检查 project compatibility，但数据本身须可读出）；
2. 避免 Kernel 成为所有组件类的导入汇聚点（保持 core 的 import 纯净，§0.3）。
反向设计（Kernel 边界拒绝未注册类型）错误更早，但会锁死"模块可选加载"，本设计不采用——此取舍已有明确倾向与理由，按任务口径不计为 S2 歧义。

### 3.4 组件存储布局（决策 D-7）

`WorldState.entities: dict[EntityId, EntityRecord]`，组件**嵌入** EntityRecord（entity-centric），而非顶层 component table。理由：
1. Spec §10.3 明确内部实现可以是 dict/Pydantic/dataclass/component tables/ECS 中任一种——**公共契约与布局无关**，故此选择不构成 public contract 分歧；
2. entity-centric 使"单 entity 全量快照/删除/引用完整性检查"为 O(1)，最契合 MVP 的 reducer 与 snapshot 需求；
3. 系统级遍历（按组件类型）由门面 `entities_with_component()` 提供，P1 不承诺性能，未来可换 table/ECS 而不改门面。

### 3.5 reducer-only 写入的预留（P2 兼容保证）

P1 阶段容器按如下三条纪律保持与 P2 写屏障（Plan P2-T01）兼容：

1. **零公共写 API**：`WorldState`、`EntityRecord`、`EntityView` 一律不提供公共 mutator；`ContractModel.frozen=True` 阻断字段再赋值；
2. **入口深拷贝**：一切外部数据进入 WorldState 必须经 `model_validate`（Pydantic 校验过程生成新容器），禁止把调用方持有的可变 dict 直接挂进状态树——阻断"外部后续修改污染源状态"与"两个 revision 共享子结构"两类别名事故（T06 隔离用例，§8.5）；
3. **唯一变更缝隙**：P2 的 reducer 将以纯函数 `apply_transaction(state: WorldState, txn: Transaction) -> WorldState` 作为**唯一**产生新 WorldState 的公共路径（Plan P2-T06）。P1 为此预留：WorldState 的全部字段可由 `(现状态 + CommittedEffect 列表)` 经 `model_copy(update=...)` / 重建构造达成，无需任何就地修改。P1 内部可提供 `_with_*` 前缀的**私有**构造助手供测试与未来 reducer 使用，但不得导出为公共 API。

---

## 4. 状态契约（P1-T02）

> 依据：Spec §8（五状态模型）、§9、ADR-003。P1 落位前四个中与 Kernel 数据直接相关者：
> WorldState、RuntimeState、BackendState（以 **ref** 形式）、TraceState（以 **TraceRecord** 形式）。
> ViewState 是派生数据（Spec §8.5），无独立 schema，P1 不定义其结构（P10 职责）。

### 4.1 `WorldState` —— 权威世界事实（Spec §8.1）

```python
class ScenarioState(ContractModel):
    """Spec §8.1 scenario state 的 Kernel 侧最小表达；剧本语义由 P9 scenario 模块填充。"""
    scenario_id: str | None = None
    stage: str | None = None
    data: dict[str, JsonValue] = Field(default_factory=dict)

class WorldState(ContractModel):
    schema_version: int = CONTRACT_SCHEMA_VERSION      # P8 存档迁移预留（§7.3）
    world_revision: Revision = INITIAL_WORLD_REVISION  # Spec §9：每次 commit +1
    entities: dict[EntityId, EntityRecord] = Field(default_factory=dict)
    world_variables: dict[str, JsonValue] = Field(default_factory=dict)   # Spec §8.1 world variables
    scenario_state: ScenarioState = Field(default_factory=ScenarioState)  # Spec §8.1 scenario state
    # —— 只读门面（非字段）——
    def entity_view(self, eid: EntityId) -> EntityView | None: ...
    def component_view(self, eid: EntityId, ct: ComponentTypeId) -> Mapping[str, JsonValue] | None: ...
    def entities_with_component(self, ct: ComponentTypeId) -> tuple[EntityId, ...]: ...
    def has_entity(self, eid: EntityId) -> bool: ...
```

**Spec §8.1 六项内容逐项落位**：

| Spec §8.1 | 落位 | 说明 |
|---|---|---|
| entities | `entities`（EntityRecord 的 entity_id/tags/class） | §3.1 |
| components | `entities[*].components` | §3.4 决策 D-7 |
| world variables | `world_variables` | 通用键值；Kernel 不预置键名 |
| scenario state | `scenario_state` | Kernel 只给信封，语义归 P9 |
| knowledge / belief components | **组件**（`entities[*].components` 中注册的 knowledge 类组件） | Kernel 无内置；P9 knowledge 模块注册组件类型（避免"标准 RPG 字段进 Kernel"） |
| persistent gameplay state | 组件 + `world_variables` | 同上 |

**四个特点（Spec §8.1）的契约保证**：authoritative（K1：唯一权威表示，ViewState/trace 不得反向写回）、serializable（§0.2）、revisioned（`world_revision` 字段）、reducer-only mutation（§3.5 三纪律）。

**WorldInstance 关系（Spec §7.2/§10.1）**：`WorldState` 本体**不**内嵌 world_instance_id——保持状态实例无关，使 snapshot 可载入新实例/分支实例而无需改写（决策 D-9）；instance 身份记录在 `Snapshot` 信封（§7.3）与运行时容器上；EntityId 的 WorldInstance 内唯一性由构造期 dict 键唯一性 + P2 reducer 的新增 entity 检查强制。

### 4.2 `RuntimeState` —— 运行时控制状态（Spec §8.2）

```python
class RuntimeLifecycle(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    PAUSED = "paused"
    STEPPING = "stepping"      # 开发单步（Spec §22 pause/step 的承载态）
    STOPPED = "stopped"

class RngState(ContractModel):
    """Spec §8.2 RNG state。Kernel 不固定算法（Spec §15.4 determinism: seeded 由 backend 声明）。"""
    algorithm: str                      # 如 "pcg32"、"mt19937"，由 P3 运行时决定
    state: dict[str, JsonValue] = Field(default_factory=dict)   # 算法私有状态（seed/counter/…）

class ScheduledEvent(ContractModel):
    """Spec §8.2 scheduler queue 条目；P1 仅占位数据，调度语义（排序/触发/同刻规则）属 Plan P3。"""
    entry_id: ScheduledEntryId
    due_tick: int                                   # 到期的 logical_tick
    kind: str                                       # "action_checkpoint" | "wakeup" | …（P3 定词表）
    payload: dict[str, JsonValue] = Field(default_factory=dict)  # 如 {instance_id: "act_…"}

class ActorWakeup(ContractModel):
    """Spec §8.2 actor wakeups 占位；语义属 Plan P4（Actor/Context）。"""
    actor_id: EntityId
    due_tick: int
    reason: str | None = None

class BackendStateRef(ContractModel):
    """Spec §8.3 BackendState 的 Kernel 侧表达：只存引用与能力声明（决策 D-10）。"""
    backend_id: str                     # 运行时内唯一
    backend_kind: str                   # "dynamics" | "space" | "inference_host" | …
    checkpointable: bool = False        # Spec §8.3 三项声明
    restorable: bool = False
    replayable: bool = False
    checkpoint_ref: str | None = None   # 外部 checkpoint 定位串，由 PersistenceBackend（P8）解析
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

class RuntimeState(ContractModel):
    schema_version: int = CONTRACT_SCHEMA_VERSION
    logical_tick: int = 0               # Spec §8.2 logical clock（决策 D-6）
    lifecycle: RuntimeLifecycle = RuntimeLifecycle.CREATED    # Spec §8.2 runtime lifecycle state
    scheduler_queue: list[ScheduledEvent] = Field(default_factory=list)   # Spec §8.2 scheduler queue（P3 语义）
    active_actions: dict[ActionInstanceId, ActiveAction] = Field(default_factory=dict)  # Spec §8.2 active actions（§23.4 字段）
    actor_wakeups: list[ActorWakeup] = Field(default_factory=list)        # Spec §8.2 actor wakeups（P4 语义）
    active_modes: list[str] = Field(default_factory=list)                 # Spec §8.2 gameplay contexts/modes；
    mode_context: dict[str, JsonValue] = Field(default_factory=dict)      #   overlay 语义 Spec §25，Plan P4
    rng_state: RngState | None = None                                     # Spec §8.2 RNG state
    pending_proposals: list[ActionProposal] = Field(default_factory=list) # Spec §8.2 pending proposals
    backend_refs: dict[str, BackendStateRef] = Field(default_factory=dict) # Spec §8.3（决策 D-10）
```

**关键决策**：

- **D-5（revision 归属）**：`world_revision` 只随 WorldState 事务提交递增；RuntimeState 变更（调度簿记、proposal 入队）**不**推进 world_revision。快照一致性由 Snapshot 信封同时固化两个状态达成（§7.3），无需第二套全局版本号。依据：Spec §9 将 revision 递增明确绑定 transaction commit。
- **D-6（逻辑时钟形态）**：`logical_tick: int` 单一单调计数即 P1 的逻辑时钟；Spec §23.1 的六层时间（action duration / decision horizon / world logical time / physics timestep / player turn / narrative compression）中，P1 只固化 world logical time 的最小载体，其余由 P3 的 Scheduler/TimePolicy 在其上定义。**日历时间（day/hour/minute）不是 RuntimeState 字段**——它是世界事实，归 WorldState（`world_variables` 或 P9 模块组件），且必须整体结构化存取。此为对 v1 **KBC-4（game_time 的 day 键首回合即丢失）** 的直接规避：v1 把日历时间放进入口状态并以部分 dict 覆写导致字段丢失；v2 中任何"时间推进"只能通过带完整 payload 的 effect 完成，payload schema 校验拒绝残缺结构。
- **D-10（BackendState 位置）**：ADR-003 明确 BackendState "不进入 WorldState 快照"；GPU buffer/外部 solver 等本质上不可 JSON 化。故 Kernel 只在 `RuntimeState.backend_refs` 存**引用 + 三项能力声明**（Spec §8.3 checkpointable/restorable/replayable），真实 checkpoint 由 PersistenceBackend（Plan P8）外置管理；backend 不支持 checkpoint 时 branch/replay 能力降级（Spec §8.3/§30.5），数据上表现为 `checkpointable=False`。
- **占位字段纪律**：`scheduler_queue`/`actor_wakeups`/`active_modes`/`mode_context` 在 P1 只有数据结构与 round-trip 保证，**无**排序、触发、合并语义（Plan：P3/P4 实现）；字段命名与 Spec §8.2 清单一一对应，P3/P4 不得改名（public contract 冻结）。

### 4.3 snapshot / trace 归属总表（哪些字段进 snapshot、哪些进 trace）

| 数据 | 进 Snapshot（Spec §30.2） | 进 Trace（Spec §8.4） | 说明 |
|---|---|---|---|
| WorldState 全部字段 | ✅ | ❌ | trace 记录"变化"，不复制状态本体 |
| RuntimeState 全部字段 | ✅ | ❌ | 含调度队列/active actions（K7 可检查、可恢复） |
| BackendState | 仅 `backend_refs`（引用+能力声明） | ❌ | 真实 checkpoint 外置（§4.2 D-10） |
| commands / action proposals / proposed effects | ❌ | ✅（TraceKind 对应项） | |
| authority / validation / conflict 决定 | ❌ | ✅ | P2 产生 |
| transactions / domain events | 仅其**结果**（已体现在 WorldState） | ✅（完整记录含 provenance） | |
| LLM calls / prompt assembly metadata | ❌ | ✅（P6 起产生） | credential 永不入 trace（Spec §31.3） |
| development interventions | ❌ | ✅（`origin=developer` 显式标记，Spec §22） | |
| ViewState | ❌ | ❌ | 派生数据，随时重算（Spec §8.5） |
| Project version / module versions | ✅（Snapshot 信封字段） | ❌ | Spec §30.2，P5 填充真实值 |

### 4.4 `TraceRecord` —— TraceState 的记录单元（Spec §8.4）

**决策 D-11**：TraceState 采用**单一信封 + kind 判别 + 开放 payload** 的 append-only 记录流，而非每类记录一个顶层模型。理由：(a) Spec §8.4 要求 trace 可流式持久化——同质信封对 append-only 文件/表最友好；(b) P2/P6 新增记录种类（conflict 决定、LLM 调用）不需要改 core 顶层类型集合，只需注册新 `TraceKind` 与 payload 子约定；(c) 前向兼容：旧工具遇未知 kind 可按 payload 原样透传。

```python
class TraceKind(str, Enum):
    COMMAND = "command"                       # Spec §8.4 commands
    ACTION_PROPOSAL = "action_proposal"       # action proposals
    PROPOSED_EFFECT = "proposed_effect"       # proposed effects
    AUTHORITY_DECISION = "authority_decision" # authority decisions（P2 产生）
    VALIDATION_DECISION = "validation_decision"
    CONFLICT_RESOLUTION = "conflict_resolution"
    TRANSACTION = "transaction"               # transactions（含 ABORTED，审计原子失败）
    DOMAIN_EVENT = "domain_event"             # events
    LLM_CALL = "llm_call"                     # LLM calls（P6 起；字段见下）
    PROMPT_ASSEMBLY = "prompt_assembly"       # prompt assembly metadata
    DEV_INTERVENTION = "dev_intervention"     # development interventions（Spec §22）
    SYSTEM = "system"                         # lifecycle/错误等杂项

class TraceRecord(ContractModel):
    record_id: TraceRecordId
    kind: TraceKind
    world_revision: Revision | None = None    # 记录产生时的 world_revision
    logical_tick: int | None = None
    wall_time: datetime | None = None         # 仅诊断；权威排序一律用 revision+tick
    producer_id: ProducerId | None = None
    transaction_id: TransactionId | None = None
    cascade_id: CascadeId | None = None
    payload: dict[str, JsonValue] = Field(default_factory=dict)
```

**payload 子约定（按 kind）**：

| kind | payload 约定字段 |
|---|---|
| `action_proposal` / `proposed_effect` / `transaction` / `domain_event` | `{"record": <对应契约模型的 model_dump(mode="json")>}`——trace 内嵌完整记录，支持无 runtime 离线审计 |
| `authority_decision` / `validation_decision` / `conflict_resolution` | `effect_id`、`decision`（P2 定义词表：allow/deny/…）、`reason`（P2 填充） |
| `llm_call` | 预留 Spec §31.3 字段：`logical_role`、`profile`、`resolved_model`、`input_token_estimate`、`prompt_metadata_ref`、`output_ref`、`latency_ms`、`parse_retry`、`base_revision`。**不得**出现 credential/api_key（Spec §31.3、K8）；P1 只冻结此键名约定，不产生记录 |
| `dev_intervention` | `origin: "developer"`（强制，Spec §22）+ 命令描述 |

**流不变量**：trace 只追加不修改；`record_id` 流内唯一；同一 WorldInstance 的 trace 与 snapshot 通过 `world_revision + logical_tick` 对齐。存储介质（文件/SQLite/…）属 PersistenceBackend（Spec §30.3，Plan P8），P1 不定。

---

## 5. 行动 / 效果 / 事件 / 事务契约（P1-T04）

### 5.0 共享小件：`provenance.py`

```python
class OriginKind(str, Enum):
    BEHAVIOR_POLICY = "behavior_policy"      # Spec §16.2 BehaviorPolicy
    DYNAMICS_BACKEND = "dynamics_backend"    # DynamicsBackend
    RULE = "rule"                            # RuleEngine
    SCRIPT = "script"                        # ScriptSystem
    SCENARIO = "scenario"                    # QuestSystem/scenario
    DEVELOPER = "developer"                  # DeveloperCommand（Spec §22 origin=developer）
    SYSTEM = "system"                        # Kernel 自身（如结构性事件）

class Provenance(ContractModel):
    """K6：任何 committed 变化可回答"谁提出"。ActionProposal/ActiveAction/DomainEvent/Transaction 共用。"""
    producer_id: ProducerId
    origin: OriginKind
    source_record_id: TraceRecordId | None = None   # 指向 trace 中的原始记录（如 llm_call）
    notes: str | None = None

class CauseKind(str, Enum):
    EVENT = "event"
    ACTION = "action"          # ActionInstanceId
    EFFECT = "effect"          # EffectId
    PROPOSAL = "proposal"      # ActionInstanceId（proposal 与 active action 同实例 ID，D-3）
    INTERVENTION = "intervention"

class CauseRef(ContractModel):
    """Spec §21.2 cause ids 的类型化表达：(kind, id) 对，避免裸字符串歧义。"""
    kind: CauseKind
    ref_id: str

class CascadeContext(ContractModel):
    """Spec §21.3：cascade_id / causal_root_id / depth 随事件传播。"""
    cascade_id: CascadeId
    causal_root_id: str        # 级联根（EventId 或 ActionInstanceId）
    depth: int = 0             # 根为 0；max cascade depth 为运行时配置（P2 executor），不是数据字段
```

### 5.1 `ActionProposal`（Spec §11.3 字段 + §9 revision 字段）

```python
class ActionTiming(ContractModel):
    """Spec §11.3 timing 的最小数据表达；调度语义属 P3。"""
    earliest_start_tick: int | None = None
    deadline_tick: int | None = None
    duration_hint_ticks: int | None = None

class FallbackSpec(ContractModel):
    action_id: ActionTypeId
    arguments: dict[str, JsonValue] = Field(default_factory=dict)

class ActionProposal(ContractModel):
    # —— 身份与主体 ——
    proposal_id: ActionInstanceId            # D-3：贯穿 proposal→ActiveAction 的实例 ID
    actor_id: EntityId                       # Spec §11.3 actor_id（Actor 是世界实体，§12.1）
    action_id: ActionTypeId                  # Spec §11.3 action_id；注册词表归 Action Registry（§11.2，P3/P5）
    arguments: dict[str, JsonValue] = Field(default_factory=dict)   # §11.3 arguments
    intent: str | None = None                # §11.3 intent（自由文本意图）
    timing: ActionTiming = Field(default_factory=ActionTiming)      # §11.3 timing
    confidence: float | None = None          # §11.3 confidence，取值 [0,1]，越界校验失败
    fallback_action: FallbackSpec | None = None                     # §11.3 fallback_action
    # —— Spec §9 异步结果修订字段 ——
    base_world_revision: Revision            # 必填：提案所基于的世界版本
    observation_id: ObservationId | None = None      # 决策所基于的观察（P4 签发）
    actor_state_revision: Revision | None = None     # 决策时 actor 相关状态对应的 world_revision
    valid_until: Revision | None = None              # 可选有效期
    # —— 来源 ——
    provenance: Provenance
```

**决策 D-12（actor_state_revision 的口径）**：v2 只有单一 world_revision（K1 单一权威状态），不建立独立 actor 修订序列；`actor_state_revision` 记录**读取 actor 决策相关状态时的 world_revision**。依据 K1，此为唯一不与"单一 authoritative state"冲突的口径。

**决策 D-13（必填性）**：`base_world_revision` 必填（Spec §9 对异步结果的要求 + 强制设计约束"异步结果携带 base_world_revision"）；`observation_id`/`actor_state_revision` 可选——同步玩家提案在 P1 阶段可能尚无观察管线（P4 才有 ContextProvider）。revalidation 的四种结果 `RevalidationOutcome(ACCEPT/REBASE/REPAIR/REJECT)` 定义于 `revision.py`（Spec §9），其**判定行为**属 P2（Plan P2-T04），P1 只落数据词表。

### 5.2 `ActiveAction`（Spec §23.4 字段逐项）

```python
class ActionLifecycleStatus(str, Enum):
    """Spec §11.4 状态机。IDLE 是 actor 层状态（未持有任何 action），不作为 action 记录状态。"""
    PROPOSED = "proposed"
    VALIDATING = "validating"
    ACTIVE = "active"
    INTERRUPTED = "interrupted"
    COMPLETED = "completed"
    FAILED = "failed"

class ActiveAction(ContractModel):
    instance_id: ActionInstanceId            # = 对应 ActionProposal.proposal_id（D-3）
    action_id: ActionTypeId                  # §23.4 action_id
    actor_id: EntityId                       # §23.4 actor_id
    status: ActionLifecycleStatus            # §11.4
    start_tick: int                          # §23.4 start_time → logical_tick 口径
    expected_end_tick: int | None = None     # §23.4 expected_end
    progress: float | None = None            # §23.4 progress，[0,1]
    interruptible: bool = True               # §23.4 interruptible
    completion_condition: dict[str, JsonValue] | None = None  # §23.4 completion_condition；
                                               # 声明式条件数据，求值器属 P3（格式契约由 P3 定，P1 保持不透明）
    next_checkpoint_tick: int | None = None  # §23.4 next_checkpoint
    base_world_revision: Revision            # 继承自 proposal（§9 revalidation 依据）
    provenance: Provenance
    last_transition_tick: int = 0            # 最近一次状态迁移的 tick（审计用）
    result_summary: dict[str, JsonValue] | None = None   # COMPLETED/FAILED 时的结果摘要
```

**K7 落位**：ActiveAction 全部字段可序列化、可检查，不存在隐藏于 coroutine 的调度事实（Spec §23.3"Scheduler state 必须显式"）。`completion_condition` 刻意保持不透明 JSON：P1 不锁定条件 DSL（v1 `condition_eval` 语法是否沿用由 Plan P3 决定），避免把 P3 决策提前扩散。

### 5.3 `ProposedEffect`（Spec §16.1 字段逐项）

```python
class EffectTypeId(str): ...                 # 名字型，词表由模块/项目注册
class StateDomainId(str): ...                # 名字型 domain tag（Spec §17.2）

class EntityTarget(ContractModel):
    kind: Literal["entity"] = "entity"
    entity_id: EntityId
    component_type: ComponentTypeId | None = None
    field_path: str | None = None            # 仅限已注册 schema 的组件（§3.2）

class StateDomainTarget(ContractModel):
    kind: Literal["state_domain"] = "state_domain"
    domain: StateDomainId                    # 如 world_variables 域 / scenario 域；词表由 P2 authority 配置声明

EffectTarget = Annotated[
    EntityTarget | StateDomainTarget,
    Field(discriminator="kind"),             # JSON 中以 "kind" 作 tagged union 判别
]

class ProposedEffect(ContractModel):
    effect_id: EffectId                      # §16.1 effect_id
    effect_type: EffectTypeId                # §16.1 effect_type
    source: ProducerId                       # §16.1 source
    target: EffectTarget                     # §16.1 target: EntityRef | StateDomain
    payload: dict[str, JsonValue]            # §16.1 payload（变更内容，schema 由 effect_type 约定）
    base_revision: Revision                  # §16.1 base_revision
    cause_ids: list[CauseRef] = Field(default_factory=list)   # §16.1 cause_ids（类型化，§5.0）
    authority_scope: str | None = None       # §16.1 authority_scope
    priority_hint: int | None = None         # §16.1 priority_hint（conflict resolver 的输入之一，§19）
    metadata: dict[str, JsonValue] = Field(default_factory=dict)  # §16.1 metadata
```

与 Spec §16.1 逐字段一致；两处具体化均有依据：`target` 的 union 用 tagged union 落 JSON（§0.2）；`cause_ids` 用 `CauseRef` 落 K6 的类型可追踪性。

### 5.4 `CommittedEffect`

```python
class CommittedEffect(ContractModel):
    effect: ProposedEffect                   # 被接受的原始提案（完整保留，provenance 不丢失）
    transaction_id: TransactionId            # 归属事务（原子单元成员证明）
    commit_revision: Revision                # 该事务产生的唯一新 revision（§20.1）
    sequence: int                            # 事务内应用序号：reducer 确定性应用顺序（§20.2 deterministic）
```

设计取舍：CommittedEffect **内嵌** ProposedEffect 而非只存 effect_id——事务/快照记录自包含，event-level replay（Spec §30.4）无需回查 trace 索引。

### 5.5 `DomainEvent`（Spec §21.1 字段 + cause/provenance）

```python
class EventTypeId(str): ...                  # 名字型；词表由模块定义，Kernel 不预置 RPG 事件

class DomainEvent(ContractModel):
    event_id: EventId                        # §21.1 event_id
    event_type: EventTypeId                  # §21.1 event_type
    world_revision: Revision                 # §21.1 world_revision（= 产生该事件的事务 commit_revision）
    logical_tick: int | None = None          # §21.1 timestamp 的权威序落位（决策 D-14）
    transaction_id: TransactionId | None = None  # §21.1 transaction_id；无事务的 runtime 事实可为 None
    payload: dict[str, JsonValue] = Field(default_factory=dict)   # §21.1 payload
    cause_ids: list[CauseRef] = Field(default_factory=list)       # §21.1 cause_ids + §21.2
    source_system: ProducerId                # §21.1 source_system
    provenance: Provenance                   # K6/§21.2 source 全量表达
    cascade: CascadeContext | None = None    # §21.3 cascade 传播
    wall_time: datetime | None = None        # §21.1 timestamp 的诊断侧：ISO-8601，仅诊断
```

**决策 D-14（timestamp 口径）**：Spec §23.1 时间分层下，"timestamp"一词有墙钟/逻辑刻/日历三种合理读法。本契约**同时**提供权威序（`logical_tick` + `world_revision`，整型、可比较、replay 友好）与诊断墙钟（`wall_time`，可空），日历时间不进事件（它是世界状态事实，可经 payload 引用）。该设计为三者并存而非择一，无需裁决。

**事件粒度（Spec §21.2）**：只要求基本 provenance，不要求微观物理过程事件化——`payload` 开放，粒度由 producer/P2 策略决定。

### 5.6 `Transaction` —— 原子提交语义的数据表达（Spec §20.1）

```python
class TransactionStatus(str, Enum):
    COMMITTED = "committed"
    ABORTED = "aborted"

class Transaction(ContractModel):
    transaction_id: TransactionId
    status: TransactionStatus
    base_revision: Revision                  # 构建时对照的 world_revision
    commit_revision: Revision | None = None  # COMMITTED 时 == base_revision + 1（唯一新版本）；ABORTED 时 None
    logical_tick: int | None = None
    effects: list[CommittedEffect] = Field(default_factory=list)  # 仅 COMMITTED 携带
    event_ids: list[EventId] = Field(default_factory=list)        # 提交时派发的事件（§20.1 emit domain events）
    cascade: CascadeContext | None = None
    provenance: Provenance | None = None     # 如 developer 注入的事务（Spec §22）
    abort_reason: str | None = None          # ABORTED 的原因（validation/conflict/atomic failure）
```

**原子性的数据层表达**（T06 以不变量用例固化）：
1. `status == COMMITTED` ⇒ `commit_revision == base_revision.next()`，且 **`effects` 必须非空**（`len(effects) >= 1`）——空事务不产生状态变化，不应消耗 revision；
2. `status == ABORTED` ⇒ `commit_revision is None` 且 `effects == []`（**部分提交不可表达**——任何 effect 要么全体共享同一 `commit_revision`，要么全体不落盘；这正是 §20.1 atomic commit 的数据形态，也是 Plan P2 必须测试的"transaction 中一项 invalid → atomic failure"的契约基础）；
3. `effects[*].sequence` 在事务内唯一且自 0 连续（reducer 确定性，§20.2）；
4. 一次 COMMITTED transaction 使 `world_revision` 恰 +1（Spec §9）——reducer 行为在 P2，P1 以字段契约与测试桩保证该语义可表达且仅可如此表达。

### 5.7 级联（Spec §21.3）的数据承载

cascade 执行器属 Plan P2-T07；P1 数据契约保证：每个 `DomainEvent`/`ProposedEffect`/`Transaction` 均可携带 `CascadeContext`（§5.0），`cause_ids` 串联因果链；`max cascade depth` 与 cycle diagnostics 是执行器运行时配置与诊断输出（P2-T08），P1 仅在 TraceKind 中为其预留记录通道（`SYSTEM`/`CONFLICT_RESOLUTION`）。

---

## 6. 序列化与快照基础设施（P1-T05）

### 6.1 JSON round-trip 规则

```python
def dump_json(model: BaseModel) -> str: ...          # model_dump(mode="json") + json.dumps(ensure_ascii=False)
def load_json(cls: type[M], text: str | bytes) -> M: # json.loads + model_validate（extra=forbid 生效）
def assert_json_clean(value: Any) -> None:           # 递归断言仅含 JSON 原生类型（T06 工具）
def deep_copy_via_roundtrip(model: M) -> M:          # dump→load，保证深拷贝与类型重建
```

规则：
1. 唯一合法出入口是 `model_dump(mode="json")` / `model_validate`；禁止自定义 `__dict__` 直写；
2. `ensure_ascii=False`（UTF-8 中文内容一等公民），加载端兼容任意合法 JSON；
3. dict 键一律 str；EntityId 键序列化后为纯字符串，反序列化由 Pydantic 重建为子类实例（T06 类型保持断言，§2.1）；
4. round-trip 不得改变任何 ID 值、revision 值、枚举字面量（G1 "public IDs stable" 的序列化侧表达）。

### 6.2 Immutable read view 策略（决策 D-15）

| 方案 | 评估 |
|---|---|
| A. Pydantic `frozen=True` | 阻止字段再赋值；但 `payload` 等嵌套 dict 仍**可被深层修改**（浅冻结）。成本最低、保留类型化 API |
| B. `MappingProxyType`/tuple 深冻结 | 真正的深度只读；但丢失契约类型 API，需包装层 |
| C. 持久化数据结构（copy-on-write 树） | 语义最优但引入重型实现，MVP 过度设计 |

**决策（D-15）**：**A 为基础 + B 为视图层**：
1. 全部契约模型 `frozen=True`（§0.1）——挡住"字段级"意外写入；
2. `snapshot.py` 提供 `freeze_view(value)`：把嵌套 dict/list 递归转为 `MappingProxyType`/`tuple`，用于**交给消费者**（P3/P4 的 policy、P10 的 view 派生）的只读视图；`EntityView.get_component()` 返回的即深冻结视图（§3.2）；
3. 深冻结视图是**咨询性**（advisory）不变量：恶意代码可绕过（Python 语言限度），强制性由 P2 写屏障 + reducer-only 公共 API 承担（§3.5）；
4. 快照固化走 `deep_copy_via_roundtrip`：Snapshot 内数据与运行时活数据**零别名**（T06 隔离用例）。

### 6.3 快照信封与版本标记（P8 存档迁移预留）

```python
CONTRACT_SCHEMA_VERSION = 1     # P1 契约版本；任何 public 字段变更必须 +1 并过 Gate
SNAPSHOT_FORMAT_VERSION = 1     # 信封格式版本

class Snapshot(ContractModel):
    snapshot_format_version: int = SNAPSHOT_FORMAT_VERSION
    contract_schema_version: int = CONTRACT_SCHEMA_VERSION
    world_instance_id: str                       # D-9：instance 身份在信封层，不在 WorldState 内
    world_state: WorldState
    runtime_state: RuntimeState
    created_logical_tick: int
    created_wall_time: datetime | None = None    # 诊断用
    project_version: str | None = None           # Spec §30.2 Project version（P5 起填充）
    module_versions: dict[str, str] = Field(default_factory=dict)  # Spec §30.2 Module versions
```

- 版本标记策略：`WorldState.schema_version` / `RuntimeState.schema_version`（内嵌）+ `Snapshot.snapshot_format_version`（信封）+ `contract_schema_version`（全局契约代）。三层使 P8 迁移器（Spec §44 `content/migrations.py`）能分别处理"信封变化 / 状态模型变化 / 契约语义变化"；
- Backend checkpoints **不**内嵌快照（§4.2 D-10），经 `runtime_state.backend_refs[*].checkpoint_ref` 关联；
- `snapshot()`/`restore_snapshot()` 为纯函数（`WorldState, RuntimeState, ... -> Snapshot` / `Snapshot -> (WorldState, RuntimeState)`），不含 IO；持久化介质属 P8 PersistenceBackend（Spec §30.3）。

---

## 7. 测试契约（P1-T06 验收口径）

> 对齐 Plan §22.2 State 五类（serialization / ID stability / revision / invalid reference / snapshot isolation）
> 与 Plan §22.3 adversarial 清单（duplicated ID / missing entity / stale revision / …）。
> 全部用例必须无网络、无 API key、无 provider、无 LangGraph（Plan §22.2、Spec §47 Phase 1 验收）。
> 建议文件：`tests/engine_v2/core/test_ids.py`、`test_entity_components.py`、`test_state.py`、`test_contracts.py`、`test_serialization_snapshot.py`、`test_import_boundary.py`。

### 7.1 ID 与 Revision（对 T01）

| # | 场景 | 验收判据 |
|---|---|---|
| R1 | ID 生成唯一性 | 每种 `new_*_id()` 连续生成 ≥10⁴ 个，无碰撞；前缀与词法正则匹配 |
| R2 | ID 稳定性 | round-trip 前后 ID 值逐字相等；`type` 保持（EntityId 等子类，§2.1） |
| R3 | parse_id | 合法/非法（错误前缀、空串、大写、非法字符）分别通过与抛 `ValueError` |
| R4 | ProducerId 词法 | 名字型语法校验；authority 配置示例（`interaction.lock_system` 等，Spec §17.1）可通过 |
| R5 | Revision 语义 | `INITIAL_WORLD_REVISION == 0`；`next_revision(r) == r+1`；JSON 中为纯整数 |
| R6 | staleness | `is_stale(base=812, current=813)` 为真；`base == current` 为假；`valid_until` 边界（`current == valid_until` 不陈旧，`current > valid_until` 陈旧） |

### 7.2 Entity / Component（对 T03）

| # | 场景 | 验收判据 |
|---|---|---|
| E1 | registry 冲突 | 同 component_type 注册不同 schema → 抛错；相同 schema 重复注册幂等 |
| E2 | 未知组件类型 | WorldState 接受未注册组件类型数据（D-8）；`validate_payload` 有 schema 时拒绝非法 payload |
| E3 | 门面只读 | `EntityView.get_component()` 返回值不可写（赋值抛 `TypeError`）；EntityView/WorldState 无公共写 API（静态断言：无公共 mutator 方法名） |
| E4 | EntityId 唯一 | 构造 WorldState 时重复 EntityId 键被 dict 语义折叠——builder 助手须显式抛错；`entities_with_component` 结果正确 |
| E5 | 引用完整性 | `EntityRef` 指向不存在 entity / 未挂载组件：门面查询返回 None，不抛未定义异常（非法引用的"判定"属 P2 validation，P1 只保证查询安全） |

### 7.3 状态容器（对 T02）

| # | 场景 | 验收判据 |
|---|---|---|
| S1 | round-trip | WorldState / RuntimeState / BackendStateRef / TraceRecord（各 kind 代表样本）`model_validate(model_dump(mode="json"))` 值相等 |
| S2 | snapshot/trace 归属 | WorldState 字段集合不含 trace/view 数据；TraceRecord 不含状态本体（§4.3 表的程序化断言） |
| S3 | 占位字段纪律 | `scheduler_queue`/`actor_wakeups`/`active_modes`/`pending_proposals`/`backend_refs` 默认空且 round-trip 保持；无任何调度语义函数被导出 |
| S4 | BackendStateRef | 三项能力声明默认 False；`checkpoint_ref` 可为 None |
| S5 | frozen | 对 WorldState/RuntimeState 字段赋值抛错（`ValidationError`/`TypeError`） |

### 7.4 行动/效果/事件/事务（对 T04）

| # | 场景 | 验收判据 |
|---|---|---|
| C1 | ActionProposal 必填 | 缺 `base_world_revision` / `provenance` → 校验失败；`confidence` 越界（<0 或 >1）→ 失败 |
| C2 | §9 字段在场 | `base_world_revision`/`observation_id`/`actor_state_revision`/`valid_until` 均可序列化承载（Spec §9 示例 `base_world_revision=812, observation_id="obs_991"` 可直接构造） |
| C3 | EffectTarget 判别 | entity / state_domain 两分支 round-trip；未知 `kind` → 失败 |
| C4 | 事务原子不变量 | COMMITTED ⇒ `commit_revision == base_revision+1`、`effects` 非空、`sequence` 唯一连续；ABORTED ⇒ `commit_revision is None` 且 `effects == []`（§5.6） |
| C5 | CommittedEffect 一致性 | 事务内全部 effects 共享同一 `transaction_id`/`commit_revision` |
| C6 | DomainEvent provenance | `provenance`/`source_system`/`world_revision` 必填；`cause_ids` 的 CauseRef 种类校验；cascade 上下文 depth/root 可承载 |
| C7 | 非法引用（adversarial，Plan §22.3） | effect 指向 missing entity、stale revision（`base_revision < current` 可被 `is_stale` 判定）、duplicated effect_id 进同一事务 → P1 提供纯函数检查器（`check_transaction_references(state, txn)`）返回结构化错误列表（判定与拒绝行为属 P2，P1 只给数据级检查） |

### 7.5 序列化 / 快照 / 隔离（对 T05）

| # | 场景 | 验收判据 |
|---|---|---|
| J1 | JSON-only | 全部契约模型样本 dump 结果经 `assert_json_clean` 通过 |
| J2 | extra=forbid | 注入未知字段 → 校验失败（契约冻结的程序化守卫） |
| J3 | 边界深拷贝隔离 | 构造 WorldState 后修改传入的原始 dict → WorldState 不受影响 |
| J4 | 快照隔离 | 两个不同 revision 的 Snapshot 互不影响；`restore_snapshot` 产物与运行中状态零别名（修改恢复产物不影响活状态） |
| J5 | 深冻结视图 | `freeze_view` 产物赋值抛错；嵌套层同样抛错 |
| J6 | 版本标记 | Snapshot 三层版本字段在场且默认值正确；篡改 `contract_schema_version` 后 restore 应报告不匹配（P1 至少给出校验函数，迁移行为属 P8） |
| J7 | Unicode/边界值 | 中文 intent/notes、空 dict、大整数、浮点极值 round-trip 无损 |

### 7.6 Import 边界（对 T01-T05 整体，G1）

| # | 场景 | 验收判据 |
|---|---|---|
| B1 | 静态扫描 | `src/engine_v2/core/` 全部 .py 无 §0.3 黑名单 import（扩展 `tests/test_engine_v2_skeleton.py` 的 AST 扫描口径） |
| B2 | 运行时扫描 | fresh import `src.engine_v2.core` 全部模块，`sys.modules` 增量不含黑名单 |
| B3 | 无网络可运行 | T06 全套用例在断网环境（不设置任何 API key 环境变量）通过 |

---

## 8. 显式非目标（P1 不做，契约已为其预留）

1. **Kernel 不含标准 RPG 字段**（Plan §10 强制约束）：无 HP/Inventory/Relationship 等内置组件、事件、字段；Spec §10.2 所列 Transform/Inventory/Health 等示例由 P9 官方模块注册为组件类型；
2. **不含 provider/model**：无 InferenceProfile、无模型名/provider 名字段（Spec §5.4/K8；trace 的 `llm_call` payload 仅冻结键名约定，§4.4）；
3. **不 import langgraph/langchain/openai**（§0.3 import 边界声明，G1）；
4. **不从 v1 GameState 复制 transient/presentation 混合结构**（Plan §10 强制约束）：v1 `player_percept`/`narrative_history`/`event_log`/`attribute_deltas` 等瞬态与呈现字段**不**进入 WorldState/RuntimeState——呈现归 ViewState（P10），过程记录归 Trace（§4.4），世界事实归组件；
5. **不实现 authority/validation/conflict/reducer 逻辑**（Plan P2-T01~T07 职责）：P1 只提供其数据底座（`authority_scope`、`authority_domain`、`priority_hint`、`base_revision`、`CommittedEffect.sequence`、`check_transaction_references` 纯函数）；
6. **不实现调度语义**（Plan P3）：RuntimeState 相关字段为占位；不实现 ActionRegistry 运行时与生命周期迁移逻辑（词表与状态枚举在场）；
7. **不实现持久化 IO / replay 执行 / branch**（Plan P8）：Snapshot 为纯数据信封，序列化函数无 IO；
8. **不定义 GameplayMode 合并语义**（Plan P4，Spec §25.3）；**不定义 Space domain 身份**（Plan P4，Spec §24）；**不定义 completion_condition 的条件语言**（Plan P3）；
9. **不创建** Spec §44 中属 P2 的 `authority.py`/`validation.py`/`conflicts.py`/`reducer.py`/`commands.py`。

---

## 9. v1 陷阱规避对照表（P0-T03 KBC → 本契约防线）

| v1 陷阱（P0-T03 报告 §4） | v2 契约防线 |
|---|---|
| **KBC-2** reducer `operator.add` 通道重复累加（action_intents ×2，好感度翻倍） | 每个 ProposedEffect 有全局 `effect_id`；事务内 `sequence` 唯一；不存在"整列表重复写入同一通道"的合并语义——reducer（P2）按 CommittedEffect 逐条确定性应用，重复 ID 可检测（§7.4 C7） |
| **KBC-4** `game_time` 的 `day` 键首回合丢失（部分 dict 覆写） | 日历时间是结构化世界数据（组件/world_variable），只能经**完整 payload** 的 effect 变更，schema 校验拒绝残缺结构（§4.2 D-6）；RuntimeState 只有单一 `logical_tick`，不存在可被部分覆写的复合时钟 |
| **KBC-6** event_log append-only 通道"压缩"只能追加摘要 | 过程记录归 TraceState（kind 化、带 ID 的结构化流，§4.4），状态容器内无日志通道；trace 生命周期管理（归档/摘要）属 P8，不污染状态 |
| **KBC-3** NPC dict 内坐标陈旧（双份位置数据源） | 组件数据唯一存放于 WorldState；任何视图（EntityView）从当前 revision 派生并携带 `revision` 标记，禁止持有跨 revision 的权威副本（§3.1） |
| **KBC-7** `player_action` None 被改写为 `{}` | 全契约 `extra="forbid"` + 严格 Optional 语义：缺省一律 `None`，空 dict 与 None 不可互换（§7.4 C1 用例口径） |
| **raw mutation 惯性**（P0-T01 §9 风险 1：`state_apply.py` 就地深改 dict） | frozen 模型 + 边界深拷贝 + 零公共写 API + reducer-only 预留（§3.5）；K2 由 P2 写屏障闭合 |
| **stale proposal**（P0-T01 §9 风险 2：NPC 基于静态快照并发决策，返回时世界已变） | `base_world_revision`/`observation_id`/`actor_state_revision`/`valid_until` 为 ActionProposal 一等字段（§5.1），提交前 revalidation（ACCEPT/REBASE/REPAIR/REJECT，Spec §9）是 P2 强制行为 |

---

## 10. 为后续 Phase 预留的接口清单（汇总）

| 后续能力 | Phase | P1 预留的数据承载 |
|---|---|---|
| Reducer-only 写屏障 | P2-T01 | frozen 容器、零公共写 API、`_with_*` 私有构造缝（§3.5） |
| Authority selector（component/field/domain/effect/entity tag，Spec §17.2） | P2-T02 | `ComponentSchema.authority_domain`、`EntityRecord.entity_class/tags`、`ProposedEffect.authority_scope`、`EffectTypeId`、`EntityTarget.field_path` |
| Effect validation / stale 判定 | P2-T04 | `base_revision`、`valid_until`、`EntityRef`、`check_transaction_references` |
| Conflict resolution | P2-T05 | `priority_hint`、`EffectTarget`（冲突检测的定位键） |
| Transaction 原子提交 + revision 递增 | P2-T06 | §5.6 全部不变量 |
| Cascade executor / cycle 诊断 | P2-T07/T08 | `CascadeContext`、`CauseRef`、TraceKind 通道 |
| Scheduler / 中断 / decision boundary | P3 | `RuntimeState.scheduler_queue`、`ActiveAction`（§23.4 全字段）、`ScheduledEvent` 占位 |
| Actor / Context / capability / observation | P4 | `ObservationId`、`actor_state_revision`、`ActorWakeup`、`EntityId` 即 actor 身份（§12.1） |
| ProjectIR / 模块注册 | P5 | `ComponentRegistry`、`ActionTypeId` 词表机制、`Snapshot.project_version/module_versions` |
| LLM Runtime 记录 | P6 | `TraceKind.LLM_CALL` payload 键名约定（§4.4） |
| Persistence / replay / branch | P8 | `Snapshot` 信封、三层版本标记、自包含 CommittedEffect/Transaction/DomainEvent、BackendStateRef 三声明 |
| 存档迁移 | P8 | `schema_version`/`contract_schema_version`/`snapshot_format_version` |

---

## 11. 章节 ↔ 权威出处对照（自检索引）

| 本文档章节 | 权威出处 |
|---|---|
| §0.1 schema 选型 | Spec §50（Spec A "包括 Pydantic/dataclass schema"）；migration-constraints §4.1 |
| §0.3 import 边界 | Plan §10 G1；Spec §47 Phase 1 验收；`src/engine_v2/README.md` §2 冻结规则 3 |
| §1 模块布局 | Spec §44；Plan §10 任务包表 |
| §2 ID/Revision | Spec §10.1（EntityId 四要求）、§9（revision 与异步字段）、§16.1、§21.3、§17.1（producer 名字）；Plan §10 T01、G1 "public IDs stable" |
| §3 Entity/Component | Spec §10.1/§10.2/§10.3、§17.2；Plan §10 T03 与强制约束（不含 RPG 字段） |
| §4 状态契约 | Spec §8.1–§8.5、§9、§23.1、§23.3、§30.2、§31.3、§22；ADR-003；Plan §10 T02 |
| §5 行动/效果/事件/事务 | Spec §11.3/§11.4、§23.4、§16.1/§16.2、§21.1/§21.2/§21.3、§20.1/§20.2、§9；ADR-001；Plan §10 T04、§22.2 |
| §6 序列化/快照 | Spec §30.1/§30.2/§30.5、§8.3；Plan §10 T05、强制约束（JSON round-trip） |
| §7 测试契约 | Plan §10 T06、§22.2 State 五类、§22.3 adversarial；Spec §47 Phase 1 验收 |
| §8 非目标 | Plan §10 强制约束；Spec §4 K8、§10.2、§8.5、§46 |
| §9 v1 陷阱规避 | P0-T03 §4（KBC-1~KBC-8）、§8；P0-T01 §4/§9 |

---

*文档完。任何对本契约 public 字段的修改必须经 Gate review（Plan §10）；P1-T07 独立 review（GLM）与人工冻结（Plan §36 第 4 条）在 G1 前完成。*
