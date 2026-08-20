# P2 Kernel Pipeline Design — Phase 2 Effect / Authority / Transaction Kernel 实现规范（Spec B）

- **任务**: P2-DESIGN（Phase 2 Kernel 管道架构设计，计划 §11/§36：QMax 任 Phase 2 架构设计者）
- **文档地位**: 等价于 Plan §11「Phase 2 — Effect / Authority / Transaction Kernel」的字段级/函数级实现规范。Q27 按本文档可"纯执行"实现 P2-T03/T08；QMax 实现 P2-T01/T02/T04/T05/T06/T07 时无需再做架构判断；GFlash 实现 P2-T09 对抗测试时无需再做场景裁剪。
- **分支**: `architecture-v2`
- **权威输入**:
  - `docs/plans/llmBasedSim_Engine_Architecture_v2_Spec.md`（下称 **Spec**）§4（K1/K2/K3/K6）、§16、§17、§18、§19、§20、§21、§22、§44
  - `docs/plans/llmBasedSim_Architecture_v2_Refactor_Development_Plan.md`（下称 **Plan**）§11（P2-T01~T09、必须测试 7 条、G2）、§7（并行纪律）、§22
  - `docs/v2/contracts/P1-core-data-contracts.md`（下称 **P1 设计**，已冻结）：§0（全局约定）、§3.5（reducer-only 三纪律）、§5（效果/事件/事务契约）、§10.1（**P2 义务登记：C2/C3/ID 种类校验**）
  - `docs/v2/reports/P1-T07-contract-review.md`（条件 C2/C3 原文与 §D 观察）
  - `docs/v2/gates/G1-gate-report.md`（M1 冻结裁定：13 个契约模块与 93 个公开导出冻结；Open Risks 1/2/3 归 P2）
  - `src/engine_v2/core/` 已冻结 13 个契约模块（commit `603535e` 基线）与 `tests/engine_v2/core/`（含 `test_transaction_references.py` 的 C7 检查器实现）
- **本任务边界**: 只定义 Phase 2 的**行为模块设计**（函数签名、算法、数据流、任务切分、测试口径）。不改变任何已冻结的 P1 public contract 字段/类型/序列化形态（G1 冻结裁定）；P2 全部产出为**新增**模块与测试，外加 §10 明确列出的三处既有测试文件机械修订（C2 义务授权范围内）。

> **Phase 编号口径**：沿用 P1 设计开头的约定——本文档一律使用 **Plan 编号**（P1–P11）。Spec §44 的 `core/` 文件清单中 `authority.py` / `validation.py` / `conflicts.py` / `reducer.py` 由本 Phase 创建，`commands.py` 本 Phase **不创建**（决策 D-P2-01，§13 非目标）。

---

## 0. 设计总决策清单

全部决策编号 `D-P2-xx`，正文引用；与 P1 决策（D-0~D-15）命名空间隔离。

| # | 决策 | 一句话结论 | 详见 |
|---|---|---|---|
| D-P2-01 | 模块落位 | 新增 6 个行为模块于 `src/engine_v2/core/`：`reducer.py`、`authority.py`、`validation.py`、`conflicts.py`、`transaction_executor.py`、`cascade.py`；Spec §44 的 `commands.py` 不创建（开发命令以 `origin=developer` 的普通 effect 走管道，命令面归 P8 devtools） | §1.2、§13 |
| D-P2-02 | 行为与契约分文件 | 事务装配/提交行为放**新文件** `transaction_executor.py`；已冻结的 `transaction.py` 保持纯数据契约，零改动 | §6.1 |
| D-P2-03 | 事务粒度 | 一个级联回合（round）的全部 accepted effects 组成**一个**事务；跨回合各自独立事务 | §6、§7.3 |
| D-P2-04 | 结构效果词表 | Kernel 定义 7 个 `core.*` **结构性** effect type（create/remove entity、set/remove component、set/remove world variable、set scenario）——这是状态机构词汇，不是 RPG 语义（无 HP/Inventory 取值）；语义型 effect type 一律经 handler 注册 | §2.1 |
| D-P2-05 | handler 扩展点 | `EffectHandlerRegistry` 承载语义 effect 的纯函数处理器；未注册 effect type → 校验期 `no_handler` 拒绝 + reducer 兜底抛错（Spec §20.2 "不静默推断语义"） | §2.3 |
| D-P2-06 | revision 递增位置 | reducer 在全部 effects 成功应用后将 `world_revision` 置为 `commit_revision`（== base+1）；执行器侧再以 `check_transaction_references` 做提交前终检 | §2.4、§6.2 |
| D-P2-07 | 写屏障三层防御 | (a) 静态 AST 审计（全仓、G2 口径）；(b) 运行时逃逸拦截（`install_write_barrier()` 类级包裹 `ContractModel` 的**四条**逃逸路径 `model_copy(update=...)`/`model_construct`/`__copy__`/`__deepcopy__`，**opt-in** 不自动安装）；(c) `guard()` 只读包装器交 producer/trigger。**不修改任何 P1 源文件** | §2.6 |
| D-P2-08 | authority 配置载体 | `AuthorityPolicy` 为 pydantic 契约模型，入口是 `model_validate(dict/JSON)`；**YAML 解析归 P5 content 层**（core import 边界只允许 stdlib+pydantic，不得引入 yaml 依赖） | §3.3 |
| D-P2-09 | authority 默认拒绝 | 无匹配规则一律 deny（closed-by-default）；**首条匹配规则拍板**（producer 在其 `allowed_writers` → allow，否则 deny），不做 fall-through | §3.3 |
| D-P2-10 | 校验两层语义 | 单 effect 校验失败 → 该 effect 被过滤（其余可继续）；事务装配后终检（`check_transaction_references` + reducer 应用）失败 → **整事务原子失败**（Plan 必须测试 3） | §4.1、§6.3 |
| D-P2-11 | 冲突锁与分组 | 冲突检测 = 锁集合相交 + 冲突图连通分量；默认策略链固定四策（authority priority → timestamp → producer priority → entity-level FIFO），默认解析器只产出 WINNER/REJECT，MERGE/DEFER/REPAIR 为 domain resolver 扩展位 | §5 |
| D-P2-12 | 事件发射映射 | 每个 CommittedEffect 发射**一个** DomainEvent：`event_type == effect_type`（1:1），`cause_ids = [CauseRef(EFFECT, effect_id)] + effect.cause_ids` | §6.4 |
| D-P2-13 | 级联深度语义 | 根事务 `depth=0`；由 depth=d 事件触发的提案在 depth=d+1 提交；`max_cascade_depth=8` 指**允许的最大触发深度**（depth 0..8 至多 9 个事务） | §7.1、§7.3 |
| D-P2-14 | 环路检测口径 | 环路 = 触发链上**冲突位置重访**：某触发提案的目标锁位置已出现在本 cascade 链祖先回合的已提交位置集中（HP变化→规则→又改HP 即此形态）；保守熔断，`location_revisit="allow"` 可退化为仅深度上限 | §7.5 |
| D-P2-15 | ID 种类校验 | P2 validation 以 `parse_id` 对 effect 全量 ID 做**种类+前缀**复检：拒绝错误前缀串与"错误种类的 typed ID 实例"（pydantic AfterValidator 只重建不拒绝，P1 §10.1 义务 3） | §4.4 |
| D-P2-16 | timestamp 策略约定 | 冲突 timestamp 策略读 `effect.metadata["producer_timestamp_ms"]`（int，P2 约定键）；**仅当组内全体成员均携带时**生效（最大者胜），否则弃权——权威序仍以 revision/到达序为准（P1 §0.2 铁律 3） | §5.4 |
| D-P2-17 | authority_scope 仅咨询 | `ProposedEffect.authority_scope` 不参与权限判定、不提升权限（K4：prompt/声明不能定义世界权限）；仅入 trace 供审计 | §3.7 |
| D-P2-18 | logical_tick 口径 | P2 管道不拥有时钟：`logical_tick` 一律可由调用方传入（缺省 None）；tick 推进归 P3 Scheduler（D-5/D-6 同源：revision 与 tick 解耦） | §6.2、§7.3 |
| D-P2-19 | re-export 与模块表同步 | 每个 P2 任务包交付时**增量更新** `core/__init__.py` 本模块导出块；P2-T01 负责同步更新**两处**独立的 13 模块清单——`tests/engine_v2/core/test_closeout.py::_CORE_SUBMODULE_NAMES` 与 `tests/engine_v2/core/test_import_boundary.py::CORE_SUBMODULES`（均 13 → 19）；closeout 的 `__all__` 并集机制与文件集合断言随之自动扩展 | §10.3 |
| D-P2-20 | INTERVENTION 因果引用 | `CauseRef(kind=INTERVENTION)` 的 `ref_id` 按 `TraceRecordId`（`trc_` 前缀）词法校验——开发干预在 trace 中以 `dev_intervention` 记录承载（Spec §22），无独立 ID 族 | §4.4 |

---

## 1. 管道总览与模块布局

### 1.1 K2 管道与数据流

Spec §4 K2 的强制路径在 P2 落地为如下单向数据流（括号为实现模块）：

```text
Producer（P3+ 的 policy/dynamics/dev；P2 以提案入参模拟）
  ↓  list[ProposedEffect]
[级联回合 round]（cascade.py: CascadeExecutor.run_round）
  ├─ Authority Check   （authority.py: check_authority，逐 effect）
  ├─ Validation        （validation.py: EffectValidator.validate_batch）
  ├─ Conflict Resolution（conflicts.py: detect_conflicts + DefaultConflictResolver）
  ├─ Transaction 装配  （transaction_executor.py: commit_transaction）
  │    ├─ 终检 check_transaction_references（validation.py，C2 晋升）
  │    ├─ Reducer 应用 （reducer.py: apply_transaction / apply_committed_effects）
  │    └─ emit DomainEvents（1:1，§6.4）
  ↓  events
同步触发器求值（cascade.py: CascadeTriggerRegistry）
  ↓  新提案（cause_ids 回指事件；depth+1；环路/深度熔断）
重复，直到无新提案或熔断
```

原子单元：**一个 round 的一个 Transaction**（D-P2-03）。全部决策点（authority/validation/conflict/transaction/event）产生 TraceRecord（§9 汇总表），trace 只追加（P1 §4.4 流不变量）。

### 1.2 文件清单（`src/engine_v2/core/` 新增 6 个）

| 文件 | 职责 | 主要公开类型/函数 | 归属任务包 |
|---|---|---|---|
| `reducer.py` | Reducer-only 变更机制（Spec §20.2）：结构效果词表、State mutation API、纯函数应用、handler 注册、写屏障（C3） | `apply_committed_effects`、`apply_transaction`、`EffectHandlerRegistry`、`WriteBarrier`、`install_write_barrier`、`write_barrier_exempt`、`guard`、`GuardedWorldState`、`state_*` 操作族、`STRUCTURAL_EFFECT_TYPES` | **P2-T01** |
| `authority.py` | Authority Contract（Spec §17）：selector、policy 求值、producer 注册 | `AuthoritySelector`、`AuthorityRule`、`AuthorityPolicy`、`AuthorityDecision`、`AuthorityVerdict`、`ProducerRegistry`、`ProducerInfo`、`check_authority`、`match_selector`、`KERNEL_STATE_DOMAINS` | **P2-T02（selector）/ P2-T03（求值）** |
| `validation.py` | Effect Validation（Spec §18）：固定阶段管道、ID 种类校验、`check_transaction_references` 晋升（C2） | `EffectValidator`、`ValidationContext`、`ValidationIssue`、`ValidationReport`、`check_transaction_references`、`check_effect_id_kinds`、`VALIDATION_ISSUE_KINDS` | **P2-T04** |
| `conflicts.py` | Conflict Resolution（Spec §19）：锁/分组检测、策略框架、默认四策 | `ConflictKey`、`ConflictGroup`、`ConflictAction`、`ConflictResolution`、`ConflictStrategy`、`DefaultConflictResolver`、`detect_conflicts`、`conflict_key`、四个默认策略类、`TIMESTAMP_METADATA_KEY` | **P2-T05** |
| `transaction_executor.py` | Transaction 装配与原子提交（Spec §20.1）+ 事件发射 | `commit_transaction`、`abort_transaction` | **P2-T06** |
| `cascade.py` | Event Cascade（Spec §21.3）：回合循环、触发器、深度/环路熔断与诊断 | `CascadeConfig`、`CascadeTrigger`、`CascadeTriggerRegistry`、`CascadeExecutor`、`CascadeResult`、`CycleDetector`、`DEFAULT_MAX_CASCADE_DEPTH` | **P2-T07（执行器）/ P2-T08（CycleDetector+诊断）** |

不创建：`commands.py`（D-P2-01，§13）。`clock.py` 仍归 P3（P1 设计 §1.1 注记不变）。

### 1.3 模块依赖图与 import 纪律

```text
（P1 冻结契约：ids/revision/components/entity/provenance/effects/actions/events/transaction/state/trace/serialization/snapshot）
        │
        ├─ reducer.py        （只依赖 P1 契约 + stdlib + pydantic）
        ├─ authority.py      （只依赖 P1 契约）
        ├─ validation.py ────→ reducer.py（handler 注册表存在性检查、结构 payload 模型）
        ├─ conflicts.py      （只依赖 P1 契约 + authority.py 的 AuthorityDecision 数据形状）
        ├─ transaction_executor.py ─→ reducer.py、validation.py（终检）、（events/transaction 契约）
        └─ cascade.py ───────→ transaction_executor.py、conflicts.py、authority.py、validation.py、reducer.py
```

依赖无环（箭头单向）。import 边界**继承 P1 设计 §0.3**：只允许 stdlib + pydantic + 同包 `src.engine_v2`；黑名单（provider SDK / v1 包 / 网络进程 IO）不变，`tests/engine_v2/core/test_import_boundary.py` 的 AST/运行时扫描自动覆盖新增模块（扫描面 = `CORE_DIR/*.py`）。

> **与 Spec §20.2 对齐**：reducer 不调用 LLM —— 由 import 边界（core 不得出现 llm/provider 依赖）+ §12 G2 静态核查双重保证；reducer 不静默推断语义 —— 未注册 effect type 一律报错（D-P2-05），无默认合并/插值行为，测试口径见 §11 类别 7。

### 1.4 与冻结 P1 契约的关系

1. **零源改动**：P2 任何任务包不得修改 13 个已冻结契约模块（`ids.py`…`snapshot.py`）的源文件。写屏障的运行时拦截以**类级包裹**（§2.6.2）而非源码修改实现。
2. **只读复用**：P2 复用 P1 的私有构造缝隙（`WorldState._with_world_revision/_with_entities/_with_world_variables/_with_scenario_state`、`EntityRecord._with_components`、`entity._build_entities`）——P1 设计 §3.5 纪律 3 明示这些缝隙"供测试与未来 P2 reducer 使用"。**缝隙仅限 `core/reducer.py` 内调用**（静态审计，§2.6.1）。
3. **既有测试的机械修订**（全部由义务/机制必然性授权，列入各任务包写入白名单；三个文件、四处改动）：
   - `tests/engine_v2/core/test_closeout.py`：`_CORE_SUBMODULE_NAMES` 13 → 19（P2-T01，D-P2-19）；
   - `tests/engine_v2/core/test_import_boundary.py`：本文件自带的 `CORE_SUBMODULES` 元组（第 40 行，与 closeout 相互独立）同步 13 → 19（P2-T01，D-P2-19）；
   - `tests/engine_v2/core/test_transaction_references.py`：删除本地函数副本、改 import core 实现（P2-T04，C2 义务原文"删除测试侧副本避免双源"）；
   - 上述文件中若出现 `model_construct` 等逃逸路径调用（现有 1 处：`TestDuplicatedEffectId`），包一层 `write_barrier_exempt()`（P2-T04 顺手完成，保证屏障武装态下全仓测试仍绿，§2.6.4）。

---

## 2. `reducer.py`（P2-T01）

> Reducer 是 authoritative state 的**唯一** mutation mechanism（Spec §20.2）。本模块同时承载 Plan P2-T01「Reducer-only write barrier / mutation API」与 P1 §10.1 条件 C3。

### 2.1 结构效果词表 `core.*`（D-P2-04）

Kernel 仅内置**结构性** effect type——改变世界所需的最小机构动词；不预置任何 RPG 语义取值（Plan §10 强制约束）。词表常量：

```python
STRUCTURAL_EFFECT_TYPES: Final[frozenset[EffectTypeId]] = frozenset({
    "core.create_entity", "core.remove_entity",
    "core.set_component", "core.remove_component",
    "core.set_world_variable", "core.remove_world_variable",
    "core.set_scenario_data",
})
```

每个结构效果的 target/payload/前置条件契约（payload pydantic 模型定义于 `reducer.py`，公开导出供 validation 与测试复用；全部 `extra="forbid"` 继承 `ContractModel`）：

| effect_type | target | payload 模型（键） | reducer 前置条件（违反 → `EffectApplicationError`） |
|---|---|---|---|
| `core.create_entity` | `EntityTarget(entity_id=新 ID)` | `CreateEntityPayload(entity_class: str\|None=None, tags: list[str]=[], components: dict[str, dict[str, JsonValue]]={})` | entity 尚不存在；`entity_id` 与 target 一致；`created_revision` 由 reducer 强制置为 `commit_revision`（payload 不得携带） |
| `core.remove_entity` | `EntityTarget(entity_id)` | `EmptyPayload({})` | entity 存在 |
| `core.set_component` | `EntityTarget(entity_id, component_type)` | payload 即**完整组件数据** dict（`dict[str, JsonValue]`） | entity 存在；若 ComponentRegistry 有 schema 则 `validate_payload` 通过（P1 D-8 校验点 (b)）。**整体替换**，无部分合并（KBC-4 防线） |
| `core.remove_component` | `EntityTarget(entity_id, component_type)` | `EmptyPayload({})` | entity 存在且组件已挂载（不存在 → 报错，显式拒绝空操作歧义） |
| `core.set_world_variable` | `StateDomainTarget(domain="world_variables")` | `SetWorldVariablePayload(key: str, value: JsonValue)` | 无（键不存在则为新增；存在则**整值替换**） |
| `core.remove_world_variable` | `StateDomainTarget(domain="world_variables")` | `RemoveWorldVariablePayload(key: str)` | 键存在 |
| `core.set_scenario_data` | `StateDomainTarget(domain="scenario")` | `SetScenarioDataPayload(scenario_id: str\|None, stage: str\|None, data: dict[str, JsonValue])` | 无（ScenarioState **整体替换**） |

`EmptyPayload` = `ContractModel` 空字段子类（`extra="forbid"` 使任何多余键非法）。`domain` 词表与 `KERNEL_STATE_DOMAINS` 见 §3.6。

### 2.2 State mutation API（纯函数 `state_*` 族）

7 个与结构效果一一对应的**纯函数**（输入 WorldState，输出新 WorldState；self 不变、零别名、整体替换语义）：

```python
def state_create_entity(state: WorldState, entity_id: EntityId, *,
                        entity_class: str | None = None, tags: Sequence[str] = (),
                        components: Mapping[ComponentTypeId, ComponentData] = {},  # 缺省空
                        created_revision: Revision) -> WorldState: ...
def state_remove_entity(state: WorldState, entity_id: EntityId) -> WorldState: ...
def state_set_component(state: WorldState, entity_id: EntityId,
                        component_type: ComponentTypeId, data: ComponentData) -> WorldState: ...
def state_remove_component(state: WorldState, entity_id: EntityId,
                           component_type: ComponentTypeId) -> WorldState: ...
def state_set_world_variable(state: WorldState, key: str, value: JsonValue) -> WorldState: ...
def state_remove_world_variable(state: WorldState, key: str) -> WorldState: ...
def state_set_scenario_state(state: WorldState, scenario: ScenarioState) -> WorldState: ...
```

- 违反结构前置条件（重复创建、删除不存在者、键缺失等）抛 `ReducerError`；
- 实现走 P1 私有缝隙（§1.4.2），产物经 `model_validate` 重建（P1 纪律 2 入口深拷贝）；
- 这组函数是**模块处理器**（§2.3 handler，P5+ 语义模块）唯一可用的状态变更 API；在 `src/engine_v2` 内其调用方静态审计白名单 = `core/reducer.py`（P2 阶段无其他 handler 消费方）。

### 2.3 `EffectHandlerRegistry`（D-P2-05）

```python
EffectHandler = Callable[[WorldState, ProposedEffect], WorldState]   # 纯函数协议

class EffectHandlerRegistry:
    def __init__(self) -> None: ...          # 预注册全部结构效果（§2.1 内置 handler）
    def register(self, effect_type: EffectTypeId, handler: EffectHandler) -> None:
        """同类型重复注册：同一 handler 幂等；不同 handler → HandlerConflictError(ValueError)。"""
    def resolve(self, effect_type: EffectTypeId) -> EffectHandler | None: ...
    def has(self, effect_type: EffectTypeId) -> bool: ...
    def effect_types(self) -> tuple[EffectTypeId, ...]: ...   # 注册序，确定性
```

- 结构效果的内置 handler 由 §2.2 `state_*` 函数派生（target/payload → 参数映射），注册于构造期，**不可被覆盖**（重复注册不同 handler 抛错）；
- handler 纪律（注册方契约，P5+ 模块遵守，P2 测试以样例 handler 固化）：纯函数、不调用 LLM/IO、不得绕过 `state_*` API 直接构造 WorldState 字段、不得静默推断 payload 之外的语义；
- 默认实例：`default_handler_registry() -> EffectHandlerRegistry`（每次新建，避免跨测试串扰）。

### 2.4 应用纯函数（P2 唯一的状态变更公共路径）

```python
def apply_committed_effects(world_state: WorldState,
                            committed_effects: Sequence[CommittedEffect], *,
                            component_registry: ComponentRegistry | None = None,
                            handlers: EffectHandlerRegistry | None = None) -> WorldState: ...

def apply_transaction(state: WorldState, txn: Transaction, *,
                      component_registry: ComponentRegistry | None = None,
                      handlers: EffectHandlerRegistry | None = None) -> WorldState: ...
```

`apply_transaction` = 薄封装：要求 `txn.status is COMMITTED`（否则 `ReducerError`），委托 `apply_committed_effects(state, txn.effects, ...)`。它是 P1 设计 §3.5 纪律 3 预告的 `apply_transaction(state, txn) -> WorldState` 唯一公共路径。

`apply_committed_effects` 步骤（确定性）：

1. 空列表 → 原样返回（文档化；事务路径永不传空——P1 §5.6 不变量 1 已保证 COMMITTED effects 非空）。
2. 防御性复检：全体 `CommittedEffect` 共享同一 `transaction_id` 与 `commit_revision`；`commit_revision == world_state.world_revision.next()`；`sequence` 恰为 `0..n-1`（与 Transaction 构造期不变量重复校验——纵深防御，对齐 C7 检查器的复检哲学）。任一违反 → `ReducerError`。
3. **批量应用（O(状态体积) 而非 O(n×状态)）**：内部构造 kernel 私有暂存结构 `_WorkingWorld`（持有 `entities: dict`、`world_variables: dict`、`scenario_state` 的**工作副本**，仅 reducer 内部可见，不导出），按 `sequence` 顺序逐条 dispatch：结构效果 → 内置 handler 作用于暂存；语义效果 → `handlers.resolve(effect_type)`，未注册 → `ReducerError(f"未注册 effect_type: ...")`（不推断）。handler/结构前置条件错误统一包装为 `EffectApplicationError(sequence=<i>, effect_id=<id>)`。
   - 事务内**顺序依赖合法**：同事务先 `core.create_entity` 后对同一 entity `core.set_component` 可成功（暂存上可见）——对抗测试类别 3 使用。
4. 暂存组装为新 WorldState（`_build_entities` 拒绝重复 ID；键一致性由 P1 model_validator 复检），最后经 `_with_world_revision(commit_revision)` 置 revision（D-P2-06）。
5. 全程纯函数：任何一步抛异常，输入 `world_state` 不受影响（原子性的函数式基础，§6.3）。

`component_registry` 传入时，`core.set_component`/`core.create_entity`（其 components 逐项）在应用时执行 `validate_payload`（P1 D-8 校验点 (b) 的兑现）。

### 2.5 异常族

```python
class ReducerError(ValueError): ...
class EffectApplicationError(ReducerError):
    """携带 sequence: int 与 effect_id: str 属性。"""
class HandlerConflictError(ValueError): ...
class WriteBarrierError(RuntimeError): ...
```

### 2.6 写屏障（P1 §10.1 条件 C3 闭合）

P1-T07 实测：`model_copy(update=...)` / `model_construct(...)` 绕过全部校验器与 frozen 语义（可把 ABORTED 事务 copy-update 出 `commit_revision`）。三层防御（D-P2-07）：

#### 2.6.1 层一：静态 AST 审计（全仓、G2 口径）

新增测试 `tests/engine_v2/kernel/test_write_barrier_static.py`：对 `src/engine_v2/**/*.py` 做 AST 扫描，禁止以下形态出现在**白名单之外**的文件：

| 禁止形态 | 白名单（允许出现的文件） |
|---|---|
| `model_copy(` 调用且带 `update=` 关键字 | `core/reducer.py`（P1 基线全仓对 `model_copy`/`model_construct` 零使用——白名单为 P2 reducer 保守预留） |
| `.model_construct(` 调用 | `core/reducer.py` |
| 对 `_with_world_revision/_with_entities/_with_world_variables/_with_scenario_state/_with_components/_build_entities` 的调用 | `core/state.py`、`core/entity.py`（定义处）、`core/reducer.py` |
| 对 WorldState/EntityRecord/ScenarioState 实例的属性赋值（`ast.Attribute` store 于上述类型注解变量） | 无（全禁） |
| `__dict__` 直写（`obj.__dict__[...] =` / `setattr(obj, ...)` 于契约模型） | 无（全禁） |

该扫描是 Plan G2「Runtime Producer 中不存在直接 authoritative state mutation」的机械化证据；扫描器实现为测试内纯函数（可复用于未来 `devtools`）。P2 阶段 `src/engine_v2` 除 core 外皆为空骨架，扫描面随 Phase 自然扩展。

#### 2.6.2 层二：运行时逃逸拦截（opt-in）

```python
def install_write_barrier() -> None: ...     # 幂等
def uninstall_write_barrier() -> None: ...   # 恢复原方法（测试夹具用）
def write_barrier_installed() -> bool: ...

class WriteBarrier:  # 上下文管理器：内部置位"reducer 活动"令牌（threading.local）
    ...

@contextmanager
def write_barrier_exempt() -> Iterator[None]:
    """显式豁免窗口：仅供测试构造病态数据与诊断；被静态审计视为受控例外（测试目录允许）。"""
```

机制：`install_write_barrier()` 在**类级**包裹 `ContractModel` 的**四条逃逸路径**：`model_copy`、`model_construct`、`__copy__`、`__deepcopy__`。逐一包裹是实测结论而非保守冗余：pydantic 2.13 的 `__copy__`/`__deepcopy__` 经 `cls.__new__` + `_object_setattr` 独立实现，**不经过** `model_copy`，只包 `model_copy` 会漏掉 `copy.copy()`/`copy.deepcopy()`。22 个契约模型全部继承 `ContractModel`，在基类一处覆盖四个方法即全模型生效。包裹层检查线程局部令牌：令牌置位（`WriteBarrier` 活动或 `write_barrier_exempt()` 内）→ 委托原方法；否则抛 `WriteBarrierError`。`apply_committed_effects`/`apply_transaction` 内部在 `WriteBarrier()` 上下文内运行（reducer 自身合法使用不受阻）。

**为何 opt-in 而非 import 自动安装**：pytest 单进程内若自动武装，P1 既有测试（`test_transaction_references.py` 的 `model_construct` 用例）将跨文件受染。武装时机由 kernel 运行时入口（`CascadeExecutor.__init__` 调用 `install_write_barrier()`，幂等）与 P2 测试夹具（`tests/engine_v2/kernel/conftest.py` autouse 夹具：每用例前 install、后 uninstall）控制；卸载后全局状态复原，P1 测试零影响。

#### 2.6.3 层三：`guard()` 只读包装器（防绕过包装器）

```python
def guard(state: WorldState) -> "GuardedWorldState": ...

class GuardedWorldState:
    """交 producer/trigger 的只读运行时门面：委托 WorldState 的 4 个只读门面 +
    model_dump/model_dump_json（序列化出口）；对 model_copy/model_construct/
    copy.copy/copy.deepcopy/属性赋值/私有缝隙访问一律抛 WriteBarrierError。
    不继承 BaseModel，不是契约模型，不参与 round-trip。"""
```

级联触发器（§7.2）与 P2-T09 对抗用例接收 `GuardedWorldState`——即使全局拦截未武装，producer 侧也拿不到任何写路径（K2 的运行时兜底）。

#### 2.6.4 与既有测试的协调

`test_transaction_references.py` 的 `model_construct` 用例在 P2-T04 迁移时（§4.5）包入 `write_barrier_exempt()`——无论屏障是否武装、无论测试执行顺序，全仓保持绿。

---

## 3. `authority.py`（P2-T02 / P2-T03）

### 3.1 `AuthoritySelector`（Spec §17.2 五维 + entity class）

```python
class AuthoritySelector(ContractModel):
    component_type: ComponentTypeId | None = None
    field_path: str | None = None            # component_type 之下的字段级细化（单段标识符，§4.6）
    domain: StateDomainId | None = None      # domain tag 维度
    effect_type: EffectTypeId | None = None
    entity_class: str | None = None          # Spec §17.2 "entity class/tag" 之 class
    entity_tags: list[str] = Field(default_factory=list)   # Spec §17.2 之 tag（全部命中 = AND 语义）
```

匹配语义：**未指定的维度 = 通配**；指定维度全部命中才算匹配。全空 selector 匹配一切效果——合法但有风险，policy 侧通常配合低 priority 使用（文档化警示）。

### 3.2 `match_selector`（P2-T02 核心纯函数）

```python
def match_selector(selector: AuthoritySelector, effect: ProposedEffect,
                   state: WorldState | None = None,
                   component_registry: ComponentRegistry | None = None) -> bool: ...
```

逐维判定（顺序固定，短路）：

1. `effect_type`：与 `effect.effect_type` 全等（不做前缀/层级匹配——确定性优先）。
2. target 分派：
   - `EntityTarget`：
     - `component_type` 维：与 `target.component_type` 全等；selector 指定而 effect 未指定 → 不匹配。
     - `field_path` 维：全等；selector 指定而 effect `field_path is None` → 不匹配。
     - `domain` 维：经 `component_registry` 查 `target.component_type` 的 `ComponentSchema.authority_domain`（P1 §3.3 预留字段）与之全等；组件未注册或无 `authority_domain` → 不匹配（域不可判定 ≠ 默认放行）。
     - `entity_class`/`entity_tags` 维：需要 `state`——查 `state.entities[target.entity_id]` 的 `EntityRecord.entity_class`/`tags`（P1 §3.1 预留字段）；`state is None` 或 entity 不存在 → **不匹配**（实体维度不可判定即不放行）；`entity_tags` 为 AND 语义（全部在 record.tags 中）。
   - `StateDomainTarget`：`domain` 维与 `target.domain` 全等；`component_type`/`field_path`/`entity_*` 维若被 selector 指定 → 不匹配（维度与目标种类不相容）。

### 3.3 `AuthorityPolicy` 与求值（P2-T03；D-P2-08/D-P2-09）

```python
class AuthorityRule(ContractModel):
    selector: AuthoritySelector
    allowed_writers: list[ProducerId]        # ≥1，model_validator 强制
    priority: int = 0                        # 越大越先求值

class AuthorityPolicy(ContractModel):
    rules: list[AuthorityRule] = Field(default_factory=list)
    description: str = ""
```

- **配置入口**：`AuthorityPolicy.model_validate(<dict/JSON>)`，与 Spec §17.1 YAML 示例同构（`authority: {<selector 描述>: {allowed_writers: [...]}}` 由 P5 content 层映射为本模型的 rules 列表；core 不引入 yaml 依赖——D-P2-08）。
- **求值序（确定性）**：rules 按 `(priority 降序, specificity 降序, 注册序升序)` 稳定排序；`specificity` = selector 指定维度计数（六个维度各计 1，`entity_tags` 非空计 1）。
- **拍板规则**：顺序遍历，**首条** `match_selector` 命中的规则拍板——`effect.source ∈ rule.allowed_writers` → allow，否则 deny；**不 fall-through**（被一条显式规则命中后不再看后续规则，语义可解释、无叠加歧义）。
- **无匹配 → deny**（closed-by-default；K3/K4：写权限只能由 engine authority system 显式授予）。

### 3.4 `ProducerRegistry`

```python
@dataclass(frozen=True)
class ProducerInfo:
    producer_id: ProducerId
    origin: OriginKind                       # P1 provenance.py 词表
    priority: int = 0                        # 冲突解析 producer priority 策略的输入（§5.4）
    description: str = ""

class ProducerRegistry:
    def register(self, info: ProducerInfo) -> None:
        """注册时校验 ProducerId 词法（PRODUCER_ID_PATTERN）；重复注册：
        同 info 幂等，冲突 → ProducerConflictError(ValueError)。"""
    def get(self, producer_id: ProducerId) -> ProducerInfo | None: ...
    def origin_of(self, producer_id: ProducerId, default: OriginKind = OriginKind.SYSTEM) -> OriginKind: ...
    def priority_of(self, producer_id: ProducerId, default: int = 0) -> int: ...
```

P1 §2.2「producer 注册表落位属 Plan P2」即本类。注册表是运行时对象（非契约模型，不进 round-trip），与 `ComponentRegistry` 同款纪律。

### 3.5 `check_authority`（P2-T03 签名）

```python
class AuthorityVerdict(str, Enum):
    ALLOW = "allow"      # trace decision 词表（P1 DECISION_PAYLOAD_KEYS 的 decision 值）
    DENY = "deny"

@dataclass(frozen=True)
class AuthorityDecision:
    effect_id: EffectId
    producer: ProducerId
    verdict: AuthorityVerdict
    reason_code: str            # "rule_allow" | "rule_deny" | "no_matching_rule"
    matched_rule_index: int | None = None    # 排序后 rules 列表中的下标（可解释性）
    rule_priority: int | None = None         # 冲突解析策略 1 的输入（§5.4）
    selector: AuthoritySelector | None = None

def check_authority(effect: ProposedEffect, policy: AuthorityPolicy,
                    state: WorldState | None = None, *,
                    component_registry: ComponentRegistry | None = None) -> AuthorityDecision: ...
```

纯函数；deny 不抛异常（过滤语义在管道层，§7.3）。

### 3.6 `KERNEL_STATE_DOMAINS` 与 domain 词表

P1 §5.3 明示 StateDomainId「词表由 P2 authority 配置声明」。Kernel 声明与 WorldState 字段对应的两个内置域：

```python
KERNEL_STATE_DOMAINS: Final[frozenset[StateDomainId]] = frozenset({"world_variables", "scenario"})
```

validation（§4.3 阶段 3）拒绝 `KERNEL_STATE_DOMAINS` 之外的 domain（未来扩展经 Gate review 追加本常量——public contract 变更纪律）。实体相关变更永远经 `EntityTarget`，不存在第三个实体域。

### 3.7 `authority_scope` 仅咨询（D-P2-17）

`ProposedEffect.authority_scope` **不参与** `check_authority` 判定（K4：声明/prompt 不能定义世界权限）。该字段仅随 `proposed_effect` trace 记录原样入档供审计。

---

## 4. `validation.py`（P2-T04）

### 4.1 两层校验语义（D-P2-10）

| 层 | 时机 | 失败后果 | 对应 Plan 必须测试 |
|---|---|---|---|
| L1 单 effect 校验 | round 内、冲突解析前 | 该 effect 被过滤（trace `validation_decision: fail`），其余 effect 继续 | — |
| L2 事务终检 | 事务装配后、reducer 应用前 | **整事务原子失败**（ABORTED，revision 不动） | 必须测试 3 |

L2 由 `check_transaction_references`（C2 晋升，§4.5）+ reducer 应用异常（§6.3）构成——L1 与 L2 之间的状态变化（级联多回合、外部装配批次）由 L2 兜底。

### 4.2 数据形状

```python
@dataclass(frozen=True)
class ValidationContext:
    state: WorldState
    component_registry: ComponentRegistry | None = None
    handlers: EffectHandlerRegistry | None = None      # None → 跳过 no_handler 阶段（纯数据校验场景）

@dataclass(frozen=True)
class ValidationIssue:
    kind: str          # VALIDATION_ISSUE_KINDS 词表
    effect_id: str
    detail: str
    def to_trace_str(self) -> str: ...   # "kind:effect_id:detail"（与 C7 报告串同构）

@dataclass(frozen=True)
class ValidationReport:
    accepted: tuple[ProposedEffect, ...]
    issues: tuple[ValidationIssue, ...]
    def issues_for(self, effect_id: str) -> tuple[ValidationIssue, ...]: ...
    @property
    def ok(self) -> bool: ...
```

`VALIDATION_ISSUE_KINDS`（冻结词表；其中 `missing_entity`/`stale_revision`/`duplicated_effect_id` 与 C7 检查器逐字对齐）：

```text
bad_id_kind, bad_type_id, bad_payload, bad_field_path,
missing_entity, missing_component,
stale_revision, future_base_revision,
unknown_domain, no_handler, precondition_failed, duplicated_effect_id
```

### 4.3 固定阶段管道（`EffectValidator`）

```python
class EffectValidator:
    def __init__(self) -> None: ...      # 固定管道，无配置（确定性；扩展走 P5+ Gate）
    def validate(self, effect: ProposedEffect, ctx: ValidationContext) -> tuple[ValidationIssue, ...]: ...
    def validate_batch(self, effects: Sequence[ProposedEffect], ctx: ValidationContext) -> ValidationReport: ...
```

阶段按固定顺序执行（前序阶段不短路后续——一次性收齐全部问题，trace 可解释性最大化）：

| # | 阶段 | 检查内容 | issue kind |
|---|---|---|---|
| 1 | ID 种类与前缀（D-P2-15） | §4.4 全量 ID 复检 | `bad_id_kind` |
| 2 | 类型标识符词法 | `effect_type`（parse_effect_type_id）；StateDomainTarget 的 `domain`（parse_state_domain_id） | `bad_type_id` |
| 3 | domain 词表与 payload schema | domain ∈ KERNEL_STATE_DOMAINS（否则 `unknown_domain`）；结构效果 payload 按 §2.1 模型校验；`core.set_component` 的 payload 经 ComponentRegistry.validate_payload（有 schema 时）；语义效果 payload 由 handler 约定，本阶段不查 | `unknown_domain`、`bad_payload` |
| 4 | 实体存在性 | EntityTarget.entity_id 存在（`ctx.state.has_entity`）；`core.remove_component` 额外要求组件已挂载 | `missing_entity`、`missing_component` |
| 5 | field_path 合法性 | §4.6 规则 | `bad_field_path` |
| 6 | 陈旧性 | `is_stale(effect.base_revision, ctx.state.world_revision)` → `stale_revision`（单向语义与 C7 一致）；`base_revision > current` → `future_base_revision`（未来版本不存在，确定性管道不可接受） | `stale_revision`、`future_base_revision` |
| 7 | 结构前置条件 + handler 存在性 | 结构效果按 §2.1 前置条件表做**数据级**预判（如 create 目标已存在、remove 目标不存在——与 reducer 同规则，提前过滤）；`ctx.handlers` 非 None 且 effect_type 未注册 → `no_handler`（D-P2-05） | `precondition_failed`、`no_handler` |

`validate_batch` = 逐 effect `validate` + **批级** `duplicated_effect_id` 检查（同批同 ID 的全部副本被拒——KBC-2 防线；与 Transaction 构造期不变量互为纵深防御）。

### 4.4 ID 种类与前缀校验（P1 §10.1 义务 3；D-P2-15/D-P2-20）

背景：typed ID 的 pydantic 路径（`AfterValidator` 重建）**不校验前缀词法**——`EffectId` 实例或错误前缀串落入 `EntityId` 字段会被静默重建（P1-T07 §D.2 实测）。`parse_id` 已备，本阶段复用：

```python
def check_effect_id_kinds(effect: ProposedEffect) -> tuple[str, ...]:
    """纯函数；问题串格式 'bad_id_kind:<field>:expected=<kind> got=<kind|lexErr>:value=<v>'。"""
```

期望种类表（`parse_id` 返回 kind 必须全等）：

| 字段 | 期望 kind | 备注 |
|---|---|---|
| `effect_id` | `EffectId` | |
| `source` | `ProducerId` | 名字型；`PRODUCER_ID_PATTERN` 词法 |
| `target.entity_id`（EntityTarget） | `EntityId` | 跨种类实例（如 EffectId 值）在此被拒 |
| `target.component_type` | `ComponentTypeId` 词法 | `parse_component_type_id` |
| `target.domain`（StateDomainTarget） | `StateDomainId` 词法 | `parse_state_domain_id` |
| `effect_type` | `EffectTypeId` 词法 | `parse_effect_type_id` |
| `cause_ids[*].ref_id` | 按 `CauseKind`：EVENT→`EventId`、ACTION→`ActionInstanceId`、EFFECT→`EffectId`、PROPOSAL→`ActionInstanceId`、INTERVENTION→`TraceRecordId`（D-P2-20） | |

`parse_id` 对错误种类 typed ID 实例同样有效：`EntityId` 字段里的 `EffectId("eff_...")` 值以 `eff_` 开头 → `parse_id` 判为 EffectId ≠ 期望 EntityId → 拒绝。种类与值前缀**双重**不一致时以 parse 结果为准报告。

### 4.5 `check_transaction_references` 晋升（P1 §10.1 义务 C2）

**逐字迁移**，签名与语义零变化：

1. `validation.py` 新增：
   ```python
   TRANSACTION_REFERENCE_ISSUE_KINDS: Final[tuple[str, ...]] = (
       "missing_entity", "stale_revision", "duplicated_effect_id")
   def check_transaction_references(state: WorldState, txn: Transaction) -> tuple[str, ...]: ...
   ```
   实现体从 `tests/engine_v2/core/test_transaction_references.py` **逐字移入**（含问题串格式 `kind:effect_id:详情`、单向 stale 语义、ABORTED 空转、state_domain 分支不查、只报告不处置）；docstring 去除"待晋升"表述，补"由 P2-T04 按 C2 晋升"溯源行。
2. `tests/engine_v2/core/test_transaction_references.py`：删除本地函数与 `ISSUE_KINDS` 定义，改为 `from src.engine_v2.core.validation import check_transaction_references, TRANSACTION_REFERENCE_ISSUE_KINDS`；15 例测试断言**逐条保留**（验收口径不变，只换被测对象来源）；`model_construct` 用例包 `write_barrier_exempt()`（§2.6.4）。
3. `core/__init__.py` re-export 两个名称（validation 块，D-P2-19）。
4. 接线：`transaction_executor.commit_transaction` 在装配后调用本函数（§6.2 步骤 6，L2 终检）——兑现 P1 设计 §10 预留表「Effect validation / stale 判定（P2-T04）依赖 check_transaction_references」。

### 4.6 `field_path` 规则

- 词法：单段标识符 `[a-z][a-z0-9_]*`（P2 只支持单层字段名；嵌套路径语法归 P5 内容 DSL）；
- 语义：`target.field_path` 非 None → 其 `component_type` 必须已注册且 `payload_model` 非 None（P1 §3.2「field_path 仅供 schema 已注册的组件使用」），且字段名 ∈ `payload_model.model_fields`；三条任一不满足 → `bad_field_path`；
- Kernel 结构效果**不使用** field_path（结构变更一律整体替换）；field_path 效果由模块 handler（P5+）消费。

---

## 5. `conflicts.py`（P2-T05）

### 5.1 `ConflictKey` 与锁推导

```python
@dataclass(frozen=True)
class ConflictKey:           # 可哈希；规范化为 tuple 参与集合运算
    kind: str                # "entity" | "domain"
    entity_id: EntityId | None = None
    component_type: ComponentTypeId | None = None   # None = 整实体级锁
    field_path: str | None = None                   # None = 整组件级锁
    domain: StateDomainId | None = None

def conflict_key(effect: ProposedEffect) -> ConflictKey: ...
def effect_locks(effect: ProposedEffect) -> frozenset[ConflictKey]: ...
```

锁规则：

| effect | 锁集合 |
|---|---|
| `EntityTarget`（无 component_type） | `{(entity, None, None)}` 整实体锁 |
| `EntityTarget`（有 component_type，无 field_path） | `{(entity, ct, None)}` 整组件锁 |
| `EntityTarget`（有 field_path） | `{(entity, ct, fp)}` 字段锁 |
| `StateDomainTarget` | `{(domain,)}` 域锁（域级粗粒度，保守；域内键级细化需要 payload 语义推断——kernel 不做） |
| `core.create_entity` / `core.remove_entity` | **整实体锁** `{(entity, None, None)}`（结构动词升级锁级别：创建/删除与同实体任何变更冲突） |

相交判定（`conflicts_with(a, b)`）：同 kind 且——entity 类：`entity_id` 相等，`component_type` 相等或任一为 None，且 `field_path` 相等或任一为 None；domain 类：`domain` 相等。

### 5.2 `detect_conflicts`（签名按任务包）

```python
@dataclass(frozen=True)
class ConflictGroup:
    effects: tuple[ProposedEffect, ...]      # ≥2，按到达序
    keys: tuple[ConflictKey, ...]            # 组内出现过的冲突键（可解释性）

def detect_conflicts(effects: Sequence[ProposedEffect]) -> list[ConflictGroup]: ...
```

算法：以 effects 为顶点、`conflicts_with` 为边建冲突图，取**连通分量**（size ≥ 2 即 ConflictGroup；BFS/并查集，确定性：按到达序遍历）。连通分量口径保证"A 与 B 冲突、B 与 C 冲突"时 A/B/C 同组一次性解析。返回按组内最小到达序排序。复杂度 O(n²) 锁比较——MVP 可接受（P1-T07 §D.6 同款性能注记；P3+ 若有性能诉求可换索引，不改签名）。

### 5.3 策略协议与解析上下文

```python
class ConflictAction(str, Enum):     # Spec §19 五种裁决
    WINNER = "winner"; MERGE = "merge"; DEFER = "defer"; REJECT = "reject"; REPAIR = "repair"

@dataclass(frozen=True)
class ResolutionContext:
    arrival: Mapping[EffectId, int]                      # round 内到达序（唯一权威序）
    authority_decisions: Mapping[EffectId, AuthorityDecision] | None = None
    producer_registry: ProducerRegistry | None = None

class ConflictStrategy(Protocol):
    name: str
    def resolve(self, group: ConflictGroup, ctx: ResolutionContext) -> ConflictResolution | None:
        """None = 弃权，交给下一策略。必须纯函数。"""

@dataclass(frozen=True)
class ConflictResolution:
    action: ConflictAction
    strategy: str                        # 拍板策略名（trace 可解释性）
    accepted: tuple[EffectId, ...]       # WINNER → 唯一胜出者；REJECT → 空
    dropped: tuple[EffectId, ...]
    reason: str
```

`DefaultConflictResolver(strategies=(...))`：顺序求策略，首个非 None 拍板；全部弃权（理论不可达——FIFO 永远可决）→ 保守裁决 REJECT 全组。

### 5.4 默认四策（固定顺序；Spec §19 "Resolver MAY use" 的确定性具体化）

| 序 | 策略类 | 输入 | 判定 | 弃权条件 |
|---|---|---|---|---|
| 1 | `AuthorityPriorityStrategy` | `ctx.authority_decisions` | 组内 `rule_priority` 最大者胜（authority 规则越具体/越高优先级，裁决权越强） | 无 decisions，或并列最大值 ≥2 |
| 2 | `TimestampStrategy`（D-P2-16） | `effect.metadata[TIMESTAMP_METADATA_KEY]`（`"producer_timestamp_ms"`，int） | **全体成员均携带**时，最大者胜（last-writer-wins）；并列 → 弃权 | 任一成员缺失键，或并列 |
| 3 | `ProducerPriorityStrategy` | `ctx.producer_registry.priority_of(source)`；并列时比 `effect.priority_hint`（None 视为 0） | 有效优先级最大者胜 | 无 registry，或并列（含 hint） |
| 4 | `EntityFifoStrategy` | `ctx.arrival` | 到达序**最小**者胜（先来先赢；确定性兜底，永不弃权） | 永不 |

落选 effects 全部进入 `dropped`（trace `conflict_resolution` 记录）。`TIMESTAMP_METADATA_KEY: Final = "producer_timestamp_ms"`——墙钟仅诊断（P1 §0.2 铁律 3），此策略仅作启发式平局破解，权威序始终是 revision + 到达序。

```python
DEFAULT_STRATEGIES: Final[tuple[ConflictStrategy, ...]] = (
    AuthorityPriorityStrategy(), TimestampStrategy(),
    ProducerPriorityStrategy(), EntityFifoStrategy(),
)   # 顺序即求值序（§5.3 DefaultConflictResolver 的缺省参数）
```

### 5.5 MERGE / DEFER / REPAIR 扩展位

默认解析器**只产出 WINNER/REJECT**（merge/repair 需要域语义，defer 需要调度语义——均属 domain-specific resolver，Spec §19 末条）：

```python
class DefaultConflictResolver:
    def __init__(self, strategies: Sequence[ConflictStrategy] = DEFAULT_STRATEGIES) -> None: ...
DomainResolverFactory = Callable[[ConflictGroup, ResolutionContext], ConflictStrategy | None]
# cascade.py 的依赖注入点：按 domain/component_type 选择性挂域解析器（P5+ 模块提供；P2 不内置任何域解析器）
```

DEFER 的管道语义（若域解析器产出）：被 defer 的 effects 作为**下一回合提案**重新进入级联（保留原 cause_ids、原到达序不变），由深度上限（§7.1）兜底防无限 defer。P2 测试以桩策略覆盖 DEFER 路径的机制正确性（不引入真实域语义）。

---

## 6. `transaction_executor.py`（P2-T06）

### 6.1 分文件决策（D-P2-02）

`transaction.py` 是冻结的数据契约（G1：public 字段/不变量冻结）；事务**装配与提交行为**放新文件 `transaction_executor.py`，对 `transaction.py` 零改动——与 P1「契约与行为分离」的同款纪律（数据在 contract，行为在 P2）。

### 6.2 `commit_transaction`（签名按任务包）

```python
def commit_transaction(base_state: WorldState,
                       accepted_effects: Sequence[ProposedEffect],
                       tx_id: TransactionId,
                       producer: Provenance, *,
                       logical_tick: int | None = None,          # D-P2-18
                       cascade: CascadeContext | None = None,
                       component_registry: ComponentRegistry | None = None,
                       handlers: EffectHandlerRegistry | None = None,
                       producer_registry: ProducerRegistry | None = None,
                       ) -> tuple[WorldState, Transaction, list[DomainEvent]]: ...
```

步骤（全部确定性、无 IO、无 LLM；线性实现，Transaction 只构造一次）：

1. **非空守卫**：`accepted_effects` 为空 → 抛 `ValueError`（空事务不消耗 revision，P1 §5.6 不变量 1 的行为侧镜像）。
2. `base_revision = base_state.world_revision`；`commit_revision = base_revision.next()`（Spec §9：恰 +1）。
3. **事件 ID 预分配**：`event_ids = [new_event_id() for _ in accepted_effects]`（数量在此固定，事件本体在步骤 8 组装——避免事务构造后再回填 frozen 字段）。
4. 装配 `CommittedEffect` 列表：`sequence` = 下标（到达序），`transaction_id=tx_id`，`commit_revision` 共享。
5. 构造 COMMITTED `Transaction`（携带 `event_ids`、`cascade`、`logical_tick`、`provenance=producer`、`base_revision`、`commit_revision`；P1 构造期不变量自动生效）。
6. **L2 终检**（D-P2-10）：`issues = check_transaction_references(base_state, txn)`；非空 → 走 §6.5 abort 路径（`abort_reason="reference_check_failed: " + "; ".join(issues)`），返回 `(base_state, aborted_txn, [])`。
7. **reducer 应用**：`new_state = apply_transaction(base_state, txn, component_registry=..., handlers=...)`；`ReducerError`/`EffectApplicationError` → abort 路径（`abort_reason="reducer_failed[seq=<i>]: <detail>"`），返回 `(base_state, aborted_txn, [])`。**纯函数保证 base_state 未被触碰**——原子性零成本成立（§6.3）。
8. **事件发射**（§6.4）：用步骤 3 的 `event_ids` 逐 CommittedEffect 组装 DomainEvent，返回 `(new_state, txn, events)`。

> 实现纪律：整个函数内**不得**出现 `model_copy(update=...)` / `model_construct`（写屏障静态审计覆盖）。

### 6.3 原子性机制（Plan 必须测试 3 的落点）

两类原子失败源，统一表现为 ABORTED 事务 + 状态/revised 原样：

1. **终检失败**：`check_transaction_references` 报告 missing_entity / stale_revision / duplicated_effect_id（典型场景：外部装配的批次、级联中途状态已前进）；
2. **reducer 应用失败**：事务内顺序交互（如 seq 0 `core.remove_entity(X)`，seq 1 对 X `core.set_component`）触发 `EffectApplicationError`。

部分提交在任何一层都不可表达（P1 §5.6 不变量 2：ABORTED ⇒ 无 commit_revision、effects 空）。失败事务**必须**产生 trace（`TraceKind.TRANSACTION`，payload 附 `rejected_effect_ids`，§9），供审计"atomic failure"。

### 6.4 事件发射映射（D-P2-12）

每个 CommittedEffect 发射**恰好一个** DomainEvent（P2 默认 1:1 映射；P5+ 模块若需富化事件形态，经 Gate 扩展映射器，不改本签名）：

```python
DomainEvent(
    event_id=<§6.2 步骤 3 预分配的 event_id>,
    event_type=effect.effect_type,                 # 1:1（EffectTypeId 与 EventTypeId 同词法空间）
    world_revision=commit_revision,                # Spec §21.1：= 产生事件的事务 commit_revision
    logical_tick=logical_tick,                     # 透传（D-P2-18）
    transaction_id=tx_id,
    payload={"effect_id": str(effect.effect_id),
             "target": effect.target.model_dump(mode="json")},   # 最小事实载荷；语义载荷归模块
    cause_ids=[CauseRef(kind=CauseKind.EFFECT, ref_id=str(effect.effect_id))] + list(effect.cause_ids),
    source_system=effect.source,                   # 提案者（K6：可回答"谁提出"）
    provenance=Provenance(producer_id=effect.source,
                          origin=<producer_registry.origin_of(effect.source)>),
    cascade=cascade,                               # 级联上下文透传（可空）
)
```

`effect.cause_ids` 原样拼接在事件因果引用之后——K6 因果链在事件上自包含可查（无需回查 trace 即可重建 effect→…→event 链）。`producer`（事务级 Provenance）入 `Transaction.provenance`，与事件级 provenance 分层：事务装配者 ≠ 各 effect 提案者是合法常态（如 dev 注入一批规则效果）。

### 6.5 `abort_transaction`

```python
def abort_transaction(base_state: WorldState, tx_id: TransactionId, reason: str,
                      producer: Provenance, *,
                      rejected_effects: Sequence[ProposedEffect] = (),
                      logical_tick: int | None = None,
                      cascade: CascadeContext | None = None) -> Transaction: ...
```

返回 ABORTED 事务（`base_revision=base_state.world_revision`、无 commit_revision、effects 空、`abort_reason=reason`）。被拒 effects 不进事务（数据层不可表达），由调用方写入 trace（`TRANSACTION` payload 附加键 `rejected_effect_ids: [str]` + `PAYLOAD_RECORD_KEY` 内嵌事务记录）。

---

## 7. `cascade.py`（P2-T07 / P2-T08）

### 7.1 `CascadeConfig`（D-P2-13）

```python
DEFAULT_MAX_CASCADE_DEPTH: Final[int] = 8      # 任务包口径：默认 8

@dataclass(frozen=True)
class CascadeConfig:
    max_cascade_depth: int = DEFAULT_MAX_CASCADE_DEPTH   # 允许的最大触发深度（depth 0..8）
    location_revisit: str = "forbid"                     # "forbid"（环路熔断，D-P2-14）| "allow"（仅深度上限）
```

深度语义（精确口径）：根提案在 `depth=0` 提交；由 depth=d 事务的事件触发的提案在 `depth=d+1` 提交；`depth > max_cascade_depth` 的回合**不启动**，记 SYSTEM 诊断。默认配置下至多 9 个 COMMITTED 事务（depth 0..8）、revision 至多 +9。

### 7.2 触发器协议与注册表

```python
class CascadeTrigger(Protocol):
    trigger_id: str                                  # 诊断名（如 "rule.on_hp_changed"）
    def evaluate(self, events: Sequence[DomainEvent], state: GuardedWorldState,
                 depth: int) -> Sequence[ProposedEffect]:
        """同步求值（Spec §21.3 'evaluate synchronous triggers'）。纯函数；
        接收 GuardedWorldState（§2.6.3）——触发器物理上拿不到写路径（K2）。"""

class CascadeTriggerRegistry:
    def register(self, trigger: CascadeTrigger) -> None: ...   # 同名重复注册幂等/冲突（同款纪律）
    def evaluate_all(self, events, state, depth) -> list[ProposedEffect]:
        """按注册序逐触发器求值并串联结果（确定性）。"""
```

**触发输出因果闭合检查（K6）**：执行器对触发器产出的每个提案校验——其 `cause_ids` 必须含 ≥1 个 `CauseKind.EVENT` 且 `ref_id` ∈ 本回合事件 ID 集；不满足的提案被丢弃 + SYSTEM 诊断（`trigger_output_dropped`）。级联链由此保证可完整重建（P1 errata C1 口径：级联串联由 cause_ids 承载）。

### 7.3 `CascadeExecutor`（P2-T07 主体）

```python
@dataclass(frozen=True)
class CascadeResult:
    final_state: WorldState
    transactions: tuple[Transaction, ...]        # 含 ABORTED（审计原子失败）
    events: tuple[DomainEvent, ...]
    trace_records: tuple[TraceRecord, ...]       # 全部决策/诊断记录（§9）
    deferred: tuple[ProposedEffect, ...]         # 域解析器 DEFER 的再入队残留（终态未消化者）
    diagnostics: tuple[CascadeDiagnostic, ...]   # §7.4/§7.5

class CascadeExecutor:
    def __init__(self, *, policy: AuthorityPolicy,
                 component_registry: ComponentRegistry | None = None,
                 producer_registry: ProducerRegistry | None = None,
                 handlers: EffectHandlerRegistry | None = None,
                 triggers: CascadeTriggerRegistry | None = None,
                 resolvers: ... | None = None,           # §5.5 域解析器挂点
                 validator: EffectValidator | None = None,
                 config: CascadeConfig | None = None) -> None:
        install_write_barrier()                  # kernel 运行时入口武装屏障（幂等，§2.6.2）
        ...
    def run(self, initial_proposals: Sequence[ProposedEffect], state: WorldState, *,
            causal_root_id: str, origin: Provenance) -> CascadeResult: ...
```

`causal_root_id` **必填**（Spec §21.3 causal_root_id；调用方传入 ActionInstanceId/EventId——P3 调度器启动级联时以 action 实例为根；P2 测试用确定性构造值）。执行器自身不发明根身份。

`run` 主循环（round 结构）：

```text
cascade_id = new_cascade_id(); depth = 0; pending = initial_proposals
while pending 非空:
    if depth > config.max_cascade_depth: SYSTEM 诊断(cascade_depth_exceeded)；break
    round_state, txn, events, traces = run_round(state, pending, depth, cascade_ctx)
    收集 txn/events/traces（txn ABORTED → 级联停止：无事件可触发，记诊断）
    环路检测武装时：run_round 内部已对本回合 accepted 逐个 check（§7.5）；此处登记本回合已提交位置集
    pending = triggers.evaluate_all(events, guard(round_state), depth) 的因果闭合过滤结果
          + 上回合 DEFER 再入队者（§5.5）
    depth += 1
```

`run_round(state, proposals, depth, cascade_ctx)`（D-P2-03：一回合事务）：

1. trace 每个提案（`PROPOSED_EFFECT` 内嵌记录）；
2. **authority**：逐 effect `check_authority(effect, policy, state, component_registry=...)`；deny → 丢弃 + trace（`AUTHORITY_DECISION`，decision=deny，reason_code 入 reason）；
3. **validation**：`validator.validate_batch(allowed, ValidationContext(state, ...))`；失败 effect 丢弃 + trace（`VALIDATION_DECISION`，decision=fail，reason=issues 串接）；
4. **conflicts**：`detect_conflicts(valid)` → 逐组解析（`DefaultConflictResolver` + 域解析器）；每组 trace（`CONFLICT_RESOLUTION`）；单元素"组"直通；
5. **装配**：accepted 按到达序；空 → 本回合无事务（不消耗 revision——空回合不 commit，P1 §5.6 不变量 1 的管道镜像）；
6. `commit_transaction(state, accepted, new_transaction_id(), origin, cascade=CascadeContext(cascade_id, causal_root_id, depth), logical_tick=None, ...)`；trace `TRANSACTION`（含 ABORTED）+ 每事件 `DOMAIN_EVENT`。

全部 TraceRecord 填充坐标：`world_revision` = 记录时 state 的 revision、`logical_tick=None`（P2 无时钟，D-P2-18）、`cascade_id`、相关 `transaction_id`/`producer_id`。

### 7.4 深度熔断与诊断载体（P2-T07 交付一半，P2-T08 补全）

```python
@dataclass(frozen=True)
class CascadeDiagnostic:
    kind: str          # "cascade_depth_exceeded" | "cycle_detected" | "trigger_output_dropped"
    depth: int
    detail: str        # 人可读 + 机可解析的结构化串
```

对应 SYSTEM trace payload 约定（冻结键名）：`{"diagnostic": <kind>, "cascade_id": str, "depth": int, "detail": str}`。

### 7.5 `CycleDetector`（P2-T08；D-P2-14）

**环路口径**：级联链上的**冲突位置重访**。任务包示例 `HP变化 → 触发规则 → 又改HP` 的推演：

```text
depth 0: 某事务修改 (ent_x, attrs.hp)          → 提交位置集 L0 = {(ent_x, attrs.hp, None)}
         事件 attrs.hp_changed（target=ent_x/attrs.hp）
depth 1: 触发器提案 effect attrs.set_hp，锁 (ent_x, attrs.hp, None)
         CycleDetector: 锁 ∈ 祖先位置集 L0 → cycle_detected，丢弃该提案 + 诊断
         （诊断 detail 重建链："[depth1] attrs.set_hp@(ent_x,attrs.hp) 重访 [depth0] 已提交位置"）
```

```python
class CycleDetector:
    def __init__(self, mode: str = "forbid") -> None: ...    # mode = CascadeConfig.location_revisit
    def observe_commit(self, depth: int, locations: frozenset[ConflictKey]) -> None: ...
    def check(self, effect: ProposedEffect) -> CycleHit | None:
        """effect 的任一锁 ∈ 祖先深度已提交位置并集 → CycleHit；
        mode='allow' → 恒 None（退化为仅深度上限）。"""

@dataclass(frozen=True)
class CycleHit:
    ancestor_depth: int          # 被重访位置首次提交的深度
    key: ConflictKey             # 重访的冲突位置
```

- 接线位置：`run_round` 装配前对 accepted effects 逐个 `check`；命中的 effect 被**丢弃**（不触发整事务失败——环路阻断是过滤语义），trace SYSTEM（cycle_detected）+ `CascadeDiagnostic`；若本回合 accepted 全部被环路丢弃 → 回合空转、级联收敛；
- T07/T08 分工：**P2-T07** 交付执行器骨架 + `cycle_detector` 注入钩子（缺省 None = 仅深度上限）；**P2-T08** 交付 `CycleDetector` 类、`CascadeExecutor` 默认构造它、诊断测试（Plan 必须测试 6 的 HP 环用例归 T08/T09 双覆盖）。

### 7.6 因果树重建（K6 验收）

任一 CascadeResult 满足：全部事件携带 `cascade`（同一 cascade_id、root 一致、depth 与所在事务一致）；`cause_ids` 链 effect↔event 交替衔接至根；任一深度 d 的提案可沿 cause_ids 回溯到 depth 0 的根提案。此性质由 P2-T09 类别 5/7 程序化断言。

---

## 8. P1 义务登记落位汇总（§10.1 → 任务/章节/测试）

| 义务 | 落位任务 | 设计章节 | 验收测试 |
|---|---|---|---|
| **C2**：`check_transaction_references` 晋升 core（签名 `(state, txn) -> tuple[str, ...]` 不变，逐字迁移，删测试侧副本） | P2-T04 | §4.5 | `tests/engine_v2/core/test_transaction_references.py`（15 例改 import 后全绿）+ `tests/engine_v2/kernel/test_transaction_executor.py`（终检触发原子失败用例） |
| **C3**：写屏障覆盖 `model_copy(update=...)` / `model_construct` 逃逸路径（reducer 外禁用/审计） | P2-T01 | §2.6 | `tests/engine_v2/kernel/test_write_barrier.py`（运行时拦截正/反例 + exempt 窗口）+ `test_write_barrier_static.py`（AST 审计，含注入违规样本捕获） |
| **ID 种类严格校验**：typed ID pydantic 路径不校验前缀，跨种类 ID 静默重建 → P2 validation 显式拒绝（parse_id 复用） | P2-T04 | §4.4 | `tests/engine_v2/kernel/test_validation.py`（EffectId 值落入 entity_id 字段、错误前缀串、INTERVENTION ref_id 词法等用例）+ P2-T09 类别 7 |

---

## 9. Trace 产生汇总表（模块 × TraceKind × payload 约定）

payload 键名继承 P1 `trace.py` 冻结常量（`PAYLOAD_RECORD_KEY="record"`、`DECISION_PAYLOAD_KEYS={effect_id, decision, reason}`）。

| 产生者 | TraceKind | decision/内容约定 | 产生时机 |
|---|---|---|---|
| cascade.py（run_round 步骤 1） | `PROPOSED_EFFECT` | `{"record": effect.model_dump(mode="json")}` | 每提案入回合 |
| cascade.py（步骤 2） | `AUTHORITY_DECISION` | `effect_id`、`decision ∈ {allow, deny}`、`reason = reason_code[+rule index]` | 每 effect 权限判定 |
| cascade.py（步骤 3） | `VALIDATION_DECISION` | `decision ∈ {pass, fail}`、`reason` = issues `to_trace_str` 分号串接 | 每 effect 校验 |
| cascade.py（步骤 4） | `CONFLICT_RESOLUTION` | `effect_id` = 胜者（或组成员串）、`decision ∈ {winner, merge, defer, reject, repair}`、`reason = 策略名 + detail` | 每冲突组 |
| transaction_executor.py | `TRANSACTION` | `{"record": txn.model_dump(mode="json")}`（**含 ABORTED**）；ABORTED 附加 `rejected_effect_ids` | 每事务（含原子失败） |
| transaction_executor.py | `DOMAIN_EVENT` | `{"record": event.model_dump(mode="json")}` | 每事件 |
| cascade.py（熔断/环路/触发丢弃） | `SYSTEM` | §7.4 payload 约定 | 诊断 |

`DEV_INTERVENTION`（Spec §22 origin=developer）不在 P2 产生——开发命令面归 P8；但 P2 管道**已能承载**：`origin=OriginKind.DEVELOPER` 的 Provenance + `dev.console` 之类 ProducerId 经 authority 显式授权即可走全管道（P2-T09 类别 1 含此用例）。

---

## 10. 任务包执行图（P2-T01 ~ P2-T09）

### 10.1 依赖与波次

```text
波次 A（并行）:  T01 reducer.py（QMax）          ∥  T02 authority.py-selector（QMax）
波次 B:          T03 authority.py-求值（Q27，T02 之后，同文件串行）
                 ∥ T04 validation.py（QMax，依赖 T01 的 registry/payload 模型 + C2）
波次 C:          T05 conflicts.py（QMax，依赖 T03 的 AuthorityDecision/ProducerRegistry）
                 ∥ T06 transaction_executor.py（QMax，依赖 T01 apply_* + T04 check_transaction_references）
波次 D:          T07 cascade.py-执行器（QMax，依赖 T05+T06，接线 T02-T04）
波次 E:          T08 cascade.py-CycleDetector+诊断（Q27，T07 之后，同文件串行）
波次 F:          T09 对抗测试（GFlash，依赖全部）
```

同文件单 Owner 纪律（Plan §7.2 / migration-constraints §2）：`authority.py`（T02→T03）与 `cascade.py`（T07→T08）严格串行；其余波次内文件互斥可并行。

### 10.2 各任务包交付物与写入白名单

| 任务 | 交付 | 写入白名单（任务包定义时必须原样照抄） |
|---|---|---|
| **P2-T01** | `reducer.py`（§2 全量：结构词表、state_* API、registry、apply_*、写屏障三层） | `src/engine_v2/core/reducer.py`（新增）、`src/engine_v2/core/__init__.py`（reducer 导出块）、`tests/engine_v2/kernel/__init__.py`、`tests/engine_v2/kernel/conftest.py`、`tests/engine_v2/kernel/test_reducer.py`、`tests/engine_v2/kernel/test_write_barrier.py`、`tests/engine_v2/kernel/test_write_barrier_static.py`（均新增）、`tests/engine_v2/core/test_closeout.py`（仅 `_CORE_SUBMODULE_NAMES` 元组 13→19 修订）、`tests/engine_v2/core/test_import_boundary.py`（仅本文件 `CORE_SUBMODULES` 元组 13→19 修订；二者均为 D-P2-19 的一行级机械修订） |
| **P2-T02** | `authority.py` 之 selector 层（§3.1/§3.2/§3.6：AuthoritySelector、match_selector、KERNEL_STATE_DOMAINS） | `src/engine_v2/core/authority.py`（新增）、`core/__init__.py`（authority 导出块第一遍）、`tests/engine_v2/kernel/test_authority.py`（新增，selector 部分） |
| **P2-T03** | `authority.py` 之求值层（§3.3/§3.4/§3.5：AuthorityRule/Policy、ProducerRegistry、check_authority、AuthorityDecision） | `src/engine_v2/core/authority.py`（续写）、`core/__init__.py`（authority 导出块补全）、`tests/engine_v2/kernel/test_authority.py`（续写） |
| **P2-T04** | `validation.py`（§4 全量）+ **C2 晋升** | `src/engine_v2/core/validation.py`（新增）、`core/__init__.py`（validation 导出块）、`tests/engine_v2/core/test_transaction_references.py`（**C2 授权修订**：删本地函数改 import + exempt 包裹，断言不变）、`tests/engine_v2/kernel/test_validation.py`（新增） |
| **P2-T05** | `conflicts.py`（§5 全量） | `src/engine_v2/core/conflicts.py`（新增）、`core/__init__.py`（conflicts 导出块）、`tests/engine_v2/kernel/test_conflicts.py`（新增） |
| **P2-T06** | `transaction_executor.py`（§6 全量） | `src/engine_v2/core/transaction_executor.py`（新增）、`core/__init__.py`（executor 导出块）、`tests/engine_v2/kernel/test_transaction_executor.py`（新增） |
| **P2-T07** | `cascade.py` 执行器骨架（§7.1-§7.4 + §7.5 注入钩子，检测器缺省 None） | `src/engine_v2/core/cascade.py`（新增）、`core/__init__.py`（cascade 导出块）、`tests/engine_v2/kernel/test_cascade.py`（新增） |
| **P2-T08** | `cascade.py` 之 CycleDetector + 诊断 + 默认接线（§7.4/§7.5 补全） | `src/engine_v2/core/cascade.py`（续写）、`core/__init__.py`（补 CycleDetector 导出）、`tests/engine_v2/kernel/test_cycle_diagnostics.py`（新增） |
| **P2-T09** | 对抗测试（§11 全量） | `tests/engine_v2/kernel/test_adversarial.py`（新增；如需辅助夹具仅可加 `tests/engine_v2/kernel/conftest.py`） |

每个任务包完成判据：`.venv/bin/python -m pytest tests/ -q` 全绿（含 989+ 既有用例零回归）、`.venv/bin/python -m ruff check src/engine_v2 tests/engine_v2` 零告警。

### 10.3 `core/__init__.py` 与 closeout 机制同步（D-P2-19）

- P2-T01 将**两处相互独立**的 13 模块清单同步扩为 19 项（追加 `authority`、`cascade`、`conflicts`、`reducer`、`transaction_executor`、`validation`）：
  - `tests/engine_v2/core/test_closeout.py::_CORE_SUBMODULE_NAMES`（驱动 closeout 的 `CORE_SUBMODULES` 模块字典与 `__all__` 并集机制）；
  - `tests/engine_v2/core/test_import_boundary.py::CORE_SUBMODULES`（驱动 B1 文件集合断言 `test_core_dir_file_set_matches_design_table` 与 B2 fresh-import 扫描面）。
  此后 closeout 的「包 `__all__` == 模块 `__all__` 并集减同名遮蔽豁免」机制与 import_boundary 的文件集合断言对新模块自动生效——**注意**：新模块导出名不得与子模块名相撞（现有豁免集恒为 `{snapshot}`，该断言机械化，撞名即测试失败，天然防线）。
- 各任务包按 §10.2 顺序在 `__init__.py` 追加本模块 re-export 块与 `__all__` 条目（字母序插入，P1 同款纪律）。

---

## 11. P2-T09 对抗性测试规范（7 类场景）

> 文件：`tests/engine_v2/kernel/test_adversarial.py`（GFlash）。每类场景给出构造要点与断言；全部用例无网络、无 LLM、无 API key。fixture 复用 `tests/engine_v2/kernel/conftest.py`。下述 7 类与 Plan §11「必须测试」7 条一一对应。

### 类别 1 —— 越权写入（必须测试 1）

构造：policy 仅授权 `rule.lock_system` 写 `door.lock_state` 组件域；攻击提案分别来自 (a) 未授权 producer `policy.alice`；(b) 完全未注册 producer `llm.narrator`；(c) 携带 `authority_scope="door.lock_state"` 伪造声明的未授权 producer（D-P2-17：声明不提升权限）；(d) 无匹配规则（空白 policy）。
断言：`check_authority` 全部 deny（reason_code 分别为 rule_deny / no_matching_rule）；`CascadeExecutor.run` 后 `final_state == 初始 state`、revision 不变、零 COMMITTED 事务；trace 含 AUTHORITY_DECISION(deny) 逐条记录。

### 类别 2 —— 双写冲突（必须测试 2）

构造：Spec §19 原型 `Move(gem, floor)` vs `Move(gem, alice_inventory)` 的结构化等价物——两个**均被授权**的 producer 对同一 `(ent_gem, space.position)` 提 `core.set_component`；另设 (a) 三写同址；(b) 同组件不同 field_path 的两个字段级效果（**不应**成组）；(c) 整组件效果 vs 字段效果（**应**成组）。
断言：`detect_conflicts` 分组正确（(b) 空、(a)(c) 成组）；DefaultConflictResolver 拍板可解释——strategy 名 + reason 入 trace（CONFLICT_RESOLUTION）；固定输入下 winner 确定（逐策略构造：authority rule_priority 差、metadata 时间戳全带/部分带、producer priority、到达序兜底各一例）；败者不落状态。

### 类别 3 —— 无效效果原子失败（必须测试 3）

构造：(a) L2 终检路径——批次内一条 effect 指向 missing entity（以 `commit_transaction` 直接装配，绕过 L1 过滤模拟外部批次）；(b) reducer 应用路径——同事务 seq0 `core.remove_entity(X)` + seq1 对 X `core.set_component`；(c) stale 批次（base_revision 落后于 state）。
断言：返回 `(base_state 原样, ABORTED 事务, [])`；`commit_revision is None`、`effects == []`（P1 不变量 2 复检）；revision 不变；trace 含 ABORTED 事务记录（含 reject id）；**部分提交在任何断言面不可观测**。

### 类别 4 —— 递增只 +1（必须测试 4）

构造：(a) N=5 效果单事务；(b) 三级级联（触发器链产生 3 个回合）；(c) 一次 ABORTED；(d) 空 accepted 回合（authority 全拒后管道空转）。
断言：(a) revision 恰 +1；(b) revision 恰 +3 且各事务 commit_revision 连续递增；(c)(d) revision +0；任何路径不出现 +2/跳号（对全部 transactions 程序化断言 `commit_revision == base_revision + 1`）。

### 类别 5 —— 循环事件熔断（必须测试 6）

构造：组件 `attrs.hp` 注册于测试 registry；触发器 `rule.on_hp_changed`：见到 target 含 `(ent_x, attrs.hp)` 的事件即回提 `core.set_component(ent_x, attrs.hp)`（cause_ids 按因果闭合要求携带事件引用）。
断言：`CycleDetector` 在 depth 1 即丢弃回环提案，诊断 `cycle_detected` 含祖先深度与位置链；级联正常收敛（无异常）；另一用例：无环但触发器链深度 > 8 → 在 depth 9 启动前停，诊断 `cascade_depth_exceeded`，至多 9 个 COMMITTED；全部事件 cascade_id/root 一致、depth 单调。

### 类别 6 —— 绕过 Reducer 拦截（必须测试 7）

构造与断言：
1. 屏障武装态下 `state.model_copy(update={"world_revision": 99})` → `WriteBarrierError`；`Transaction.model_construct(...)` → `WriteBarrierError`；`copy.copy(state)` / `copy.deepcopy(state)` → `WriteBarrierError`（四条逃逸路径逐一断言）；`write_barrier_exempt()` 内四者放行（豁免窗口有效且最小）；
2. `guard(state)` 包装器：4 个只读门面 + `model_dump` 可用；`model_copy`/`model_construct`/属性赋值/`_with_*` 访问全部 `WriteBarrierError`；
3. 静态审计自测：向扫描器喂入**合成的违规源码字符串**（含 `model_copy(update=`、`.model_construct(`、`_with_entities` 调用各一）→ 全部被捕获；喂入 `reducer.py` 自身 → 白名单放行；
4. 管道面：触发器收到的是 `GuardedWorldState`（isinstance 断言 + 写路径抛错）；
5. `uninstall_write_barrier()` 后 P1 语义复原（`model_construct` 可用）——保证 P1 测试不受染。

### 类别 7 —— 管道纪律与 K6 溯源（必须测试 5 + ID 义务）

构造与断言：
1. 提交后每个事件携带 `transaction_id`、`source_system == effect.source`、`cause_ids` 含 `CauseRef(EFFECT, effect_id)`、`world_revision == commit_revision`（K6 六要素逐项程序化断言）；
2. 跨种类 ID 攻击：`EffectId` 值写入 target.entity_id 字段、`"evt_x"` 串写入 effect_id 字段、INTERVENTION cause 携带非 `trc_` ref_id → validation `bad_id_kind` 拒绝；
3. 未注册 effect_type（语义型且无 handler）→ `no_handler` 拒绝；直接喂 reducer → `ReducerError`（纵深）；
4. 同批重复 effect_id → `duplicated_effect_id` 全副本拒绝；
5. `future_base_revision`（base > current）→ 拒绝；
6. 开发干预通道：`origin=DEVELOPER` 的 producer 经 policy 显式授权后可提交，trace provenance 完整（Spec §22 管道承载验证）。

---

## 12. G2 门禁对齐（Plan §11）

| G2 要求 | 机制与归属 |
|---|---|
| 必须测试 1-7 全部通过 | §11 类别 1-7（P2-T09）+ 各任务包单测（T01-T08 已内含同口径基础用例，T09 做对抗加固） |
| 静态确认：Runtime Producer 无直接 authoritative state mutation | §2.6.1 AST 审计测试（P2-T01 交付，扫描 `src/engine_v2/**`，G2 时复跑） |
| 静态确认：Reducer 不调用 LLM | import 边界（`test_import_boundary.py` 自动覆盖新模块，provider/llm 黑名单）+ reducer.py 无 IO/网络 import |
| 静态确认：Reducer 不做语义推断 | 行为测试：未注册 effect type 抛错（§11 类别 7.3）；结构变更一律整体替换、无合并/插值分支（§2.1 前置条件表 + 用例） |

G2 复跑命令口径（与 G1 一致）：`.venv/bin/python -m pytest tests/ -q`、`.venv/bin/python -m ruff check src/engine_v2 tests/engine_v2`、kernel 写屏障静态测试。

---

## 13. 显式非目标（P2 不做）

1. **`commands.py` / 开发命令面**（Spec §44/§22）：P2 只保证 `origin=developer` 的效果可经管道提交（§9/§11 类别 7.6）；`DevelopmentCommand` 类型、pause/step/patch_state 等命令语义归 P3（lifecycle）与 P8（devtools）。
2. **调度与时钟**：`logical_tick` 推进、scheduler queue 语义、action lifecycle 迁移归 P3（D-P2-18）；P2 事件/事务的 logical_tick 一律透传或 None。
3. **RuntimeState 变更**：P2 管道只写 WorldState；`pending_proposals`/`active_actions` 等运行时状态的入队/迁移语义属 P3/P4。
4. **域解析器与语义 effect**：MERGE/REPAIR/DEFER 的真实域语义、RPG 组件（HP/Inventory 等）归 P5/P9 模块；P2 只提供注册位与桩测试（D-P2-11）。
5. **trace 持久化**：TraceRecord 的存储介质/流式落盘归 P8 PersistenceBackend；P2 只产出记录对象（CascadeResult.trace_records）。
6. **YAML/项目配置加载**：authority policy 的 YAML 映射归 P5 content 层（D-P2-08）。
7. **异步 producer**：P2 管道为同步收集-解析-提交模型；异步提案的 base_revision revalidation 决策流（ACCEPT/REBASE/REPAIR/REJECT 的**判定**）在 P3 调度边界与 P4 actor 管线中基于本管道实现（词表已在 P1 `revision.py`）。
8. **性能工程**：冲突检测 O(n²)、`_WorkingWorld` 批量应用为 MVP 口径；索引化/增量化归后续 Phase（不改签名）。

---

## 14. Open Questions（需架构确认；无阻断项）

1. **`core.*` 结构词表的冻结级别**：本文档将 7 个结构 effect type 视为 public contract（值一经使用即稳定，G1 同款纪律）。若 P5/P9 模块落地时发现需要新结构动词（如 `core.move_component` 类原子移动），确认走 Gate review 追加而非静默扩展。（倾向：是，按冻结处理。）
2. **一回合事务粒度**（D-P2-03）：P2 定为"一回合事务"。P3 调度器可能需要按 producer 组或按 tick 边界拆分事务的语义——届时由 P3 在 `commit_transaction` 之上组织批次，不改 P2 签名。确认此分层无争议。
3. **DEFER 再入队的公平性**：域解析器 DEFER 的效果在下一回合以原到达序重入；若多组互相 defer，P2 仅以深度上限兜底。确认 P2 不需要额外的 defer 预算机制（倾向：不需要，深度上限足够）。
4. **`producer_timestamp_ms` 约定键**（D-P2-16）：作为 metadata 开放字段的 P2 约定键，不进入契约 schema。若 P6 LLM Runtime 希望标准化提案时间戳字段，届时经 Gate 决定是否升格为 ProposedEffect 字段（当前保持 metadata，避免触碰冻结契约）。

---

## 15. 章节 ↔ 权威出处对照（自检索引）

| 本文档章节 | 权威出处 |
|---|---|
| §1.1 管道路径 | Spec §4 K2（八段路径原文）、K3、K6 |
| §1.2 文件清单 | Spec §44（authority/validation/conflicts/reducer/transaction 命名保留）、P1 设计 §1.1 注记（P2 文件名沿用） |
| §2 reducer | Spec §20.2（deterministic / reject invalid / no LLM / no silent infer）；P1 设计 §3.5 纪律 3（`apply_transaction` 唯一公共路径预告）、§10.1 C3；P1-T07 §C.2/§D.1 |
| §2.1 结构词表 | Plan §10 强制约束（Kernel 不预置 RPG 字段）；P1 设计 §8 非目标 1 |
| §2.4 revision 置位 | Spec §9（commit +1）、§20.1（produce one world revision）；P1 设计 §2.3 D-5 |
| §3 authority | Spec §17.1/§17.2、§4 K3/K4；P1 设计 §2.2 D-4（ProducerId 名字型）、§10 预留表（authority selector 五维数据承载） |
| §4 validation | Spec §18（schema/preconditions/existence/type/invariants/stale）；P1 设计 §10.1（C2、ID 种类义务）、§7.4 C7；P1-T07 §D.2/D.3 |
| §5 conflicts | Spec §19（winner/merge/defer/reject/repair；authority priority/timestamp/producer priority/causality/domain resolver）；P1 设计 §10 预留表（priority_hint、EffectTarget 定位键） |
| §6 transaction_executor | Spec §20.1（atomic commit / one revision / emit events / retain provenance）；P1 设计 §5.6 四条不变量；P1-T07 §A.3 |
| §7 cascade | Spec §21.3（cascade_id/causal_root_id/depth/cycle diagnostics/max depth 五要素）、§21.1/§21.2；P1 设计 §5.7 errata（级联由 cause_ids 承载、CascadeContext 仅 DomainEvent/Transaction 携带） |
| §9 trace 汇总 | P1 设计 §4.4（TraceKind 与 payload 子约定、DECISION_PAYLOAD_KEYS）；Spec §8.4 |
| §10 任务切分 | Plan §11 任务表（ID/属性/难度/默认模型）、§7 并行纪律；P1 设计 §1.2 执行次序范式 |
| §11 对抗测试 | Plan §11 必须测试 7 条、Plan §22.3 adversarial 范式；Spec §9（stale 示例 812/813） |
| §12 G2 | Plan §11 G2 原文三条静态确认 |

---

*文档完。本设计不改变任何已冻结 P1 public contract；实现过程中若出现与本文档的偏差，须按 Plan §10「public contract 修改必须经 Gate review」披露。P2 各任务包以本文档为唯一执行依据。*
