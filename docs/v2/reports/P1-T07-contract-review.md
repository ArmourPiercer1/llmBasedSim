# P1-T07 Core Contract 独立审查报告（GLM，按计划 §10）

- **任务**: P1-T07 -- Core Contract Independent Review（探索代码区，独立 review，不改代码）
- **审查对象**:
  1. 设计文档 `docs/v2/contracts/P1-core-data-contracts.md`（857 行，P1 Contract owner 产出）；
  2. 实现 `src/engine_v2/core/` 13 个契约模块 + `__init__.py` re-export（commit `603535e`，分支 `architecture-v2`）；
  3. 测试 `tests/engine_v2/core/`（9 个文件，538 例）+ `tests/test_engine_v2_skeleton.py`（经 T06 最小修订，6 例）；
  4. 权威依据：Spec §4/§8–§11/§16/§20/§21/§23/§44/§46/§47/§50、Plan §10（含 G1 与强制约束）/§22.2/§22.3、ADR-001/ADR-003。
- **审查方式**: 全文阅读设计文档与全部实现/测试源码；独立复跑 G1 门禁命令；**独立编写只读验证脚本**（round-trip / revision / ID / 隔离 / 字段级比对 / 逃逸路径探针，不依赖既有测试自身的断言）；只读 git log/diff 核对 T06 修订范围。
- **本报告写入文件**: `docs/v2/reports/P1-T07-contract-review.md`（唯一写入文件；未改动 src/tests/docs 任何其他文件）。

---

## 0. 结论速览

| 维度 | 结论 |
|---|---|
| G1 五条机械门禁 | **全部通过**（证据见 §A） |
| G1 核心判断（是否存在"后续必须 breaking change"） | **未发现** blocking 级问题（分析见 §A.6、§D） |
| T01–T06 已披露裁定（B 节 6 组 13 项） | **全部接受**；其中 2 项附跟进条件（C7 晋升、写屏障覆盖逃逸路径） |
| 架构红线抽查（C 节） | **无违规**；22 个 pydantic 契约模型字段名与顺序与设计文档逐项一致，未发现未披露偏差 |
| blocking issues | **无** |
| **最终 verdict** | **APPROVE_WITH_CONDITIONS**（3 条条件均为后续 Phase/文档跟进项，不要求 P1 返工，见 §E） |

---

## A. G1 门禁逐条核验（含证据命令与输出摘要）

### A.1 Core import 不需要 LangGraph/OpenAI —— 通过

**证据命令**：

```bash
$ .venv/bin/python -m pytest tests/engine_v2/core/test_import_boundary.py tests/test_engine_v2_skeleton.py -q
11 passed in 0.15s
```

**独立抽查**（fresh 解释器，不经既有测试断言）：

```bash
$ .venv/bin/python -c "<fresh import src.engine_v2.core + 全部 13 个子模块，检查 sys.modules 增量>"
blacklisted modules pulled: []          # langgraph/langchain/openai/anthropic 均未出现
pydantic version: 2.13.4
core.snapshot is module: True           # 同名遮蔽豁免行为符合预期（见 B.6）
```

- B1 静态扫描（AST，保留完整点分模块名，区分 `src.engine_v2` 同包与 v1 包）+ B2 运行时扫描（fresh import 后 sys.modules 增量）+ B3 测试树静态扫描三保险均通过；core 文件集合恰为 §1.1 的 13 模块 + `__init__.py`（`test_core_dir_file_set_matches_design_table`）。
- **观察（非违规）**：pydantic 2.13.4 自身 import 会传递性载入 `socket`/`subprocess`（已单独验证 `import pydantic` 即拉入二者）。这是第三方库内部行为，非 core 自身 import（B1 对 core 源码的 AST 扫描为零命中）；G1 判据（不需要 LangGraph/OpenAI、无网络可跑测试）不受影响。附带效果：B2 的运行时增量检查在 pytest 进程内运行时 pydantic 已被预先载入，故 pydantic 的传递性 stdlib IO import 不会出现在增量中——该口径对本判据是正确的（它要拦的是 provider SDK 与 core 主动 IO）。

### A.2 所有 schema 可 round-trip —— 通过

**证据命令**：

```bash
$ .venv/bin/python -m pytest tests/engine_v2 tests/test_engine_v2_skeleton.py -q
544 passed in 0.52s
$ .venv/bin/python -m pytest -q          # 全仓回归
989 passed in 3.52s
```

- T05 的参数化 round-trip（`TestContractModelJsonRoundtrip`）覆盖 **25 个模型形态**（EntityRecord/EntityRef/ScenarioState/RngState/ScheduledEvent/ActorWakeup/BackendStateRef/RuntimeState/WorldState/Provenance/CauseRef/CascadeContext/EntityTarget/StateDomainTarget/ProposedEffect×2 分支/CommittedEffect/ActionTiming/FallbackSpec/ActionProposal/ActiveAction/DomainEvent/Transaction/TraceRecord/Snapshot），逐字段递归断言**值相等 + 精确类型保持**（含 dict 键的 typed ID 重建、discriminated union 分支保持、枚举成员同一性）。
- **独立抽查**：本人另行构造 36 个样本（上述形态 + 全部 12 种 TraceKind + 中文 intent/payload、tz-aware datetime、空容器、嵌套 dict/list、tagged union 双分支）经 `dump_json -> load_json` 全部值相等、`assert_json_clean` 通过、typed ID/Revision/ComponentTypeId/枚举类型精确保持；`WorldState` dict 键重建为 `EntityId`、`active_actions` 键重建为 `ActionInstanceId` 均验证。
- extra=forbid（J2）、frozen 赋值拒绝（S5/E3）、Transaction 不变量在 round-trip 后重校验，均有参数化用例。

### A.3 World revision 语义明确 —— 通过

- **commit +1**：`Transaction._check_atomic_invariants` 在构造与 `model_validate`（含 round-trip）时强制 `COMMITTED ⇒ commit_revision == base_revision.next()`，ABORTED ⇒ `commit_revision is None` 且 `effects == []`（部分提交 schema 层不可表达）；effects 非空、sequence 唯一且自 0 连续一并强制（设计 §5.6 四条不变量全部数据层固化，C4 用例逐条覆盖，越界值参数化拒绝）。
- **base_world_revision**：`ActionProposal.base_world_revision` 必填（缺省即 ValidationError，C1）；`ProposedEffect.base_revision` 必填；Spec §9 示例（`base_world_revision=812, observation_id="obs_991"`）可直接构造（C2）。
- **is_stale**：独立验证 `is_stale(812, 813) is True`、`is_stale(812, 812) is False`、`valid_until` 边界（`current == valid_until` 不陈旧、`current > valid_until` 陈旧）与设计 §2.3/§7.1 R6 逐条一致；纯函数。
- **D-5 归属**：`world_revision` 仅在 WorldState 上；RuntimeState 无任何 revision 字段（字段集与 Spec §8.2 清单一一对应，程序化断言固化）。

### A.4 public ID 稳定 —— 通过

- **前缀表**与设计 §2.2 逐项一致（独立验证 `PREFIX_TO_KIND` == 9 前缀映射；测试另断言前缀互斥，parse_id 无歧义）；`ProducerId` 无随机前缀（D-4）。
- **词法/生成**：R1 对每种工厂 10⁴ 次生成无碰撞、正文 32 位小写 hex；确定性构造（`EntityId("ent_test_1")`）合法；parse_id 对错误前缀/空串/大写/非法字符抛 `ValueError`（本人独立复验 6 类非法输入）。
- **值与类型稳定（round-trip 侧）**：R2 断言 ID 值逐字相等 + `type(x) is EntityId`；类型保持机制见 B.1。G1 "public IDs stable" 双重含义（值不变 + 类型名/前缀冻结走 Gate）在文档 §2.2 与实现/测试两侧闭环。

### A.5 Core 单元测试无网络通过 —— 通过

```bash
$ .venv/bin/python -m pytest tests/engine_v2 tests/test_engine_v2_skeleton.py -q
544 passed in 0.52s        # 无 API key、无网络、0.52s 完成
```

分文件：test_ids 71 / test_revision 23 / test_entity_components 69 / test_state 101 / test_contracts 133 / test_serialization_snapshot 106 / test_transaction_references 15 / test_closeout 15 / test_import_boundary 5 / 骨架 6，共 544。B3 对 `tests/engine_v2/**` 的静态扫描（网络/进程/provider/v1 import 零命中）提供机械保证。

### A.6 核心判断：是否存在"后续必须 breaking change"的明显问题 —— 未发现

按"数据契约一旦冻结，后续 Phase 是否会被迫改 public 字段/类型/序列化形态"的口径逐项排查（完整清单见 §D）：

- **序列化形态**：全部契约 JSON 侧为纯字符串/整数/字符串字面量，tagged union 判别、dict 键 typed ID 重建、datetime ISO 均已固化且测试钉死；P2–P10 在其上加行为不改形态。
- **预留充分性**（设计 §10 表逐项核对）：authority selector（entity_class/tags/authority_domain/authority_scope/field_path）、conflict（priority_hint/EffectTarget）、revalidation（base_revision/valid_until/observation_id/actor_state_revision/RevalidationOutcome）、scheduler（scheduler_queue/ActiveAction 全字段/ScheduledEvent）、cascade（CascadeContext/CauseRef/TraceKind 通道）、P8（三层版本标记/Snapshot 信封/自包含 CommittedEffect）——P2+ 所需数据承载**全部在场**，未发现"P2/P3 会要求补字段"的缺口。
- **已知风险均为非 breaking**（§D 详列）：pydantic 逃逸路径（advisory 执行，设计已自认并由 P2 写屏障兜底）、`snapshot()` 包属性遮蔽 wart（稳定且有机械化豁免断言）、`EntityView.components` 公开字段（低风险）、C7 检查器暂居测试侧（P2-T04 晋升计划披露）。

**结论：G1 六条全部满足，无 blocking 问题。**

---

## B. T01–T06 已披露裁定逐项复核

### B.1 T01：pydantic 2.13.4 下 `__get_pydantic_core_schema__` + AfterValidator 替代 BeforeValidator；parse_id 无前缀裸小写串判 ProducerId —— **接受**

1. **兜底形态替换（契约语义不变）**：
   - 本人独立复现根因：pydantic 2.13.4 下裸 `str` 子类注解（无 hook）直接抛 `PydanticSchemaGenerationError: Unable to generate pydantic-core schema for <class 'Bare'>... implement __get_pydantic_core_schema__`——pydantic 错误信息本身就推荐该 hook，T01 的替换是**官方指定路径**而非自创 hack。
   - 契约语义验证：`handler(Annotated[str, AfterValidator(cls)])` 接受原生 str、校验链末端重建子类实例——`model_validate` 后 `type(x) is EntityId`（含 dict 键/list 元素），`model_dump(mode="json")` 为纯字符串；设计文档字面的 `Annotated[EntityId, BeforeValidator(...)]` 形态在该兜底之上同样可用（`test_ids.py::test_fallback_annotated_before_validator_pattern` 固化）。Revision（int 子类）同构处理，JSON 纯整数。
   - 判定：**替换合法**，且比逐注解点写 BeforeValidator 更集中、更不易漏。
2. **parse_id 裸小写串 → ProducerId**：设计 §2.2 只写"校验前缀与词法"，未规定无前缀串的归属；R4 要求 authority 名字（`interaction.lock_system` 等）可通过，ProducerId 无前缀，"前缀表优先、无前缀再按 ProducerId 词法匹配"是唯一自洽读法。前缀互斥已断言，匹配确定性有保证。
   - **边界注记（非阻断）**：单段名字若恰好以保留前缀开头（如假想的 producer 名 `act_ingester`）会被 parse_id 判为 ActionInstanceId。parse_id 是词法诊断入口而非注册闸门（producer 唯一性归 P2 注册表），此边界影响极小；如需收紧只需改 parse_id 规则（如要求 producer 至少一段含点或引入保留字冲突检查），**不触碰 schema**，非 breaking。

### B.2 T03：EntityView 内部 components 字段名最小落位；StateDomainId TYPE_CHECKING 前向引用 —— **接受**

1. 设计 §3.2 对 EntityView 只给出 4 个字段 + 2 方法与"内部持有 MappingProxyType 深冻结视图"的描述，未指定内部字段名。实现以 dataclass 字段 `components`（缺省空 MappingProxyType）落位，值深冻结（`_freeze_value` 递归）、frozen dataclass 不可赋值、公共方法面恰为 `component_types`/`get_component`（`test_entity_view_public_surface_is_identity_plus_two_queries` 静态钉死）。
   - **注记**：设计用词"内部"而实现为公开属性（dataclass 无真私有字段）；若日后要收窄为私有需微调构造签名——但 EntityView 的构造入口是 `WorldState.entity_view()`/`_from_record`（私有），消费者只读，风险低。接受为最小落位。
2. `components.py` 以 `TYPE_CHECKING` 前向引用 `effects.StateDomainId`（`ComponentSchema.authority_domain`）：本人验证运行时无循环 import（effects → components 单向），frozen dataclass 不求值注解；`ComponentSchema(authority_domain=StateDomainId("physics.kinematics"))` 运行时构造正常。落位正确。

### B.3 T04：§5.7/§5.3 矛盾裁定（ProposedEffect 不带 cascade）；progress ge/le；Transaction 附加 C5 与 effect_id 唯一 —— **接受**

1. **cascade 矛盾裁定**：设计 §5.7 字面"每个 DomainEvent/ProposedEffect/Transaction 均可携带 CascadeContext"与 §5.3 字段清单（无 cascade 字段）矛盾；T04 按 **Spec §16.1**（权威、字段清单里没有 cascade）裁定不加字段、级联因果由 `cause_ids`（CauseRef 链）承载、`CascadeContext` 落在 DomainEvent/Transaction——裁定正确。级联链可完整重建（effect→cause_ids→触发事件→事件携带 cascade），无数据丢失。
   - **跟进条件 C1（文档级）**：设计文档本身应在 G1 人工冻结前出 errata 消除 §5.7 的矛盾表述（纯文档修订，非 breaking）。
2. **progress ge/le**：设计 §5.2 注释明写 `progress [0,1]`，`Field(ge=0.0, le=1.0)` 是忠实落地（与 confidence 同款），非私自加严。接受。
3. **Transaction 数据层附加规则**：
   - C5（事务内 effects 共享 transaction_id/commit_revision 且与事务自身一致）与 effect_id 事务内唯一（KBC-2 防线）：设计 §7.4 C5/C7 原文只要求"可检测/一致性检查"，实现升格为**构造期拒绝**。方向是"更严"且完全在 §5.6"仅可如此表达"的语义内（重复 effect_id 的数据本就是 KBC-2 事故形态，不存在合法用途）；round-trip 后重校验，不会产生"已存数据无法重载"问题。接受。
   - ABORTED ⇒ 无 revision 无 effects：部分提交不可表达，C4 固化。COMMITTED ⇒ effects 非空（空事务不消耗 revision）：设计 §5.6 不变量 1 明文。均与设计一致。

### B.4 T02：CONTRACT_SCHEMA_VERSION 落 state.py；键/记录一致性双 validator；RuntimeState 无 _with_* 缝隙 —— **接受**

1. 常量单源：`state.py` 定义、`snapshot.py` import 复用、包级再 re-export，三处同一对象（`test_contract_schema_version_single_source` + closeout 同款断言；本人复核）。T02 先行（§1.2 执行次序）导致常量前移至 state.py 是依赖使然，且避免了双源复写风险。接受。
2. 双 validator（`WorldState._check_entities_key_consistency` / `RuntimeState._check_active_action_key_consistency`）：纯数据完整性检查，拒绝"键与记录身份分裂"的畸形数据（KBC-3 同型陷阱的数据层防线），不改字段形态、round-trip 幂等。属于设计 §3.5 纪律的自然延伸，接受。
3. RuntimeState 无任何 `_with_*` 缝隙（本人 grep + `test_no_seams_or_scheduler_methods_in_p1`）：P1 阶段 RuntimeState 无变更语义，缝隙留给 P3/P4 按需设计——正确克制。

### B.5 T05：check_snapshot_versions 公开函数（J6）；float 有限性加严 —— **接受**

1. `check_snapshot_versions(snap) -> tuple[str, ...]` 覆盖四枚版本标记（信封格式 / WorldState.schema_version / RuntimeState.schema_version / 全局契约代），空元组=匹配，篡改任一标记均有结构化报告（J6 四个篡改用例 + 多重不匹配合并报告）；`restore_snapshot` 本身不做版本门禁（迁移行为归 P8）——与设计 §6.3"P1 至少给出校验函数"精确一致。
2. `assert_json_clean` 拒绝 NaN/±inf：严格 JSON 无对应字面量，Python `json` 默认 `allow_nan=True` 会静默产出非标准 token，破坏"加载端兼容任意合法 JSON"与跨语言互通。该加严不收窄任何合法契约数据（NaN/inf 从来不是合法 JSON 值），且在 J1 全模型样本上执行。接受。

### B.6 T06：C7 检查器落测试侧；snapshot 同名遮蔽豁免；骨架测试修订范围 —— **接受（附条件 C2）**

1. **C7 `check_transaction_references` 落测试侧**：
   - 实现按设计签名与语义（纯函数、`(state, txn) -> tuple[str, ...]`、`missing_entity`/`stale_revision`/`duplicated_effect_id` 三项、只报告不处置），15 例测试含纯函数性（前后 model_dump 不变）、结构化输出、单向 stale 语义、ABORTED 空转、"检查确实读取 state"对照。质量合格。
   - 落位偏差已披露：设计 §8 非目标 5/§10 表将其定位为 **core 数据底座**（P2-T04 依赖项），T06 受任务包写入白名单约束（不得改 core 契约模块、不得新增 core 模块）只能落测试侧。**判定：接受，附条件 C2**——P2-T04 任务包定义时必须包含"逐字晋升入 core（依赖面仅 WorldState/Transaction/is_stale/EntityTarget，迁移零风险）"，否则设计 §10 承诺的 P2 依赖将悬空。
2. **snapshot 同名遮蔽豁免集 {snapshot}**：若把 `snapshot()` 函数绑包属性会覆盖子模块属性（bpo-30024），破坏 `import src.engine_v2.core.snapshot as m`。豁免经 closeout **机械化断言**（与子模块撞名的导出集合必须恰为 {snapshot}；`__all__` == 13 模块 `__all__` 并集减豁免；每个 re-export 与来源模块属性 `is` 同一对象）。本人独立验证 `core.snapshot` 是模块、`core.snapshot.snapshot` 是函数。判定：接受（属稳定的 API wart，已有测试钉死；改名函数/模块反而违背设计 §1.1/§6.3）。
3. **骨架测试修订范围**：git diff（`105afd5..603535e`）核实——`tests/test_engine_v2_skeleton.py` 仅放宽 `core/__init__.py` 允许 re-export 语句与 `__all__` 清单（AST 级：只允许 `src.engine_v2.core.*` 绝对 import 或 level-1 相对 import + 单一 `__all__` 字符串常量赋值），其余 13 子包 + 根包"仅 docstring"纪律不变；同一 commit 对 core 的改动仅 `__init__.py`/`serialization.py`/`snapshot.py`（T05 交付物）——**修订范围最小且与设计 §0.4 预告一致**。接受。

---

## C. 架构红线抽查

### C.1 Kernel 无标准 RPG 字段 / provider / model —— 无违规

- 全模块 grep（hp/health/inventory/mana/exp/level/attack/damage/npc/player_percept/narrative_history/event_log/attribute_deltas/game_time/provider/api_key/model_name/gpt/deepseek/claude）：**schema 字段零命中**；命中项全部为 docstring/注释（ContextProvider 是 Spec §13 概念引用、"health"仅作词法示例、game_time 仅在 KBC-4 防线说明中出现）。
- `resolved_model` 仅作为 `LLM_CALL_PAYLOAD_KEYS` 冻结键名出现（设计 §4.4 按 Spec §31.3 明文要求预留的 trace 记录键名约定），**不是** provider/model 字段；credential/api_key 永不入键集合（K8 合规）。P1 不产生 llm_call 记录。
- 类型标识符族（Component/Action/Effect/Event/StateDomain）全部为名字型 typed str，Kernel 零内置取值（Plan §10 强制约束合规）。

### C.2 无绕过 frozen/私有缝隙的公共写路径 —— 合规（附 P2 注意项）

- 22 个 ContractModel 子类全部 `frozen=True + extra="forbid"`（机械化参数化断言覆盖全部模型）；字段赋值抛 ValidationError（S5/E3 参数化）。
- 私有构造缝（`_with_world_revision`/`_with_entities`/`_with_world_variables`/`_with_scenario_state`/`_with_components`/`_build_entities`/`_from_record`/`_freeze_value`/`_entity_ids_with_component`）：全部下划线前缀、**不在任何模块 `__all__`**、不在包级 re-export（本人 grep `__init__.py` 零命中 + `test_seams_are_private_not_exported`、closeout 的 `__all__` 一致性断言）。
- `WorldState` 公共方法面恰为 4 个只读门面（`test_public_surface_is_four_readonly_facade`）；EntityView 公共面恰为 2 查询方法；EntityRecord 无 mutator。
- **P2 注意项（非 P1 缺陷，设计已自认 advisory）**：pydantic `BaseModel` 自带的 `model_copy(update=...)` 与 `model_construct(...)` 会绕过全部校验器与 frozen 语义——本人实测可把 ABORTED 事务 copy-update 出 `commit_revision`（违反原子不变量）。设计 §3.5/D-15 已明确"强制性由 P2 写屏障 + reducer-only 公共 API 承担"，且设计 §3.5 本身将 `model_copy(update=...)` 列为 P2 reducer 可用路径之一。**条件 C3**：P2-T01 写屏障任务包必须显式覆盖这两条逃逸路径（reducer 外禁用/审计），否则 Transaction 原子不变量在公共 API 层可被绕过。

### C.3 状态模型符合 ADR-003 —— 合规

- WorldState（权威世界事实）/RuntimeState（运行时控制）分离，字段集分别与 Spec §8.1 六项内容、§8.2 清单一一对应（§8.1 六项落位表 + 程序化字段集断言）。
- BackendState 仅以 `BackendStateRef`（引用 + 三能力声明）进 RuntimeState/快照，真实 checkpoint 外置（D-10，ADR-003"不进入 WorldState 快照"合规）；`checkpointable` 等三声明默认 False。
- TraceState 以 `TraceRecord`（单一信封 + kind 判别 + 开放 payload，D-11）承载，**不含任何状态本体字段**（S2 程序化断言：WorldState/RuntimeState 无 trace/view 字段、TraceRecord 无 entities/scheduler 等状态字段）。
- ViewState 不在 P1 定义（P10 职责）。
- 无 v1 transient/presentation 混入：`player_percept`/`narrative_history`/`event_log`/`attribute_deltas`/复合 `game_time` 均不存在；KBC-4 防线落地为"RuntimeState 仅单一 `logical_tick` + 日历时间为 WorldState 结构化数据 + `_with_world_variables` 整体替换无缝隙"（专测 `TestCalendarTimeKbc4`）。

### C.4 设计文档 ↔ 实现字段级比对 —— 完全一致（含顺序），未发现未披露偏差

本人独立脚本比对 22 个 pydantic 契约模型的字段**名称与顺序** vs 设计文档代码块（ProposedEffect/CommittedEffect/EntityTarget/StateDomainTarget/ActionProposal/ActiveAction/ActionTiming/FallbackSpec/DomainEvent/Transaction/EntityRecord/EntityRef/ScenarioState/WorldState/RuntimeState/RngState/ScheduledEvent/ActorWakeup/BackendStateRef/TraceRecord/Snapshot/Provenance 族）：

```
FIELD-SET COMPARISON (pydantic models): ALL MATCH (names and order)
ComponentSchema (frozen dataclass): component_type/version/description/payload_model/authority_domain ✓
EntityView (frozen dataclass): entity_id/entity_class/tags/revision/components ✓
```

与 T04 各 `test_field_set_matches_design_doc` 相互印证。对照 **Spec** 原文的四处具体化（cause_ids: list[str]→list[CauseRef]、target union→tagged union、timestamp→logical_tick+wall_time、ActiveAction 增 instance_id/status/§9 字段）全部在设计文档中有决策编号与依据，属"设计文档对 Spec 的合法具体化"，实现忠实于设计文档。**结论：文档-代码一致性问题为零；全部实现侧偏差均已披露并在 B 节复核。**

---

## D. 非阻断观察与风险（供后续 Phase 参考，均非 breaking）

| # | 观察 | 影响 | 建议归属 |
|---|---|---|---|
| 1 | `model_copy(update=...)` / `model_construct` 绕过全部数据不变量（含 Transaction 原子性、键一致性） | P2 前为 advisory（设计自认）；若 P2 写屏障不覆盖则 K2 出现缝隙 | **P2-T01**（条件 C3） |
| 2 | typed ID 的 schema 层不做前缀/词法校验：`EntityId` 字段接受 `EffectId` 实例或错误前缀串并静默重建（D-1 承诺的是"可区分"，非"自动拒绝"） | P2 validation 必须显式做 ID 种类/前缀校验（parse_id 已备） | P2-T04 |
| 3 | C7 检查器在测试侧，设计 §10 将其列为 P2-T04 依赖 | 依赖悬空风险 | **P2-T04**（条件 C2） |
| 4 | `snapshot()` 函数不能从包根导入（同名遮蔽豁免） | API 易用性 wart（`from src.engine_v2.core.snapshot import snapshot` 可达，测试钉死） | 无需行动；如日后缓解须 Gate |
| 5 | `EntityView.components` 为公开 dataclass 字段（设计用词"内部"） | 若日后改私有属 minor breaking；当前构造入口受控、frozen、有表面断言 | P2/P10 消费时注意只读纪律 |
| 6 | `WorldState._with_*` 每次全量 `model_dump(mode="json") -> model_validate`，O(状态体积) | 大世界高频 reducer 的性能考量（非正确性） | P2-T06 可增补高效构造路径（additive，非 breaking） |
| 7 | pydantic 2.13 lax 模式下 `bool`/整值 `float` 可进 `Revision` 字段（与裸 `int` 字段行为一致，JSON 侧归一为整数） | 上游基线行为，round-trip 无损 | 无需行动 |
| 8 | 设计文档 §5.7 与 §5.3 矛盾未消除；§2.3 交叉引用笔误（"§6.1/§6.3"应为 §5.1/§5.3） | 文档内部一致性 | **冻结前 errata**（条件 C1） |
| 9 | pydantic 2.13 自身 import 传递性拉入 socket/subprocess | 第三方内部行为，B1/B3 口径不受影响；若未来要求全链路零 IO import 需在 B2 口径中处理 pydantic 预载 | 无需行动（记录在案） |

---

## E. Blocking issues 与最终裁定

### Blocking issues

**无。** G1 判定标准（"高级 reviewer 没有发现后续必须 breaking change 的明显问题"）满足：全部契约的 public 字段/类型/前缀/序列化形态经独立核验与设计文档逐项一致，P2+ 所需数据承载齐备，未发现任何将迫使后续 Phase 修改 public contract 的缺陷。

### Verdict: **APPROVE_WITH_CONDITIONS**

条件（均不要求 P1 返工）：

- **C1（G1 人工冻结前，文档 errata）**：由 Contract owner 修订设计文档——消除 §5.7 与 §5.3 关于 ProposedEffect 是否携带 CascadeContext 的矛盾表述（按 T04 已裁定口径：不携带，级联由 DomainEvent/Transaction 的 CascadeContext + cause_ids 承载）；顺带修正 §2.3 的交叉引用笔误。
- **C2（P2-T04 任务包定义时）**：将 `check_transaction_references` 从测试侧晋升入 core（逐字迁移已测试实现，签名与语义不变），兑现设计 §10 对 P2-T04 的依赖承诺。
- **C3（P2-T01 任务包定义时）**：写屏障范围显式覆盖 pydantic 逃逸路径（`model_copy(update=...)`、`model_construct`），保证 Transaction 原子不变量与键一致性在全部公共路径不可绕过（K2 闭合）。

---

## 附：审查执行记录

| 命令 | 结果 |
|---|---|
| `.venv/bin/python -m pytest tests/engine_v2 tests/test_engine_v2_skeleton.py -q` | **544 passed**（0.52s） |
| `.venv/bin/python -m pytest -q`（全仓） | **989 passed**（3.52s） |
| `.venv/bin/python -m pytest tests/engine_v2/core/test_import_boundary.py tests/test_engine_v2_skeleton.py -q` | 11 passed |
| 独立 fresh-import 黑名单检查（子进程） | langgraph/langchain/openai 等 provider SDK 零命中 |
| 独立 round-trip 脚本（36 样本：全模型形态 + 12 TraceKind + 中文/datetime/空容器/union 双分支） | 全部值相等 + 类型保持 + JSON 纯净 |
| 独立 revision/is_stale/parse_id 断言脚本 | 全部符合 Spec §9 与设计 §2.2/§2.3 |
| 独立字段级比对脚本（22 pydantic 模型 + 2 dataclass） | 名称与顺序全部一致 |
| 逃逸路径探针（model_copy/model_construct/bool→Revision/跨种类 ID） | 行为已记录（§D.1/2/7） |
| `git log/diff`（只读） | T06 修订范围核实：骨架测试最小放宽 + 无 core 契约模块改动 |

*本报告为 P1-T07 唯一写入文件；未改动 src/、tests/、docs/（除本报告）任何文件，未执行任何 git 写操作。*
