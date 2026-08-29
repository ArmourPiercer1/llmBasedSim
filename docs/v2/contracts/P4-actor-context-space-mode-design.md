# P4 Actor / Context / Space / Mode Design — Phase 4 Actor 决策面 / 空间语义 / 游戏模式 实现规范（Spec B）

- **任务**: P4-DESIGN（Phase 4 — Actor / Context / Space / GameplayMode 架构设计，Plan §13；先例：P2-DESIGN / P3-DESIGN）
- **文档地位**: 等价于 Plan §13「Phase 4 — Actor / Context / Space / GameplayMode」（Plan:552-582）的字段级/函数级实现规范。任务归属 T01/T04/T06/T09 → Q27、T10 → GFlash（Plan:560-571）：Q27 按本文档可"纯执行"实现 P4-T01/T04/T06/T09；QMax 实现 P4-T02/T03/T05/T07/T08 时无需再做架构判断；GFlash 执行 P4-T10 测试时无需再做场景裁剪；执行路由由 L5 统一覆写为 qiyuan-self（路由声明）。全部决策编号钉死为 **D-P4-01~D-P4-17**（§4）；全部行号引用已对冻结源逐行核验（P1 @ `603535e` / P2 @ `f49ecd5` / P3 @ HEAD `ab0c7d2`），引用格式 `file:line`；Gate 断言共 **19 条**（§5.4，G4-1~G4-6 = 3+3+3+3+4+3）。
- **路由声明（2026-08-20 人工路由覆盖）**: P4-T01~P4-T10 全部路由 **qiyuan-self（qwen3.8-27b）**；Plan §13 任务表"默认模型"列（Q27/QMax/GFlash，Plan:560-571）不生效。
- **分支**: `architecture-v2`（HEAD `ab0c7d2`，P3 门禁已闭合 PASS）
- **权威输入**:
  - `docs/plans/llmBasedSim_Engine_Architecture_v2_Spec.md`（下称 **Spec**）§4（K1–K8，L242-339）、§8.1/8.2/8.3（L542-605）、§12（L806-868）、§13（L872-909）、§24（L1341-1392）、§25（L1396-1452）
  - `docs/plans/llmBasedSim_Architecture_v2_Refactor_Development_Plan.md`（下称 **Plan**）§13（L552-582：目标 L556、任务表 L560-571（表头 L560，数据行 L562-571）、G4 L573-582）
  - `docs/v2/gates/G3-gate-report.md` §7（L160-171，移交 P4 的接口与约束十条）
  - `docs/v2/contracts/P3-scheduler-time-action-design.md`（下称 **P3 设计**，体例先例：§1.2 L48 逐条回应、§3.10 L780-792 波次、§4 决策清单 L816-1040、§5 Gate L1044-1111、§10 L1409-1421）
  - 冻结源：`src/engine_v2/core/*`（P1 13 + P2 6 + P3 7 = 26 子模块）、`tests/engine_v2/core/*`
- **审查历史**: R1 盲审（4 审查者：2 阻塞 / 1 补充内容 / 1 通过；2 BLOCK + 9 SUPP + DOC 全量修复于 R1 修复轮）→ R2 盲审（4 审查者：1 阻塞 / 1 补充内容 / 2 通过；1 BLOCK + 1 SUPP + 17 DOC + 1 INFO 修复于 R2 修复轮）→ R3 盲审（4 审查者：2 补充内容 / 2 通过；2 SUPP + 6 DOC + 3 INFO 修复于 R3 修复轮）→ R4 盲审（A 补充 1S+1DOC+3INFO / B 阻塞 1B+4DOC+1INFO / C 通过 1DOC / D 通过 1INFO；Leader 裁定 + R4 修复轮完成）→ R5 盲审（4/4 通过，0 BLOCK / 0 SUPPLEMENT / 0 执行失败；残留 3 DOC 按 G3 DOC-1 先例以免费文档级闭合补丁应用、不复审）→ 设计闭合

**体例注**：本文档沿用 P3 设计体例——§1.2 对 G4 六条逐条回应、§1.4 对 G3 §7 十条逐条回应、§3 文件清单 + 逐模块字段级规格 + `__init__` 同步机制、§4 决策清单（每条：问题/备选/选择/理由与一致性）、§5 核心 Gate 场景（fixture 逐字 + 步表 + 分支表 + 断言清单 + "不得"清单）、§6 测试规格（逐模块 + 对抗 A1-A8）、§8 自检（K1-K8 矩阵 + 台账 + 偏离披露 D1-D6）、§9 勘误（纯追加，初版无）、§10 未决问题（初版：无 + 裁定说明）。

## 1. 目标与范围

### 1.1 目标

形成 **Runtime 世界语义层**（Plan:556 逐字："形成 Runtime 世界语义层，但仍不接实际云模型"）。四个语义面：

1. **Actor 决策面**（`behavior_policy.py` + `context_provider.py` + `capability.py`）：`ActorDecisionContext` 认识论边界 + `Capability` 授权/核查 + `BehaviorPolicy`/`PlayerPolicy` 协议与执行门面（Spec §12/§13）；
2. **标准 Observation / Knowledge / Memory 骨架**（`knowledge.py`）：数据契约 + 组件载荷编解码——P1 `state.py:255-257` 逐字预留："knowledge / belief components → **组件**（``entities[*].components`` 中注册的 knowledge 类组件；Kernel 无内置，P9 knowledge 模块注册组件类型，避免"标准 RPG 字段进 Kernel"）"；P4 落位裁定（P4 承接组件类型注册、P9 复用）见 §8.5 偏离 D6；
3. **空间语义**（`space.py`）：named `SpatialDomain` + `SpaceBackend` 协议 + `GraphSpace`/`GridSpace` 参考实现 + Entity 多空间映射（Spec §24）；
4. **游戏模式**（`gameplay_mode.py`）：`ModeOverlay` + per-property 合并 + `ModeChangeRequest` 解析器——纯 RuntimeState 簿记（Spec §25）。

**P4 不接云模型**（Plan:556）：6 个新模块零 provider/LLM/asyncio/random/datetime/直接-json 导入（§3.4 黑名单全部 ✗，import 边界自动覆盖）；`BehaviorPolicy.decide` 为**同步**纯函数（D-P4-01）；LLM Director 的接入点是 `BehaviorPolicy`/`ModePolicy` 两个协议（P5 实现策略内容，D-P4-16）。

### 1.2 G4 六条逐条回应（Plan:577-582；先例：P3 设计 §1.2 L48 对 Plan §12 三条"不得"的逐条回应）

| # | G4 条款（Plan 行） | P4 实现手段 | Gate 断言锚点（§5.4） |
|---|---|---|---|
| G4-1 | "Alice 不知道她没有 Observation/Knowledge 的 Bob 偷窃事件"（Plan:577） | 认识论边界 = **构建期物化**：`ActorDecisionContext` 只持物化值、不持 `GuardedWorldState` 引用（CX-INV-4，D-P4-05）；alice 无 observations/knowledge 组件 → `observations == ()` 且 `knowledge is None`；可见集 = {self} ∪ 观察对象 ∪ 知识引用 ∪ local 邻域（CX-INV-2/3）；theft 已在 R1 提交入世界（事件在 WorldState 侧），与 alice 上下文完全隔离 | G4-1①②③ |
| G4-2 | "自定义 Policy 不能因为更换 Prompt 而获得 global read"（Plan:578） | 唯一授权面 = `CapabilityTable`（K4：Prompt 不能定义权限，Spec:295）：`DefaultContextProvider(prompt=...)` 的 Prompt 为不透明参数、构建期从不查询（CX-INV-5）；`granted_capabilities` 回显 = 授权表 ∩ 上下文填充字段；G4-2 双 provider（baseline/override prompt）上下文全等 + 阳性对照（显式 global 授权 → `global_entity_views` 非 None）；A2 补静态签名扫描 | G4-2①②③ + A2 |
| G4-3 | "一个 Entity 可拥有 overworld + tactical 映射"（Plan:579） | `spaces` 组件（`SPACES_COMPONENT`）承载 per-domain 映射（S-INV-3：一 domain 一 position）+ `SpaceRegistry`（S-INV-4/5）；gate fixture 中 alice/bob 各持 `{"overworld": grid 坐标, "tactical": 图节点}` 双映射；G4-3 断言解码保序、`entity_domain_positions` 双域、tactical 跨节点 BFS 距离 | G4-3①②③ |
| G4-4 | "Dialogue + Tactical 可同时 active"（Plan:580） | `RuntimeState.active_modes`（state.py:223，排序 list 即集合）+ `mode_context`（state.py:224，per-mode 上下文 dict）；`apply_mode_change` 增量激活（D-P4-15）；Spec:1413 "多个 mode MAY 同时激活" 的直接落地 | G4-4①②③ |
| G4-5 | "TimePolicy 冲突有明确 winner"（Plan:581） | `merge_modes` per-property 单胜者语义：非空值中 argmax `priority`，平手 → casefold 较小 `mode_id`（D-P4-14）；`time_policy` 字段整对象替换（Spec:1428 "time_policy → priority winner"）；`activated_systems` 并集（Spec:1426）、动作可用性 deny > allow 交集 > none（Spec:1424-1425 "union/intersection"，P4 取交集 = 保守侧） | G4-5①②③④ |
| G4-6 | "mode change 不复制 WorldState"（Plan:582） | `apply_mode_change(*, request, runtime, registry)` **无 WorldState 参数**（M-INV-3）；内部唯一重建路径 = `rebuild_runtime`（clock.py:151，RuntimeState-only）；G4-6 四重断言：`inspect.signature` 参数集 + world 对象同一性 + revision 不变 + 复制点 monkeypatch 全部 raise 仍通过（Spec:1409 "切换 mode 不创建第二份 WorldState"） | G4-6①②③ |

### 1.3 范围边界（P4 做 / 不做）

**做**（归属显式登记）：

- 6 个新 core 模块 + **59 个导出**（capability 6 / knowledge 11 / space 18 / context_provider 6 / behavior_policy 4 / gameplay_mode 14，§3.1/§8.3）；
- `core/__init__.py` 导入块与 `__all__` **纯增量**同步：249 → **308**（§3.11 同步机制 + §8.3 台账逐名相邻位）；
- conftest P4 节 + 6 个模块单测 + Gate 场景 + 对抗 + 集成测试（`P4_TEST_FILES` = 10 文件，§3.12 白名单）；
- `test_closeout.py` / `test_import_boundary.py` 锚点同步（26 → **32** 子模块，§3.11）；
- **非阻塞中断后的 NPC 重提案：接缝 + 契约 + 集成证明**（本文档裁定，D-P4-16）：P4 提供 `BehaviorPolicy.decide` 接口、context 的 `wake_reason` 字段、具体 `PolicyWakeupHook`（§5.1 conftest 逐字），T10 集成测试端到端证明（wakeup → hook → 重提案 → `submit_proposal` 全管道 ACCEPT → 新实例 + `checkpoint_skipped_interrupted` 诊断 + 显式 `resume_action`/`abort_action` 两条外部收敛路径）；**重提案策略内容（中断后"决定做什么"）= P5**。机械层 → P4，内容层 → P5（与 G3 移交 5 named_triggers → P5 同逻辑，G3:166）。
- G3 移交 1（G3:162）"REPAIR 分支的 actor 重提案策略是 P4 域"的落实口径 = **仅接缝**：`RevalidationOutcome.REPAIR`（revision.py:100）仍不由 scheduler 产生——P3 `_revalidate` 钉死 `allow_rebase=False`（scheduler.py:1661-1663），故 scheduler 路径结果域 = {ACCEPT, REJECT}，stale 重提案 ⇒ **REJECT**（非 REBASE；A7b 断言）；P4 不产生 REPAIR 结果，亦不把结果域钉死为固定基数词表（移交 1 原文纪律）。

**不做**（归属显式登记，与 P2/P3 同纪律）：

- 真实 LLM / 云模型接入、PromptAssembler 实现、token/预算/成本（P5/P8；Plan:556）；
- 重提案策略内容（NPC 中断后的行为选择逻辑）= P5（D-P4-16）；
- 生产 named trigger 装配（scenario 触发器接线）= P5（G3 移交 5，G3:166；P4 Gate 沿用 D-P3-26/27 幂等 stub + 显式空 `trigger_registry` 单路化）；
- `RuntimeState.backend_refs`（state.py:227）真实后端引用 = P5/P8（G3 移交 7，G3:168：P3 保持未触碰，P4 沿用不触碰）；
- `RuntimeState.rng_state`（state.py:225）= P8（G3 移交 7）；
- renderer / UI layers 的 composition 合并（Spec:1427/1430）= P8 表现层；P4 的 `ModeOverlay.input_policy` 为不透明 `JsonValue` 直通（M-INV-6），P4 不解释（§10 裁定说明 3）；
- `scheduler_fingerprint` 输入面扩展 = P5 义务（G3 移交 2，G3:163）；P4 真实接线恰好改动一个 Scheduler 构造输入——`wakeup_hooks`（`make_p4_scheduler` 装配 `PolicyWakeupHook`，scheduler.py:615）——但该项为指纹中性：`wakeup_hooks` 不在 `scheduler_fingerprint` 输入面（registry + time_policy + boundaries，scheduler.py:429-452）内（构造输入面，结构排除）；「4 个 callable 配置面」（named_triggers / trigger_registry / wakeup_hooks / condition_resolvers）为 G3:151（R4）口径——E-P3-39③ 原文（P3:1384-1387）点名 named_triggers/trigger_registry，另两面为构造输入面结构排除；指纹输入面零变化；P4 取 G3:163「在测试层显式披露」分支（偏离 D5 + §6.2 移交 2 行）；
- Spec §12.3（Spec:840-868）的 CharacterDefinition / CharacterState 两预设（identity / baseline traits / background / core values / emotion / goals / relationships 等）= P5 内容层，P4 不落地（与 D-P4-16 机械层→P4 / 内容层→P5 分层一致；P4 knowledge.py 只落地 §12.3 的 KnowledgeState / Memory 机械容器——`KnowledgeState` 容器类 + `MEMORY_COMPONENT` 组件槽位（原始载荷，D-P4-09），见 §3.6）。

### 1.4 G3 §7 十条移交逐条回应（G3:160-171）

| # | 移交（G3 行） | P4 回应 |
|---|---|---|
| 1 | REPAIR 扩展（G3:162） | §1.3 第 6 条：P4 = 接缝 + 集成证明；P4 scheduler 路径永不产生 REPAIR（stale ⇒ REJECT，scheduler.py:1661-1663）；A7 断言用 outcome 值不用集合基数 |
| 2 | `scheduler_fingerprint` 输入面（G3:163） | P4 真实接线恰好改动一个构造输入（`wakeup_hooks`，scheduler.py:615），其不在 scheduler_fingerprint 输入面（registry + time_policy + boundaries，scheduler.py:429-452）内（构造输入面结构排除；「4 个 callable 配置面」为 G3:151 R4 口径，E-P3-39③ 原文 P3:1384-1387 点名 named_triggers/trigger_registry）→ 指纹零变化；P4 取「在测试层显式披露」（§6.2 移交 2 行）；P5 接入真实策略时扩展或披露（§1.3 不做末条 + 偏离 D5） |
| 3 | WakeupHook 协议接缝（G3:164） | P4 落地首个真实消费者：`PolicyWakeupHook`（§5.1 逐字，concrete 于 `BehaviorPolicy` + `DefaultContextProvider`）+ T10 集成证明；hook 异常 → `SchedulerWakeupError` 整 tick 原子回滚为 P3 既有行为（scheduler.py:1174-1177），A7c 复用 |
| 4 | NPC 非阻塞中断收敛（G3:165） | P4 提供收敛路径 ①（wakeup 重提案，集成分支 A 端到端）与路径 ②（显式 abort，§5.4 R7）；自动收敛仍不提供（设计使然，R6 断言终态旧实例保持 INTERRUPTED） |
| 5 | named_triggers 生产注册表（G3:166） | 不做（P5）；P4 Gate fixture 幂等 stub + 显式空 `trigger_registry`（D-P3-26/27 纪律沿用，§5.1） |
| 6 | RESUMED 边（G3:167） | 集成分支 B 证明生产触发路径的显式形态：`scheduler.resume_action`（scheduler.py:1595-1613）→ t12 RESUMED 边；分支 A 证明重提案路径（新实例，不复用旧实例）——两路径互斥口径见 §5.3 |
| 7 | P1 字段未触碰面（G3:168） | `active_modes`/`mode_context`（state.py:223-224）**P4 启用**（M-INV-3/4/5 口径）；`backend_refs`/`rng_state` 仍不触碰 |
| 8 | 冻结与台账沿用（G3:169） | P4 纯增量：6 新模块，既有 26 子模块代码零改动（唯一触碰 = `__init__.py` 导出块 + `__all__`）；249 → 308（§8.3） |
| 9 | G0 遗留（G3:170） | 与 P4 无依赖（v1 boot proof 待 API key） |
| 10 | G4 门禁参照（G3:171） | §1.2 六条逐条回应（体例沿 P3 设计 §1.2 L48）；断言锚点 G4-1~G4-6 共 19 条（§5.4） |

## 2. 总体设计

### 2.1 Spec 映射表

| Spec 锚点 | 内容 | P4 落点 |
|---|---|---|
| Spec:246（K1） | 唯一权威表示，派生表示不得反向写回 | `ActorDecisionContext` = guard 视图单向物化投影（D-P4-04/05），无写回路径；mode 合并为纯函数投影 |
| Spec:252（K2） | 变更必须走权威管道 | `apply_mode_change` 仅重建 RuntimeState（rebuild_runtime，clock.py:151）；P4 零 WorldState 效果（M-INV-3/4） |
| Spec:285（K3） | Authority 与 Commit 分离：有写权限 = 有权决定候选新状态，非直接写内存对象 | `CapabilityTable` 唯一授权面（D-P4-08）；一切写入经 commit 管道（`scheduler.submit_proposal` scheduler.py:1520-1522 / `apply_mode_change` 权威管道 D-P4-10）；JSON-clean 为 P1 §0.2 铁律 1 纪律（serialization.py:82-100），非 Spec K 条款；`INF_DISTANCE` 永不入 JSON（D-P4-12）；A2 |
| Spec:295（K4） | Prompt 不能定义权限 | `CapabilityTable` 唯一授权面；provider 的 `prompt` 参数不透明（CX-INV-5，D-P4-08）；A2 |
| Spec:305（K5） | Agent 是 Policy 不是 Engine | `BehaviorPolicy` 只有 `decide`（提议权）；任何提案必须经 `scheduler.submit_proposal`（scheduler.py:1520-1522）全管道 |
| Spec:315（K6） | provenance 必填 | `ActionProposal.provenance`（actions.py:188）、`ModeChangeRequest.source`（M-INV-2） |
| Spec:326（K7） | 运行时状态可检查 | 后端/注册表/表 = 构造期配置（INV-P4-3），frozen 视图；临时结果不持久化（D-P4-04） |
| Spec:330（K8） | Deployment 与 Game Project 分离：开发者不得固定 provider/model name/endpoint/credential，项目只声明能力需求 | 6 新模块零 provider/model/endpoint/credential（LLM 接入属 P5，Plan:556）；space/mode/capability 全为数据驱动配置，P4 无内置项目内容；确定性（零 random/time/asyncio，§3.4 黑名单；合并平手 casefold 决胜 D-P4-14）为 P4 自设纪律，非 K 条款 |
| Spec:554（§8.1） | knowledge / belief 为组件 | `knowledge.py` 三组件（observations/knowledge/memory）+ 编解码（D-P4-09） |
| Spec:575（§8.2） | gameplay contexts/modes ∈ RuntimeState | `gameplay_mode.py` 写 `active_modes`/`mode_context`（state.py:223-224） |
| Spec:581-605（§8.3） | BackendState：插件/数值后端私有状态；Backend MUST 声明 checkpointable/restorable/replayable | 声明义务对象 = 插件/数值后端（P9 动力学域）；P4 space/mode 后端为冻结无状态配置（D-P4-11），无私有 backend state、无声明义务；mode_context 为 RuntimeState 字段（state.py:223-224）非 BackendState——`ModeChangeResolution` 完整返回簿记结果、mode_context 可 roundtrip（A6，同类纪律自设断言） |
| Spec:818-825（§12） | `decide(context) -> ActionProposal` | D-P4-01：同步落地 + `Optional` 返回（偏离 D1） |
| Spec:833（§12） | PlayerPolicy 变体 | D-P4-02：marker Protocol + `bound_input_source` |
| Spec:842（§12） | 标准预设 SHOULD | `knowledge.py` = 标准骨架（SHOULD 非 MUST：作者 MAY 自定义，P4 不封锁） |
| Spec:858-866（§12） | KnowledgeState/Memory 概念树 | D-P4-09：beliefs × confidence 编码 uncertainty；Memory = 原始 JsonValue 列表 |
| Spec:876（§13.1） | Policy 不应默认读取 entire WorldState | CX-INV-4：context 无 guard 引用（D-P4-05） |
| Spec:884-892（§13.2） | 8 个能力 token | `Capability` str-Enum **逐字**：observation.read / knowledge.read / memory.read / world.read.local / world.read.global / physics.summary / physics.raw / trace.read |
| Spec:895-899（§13.2） | 普通 NPC 默认 3 项 | `DEFAULT_NPC_CAPABILITIES`（observation/knowledge/memory.read） |
| Spec:901-905（§13.2） | Director MAY 获得 global | 授权 = 配置面（grant 入表），非特权；G4-2 阳性对照 |
| Spec:909（§13.3） | PromptAssembler MUST NOT 自动获得未授权数据 | G4-2 + A2 |
| Spec:1345（§24.1） | 空间 MUST 可替换 | `SpaceBackend` Protocol（space.py）+ `make_backend` 工厂（D-P4-11） |
| Spec:1348-1350（§24.1） | `SpaceBackend(Protocol)` | 同名 Protocol 落位 |
| Spec:1354-1361（§24.1） | 6 种空间形态 | `SPATIAL_BACKEND_KINDS = {"graph","grid","hex","continuous2d","continuous3d","custom"}`（GraphSpace/GridSpace 实现，余为 reserved → `UnknownBackendError`，P5+ 扩展） |
| Spec:1365-1372（§24.2） | 多 named spatial domains | `SpatialDomain`（domain_id 命名 + backend_kind + parameters）；gate 用 overworld/tactical |
| Spec:1384-1390（§24.3） | Entity MAY 多空间 | `SPACES_COMPONENT` per-domain 映射 |
| Spec:1392（§24.3） | 每个 mapping 必须明确所属 domain | S-INV-3 + `decode_spaces` 拒绝 domain 缺失/重复 |
| Spec:1409（§25.1） | 切换 mode 不创建第二份 WorldState | M-INV-3 + G4-6 |
| Spec:1413（§25.2） | 多个 mode MAY 同时激活 | G4-4 |
| Spec:1424-1431（§25.3） | per-property 合并语义 | `merge_modes`（D-P4-14）：available_actions 交集（allow）/并集（system_activation）/time_policy 与 input_policy 胜者整值 |
| Spec:1433（§25.3） | 所有冲突策略 MUST 可检查 | `MergedModeConfiguration.winner_by_field` 记录每字段胜者 mode_id（G4-5 断言） |
| Spec:1439-1443（§25.4） | Script/RuleEngine/LLM Director/Plugin | `ModeChangeRequest.source` Provenance origin 映射（D-P4-15） |
| Spec:1448-1449（§25.4） | 统一输出 ModeChangeRequest | 同名数据类落位 |
| Spec:1452（§25.4） | 由 ModePolicy 解析 | `ModePolicy` Protocol = P5 接缝 + `DefaultModePolicy`（P4 缺省解析器） |

### 2.2 与 P2 / P3 的集成缝

| 缝 | P2/P3 既有契约（引用） | P4 消费方式 |
|---|---|---|
| 世界读 | `reducer.guard(world)`（reducer.py:1590）→ `GuardedWorldState`（reducer.py:1639）；门面 `entity_view`/`component_view`/`entities_with_component`/`has_entity`（reducer.py:1738-1754） | `DefaultContextProvider.build` 在**当刻 guard 视图**上物化（每 tick 新视图，G2 移交 2 纪律；context 不持 token，D-P4-05） |
| 提案管道 | `scheduler.submit_proposal(world, runtime, proposal)`（scheduler.py:1520-1522）→ revalidation（scheduler.py:1661-1663，`allow_rebase=False`）→ ACCEPT 入队调度 / REJECT 留痕（scheduler.py:1570-1572） | 重提案唯一出口；stale base ⇒ REJECT（A7b）；P4 任何代码不得绕过（A7a 管道断言） |
| 唤醒钩子 | `WakeupHook.on_wakeup(actor_id, view, clock, reason)`（scheduler.py:330-336）；`_drain_wakeup`：reason 查 `actor_wakeups` 记录（scheduler.py:1160-1163）、hook 异常 → `SchedulerWakeupError` 整 tick 原子回滚（scheduler.py:1174-1177）、返回提案逐条 `submit_proposal`（scheduler.py:1178-1182） | `PolicyWakeupHook` 实现协议（§5.1）；`view` = 当刻 guard（G2 移交 2）；`reason` = boundary_id（"B1"） |
| 中断语义 | `DecisionBoundary`（interrupt.py:108-135；`blocking` L133 / `interrupt` L134）；`CONDITION_KINDS`（interrupt.py:70-72）含 `event_type`；fired → ACTIVE+interruptible 迁 INTERRUPTED 并 re-anchor `base_world_revision`（scheduler.py:783-790）+ `enqueue_actor_wakeup(due_tick=tick, reason=boundary_id)`（scheduler.py:791-794） | gate fixture B1 = `event_type="core.set_component"` 非阻塞中断边界（§5.1） |
| RuntimeState 重建 | `rebuild_runtime(runtime, **updates)`（clock.py:151-158）——P1 唯一合法重建路径 | `apply_mode_change` 唯一重建通道（M-INV-5） |
| 时间值 | `LogicalClock.of(runtime)`（clock.py:88-94）、`TimePolicy`（scheduler.py:251-271，四字段 L268-271） | context 的 `tick` 来自 hook 传入的 `clock`（scheduler.py:1171-1173）；mode overlay 的 `time_policy` 字段类型 = 该 TimePolicy（整值替换合并） |
| 生命周期 | `resume_action`（scheduler.py:1595-1613，RESUMED 边 D-P3-07）/ `abort_action`（scheduler.py:1615-1624，INTERRUPTED→FAILED，ABORTED 边，仅返回 RuntimeState）；`checkpoint_skipped_interrupted` 诊断（D-P3-25） | 集成分支 B（显式 resume）/ §5.4 R7（显式 abort）/ R4（跳过诊断断言） |
| revalidation 词表 | `RevalidationOutcome` 四值（revision.py:98-101：ACCEPT/REBASE/REPAIR/REJECT）；`RevalidationDecision`（revalidation.py:63-91，`outcome` L87 / `reason` L88 / `details` L89） | P4 消费 `decision.outcome` 值（不钉集合基数，G3 移交 1）；scheduler 路径 stale ⇒ REJECT |
| 事件/组件/ID | `DomainEvent.event_type`（events.py:132）；`EntityTarget`（effects.py:163-175）；`ProposedEffect`（effects.py:197-226）；`new_observation_id`（ids.py:247）；`ComponentTypeId`（components.py） | gate fixture 偷窃 stub 双 `set_component` effect；P4 无新 ID 种类（D-P4-07） |

### 2.3 P4 不变量集（INV-P4-*）

- **INV-P4-1（认识论边界）**：`ActorDecisionContext` 的每个字段都是构建时刻 guard 视图的物化值；context 中不存在 `GuardedWorldState`/token/跨 tick 引用；context 构建后 guard token 释放不影响 context 可用性。违反 = `ContextInvariantError`（构造期检查，CX-INV-4）。
- **INV-P4-2（能力限定）**：context 中任一数据字段（observations/knowledge/memory/local 视图/global 视图/候选动作）当且仅当对应 capability 已授权且 `check_capability` 通过时被填充；未授权字段取缺省空值（None/()），**绝不**填充（K4 的数据表达）。
- **INV-P4-3（配置即状态边界）**：`SpaceBackend` 实现、`SpaceRegistry`、`CapabilityTable`、`ModeOverlayRegistry`、`ActionRegistry`（P3）均为构造期注入的不可变配置（K7：重对象 = 构造期配置）；P4 无模块级可变全局、无单例注册表（`BUILTIN_CONDITION_RESOLVERS` 型共享缺例除外且 P4 不设）。
- **INV-P4-4（双门正交）**：capability（决策面读授权）与 authority（世界写授权，authority.py:550 `check_authority`）相互独立：grant 不授予写权（A8a：授权齐备但无 authority 的提案仍被 P2 validation 拒绝），写权不蕴含读能力（A8b：有 authority 的 producer 其 context 仍按 grant 裁剪）。P4 六模块 import 图中 capability ↔ authority 零边（A8c AST 方向检查：仅 context_provider→capability，无任何模块 import authority 做读门）。
- **INV-P4-5（模式簿记封闭）**：P4 对 `RuntimeState` 的写面 = `active_modes`/`mode_context` 两字段（经 `rebuild_runtime`）；对 `WorldState` 的写面 = 空；对调度队列/簿记的写面 = 空。`ModeChangeResolution.effects` 在 P4 恒为 `()`（M-INV-4）。

## 3. 文件清单、命名与依赖

### 3.1 文件清单

| 文件 | 任务 | 动作 | 导出数 |
|---|---|---|---|
| `src/engine_v2/core/capability.py` | P4-T03 | 新增 | 6 |
| `src/engine_v2/core/knowledge.py` | P4-T04 | 新增 | 11 |
| `src/engine_v2/core/space.py` | P4-T05/T06/T07 | 新增 | 18 |
| `src/engine_v2/core/context_provider.py` | P4-T02 | 新增 | 6 |
| `src/engine_v2/core/behavior_policy.py` | P4-T01 | 新增 | 4 |
| `src/engine_v2/core/gameplay_mode.py` | P4-T08/T09 | 新增 | 14 |
| `src/engine_v2/core/__init__.py` | 同步 | 修改（6 个新导入块（5 个插入位，behavior_policy/capability 共位）+ `__all__` +59） | 249 → 308 |
| `tests/engine_v2/core/conftest.py` | P4-T10 | 扩展（追加 P4 节，既有节零触碰） | — |
| `tests/engine_v2/core/test_capability.py` 等 6 个模块单测 | T01-T09 | 新增 | — |
| `tests/engine_v2/core/test_p4_gate_scenario.py` | P4-T10 | 新增 | — |
| `tests/engine_v2/core/test_p4_adversarial.py` | P4-T10 | 新增 | — |
| `tests/engine_v2/core/test_p4_integration.py` | P4-T10 | 新增 | — |
| `tests/engine_v2/core/test_closeout.py` | 同步 | 修改（3 锚点，§3.11） | — |
| `tests/engine_v2/core/test_import_boundary.py` | 同步 | 修改（锚点 + 2 平行函数，§3.11） | — |

### 3.2 命名论证

- 模块名与 Spec 章节术语一一对应：`capability`（Spec:880 §13.2）、`knowledge`（Spec:858 §12 KnowledgeState 标准骨架）、`space`（Spec:1341 §24 Space Contract）、`context_provider`（Spec:874 §13.1 ContextProvider）、`behavior_policy`（Spec §12 BehaviorPolicy + `OriginKind.BEHAVIOR_POLICY` provenance.py:49 同源词）、`gameplay_mode`（Plan:552 标题 + Spec:1396 §25 GameplayMode）。
- **不设通用 "registry" 模块**（偏离 D2）：注册面随域内聚——`SpaceRegistry` ∈ space.py、`ModeOverlayRegistry` ∈ gameplay_mode.py、`CapabilityTable` ∈ capability.py。先例：P3 的 `ActionRegistry` 亦为单域注册表（action_registry.py:203）；P1 的注册面同理内聚（`ProducerRegistry` authority.py:295、`ComponentRegistry` components.py）。Kernel 无跨域注册中枢 = K1 单权威的数据面纪律。
- 类名与 Spec 逐字对齐处：`SpaceBackend`（Spec:1348）、`ModeChangeRequest`（Spec:1449）、`ModePolicy`（Spec:1452）、`BehaviorPolicy`/`PlayerPolicy`（Spec §12 L818-833）。

### 3.3 依赖图（模块级 import 边，全部指向 P1/P3 冻结模块或同相内更下层）

```text
P1 冻结底座: entity / components / ids / provenance / revision / serialization / state / reducer / events / effects
P3 冻结底座: actions / action_registry / scheduler(仅 TimePolicy 类型消费) / clock / interrupt(仅 fixture 消费)

capability.py          → entity(ContractModel, EntityId), actions(ActionTypeId), pydantic
knowledge.py           → entity(ContractModel), ids(ObservationId), components(ComponentTypeId), events(EventTypeId)
space.py               → entity(ContractModel), components(ComponentTypeId), pydantic
context_provider.py    → reducer(GuardedWorldState 门面), entity, actions, action_registry, capability, knowledge, space
behavior_policy.py     → actions(ActionProposal), context_provider(ActorDecisionContext, TYPE_CHECKING 亦可)
gameplay_mode.py       → entity(ContractModel), provenance, state(RuntimeState), clock(rebuild_runtime),
                         scheduler(TimePolicy 类型), effects(ProposedEffect 类型)
```

- 无环：context_provider → {capability, knowledge, space}；behavior_policy → context_provider；gameplay_mode 与前三者零边。
- behavior_policy **不** import reducer/scheduler（context 已物化，D-P4-05；K5：policy 无调度权）。
- context_provider **不** import scheduler（避免依赖图顶端回边；tick 由 `ContextBuildInput.tick` 显式传入）。
- gameplay_mode import scheduler 仅取 `TimePolicy` 类型（scheduler.py:251）——类型级依赖，运行时零调用（M1③ AST 核查：gameplay_mode 对 scheduler 的 import 名集 ⊆ {TimePolicy}）。

### 3.4 import 纪律（六模块黑名单，全部 ✗）

| 模块 | asyncio | random | datetime/time | uuid | json(直接) | os/subprocess | requests/urllib/http/socket | provider/LLM 面 |
|---|---|---|---|---|---|---|---|---|
| capability | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| knowledge | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| space | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| context_provider | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| behavior_policy | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| gameplay_mode | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |

口径（与 P3 §3.11 一致）：ID 一律经 P1 `ids.py` 工厂（如 `new_observation_id` ids.py:247；D-P4-07 无新 ID 种类）；JSON 校验经 P1 `serialization.py`（`assert_json_clean` serialization.py:82，测试侧）；`json` 标准库直接 import 禁止（P1/P2 纪律沿袭）。机械覆盖 = `test_import_boundary.py` 新增 P4 双函数（§3.11）+ 每模块单测内静态签名扫描。
**provider/LLM 面列机械口径**（M1④；§3.4/§5.5/§6.4 三处规范要素一致：§3.4 ≡ §5.5，§6.4 依 §3.4 引用）：封闭标识符集（封闭枚举，不得增删）= `openai`、`anthropic`、`langchain`、`litellm`、`ollama`、`gemini`、`gpt`、`claude`、`llm`、`provider`、`api_key`、`base_url`；匹配规则 = 源文本 casefold 后按**词边界**逐词匹配集合成员（正则 `\b`，大小写不敏感）；扫描对象 = P4 六模块全源文本（含 docstring/注释）；**0 命中**。

### 3.5 `capability.py`（P4-T03；6 导出）

```python
class Capability(str, Enum):
    """8 能力 token（Spec:884-892 逐字；str-Enum 保证 JSON/比较透明）。"""
    OBSERVATION_READ = "observation.read"
    KNOWLEDGE_READ = "knowledge.read"
    MEMORY_READ = "memory.read"
    WORLD_READ_LOCAL = "world.read.local"
    WORLD_READ_GLOBAL = "world.read.global"
    PHYSICS_SUMMARY = "physics.summary"
    PHYSICS_RAW = "physics.raw"
    TRACE_READ = "trace.read"

class CapabilityGrant(ContractModel):
    """单条授权：actor × capability × 可选 scope。

    - ``scope``：JSON 不透明值；``world.read.local`` 约定键
      ``{"radius": int ≥ 1}`` / ``{"domain": str}`` / 两者 / 缺省（D-P4-06）；
      其余 capability 的 scope 由使用方约定，P4 不解释；
    - 无 scope（None）= 该 capability 的全量授权。
    """
    actor_id: EntityId
    capability: Capability
    scope: JsonValue | None = None

class CapabilityTable(ContractModel):
    """授权表（K7 配置面，INV-P4-3）。

    构造期不变量 **C-INV-1**：``(actor_id, capability)`` 组合重复 →
    :class:`CapabilityScopeError`（静默覆盖 = KBC 类陷阱，数据层拒绝）。
    """
    grants: tuple[CapabilityGrant, ...] = ()
    action_requirements: dict[ActionTypeId, tuple[Capability, ...]] = {}

    def grants_for(self, actor_id: EntityId) -> tuple[CapabilityGrant, ...]: ...
    def requires(self, action_id: ActionTypeId) -> tuple[Capability, ...]: ...
    def satisfied(self, actor_id: EntityId, action_id: ActionTypeId) -> bool:
        """actor 对 action 的全部要求 capability 均已授权（scope 缺省检查）。"""

def check_capability(
    table: CapabilityTable, actor_id: EntityId, capability: Capability, *,
    scope: JsonValue | None = None,
) -> bool:
    """核查：存在 (actor, capability) 授权且请求 scope 被授权 scope 覆盖。

    覆盖语义钉死：请求 scope 为 None → 仅需授权存在；双方均为 dict →
    请求的每个键值对必须等于授权同键值（子集语义）；非 dict → 逐字相等。
    未授权 / 覆盖不足 → False（不抛——读门是判定不是错误）。
    """

#: 普通 NPC 默认（Spec:895-899 "Observation + Knowledge + Memory" 逐字映射）
DEFAULT_NPC_CAPABILITIES: Final[frozenset[Capability]] = frozenset(
    {Capability.OBSERVATION_READ, Capability.KNOWLEDGE_READ, Capability.MEMORY_READ}
)

class CapabilityScopeError(ValueError):
    """C-INV-1 重复授权 / scope 结构非法。"""
```

单测口径（test_capability.py）：8 token 逐字断言（值集合 + 字符串相等）；C-INV-1 重复 → `CapabilityScopeError`；`satisfied` 全满足/缺一/空要求三态；`check_capability` scope 子集四态（None/None、dict⊆dict、dict⊄dict、非 dict 相等/不等）；`DEFAULT_NPC_CAPABILITIES` == 3 元集。

### 3.6 `knowledge.py`（P4-T04；11 导出）

```python
class BeliefKind(str, Enum):
    FACT = "fact"
    RUMOR = "rumor"

class Belief(ContractModel):
    """单条信念（Spec:858-862 KnowledgeState.beliefs 的标准骨架）。

    - ``subject`` / ``predicate``：自由串（entity_id 或概念词；P4 不建词表）；
    - ``value``：JSON 值（P1 §0.2 铁律 1：JSON-native 类型）；
    - ``confidence``：[0,1]——uncertainty 维度的编码（D-P4-09：Spec:862
      "uncertainty" 不另设 kind，由 kind × confidence 承载）；
    - ``origin_event_id``：可空因果回指（K6 数据面）。
    """
    kind: BeliefKind
    subject: str
    predicate: str
    value: JsonValue
    confidence: float = Field(ge=0.0, le=1.0)
    formed_tick: int = Field(ge=0)
    origin_event_id: EventTypeId | None = None

class KnowledgeState(ContractModel):
    """知识状态视图（从组件载荷解析的临时物化，D-P4-04 不持久化自身）。"""
    beliefs: tuple[Belief, ...] = ()
    last_updated_tick: int = 0

    def reference_entity_ids(self) -> frozenset[str]:
        """全部 belief 的 subject 去重集合（调用方 ∩ 世界实存，CX-INV-2）。"""
    def beliefs_about(self, subject: str) -> tuple[Belief, ...]:
        """subject 全等的 belief 序列（载荷序，确定性）。"""

class ObservationRecord(ContractModel):
    """单条观察记录（P1 ``ObservationId`` ids.py:150 + 工厂 ids.py:247）。

    **OBS-INV-1**：``observed_entity_ids`` 重复 → 构造失败
    （K7 可检查不静默；与 P1 builder 助手拒绝重复同纪律，entity.py:86-97）。
    """
    observation_id: ObservationId
    actor_id: EntityId
    tick: int = Field(ge=0)
    payload: dict[str, JsonValue] = {}
    observed_entity_ids: tuple[EntityId, ...] = ()
    cause_event_id: EventTypeId | None = None

#: 组件类型 ID（P1 无内置 knowledge 类组件的槽位落位，state.py:255-257 逐字；
#  P4 注册归属裁定见 §8.5 偏离 D6，P9 必须复用、不得重复注册）
OBSERVATIONS_COMPONENT = ComponentTypeId("observations")
KNOWLEDGE_COMPONENT = ComponentTypeId("knowledge")
MEMORY_COMPONENT = ComponentTypeId("memory")

def encode_observations(records: tuple[ObservationRecord, ...]) -> dict[str, JsonValue]:
    """→ ``{"items": [record 全字段 JSON, ...]}``（载荷序）。"""

def decode_observations(payload: Mapping[str, JsonValue]) -> tuple[ObservationRecord, ...]:
    """载荷 → 记录序列；字段畸形 → pydantic ``ValidationError``（不吞）。"""

def encode_knowledge(state: KnowledgeState) -> dict[str, JsonValue]:
    """→ ``{"beliefs": [...], "last_updated_tick": int}``。"""

def decode_knowledge(payload: Mapping[str, JsonValue]) -> KnowledgeState:
    """载荷 → KnowledgeState；字段畸形 → pydantic ``ValidationError``。"""
```

- **Memory 无编解码器**（D-P4-09）：`memory` 组件载荷 = `{"items": list[JsonValue]}` 原始列表，episodic/semantic/retrieved 结构属 Spec:864-865 MAY 自定义域，P4 只透传（context 侧 `memory` 字段 = 原始 tuple，不解释）。
- 组件缺失语义：`component_view(eid, KNOWLEDGE_COMPONENT) is None` → context 的 `knowledge is None`（G4-1② 断言面）。
- 单测口径（test_knowledge.py）：Belief confidence 越界拒绝（0.5+ 边界）；OBS-INV-1 重复 id 拒绝；四个编解码 roundtrip 全等（encode→decode→encode 字节级）；畸形载荷 → `ValidationError`（不静默、不降级）；`reference_entity_ids` 去重与 `beliefs_about` 序。

### 3.7 `space.py`（P4-T05/T06/T07；18 导出）

```python
SpacePosition = JsonValue
#: 位置值类型（D-P4-10：格式由 backend 自校验，P4 无全局位置校验器）

SPATIAL_BACKEND_KINDS: Final[frozenset[str]] = frozenset(
    {"graph", "grid", "hex", "continuous2d", "continuous3d", "custom"}
)
#: 6 种空间形态（Spec:1354-1361 词表小写 token 化；P4 实现 graph/grid，
#: 余为 reserved 扩展位 → make_backend 拒绝，P5+ 落地）

class SpatialDomain(ContractModel):
    """named spatial domain（Spec:1365-1372：overworld/city/tavern/…）。

    **S-INV-1**：``domain_id`` 匹配 ``^[a-z][a-z0-9_]*$``（构造期拒绝）；
    **S-INV-2**：``backend_kind`` ∈ :data:`SPATIAL_BACKEND_KINDS`（构造期拒绝）。
    """
    domain_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    backend_kind: str
    parameters: dict[str, JsonValue] = {}

class SpaceBackend(Protocol):
    """空间后端协议（Spec:1348-1350 "空间 MUST 可替换" Spec:1345）。

    实现纪律（D-P4-11 / INV-P4-3）：不可变配置对象——全部几何数据构造期
    注入，运行期零状态变更；四方法全纯。
    """
    def validate_position(self, position: SpacePosition) -> None:
        """非法位置 → :class:`InvalidPositionError`（含 domain 无关诊断）。"""
    def neighbors(self, position: SpacePosition) -> tuple[SpacePosition, ...]:
        """邻接位置（**确定性序**：grid 上/右/下/左，D-P4-12；graph 排序节点序）。"""
    def distance(self, a: SpacePosition, b: SpacePosition) -> float:
        """距离（graph = BFS 跳数，grid = 曼哈顿；不可达 → INF_DISTANCE）。"""
    def positions(self) -> tuple[SpacePosition, ...]:
        """全位置枚举（确定性序：grid 行主序 y→x；graph 节点 casefold 排序）。"""

class GraphSpace:
    """无向图空间参考实现（P4-T06）。

    构造：``GraphSpace(nodes: Sequence[str], edges: Sequence[tuple[str, str]])``。
    **G-INV**（构造期拒绝，:class:`SpaceInvariantError`）：节点 id 非空串；
    自环边（a==b）拒绝；重复边（无向，(a,b)≡(b,a)）拒绝；边端点未声明拒绝。
    距离 = BFS 跳数（float）；不可达 → :data:`INF_DISTANCE`。
    """

class GridSpace:
    """二维网格参考实现（P4-T06）。

    构造：``GridSpace(width: int, height: int)``，w/h ≤ 0 →
    :class:`SpaceInvariantError`。位置 = ``{"x": int, "y": int}``，
    x ∈ [0, width)、y ∈ [0, height)；4 邻 = 上/右/下/左（D-P4-12 固定序，
    出界裁剪）；距离 = 曼哈顿；``positions()`` = 行主序（y 外层、x 内层）。
    位置校验：恰含 x/y 两键且为整数且在界内，否则 InvalidPositionError。
    """

INF_DISTANCE: Final[float] = float("inf")
#: 不可达距离哨兵（D-P4-12：计算值、永不入 JSON——P1 §0.2 铁律 1 的落位：
#: 距离不是持久化字段；测试中禁止对其 dump_json）

class SpaceRegistry:
    """domain 名 → (SpatialDomain, SpaceBackend) 不可变注册表（INV-P4-3）。

    构造：``SpaceRegistry(entries: Mapping[str, tuple[SpatialDomain, SpaceBackend]])``。
    **S-INV-4**：键必须 == ``entry[0].domain_id``，否则 :class:`SpaceInvariantError`；
    **S-INV-5**：``entry[0].backend_kind`` 必须与 backend 实际种类一致
    （graph→GraphSpace / grid→GridSpace isinstance 核对），否则同错。
    零公共 mutator；``domain_ids()`` 返回排序元组。
    """
    def domain(self, domain_id: str) -> SpatialDomain:
        """未注册 → :class:`UnknownDomainError`（查找点抛出，D-P3-16 双轨同纪律）。"""
    def backend(self, domain_id: str) -> SpaceBackend: ...
    def domain_ids(self) -> tuple[str, ...]: ...

def make_backend(kind: str, parameters: dict[str, JsonValue]) -> SpaceBackend:
    """工厂（Spec:1345 可替换性的构造侧）：graph → GraphSpace（parameters:
    ``nodes``/``edges``）、grid → GridSpace（``width``/``height``）；
    其余 kind（hex/continuous2d/continuous3d/custom）→
    :class:`UnknownBackendError`（reserved 显式拒绝，不静默降级）。"""

class SpaceMapping(ContractModel):
    """单条 entity × domain 映射（Spec:1384-1392 "每个 mapping 必须明确
    所属 spatial domain" 的数据表达）。"""
    domain_id: str
    position: SpacePosition
    entered_tick: int = 0

#: 组件类型 ID（P1 无内置 spaces 类组件；槽位锚定 state.py:258
#  "persistent gameplay state → 组件 + world_variables"；空间映射 = spaces 组件、域内唯一（D-P4-13）；见 §8.5 偏离 D6）
SPACES_COMPONENT = ComponentTypeId("spaces")

def encode_spaces(mappings: tuple[SpaceMapping, ...]) -> dict[str, JsonValue]:
    """→ ``{"mappings": [mapping 全字段 JSON, ...]}``（载荷序）。"""

def decode_spaces(payload: Mapping[str, JsonValue]) -> tuple[SpaceMapping, ...]:
    """载荷 → 映射序列；**S-INV-3**：同一 domain 出现两次 →
    :class:`SpaceInvariantError`（一 domain 一 position）；字段畸形 →
    pydantic ValidationError。"""

def entity_domain_positions(view: EntityView) -> dict[str, SpacePosition]:
    """EntityView 的 spaces 组件 → ``{domain_id: position}``；组件缺失 → {}。"""

class UnknownDomainError(LookupError): ...
class UnknownBackendError(LookupError): ...
class InvalidPositionError(ValueError): ...
class SpaceInvariantError(ValueError): ...
```

错误族（4）：`SpaceInvariantError(ValueError)`（S-INV-1~5/G-INV 构造与载荷期）、`UnknownDomainError(LookupError)`（registry 查找）、`InvalidPositionError(ValueError)`（backend.validate_position）、`UnknownBackendError(LookupError)`（make_backend reserved）。

单测口径（test_space.py）：SpatialDomain 两 INV 构造拒绝（大写 id / 词表外 kind）；GraphSpace 自环/重复边/未知端点拒绝 + BFS 三态（同节点 0.0、两跳 2.0、不可达 INF）+ 邻接排序；GridSpace 越界 w/h 拒绝 + 四邻序与出界裁剪 + 曼哈顿 + 行主序 + 位置校验五拒绝（缺键/多键/浮点/负值/越界）；S-INV-3/4/5 三拒绝；make_backend 六 kind 分派（graph/grid 成功 + 四 reserved 拒绝）；spaces 编解码 roundtrip + 重复 domain 拒绝 + `entity_domain_positions` 缺失/在位。

### 3.8 `context_provider.py`（P4-T02；6 导出）

```python
@dataclass(frozen=True)
class ContextBuildInput:
    """构建输入（当刻快照面；全部值传递，无别名风险）。

    - ``actor_id``：为其构建上下文的 actor——决策主体身份的唯一依据
      （CX-INV-1 查找基；唤醒侧值传递传入，ERR-P4-1）；
    - ``state``：**当刻** ``GuardedWorldState`` guard 视图（reducer.guard 产物，
      reducer.py:1590）——只用于 build 期间读取，**绝不**进入结果（CX-INV-4）；
    - ``tick``：逻辑刻（hook 侧 = ``clock.tick``，scheduler.py:1171-1173 传入）；
    - ``wake_reason``：唤醒原因（= boundary_id，G2 移交 3 双记录口径）或 None。
    """
    actor_id: EntityId
    state: "GuardedWorldState"
    registry: ActionRegistry
    capability_table: CapabilityTable
    space_registry: SpaceRegistry | None
    tick: int
    wake_reason: str | None

@dataclass(frozen=True)
class ActorDecisionContext:
    """Actor 决策上下文——**13 字段**（字段级契约，K7 全可检查）。

    - ``actor_id`` / ``tick`` / ``base_world_revision`` / ``wake_reason``：身份与时序锚
      （base = 构建刻 ``state.world_revision``，reducer 委托面）；
    - ``self_view``：actor 自身 EntityView（深冻结，entity.py:173-196）；
    - ``visible_entities``：可见 id 集（CX-INV-2 的并集口径，见下）；
    - ``local_entity_views``：local 域内邻域视图（授权且空间可达才填充）；
    - ``global_entity_views``：全实体视图（**未授权 world.read.global → None**）；
    - ``observations`` / ``knowledge`` / ``memory``：三组件物化（未授权/缺失 →
      缺省空值：``()`` / ``None`` / ``()``）；
    - ``candidate_actions``：要求能力全部满足的注册 action_id（casefold 排序）；
    - ``granted_capabilities``：本 actor 已授权 capability 集（回显，G4-2 断言面）。
    """
    actor_id: EntityId
    tick: int
    base_world_revision: Revision
    wake_reason: str | None
    self_view: EntityView
    visible_entities: frozenset[EntityId]
    local_entity_views: dict[EntityId, EntityView]
    global_entity_views: dict[EntityId, EntityView] | None
    observations: tuple[ObservationRecord, ...]
    knowledge: KnowledgeState | None
    memory: tuple[JsonValue, ...]
    candidate_actions: tuple[ActionTypeId, ...]
    granted_capabilities: frozenset[Capability]
```

**CX-INV 逐条**（DefaultContextProvider.build 构造期强制；违反 → `ContextInvariantError`）：

- **CX-INV-1**：actor 不存在（`entity_view` 返回 None，reducer.py:1738-1740）→ `ActorUnknownError`（不产半截 context）；
- **CX-INV-2**：`visible_entities == {actor} ∪ {o.observed_entity_ids} ∪ (knowledge.reference_entity_ids() ∩ 世界实存) ∪ local 键集`——超集禁止、缺项禁止（两侧集合运算断言）；
- **CX-INV-3**：`local_entity_views` 键 ⊆ `visible_entities`，且每视图 `revision == base_world_revision`（同刻物化，跨刻混入即 KBC-3 同型陷阱）;
- **CX-INV-4**：context 13 字段类型全为值类型（EntityView/记录/元组/集合/标量）——无 `GuardedWorldState`、无 token、无可调用（A1 类体静态扫描 + 运行期 `type()` 核查）；
- **CX-INV-5**：DefaultContextProvider 的 `prompt` 属性在 build 路径零引用（A2 静态扫描：`prompt` 只出现于 `__init__` 存储点）；
- **CX-INV-6**：能力门控填充矩阵（INV-P4-2 数据表达）——observations ⇔ observation.read；knowledge ⇔ knowledge.read；memory ⇔ memory.read；local_entity_views ⇔ world.read.local；global_entity_views ⇔ world.read.global（未授权 → **None**，非 {}）；candidate_actions 逐 action 经 `table.satisfied`（空要求 = 恒满足）；
- **CX-INV-7**：`candidate_actions` = `registry.specs`（action_registry.py:219 公共面）键集中满足要求者，casefold 排序元组（确定性，P4 自设纪律，§3.4）。

**local 范围语义（D-P4-06 钉死）**：world.read.local 的 grant scope：
- scope 为 None/缺键 → 全部注册域，半径 = 1（保守缺省：仅邻接）；
- `{"radius": r}`（int ≥ 1）→ 全部注册域，半径 r（r=0 → `ContextInvariantError`，D-P4-06 权威）；
- `{"domain": d}` → 仅域 d，半径 1；`{"domain": d, "radius": r}` → 两者；
- 未知 scope 键 → `ContextInvariantError`（可检查不静默）；
- actor 在域 d 无 mapping（`entity_domain_positions` 无 d 键）→ 该域不贡献 local（不崩溃；未映射域以空贡献回退，与「全部注册域」读法行为等价）；
- 邻域判定 = `backend.validate_position` 通过 ∧ `backend.distance(self_pos, pos) <= radius`（backend 自校验，D-P4-10）；
- `space_registry is None` → local 恒空（无空间面 = 无 local 数据，降级不报错）。

```python
class ContextProvider(Protocol):
    """上下文提供者协议（Spec:874-878：Policy 经 ContextProvider 获得
    能力限定的数据，不读 entire WorldState Spec:876）。"""
    def build(self, input: ContextBuildInput) -> ActorDecisionContext: ...

class DefaultContextProvider:
    """缺省实现：构建期物化（D-P4-05）。

    ``__init__(self, *, prompt: str | None = None)``——prompt 不透明存储
    （CX-INV-5；K4：Prompt 不定义权限，Spec:295/909）。build 六步次序钉死：
    1. self_view（CX-INV-1）；2. 授权集（granted_capabilities 回显）；
    3. 三组件物化（CX-INV-6 矩阵）；4. local/global 物化（D-P4-06）；
    5. 候选动作（CX-INV-7）；6. 可见集并集（CX-INV-2）+ 一致性自检。
    """

class ActorUnknownError(LookupError):
    """CX-INV-1：actor 不存在于世界。"""

class ContextInvariantError(ValueError):
    """CX-INV-2/3/6 及 scope 结构非法。"""
```

单测口径（test_context_provider.py）：13 字段构造与冻结（字段再赋值抛 FrozenInstanceError）；无 actor → ActorUnknownError；能力矩阵六行（每 capability 授予/撤回两态 × 对应字段填充/缺省）；可见集并集四来源各一（self/obs/knowledge/local 各贡献恰一 id）+ 超集/缺项负例；local 五态（None scope 半径 1 / 半径 r / domain 限定 / 双键 / 未知键拒绝）+ 无 mapping 域不崩 + registry None 降级；prompt 不透明（不同 prompt 同输入 → 同 context，A2 的运行期面）；`granted_capabilities` 回显 == 表内该 actor 授权集。

### 3.9 `behavior_policy.py`（P4-T01；4 导出）

```python
class BehaviorPolicy(Protocol):
    """行为策略协议（Spec:818-825 的同步落地，D-P4-01 / 偏离 D1）。

    **B-CON 逐条**（单测机械断言面）：
    - B-CON-1：``decide`` 为同步方法（非协程函数——``inspect.iscoroutinefunction``
      为 False；云模型异步性属 P5 实现细节，经同步门面收敛，§3.4 确定性纪律）；
    - B-CON-2：签名 = 单参数 ``context``（ActorDecisionContext）；
    - B-CON-3：返回 ``ActionProposal | None``（None = 本 tick 不提案，合法）；
    - B-CON-4：policy 实例不持有 random/时钟/网络面（单测静态扫描类体 import 面）；
    - B-CON-5：返回提案的 ``actor_id`` 必须 == ``context.actor_id``
      （门面执行，D-P4-03；capability ⊥ authority，D-P4-08——缝不门控写授权；违规 = 越权代言，K5 数据面防线）。
    """
    def decide(self, context: "ActorDecisionContext") -> "ActionProposal | None": ...

class PlayerPolicy(BehaviorPolicy):
    """玩家策略标记协议（Spec:833 PlayerPolicy 变体；D-P4-02）。

    结构面 = BehaviorPolicy + ``bound_input_source: str | None``（不透明标签
    （JSON-clean）；P5 接线真实输入设备/网络输入，P4 只定契约不定实现）。
    """
    bound_input_source: str | None

def run_policy_decide(policy: BehaviorPolicy, context: ActorDecisionContext) -> ActionProposal | None:
    """策略执行门面（唯一执行点；P4 集成路径全部经此）。

    次序钉死：1. ``proposal = policy.decide(context)``——policy 抛出的任何
    异常**原样传播**（不包装——wakeup 侧由 P3 既有 ``SchedulerWakeupError``
    机制捕获，scheduler.py:1174-1177；非 wakeup 调用方自行负责）；
    2. None → 返回 None；3. ``proposal.actor_id != context.actor_id`` →
    :class:`PolicyActorMismatchError`（B-CON-5 / D-P4-03）；4. 返回 proposal。
    **不检查** ``base_world_revision`` 漂移——stale 判定唯一属 revalidation
    （scheduler.py:1661-1663），门面预检 = 双份事实源（KBC-3 反模式）。
    """
    ...

class PolicyActorMismatchError(ValueError):
    """B-CON-5：策略代言了非上下文的 actor。"""
```

单测口径（test_behavior_policy.py）：B-CON-1~5 机械断言（协议符合性：合规类通过 + 异步 decide 拒绝 + 双参数签名拒绝 + actor 错配拒绝 + None 合法）；`run_policy_decide` 异常传播（policy 抛 ValueError → 门面不包装、原样上抛）；base 漂移不拦（构造 stale base 提案 → 门面放行——REJECT 归 revalidation，与 A7b 呼应）。

### 3.10 `gameplay_mode.py`（P4-T08/T09；14 导出）

```python
class ModeOperationKind(str, Enum):
    ACTIVATE = "activate"
    DEACTIVATE = "deactivate"

class ModeOperation(ContractModel):
    operation_kind: ModeOperationKind
    mode_id: str

class ModeOverlay(ContractModel):
    """模式叠加层（Spec:1398-1409 "Mode 是 overlay，不是另一个 world"）。

    - ``priority``：≥ 0（Spec:1428/1429 winner 语义的排序键；D-P4-14）；
    - ``action_filter_kind``：none | allow | deny（Spec:1424-1425 "available_actions
      → union/intersection" 的可检查落位；P4 取交集 = 保守侧，D-P4-14b）；
    - ``systems``：系统激活名（Spec:1426 "system_activation → union"）；
    - ``time_policy``：**整对象** TimePolicy（scheduler.py:251-271）——winner 全量
      替换，不做字段级 merge（Spec:1428 "time_policy → priority winner"）；
    - ``checkpoint_interval``：模式建议 checkpoint 粒度（winner 取值；P4 簿记面，
      执行语义 = P5/scheduler 扩展位）；与 ``TimePolicy.checkpoint_interval_ticks``（scheduler.py:1584 读 time_policy 侧）数值分歧时，执行语义 = P5 义务（P4 纯簿记；与 G3 移交 2 同式登记）；
    - ``input_policy``：不透明 JsonValue（M-INV-6；P4 直通不解释，P8 表现层消费）；
    - ``context``：per-mode 上下文 → ``mode_context[mode_id]``（Spec:1413 侧）。
    **M-INV-1**：``mode_id`` 匹配 ``^[a-z][a-z0-9_]*$``；``action_filter_kind ==
    "none"`` ⇒ ``action_ids == ()``；allow/deny ⇒ ``action_ids`` 非空（构造期拒绝）。
    """
    mode_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    priority: int = Field(ge=0)
    action_filter_kind: Literal["none", "allow", "deny"] = "none"
    action_ids: tuple[str, ...] = ()
    systems: tuple[str, ...] = ()
    time_policy: TimePolicy | None = None
    checkpoint_interval: int | None = Field(default=None, ge=1)
    input_policy: JsonValue | None = None
    context: dict[str, JsonValue] = {}

class ModeOverlayRegistry:
    """mode_id → ModeOverlay 不可变注册表（INV-P4-3；构造期核对键 ==
    overlay.mode_id，违例 → :class:`ModeInvariantError`）。

    ``get(mode_id) -> ModeOverlay | None``；``mode_ids() -> tuple[str, ...]`` 排序。
    """

class ModeChangeRequest(ContractModel):
    """模式变更请求（Spec:1448-1449 统一输出；Spec:1439-1443 四来源）。

    **M-INV-2**：``source``（Provenance，K6 Spec:315）必填非空；
    ``operations`` 非空（空请求 → :class:`ModeInvariantError` 构造期拒绝）；
    全部 ``op.mode_id`` ∈ registry（解析期原子校验，先于任何簿记变更）。
    origin 映射钉死（D-P4-15，provenance.py:41-55 词表）：
    Script → SCENARIO（provenance.py:53）/ RuleEngine → SYSTEM（:55）/
    Plugin → SYSTEM（:55）/ Spec:1439-1443 四来源之行为策略侧源
    （Spec:1442）→ BEHAVIOR_POLICY（:49）。
    """
    request_id: str
    source: Provenance
    operations: tuple[ModeOperation, ...]

class ModeChangeResolution(ContractModel):
    """解析结果（判定结果 = 数据，K7）。

    **M-INV-4**：P4 域 ``effects`` 恒为 ``()``（模式变更零世界效果；P5 扩展
    位保留字段，Spec:1452 由 ModePolicy 解析的扩展空间）；
    ``applied`` / ``ignored`` = 操作字符串序列（``"activate:dialogue"`` 形态，
    请求序）；``new_active_modes`` 排序；``new_mode_context`` = 变更后的完整
    per-mode 上下文 dict。
    """
    effects: tuple[ProposedEffect, ...] = ()
    new_active_modes: tuple[str, ...]
    new_mode_context: dict[str, JsonValue]
    applied: tuple[str, ...] = ()
    ignored: tuple[str, ...] = ()

class MergedModeConfiguration(ContractModel):
    """per-property 合并结果（Spec:1422-1433；"所有冲突策略 MUST 可检查"
    Spec:1433（MUST 可检查）经 ``winner_by_field`` 逐字段胜者记录落地）。

    - ``winner_by_field``：字段 ∈ {"time_policy", "checkpoint_interval",
      "input_policy", "action_filter"} → 胜者 mode_id（仅非空值在场时收录）；
    - ``time_policy`` / ``checkpoint_interval`` / ``input_policy``：胜者整值（缺 → None）；
    - ``action_filter_kind`` / ``action_ids``：deny 优先——任一 deny 在场 →
      kind="deny"、ids = 各 deny 集并集（排序）；否则任一 allow 在场 →
      kind="allow"、ids = 各 allow 集**交集**（排序）；否则 none/()；
    - ``activated_systems``：各 overlay systems **并集**（Spec:1426）；
    - ``context``：浅合并——按 (-priority, casefold(mode_id)) 逆序应用
      ``update``（低优先先写、胜者后写覆盖；平手 → casefold 较小 id 胜，D-P4-14）。
    """
    winner_by_field: dict[str, str]
    time_policy: TimePolicy | None
    checkpoint_interval: int | None
    input_policy: JsonValue | None
    action_filter_kind: Literal["none", "allow", "deny"]
    action_ids: tuple[str, ...]
    activated_systems: frozenset[str]
    context: dict[str, JsonValue]

def merge_modes(overlays: Mapping[str, ModeOverlay]) -> MergedModeConfiguration:
    """纯函数合并（输入 = 当前 active 的 overlay 映射；空输入 → 全缺省）。

    算法（确定性，P4 自设纪律，§3.4）：1. 排序键 (-priority, casefold(mode_id))；
    2. 单胜者字段 = 排序首现非空值（D-P4-14）；3. action_filter 三段判定；
    4. systems 并集；5. context 逆序 update。平手裁定 = casefold 较小 id
    （G4-5 断言面；A4 排列不变性对抗）。
    """

def is_action_available(merged: MergedModeConfiguration, action_id: str) -> bool:
    """deny（不在 deny 并集）> allow（在 allow 交集）> none（恒真）。"""

class ModePolicy(Protocol):
    """模式策略协议（Spec:1452 "由 ModePolicy 解析"；**P5 接缝**——
    行为策略侧解析器（Spec:1439-1443 四来源之行为策略侧源）实现本协议，
    P4 提供缺省实现）。"""
    def resolve(self, request: ModeChangeRequest, registry: ModeOverlayRegistry,
                runtime: RuntimeState) -> ModeChangeResolution: ...

class DefaultModePolicy:
    """缺省解析器：委托 :func:`apply_mode_change`（无额外判定逻辑）。"""

def apply_mode_change(
    *, request: ModeChangeRequest, runtime: RuntimeState,
    registry: ModeOverlayRegistry,
) -> tuple[RuntimeState, ModeChangeResolution]:
    """模式变更执行器（**T09 核心；P4 唯一 mode 写面**）。

    **M-INV-3**：签名 = 三关键字参数（request/runtime/registry）——**无
    世界状态参数**（Spec:1409；G4-6 结构断言面）。
    次序钉死：1. 原子预校验——任一 op.mode_id ∉ registry →
    :class:`UnknownModeError`（先于任何簿记变更，原子性）；2. active 集合与
    mode_context dict 的本地工作副本；3. 按请求序执行操作：ACTIVATE 已激活 →
    ignored；DEACTIVATE 未激活 → ignored；其余 applied（activate 写入
    ``ctx[mode_id] = overlay.context``，deactivate 弹出）；4. 唯一重建通道
    ``rebuild_runtime(runtime, active_modes=sorted(active), mode_context=ctx)``
    （clock.py:151-158；**M-INV-5** 其余字段位级不变 + 别名断裂由 model_dump/
    model_validate roundtrip 保证，A6 断言）；5. 组装 resolution（M-INV-4
    effects=()）；6. 返回 (new_runtime, resolution)。
    零世界状态效果、零事件、零事务、零队列变更（INV-P4-5）。
    """

class UnknownModeError(LookupError): ...
class ModeInvariantError(ValueError): ...
```

错误族（2）：`UnknownModeError(LookupError)`（M-INV-2 查找点）、`ModeInvariantError(ValueError)`（M-INV-1/2 构造期）。

单测口径（test_gameplay_mode.py）：M-INV-1 三拒绝（非法 mode_id / none+ids / allow+空 ids）；M-INV-2 空 operations 拒绝 + origin 四映射值断言；registry 键不匹配拒绝；merge 五性质（单 overlay 透传 / 双 overlay 高优先胜 / 平手 casefold / 空输入全缺省 / winner_by_field 键集与值）；action_filter 四态（none / allow 单 / allow 双交集 / deny 压 allow）；is_action_available 三态；apply 五路径（activate 新 / activate 重复 ignored / deactivate 在位 / deactivate 缺席 ignored / 未知 mode 原子拒绝——断言 runtime 全字段不变）；M-INV-5 字段逐一比较（除两字段外 model_dump 全等）；context 别名断裂（apply 后改 overlay.context → runtime.mode_context 不变）。

### 3.11 `__init__.py` 与测试锚点同步机制

**导入块**（`core/__init__.py:51-343`：26 模块导入组；冻结基线组序非全局 casefold 有序（历史布局））——6 个新导入块（5 个插入位，behavior_policy/capability 共位；已核验，组锚点行号 = 冻结 HEAD，插入位锚定于下表已核验的组邻接线号，非由 casefold 推导）：

| 新模块 | 插入于 | 依据（casefold 序） |
|---|---|---|
| `behavior_policy`、`capability` | authority 块（止于 __init__.py:97）之后、clock 块（__init__.py:98）之前 | authority < behavior_policy < capability < clock |
| `context_provider` | conflicts 块（止于 __init__.py:158）之后、effects 块（__init__.py:159）之前 | conflicts < context_provider < effects |
| `gameplay_mode` | events 块（止于 __init__.py:185）之后、ids 块（__init__.py:186）之前 | events < gameplay_mode < ids |
| `knowledge` | interrupt 块（止于 __init__.py:223）之后、provenance 块（__init__.py:224）之前 | interrupt < knowledge < provenance |
| `space` | snapshot 块（止于 __init__.py:310）之后、state 块（__init__.py:311）之前 | snapshot < space < state（snapshot 同名遮蔽注释 __init__.py:301-303 原样保留） |

**`__all__`**（`core/__init__.py:345` `__all__ = [` … `:595` `]`，249 条 L346-594）：+59 名。沿用 P3 设计:810『字母序插入，P1/P2 同款纪律』，并机械化为 casefold 插入规则：**每个新名插入其 casefold 位，既有 249 名相对顺序零重排**。基线非全局有序（历史局部序：ScenarioState 位于 VALIDATION_ISSUE_KINDS 之后、SyncTrigger 位于 StateDomainId 之前——重排即破坏 G3 台账逐行对齐）→ 插入规则钉死（机械可验）：对既有列表 L（249 项），新名 n 的插入索引

```text
i(n) = max { i ∈ [0..249] : (i==0 或 L[i-1].casefold() < n.casefold())
             且 (i==249 或 L[i].casefold() > n.casefold()) }
```

59 名逐名相邻位（本会话脚本对冻结 HEAD 核验产出，实现者照表落位、落位后重跑同一脚本须 0 偏差）：

| 新名 | 模块 | 位于 … 之后 | 位于 … 之前 |
|---|---|---|---|
| Capability / CapabilityGrant / CapabilityTable / CapabilityScopeError / Belief / BeliefKind / BehaviorPolicy | cap/know/beh | `assert_json_clean` | `check_authority` |
| check_capability | cap | `check_authority` | `check_effect_id_kinds` |
| DEFAULT_NPC_CAPABILITIES / DefaultContextProvider / DefaultModePolicy | cap/ctx/mode | `default_handler_registry` | `detect_conflicts` |
| KnowledgeState / KNOWLEDGE_COMPONENT | know | `is_stale` | `load_json` |
| ObservationRecord / OBSERVATIONS_COMPONENT | know | `next_revision` | `parse_action_type_id` |
| MEMORY_COMPONENT / ModeInvariantError / ModeOperation / ModeOperationKind / ModeOverlay / ModeOverlayRegistry / ModeChangeRequest / ModeChangeResolution / MergedModeConfiguration / merge_modes / ModePolicy | know/mode | `match_selector` | `new_action_instance_id` |
| decode_observations / decode_knowledge / decode_spaces / ContextBuildInput / ContextProvider / ContextInvariantError | know/space/ctx | `conflicts_with` | `deep_copy_via_roundtrip` |
| ActorDecisionContext / ActorUnknownError | ctx | `abort_transaction` | `apply_committed_effects` |
| encode_observations / encode_knowledge / encode_spaces / entity_domain_positions | know/space | `effect_locks` | `extract_effect_locks` |
| GraphSpace / GridSpace | space | `freeze_view` | `guard` |
| INF_DISTANCE | space | `guard` | `install_write_barrier` |
| InvalidPositionError / is_action_available | space/mode | `install_write_barrier` | `is_guarded` |
| make_backend | space | `load_json` | `match_selector` |
| apply_mode_change | mode | `apply_committed_effects` | `apply_transaction` |
| PlayerPolicy / PolicyActorMismatchError | beh | `parse_state_domain_id` | `restore_snapshot` |
| SpacePosition / SpatialDomain / SPATIAL_BACKEND_KINDS / SpaceBackend / SpaceRegistry / SpaceMapping / SPACES_COMPONENT / SpaceInvariantError / run_policy_decide | space/beh | `resolve_conflicts` | `state_create_entity` |
| UnknownDomainError / UnknownBackendError / UnknownModeError | space/mode | `uninstall_write_barrier` | `validate_proposed_effect` |

注（R1 盲审 D-I1 闭合）：同一间隙内多个新名按表所给顺序落位，不再 casefold 重排；closeout 锚点仅断言集合相等 + 计数 + 同一性、不断言顺序（test_closeout.py:164-171 集合 / 214 计数 / 216-226 同一性）；表中 10 个错误类型（LookupError 族 4 + ValueError 族 6）集中列全见 D-P4-17。

**closeout / import_boundary 锚点**（P4 末波 F 执行）：

- `test_closeout.py`：:94 `_CORE_SUBMODULE_NAMES` 26 → **32**（+behavior_policy/capability/context_provider/gameplay_mode/knowledge/space）；:214 `assert len(core_pkg.__all__) == 249` → **308**；:173-213 注释算术块同步（26+6 / 249+59 口径）；:161 `shadowed == {"snapshot"}` **不变**（本会话脚本核验：59 新名与 32 子模块名零相交；唯一既有遮蔽仍为 snapshot 函数/子模块同名）；:216-226 同一性、:246-253 版本号、:255-259 star-import 锚点零改动（纯增量自动绿）。
- `test_import_boundary.py`：:54 `CORE_SUBMODULES` 26 → 32；新增 `P4_SUBMODULES`（6 名）、`P4_TEST_FILES`（10 文件：test_capability / test_knowledge / test_space / test_context_provider / test_behavior_policy / test_gameplay_mode / test_p4_gate_scenario / test_p4_adversarial / test_p4_integration / conftest）、`P4_NONDETERMINISM_ROOTS`（= P3 同款 {datetime, time, random, asyncio}，test_import_boundary.py:147-176 P3 常量块同源）；新增 2 个平行测试函数（`test_p4_core_modules_no_nondeterminism_imports` / `test_p4_test_files_full_predicate`，结构复制 test_import_boundary.py:342-376 的 P3 对）；:255-260 stems 断言与 :282-314 B2 fresh-import（迭代 CORE_SUBMODULES）、:317-323 B3 对 P4 **自动覆盖**（锚点升 32 后无需改体）——此为结构性多行编辑，预披露于偏离 D4。

### 3.12 波次与文件白名单

```text
波次 A（并行）: T03 capability.py ∥ T04 knowledge.py ∥ T05 space.py 上半
               （SpatialDomain/SpaceBackend/SPATIAL_BACKEND_KINDS/SpaceRegistry/
                make_backend/INF_DISTANCE/4 错误）
波次 B（并行，A 后）: T02 context_provider.py（依赖 capability+knowledge+space）
               ∥ T06/T07 space.py 下半（SpacePosition/GraphSpace/GridSpace/
                 SpaceMapping/SPACES_COMPONENT/2 编解码/entity_domain_positions ——
                 T07 = 实体多空间映射面（Plan:568），与 T05 同文件串行）
               ∥ T08 gameplay_mode.py 上半（ModeOperationKind/ModeOperation/ModeOverlay/
                 ModeOverlayRegistry/MergedModeConfiguration/merge_modes/
                 is_action_available + M-INV-1）
波次 C（并行，B 后）: T01 behavior_policy.py（依赖 context_provider 类型面）
               ∥ T09 gameplay_mode.py 下半（ModeChangeRequest/ModeChangeResolution/
                 ModePolicy/DefaultModePolicy/apply_mode_change/UnknownModeError/
                 ModeInvariantError + M-INV-2~6 —— 与 T08 同文件串行）
波次 D:        conftest.py P4 节（§5.1 逐字）+ 6 个模块单测
波次 E:        test_p4_gate_scenario.py（G4 六条 19 断言，§5.2/§5.4）
波次 F（末，串行）: test_p4_adversarial.py（A1-A8）+ test_p4_integration.py
               （R1-R8 + 分支 B/C）+ core/__init__.py + test_closeout.py +
               test_import_boundary.py 同步（§3.11）
```

同文件单 Owner 纪律（Plan §7.2 沿 P3 设计:792）：`space.py`（T05→T06/T07）与 `gameplay_mode.py`（T08→T09）严格串行；`conftest.py` 仅 D/E/F 波触碰且只追加 P4 节。

波次名闭合核验：波次名枚举 ∪ 所引整模块（T01/T02/T03/T04 = behavior_policy 4 / context_provider 6 / capability 6 / knowledge 11，§8.3 账本）= **59 导出名全闭合**；`space.py` 18 名全部落于波次 A（10 名）+ 波次 B T06/T07（8 名：SpacePosition/GraphSpace/GridSpace/SpaceMapping/SPACES_COMPONENT/2 编解码/entity_domain_positions），零缺口。

**文件白名单（穷举；未列文件一律不触碰）**：

| 类别 | 文件（共 19） |
|---|---|
| core 新增（6） | capability.py / knowledge.py / space.py / context_provider.py / behavior_policy.py / gameplay_mode.py |
| core 修改（1） | __init__.py |
| 测试新增（9） | 6 模块单测 + test_p4_gate_scenario.py + test_p4_adversarial.py + test_p4_integration.py |
| 测试修改（3） | conftest.py（追加）/ test_closeout.py / test_import_boundary.py |
---

## 4. 决策记录（D-P4-01 ~ D-P4-17）

每条给出 **决策内容与理由与一致性**（各条问题/备选呈现形式见条内；17 条选择全部钉死）。
本决策表是 §3 模块规格的"为什么"层；实现者（QMax）遇到本文档未覆盖的细节时，
以本表意图 + K 铁律外推，**不得**另行发明架构（QMax 零判断纪律）。

### D-P4-01 `BehaviorPolicy.decide` 同步化，返回 `ActionProposal | None`

- **问题**：Spec §12（Spec:818-825）勾勒 `async def decide(context) -> ActionProposal`；
  P4 主循环是 P3 同步 tick 循环（scheduler.py:1471-1505），tick 内无 asyncio 事件循环。
- **备选**：A) 忠实 Spec 异步（在 tick 循环内嵌事件循环）；B) 同步
  `decide(context) -> ActionProposal | None`，LLM 异步性收敛为 P5 内部实现细节。
- **选择**：B（偏离 D1，§8.5）。
- **理由与一致性**：P4 自设确定性纪律（§3.4 黑名单，非 Spec K 条款）优先于接口勾勒；`None` 是合法 no-op 提案（不产提案、
  不进流水线、不产 trace 失败记录）。B-CON-1 机械断言同步签名；P5 的 LLM 封装
  "内部异步、对外同步"（门面内部等待/超时，超时 → None）。Gate 分支 B（PassPolicy）
  即 no-op 路径的集成证明，故异步性缺席不削弱 Gate 覆盖。

### D-P4-02 `PlayerPolicy` = 标记接口 + `bound_input_source` 标签

- **问题**：Spec §12（Spec:818-838，PlayerPolicy@833 列为内部实现变体）区分玩家/ NPC 两类策略；输入（P8 表现层）
  在 P4 不存在，但缝必须预留，且缝上不得让策略自述输入。
- **选择**：`PlayerPolicy(BehaviorPolicy)` 纯标记（不新增必选方法）；实例携带
  `bound_input_source: str | None` 不透明标签（JSON-clean，P4 不解释其内容；§3.9 字段级已同步本口径）。
- **理由与一致性**：玩家的 `decide` 实际是"读取输入队列 → 提案"（P8 落地）；
  P4 只断言缝形状（B-CON-2/3：PlayerPolicy 是 BehaviorPolicy 子型、decide 同样
  受 actor_id 唯一约束）。K4：输入策略归属呈现层配置，策略不自我声明。

### D-P4-03 策略缝只强制 `actor_id`；base 漂移归 revalidation 门

- **问题**：`run_policy_decide` 是否预检 `proposal.base_world_revision` 与当前
  revision 的一致性？
- **备选**：A) 缝上预检（漂移 → 抛错）；B) 只强制 actor_id 匹配（不匹配 →
  PolicyActorMismatchError），base 漂移不预检。
- **选择**：B。
- **理由与一致性**：base 有效性是 revalidation 门的单一职责
  （scheduler.py:1661-1663，`allow_rebase=False` → stale ⇒ REJECT）；同一事实
  双门判定必漂移（K2 单一权威门纪律的横向应用）。stale 提案的终局是 REJECT
  路径（scheduler.py:1570-1572：FAILED trace + 世界/队列零变更 + 提案滞留
  pending_proposals），由 A7b 直接证明；缝上不重复裁决。

### D-P4-04 context 一次性（ephemeral），永不持久化

- **问题**：`ActorDecisionContext` 是否写入 WorldState / RuntimeState / snapshot？
- **选择**：否。context 对象在每次 `on_wakeup` 内构建、`decide` 返回后即弃；
  不进入任何组件、任何 RuntimeState 字段、任何快照。
- **理由与一致性**：K7 + INV-P4-1（context 是世界的投影；持久化投影 = 第二世界
  状态，Spec:1409 禁）。序列化（A6a 往返）只用于可观察性/测试，不改变不持久化
  的事实。M2 以 `model_fields` 扫描 + 模块源文本扫描机械执行本条。

### D-P4-05 认识论边界 = 构建期固化（materialization at build time）

- **选择**：`DefaultContextProvider.build` 只经 `GuardedWorldState` 读取
  （guard 深冻结视图，reducer.py:1590）；全部结果**复制**进冻结 dataclass
  （EntityView 拷贝 + JsonValue 纯数据）。CX-INV-4 断言 context 不持有
  `GuardedWorldState` 或其 entity/component 视图的引用。
- **理由与一致性**：若 context 持视图引用，"角色所见"将随世界漂移（跨 tick 看到
  构建后提交/回滚的状态），认识论边界失效；固化使可见性快照锚定在构建 tick。
  A1 的序列化字符串扫描是机械证明（攻击面：视图引用、token 泄漏）。

### D-P4-06 `local_scope` 语义（四形态 + 两个兜底）

- **定义**（与 §3.8 local 范围语义（D-P4-06 钉死）段 L504-511 一致）：scope 只允许四种形态——
  1. `None` → 全部注册域，半径 1；
  2. `{"radius": r}`（`r ≥ 1` 整型）→ 全部注册域，半径 r；
  3. `{"domain": d}` → 仅域 d，半径 1；
  4. `{"domain": d, "radius": r}` → 仅 d，半径 r。
  出现第四形态之外的键 → `ContextInvariantError`（fail-fast，禁止静默默认）。
- **兜底**：实体在 spaces 组件无映射的域对 local 可见性贡献为空（不报错）；
  `space_registry is None` → local 恒为空（无空间语义、不崩溃）。
- **理由与一致性**：半径 1 = 相邻格/邻接节点（最小感知单元）；域限定形态对应
  "战术模式近距感知"类场景（§25 模式的 context 可注入 scope）。未知键报错是
  "配置错误必须可检查"（Spec:1433）在本模块的落地。

### D-P4-07 不新增 ID 工厂

- **选择**：ids.py 冻结（P1，`603535e`）；P4 仅复用 `new_observation_id`
  （ids.py:247）与 `new_action_instance_id`（P1 既有导出）。
- **理由与一致性**：ID 权威集中于 ids.py（K6/K7）；P4 新增工厂会分裂 ID 命名
  空间并破坏 P1 的 ID 不变式。Gate 中 BobPolicy 产出的提案 ID 为工厂值
  （非确定字符串），故断言一律按**集合差**定位新实例（§5.4 注），replay 口径
  （D-P3-15①）的事件键本就不含实例 ID，确定性不受影响。

### D-P4-08 capability ⊥ authority（双门正交）

- **选择**：capability 只门控 context 构建（策略**能看见**什么）；authority 只门控
  effect 流水线（**谁能写**世界）。两个模块之间、以及 P4 任一模块与 authority 的
  effect 门之间，零 import 边（A8 AST 依赖方向检查）。
- **理由与一致性**：Spec §13.3（Spec:907-909）在 Prompt 侧确立同族纪律
  （override 不提升权限）；capability 侧同理——token 只界定**读**范围，写授权
  唯一来源为 P2 authority（K4，Spec:295-303；INV-P4-4）。Gate 中
  偷窃提交成功恰因它是 authority-only（A8a：无角色持任何相关 capability 也照常
  提交）；A8b 反向证明 grant 不产生写能力。

### D-P4-09 不确定性建模：`Belief` kind×confidence；Memory = 原始 JsonValue

- **选择**：`Belief` 七字段契约（§3.6 字段级权威，逐字）：`kind ∈ {FACT, RUMOR}`、
  `subject: str`、`predicate: str`、`value: JsonValue`、`confidence: float ∈ [0,1]`、
  `formed_tick: int ≥ 0`、`origin_event_id: EventTypeId | None`（可空因果回指，
  K6 数据面）；不设第三种 kind——直接观察才可 FACT，其余（传闻/推断/LLM 断言）
  一律 RUMOR，uncertainty 由 kind × confidence 承载（不另设字段）。
  Memory = `list[JsonValue]` 原始列表，无 codec。
- **理由与一致性**：Spec §13 知识层要求"信念 + 不确定性"；FACT/RUMOR 二值是
  确定性引擎的最小完备集（confidence 是不透明 float，引擎不对其做推理）。
  Memory 无 codec = K7 可检查性的直接推论（任意 JSON 可存、可 dump）；结构化
  记忆（摘要/索引）是 P5 策略内容，不是 P4 机制。

### D-P4-10 position = 不透明 `JsonValue`，backend 自校验

- **选择**：`SpaceMapping.position: JsonValue`；合法语法由各 backend 自行校验
  （Grid：`{x:int, y:int}` 且在 `[0,w)×[0,h)`；Graph：节点 id ∈ nodes）；
  校验失败 → `InvalidPositionError`。
- **理由与一致性**：六类空间位置语法各异（Spec:1354-1361）；统一类型化 position
  要么做类型最小公倍数（泄漏 backend 细节）、要么 backend 子类化（过度拟合）。
  不透明 + 自校验把语法权威留在 backend 内（Spec §24 "backend 封装空间语义"），
  与 D-P3 的 trigger 参数不透明口径同构。

### D-P4-11 空间 backend 是只读配置（运行时不可变）

- **选择**：GraphSpace / GridSpace 不可变：无公开变更 API（结构不变量见 G-INV（L374-375）与 Grid 构造守卫（L382-386）），P4 不提供任何拓扑
  变更 API；拓扑变化未来（P5+）以世界 effect 整体替换 spaces 组件实现。
- **理由与一致性**：INV-P4-3（配置即状态边界）：若拓扑可运行时变更，变更必须
  走 ProposedEffect→…→Reducer 流水线（K2），P4 不承接该流水线面；只读配置
  使 SpaceRegistry 可安全跨 tick 共享（guard 视图之外的第二只读配置源）。

### D-P4-12 距离语义：BFS 跳数（float）/ Manhattan / INF 永不入 JSON

- **选择**：`GraphSpace.distance` = BFS 最短跳数（float 返回，不可达 →
  `INF_DISTANCE = float("inf")`）；`GridSpace.distance` = Manhattan；
  4-邻接（up/right/down/left）是唯一邻接定义；`INF_DISTANCE` 是纯函数返回值，
  **永不**写入任何组件/事件（JSON 无法表达 inf；spaces 组件 codec 只编码
  位置映射，不编码距离）。
- **理由与一致性**：Spec §24 grid 例语义即 Manhattan；graph 例语义即跳数。
  K7 JSON-clean 铁律禁止 inf 进入持久层；距离是派生量（纯函数），不入状态。

### D-P4-13 空间映射 = spaces 组件，域内唯一

- **选择**：实体→域映射存 `"spaces"` 组件，载荷形状以 §3.7 为权威——
  `encode_spaces` → `{"mappings": [{domain_id, position, entered_tick}, ...]}`
  （mappings 列表，载荷序；`decode_spaces` 逆解析）；
  一实体在同一域至多一个映射（S-INV-3，重复 → `SpaceInvariantError`），
  可映射多个域。
- **理由与一致性**：Spec §24 允许"实体同时存在于多个空间"；组件载体是 K2
  下世界状态的唯一合法位置（"配置即状态"——映射是状态，不是配置）；域内
  唯一是物理一致性底线（同一实体在同一空间不能同时在两处）。

### D-P4-14 模式合并规则（每字段单一胜者）

- **选择**（Spec:1424-1431 合并表 + 本文 §3.10 `merge_modes`）：
  - **胜者**：priority 最大；平局 → mode_id 的 casefold 较小者（确定性裁决，A4b）；
  - `time_policy` / `checkpoint_interval` / `input_policy` / `action_filter`：
    **单一胜者**（取胜者值），`winner_by_field` 逐字段记录胜者（G4-5① 可检查）；
  - `activated_systems`：**并集**（激活单调；停用走显式 DEACTIVATE 操作）；
  - `context`：浅合并，高 priority 逐键胜；
  - `available_actions`（`is_action_available` 判定序）：deny > allow 交集 > 无约束
    ——任一激活模式的 deny 集含该 action ⇒ 不可用；否则该 action 必须属于
    **每个**持 allow 集的激活模式的 allow 集（无 allow 集的模式不约束）⇒ 可用。
- **理由与一致性**：单一胜者使"谁决定该字段"可检查（Spec:1433 冲突策略 MUST
  可检查的直接落地）；deny 优先是安全默认（冲突时取更严）；allow 交集对应
  Spec:1424-1431 第一行 union/intersection 口径中 allow 侧取交、deny 侧取并。

### D-P4-15 模式变更 = RuntimeState 簿记，P4 世界效果零

- **选择**：`apply_mode_change(*, request, runtime, registry) -> (RuntimeState,
  ModeChangeResolution)`——签名**无 world 参数**；内部唯一状态变更路径是
  `rebuild_runtime`（clock.py:151-158，model_dump→dict update→model_validate
  往返，容器别名天然断裂）；`ModeChangeResolution.effects` 恒为 `()`
  （M-INV-4）。`ModePolicy` Protocol 是 P5 缝：P5 的"模式变更可伴随世界效果"
  经 ModePolicy 产出提案走主流水线；P4 的 `DefaultModePolicy` 零产出。
  origin 映射（M-INV-2 强制合法源）：Script→SCENARIO（provenance.py:53）、
  RuleEngine→SYSTEM（provenance.py:55）、Plugin→SYSTEM（provenance.py:55）、
  LLM Director→BEHAVIOR_POLICY（provenance.py:49）；其余 origin →
  `ModeInvariantError`。Spec §25.4 四来源在模式变更提案来源语义层面归属；SCRIPT / RULE 字面值属 P1 writer 族 origin 值（provenance.py:49-55，其中 SCRIPT 在 provenance.py:52）；P4 映射不复用 SCRIPT 字面值而归入 SCENARIO 族；该映射是 P4 内部归属约定（M-INV-2 合法源清单），不改变 OriginKind 字面值集。
- **原子性**：M-INV-3——全部校验（operations 非空、mode 存在、origin 合法）
  先于任何变更；任一失败 → runtime 逐字段不变（C1 分支证明）。
- **理由与一致性**：Spec:575/Spec:1409（模式 ∈ RuntimeState；禁第二世界状态）；
  K2：P4 的模式变更**不是**世界 effect（偏离 D3，§8.5）——它是调度簿记，
  与 active_actions 同层。sources 清单（Spec:1439-1443）经 origin 映射收进
  provenance 四值域，不新增 OriginKind（ids/provenance 冻结）。

### D-P4-16 re-propose 边界裁定（P4 唯一跨阶段裁定）

- **裁定**：re-propose 的**缝/契约/集成证明**属 P4——T01（WakeupHook 契约 +
  `wake_reason = boundary_id` 口径）、T10（Gate 证明：re-proposed 提案走完整
  流水线得 ACCEPT、RESUMED 边可复用旧实例、显式 abort 收敛 FAILED）；
  **策略内容**（何时 re-propose、re-propose 什么、fallback 链）属 P5。
- **REPAIR 边界**：P4 永不产出 REPAIR 结果——scheduler 路径恒
  `allow_rebase=False`（scheduler.py:1661-1663）⇒ stale ⇒ REJECT
  （REJECT 路径 scheduler.py:1570-1572，F2-12 pending 滞留）；REBASE/REPAIR
  是 P5 的"提案修订"语义，P5 若引入必须新开流水线入口并在 P5 Gate 声明
  （G3 移交 1 的值域断言纪律对 P5 同样有效）。
- **理由与一致性**：按 §1.4 同逻辑自行拆分（机制→P4、内容→P5），与 G3 移交 3/6（G3:164/167，重提案接缝 / 生产触发路径均标 P4/P5 域）精神一致，非逐字引自 G3；
  Gate 的 BobPolicy 是最小确定性 stub，P5 整体替换——Gate 只断言流水线
  机制（R1-R8），不断言策略正确性。

### D-P4-17 错误分类法（10 型，两族）

- **LookupError 族**（引用不存在的资源）：`ActorUnknownError`、
  `UnknownDomainError`、`UnknownBackendError`、`UnknownModeError`；
- **ValueError 族**（输入/配置违反不变式）：`CapabilityScopeError`、
  `ContextInvariantError`、`PolicyActorMismatchError`、`InvalidPositionError`、
  `SpaceInvariantError`、`ModeInvariantError`。
- **理由与一致性**：沿用 P1/P2/P3 既有 LookupError/ValueError 二族风格；
  scheduler 自带异常（SchedulerWakeupError 等）不在本表——它们是运行时异常，
  归 P3 所有。10 型全部导出（§3.11），测试按族断言。

---

## 5. Gate 场景（`tests/engine_v2/core/test_p4_gate_scenario.py`）

体例同 P3 设计文档 §5（P3:1044-1111）。Gate 单一职责：**证明 D-P4-16 的
re-propose 缝在 P3 流水线上端到端成立，且 P4 六模块在集成下满足 INV-P4-1~5**。
策略内容是 stub（BobPolicy），策略正确性不在 Gate 断言面。

### 5.1 conftest P4 节（`tests/engine_v2/core/conftest.py` 追加，置于 P3 节之后）

P4 节**复用** P3 节既有面（不重复定义）：`ENT_DEST` / `DEST_POSITION` /
`START_POSITION` / `COMP_MOVEMENT` / `TRAVEL` / `TRIGGER_ARRIVAL` /
`ORIGIN_SCENARIO` / `ORIGIN_PROVENANCE` / `R0`（conftest.py:83-106）、
`travel_spec`（conftest.py:112-122，hint 30 / interruptible /
completion_trigger="movement.arrival"）、`make_gate_registry`
（conftest.py:142-144）、`make_gate_time_policy`（conftest.py:147-149，cp=10）。

```python
# ─────────────────────────── P4 gate 节 ───────────────────────────
# D-P4-16：Gate 只证明 re-propose 流水线机制；BobPolicy 为最小确定性 stub，
# P5 整体替换策略内容。

from src.engine_v2.core.action_lifecycle import progress_of
from src.engine_v2.core.behavior_policy import run_policy_decide
from src.engine_v2.core.capability import (
    DEFAULT_NPC_CAPABILITIES,
    CapabilityGrant,
    CapabilityTable,
)
from src.engine_v2.core.context_provider import (
    ActorDecisionContext,
    ContextBuildInput,
    DefaultContextProvider,
)
from src.engine_v2.core.gameplay_mode import (
    ModeChangeRequest,
    ModeChangeResolution,
    ModeOperation,
    ModeOperationKind,
    ModeOverlay,
    ModeOverlayRegistry,
    apply_mode_change,
)
from src.engine_v2.core.ids import new_action_instance_id
from src.engine_v2.core.knowledge import (
    KNOWLEDGE_COMPONENT,
    MEMORY_COMPONENT,
    OBSERVATIONS_COMPONENT,
)
from src.engine_v2.core.scheduler import WakeupHookRegistry
from src.engine_v2.core.space import (
    GraphSpace,
    GridSpace,
    SpaceMapping,
    SpaceRegistry,
    SpatialDomain,
    decode_spaces,
    encode_spaces,
    entity_domain_positions,
)

ENT_ALICE = EntityId("ent_alice")
ENT_BOB = EntityId("ent_bob")
ENT_VAULT = EntityId("ent_vault")
COMP_SPACES = ComponentTypeId("spaces")
COMP_LOOT = ComponentTypeId("loot")
COMP_INVENTORY = ComponentTypeId("inventory")
BOB_START_POSITION = {"x": 5, "y": 0}
ORIGIN_SCRIPT_PROVENANCE = Provenance(
    producer_id=ProducerId("origin_script"), origin=OriginKind.SCENARIO
)


def make_p4_world() -> WorldState:
    """S0 世界（R0，构造形态同 conftest.py:125-139）。

    alice/bob 双域映射（overworld + tactical）；alice 无任何认识论组件
    （obs/knowledge/memory 缺席——G4-1 的空上下文即由此而来）；
    dest/vault 无 spaces 映射（A3d unmapped-domain 口径天然覆盖）。
    """
    alice_spaces = encode_spaces((
        SpaceMapping(domain_id="overworld", position=dict(START_POSITION)),
        SpaceMapping(domain_id="tactical", position="t0"),
    ))
    bob_spaces = encode_spaces((
        SpaceMapping(domain_id="overworld", position=dict(BOB_START_POSITION)),
        SpaceMapping(domain_id="tactical", position="t1"),
    ))
    return WorldState(entities={
        ENT_ALICE: EntityRecord(
            entity_id=ENT_ALICE,
            components={
                COMP_MOVEMENT: {"position": dict(START_POSITION)},
                COMP_SPACES: alice_spaces,
            },
        ),
        ENT_BOB: EntityRecord(
            entity_id=ENT_BOB,
            components={
                COMP_MOVEMENT: {"position": dict(BOB_START_POSITION)},
                COMP_SPACES: bob_spaces,
                COMP_INVENTORY: {"items": []},
            },
        ),
        ENT_DEST: EntityRecord(
            entity_id=ENT_DEST,
            components={COMP_MOVEMENT: {"position": dict(DEST_POSITION)}},
        ),
        ENT_VAULT: EntityRecord(
            entity_id=ENT_VAULT,
            components={COMP_LOOT: {"loot": ["gold_cup"]}},
        ),
    })


def make_p4_runtime() -> RuntimeState:
    """P4 S0 运行时：全新 ``RuntimeState``（logical_tick=0），调度队列
    （``scheduler_queue``）、``active_actions``、``actor_wakeups`` 全空
    （state.py:217-222 缺省构造，本工厂零预置条目）。

    与 P3 节 ``make_initial_runtime``（conftest.py:307-316）的差异：后者为
    P3 Gate 专用、预置 ev_enc@12（kind="event"，trigger_id=
    scenario.encounter_12）；P4 Gate 的事件条目（scenario.theft_12@12）
    在 S0 装配处逐字入队（Gate 测试体，形态同 conftest.py:310-315），
    故 P4 工厂只产空队列，两 Gate 的预置面互不混用。
    """
    return RuntimeState()


def make_p4_space_registry() -> SpaceRegistry:
    """双域注册表：overworld = Grid(10×10)；tactical = Graph(t0-t1-t2 链)。"""
    return SpaceRegistry({
        "overworld": (
            SpatialDomain(domain_id="overworld", backend_kind="grid"),
            GridSpace(width=10, height=10),
        ),
        "tactical": (
            SpatialDomain(domain_id="tactical", backend_kind="graph"),
            GraphSpace(nodes=("t0", "t1", "t2"),
                       edges=(("t0", "t1"), ("t1", "t2"))),
        ),
    })


def make_p4_capability_table() -> CapabilityTable:
    """alice/bob 各持 NPC 默认 3 权（Spec:895-899）；action_requirements 空。"""
    grants = tuple(
        CapabilityGrant(actor_id=actor, capability=cap)
        for actor in (ENT_ALICE, ENT_BOB)
        for cap in sorted(DEFAULT_NPC_CAPABILITIES, key=lambda c: c.value)
    )
    return CapabilityTable(grants=grants, action_requirements={})


def p4_theft_stub() -> SyncTrigger:
    """``scenario.theft_12`` → 双 set_component（vault.loot=[] /
    bob.inventory←gold_cup）；签名形态同 conftest.py:161-163。

    幂等状态守卫（E-P3-24 纪律继承，形态同 conftest.py:164-165）：
    bob.inventory 已含 gold_cup → 返回空 effect 列表。
    producer = origin_scenario（注册时声明，写入 ProposedEffect.source，
    conftest.py:156 口径）。
    """

    def evaluate(
        events: Sequence[DomainEvent], state: GuardedWorldState, depth: int
    ) -> Sequence[ProposedEffect]:
        inv = state.component_view(ENT_BOB, COMP_INVENTORY)
        if inv is not None and "gold_cup" in tuple(inv.get("items", ())):
            return []
        return [
            ProposedEffect(
                effect_id=EffectId("eff_theft_vault_001"),
                effect_type=EFFECT_SET_COMPONENT,
                source=ORIGIN_SCENARIO,
                target=EntityTarget(
                    entity_id=ENT_VAULT, component_type=COMP_LOOT
                ),
                payload={"loot": []},
                base_revision=state.world_revision,
                cause_ids=[],
            ),
            ProposedEffect(
                effect_id=EffectId("eff_theft_inv_002"),
                effect_type=EFFECT_SET_COMPONENT,
                source=ORIGIN_SCENARIO,
                target=EntityTarget(
                    entity_id=ENT_BOB, component_type=COMP_INVENTORY
                ),
                payload={"items": ["gold_cup"]},
                base_revision=state.world_revision,
                cause_ids=[],
            ),
        ]

    return SyncTrigger("scenario.theft_12", evaluate)


def p4_arrival_stub() -> SyncTrigger:
    """``movement.arrival`` → set_component(ENT_BOB, movement,
    position=DEST_POSITION)；幂等守卫：bob 已在 DEST_POSITION → 返回 []。

    与 P3 节 make_arrival_stub（conftest.py:185-214，面向 ENT_PLAYER）区分：
    本 stub 面向 ENT_BOB，注册在 P4 独立 Scheduler 实例的 named_triggers 上，
    两节互不干扰。
    """

    def evaluate(
        events: Sequence[DomainEvent], state: GuardedWorldState, depth: int
    ) -> Sequence[ProposedEffect]:
        current = state.component_view(ENT_BOB, COMP_MOVEMENT)
        if current is not None and current.get("position") == DEST_POSITION:
            return []
        return [
            ProposedEffect(
                effect_id=EffectId("eff_arrival_bob_001"),
                effect_type=EFFECT_SET_COMPONENT,
                source=ORIGIN_SCENARIO,
                target=EntityTarget(
                    entity_id=ENT_BOB, component_type=COMP_MOVEMENT
                ),
                payload={"position": dict(DEST_POSITION)},
                base_revision=state.world_revision,
                cause_ids=[],
            )
        ]

    return SyncTrigger(TRIGGER_ARRIVAL, evaluate)


def make_p4_boundary() -> DecisionBoundary:
    """B1（P4 口径）：bob 的**非阻塞** interrupt 边界——本刻事件流含
    event_type=core.set_component 的事件（命中口径 conftest.py:218-221 同款）
    → fired；blocking=False ∧ interrupt=True → 命中行动 ACTIVE→INTERRUPTED
    （scheduler.py:783-790）+ enqueue_actor_wakeup(due_tick=本刻,
    reason="B1")（scheduler.py:791-794）。

    与 P3 节 make_gate_boundary（conftest.py:217-234，blocking=True → PAUSE）
    的差异正是本 Gate 的断言面：P4 走"不暂停"的中断+wakeup 路径。
    """
    return DecisionBoundary(
        boundary_id="B1",
        actor_id=ENT_BOB,
        kind="condition",
        condition=InterruptCondition(
            condition_id="b1_theft",
            kind="event_type",
            parameters={"event_type": "core.set_component"},
        ),
        blocking=False,
        interrupt=True,
        reason="theft",
    )


def make_p4_authority_policy() -> AuthorityPolicy:
    """P4 §5.1 授权策略（closed-by-default，D-P3-23 继承；构造形态
    conftest.py:237-261）：仅 origin_scenario 可 set_component 写
    loot / inventory / movement 三个组件面。"""
    return AuthorityPolicy(rules=[
        AuthorityRule(
            rule_id="ap_set_loot",
            selector=AuthoritySelector(
                effect_type=EFFECT_SET_COMPONENT, component_type=COMP_LOOT
            ),
            allowed_writers=[ORIGIN_SCENARIO],
        ),
        AuthorityRule(
            rule_id="ap_set_inventory",
            selector=AuthoritySelector(
                effect_type=EFFECT_SET_COMPONENT, component_type=COMP_INVENTORY
            ),
            allowed_writers=[ORIGIN_SCENARIO],
        ),
        AuthorityRule(
            rule_id="ap_set_movement",
            selector=AuthoritySelector(
                effect_type=EFFECT_SET_COMPONENT, component_type=COMP_MOVEMENT
            ),
            allowed_writers=[ORIGIN_SCENARIO],
        ),
    ])


class BobPolicy:
    """re-propose 策略 stub（D-P4-16：P4 供缝，内容是最小确定性口径）。

    规则：``wake_reason == "B1"`` ∧ bob 的 movement.position ≠ DEST_POSITION
    → re-propose travel（新提案 ID 走工厂、base = context.base_world_revision）；
    否则 → None（no-op，D-P4-01）。P5 整体替换本类。
    """

    def decide(self, context: ActorDecisionContext):
        if context.wake_reason != "B1":
            return None
        mv = context.self_view.get_component(COMP_MOVEMENT)
        if mv is not None and mv.get("position") == DEST_POSITION:
            return None
        return ActionProposal(
            proposal_id=new_action_instance_id(),
            actor_id=context.actor_id,
            action_id=TRAVEL,
            arguments={"destination": ENT_DEST},
            timing=ActionTiming(duration_hint_ticks=30),
            base_world_revision=context.base_world_revision,
            provenance=Provenance(
                producer_id=ProducerId("bob_policy"),
                origin=OriginKind.BEHAVIOR_POLICY,
            ),
        )


class PassPolicy:
    """分支 B：no-op 策略（D-P4-01 None 口径）——证明"wakeup 但无 re-propose"
    路径：不产新实例、旧实例保持 INTERRUPTED、RESUMED 边仍可复用旧实例。"""

    def decide(self, context: ActorDecisionContext):
        return None


class PolicyWakeupHook:
    """P4 具体 WakeupHook（实现 scheduler.py:316-336 协议）。

    流程：guard 视图 → DefaultContextProvider.build（一次性 context，
    D-P4-04/05）→ run_policy_decide（actor_id 唯一强制，D-P4-03）→
    提案序列（None → 空序列）。实例属性 ``actor_id`` 供
    WakeupHookRegistry.register 读取（scheduler.py:355-367）。
    """

    def __init__(self, actor_id, policy, provider, table, action_registry,
                 space_registry=None):
        self.actor_id = actor_id
        self._policy = policy
        self._provider = provider
        self._table = table
        self._registry = action_registry
        self._space_registry = space_registry

    def on_wakeup(self, actor_id, view, clock, reason):
        ctx = self._provider.build(ContextBuildInput(
            actor_id=actor_id,
            state=view,
            registry=self._registry,
            capability_table=self._table,
            space_registry=self._space_registry,
            tick=clock.tick,
            wake_reason=reason,
        ))
        proposal = run_policy_decide(self._policy, ctx)
        return (proposal,) if proposal is not None else ()


def make_p4_scheduler(wakeup_hooks: WakeupHookRegistry) -> Scheduler:
    """P4 Scheduler 装配（参数名/顺序以 scheduler.py:606-622 为准；
    装配形态同 conftest.py:264-290）：travel 注册表（P3 节复用）+
    双 named stub + B1 边界 + bob wakeup hook + 空 player 集
    （B1 blocking=False，无需 player 集）。"""
    install_write_barrier()
    return Scheduler(
        make_gate_registry(),
        authority_policy=make_p4_authority_policy(),
        origin=ORIGIN_PROVENANCE,
        time_policy=make_gate_time_policy(),
        boundaries=[make_p4_boundary()],
        trigger_registry=CascadeTriggerRegistry(),
        named_triggers=frozenset({
            ("scenario.theft_12", p4_theft_stub()),
            (TRIGGER_ARRIVAL, p4_arrival_stub()),
        }),
        wakeup_hooks=wakeup_hooks,
        player_actor_ids=frozenset(),
        assert_barrier_armed=True,
    )


def make_p4_mode_overlays() -> ModeOverlayRegistry:
    """两个模式 overlay（S12/S13 依次激活；字段口径见 §3.10）。

    dialogue：priority 10、checkpoint_interval 5、systems=("dialogue_system",)、
    context={"active": True}。
    tactical：priority 20、action_filter_kind="allow"、action_ids=("travel",)、
    checkpoint_interval 20、systems=("combat_system",)、
    time_policy=TimePolicy(checkpoint_interval_ticks=20)、
    input_policy={"capture_mode": "tactical"}、context={"active": True}。
    """
    return ModeOverlayRegistry({
        "dialogue": ModeOverlay(
            mode_id="dialogue", priority=10, checkpoint_interval=5,
            systems=("dialogue_system",), context={"active": True},
        ),
        "tactical": ModeOverlay(
            mode_id="tactical", priority=20,
            action_filter_kind="allow", action_ids=("travel",),
            checkpoint_interval=20, systems=("combat_system",),
            time_policy=TimePolicy(checkpoint_interval_ticks=20),
            input_policy={"capture_mode": "tactical"},
            context={"active": True},
        ),
    })
```

**Gate 测试体内的 S0 装配**（`test_p4_gate_scenario.py`）：

```python
w0 = make_p4_world()                      # R0
rt0 = make_p4_runtime()                   # P4 节新工厂（§5.1；t0，空队列——
                                          # 区别于 P3 make_initial_runtime 预置 ev_enc@12）
rt0 = enqueue_scheduled_event(
    rt0,
    make_scheduled_event(
        "event", 12, payload={"trigger_id": "scenario.theft_12"}),
)                                         # 形态同 conftest.py:310-315（make_initial_runtime 内 ev_enc 的 enqueue_scheduled_event）；必须将返回值 rebind 回 rt0（纯函数语义：event_queue.py:150-165 返回新 RuntimeState、self 不变）

provider = DefaultContextProvider()       # prompt 缺省（opaque，D-P4-05）
hook = PolicyWakeupHook(
    ENT_BOB, BobPolicy(), provider,
    make_p4_capability_table(), make_gate_registry(),
    make_p4_space_registry())
hook_registry = WakeupHookRegistry()
hook_registry.register(hook)              # 读 hook.actor_id（scheduler.py:355-367）
scheduler = make_p4_scheduler(hook_registry)
mode_registry = make_p4_mode_overlays()

P_BOB = ActionProposal(
    proposal_id=ActionInstanceId("act_bob"),
    actor_id=ENT_BOB,
    action_id=TRAVEL,
    arguments={"destination": ENT_DEST},
    timing=ActionTiming(duration_hint_ticks=30),
    base_world_revision=R0,
    provenance=ORIGIN_PROVENANCE,
)
```

### 5.2 步骤表（S0–S13）

列：步 | 操作 | 时钟 | 队列（步后，简记）| 行动状态（progress）| 世界 rev | 事务/事件。
rev 记法：R0 = INITIAL_WORLD_REVISION（conftest.py:104）；R1/R2 = R0+1 / R0+2。

| 步 | 操作 | 时钟 | 队列 | 行动状态（progress） | rev | 事务/事件 |
|---|---|---|---|---|---|---|
| S0 | fixture 装配（§5.1 代码块）：W0（4 实体，R0）、rt0（t0，空队列）+ 预置 event 条目（due=12，trigger_id="scenario.theft_12"）、scheduler（bob hook）、mode_registry（已建未应用） | t0 | event@12 | 无活动行动 | R0 | — |
| S1 | `w, rt, out = scheduler.submit_proposal(w0, rt0, P_BOB)`（scheduler.py:1520-1593；base R0 == current R0 → revalidation ACCEPT） | t0 | cp@10、cp@20、end@30（act_bob） | act_bob ACTIVE（0→30，hint 30） | R0 | ACCEPT；0 tx / 0 evt |
| S2 | `fast_forward`（无界）→ t10：act_bob checkpoint | t10 | cp@20、end@30 | act_bob progress == (10-0)/(30-0) | R0 | 0 tx / 0 evt |
| S3 | t12：event 条目触发 → p4_theft_stub（幂等守卫通过：bob inventory 空）→ 双 set_component → 事务提交 | t12 | （event 消费）+ S4 的 wakeup@12 | — | R1 | 1 tx / 2 evt（core.set_component ×2） |
| S4 | 同刻：B1 condition 命中（本刻事件流含 event_type=core.set_component）→ act_bob ACTIVE→INTERRUPTED（at_tick=12；base_world_revision 重锚 R1）+ `enqueue_actor_wakeup(due_tick=12, reason="B1")`（scheduler.py:783-794） | t12 | + wakeup@12（reason="B1"） | act_bob INTERRUPTED（base R1） | R1 | 0 tx / 0 evt（仅生命周期迁移 + trace） |
| S5 | 同刻：`_drain_wakeup`（scheduler.py:1146-1229）：reason="B1" → PolicyWakeupHook → BobPolicy（wake_reason=="B1" ∧ position {5,0} ≠ DEST）→ P_bob2（新 ID 工厂、base=R1=current）→ `submit_proposal` 全流水线 → ACCEPT（**非** REJECT：base 与 current 一致） | t12 | cp@22、cp@32、end@42（ACT_BOB2） | ACT_BOB2 ACTIVE（12→42） | R1 | 0 tx / 0 evt（ACCEPT 不提交效果） |
| S6 | → t20：act_bob 旧 cp 条目 → 非 ACTIVE → no-op + 诊断 `checkpoint_skipped_interrupted`（D-P3-25 trace 口径） | t20 | cp@22、cp@32、end@30、end@42 | act_bob INTERRUPTED（不变） | R1 | 0 tx / 0 evt（+1 trace） |
| S7 | → t22：ACT_BOB2 checkpoint | t22 | cp@32、end@30、end@42 | ACT_BOB2 progress == (22-12)/(42-12) | R1 | 0 tx / 0 evt |
| S8 | → t30：act_bob 旧 end 条目 → 非 ACTIVE → no-op（旧实例**不**自动收敛，G3:165 移交 4 口径） | t30 | cp@32、end@42 | act_bob INTERRUPTED（不变） | R1 | 0 tx / 0 evt |
| S9 | → t32：ACT_BOB2 checkpoint | t32 | end@42 | ACT_BOB2 progress == (32-12)/(42-12) | R1 | 0 tx / 0 evt |
| S10 | → t42：ACT_BOB2 end → completion_trigger="movement.arrival" → p4_arrival_stub（守卫通过）→ set_component(bob, movement, position={30,0}) 提交 → ACT_BOB2 ACTIVE→COMPLETED | t42 | 空 | ACT_BOB2 COMPLETED；act_bob 仍 INTERRUPTED | R2 | 1 tx / 1 evt |
| S11 | 队列空 → `fast_forward` 返回（确定性终态口径 clock.py:137-148） | t42 | 空 | `out.ticks_processed == 42` ∧ `out.paused is False`（scheduler.py:304-306） | R2 | 全程合计 2 tx / 3 evt |
| S12 | `rt_mode1, res1 = apply_mode_change(request=ModeChangeRequest(request_id="req_dlg", source=ORIGIN_SCRIPT_PROVENANCE, operations=(ModeOperation(operation_kind=ModeOperationKind.ACTIVATE, mode_id="dialogue"),)), runtime=rt_final, registry=mode_registry)` | —（簿记不推进时钟） | — | active_modes == ["dialogue"]；mode_context == {"dialogue": {"active": True}} | R2（不变） | 0 tx / 0 evt |
| S13 | `rt_mode2, res2 = apply_mode_change(request=...（operations=(ACTIVATE "tactical",)）, runtime=rt_mode1, registry=mode_registry)` | — | — | active_modes == ["dialogue", "tactical"]；mode_context 恰 2 键 | R2（不变） | 0 tx / 0 evt |

**队列记法**：cp@N = act 的 action_checkpoint 条目（due=N）；end@N = 完成条目；
wakeup@N = actor_wakeups 记录。S3 的 event 条目消费后不占队列（事件队列与
调度队列分列，P2 口径）。

### 5.3 分支表（A / B / C）

| 分支 | fixture 差异 | 操作序列 | 断言锚点 |
|---|---|---|---|
| **A 主分支** | §5.1 原样（BobPolicy） | S0→S13 | R1–R7 + G4 #1–#19（§5.4） |
| **B PassPolicy** | hook 策略 = PassPolicy（decide→None，D-P4-01） | S0→S4 同 A（中断+wakeup 照常）；S5′：drain → PassPolicy → 无提案 → 队列仅剩旧 act_bob 的 cp@20/end@30；随后 `fast_forward(w, rt, max_tick=12)` 有界停在 t12（scheduler.py:1471-1505）→ `scheduler.resume_action(w, rt, ActionInstanceId("act_bob"))`（scheduler.py:1595-1613，RESUMED 边）→ 再 `fast_forward` 至终态 | R8（§5.4） |
| **C 模式错误路径** | 纯簿记面，与时间流无关（可在任意分支后执行） | C1：operations 含未知 mode_id → `UnknownModeError`；C2：`ModeChangeRequest(operations=())` → `ModeInvariantError`（构造时，M-INV-2）；C3：重复激活已激活 dialogue → ignored no-op | C1–C3 口径（原子性/no-op，§5.4） |

分支 B 的有界停止断言 `out_bounded.paused is True`；resume 后
`rt.active_actions["act_bob"].status is ActionLifecycleStatus.ACTIVE` ∧
`last_transition_tick == 12`（actions.py:234/243）；终态 `rt30.logical_tick == 30`。

### 5.4 G4 断言（19 条编号）+ R1–R8 + C1–C3

**G4 断言**（对应 Plan:577-582 六条；编号即 §6.2 机械核验表的引用编号）：

1. **[G4-1]** 终态世界（R2，S11 后）上构建 alice 的 context：
   `alice_ctx.visible_entities == frozenset({ENT_ALICE})`。
2. **[G4-1]** `alice_ctx.observations == ()` ∧ `alice_ctx.knowledge is None`
   （alice 无任何认识论组件）。
3. **[G4-1]** `alice_ctx.local_entity_views == {}` ∧
   `alice_ctx.global_entity_views is None`；**对照断言**（世界侧数据存在性）：
   `world_final.component_view(ENT_VAULT, COMP_LOOT) == {"loot": []}` ∧
   `world_final.component_view(ENT_BOB, COMP_INVENTORY) == {"items": ["gold_cup"]}`
   ——偷窃在 R1 已提交、世界可见，但 alice 的 context 完全不受影响
   （认识论边界 = 构建期固化，D-P4-05）。
4. **[G4-2]** `ctx_baseline == ctx_override`：两个 `DefaultContextProvider`
   （prompt 分别为基线文本与含越权诱导措辞的多行文本）对**同一**
   ContextBuildInput 构建 → 冻结 dataclass 逐字段相等（prompt 不进入
   context 任何字段，K4/Spec:907-909）。
5. **[G4-2]** `bob_ctx.granted_capabilities == DEFAULT_NPC_CAPABILITIES`（3 权集合，
   Spec:895-899）∧ `bob_ctx.global_entity_views is None`（未授予
   world.read.global）。
6. **[G4-2]** **正对照**：capability_table 中给 bob 显式加授
   `Capability("world.read.global")` 后重建 context →
   `bob_ctx_global.global_entity_views is not None` ∧
   `len(bob_ctx_global.global_entity_views) == 4`（全部 4 实体）——证明 #5 的
   None 是 capability 门控结果而非构建器缺陷。
7. **[G4-3]** `decoded = decode_spaces(make_p4_world().entities[ENT_ALICE]
   .components[COMP_SPACES])` → `len(decoded) == 2` ∧ 顺序保持：
   `[m.domain_id for m in decoded] == ["overworld", "tactical"]`（S-INV-3 codec 往返）。
8. **[G4-3]** `entity_domain_positions(alice_view) == {"overworld": {"x": 0, "y": 0}, "tactical": "t0"}`
   （EntityView 形态同 conftest trigger 桩的 state 访问口径，reducer.py:1738-1752）。
9. **[G4-3]** `make_p4_space_registry().backend("tactical").distance("t0", "t2") == 2.0`
   （BFS 两跳，D-P4-12；float 返回口径）。
10. **[G4-4]** S13 后：`rt_mode2.active_modes == ["dialogue", "tactical"]`
    （state.py:223，排序口径）。
11. **[G4-4]** `set(rt_mode2.mode_context) == {"dialogue", "tactical"}` ∧
    `rt_mode2.mode_context["dialogue"] == {"active": True}`（state.py:224）。
12. **[G4-4]** `res1.applied == ("activate:dialogue",)` ∧ `res1.ignored == ()` ∧
    `res2.applied == ("activate:tactical",)` ∧ `res2.ignored == ()` ∧
    `res2.new_active_modes == ("dialogue", "tactical")` ∧
    `res1.effects == () == res2.effects`（M-INV-4）。
13. **[G4-5]** `merged = merge_modes({"dialogue": dialogue_overlay,
     "tactical": tactical_overlay})`（入参 = mode_id → overlay 映射，§3.10
     `Mapping[str, ModeOverlay]` 签名）→
     `merged.winner_by_field["time_policy"] == "tactical"` ∧
     `merged.winner_by_field["checkpoint_interval"] == "tactical"` ∧
     `merged.winner_by_field["input_policy"] == "tactical"`
     （胜者 = priority 20 > 10，D-P4-14 判定序）。
14. **[G4-5]** `merged.checkpoint_interval == 20`（dialogue 的 5 被胜者覆盖）∧
    `merged.time_policy == TimePolicy(checkpoint_interval_ticks=20)`。
15. **[G4-5]** `merged.input_policy == {"capture_mode": "tactical"}`
    （不透明透传，M-INV-6）。
16. **[G4-5]** `merged.activated_systems == frozenset({"dialogue_system", "combat_system"})`
    （并集）∧ `is_action_available(merged, "travel") is True` ∧
    `is_action_available(merged, "travel_alt") is False`
    （travel_alt 不在 tactical 的 allow 集，D-P4-14 判定序）。
17. **[G4-6]** `world_final is world_before_modes`（同一对象引用：
    apply_mode_change 签名无 world 参数，测试体保持同一引用穿过 S12/S13）。
18. **[G4-6]** `world_final.world_revision == R2`（S12/S13 未推进 revision）∧
    `set(inspect.signature(apply_mode_change).parameters) == {"request", "runtime", "registry"}`
    （M-INV-3 口径，D-P4-15）。
19. **[G4-6]** monkeypatch 三处世界拷贝路径全部抛 AssertionError——
    `WorldState.model_copy`、`snapshot.snapshot`、`snapshot.restore_snapshot`
    ——`apply_mode_change` 仍正常返回（证明其不触达任何世界拷贝路径；别名
    防御 = rebuild_runtime 往返，clock.py:151-158，**不**依赖
    serialization.deep_copy_via_roundtrip——后者 P4 故意不调用）；且静态扫描
    （口径钉死）：仅扫描 `src/engine_v2/core/gameplay_mode.py` 的 **import
    语句行与 def 签名行**，源文本 casefold 后以词边界匹配
    （正则 `\bworldstate\b`）→ **0 命中**（模块类型面零世界状态引用，
    M-INV-3 结构像）。

**R1–R8**（集成断言，`test_p4_integration.py`，基于分支 A 的 S0–S11 状态快照）：

- **R1**（S4 后）：`rt12.active_actions["act_bob"].status is
  ActionLifecycleStatus.INTERRUPTED` ∧ `last_transition_tick == 12`
  （actions.py:234/243）∧ `base_world_revision` 重锚：
  `rt12.active_actions["act_bob"].base_world_revision == R1`（actions.py:241；
  S4 迁移 updates 携带 base_world_revision，scheduler.py:783-790）。
- **R2**（S5 后）：`set(rt12b.active_actions) - {"act_bob"}` 恰含 1 个新键
  （记为 ACT_BOB2，集合差捕获——ID 为工厂值，D-P4-07）∧
  `rt12b.active_actions[ACT_BOB2].status is ActionLifecycleStatus.ACTIVE`
  （ACT_BOB2 为 ACCEPT 后果：P_bob2 `timing.earliest_start_tick=None` ⇒ ACCEPT 当刻
  `start_action` 两跳复合直接落 ACTIVE，scheduler.py:1577-1586；S5 步表行
  「ACT_BOB2 ACTIVE（12→42）」同口径）∧ trace 中**无** ACT_BOB2 的 FAILED 生命周期记录
  （REJECT 路径会留 FAILED trace，scheduler.py:1570-1572——缺席 + 实例存在
  = ACCEPT 的逻辑像；直接流水线 REJECT 证明见 A7b）。
- **R3**（S5 后）：`rt12b.active_actions[ACT_BOB2].start_tick == 12` ∧
  `expected_end_tick == 42`（actions.py:235/236；hint 30，start 12）∧
  `base_world_revision == R1`（actions.py:241，context 固化口径 D-P4-05）。
- **R4**（S6 后）：trace_records 中存在 `diagnostic == "checkpoint_skipped_interrupted"`
  ∧ instance_id == "act_bob" 的 SYSTEM 记录（D-P3-25 trace 口径）。
- **R5**（S10/S11 终态）：`rt_final.active_actions[ACT_BOB2].status is
  ActionLifecycleStatus.COMPLETED` ∧ `world_final.world_revision == R2` ∧
  `world_final.component_view(ENT_BOB, COMP_MOVEMENT) == {"position": {"x": 30, "y": 0}}`
  （== DEST_POSITION，conftest.py:93）。
- **R6**（S11 终态）：`rt_final.active_actions["act_bob"].status is
  ActionLifecycleStatus.INTERRUPTED`——旧实例**不**自动收敛（G3:165 移交 4；
  收敛只能由显式操作触发）。
- **R7**（R6 之后，显式 abort）：
  `rt7 = scheduler.abort_action(world_final, rt_final, ActionInstanceId("act_bob"))`
  （scheduler.py:1615-1624，仅返回 RuntimeState）→
  `rt7.active_actions["act_bob"].status is ActionLifecycleStatus.FAILED`
  （ABORTED 边：INTERRUPTED→FAILED；**无** ABORTED 状态值，actions.py:191-205）
  ∧ world 引用/内容不变（abort 不接世界）。
- **R8**（分支 B）：有界 `fast_forward(max_tick=12)` → `out_bounded.paused is
  True`；`resume_action` 后 `rt.active_actions["act_bob"].status is
  ActionLifecycleStatus.ACTIVE` ∧ `last_transition_tick == 12`；
  `progress_of(rt.active_actions["act_bob"], 12) == 0.4`
  （action_lifecycle.py:367-380，同式 (12-0)/(30-0)，0.4 精确）；再
  `fast_forward` 至终态 → `rt30.logical_tick == 30` ∧ act_bob COMPLETED ∧
  世界 R2 ∧ `set(rt30.active_actions) == {"act_bob"}`（**无**第二实例——RESUMED
  边复用旧实例，与分支 A 的新实例路径对照）。

**C1–C3**（分支 C 口径）：

- **C1**：`request_bad = ModeChangeRequest(..., operations=(ModeOperation(operation_kind=ModeOperationKind.ACTIVATE, mode_id="nope"),))`
  → `apply_mode_change` 抛 `UnknownModeError`；异常后原 runtime 逐字段不变
  （测试体保持同一对象引用 + dump 对比）——M-INV-3 原子性。
- **C2**：`ModeChangeRequest(request_id=..., source=ORIGIN_SCRIPT_PROVENANCE, operations=())`
  → 构造时即抛 `ModeInvariantError`（M-INV-2 非空操作）。
- **C3**：S12 之后再次 ACTIVATE dialogue → `res3.applied == ()` ∧
  `res3.ignored == ("activate:dialogue",)` ∧ `rt_mode1` 的 active_modes /
  mode_context 逐字段不变（幂等 no-op）。

### 5.5 不得-断言（M1–M3，机械执行）

- **M1（P4 无世界写路径 / 无 LLM 面）**：对 P4 六模块做 AST 扫描——
  ① 不 import `engine_v2.providers.*`、不 import asyncio / random / datetime；
  不直接 import json（序列化统一走 P1 serialization 面）；
  ② 不 import transaction / transaction_executor，不调用
  `apply_transaction` / `apply_committed_effects`；
  ③ gameplay_mode.py 不调用 `set_logical_tick` / `enqueue_scheduled_event`，
  不 import scheduler 的 TimePolicy 之外符号（import 子集 ⊆ {TimePolicy}）；
  ④ Plan §13（Plan:556）"形成 Runtime 世界语义层，但仍不接实际云模型"的
  机械像：对 P4 六模块全源文本（含 docstring/注释）以**封闭标识符集**
  （封闭枚举，不得增删）：`openai`、`anthropic`、`langchain`、`litellm`、
  `ollama`、`gemini`、`gpt`、`claude`、`llm`、`provider`、`api_key`、
  `base_url` 做 casefold + 词边界匹配（正则 `\b`，大小写不敏感）→
  **0 命中**（§3.4 规范要素口径）。
- **M2（context 不持久化）**：`WorldState.model_fields` 与
  `RuntimeState.model_fields`（state.py:217-280）中无任何字段类型为
  `ActorDecisionContext` 或其容器；P4 六模块源文本中 "ActorDecisionContext"
  仅允许出现于 context_provider.py / behavior_policy.py。
- **M3（P4 不产出 REPAIR）**：P4 全部测试（gate + integration + adversarial）
  的断言面中，任何 RevalidationDecision 的 outcome ∈ {ACCEPT, REJECT}
  （值域断言，非基数断言——G3 移交 1 口径）；REPAIR/REBASE 缺席是
  scheduler 路径 `allow_rebase=False`（scheduler.py:1661-1663）的必然像，
  由 A7b 直接证明。

---
## 6. 测试规格

### 6.1 模块单测（6 个文件，Wave D）

| 文件 | 覆盖面（对应 §3 模块规格的不变式） |
|---|---|
| `test_capability.py` | C-INV-1（(actor_id, capability) 组合重复 → CapabilityScopeError）；`check_capability` 子集语义（actor 无 grant / grant 为请求 token 真子集 → False）；`DEFAULT_NPC_CAPABILITIES` 恰 3 权（Spec:895-899）；CapabilityTable 序列化往返；8 token 全集（Spec:884-892）逐值核对 |
| `test_knowledge.py` | OBS-INV-1（observation_id 唯一）；`encode/decode_observations` 与 `encode/decode_knowledge` 往返（含 confidence 边界 0/1）；Belief kind ∈ {FACT, RUMOR}（D-P4-09）；reference_entity_ids / beliefs_about 一致性；Memory 原始 JsonValue 列表（无 codec，D-P4-09）；三组件常量（OBSERVATIONS/KNOWLEDGE/MEMORY_COMPONENT） |
| `test_space.py` | S-INV-1（domain_id 模式 `^[a-z][a-z0-9_]*$`）/ S-INV-2（backend_kind ∈ 6 类，Spec:1354-1361）/ S-INV-3（域内唯一 + codec 重复拒绝）/ S-INV-4（registry 键与 domain 一致）/ S-INV-5（backend_kind↔isinstance 一致，graph→GraphSpace / grid→GridSpace）；G-INV（自环/重边/未知端点拒绝；BFS float；INF 不可达）；Grid（w×h>0；4-邻接 up/right/down/left；越界拒绝；Manhattan）；`make_backend` 保留字 → UnknownBackendError；`entity_domain_positions` 域过滤 |
| `test_context_provider.py` | CX-INV-1~7；D-P4-06 六形态矩阵（None / radius / domain / both / 未知键 → ContextInvariantError / space_registry=None）；radius=0 负例 → ContextInvariantError（r ≥ 1 边界，D-P4-06 权威）；未映射域零贡献；prompt 不透明（不同 prompt → 相同 context，A2 单测像）；可见集 = self ∪ 授予局部（A1 单测像） |
| `test_behavior_policy.py` | B-CON-1~5（同步签名机械断言、None 合法、actor 匹配唯一强制、异常穿透、无 base 预检——stale base 过缝由 A7b 流水线层面拒绝）；PlayerPolicy 子型（D-P4-02）；`run_policy_decide` 抛 PolicyActorMismatchError 的路径 |
| `test_gameplay_mode.py` | M-INV-1（overlay 字段冻结）/ M-INV-2（operations 非空 + origin 映射合法性，provenance.py:49/53/55）/ M-INV-3（三关键字签名无 world 参数）/ M-INV-4（effects 恒空）/ M-INV-5（rebuild_runtime 唯一重建通道 + 其余字段位级不变 + context 别名断裂）/ M-INV-6（input_policy 不透明透传）；merge_modes 确定性（A4 单测像）；`is_action_available` 判定序（deny > allow 交集 > 无约束）；origin 非法 → ModeInvariantError |

### 6.2 G4 机械核验表

| G4 条款（Plan:577-582） | 证明文件 | 测试函数（锚） | 断言编号 |
|---|---|---|---|
| G4-1 认识论边界 | test_p4_gate_scenario.py | `test_g4_1_epistemic_boundary` | #1–#3（+ A1 强化） |
| G4-2 prompt 不定义权限 | test_p4_gate_scenario.py | `test_g4_2_prompt_cannot_grant` | #4–#6（+ A2 强化） |
| G4-3 多空间 | test_p4_gate_scenario.py | `test_g4_3_multi_space` | #7–#9（+ A3 强化） |
| G4-4 模式簿记封闭 | test_p4_gate_scenario.py | `test_g4_4_mode_bookkeeping` | #10–#12（+ A5 强化） |
| G4-5 合并确定性 | test_p4_gate_scenario.py | `test_g4_5_merge_deterministic` | #13–#16（+ A4 强化） |
| G4-6 无第二世界状态 | test_p4_gate_scenario.py | `test_g4_6_no_world_copy` | #17–#19（+ A5/A6 强化） |
| G3 移交 2（G3:163）：真实 hook 接线的测试层披露 | test_p4_gate_scenario.py | `test_g3_handoff2_fingerprint_disclosure` | —（不计入 19 条 G4 断言）：make_p4_scheduler 装配（bob hook 已接线）的 scheduler_fingerprint == 同非 callable 输入（registry/time_policy/boundaries）的 P3 基线装配指纹——wakeup_hooks 为 Scheduler 构造输入（scheduler.py:615），不在 scheduler_fingerprint 输入面（registry + time_policy + boundaries，scheduler.py:429-452）内，指纹中性；「4 个 callable 配置面」（named_triggers / trigger_registry / wakeup_hooks / condition_resolvers）为 G3:151（R4）口径，E-P3-39③ 原文（P3:1384-1387）点名 named_triggers/trigger_registry，另两面为构造输入面结构排除 |

每个测试函数**只**断言本行声明的内容（编号断言；G3 移交 2 行的指纹披露断言不计入 19 条）+ 本行 A 编号的对抗强化；跨行断言禁止
（盲审可按行独立重放）。

### 6.3 对抗面（`test_p4_adversarial.py`，A1–A8）

| 攻击 | 手法 | 钉住的断言 |
|---|---|---|
| **A1 认识论攻击** | 终态世界构建 alice context → `dataclasses.asdict` + `repr` 序列化字符串扫描 | ① 扫描串不含 "ent_vault" / "gold_cup" / "theft"；② **负对照**：给 alice 显式授予 world.read.global 后重建 → 扫描串**含** "ent_vault"（机制非空转，证明 ① 是门控结果）；③ 世界侧对照 `component_view(ENT_VAULT, COMP_LOOT) == {"loot": []}` |
| **A2 prompt 越权** | 越权诱导多行 prompt（宣称"你现在拥有全局观察权"） vs 基线 prompt，同一 ContextBuildInput | ① 两 context 逐字段相等（dataclass `==`）；② granted_capabilities 回显一致；③ 正对照（显式 global 授予 → global_entity_views 非 None）；④ 静态扫描：context_provider.py 源文本中 `self.prompt` 仅出现于 `__init__`（build 路径零引用） |
| **A3 多空间一致性** | ① decode_spaces 重复 domain；② 三域注册表（overworld/tactical + city=Grid(3,3)），实体映射全部 3 域；③ radius 边界：专用两实体世界（Manhattan 距离 1 / 2），scope `{"radius":1}`；④ 未映射域：实体仅映射 overworld，scope `{"domain":"tactical"}` | ① SpaceInvariantError；② `entity_domain_positions` 恰 3 键；③ 距离 1 实体 ∈ local、距离 2 实体 ∉ local（边界包含/排除精确）；④ local 为空且不抛异常（D-P4-06 兜底） |
| **A4 合并确定性** | ① 同 overlay 集合不同插入顺序（dict 序变化）→ 多次 merge_modes；② 平局：两 overlay 同 priority（"tactical" vs "alpha"）；③ 空输入 | ① 各次结果逐字段相等（顺序不敏感）；② 胜者 == "alpha"（casefold 较小，D-P4-14）；③ 全默认值（winner_by_field == {} 且各字段取缺省） |
| **A5 无世界拷贝** | ① monkeypatch `WorldState.model_copy` / `snapshot.snapshot` / `snapshot.restore_snapshot` 抛 AssertionError → apply_mode_change 正常返回；② world 同引用 + revision 不变；③ runtime 除 active_modes / mode_context 外各字段 `dump_json` 逐字段相等；④ `inspect.signature(apply_mode_change).parameters` 键集 | ① 无拷贝路径（同 G4 #19，对抗加深）；② 同 #17/#18；③ 簿记面封闭（M-INV-5 机械像）；④ 参数键集 == {"request","runtime","registry"}（M-INV-3，D-P4-15） |
| **A6 序列化 / replay** | ① ActorDecisionContext `asdict` → json → 重建 → 相等；② runtime（含 mode_context）dump_json → 重载 → 相等；③ Gate S0–S11 独立跑两次（全新 fixture）→ 事件键同构；④ context 冻结性 | ① JSON-clean（K7，D-P4-04 观察面）；② mode 簿记 JSON-clean（state.py:223-224）；③ 事件键 = (event_type, world_revision, 事件发生刻)（D-P3-15① 口径，键集不含实例 ID——D-P4-07 工厂值不影响同构）；次数相等 ∧ 位置同构；每事件 `logical_tick is None`（D-P2-18，events.py:134）；④ 原 context 不可变（frozen dataclass 构造后抛异常） |
| **A7 re-propose 流水线**（①=A7a，②=A7b） | ① 全流水线无绕过：PolicyWakeupHook 源文本断言（build → run_policy_decide → 返回序列，无旁路提交）；② **stale base → REJECT**：直接 `scheduler.submit_proposal` 提交 base=R0 的提案于当前 R1 时刻 → `decision.outcome is RevalidationOutcome.REJECT`（**非** REBASE：`allow_rebase=False`，scheduler.py:1661-1663）∧ 无新 ACTIVE 状态 ActiveAction（未 start_action、未入调度队列）∧ active_actions 恰新增 1 条 FAILED 记录（instance_id == proposal.proposal_id，scheduler.py:1699-1733）∧ decision.details 非空（诊断）∧ 提案滞留 pending_proposals（F2-12）∧ 世界/调度队列零新增变更；③ hook 异常：on_wakeup 抛 RuntimeError → `SchedulerWakeupError` ∧ tick 原子回滚（调度器恢复状态 == tick 前状态，scheduler.py:1174-1177）；④ 旧实例收敛 | ① 结构性（缝唯一）；② REJECT 值域断言（M3 口径）；③ 异常面 = tick 原子性（P3 既有保证在 P4 hook 上回归成立）；④ R6/R7（INTERRUPTED 滞留 + 显式 abort → FAILED） |
| **A8 capability ⊥ authority** | ① 授权但无 grant：S3 偷窃提交在 alice/bob 无任何相关 grant 下成功；② grant 不授写权：AST 检查 capability.py 公共 API 无任何 def 的形参含 ProposedEffect / AuthorityPolicy / AuthoritySelector；③ 依赖方向：P4 六模块对 authority.py 的 import 名集合 == ∅；context_provider 对 capability.py 的 import ⊇ {Capability, check_capability}（唯一读边） | ① R1 提交成功 ∧ 世界 R1（authority-only 写）；② grant 不产生写面（Spec:907-909 机械像）；③ 零 authority 依赖边（INV-P4-4） |

### 6.4 import 边界预披露（`test_import_boundary.py` 同步，Wave F）

- L54 `CORE_SUBMODULES` 26 → 32（新增 6 模块名，与 §3.1 文件清单一致）；
- 新增常量块（形态镜像 P3 块，test_import_boundary.py:147-176）：
  `P4_SUBMODULES`（6）、`P4_TEST_FILES`（10：6 单测 + gate + adversarial +
  integration + conftest）、`P4_NONDETERMINISM_ROOTS`（= P3 同款 {datetime, time,
  random, asyncio}，test_import_boundary.py:147-176 P3 常量块同源，AST 扫描实现）、
  `P4_LLM_PROVIDER_BLACKLIST`（M1④ 封闭标识符集 12 名，规范要素与 §3.4/§5.5 一致、依 §3.4 引用）；
- 新增 2 个并行结构测试函数（镜像 P3 同名函数的 P4 实例，
  test_import_boundary.py:342-376 形态；前函数断言面含 M1④：以
  `P4_LLM_PROVIDER_BLACKLIST` 对六模块全源文本做 casefold 词边界匹配，
  0 命中）——**多行结构性编辑**，偏离 D4
  预披露于 §8.5；
- 其余（stems 集合、B2/B3 规则）对新文件**自动覆盖**，零编辑。

---

## 7. G4 六条映射表

| G4 条款（Plan:577-582 逐字序） | Spec 依据 | P4 落位（本文档） | Gate 证明 | 断言 |
|---|---|---|---|---|
| G4-1 "Alice 不知道她没有 Observation/Knowledge 的 Bob 偷窃事件"（Plan:577 逐字） | Spec:884-892 / 895-899 / 901-905 / 907-909 | capability.py + context_provider.py——Actor 认识论边界（只见所授；CX-INV-1~7；D-P4-05/06/08） | S11 后 alice context + 世界侧对照 | #1–#3，A1 |
| G4-2 "自定义 Policy 不能因为更换 Prompt 而获得 global read"（Plan:578 逐字） | Spec:907-909 | context_provider.py——prompt 不能定义权限（K4；prompt 不透明；granted 回显；B-CON-4 同型） | 双 provider 对照 + 正对照 | #4–#6，A2 |
| G4-3 "一个 Entity 可拥有 overworld + tactical 映射"（Plan:579 逐字） | Spec:1354-1361（§24 六类空间） | space.py——Space 多空间一致（S-INV-1~5；D-P4-10~13） | 双域 registry + codec 往返 + BFS | #7–#9，A3 |
| G4-4 "Dialogue + Tactical 可同时 active"（Plan:580 逐字） | Spec:1396-1452（§25；Spec:1409） | gameplay_mode.py——GameplayMode 簿记封闭（无第二世界状态；M-INV-1~6；D-P4-15） | S12/S13 双激活 + 错误路径 | #10–#12，A5，C1–C3 |
| G4-5 "TimePolicy 冲突有明确 winner"（Plan:581 逐字） | Spec:1424-1431 / 1433 | gameplay_mode.py `merge_modes`——模式合并确定性（冲突策略可检查；D-P4-14；winner_by_field） | 双 overlay 合并 | #13–#16，A4 |
| G4-6 "mode change 不复制 WorldState"（Plan:582 逐字） | Plan:556 逐字 + K2 + Spec:1409 | 六模块整体——P4 不接云模型 / 不复制世界（M1/M2 机械面；rebuild_runtime 别名防御 clock.py:151-158） | monkeypatch 拷贝路径 + 签名/源文本扫描 | #17–#19，A5，A6 |

---

## 8. 自检

### 8.1 对齐表（本文档 ↔ 上游事实面）

| 上游事实 | 上游位置 | 本文档落位 |
|---|---|---|
| P1 认识论空槽（承接 P1 前向指涉，P4 落位裁定） | state.py:255-257 | knowledge.py 整体（§3.6）；INV-P4-1（§2.3）；偏离 D6（§8.5） |
| Spec §12 Actor/Policy 接口 | Spec:818-866 | behavior_policy.py + context_provider.py（§3.8/3.9；偏离 D1） |
| Spec §13 capability 8 token | Spec:884-909 | capability.py（§3.5；8 token 逐值） |
| Spec §24 空间层 | Spec:1341-1392 | space.py（§3.7；6 类 kind，Spec:1354-1361） |
| Spec §25 模式层 | Spec:1396-1452 | gameplay_mode.py（§3.10；合并表 Spec:1424-1431） |
| P3 移交 1（REJECT 值域断言） | G3:162 | §5.5 M3 + A7b |
| P3 移交 8（冻结与台账沿用，含 G2 移交 2 每轮重新 guard 深冻结快照语义） | G3:169 | §2.2 世界读行（当刻 guard 视图上物化）+ PolicyWakeupHook 流程（§5.1） |
| P3 移交 4（INTERRUPTED 不自动收敛） | G3:165 | S8 + R6 |
| P3 移交 3/6（WakeupHook 协议接缝 / RESUMED 边，均标 P4/P5 域） | G3:164/167 | D-P4-16 整体（§1.3 第 6 条 + §1.4 行 3/6） |
| P3 移交 2（scheduler_fingerprint 输入面，扩展或披露） | G3:163 | §1.4 行 2 + §8.5-D5 + §6.2 移交 2 行（测试层披露） |
| Plan §13 目标（世界语义层，不接云模型） | Plan:556 | §1.1 + M1 ④ |
| Plan 任务表（T01/T04/T06/T09 → Q27、T10 → GFlash；T02/T03/T05/T07/T08 → QMax） | Plan:560-571 | §1.1 路由声明 + §3.12 waves |
| Spec:1427/1430 renderer/UI composition 合并（表现层归属） | Spec:1427/1430 | P8 表现层（§1.3/§10 裁定 3，M-INV-6 input_policy 直通） |

### 8.2 K1–K8 × 六模块覆盖矩阵

| 铁律 | capability | knowledge | space | context_provider | behavior_policy | gameplay_mode |
|---|---|---|---|---|---|---|
| K1 单一 authoritative state（派生表示不写回） | ✓（无写面；M2） | ✓（无写面；观察经 P5 effect 入世界） | ✓（无写面；D-P4-11） | ✓（无写面；D-P4-05） | ✓（decide 只产提案，不产 effect） | ✓（M-INV-3/4：effects 恒空） |
| K2 禁止直接状态写入（变更走权威管道） | ✓ | ✓ | ✓ | ✓（只读 guard） | ✓ | ✓（rebuild_runtime 往返 = 容器替换惯例，clock.py:151-158） |
| K3 Authority 与 Commit 分离 | ✓（CapabilityTable = 授权面：决定候选新状态之权，无写权；M2） | ✓（codec 只读；commit = 管道） | ✓（后端只读配置，D-P4-11） | ✓（build = 只读投影，不写入，D-P4-04） | ✓（decide = 提议权；commit 经 submit_proposal，scheduler.py:1520-1522） | ✓（apply_mode_change = 簿记 commit 权威管道，D-P4-10） |
| K4 prompt 不定义权限 | ✓（token 是配置） | — | — | ✓（prompt 不透明；A2） | ✓（B-CON-4） | —（origin 映射是 provenance 纪律，非 prompt） |
| K5 Agent 是 Policy 非 Engine | — | — | — | ✓（materialization 是投影，不是引擎状态） | ✓（decide→提案；无执行语义） | — |
| K6 provenance | — | ✓（Belief.origin_event_id / formed_tick 因果回指 / ObservationRecord 来源） | — | ✓（context 携带 base_world_revision 锚） | ✓（D-P4-16 BEHAVIOR_POLICY，provenance.py:49） | ✓（M-INV-2 origin 映射，provenance.py:49/53/55） |
| K7 关键状态可检查（含 JSON-clean） | ✓（ContractModel 冻结） | ✓（codec 往返；A6） | ✓（INF 永不入 JSON，D-P4-12） | ✓（frozen dataclass；A6①） | —（无状态） | ✓（M-INV-6 不透明透传；A6②） |
| K8 Deployment 与 Game Project 分离 | ✓（token = 配置；无 provider/credential） | ✓（标准骨架 = 数据契约，无项目字段） | ✓（backend kind = 枚举配置；部署内容属 P5/P8） | ✓（prompt = 不透明参数，非部署配置） | ✓（协议无部署耦合；LLM 封装属 P5） | ✓（overlay = 游戏内容数据；无内置项目预设） |

"—" = 该铁律对该模块无适用面（非缺口）；每个 "✓" 均有 §5/§6 的机械断言支撑。

### 8.3 导出账本（59 → 308）

| 模块 | 新增导出 | 小计 |
|---|---|---|
| capability | Capability, CapabilityGrant, CapabilityTable, check_capability, DEFAULT_NPC_CAPABILITIES, CapabilityScopeError | 6 |
| knowledge | BeliefKind, Belief, KnowledgeState, ObservationRecord, OBSERVATIONS_COMPONENT, KNOWLEDGE_COMPONENT, MEMORY_COMPONENT, encode_observations, decode_observations, encode_knowledge, decode_knowledge | 11 |
| space | SpacePosition, SpatialDomain, SPATIAL_BACKEND_KINDS, SpaceBackend, GraphSpace, GridSpace, INF_DISTANCE, SpaceRegistry, make_backend, SpaceMapping, SPACES_COMPONENT, encode_spaces, decode_spaces, entity_domain_positions, SpaceInvariantError, UnknownDomainError, InvalidPositionError, UnknownBackendError | 18 |
| context_provider | ContextBuildInput, ActorDecisionContext, ContextProvider, DefaultContextProvider, ActorUnknownError, ContextInvariantError | 6 |
| behavior_policy | BehaviorPolicy, PlayerPolicy, PolicyActorMismatchError, run_policy_decide | 4 |
| gameplay_mode | ModeOperationKind, ModeOperation, ModeOverlay, ModeOverlayRegistry, ModeChangeRequest, ModeChangeResolution, MergedModeConfiguration, merge_modes, is_action_available, ModePolicy, DefaultModePolicy, apply_mode_change, UnknownModeError, ModeInvariantError | 14 |
| **合计** | | **59** |

核验口径（Wave F 脚本，`core/__init__.py` 同步后执行）：
① 59 名互异 ∧ 与既有 249 名零碰撞（脚本断言）；
② 与 32 个子模块名零遮蔽——`shadowed == {"snapshot"}` 保持绿
（test_closeout.py:161 既有口径不变）；
③ `len(core_pkg.__all__) == 308`（test_closeout.py:214 249 → 308 同步）；
④ casefold 插入位符合 §3.11 规则（59 行邻接表已钉）。

### 8.4 清单

- [x] 本文档全部行号引用已对实读源码逐一核验（P1 `603535e` / P2 `f49ecd5` /
  P3 `ab0c7d2` 树 + Plan + Spec + G3 报告 + P3 设计文档体例）；
- [x] 仅允许触碰 §3.12 白名单 19 文件（6 core 新增 + 1 core 修改 + 9 test 新增 + 3 test 修改）；
- [x] 全程零 git 操作；
- [x] 仅 `.venv/bin/python`；
- [x] 无 LLM / 网络 / API key（Plan:556 逐字约束，M1 ④ 机械执行）；
- [x] 中文行文 + 英文标识符；
- [x] 未决问题 = 无（§10）；偏离 D1–D6 全部预披露（§8.5）。

### 8.5 偏离登记（D1–D6）

- **D1（同步 decide）**：Spec:818-825 `async def decide` → 同步
  `decide(context) -> ActionProposal | None`。理由：P4 自设确定性纪律（§3.4
  黑名单，非 Spec K 条款）+ P3 同步 tick
  循环（scheduler.py:1471-1505）无事件循环宿主；异步性收敛为 P5 内部实现
  细节（门面内等待/超时 → None）。Gate 影响：分支 B 覆盖 no-op 路径，异步缺席
  不削弱覆盖。B-CON-1 机械断言同步签名。
- **D2（无通用 registry 模块）**：任务书初稿含通用注册表层；P1 现实是注册表
  内联于领域模块（action_registry.py:203、authority.py:295 先例）。P4 沿用：
  SpaceRegistry / ModeOverlayRegistry / CapabilityTable 各自归属其领域模块，
  不新增 `registry.py`。
- **D3（模式簿记走 rebuild_runtime 而非世界流水线）**：Spec:575/Spec:1409
  模式 ∈ RuntimeState 且禁第二世界状态；P4 的模式变更是调度簿记（与
  active_actions 同层），不是世界 effect。P5 若需"模式变更伴随世界效果"，
  经 ModePolicy 缝产提案走主流水线（D-P4-15）。
- **D4（多行结构性测试编辑）**：test_closeout.py（L94 26→32、L214 249→308、
  注释算术块 L173-213）与 test_import_boundary.py（L54 26→32、P4 常量块、
  2 个并行函数）是**多行**结构性编辑，非单行锚点；已在 §6.4/§3.11 预披露
  精确口径。
- **D5（scheduler_fingerprint 零变化：唯一改动构造输入为指纹中性面）**：P4 真实接线
  恰好改动一个 Scheduler 构造输入——`wakeup_hooks`（`make_p4_scheduler` 装配 per-actor
  `PolicyWakeupHook` 传入 `Scheduler.__init__`，scheduler.py:615）。该改动为指纹中性：
  `wakeup_hooks` 不在 `scheduler_fingerprint` 输入面（registry + time_policy +
  boundaries，scheduler.py:429-452）内——构造输入面结构排除；「4 个 callable
  配置面」（named_triggers / trigger_registry / wakeup_hooks / condition_resolvers）为 G3:151（R4）口径，E-P3-39③ 原文（P3:1384-1387）点名 named_triggers/trigger_registry，另两面为构造输入面结构排除；指纹零变化。P4 取 G3:163
  「在测试层显式披露」分支：§6.2 移交 2 行（`test_g3_handoff2_fingerprint_disclosure`）
  断言 hook 已接线装配与 P3 基线装配的指纹相等；输入面扩展本身（真实 hook/trigger 策略
  纳入指纹）= P5 义务（G3:163）。
- **D6（P4 承接组件类型注册，沿 P1 前向指涉）**：P1 `WorldState` docstring
  （state.py:255-257，逐字）："knowledge / belief components → **组件**（``entities[*].components``
  中注册的 knowledge 类组件；Kernel 无内置，P9 knowledge 模块注册组件类型，
  避免"标准 RPG 字段进 Kernel"）"；Plan §13 任务表（Plan:565，逐字）：
  "| P4-T04 | Standard Observation / Knowledge skeleton | 开发 | 少量思考 | 纯coding | 256K | Q27 |"。
  裁定：Plan 的范围划分为准——P4-T04 将 "Standard Observation / Knowledge skeleton"
  指派给 P4，骨架的数据契约 + 组件类型注册属 P4 范围；P1 docstring 为 P1 时代前向
  指涉（Plan 将 knowledge 域拆分为 P4 骨架 / P9 内容之前所写），其 "P9 注册组件类型"
  表述不否定 P4-T04 范围。边界：**零新增 Kernel state schema 字段**——P4 仅注册 4 个 `ComponentTypeId`
  常量（OBSERVATIONS_COMPONENT / KNOWLEDGE_COMPONENT / MEMORY_COMPONENT 锚定
  state.py:255-257，P1 docstring knowledge/belief 专属槽位行，本条开头逐字引文；
  SPACES_COMPONENT 锚定 state.py:258——该行原文 "persistent gameplay state → 组件 + world_variables" 为通用项，P1 docstring 无 spaces 专属槽位行，见 §3.7 L420-421 逐字锚定）+ 纯编解码，组件载荷仍在 `entities[*].components`（P1 D-7 entity-centric）；
  无标准 RPG 字段进 Kernel（P1 docstring 意图保留）。后续阶段义务：**P9
  knowledge 模块必须复用 P4 已注册的 4 个组件类型常量（及其编解码），不得
  重复注册或新增 Kernel 字段**。一致性：§3.6 组件常量与 §3.7 SPACES_COMPONENT
  为此裁定落地；§2.3 INV-P4-1；§8.1 对齐表行 1。

---

## 9. 勘误

纯追加节（不修改/不删除正文）。

**ERR-P4-1**（P4 实现 Wave B 前置发现，Leader 裁定；按 G3 DOC-1 先例以
文档级闭合补丁应用、不复审、不占代码补充预算）：

- **症状**：§3.8 `ContextBuildInput` 原字段表（state/registry/
  capability_table/space_registry/tick/wake_reason 共 6 字段）未携带
  `actor_id`。而 `ActorDecisionContext` 输出 13 字段之首即 `actor_id`
  （§3.8 L482），`build` 的六步中第 1 步（CX-INV-1 经
  `entity_view` 解析 actor）与第 2/3/6 步（授权集回显、三组件物化、
  可见集并集）全部以 actor 为基准；`ContextProvider.build(self, input)`
  协议（§3.8 L520）除 `input` 外无 actor 参数，`DefaultContextProvider.
  __init__` 仅收 `prompt`——build 无 actor 身份来源，T02 不可实现
  （§6.1 单测口径「无 actor → ActorUnknownError」亦无输入面可承载）。
- **裁定**（纯追加，两处）：① §3.8 `ContextBuildInput` 字段表首位增
  `actor_id: EntityId` + docstring 条目（决策主体身份唯一依据；唤醒侧
  值传递传入，符合该类「全部值传递」纪律）；② §5.1 逐字
  `PolicyWakeupHook.on_wakeup` 的 `ContextBuildInput(...)` 调用首位增
  `actor_id=actor_id,` 关键字——`on_wakeup` 首参 `actor_id` 为冻结源
  scheduler.py:330-336 协议签名既有参数（`_drain_wakeup` 以被唤醒
  actor 传入），hook 侧除透传外零变更。
- **影响面核验**：`ContextBuildInput` 输入 6→7 字段；输出
  `ActorDecisionContext` 13 字段不变；`context_provider` 导出仍 6 项
  （§8.3 账本 L1759 不变，59→308 总量不变）；`build` 协议签名不变；
  G4-2「同一 ContextBuildInput → 两 provider 逐字段相等」口径在本勘误
  下成立且更严（同 actor、不同 prompt → 同 context，恰为 prompt
  不透明断言面）。

**ERR-P4-2**（P4 实现 Wave B 发现，Leader 裁定；按 G3 DOC-1 先例以
文档级闭合补丁应用、不复审、不占代码补充预算）：

- **症状**：§3.8 单测口径（test_context_provider.py）原文钉「13 字段构造与
  冻结（字段再赋值 TypeError）」。§3.8 的 `ContextBuildInput` /
  `ActorDecisionContext` 为 stdlib `@dataclass(frozen=True)`（非 pydantic）；
  frozen dataclass 字段再赋值实际抛 `dataclasses.FrozenInstanceError`
  （MRO：FrozenInstanceError → AttributeError，**非** TypeError 子类）。
  代码库基线 = `pytest.raises(FrozenInstanceError)`（test_entity_components.
  py:336/634、test_cascade.py:303、test_closeout.py:292）；Wave D 若按
  文档字面 TypeError 断言必失败。
- **裁定**：该口径改「字段再赋值抛 FrozenInstanceError」；§6.1
  test_context_provider.py 的 13 字段冻结断言口径随之统一。
- **影响面核验**：纯文档措辞修复；§3.8 13 字段结构 / 6 导出 / dataclass
  构造冻结语义零变化；TypeError 全文仅此处一处（grep 核验）；不占代码
  补充预算。

---

## 10. 未决问题

**无。**

裁定说明（3 项，均已在正文钉死，此处仅汇总以便盲审核对）：

1. **re-propose 边界裁定**（D-P4-16）：缝/契约/集成证明属 P4（T01/T10），
   策略内容属 P5——本文档按 §1.4 同逻辑自行拆分（机制→P4、内容→P5），与 G3
   移交 3/6（G3:164/167，均标 P4/P5 域）精神一致，非逐字引自 G3。P4 永不产出 REPAIR
   （scheduler 路径 allow_rebase=False，scheduler.py:1661-1663）。
2. **同步 decide 裁定**（D1/偏离 D1）：Spec §12 的 async 是接口勾勒而非
   K 铁律；确定性纪律（§3.4 黑名单，P4 自设）优先，同步门面收敛 LLM 异步到 P5 内部。
3. **renderer/UI 合并未落地**：Spec:1424-1431 的 renderer → composition 行
   属表现层（P8）；P4 的 `input_policy` 为不透明透传（M-INV-6），预留字段
   不解释内容——不裁定呈现层语义，避免越权。

*本文档为 P4 字段级实施规格（Spec B 定位，体例承 P3 设计文档 P3:1409-1421）。
Q27 / QMax / GFlash 可据此纯执行：T01/T04/T06/T09 → Q27、T10 → GFlash
（Plan:560-571）、T02/T03/T05/T07/T08 → QMax；执行路由由 L5 统一覆写为 qiyuan-self；盲审驱动的规则级补充以纯追加勘误形式进入 §9。*
