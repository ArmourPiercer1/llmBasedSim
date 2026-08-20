# G1 Gate Report — Phase 1 Core Data Contracts

按 `docs/plans/llmBasedSim_Architecture_v2_Refactor_Development_Plan.md` §10、§21、§25 编制。

---

## 1. 基础信息

- **Gate**: G1（Phase 1 — Core Data Contracts 门禁）
- **Commit SHA**: `603535e`（包含工作区未提交的 review/errata 交付件：`docs/v2/reports/P1-T07-contract-review.md` 与 `docs/v2/contracts/P1-core-data-contracts.md` C1 勘误）
- **分支**: `architecture-v2`
- **Agent**: Integration Agent（任务 ID: `P1-INTEGRATION`）
- **审查基准**: commit `e010c9b`（M0 门禁点）至 HEAD

---

## 2. 任务完成情况

### Tasks completed:
1. **P1-DESIGN** (`105afd5`): Core Data Contracts 架构设计文档（Spec §50 Spec A 落地，857 行）。
2. **P1-T01** (`21488df`): `EntityId / EffectId / EventId / TransactionId / Revision` 等 ID 与 Revision 原语（94 例单测）。
3. **P1-T03** (`21488df`): Entity + typed component logical facade（`ContractModel` 基类、`ComponentSchema`、`EntityRecord`、`EntityRef`、`EntityView` 等，69 例单测）。
4. **P1-T04** (`222825b`): `ActionProposal / ActiveAction / ProposedEffect / CommittedEffect / DomainEvent / Transaction` 等 schemas 及不变量（133 例单测）。
5. **P1-T02** (`222825b`): `WorldState / RuntimeState / BackendStateRef / TraceRecord` 状态契约（101 例单测）。
6. **P1-T05** (`603535e`): 序列化与快照基础设施（`serialization.py`、`snapshot.py`、`check_snapshot_versions`，106 例单测）。
7. **P1-T06** (`603535e`): Core 契约测试收尾、re-export 及骨架测试最小修订（35 例测试，全仓达到 989 passed）。
8. **P1-T07** (工作区报告): Core Contract 独立审查（产出 `docs/v2/reports/P1-T07-contract-review.md`，结论 APPROVE_WITH_CONDITIONS，3 条条件 C1/C2/C3）。
9. **P1-ERRATA** (工作区修订): 针对 T07 条件 C1 的勘误（消除 §5.7/§5.3 关于 ProposedEffect 是否携带 cascade 的矛盾，修正 §2.3 交叉引用笔误，并在 §10.1 登记 P2 义务 C2/C3）。

### Tasks waived:
- **无**（Phase 1 所有规划任务全部完成）。

---

## 3. 测试与静态分析执行结果

### Tests:
- **全仓回归**: `.venv/bin/python -m pytest tests/ -q`
  - **结果**: `989 passed in 3.63s`（零失败、零警告退出、零网络依赖）。
- **Phase 1 专属测试**: `.venv/bin/python -m pytest tests/engine_v2/ tests/test_engine_v2_skeleton.py -q`
  - **结果**: `544 passed in 0.52s`。
  - 分布：
    - `test_ids.py`: 71 passed
    - `test_revision.py`: 23 passed
    - `test_entity_components.py`: 69 passed
    - `test_state.py`: 101 passed
    - `test_contracts.py`: 133 passed
    - `test_serialization_snapshot.py`: 106 passed
    - `test_transaction_references.py`: 15 passed
    - `test_closeout.py`: 15 passed
    - `test_import_boundary.py`: 5 passed
    - `test_engine_v2_skeleton.py`: 6 passed
- **代码规范检查**: `.venv/bin/python -m ruff check src/engine_v2 tests/engine_v2`
  - **结果**: `All checks passed!`（零告警）。

### Known failures:
- **无**（989 项测试全部 PASS，无遗留已知失败）。

---

## 4. 架构与文件范围核验

### Diff 范围检查
- 核对 `git diff e010c9b..HEAD --name-status`：
  - 改动文件集合严格限定于 `src/engine_v2/core/`（13 个契约模块 + `__init__.py`）、`tests/engine_v2/core/`（9 个测试文件）、`tests/test_engine_v2_skeleton.py`（T06 最小放宽骨架测试）及 `docs/v2/`。
  - **v1 既有代码零改动**（`src/` 既有业务代码、既有测试、`prompts/`、`config/`、`web/`、`public_start/` 均未受任何影响）。

### 单一性与重复实现检查
1. **CONTRACT_SCHEMA_VERSION 单源**: 定义于 `src/engine_v2/core/state.py:99`，`snapshot.py` 与 `core/__init__.py` 均为 import 复用，不存在双源或硬编码分叉。
2. **ContractModel 基类单一**: 唯一定义于 `src/engine_v2/core/entity.py:51`，所有 22 个 pydantic 契约模型均继承自该类（`frozen=True`, `extra="forbid"`）。
3. **类型保持机制一致**: 所有 typed ID（`EntityId`, `EffectId` 等）与 `Revision` 均采用统一的 `__get_pydantic_core_schema__` + `AfterValidator` 钩子模式，round-trip 保持 typed ID / Revision / Tagged Union 精确类型。
4. **临时 Hack 检查**: 对 `src/engine_v2` 和 `tests/engine_v2` 全量 grep `TODO|FIXME|HACK|XXX`，**零命中**。
5. **命名与语义一致性**: 模块、字段、类型名称与 Spec §50 / 设计文档 `P1-core-data-contracts.md` 逐字段完全一致。

---

## 5. G1 门禁六条指标逐条核验

| G1 判据 | 要求 | 核验结果 | 证据 / 说明 |
|---|---|---|---|
| **a. 依赖隔离** | Core import 不需要 LangGraph / OpenAI | **PASS** | `test_import_boundary.py` AST 与运行时黑名单扫描全绿；fresh import 子进程确认 provider SDK 零引入。 |
| **b. 序列化往返** | 所有 schema 可 round-trip | **PASS** | 25 种核心模型形态及 36 组全覆盖样本（含 12 种 TraceKind、中文、datetime、Tagged Union 等）往返值完全相等且类型精确保持。 |
| **c. Revision 语义** | World revision 明确 | **PASS** | COMMITTED 强制 `commit_revision == base_revision.next()`，ABORTED revision 为 None；`is_stale` 纯函数边界验证严格；RuntimeState 无 revision 字段。 |
| **d. ID 稳定性** | public IDs stable | **PASS** | 9 大 ID 前缀表互斥锁定，`PREFIX_TO_KIND` 稳定，10^4 次生成无碰撞，`parse_id` 词法检查严格。 |
| **e. 纯净单测** | Core unit tests 无网络通过 | **PASS** | 544 例 v2 测试在无网络、无 API Key 环境下 0.52 秒全绿完成。 |
| **f. 独立审查** | Reviewer 未发现必须 breaking change 的问题 | **PASS** | T07 独立 Review 给出 APPROVE_WITH_CONDITIONS；3 条条件已全部明确处置路径（C1 闭环，C2/C3 挂账 P2）。 |

---

## 6. T07 审查条件（C1 / C2 / C3）处置状态

1. **条件 C1（文档级 errata）**: **已闭环**
   - 处置：设计文档 `docs/v2/contracts/P1-core-data-contracts.md` 已完成勘误更新，明确 `ProposedEffect` 不携带 `CascadeContext`（以 Spec §16.1 字段清单为准，级联因果由 `cause_ids` 承载），修正了 §2.3 交叉引用笔误，并新增 §10.1 章节显式登记 P2 义务。
2. **条件 C2（`check_transaction_references` 晋升 core）**: **已挂账至 P2-T04**
   - 处置：T06 在测试侧完整实现了 C7 引用检查器（15 例测试）；已登记于设计文档 §10.1，作为 P2-T04 任务包的显式执行内容（逐字迁移入 core 模块并删除测试侧副本，依赖面仅 WorldState/Transaction/is_stale/EntityTarget，零架构风险）。
3. **条件 C3（写屏障覆盖 pydantic 逃逸路径）**: **已挂账至 P2-T01**
   - 处置：已确认 P1 数据层不变量为 advisory，pydantic 的 `model_copy(update=...)` 与 `model_construct` 绕过校验器的问题已登记于设计文档 §10.1，明确由 P2-T01 写屏障在公共 API 与 reducer 外层实施审计与拦截，彻底闭合 K2 状态写安全。

---

## 7. Architecture Deviations

- **零未披露架构偏离**。
- 实现过程中对 Spec 的四处具体化与设计裁定（`cause_ids` 类型、Tagged Union 判别落 JSON、`logical_tick`/`wall_time` 分离、`ActiveAction` 字段补充、`__get_pydantic_core_schema__` 替代方案）均已在设计文档、T01-T06 交付物及 T07 审查报告中充分论证并闭环，不构成破坏性偏离。

---

## 8. Open Risks (供下游 Phase 跟踪)

1. **pydantic 逃逸路径 (P2-T01)**: `model_copy(update=...)` 与 `model_construct` 会跳过字段验证与 frozen 约束，P2 写屏障必须强制兜底拦截。
2. **跨种类 ID 词法校验 (P2-T04)**: typed ID 的 pydantic 重建路径在 schema 层接受合法字符串重建，跨种类前缀校验（如 `EffectId` 误填入 `EntityId` 字段）的严格拦截职责由 P2 validation pipeline 承担。
3. **`WorldState._with_*` 构造开销 (P2-T06)**: 目前采用 `model_dump -> model_validate` 深拷贝确保绝对不可变，高频大规模演化若出现性能瓶颈，可在 P2 增加内部高效构造路径（additive 改动，非 breaking）。
4. **`snapshot()` 模块同名遮蔽**: `from src.engine_v2.core.snapshot import snapshot` 稳定可用，包根保持遮蔽豁免，已有机械化测试钉死，后续开发应遵守该 import 约定。

---

## 9. Human Review Required

**是（REQUIRED）**。
- 根据重构计划 §36 步骤 4 与 §23 H2：在 G1 通过后、正式启动 Phase 2（Effect / Authority / Transaction Kernel）之前，**由人工执行 P1 public Contract 最终冻结裁定**。

---

## 10. Recommended Decision

### **PASS**

---

## 11. Human Review Record（M1 契约冻结，2026-08-20）

人工（架构负责人）已审阅 Phase 1 核心数据契约导读与 G1 Gate Report，裁定如下：

1. **Phase 1 Contract 冻结**：正式批准冻结 `src/engine_v2/core/` 13 个契约模块及其公开导出（93 个接口）。
2. **后续自动化推进授权**：
   - 批准进入 Phase 2（Effect / Authority / Transaction Kernel 管道开发）。
   - 后续 Phase 开发无需在每个 Gate 停下等待人工介入，仅在触发重大路线变更、严重违背计划设计思想时中途停止。
   - 门禁双审机制：在需要评审的节点拉起 `glm-5.3` 和 `qwen3.8-max` 双子代理独立审查，两者均同意时自动继续推进；仅在出现明确反对意见时请求人工介入。

### 理由：
1. **G1 门禁全部 6 条硬性指标 100% 达标**：全仓 989 例测试全通，ruff 静态检查 0 告警，Core 契约无外部重依赖且纯净无网络运行。
2. **核心契约稳定，零 breaking change 隐患**：22 个数据契约模型经独立比对与设计文档完全一致，向下游 Phase（P2–P10）预留的能力承载完整无缺口。
3. **审查条件全部妥善处置**：T07 提出的 C1 勘误已落盘闭环；C2、C3 均已在设计文档 §10.1 明确登记并纳入 P2 任务包执行清单，下游义务链路清晰。
4. **代码纯净，边界清晰**：v1 文件零触碰，无临时 TODO/FIXME 代码，架构纪律严格贯彻。
