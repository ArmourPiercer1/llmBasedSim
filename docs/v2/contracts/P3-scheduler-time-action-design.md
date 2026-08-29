# P3 Scheduler / Time / Action Design — Phase 3 调度器 / 逻辑时间 / 行动生命周期 实现规范（Spec B）

- **任务**: P3-DESIGN（Phase 3 — Scheduler / Time / Action 架构设计，计划 §12；先例：P2-DESIGN）
- **文档地位**: 等价于 Plan §12「Phase 3 — Scheduler / Time / Action」的字段级/函数级实现规范。Q27 按本文档可"纯执行"实现 P3-T02/T03/T06；QMax 实现 P3-T01/T04/T05/T07 时无需再做架构判断；GFlash 实现 P3-T08 测试时无需再做场景裁剪。R3 盲审驱动新增的 **D-P3-24~D-P3-25** 与 D-P3-17~D-P3-23 同性质——规则层补全（把未定义行为钉死为可执行口径）；R4 盲审驱动新增的 **D-P3-26**（`named_triggers` 显式构造参数）与 §5.1 触发器 stub 幂等守卫机制亦属规格补全；R5 盲审驱动新增 **D-P3-27**（Gate fixture 单路化：`trigger_registry` 显式空注册表、stub 仅存 `named_triggers`，stub 幂等守卫重定位为通用契约）并钉死 F4-02/F4-03 口径（D-P3-24 重报保证限定于该行动仍处 INTERRUPTED 期间 + 无背书边缘一次性声明、`TimePolicy.pause_on_player_boundary=False` 语义落定）；R6 盲审驱动新增 **E-P3-33~E-P3-36**（L5-01 引用区间修正、F5-01 run()-级 origin `OriginKind` 钉死、F5-02 wakeup 双记录口径与 P1 冻结真相对齐、F5-03 `TimePolicy.pause_on_player_boundary=False` 重裁为 record-only——重裁 E-P3-32① 中断部分）；R7 盲审（收尾轮）驱动新增 **E-P3-37~E-P3-39**（D-P3-20 工厂区间就地更正并取代 E-P3-21/E-P3-33 该处裁定、F2-15 `causal_root_id` docstring 偏离披露、九项文档级口径——S8 transitions 承诺 / Spec §23.2 锚点 / `scheduler_fingerprint` 签名与输入面 / `BUILTIN_CONDITION_RESOLVERS` 缺省注记 / `wakeup_hooks` 缺省 / 门面返回类型 / `kind="event"` payload 互斥 / `submit_proposal` 次序 / `cause_ids` 引用区间）——**R4/R5/R6/R7 四轮盲审所驱动者均为规格补全/重裁/文档级修正，实现侧仍为纯执行、无任何架构判断**（§4 体例注、§9 勘误逐条留痕）。
- **分支**: `architecture-v2`
- **权威输入**:
  - `docs/plans/llmBasedSim_Engine_Architecture_v2_Spec.md`（下称 **Spec**）§4（K7）、§7.3、§8.2、§9、§11、§23、§43.2/43.3、§48（Scenario D）、§50（Spec B）
  - `docs/plans/llmBasedSim_Architecture_v2_Refactor_Development_Plan.md`（下称 **Plan**）§12（P3-T01~T08、核心 Gate 场景、三条"不得"、G3）
  - `docs/v2/contracts/P1-core-data-contracts.md`（下称 **P1 设计**，已冻结）与 `src/engine_v2/core/` 冻结 13 契约模块（基线 `603535e`）
  - `docs/v2/contracts/P2-kernel-pipeline-design.md`（下称 **P2 设计**，G2 已 PASS）与其勘误（尤其 **E4 测试布局**：P2 测试实际位于 `tests/engine_v2/core/`）、E6（`apply_committed_effects` 复检）
  - `docs/v2/gates/G2-gate-report.md` §6（风险 R1）、§7（**移交 P3 六条约束**）；G2 HEAD `f49ecd5`，1491 测试
- **本任务边界**: 只定义 Phase 3 的**行为模块设计**（函数签名、算法、数据流、任务切分、测试口径）。不改变任何已冻结的 P1 public contract 字段/类型/序列化形态；不修改 P2 六模块源码；P3 全部产出为**新增**模块与测试，外加 §3.11 明确列出的三处既有测试锚点机械修订（两个 19 模块列表 + 一个 `__all__` 196 规模锚点，D-P3-12，与 P2 D-P2-19 同款披露模式）。
- **已核实的集成事实**（直接引用，实现时不得重查）:
  - P1 冻结 `actions.py`：`ActionTiming`（3 可空 int tick 字段，L122-131）、`FallbackSpec`（L134-142）、`ActionProposal`（`base_world_revision` 必填 + `observation_id`/`actor_state_revision`/`valid_until` 可空 + `provenance` 必填，L145-188）、`ActionLifecycleStatus` 六态枚举（L191-204）、`ActiveAction` 14 字段（L207-244，字段块 L231-244，含 `progress`/`interruptible`/`completion_condition`/`next_checkpoint_tick`/`base_world_revision`/`last_transition_tick`/`result_summary`）；
  - P1 冻结 `state.py`：`RuntimeState` 11 字段（L192-227，含 `logical_tick`/`scheduler_queue`/`active_actions`/`actor_wakeups`/`pending_proposals`），**`ScheduledEvent`（L143-155）与 `ActorWakeup`（L158-166）已在 P1 落为占位契约**；决策 D-5（RuntimeState 变更不推进 `world_revision`，L211-212）、D-6（`logical_tick` 单一单调计数）；`RuntimeState` 不提供公共 mutator，"P3 的调度语义实现负责以重建构造产生新实例"（L213-214 原文授权）；
  - P1 冻结 `ids.py`：`ScheduledEntryId` 前缀 `sch_`（L171-177）、`ActionInstanceId` 前缀 `act_`（L160-168）、`ProducerId` 无随机段名字型（L189-198）；
  - P1 冻结 `revision.py`：`Revision`（typed int）、`is_stale(base, current, valid_until)`（L78-88：`base < current` 或 `current > valid_until` 即陈旧，`current == valid_until` 不陈旧）、`RevalidationOutcome` 四值词表（L91-101）；
  - P1 冻结 `serialization.py`：`dump_json`（L54）/`load_json`（L67）/`assert_json_clean`（L82）/`deep_copy_via_roundtrip`（L135；L41-46 为 `__all__` 块）；`snapshot.py`：`Snapshot` 信封收 `WorldState`/`RuntimeState` 全字段、`snapshot`/`restore_snapshot` 纯函数、`check_snapshot_versions`；
  - P2 双入口：`commit_transaction`（`transaction_executor.py:162-173`，`logical_tick` 参数见 L168，三类原子失败源：终检失败 / base_revision 不一致 / 应用失败）与 `apply_committed_effects`（`reducer.py:843`，含逐 effect base_revision 一致性防御复检，勘误 E6）；`check_transaction_references(state, txn) -> tuple[str, ...]`（`validation.py:857`，L2 检查器，只报告不抛）；
  - P2 写屏障：唯一武装点 `CascadeExecutor.__init__`（`cascade.py:810`）；`guard(state) -> GuardedWorldState`（`reducer.py:1590`，guard() 时刻深冻结快照视图，跨 commit 不反映新状态）；`install_write_barrier`/`write_barrier_installed`/`write_barrier_exempt`（`reducer.py:1111/1150/1065`）；
  - core 当前 19 子模块、包 `__all__` 196 成员（纯增量空间）。

> **Phase 编号口径**：沿用 P1/P2 约定——本文档一律使用 **Plan 编号**（P1–P11）。时钟语义承接 P2 设计 D-P2-18（"P2 管道不拥有时钟……tick 推进归 P3 Scheduler"）与 Plan 非目标（Spec §43.3 必重写清单中的 `tick_speed_resolve`）。

---

## 1. 目标与范围

### 1.1 定位：替代什么、实现什么

本 Phase 是 Spec §23（Scheduler / Time Contract）与 Plan §12 的落位，替代两个 v1 核心假设（Spec §43.2 应移除清单 / §43.3 必重写清单）：

1. **`tick_speed_resolve`**（`tick_speed_resolve` 每回合全量推进 + 速度换算）→ 由 **逻辑时钟 + 事件驱动 fast-forward** 取代（§2.3/§2.4）：时间只在有事件/边界处前进，无逐回合全量结算。
2. **LangGraph 固定全局 tick 流水线**（`all NPC decide every turn`、`universal tick`）→ 由 **Actor wakeup + 决策边界** 取代（§3.7/§3.8）：NPC 只在 wakeup 时刻决策，玩家只在 blocking 边界交出/收回控制，调度器不再有固定回合骨架。

落地的 Kernel 不变量（Spec §4 K7，原文 L326-328）：

> Scheduler、ActiveAction、GameplayMode、Actor wakeup 等关键 runtime 状态 MUST NOT 完全隐藏在不可序列化 coroutine/generator continuation 中。

P3 的 K7 程序化落位（三条）：

- **状态显式**：调度的全部真相 = `(WorldState, RuntimeState)` 对——`logical_tick`（`state.py:218`）、`scheduler_queue`（L220）、`active_actions`（L221）、`actor_wakeups`（L222）、`pending_proposals`（L226）均为冻结契约字段；下一调度步骤可仅由 `take_due(queue)` 推导（§2.4）；
- **可恢复**：`snapshot(world, runtime)`（P1 `snapshot.py`）收全部字段；`restore_snapshot` 后调度器从同一状态继续，无任何 continuation（§4-D-P3-15、G3-2/G3-4 测试）；
- **无隐藏控制流**：P3 七模块不得 import `asyncio`，不得把 coroutine/generator 存进状态（§8.3 import 边界）；中断/恢复是状态迁移（D-P3-07），不是暂停的协程。

GameplayMode 不在 P3 范围（`active_modes`/`mode_context` 字段语义归 P4，P1 设计占位纪律）；K7 对本 Phase 的约束面即上述三项。

### 1.2 逐条回应 Plan §12 三条"不得"

| # | 不得（Plan §12 原文） | P3 机制落位 | 可测试表述 |
|---|---|---|---|
| 1 | 因 NPC 1 秒动作强迫玩家每秒操作 | 边界阻塞规则（D-P3-10）：blocking 暂停只认 `player_actor_ids`；NPC 边界非阻塞 → 记录 + 入队 `ActorWakeup`，fast-forward 不中断 | §5.5-M1：NPC 每 tick 短动作 ×200（t=0..199 每 tick 排一次，200 个队列条目——该 fixture 数字唯一口径），玩家 30 tick 旅行——t<12 期间暂停次数 == 0，玩家零 wakeup |
| 2 | 通过"把 position 直接设置到终点"伪装长动作 | progress 由时钟推导（D-P3-08）：位置只能作为**完成时刻**的 ProposedEffect 经 P2 管道提交（`ActionSpec.completion_trigger`，§3.5）；中途无任何位置 effect；progress 不可被 effect 篡改 | §5.5-M2：t=10/12/20 位置恒为起点；首个位置变更事务恰在 t=30（R2）；t=12 时 progress==12/30 而非 1.0 |
| 3 | 使用不可检查 coroutine 作为唯一 scheduler truth | K7 三落位（§1.1）+ 声明式中断条件（D-P3-09，数据模型内无闭包）+ 调度器纯函数化（D-P3-03 确定性论证） | §5.5-M3：同状态两次 fast-forward 结果恒同；snapshot round-trip 后决策不变；七模块无 `asyncio` import（import 边界自动覆盖） |

### 1.3 范围边界（P3 做 / 不做）

**做**：逻辑时钟语义与推进；调度队列词表/排序/抽取；ActionRegistry 结构与参数校验；生命周期迁移表与迁移纯函数；progress/checkpoint/completion 语义；InterruptCondition/DecisionBoundary 与阻塞规则；wakeup hook 协议；通用 stale proposal revalidation；fast-forward/step/submit 编排门面；调度状态序列化与回放判据；错误族；P3-T08 全部测试。

**不做**（归属显式登记，与 P2 §13 同纪律）：

1. **YAML/项目文件加载**（action registry 的 YAML→`ActionSpec` 构造、tick↔分钟换算常数）归 **P5** content 层（D-P3-06/D-P3-13；core import 边界无 yaml，P2 D-P2-08 先例）；
2. **LLM/Policy 管线**（`BehaviorPolicy` 真实现、`ContextProvider`、观察签发）归 **P4**；P3 的 `WakeupHook`/提案入口只接受已构造好的 `ActionProposal`（P1 冻结契约）；
3. **持久化介质 / 分支 / 存档 IO**（`PersistenceBackend`、branch 能力降级报告）归 **P8**；P3 只提供 `scheduler_fingerprint` 与回放判据；
4. **开发命令面**（pause/step 的 devtools 命令、`DevelopmentCommand`）归 **P8**；P3 只暴露 `Scheduler.step()` 原语（Spec §22 承载态 `STEPPING` 的语义在此）；
5. **GameplayMode overlay 语义**（`active_modes` 读写规则、TimePolicy 与 mode 的联动）归 **P4**；P3 的 `TimePolicy` 不读 mode 字段。

---

## 2. 逻辑时间模型

### 2.1 Spec §23.1 六层时间映射表

Spec 要求区分六层时间（L1280-1289）。P3 只**拥有第 3 层**，其余层显式映射到既有机制，不新建第二时钟：

| Spec §23.1 层 | P3 机制 / 归属 |
|---|---|
| 1. Action duration | `ActionTiming.duration_hint_ticks` + `DurationPolicy` 解析（§3.5）→ `ActiveAction.expected_end_tick`（D-P3-08） |
| 2. Actor decision horizon | `ActorWakeup.due_tick`（`state.py:158-166`）+ `WakeupHook`（§3.8）；P4 决定 horizon 取值，P3 只执行 |
| 3. **World logical time** | **`RuntimeState.logical_tick`（权威，P1 D-6 单一单调计数）+ `LogicalClock` 值类型（§2.3）** |
| 4. Physics integration timestep | SpaceBackend / dynamics backend 私有（P5/P8）；`RuntimeState.rng_state`/`backend_refs` 字段已预留（`state.py:225-227`）；P3 不消费 |
| 5. Player-facing turn | blocking `DecisionBoundary` → 调度暂停 = 玩家回合（D-P3-10）；暂停期间逻辑时钟**不前进**（无墙钟语义） |
| 6. Narrative time compression | **fast-forward 本身**（§2.4）：压缩 = 跳变推进，无逐 tick 渲染 |

### 2.2 时间单位决策（D-P3-01）

**决策：1 tick ≙ 1 世界分钟（默认映射）。core 层单位无关，只计数 tick。**

问题：Gate 场景以"分钟"计（"30 min travel"、"t = 12 min"），而冻结契约的全部时间字段都是 **int tick**（`ActionTiming.*_tick`、`ScheduledEvent.due_tick`、`ActiveAction.start_tick/next_checkpoint_tick/last_transition_tick`、`RuntimeState.logical_tick`）——需要裁定 tick 与世界分钟的换算。

备选：

- **A：1 tick = 1 分钟**（选择）；
- **B：1 分钟 = 60 ticks（tick = 1 秒）**。

理由（选 A）：① **Gate 场景字面对齐**——Plan §12 写 `progress == 12/30`，A 下 start=0 / duration=30 / encounter@12 逐字相等；B 下同一断言变 `720/1800`，偏离 Plan 字面且测试数字全 ×60。② **事件驱动无亚分钟消费方**——fast-forward 只跳变到事件边界（§2.4），tick 只是刻度而非步长；B 的每秒粒度 MVP 无消费方（第 4 层物理步长归 backend，不经 scheduler）。③ **子 tick 动作有确定处置**——NPC"1 秒动作"在 A 下为亚 tick → **钳制为 1 tick + 诊断**（`resolve_duration` 对 <1 的结果钳到 1，§3.5）；是显式量化规则而非精度损失（D3 披露，§8.5）。④ **换算常数是内容决定**——若某项目真要每秒粒度，P5 内容层设换算常数（`ticks_per_game_minute=60`）即可，core 零改动；A 不锁死未来，只是**默认**。

映射规则（实现口径）：`duration 分钟数 × TICKS_PER_GAME_MINUTE`（默认常数 1，P5 注册）；`ActionTiming` 三字段与 `ActiveAction` 各 tick 字段**一律已是 tick 单位**，core 内不再出现"分钟"字面量。Gate 场景全程用默认映射：30 min travel = 30 ticks。

### 2.3 LogicalClock（D-P3-02）

**决策：不新增状态载体。** 权威时钟恒为冻结字段 `RuntimeState.logical_tick`（`state.py:218`，P1 D-6）；`LogicalClock` 是 **Revision 同款的值类型**（typed 值、无状态引用——`revision.py:43-51` 先例），用于计算与派生视图：

```python
# core/clock.py
class LogicalClock(ContractModel):
    """逻辑时钟值类型（Revision 模式，D-P3-02）。

    不是第二权威：任何时刻权威值 = RuntimeState.logical_tick（K1 同源
    纪律）；本对象仅作派生视图与纯计算，经 LogicalClock.of(runtime) 投影、
    经 set_logical_tick 写回，生命周期不超出一次纯函数求值。
    """
    tick: int = Field(ge=0)

    @classmethod
    def of(cls, runtime: RuntimeState) -> "LogicalClock": ...   # 投影（新增）
    def elapsed(self, since_tick: int) -> int: ...              # max(0, tick - since_tick)
    def advanced(self, delta_ticks: int) -> "LogicalClock": ... # delta >= 0，否则 ClockRollbackError
```

性质与口径：

- **单调**：`set_logical_tick(runtime, tick)` 是调度器**唯一**时钟写点（重建模式，§3.3）；`tick < runtime.logical_tick` → `ClockRollbackError`（回退只允许发生在状态级 restore，即整对 `(world, runtime)` 从快照还原，不经时钟函数）；
- **无墙钟**：core 七模块 import 边界禁 `datetime`/`time`/`random`（§8.3）；暂停期间（玩家回合）逻辑时间冻结——这是 Spec 第 5 层的叙事约定，也是"暂停消耗墙钟时间"被排除的原因（墙钟不可复现，G3-4 回放一致性立即崩塌）；
- **可序列化**：时钟是 `RuntimeState` 内的 int，`dump_json`/`load_json` round-trip 恒等（P1 `serialization.py` 基础设施，零新增）；`LogicalClock` 自身也是 ContractModel（round-trip 可测）。
- 与 revision 解耦（P2 D-P2-18 原文）：tick 推进**不**推进 `world_revision`（P1 D-5）；经 `CascadeExecutor` 提交的事务/事件 `logical_tick` 恒为 **None**（P2 不拥有时钟，D-P2-18：`run()` 无 tick 参数，`cascade.py:867-874`，内部 commit 未传 `logical_tick`，`cascade.py:1171-1180`）——逻辑时刻归属由 `RuntimeState.logical_tick`（唯一权威时钟）+ `ScheduledEvent.due_tick` + `LifecycleTransition.at_tick` + outcome 按调用 tick 水位（`ticks_processed`）承载（D-P3-20）；Gate 场景若确需打戳事件，须先经 P2 勘误流程（`CascadeExecutor.run` 增 tick 参数 + 新 D 项），P3 范围外、不作为隐性预期。

### 2.4 fast-forward 推进算法（D-P3-03）

**决策：事件驱动跳变主循环。** 全部逻辑：

```text
fast_forward(world, runtime, max_tick=None):
    # —— 入口首检（未响应暂停幂等重报，D-P3-24，重入零副作用，置于播种之前）：
    #    若 ∃ a ∈ runtime.active_actions.values()：a.status == INTERRUPTED，且 ∃ b ∈ boundaries：
    #    b.blocking 且 b.actor_id == a.actor_id 且 a.actor_id ∈ player_actor_ids
    #    → 立即返回同一暂停（paused=True，pause_reason 按注册序取首个命中边界、
    #    tick = 当前 logical_tick，ticks_processed = 当前 logical_tick，
    #    transactions/events/transitions/errors 全空）；不推进时钟、不消费队列
    #    （cp@20/end@30 等条目不处理）；纯 (WorldState, RuntimeState, config) 派生，
    #    resume/abort（status 离开 INTERRUPTED）后规则自动失效（step 同口径）；重报保证
    #    **限定于该行动仍处 INTERRUPTED（玩家未响应）期间**（D-P3-24③，R5/F4-02）——
    #    无 INTERRUPTED 背书的边缘（玩家 blocking 边界命中但无行动进入 INTERRUPTED）：
    #    暂停仅返回一次（BoundaryReport.fired 记录 + trace 留痕、已送达），重入正常推进、
    #    该边界不重检——一次性，非"静默跳过"（D-P3-24⑥）；且本规则以
    #    TimePolicy.pause_on_player_boundary=True 为前置，False 时不返回暂停、
    #    重报规则不生效（R5/F4-03；R6/F5-03 重裁 record-only：False 路径行动不被中断、
    #    无 INTERRUPTED 背书，E-P3-36；§3.8 字段位口径）。
    # —— 循环前播种（幂等，D-P3-22）：对 kind="scheduled" 且 due_tick > 当前刻的
    #    边界，补入一条 kind="decision_boundary" 队列条目（按 boundary_id 去重，
    #    entry_id 经 new_scheduled_entry_id() 签发；条目只是时钟停靠点，无 payload
    #    effect；重复调用不重复补入）——
    while True:
        batch_opt = take_due(runtime)                 # 抽走最小 due_tick 的整批（同刻批，稳定 FIFO）
        if batch_opt is None: return terminal         # 队列空 = 无更多调度工作（确定性终点）
        (runtime, batch) = batch_opt
        t = batch[0].due_tick
        if max_tick is not None and t > max_tick: return bounded   # step/测试边界
        if t > LogicalClock.of(runtime).tick:
            runtime = set_logical_tick(runtime, t)    # 跳变（不逐 tick 迭代；D-P3-03 核心）
        for entry in batch:                           # 同刻批按队列序＝插入序 FIFO（D-P3-05；Gate 分支 A 的 end@30（t=0 入队）
                                                       # 先于 cp@30（t=20 派生）——先入队先处理，§5.3 A2/A4）
            match entry.kind:
                "event":            # payload: {"trigger_id": …} 或显式 effects
                    world, runtime, txs = _commit_scheduled(world, runtime, entry, t)
                "action_start":     start_action(...)                 # PROPOSED→…→ACTIVE
                "action_checkpoint":apply_checkpoint(...)             # re-anchor（D-P3-08）；非 ACTIVE 实例守卫 no-op
                                                                       # + 诊断 TraceRecord（F2-02/D-P3-25，§3.6）
                "action_end":       若仍 ACTIVE 且到点 → complete_action(...)  # 完成 effect 经管道
                "deadline":         若仍 ACTIVE → fail_action(deadline_missed)
                "wakeup":           _drain_wakeup(...)                # WakeupHook（§3.8）
                "decision_boundary": 预注册边界（刻到即视为候选，参与刻后求值；
                                     条目由循环前播种入队，D-P3-22）
        # —— 刻后求值（顺序固定，D-P3-09/10）——
        view = guard(world)                               # 每刻提交后重新 guard（G2 移交 2）
        report = evaluate_boundaries(view, runtime, tick=t, events=events_at_tick, config)
                                                            # 完整签名见 §3.7：config 展开为 (boundaries, registry, player_actor_ids)；tick 显式传当前刻（D-P3-21）
        for (boundary, action_ids) in report.fired:
            b = boundaries 中 boundary 对应的 DecisionBoundary        # config 级读（确定性；注册序稳定）
            player_hit = b.blocking 且 b.actor_id ∈ player_actor_ids  # 玩家 blocking 命中（D-P3-10）
            if player_hit 且 not time_policy.pause_on_player_boundary:
                continue    # flag=False（R5/F4-03；R6/F5-03 重裁 record-only，E-P3-36）：边界仍 fired
                            #（fired 记录 + trace 照常），但不中断可中断行动——行动生命周期照常推进
                            #（checkpoint/end 条目正常处理、行动正常 COMPLETED）；npc 分支不受辖
            对 action_ids 中 status==ACTIVE 且 interruptible 的 aid:
                transition_action(runtime, aid, INTERRUPTED, at_tick=t,
                    updates={'base_world_revision': world.world_revision})   # 中断时刻 re-anchor 至当前世界 revision（§3.6 docstring / D-P3-08；G3-1 断言 6）
        for (boundary_id, actor_id) in report.npc_notices:    # 非阻塞命中（D-P3-10 选 B；不受 pause_on_player_boundary 辖制）
            runtime = enqueue_actor_wakeup(runtime, actor_id, due_tick=t, reason=boundary_id)
                # （收敛路径 D-P3-25：P4/P5 actor 重新提案；P3 层只入队不执行；
                #  双记录口径 §2.5 尾注：两条记录 (actor_id, due_tick) 一致，payload 仅 actor_id、
                #  reason 仅存 ActorWakeup 记录、不入 payload）
        if report.player_blocking 且 time_policy.pause_on_player_boundary:   # 仅玩家（D-P3-10）；flag=False 时不返回暂停（R6/F5-03，E-P3-36）
            return paused(SchedulerOutcome(pause_reason=boundary, tick=t))
    # 循环外：无暂停 → 队列耗尽终点
```

确定性论证（五要素，G3-4 的理论基础）：

1. **批次序列唯一**：队列是 `(due_tick, 插入序)` 的全序（D-P3-05 写时稳定排序 + 同刻 FIFO）→ 批序列唯一；
2. **时钟跳变由批决定**：`t = batch[0].due_tick`，无随机、无墙钟、无 I/O；
3. **提交路径确定性**：批内全部世界写入经 P2 管道（`CascadeExecutor`，G2 已验证确定性：冲突策略固定顺序、事件 ID 预分配 `transaction_executor.py` 步骤 3）；
4. **求值顺序固定**：边界按注册序、wakeup 按队列序、hook 同步纯函数（§3.7/§3.8）；
5. **原子刻**：单刻处理中任何 P3 错误 → 返回刻前状态对（不可变值 = 天然回滚，§4-D-P3-16）→ 部分提交不可见。

∴ `fast_forward` 结果是 `(WorldState, RuntimeState, Scheduler 配置, max_tick)` 的纯函数。推论（即测试）：同输入两次运行产出逐事件同序；snapshot round-trip 不改变后续决策。

边界情形：批处理中**新入队且 due_tick == t** 的条目（如 checkpoint 派生下一 checkpoint、wakeup hook 提案派生新事件）——追加至同刻批尾部（稳定 FIFO 自然覆盖），仍在同一 `t` 内处理完；`due_tick > t` 者进入后续迭代；`due_tick < t` 在入队时即被 `QueueInvariantError` 拒绝（D-P3-05）。

### 2.5 ScheduledEvent 与队列（D-P3-04 / D-P3-05）

**决策：复用 P1 冻结 `ScheduledEvent`，不新建条目类型。** P1 已落：

```python
# state.py:143-155（冻结，零改动）
class ScheduledEvent(ContractModel):
    entry_id: ScheduledEntryId          # sch_ 前缀（ids.py:171-177）
    due_tick: int
    kind: str                           # "P3 定词表"（P1 原文授权）
    payload: dict[str, JsonValue]
```

P3 新增的只有三样：**kind 封闭词表**、**逐 kind payload 契约**、**队列操作纯函数**（均在 `event_queue.py`，§3.4）。序列化零新增：条目经 P1 `dump_json`/`load_json` round-trip（`entry_id` 前缀重建、`assert_json_clean` 可测，G3-2）。

kind 词表与 payload 契约（`make_scheduled_event` 在入队点强制校验——可检查不静默）：

| kind | 语义 | 必填 payload 键 | 处理动作（§2.4 match 分支） |
|---|---|---|---|
| `action_start` | 提案已验收、预约开跑（`earliest_start_tick` 延迟开跑） | `instance_id` | `start_action` |
| `action_checkpoint` | 周期检查点（re-anchor） | `instance_id` | `apply_checkpoint` |
| `action_end` | 预期完成刻 | `instance_id` | 到点且 ACTIVE → `complete_action` |
| `deadline` | `ActionTiming.deadline_tick` 截止 | `instance_id` | 到点且 ACTIVE → `fail_action("deadline_missed")` |
| `wakeup` | Actor 决策时刻（Spec §23.1 第 2 层） | `actor_id` | `_drain_wakeup` → `WakeupHook` |
| `decision_boundary` | 预注册决策边界（刻到即候选；由 `fast_forward`/`step` 循环前播种入队，D-P3-22） | `boundary_id`、`actor_id` | 参与刻后边界求值（no-op 分支：条目本身无 effect） |
| `event` | 通用外部事件（如 t=12 encounter） | `trigger_id` 与 `effects` 恰居其一（互斥，均声明式） | `_commit_scheduled`（经 P2 管道） |

> `kind="event"` 的两种 payload 形态都是**声明式**（K7/不得 3）：`{"trigger_id": "scenario.encounter_12"}` 引用**命名的** P2 `CascadeTrigger` 协议（cascade.py:473；注册表 `CascadeTriggerRegistry`，cascade.py:573，别名 `TriggerRegistry`，cascade.py:650——注册表持有）；`{"effects": [ProposedEffect JSON…], "producer": "…"}` 携带显式预声明效果批。payload 内禁止可执行物；缺 `trigger_id` 且无 `effects`，或两者同时存在 → `QueueInvariantError`（互斥，唯一口径，R7-S4 风险3）。

队列有序性（`event_queue.py` 不变量，`enqueue_scheduled_event` 维护）：

1. **写时稳定排序**：入队后按 `due_tick` 单键稳定重排（相等 tick 保持插入相对序）——队列任意时刻肉眼可检（K7），`take_due` 无需运行时排序；
2. **同刻序 = 稳定 FIFO**：同 `due_tick` 批内按列表位置（插入序）处理；调度器永不重排（重排 = 不确定性源）；
3. **禁止过去调度**：`due_tick < runtime.logical_tick` → `QueueInvariantError`（时间只能向前，与 D-P3-02 单调性同源）；
4. **身份唯一**：`entry_id` 由 `new_scheduled_entry_id()`（`sch_`）签发，重复 `entry_id` 入队 → `QueueInvariantError`（构造点拒绝，KBC-2 同款去重纪律）。

`ActorWakeup`（`state.py:158-166`，冻结）与队列的关系：`actor_wakeups` 是**独立的待唤醒列表**（Spec §8.2 单列字段），`kind="wakeup"` 的队列条目是它的**时刻化引用**——wakeup 到期时由 `enqueue_actor_wakeup` 写入 `actor_wakeups`（P4 语义的占位执行）；P3 只保证两条记录在 `(actor_id, due_tick)` 上一致——`ActorWakeup` 记录的 `reason` 字段（`state.py:166`，可空）仅存于 `actor_wakeups` 侧，`kind="wakeup"` 队列条目的 payload 仅携带 `actor_id`（上表），`reason` 不入 payload（测试口径，§6.1）。

---

## 3. 模块切分与任务包映射

### 3.1 文件清单（`src/engine_v2/core/` 新增 7 个）与命名论证

| 文件 | 职责 | 对应任务包 | 命名论证 |
|---|---|---|---|
| `clock.py` | `LogicalClock` 值类型、唯一时钟写点、**P3 错误基类族宿主**（依赖叶模块，无 P3 内部 import → 无环） | P3-T01 | 时间原语独立成文，与 P2 `transaction_executor.py`"契约/行为分文件"同纪律；错误基类置此避免跨模块环（§4-D-P3-16） |
| `event_queue.py` | 队列条目构造（kind 词表 + payload 契约）、排序不变量、同刻批抽取 | P3-T01 | 弃用建议名 `scheduled.py`：该名与 P1 冻结类 `ScheduledEvent` 撞语义边界（类型 vs 队列行为）；`event_queue` 直指"队列行为"，与 P2 `conflicts.py` 按行为而非数据命名一致 |
| `action_registry.py` | `ActionSpec`/`ParameterSpec`/`DurationPolicy`/`ActionRegistry`、参数 schema 校验、时长解析 | P3-T02 | 与 P2 `authority.py`（`AuthorityPolicy` 载体）同构：注册表 = 数据契约 + 纯校验函数 |
| `action_lifecycle.py` | 迁移表、`transition_action`、progress/checkpoint/resume/complete/fail 纯函数 | P3-T03 + T04 | 生命周期是行动域行为核心，与 P1 `actions.py`（纯数据）分文件（P2 D-P2-02 先例） |
| `interrupt.py` | `InterruptCondition`/`DecisionBoundary` 声明式模型、内置 4 kind 纯求值、边界报告 | P3-T05 | 中断/边界：Spec §23.2 decision boundary 概念（Spec L1305）；`DecisionBoundary` 为 P3 新增单列类型、定位为 §23.3 SHOULD 显式状态清单的扩展项（清单为 SHOULD 非穷举，扩展不构成违背）；独立成文便于 P5 注册扩展条件 |
| `revalidation.py` | 通用 stale 提案 revalidation（任意 producer）、REBASE 纯变换 | P3-T07 | "单一实现对任意 producer 生效"（G2 移交 3）需要独立模块，避免被行动域私有化 |
| `scheduler.py` | `Scheduler` 门面、`fast_forward`/`step`/`submit_proposal`、`TimePolicy`、`WakeupHook` 协议与注册表、编排 | P3-T04/05/06 | 编排层与时间原语分离：`fast_forward` 依赖其余 6 模块（依赖图顶端），单独成文保持 P3 内部依赖无环 |

命名纪律：7 个新模块名均不与现有 19 个子模块名及包 `__all__` 导出名相撞（closeout 撞名即测试失败，天然防线，P2 §10.3 机制原样生效）。

### 3.2 依赖图与 import 纪律

```text
（基座：P1 13 冻结模块 — ids/revision/components/entity/provenance/effects/actions/events/transaction/state/trace/serialization/snapshot；P2 六模块 — reducer/authority/validation/conflicts/transaction_executor/cascade）
        │
        ├─ clock.py            （只依赖 P1：state/revision/serialization + entity（ContractModel 基类，entity.py:51） + stdlib）
        ├─ event_queue.py      （P1 + clock.py）
        ├─ action_registry.py  （P1：actions/ids + entity（ContractModel 基类，entity.py:51） + stdlib + pydantic）
        ├─ interrupt.py        （P1 + P2 reducer.guard 视图类型 + clock.py）
        ├─ revalidation.py     （P1：revision（is_stale）/ state（has_entity）；P2
        │                       validation.check_transaction_references 仅测试口径一致性复用（§6.1），不入运行时路径）
        ├─ action_lifecycle.py （P1：actions/state/revision/ids/trace/effects/entity + stdlib + pydantic
        │                       + clock/event_queue/action_registry；纯函数不消费 P2 符号，
        │                       apply_checkpoint 返回的 TraceRecord 为 P1 trace.py 类型，R4/F3-06）
        └─ scheduler.py        （以上全部 + P2 cascade.CascadeExecutor/trigger 协议）
```

依赖无环（箭头单向）。import 边界**继承 P1 设计 §0.3 / P2 §1.3**：只允许 stdlib + pydantic + 同包 `src.engine_v2`；既有三类全局黑名单（provider SDK / v1 包 / 网络 IO）对 core 全部文件保持不变，另加 P3 专项：禁 `datetime`/`time`/`random`/`asyncio`（无墙钟、无隐式随机、无协程真相，§8.3）——P3 专项谓词**仅作用于 7 个新模块**（`tests/engine_v2/core/test_import_boundary.py` 新增 `P3_SUBMODULES` 元组 + 仅对该集合文件生效的 P3 专项谓词，按模块分流的作用域实现；3 个 P1 冻结模块 `trace.py:46`/`events.py:36`/`snapshot.py:44` 保留诊断性 `datetime` import，P1 铁律 3、字节冻结，不受 P3 专项约束；B2 运行时增量扫描维持原三类谓词，`datetime` 由既有冻结模块带入属预期、不判违规——§6.4/§8.5-D4 预披露的结构性测试修订）。

### 3.3 `clock.py`（P3-T01）

```python
# LogicalClock 值类型定义见 §2.3（同一模块；tick: int = Field(ge=0)，of/elapsed/advanced 三方法）

def set_logical_tick(runtime: RuntimeState, tick: int) -> RuntimeState: ...  # 唯一时钟写点；tick < 当前 → ClockRollbackError（D-P3-02）；内部经 rebuild_runtime

def next_due_tick(runtime: RuntimeState) -> int | None: ...  # min(queue.due_tick)；队列空 → None（fast-forward 终点判据，§2.4）

def rebuild_runtime(runtime: RuntimeState, **updates: Any) -> RuntimeState:
    """RuntimeState 重建公共缝隙（P1 state.py:213-214 授权的行为侧实现）：model_dump() →
    dict 更新 → model_validate()——走 P1 唯一合法序列化路径（serialization.py 规则 1），
    不触碰 P2 写屏障四逃逸路径；重跑 active_actions 键一致性 model_validator。
    P3 全部 RuntimeState 簿记变更统一经此函数。"""

class SchedulerError(ValueError): ...                 # 新增（P3 错误基类，D-P3-16）
class ClockRollbackError(SchedulerError): ...
```

### 3.4 `event_queue.py`（P3-T01）

```python
SCHEDULED_EVENT_KINDS: Final[frozenset[str]]   # 新增：7 kind = §2.5 表 kind 列（词表以 §2.5 表为唯一定义处）

def make_scheduled_event(kind: str, due_tick: int, *,
                         payload: dict[str, JsonValue] | None = None,
                         entry_id: ScheduledEntryId | None = None) -> ScheduledEvent: ...
    """kind 词表 + 逐 kind 必填 payload 键校验（§2.5 表）+ due_tick >= 0；entry_id 缺省
    new_scheduled_entry_id()（sch_ 前缀，ids.py:263）；违例 → QueueInvariantError（可检查不静默）。"""

def enqueue_scheduled_event(runtime: RuntimeState, event: ScheduledEvent) -> RuntimeState: ...
    """追加 + 写时稳定排序（due_tick 单键，D-P3-05）；due_tick < clock / entry_id 重复 → QueueInvariantError。"""

def take_due(runtime: RuntimeState) -> tuple[RuntimeState, list[ScheduledEvent]] | None: ...
    """抽走最小 due_tick 的整批（同刻批，稳定 FIFO 序）；队列空 → None。"""

class QueueInvariantError(SchedulerError): ...        # 新增
```

### 3.5 `action_registry.py`（P3-T02）

```python
PARAMETER_TYPES: Final[frozenset[str]] = frozenset(   # 新增（Spec §11.2 YAML 示例的 type 词表）
    {"entity", "number", "string", "boolean"}
)

class ParameterSpec(ContractModel):                   # 新增
    type: str                        # PARAMETER_TYPES 词表
    required: bool = True
    enum_values: list[JsonValue] | None = None
    min_value: float | None = None       # 仅 type=="number" 生效
    max_value: float | None = None
    description: str | None = None

class DurationPolicy(ContractModel):                  # 新增
    kind: str                        # "fixed" | "hint" | "none"
    duration_ticks: int | None = None    # kind=="fixed" 必填且 >= 1
    hint_scale: float | None = Field(default=None, gt=0.0)   # kind=="hint"
    description: str | None = None

class ActionSpec(ContractModel):                      # 新增
    action_id: ActionTypeId
    executor: str                  # P5 producer/trigger 名字（与 ProducerId 同词法，ids.py:189-198；不持随机段）
                                   # ——P4/P5 执行层归属用途；P3 effect 侧 producer 口径不引用本字段（D-P3-11/F2-01）
    parameters: dict[str, ParameterSpec] = Field(default_factory=dict)
    duration_policy: DurationPolicy = Field(default_factory=lambda: DurationPolicy(kind="none"))
    interruptible: bool = True             # 默认与 ActiveAction.interruptible 一致（actions.py:238）
    completion_trigger: str | None = None  # 命名 P2 CascadeTrigger（cascade.py:473；complete 时刻求值出完成效果，
                                           # 如 arrival 位置 effect；D-P3-08"位置只在此刻经管道提交"）
    tags: list[str] = Field(default_factory=list)

class ActionRegistry(ContractModel):                # 新增
    specs: dict[ActionTypeId, ActionSpec] = Field(default_factory=dict)
    # model_validator: 键 == spec.action_id（P1 RuntimeState 键一致性同款纪律）

    def lookup(self, action_id: ActionTypeId) -> ActionSpec | None: ...
    def validate_arguments(self, action_id: ActionTypeId,
                           arguments: dict[str, JsonValue]) -> tuple[str, ...]: ...
        """未注册 action_id → 抛 UnknownActionError（D-P3-16）；
        参数问题返回 issue 串（缺必填 / 未知键 / 类型不符 / 越界 / enum 不在集合）。"""
    def resolve_duration(self, spec: ActionSpec, timing: ActionTiming) -> int | None: ...
        """fixed → duration_ticks；hint → round(hint_scale * timing.duration_hint_ticks)
        （hint 缺失 → None = 事件驱动完成）；none → None；结果 <1 → 钳制为 1 tick + 诊断（D-P3-01 子 tick 规则）。"""

def validate_timing(timing: ActionTiming) -> tuple[str, ...]: ...
    """deadline_tick >= earliest_start_tick；duration_hint_ticks >= 1；issue 串。"""

class UnknownActionError(SchedulerError): ...       # 新增
```

### 3.6 `action_lifecycle.py`（P3-T03 状态机 + P3-T04 progress/checkpoint/completion）

```python
class LifecycleEvent(str, Enum):                    # 新增（P3 语义层事件词表）
    VALIDATION_ACCEPTED = "validation_accepted"
    VALIDATION_REJECTED = "validation_rejected"
    SCHEDULED = "scheduled"          # VALIDATING → ACTIVE（预约开跑确认）
    CHECKPOINT = "checkpoint"
    INTERRUPTED = "interrupted"
    COMPLETED = "completed"
    FAILED = "failed"
    RESUMED = "resumed"              # INTERRUPTED → ACTIVE（D-P3-07，Plan Gate 授权）
    ABORTED = "aborted"

LIFECYCLE_TRANSITIONS: Final[dict[ActionLifecycleStatus,
    frozenset[tuple[LifecycleEvent, ActionLifecycleStatus]]]] = {   # 新增（迁移表，D-P3-07）
    ActionLifecycleStatus.PROPOSED:    {(VALIDATION_ACCEPTED, VALIDATING), (VALIDATION_REJECTED, FAILED)},
    ActionLifecycleStatus.VALIDATING:  {(SCHEDULED, ACTIVE), (VALIDATION_REJECTED, FAILED)},
    ActionLifecycleStatus.ACTIVE:      {(CHECKPOINT, ACTIVE), (INTERRUPTED, INTERRUPTED),
                                        (COMPLETED, COMPLETED), (FAILED, FAILED)},
    ActionLifecycleStatus.INTERRUPTED: {(RESUMED, ACTIVE), (ABORTED, FAILED)},
    ActionLifecycleStatus.COMPLETED:   frozenset(),     # 终态：表外 = IllegalTransitionError
    ActionLifecycleStatus.FAILED:      frozenset(),
}

class LifecycleTransition(ContractModel):           # 新增（迁移记录，trace 可用）
    instance_id: ActionInstanceId
    from_status: ActionLifecycleStatus
    to_status: ActionLifecycleStatus
    event: LifecycleEvent
    at_tick: int
    reason: str | None = None

def transition_action(runtime: RuntimeState, instance_id: ActionInstanceId,
                      event: LifecycleEvent, *, at_tick: int,
                      reason: str | None = None,
                      updates: dict[str, JsonValue] | None = None
                      ) -> tuple[RuntimeState, LifecycleTransition]: ...
    """唯一迁移入口（D-P3-07）：查表 → 表外/实例不存在/状态不符 → IllegalTransitionError
    （携带 from/to/event，不静默）；updates 合并进 ActiveAction 字段（rebuild 模式，
    与 P1 冻结字段逐字对齐）；自动置 last_transition_tick=at_tick（actions.py:243 审计字段）；
    **INTERRUPTED 与 RESUMED 迁移在 updates 中同步更新 progress 镜像字段**
    （`progress_of(action, at_tick)`，D-P3-08：纯派生、不累加、不可被 effect 篡改）——运行时
    权威值恒为派生，镜像供快照/restore/trace 观察（G3-1 断言 4：t=12 INTERRUPTED 迁移后
    `act_1.progress == 0.4` 即本镜像口径，§5.2 S7 / §6.2 G3-3"snapshot round-trip 后重算恒等"一致）；
    **INTERRUPTED 边将 base_world_revision re-anchor 至当前世界 revision**（经 updates 携带，
    依据 §5.2 S7、G3-1 断言 6；与 apply_checkpoint / resume_action 的 re-anchor 口径对齐，D-P3-08）；
    **INTERRUPTED 不剪除队列条目**（条目留在队列，与 §5.2 S8 断言 7 / §6.3 A1 口径一致）；
    **剪除仅发生于进入终态（COMPLETED/FAILED）**——此时剪除该实例剩余队列条目（确定性簿记，D-P3-25）。"""

def progress_of(action: ActiveAction, clock_tick: int) -> float | None: ...
    """D-P3-08：expected_end_tick 为 None → None（事件驱动）；否则 min(1.0, max(0.0,
    (clock_tick - start_tick) / (expected_end_tick - start_tick)))。纯派生、不累加——
    progress 不可被任何 effect 篡改（不得 2 的数学保证）。"""

def apply_checkpoint(runtime: RuntimeState, instance_id: ActionInstanceId, *,
                     at_tick: int, current_revision: Revision
                     ) -> tuple[RuntimeState, TraceRecord | None]: ...
    """CHECKPOINT 自迁移 + progress 重算 + base_world_revision re-anchor 至 current_revision
    + 入队下一 checkpoint（now + TimePolicy 间隔，若策略开启）。纯 RuntimeState 簿记：
    不提交世界事务、不推进 revision（P1 D-5）。返回 `(runtime, record)`：正常路径 record=None。
    **非 ACTIVE 守卫（F2-02，第二道防线）**：实例 status 非 ACTIVE（INTERRUPTED 或终态
    COMPLETED/FAILED）→ **不查迁移表、不调 transition_action、不入队下一 checkpoint**，
    返回（未变更 runtime, 一条诊断 `TraceRecord`）——由调用方（Scheduler）追加进本次调用
    `outcome.trace_records`（`TraceRecord` 开放信封，trace.py:113-139：kind 取 `TraceKind` 既有
    词表值 `SYSTEM`（trace.py:110），payload 开放 dict 携带诊断串：终态 →
    `checkpoint_skipped_terminal`；INTERRUPTED → `checkpoint_skipped_interrupted`（D-P3-25）），
    跳过该条目、时钟继续（玩家暂停场景由 D-P3-24 入口首检第一道拦截，§2.4）。"""

def start_action(world: WorldState, runtime: RuntimeState, proposal: ActionProposal,
                 spec: ActionSpec, *, at_tick: int, checkpoint_interval: int | None
                 ) -> tuple[WorldState, RuntimeState, tuple[LifecycleTransition, ...]]: ...
    """PROPOSED→VALIDATING→ACTIVE 两跳复合：按迁移表查两次，落 **2 条** LifecycleTransition
    记录（VALIDATION_ACCEPTED@at_tick + SCHEDULED@at_tick，顺序 = 迁移序，返回元组第 3 位；
    D-P3-19）；写 ActiveAction 记录
    （start_tick=at_tick、expected_end_tick=at_tick+duration（可空）、
    interruptible=spec.interruptible、base_world_revision=proposal.base_world_revision）
    + 入队 checkpoint/end/deadline 条目（§2.5 表）。开始时刻无世界 effect（位置不动，不得 2）。"""

def resume_action(world: WorldState, runtime: RuntimeState, instance_id: ActionInstanceId, *,
                  at_tick: int, current_revision: Revision) -> tuple[WorldState, RuntimeState, LifecycleTransition]: ...
    """INTERRUPTED→ACTIVE（RESUMED，D-P3-07）：start_tick/expected_end_tick **不变**
    （progress 连续，暂停不消耗逻辑时间——§2.3）；base_world_revision re-anchor 至
    current_revision；**中断不剪除队列条目**（D-P3-25）：resume 时下一 checkpoint 条目
    必然仍在队列（不重复入队，与 §5.3 A1 同口径）；若因缺陷缺失则补入队并输出诊断
    `checkpoint_requeued_after_defect`。"""

def abort_action(runtime: RuntimeState, instance_id: ActionInstanceId, *,
                 at_tick: int, reason: str = "aborted") -> RuntimeState: ...
    """INTERRUPTED→FAILED（ABORTED）：result_summary={"reason":…, "tick":…, "progress": progress_of(…)}；
    剪除剩余队列条目；无完成 effect。"""

def complete_action(world: WorldState, runtime: RuntimeState, instance_id: ActionInstanceId,
                    *, at_tick: int, completion_effects: Sequence[ProposedEffect]
                    ) -> tuple[WorldState, RuntimeState, LifecycleTransition]: ...
    """ACTIVE→COMPLETED：result_summary={"completed_at": at_tick, …}；completion_effects
    （由 spec.completion_trigger 求值所得，如位置 effect）由调用方（Scheduler）经 P2 管道
    提交——纯函数本身只出 effect、不写世界；无 completion_effects 时仍提交生命周期簿记，
    世界 revision 不变。"""

def fail_action(runtime: RuntimeState, instance_id: ActionInstanceId, *,
                at_tick: int, reason: str) -> RuntimeState: ...
    """ACTIVE→FAILED：result_summary={"reason": reason, "tick": at_tick}。
    （迁移表中 FAILED 目标边仅出自 ACTIVE——VALIDATING→FAILED 经 VALIDATION_REJECTED 边，
    属 submit_proposal REJECT 轨迹路径，不经本函数。）"""

class IllegalTransitionError(SchedulerError): ...   # 新增
```

### 3.7 `interrupt.py`（P3-T05）

```python
CONDITION_KINDS: Final[frozenset[str]] = frozenset(   # 新增（内置声明式 kind，D-P3-09/D-P3-17）
    {"event_type", "world_variable", "entity_component", "time"}
)
# 各 kind 的 parameters 契约（求值纯函数，view 为 guard() 深冻结视图）：
#   event_type:        {"event_type": str} —— 匹配 DomainEvent.event_type（真实字段，events.py:131-141
#                     无 kind 字段；事件类型恒等于 effect 类型，transaction_executor.py:146；
#                     结构 effect 词表全为 core.*，reducer.py:216-222）——本刻提交事件流中出现
#                     该 event_type 的事件即命中（D-P3-17）
#   world_variable:    {"key": str, "op": "gt|gte|lt|lte|eq", "value": JsonValue}
#   entity_component:  {"entity_id": EntityId, "component_type": str, "field_path": str, "op" 同上, "value": JsonValue}
#   time:              {"tick": int}（op 同上一律支持，缺省 gte；当前逻辑刻经 evaluate 的
#                     tick 入参显式传入，D-P3-21——view 与事件流均不携带当前刻）

class InterruptCondition(ContractModel):              # 新增（声明式，禁闭包）
    condition_id: str
    kind: str                      # CONDITION_KINDS 或已注册 resolver 名（下）
    parameters: dict[str, JsonValue] = Field(default_factory=dict)

class DecisionBoundary(ContractModel):                # 新增（Spec §23.2 decision boundary 概念（Spec L1305）；
                                            # P3 新增单列类型，定位为 §23.3 SHOULD 显式状态清单的扩展项——
                                            # 清单为 SHOULD 非穷举，扩展不构成违背）
    boundary_id: str
    actor_id: EntityId
    kind: str                      # "scheduled"（刻到即候选）| "condition"
    due_tick: int | None = None                # kind=="scheduled" 必填
    condition: InterruptCondition | None = None  # kind=="condition" 必填
    blocking: bool = False                 # True 且 actor ∈ player_actor_ids 才暂停（D-P3-10）
    interrupt: bool = True                 # 命中时是否中断该 actor 的 ACTIVE interruptible 行动
                                           #（非阻塞边界命中 → 迁 INTERRUPTED、不暂停；其后 checkpoint 刻守卫 no-op
                                           # 诊断 checkpoint_skipped_interrupted 与收敛路径见 D-P3-25）
    reason: str | None = None

class ConditionResolver(Protocol):                   # 新增（P5/P9 扩展位；命名注册）
    def evaluate(self, condition: InterruptCondition, view: GuardedWorldState,
                 events: Sequence[DomainEvent], *, tick: int) -> bool: ...
    # tick = 当前逻辑刻（D-P3-21）：time kind 的唯一来源；view 为世界态视图
    # （WorldState 无 logical_tick 字段，state.py:246-），事件 logical_tick 恒 None（D-P2-18）

class ConditionResolverRegistry:                     # 新增（普通类：持 callable，非状态）
    def register(self, kind: str, resolver: ConditionResolver) -> None: ...
    def resolve(self, kind: str) -> ConditionResolver | None: ...

BUILTIN_CONDITION_RESOLVERS: Final[ConditionResolverRegistry]   # 新增（4 内置 kind 纯实现）

class BoundaryReport(ContractModel):                 # 新增（刻后求值结果）
    tick: int
    fired: list[tuple[str, list[ActionInstanceId]]]  # (boundary_id, 被中断实例)
    player_blocking: bool = False                    # 是否触发调度暂停（D-P3-10）
    npc_notices: list[tuple[str, EntityId]] = []     # 非阻塞命中 → wakeup 建议

def evaluate_condition(condition: InterruptCondition, view: GuardedWorldState,
                       events: Sequence[DomainEvent], *, tick: int,
                       registry: ConditionResolverRegistry) -> bool: ...
    """内置 kind → BUILTIN；否则查 registry；两者皆无 → UnknownConditionError（可检查不静默，D-P3-16）。
    tick = 当前逻辑刻（evaluate_boundaries 已有入参，直接透传，D-P3-21）。"""

def evaluate_boundaries(view: GuardedWorldState, runtime: RuntimeState, *,
                        tick: int, events: Sequence[DomainEvent],
                        boundaries: Sequence[DecisionBoundary],
                        registry: ConditionResolverRegistry,
                        player_actor_ids: frozenset[EntityId]) -> BoundaryReport: ...
    """按注册序求值（确定性）；scheduled 边界仅 due_tick <= tick 时参评；blocking 判定 = boundary.blocking 且 actor ∈ player_actor_ids（D-P3-10）。"""

class UnknownConditionError(SchedulerError): ...     # 新增
```

### 3.8 `scheduler.py`（P3-T04/05/06 编排层）

```python
class TimePolicy(ContractModel):                     # 新增（D-P3-13，Spec §50 Spec B 的 P3 形态）
    fast_forward_enabled: bool = True
    checkpoint_interval_ticks: int | None = Field(default=None, ge=1)  # None → 无周期 checkpoint
    max_ticks_per_step: int | None = Field(default=None, ge=1)         # step() 单步跳变上限
    pause_on_player_boundary: bool = True   # True 缺省（现口径、Gate）：玩家 blocking 边界命中 → 中断被命中的可中断行动（INTERRUPTED）并返回 paused 待 resume/abort（D-P3-24）；False（R5/F4-03；R6/F5-03 重裁 record-only，E-P3-36）：玩家 blocking 边界命中仍 fired（BoundaryReport.fired + trace 留痕）但**不中断**可中断行动（行动生命周期照常推进：checkpoint/end 条目正常处理、行动正常 COMPLETED），且不返回暂停、继续推进至本次调用终点（max_tick/terminal）；D-P3-24 入口重报规则不生效（以本标志为前置）；NPC 边界中断/wakeup 不受本标志辖制（D-P3-10/D-P3-25 口径不变）。僵尸路径由构造消解：False 路径下行动永不被中断、其条目全部正常消费（原"仍中断"口径的推演缺陷见 E-P3-36）

class PauseReason(ContractModel):                    # 新增
    kind: str                      # "decision_boundary" | "bounded" | "terminal"
    boundary_id: str | None = None
    tick: int

class SchedulerOutcome(ContractModel):               # 新增（一次 fast_forward/step 的结构化结果）
    """按调用聚合（D-P3-18）：作用域 = 本次调用（从本次 fast_forward/step 开始至其返回，
    与 §5.3 A5 transactions=[txn_2] 口径一致），不累计历次调用；承载级联管道完整产出
    （CascadeResult 对应面，cascade.py:678-702）。调度器**不存储**事件（K1：事件不是
    世界状态组成部分——WorldState/RuntimeState 均无事件存储字段，state.py:246- / 217-227；
    trace.py 仅数据类型）——outcome 是调用观察值，不落 WorldState/RuntimeState。"""
    paused: bool
    pause_reason: PauseReason | None = None
    ticks_processed: int                    # 本次调用达到的 tick 水位（= 结果 RuntimeState.logical_tick）
    transactions: tuple[Transaction, ...] = ()    # 完整对象、含 ABORTED、commit 序
                                                  #（Transaction.effects 即回放所需 CommittedEffect 序列）
    events: tuple[DomainEvent, ...] = ()          # 本次调用全部发射事件（1:1 于已提交 effect，
                                                  # commit 序，D-P2-12；event.logical_tick 恒 None，D-P2-18）
    trace_records: tuple[TraceRecord, ...] = ()   # 本次调用全部决策/诊断记录（追加序）
    transitions: tuple[LifecycleTransition, ...] = ()
    # 本次调用产出的迁移记录（start_action 的 2 条复合记录在 submit_proposal 侧产出，
    # 不属于任何 fast_forward 调用的 outcome，D-P3-18/19）
    errors: tuple[str, ...] = ()

class WakeupHook(Protocol):                          # 新增（D-P3-14；Spec §50 BehaviorPolicy 的唤醒侧接缝）
    def on_wakeup(self, actor_id: EntityId, view: GuardedWorldState,
                  clock: LogicalClock, reason: str | None) -> Sequence[ActionProposal]: ...
    """同步纯函数：只读 guard 视图，返回新提案（不写世界、不直接调度）；确定性顺序由调用方（队列序）保证，hook 本体无内部时钟/随机。"""

class WakeupHookRegistry:                            # 新增（普通类；配置非状态）
    def register(self, hook: WakeupHook) -> None: ...
    def hook_for(self, actor_id: EntityId) -> WakeupHook | None: ...

def enqueue_actor_wakeup(runtime: RuntimeState, actor_id: EntityId,
                         due_tick: int, reason: str | None = None) -> RuntimeState: ...
    """写 actor_wakeups（稳定序：due_tick 单键）+ 同步入队 kind="wakeup" 条目
    （payload {"actor_id": …}）；两条记录 (actor_id, due_tick) 一致，reason 仅存 actor_wakeups
    记录、不入 payload（§2.5 尾注）。"""

def scheduler_fingerprint(registry: ActionRegistry, time_policy: TimePolicy,
                          boundaries: tuple[DecisionBoundary, ...]) -> str:   # 新增（D-P3-15：输入面 = registry + TimePolicy + boundaries 三项，R7-S4 补充2）
    """确定性指纹：各 Pydantic 模型按 model_fields 顺序做纯 dict 投影 →
    json.dumps(sort_keys=True, ensure_ascii=False, separators=(",", ":")) → sha256 hex
    （唯一、确定性，K7）——回放时校验 config 同构，不一致 → 回放拒绝（不静默）。
    排除面（已披露设计选择）：named_triggers/trigger_registry（callable/SyncTrigger
    闭包，非可序列化）不入指纹——Gate fixture 触发器为确定性纯函数，G3-4 判据在
    测试层机械可验证（R7-S4 补充2，E-P3-39③）。"""

class Scheduler:                                     # 新增（门面；**不是**真相——K7）
    def __init__(self, registry: ActionRegistry, *,
                 authority_policy: AuthorityPolicy,              # 必填（D-P3-23）：closed-by-default（D-P2-09）
                 time_policy: TimePolicy = TimePolicy(),
                 boundaries: Sequence[DecisionBoundary] = (),
                 condition_resolvers: ConditionResolverRegistry = BUILTIN_CONDITION_RESOLVERS,
                                                                         # 共享缺省实例为 Final：对共享缺省实例调用 register 属配置错误
                                                                         # （实现方须自建 registry 传入）；Gate fixture 全部显式构造，
                                                                         # 不受影响（R7-S2 风险1 防御注记，E-P3-39④）
                 wakeup_hooks: WakeupHookRegistry | None = None,    # 缺省 None → 空 WakeupHookRegistry；wakeup 条目命中时
                                                                    # 无 hook 可调 → 仅输出诊断（TraceRecord，SYSTEM），
                                                                    # 不崩溃、不影响簿记（R7-S4 风险1，E-P3-39⑤）
                 trigger_registry: CascadeTriggerRegistry | None = None,   # P2 cascade 触发器注册表（类型
                                                                       # CascadeTriggerRegistry，cascade.py:573；别名 TriggerRegistry，
                                                                       # cascade.py:650，两名字同一对象）
                                                                        # None 缺省 = 空注册表（cascade.py:852），R5/D-P3-27
                 named_triggers: frozenset[tuple[str, CascadeTrigger]],   # 必填（D-P3-26）：trigger_id→trigger
                                                                       # 点名求值映射的唯一数据来源（不可变、确定性；
                                                                       # 与 trigger_registry 注册同一批对象（fixture 向注册表
                                                                        # 注册触发器时惯例；Gate fixture 单路化：注册表为空、
                                                                        # stub 仅存于此参数，D-P3-27/§5.1）
                 component_registry: ComponentRegistry | None = None,
                 producer_registry: ProducerRegistry | None = None,
                 player_actor_ids: frozenset[EntityId] = frozenset(),
                 assert_barrier_armed: bool = True) -> None: ...
        """R1 落地（G2 移交 1，D-P3-11）+ 权威/执行器装配（D-P3-23）。
        **检查次序钉死（F2-06）**：`assert_barrier_armed=True` 时，`write_barrier_installed()`
        （reducer.py:1150）检查为 `__init__` **第一步**，**先于内部唯一 CascadeExecutor 构造**——
        未武装 → 抛 `SchedulerConfigurationError`（**不构造执行器**；因
        `CascadeExecutor.__init__` 自身调用 `install_write_barrier()`，cascade.py:810，幂等，
        "先构造执行器后检查"将使检查时刻屏障必已武装、该错误成死代码）。
        构造前检查 + 构造期幂等武装（cascade.py:810）**双重保证**：武装态贯穿 P3 套件全
        生命周期（conftest 预武装；回归测试断言套件内武装态不卸载，§6.1 scheduler 首条）。
        随后内部构造**唯一** CascadeExecutor（policy=authority_policy、triggers=trigger_registry、
        component_registry/producer_registry 透传）——全部世界写入经它（D-P3-11 ①；
        `policy` 为必填构造参数，cascade.py:800；AuthorityPolicy closed-by-default，
        authority.py：default_decision 缺省 DENY、空 rules = 完全封闭，D-P2-09）——
        装配方必须显式授予实际产 effect 的 producer 写域（Gate fixture 见 §5.1）。
        **触发器名称解析（F2-13；R4 修正 D-P3-26）**：scheduler 自持 `trigger_id→trigger`
        映射（**由必填构造参数 `named_triggers` 建立**（D-P3-26：不可变、确定性、零私有访问；
        不新增运行时状态））——因 `CascadeTriggerRegistry` 公开 API 仅 `register`/
        `evaluate_all`/`trigger_ids`（cascade.py:589-644，`_triggers` 私有），无按名单个查询，
        不得以私有字段访问补位（K7）；装配方（fixture）将注册进 `trigger_registry` 的
        **同一批**触发器对象经 `named_triggers` 显式传入（§5.1）。`kind="event"` 的
        `trigger_id` payload 与 `completion_trigger` 到点时由 scheduler 经该映射点名求值；
        **`trigger_registry` 参数语义（R5/D-P3-27）**：`None`（缺省）与显式传空注册表等价
        （cascade.py:852：`triggers=None` 缺省即空 `CascadeTriggerRegistry()`）——点名求值不受
        影响，级联回合再求值面为空（`evaluate_all` 返回空、无 `trigger_output_dropped`）；
        Gate fixture 显式传空注册表单路（§5.1，D-P3-27）；注册表非空时级联再求值
        （cascade.py:969-981）命中注册触发器，stub 幂等守卫与 `cause_ids` 口径见 §5.1 通用
        契约（抑制"effect 已生效后重发"；产出须回指本回合事件，否则空 `cause_ids` 被
        确定性丢弃，`trigger_output_dropped` 诊断，不静默，E-P3-24/E-P3-30）。
        武装态下的状态副本口径 = deep_copy_via_roundtrip（serialization.py:135，不经写屏障
        四逃逸路径；write_barrier_exempt()（reducer.py:1065）仅受控例外备路，§5.5-M3a）。"""

    def fast_forward(self, world: WorldState, runtime: RuntimeState, *,
                     max_tick: int | None = None
                     ) -> tuple[WorldState, RuntimeState, SchedulerOutcome]: ...
        """§2.4 主循环（入口首检＝未响应暂停幂等重报，D-P3-24，重报保证**限定于该行动仍处 INTERRUPTED（玩家未响应）期间**、无 INTERRUPTED 背书的边缘暂停仅返回一次且重入正常推进（D-P3-24⑥，R5/F4-02）；含循环前 scheduled 边界播种，
        幂等去重，D-P3-22）；**重报规则以 `TimePolicy.pause_on_player_boundary=True` 为前置，False 时玩家边界命中仍 fired（fired 记录 + trace）但不中断可中断行动、不返回 paused、重报规则不生效（R5/F4-03；R6/F5-03 重裁 record-only，E-P3-36，见字段位口径）**；全部世界写入统一经 CascadeExecutor（G2 移交 1）；
        **producer 归属（统一口径，F2-01/D-P3-11）：凡触发器（含 completion_trigger）求值
        产生的 effect → producer = 该触发器注册时声明的 producer（Gate fixture 两触发器注册为
        origin_scenario，§5.1；『注册时声明』的载体 = stub `evaluate` 写入 `ProposedEffect.source`，
        详见 §5.1 触发器 bullet）；kind="event" 显式 effects 批形态 → payload 声明的 producer**
        （producer 身份与 authority_policy 放行面对齐，D-P3-23）；scheduler 自身（"scheduler"）
        不产世界 effect（迁移至 COMPLETED 是簿记、非世界 effect、不经 authority，§5.3 A4）。
        **提交参数钉死（F2-15）**：每次 `CascadeExecutor.run` 提交，`causal_root_id` = 驱动
        该批的队列条目 `entry_id` 字符串（本刻批首条 entry），`origin` = 所产 effect 的
        producer 之 `Provenance`（确定性值，不自由裁量；run 守卫 cascade.py:906-914）；
        **P2 冻结 docstring 偏离披露（R7-S4 补充1，E-P3-38）**：`cascade.py:882-884`
        docstring 对 P3 用法的示例性表述（『以 action 实例为根』）被本段 `entry_id`
        口径取代（entry_id 覆盖全部条目 kind——kind=event 无 action 实例可指）；
        该 docstring 属 P2 冻结面不可修改，run 守卫仅要求非空 str + origin 为
        Provenance → `sch_` entry_id 合规，因果链仍经 cause_ids/trace 确定性闭合，
        无任何 Gate 断言依赖 `causal_root_id` 的值；
        **run()-级 origin 的 OriginKind 钉死（R6/F5-01）**：Gate fixture 的 run()-级 origin
        一律构造为 `Provenance(producer_id=origin_scenario, origin=OriginKind.SCENARIO)`
        （provenance.py:41-53，SCENARIO ∈ 冻结词表；`Provenance` 的 `producer_id`/`origin`
        双必填无默认——缺 origin 即 ValidationError，探针核验），通用口径 = fixture 声明
        producer 时一并声明其 `OriginKind`（缺省 SCENARIO），随 named_triggers/fixture 装配
        显式传入，不自由裁量；事件级 `DomainEvent.provenance` 仍由 P2 承载
        （transaction_executor.py:156-157，origin 经 `producer_registry.origin_of` 解析、缺省
        SYSTEM，transaction_executor.py:139-143——事务级/事件级两个 origin 面区分），本条
        只钉 scheduler 的 run() 参数。
        返回 outcome 为按调用聚合（D-P3-18）；**原子刻错误路径（F2-03）**：单刻处理中任何
        P3 错误 → 返回刻前状态对 + `SchedulerOutcome(paused=False, pause_reason=None,
        ticks_processed=<刻前 logical_tick>, transactions=(), events=(), trace_records=(),
        transitions=(), errors=<非空诊断串>)`（不崩溃、部分提交不可见，§2.4 确定性论证 5；
        §6.1 刻原子性用例可执行口径）。"""

    def step(self, world: WorldState, runtime: RuntimeState
             ) -> tuple[WorldState, RuntimeState, SchedulerOutcome]: ...
        """开发单步（RuntimeLifecycle.STEPPING 语义，state.py:115-127）：推进至下一边界（单批 + 刻后求值）后强制暂停。
        **强制暂停 outcome 形态钉死**：`paused=True`、`pause_reason = PauseReason(kind="bounded",
        tick = 本步到达刻)`（`PauseReason` 词表："decision_boundary" | "bounded" | "terminal"）、
        `ticks_processed = 本步到达刻`。"""

    def submit_proposal(self, world: WorldState, runtime: RuntimeState,
                        proposal: ActionProposal
                        ) -> tuple[WorldState, RuntimeState, RevalidationDecision]: ...
        """外部提案入口（玩家/devtools/P4）：revalidation（§3.9）→ ACCEPT 则入 pending_proposals
        并按 timing 调度（earliest_start_tick 未到 → kind="action_start" 预约）；REJECT 则记录 FAILED 生命周期轨迹 + 诊断。
        **内部次序钉死（R7-S4 风险4）**：1) registry 查找（未注册 action_id →
        `UnknownActionError` → FAILED 轨迹，reason="unknown_action"，D-P3-16/A5 口径，
        该错误路径不创建 PROPOSED ActiveAction 记录）；2) revalidate_proposal（§3.9）；
        3) ACCEPT → 创建 PROPOSED ActiveAction 记录 + start_action 复合 2 条迁移
        （D-P3-19；start_action 成功时移出 pending_proposals，F2-12）——确保 A5 错误
        路径不产生悬空 PROPOSED 记录。
        **pending_proposals 簿记口径（F2-12）**：ACCEPT 提案于 `start_action` 成功时移出
        `RuntimeState.pending_proposals`；REJECT/FAILED 轨迹留痕（留痕 = 仍在列表 + `RevalidationDecision`
        的 REJECT 记录——`ActionProposal` 无 status 字段（actions.py:145-188），留痕不依赖状态字段）。
        **start 迁移记录观察出口（范围声明，F2-16）**：`start_action` 的 2 条 LifecycleTransition
        （VALIDATION_ACCEPTED + SCHEDULED，D-P3-19）在模块级直调返回中可观察（`start_action`
        返回元组第 3 位，§6.1 测试口径）；本门面签名 `(WorldState, RuntimeState,
        RevalidationDecision)` 不携带（17 条 Gate 断言亦不引用）；若后续 G3/trace 判据需门面级
        观察，可经 trace_records/诊断补出口——P3 不加。"""

    def resume_action(self, world, runtime, instance_id) -> tuple[WorldState, RuntimeState, LifecycleTransition]: ...   # 玩家恢复（Gate 分支 A；返回类型与模块级签名对齐，§3.6，R7-S4 风险2）
    def abort_action(self, world, runtime, instance_id) -> RuntimeState: ...    # 玩家中止（Gate 分支 B；返回类型与模块级签名对齐，§3.6，R7-S4 风险2）

class SchedulerConfigurationError(SchedulerError): ...  # 新增（含 R1 未武装断言失败）
class SchedulerWakeupError(SchedulerError): ...         # 新增（hook 抛错：actor_id + 原因）
```

### 3.9 `revalidation.py`（P3-T07）

```python
class RevalidationDecision(ContractModel):            # 新增（判定结果 = 数据，不是异常）
    proposal_id: ActionInstanceId
    outcome: RevalidationOutcome          # 复用 P1 四值词表（revision.py:91-101）
    reason: str                   # "accept" | "stale_revision" | "valid_until_expired" | "actor_missing" | "actor_not_alive" | "rebased" | …
    details: tuple[str, ...] = ()
    at_revision: Revision
    rebased_proposal: ActionProposal | None = None   # outcome==REBASE 时非空

def revalidate_proposal(state: WorldState, proposal: ActionProposal, *,
                        current: Revision | None = None,          # 缺省 state.world_revision
                        allow_rebase: bool = False,
                        actor_alive_check: Callable[[GuardedWorldState, EntityId], bool]
                            | None = None) -> RevalidationDecision: ...
    """通用 stale 提案 revalidation（**任意 producer 单一实现**，G2 移交 3）：
    1. is_stale(proposal.base_world_revision, current, proposal.valid_until)
       （复用 revision.py:78 口径）→ True：allow_rebase 且 actor 存活 → REBASE
       （rebased_proposal = rebase_proposal(…)）；否则 REJECT——**REJECT 原因优先级钉死（F2-05，
       过期优先）**：若 `valid_until` 非 None 且 `current > valid_until` → `valid_until_expired`；
       否则 → `stale_revision`（两条件同时满足时不随实现顺序漂移，§6.3 A1 变体口径）；
    2. actor 存在性：state.has_entity(proposal.actor_id) 否 → REJECT actor_missing；
    3. actor_alive_check（P5/P4 钩子，如昏迷判定；缺省恒真）→ 假 → REJECT actor_not_alive；
    4. actor_state_revision 非空且 is_stale → 仅 details 诊断（D-12 口径：记录"读取时"revision，
       不作 REJECT 依据）；observation_id 仅词法在 P1 构造期已校验，P3 记录 details
       （内容级一致性检查属 P4 观察管线，扩展位）；
    5. 全过 → ACCEPT。
    **REPAIR 范围声明（R4/E-P3-26）**：`RevalidationOutcome.REPAIR`（revision.py:91-101
    四值冻结词表之一）**不产生于 P3 同步 tick 循环 revalidation**——REPAIR 属 Spec §9 异步
    结果 revalidation 语境（P4 携带 base_world_revision/observation_id/actor_state_revision/
    valid_until 的异步结果路径）；**P3 `revalidate_proposal` 结果域 = {ACCEPT, REBASE,
    REJECT}**，P4 异步路径保留 REPAIR 产出能力（词表已冻结，P3 不扩展不缩减）。"""

def rebase_proposal(proposal: ActionProposal, current: Revision) -> ActionProposal: ...
    """REBASE 纯变换：base_world_revision → current（rebuild 模式；其余字段逐字保持）。调用方（submit_proposal）决定何时允许 REBASE（默认关闭）。"""
```

### 3.10 任务包映射、波次与写入白名单

```text
波次 A（并行）: T01 clock.py + event_queue.py（QMax） ∥ T02 action_registry.py（Q27）
波次 B:        T03 action_lifecycle.py-状态机（Q27，T02 之后，同文件串行）
波次 C:        T04 action_lifecycle.py-progress/checkpoint/completion（QMax，T03 同文件串行）
              + scheduler.py 核心循环 fast_forward/submit（QMax，T01 之后）
波次 D:        T05 interrupt.py + scheduler.py 中断/边界接线（QMax，T04 同文件串行）
波次 E（并行）: T06 scheduler.py-wakeup hook（Q27，T05 同文件串行） ∥ T07 revalidation.py（QMax，T04 之后，独立文件）
波次 F:        T08 测试套件（GFlash，依赖全部）
```

同文件单 Owner 纪律（Plan §7.2）：`action_lifecycle.py`（T03→T04）与 `scheduler.py`（T04→T05→T06）严格串行；`tests/engine_v2/core/conftest.py` 由 T08 首次创建（P2 测试在 `core/` 下无共享 conftest，P2 勘误 E4 布局沿袭）。

| 任务 | 交付 | 写入白名单 |
|---|---|---|
| **P3-T01** | `clock.py` + `event_queue.py`（§3.3/§3.4 全量） | `src/engine_v2/core/clock.py`（新增）、`src/engine_v2/core/event_queue.py`（新增）、`core/__init__.py`（两块导出）、`tests/engine_v2/core/test_clock.py`、`tests/engine_v2/core/test_event_queue.py`（新增）、`tests/engine_v2/core/test_closeout.py`（仅 `_CORE_SUBMODULE_NAMES` 19→26 + L184 规模锚点 `assert len(core_pkg.__all__) == 196` → 249（含注释块 L164-183））、`tests/engine_v2/core/test_import_boundary.py`（仅 `CORE_SUBMODULES` 19→26；D-P3-12 三锚点机械修订） |
| **P3-T02** | `action_registry.py`（§3.5 全量） | `src/engine_v2/core/action_registry.py`（新增）、`core/__init__.py`（导出块）、`tests/engine_v2/core/test_action_registry.py`（新增） |
| **P3-T03** | `action_lifecycle.py` 迁移表层（§3.6 上半：枚举/迁移表/transition_action/IllegalTransitionError） | `src/engine_v2/core/action_lifecycle.py`（新增）、`core/__init__.py`（导出块）、`tests/engine_v2/core/test_action_lifecycle.py`（新增） |
| **P3-T04** | `action_lifecycle.py` progress/checkpoint/completion（§3.6 下半）+ `scheduler.py` 核心（§3.8：TimePolicy/SchedulerOutcome/fast_forward/step/submit_proposal/Scheduler 骨架） | `src/engine_v2/core/action_lifecycle.py`（追加）、`src/engine_v2/core/scheduler.py`（新增）、`core/__init__.py`（导出块）、`tests/engine_v2/core/test_action_lifecycle.py`（追加）、`tests/engine_v2/core/test_scheduler.py`（新增） |
| **P3-T05** | `interrupt.py`（§3.7 全量）+ `scheduler.py` 刻后求值接线 | `src/engine_v2/core/interrupt.py`（新增）、`src/engine_v2/core/scheduler.py`（追加）、`core/__init__.py`（导出块）、`tests/engine_v2/core/test_interrupt.py`（新增）、`tests/engine_v2/core/test_scheduler.py`（追加） |
| **P3-T06** | `scheduler.py` wakeup 协议与接线（§3.8：WakeupHook/Registry/enqueue_actor_wakeup） | `src/engine_v2/core/scheduler.py`（追加）、`core/__init__.py`（导出块）、`tests/engine_v2/core/test_scheduler.py`（追加） |
| **P3-T07** | `revalidation.py`（§3.9 全量） | `src/engine_v2/core/revalidation.py`（新增）、`core/__init__.py`（导出块）、`tests/engine_v2/core/test_revalidation.py`（新增） |
| **P3-T08** | G3 端到端 + 对抗测试（§6 全量） | `tests/engine_v2/core/conftest.py`（新增）、`tests/engine_v2/core/test_p3_gate_scenario.py`（新增）、`tests/engine_v2/core/test_p3_adversarial.py`（新增）、`tests/engine_v2/core/test_import_boundary.py`（新增 `P3_SUBMODULES` 元组 + P3 专项谓词 + `P3_TEST_FILES` 元组（10 个新增测试文件列举，G3-5 机械口径）；§6.4/§8.5-D4 预披露结构性修订） |

> **实现期核验注记（P3-T01 白名单，R4/L3-07）**：实现完成后须以 diff/哈希核验——`core/__init__.py` 相对基线纯增量（既有 196 条目顺序/内容零改动）、13 个 P1 契约模块 `.py` 与 `603535e` 逐字节一致、53 新导出名与既有 196 名及 26 子模块名零撞名（closeout 规模锚点 249 为机械兜底）。

### 3.11 `core/__init__.py` 与 closeout 机制同步（D-P3-12）

- P3-T01 同步修订既有测试文件中的**三锚点**（D-P3-12 锚点清单，全量）：**①② 两个相互独立的 19 模块清单**扩为 26 项（追加 `action_lifecycle`、`action_registry`、`clock`、`event_queue`、`interrupt`、`revalidation`、`scheduler`）——`tests/engine_v2/core/test_closeout.py::_CORE_SUBMODULE_NAMES`（L92）与 `tests/engine_v2/core/test_import_boundary.py::CORE_SUBMODULES`（文件自带元组）；**③ 规模锚点**：`test_closeout.py` L184（含注释块 L164-183）`assert len(core_pkg.__all__) == 196` → **249**（`__all__` 纯增量 196→249 的一行级机械同步，性质与 ①② 同类，§8.5-D5）。
- 包 `__all__` 196 → **249**（新增 53 符号：clock 6 / event_queue 5 / action_registry 7 / action_lifecycle 12 / interrupt 10 / revalidation 3 / scheduler 10；逐模块清单见 §3.3–§3.9 代码块）。各任务包按 §3.10 顺序在 `__init__.py` 追加 re-export 块与 `__all__` 条目（字母序插入，P1/P2 同款纪律）。
- 新导出名不得与 26 个子模块名相撞（豁免集恒为 `{snapshot}`，撞名即测试失败）；已核 53 符号与子模块名无撞名。
- 此机械修订为**已知披露偏差模式**（P2 D-P2-19 先例：既有测试文件的一行级元组修订，列入任务包白名单，Gate 报告偏差登记披露），非 P1 源改动。

---

## 4. 设计决策（D-P3-01 ~ D-P3-27）

> 体例（P2 同款）：问题 / 备选 / 选择 / 理由 / 一致性；全部 27 项决策（D-P3-01~D-P3-27）在此给出全文，编号与 P1（D-0~D-15）、P2（D-P2-01~D-P2-20）命名空间隔离。其中 **D-P3-17~D-P3-23 为 R2 盲审驱动的闭合决策**、**D-P3-24~D-P3-25 为 R3 盲审驱动的规则补全决策**、**D-P3-26 为 R4 盲审驱动的修正决策**、**D-P3-27 为 R5 盲审驱动的规格补全决策**（Gate fixture 单路化，F4-01；均 §9 勘误逐条留痕）。

### D-P3-01 时间单位（1 tick ≙ 1 分钟）

- **问题**：Gate 场景用"分钟"，冻结契约字段全是 int tick；tick↔分钟换算未定。
- **备选**：A：1 tick = 1 分钟；B：1 分钟 = 60 ticks。
- **选择**：A（默认映射）；core 单位无关，换算常数归 P5（`TICKS_PER_GAME_MINUTE`，默认 1）。
- **理由**：§2.2 四条（Gate 字面对齐 `progress == 12/30`；事件驱动无逐秒消费方；子 tick 有显式钳制规则；常数是内容决定不锁死未来）。
- **一致性**：P1 全部 tick 字段零改动；Spec §23.1 第 3 层（world logical time）由 tick 唯一承载；Plan Gate 数字 30/12 直接入测试。

### D-P3-02 时钟载体（不新增状态，值类型）

- **问题**：`LogicalClock` 放哪——新状态字段？独立模块持有？
- **备选**：A：`RuntimeState` 新增 clock 对象字段（改 P1，禁止）；B：独立 ClockState 平行持有（双源风险，违反 K1 单一权威同源纪律）；C：冻结 `logical_tick` 为唯一权威 + `LogicalClock` 值类型（Revision 模式）。
- **选择**：C。
- **理由**：P1 D-6 已定"单一单调计数"；Revision 值类型先例（`revision.py:43-51`）证明"无状态值类型 + 重建写回"在 frozen 契约下可行；值类型使 round-trip/相等断言免费。
- **一致性**：`state.py:218` 零改动；G3-2（队列/时钟可序列化）直接复用 P1 序列化；P2 D-P2-18 的"tick 推进归 P3"由 `set_logical_tick` 唯一写点兑现。

### D-P3-03 fast-forward 推进算法

- **问题**：时间如何前进——逐 tick 迭代？跳变？边界事件驱动？
- **备选**：A：逐 tick 循环（v1 `tick_speed_resolve` 形态，O(时长) 且天然全量结算）；B：跳变至下一 due tick + 同刻批 + 刻后求值（事件驱动，Spec §23.2 "长行动不是重复 tick"）。
- **选择**：B（§2.4 伪代码 + 五要素确定性论证）。
- **理由**：Spec §23.2 原文；"不得 2"要求长行动无逐 tick 伪装工作；B 的复杂度与事件数成正比、与时间跨度无关；确定性五要素支撑 G3-4 回放判据。
- **一致性**：Plan §12 目标（替代 tick_speed_resolve）；G2 移交 2（每刻重新 guard）落在刻后求值点。

### D-P3-04 ScheduledEvent 复用与 kind 词表

- **问题**：队列条目类型——新建 P3 类型还是复用 P1 占位？（任务书原文预期"新类型"。）
- **备选**：A：新建 `P3ScheduledEvent`（与 P1 `ScheduledEvent` 并存 → 双源，且 `RuntimeState.scheduler_queue: list[ScheduledEvent]` 是冻结字段类型，新类型放不进去）；B：复用 P1 `ScheduledEvent` + P3 定 `kind` 词表与 payload 契约。
- **选择**：B。**（对任务书的澄清性偏差，§8.5-D1）**
- **理由**：P1 零改动是最高约束（G2 移交 4）；`state.py:143` docstring 原文"P3 定词表"——P1 已把词表决定权显式让渡给 P3；`kind: str` + `payload: dict` 的开放度恰好容纳 7 种 kind 而无需改 schema。
- **一致性**：`ids.py:171-177`（`sch_`）、`state.py:143-155` 零改动；G3-2 序列化判据直接落在冻结类型上。

### D-P3-05 同刻序与队列不变量

- **问题**：同一 due_tick 多条目处理顺序；排序时机。
- **备选**：A：消费时排序（队列平时乱序，K7 可检查性弱化）；B：写时稳定排序 + 同刻稳定 FIFO（插入序）。
- **选择**：B；另加两条不变量：禁过去调度（`due_tick < clock` → `QueueInvariantError`）、`entry_id` 唯一。
- **理由**：稳定排序（`list.sort`，key 仅 `due_tick`）是纯函数；同刻 FIFO 使"先入队先处理"成为可断言的确定性（对抗 A3）；过去调度在事件驱动模型中无合法语义（时间只向前）。
- **一致性**：K7（队列任意时刻可检）；G3-4（顺序一致判据的序来源）；P1 列表字段语义零改动。

### D-P3-06 ActionRegistry 与参数 schema（core 只做结构 + 校验点）

- **问题**：YAML 注册表（Spec §11.2 示例）在 core 加载吗？
- **备选**：A：core 引 yaml 依赖加载（破坏 import 边界白名单 stdlib+pydantic）；B：core 只落 `ActionSpec` 结构 + 纯校验函数，P5 加载 YAML 后 `model_validate` 构造。
- **选择**：B。
- **理由**：P2 D-P2-08 先例（`AuthorityPolicy` 同款：pydantic 入口，YAML 归 P5）；core import 边界是 G2 静态核查项，引 yaml 即破坏 `test_import_boundary` 口径。
- **一致性**：Spec §11.2 的 `executor`/`parameters`/`duration_policy`/`tags` 字段逐项映射到 `ActionSpec`（新增 `completion_trigger`，D-P3-08 需要）；参数 `type: entity` 词表落 `PARAMETER_TYPES`。

### D-P3-07 生命周期状态机（六态 + 9 事件 + RESUMED 边）

- **问题**：迁移表怎么定？Spec §11.4 图示无 `INTERRUPTED → ACTIVE` 返回边，但 Plan Gate 要求"action may resume / abort"。
- **备选**：A：严格照 Spec 图示（resume 不可表达 → Gate 场景分支 A 无法实现）；B：六态枚举（P1 冻结）+ 9 事件迁移表，**新增 RESUMED 边**，表外一律 `IllegalTransitionError`。
- **选择**：B。**（Spec"建议"图示 vs Plan Gate 的裁定，§8.5-D2）**
- **理由**：Spec §11.4 原文是"**建议**标准状态机"（非 MUST）；Plan §12 Gate 是 G3 判据来源（"场景精确通过"），resume 是场景明文要求；P1 冻结枚举本就含 INTERRUPTED 态（`actions.py:202`），返回边只是语义层决定，不动任何冻结物。终态（COMPLETED/FAILED）无出边——"场景精确通过"要求迁移不可逆可断言。
- **一致性**：P1 枚举零改动；对抗 A2（迁移矩阵全表测试）；`last_transition_tick` 审计字段逐迁移更新（`actions.py:243`）。

### D-P3-08 progress / checkpoint / completion 语义

- **问题**：progress 存还是算？checkpoint 做什么？完成效果谁提交？
- **备选**：A：progress 累加存储（每次 +1 tick 写回——可被篡改、恢复误差累积）；B：progress 由时钟**纯推导**（`(clock - start_tick)/(expected_end_tick - start_tick)`，存储字段仅作快照镜像）；checkpoint = 队列条目 + re-anchor；完成 effect 由 `ActionSpec.completion_trigger` 命名触发器在 COMPLETED 刻求值、经 P2 管道提交。
- **选择**：B。
- **理由**：时钟单调 → 推导恒等式不可伪造（"不得 2"的数学保证：位置/进度只能在完成刻经事务移动，中途 world 里没有位置 effect 可提交）；re-anchor 使长行动的 `base_world_revision` 随世界前进（stale 判定不失真，与 P3-T07 口径衔接）；checkpoint 本身不提交事务（P1 D-5：RuntimeState 簿记不推进 revision），避免每 checkpoint 一次无谓 revision。
- **一致性**：`ActiveAction.progress` 字段语义（`actions.py:237`，0..1 约束由推导式 clamp 保证）；`next_checkpoint_tick`/`last_transition_tick` 逐字复用；Spec §23.4 示例字段全对齐。

### D-P3-09 InterruptCondition / DecisionBoundary 可声明可检查

- **问题**：中断条件与边界用闭包还是数据？
- **备选**：A：`Callable[[state], bool]`（表达力强，但不可序列化、不可回放、K7 直接违反）；B：声明式数据模型（4 内置 kind 纯求值）+ **命名** resolver 注册表扩展位（callable 只存在注册表=配置侧，数据模型只持 kind 名字）。
- **选择**：B。
- **理由**："不得 3"与 K7 要求调度事实可序列化——条件进快照才能回放；命名 resolver 保留 P5/P9 扩展空间且保持"数据面可检查"（trace 记录 kind + parameters，debugger 可解释）；4 内置 kind 覆盖 Spec 场景 D/G 所需（`event_type` 匹配 `DomainEvent.event_type`，支撑 encounter 中断——R2 重定义，D-P3-17）。
- **一致性**：Spec §23.3（InterruptCondition 单列）；G3-4（回放时条件从快照恢复、求值纯函数）。

### D-P3-10 边界阻塞规则（玩家/NPC 差异）

- **问题**：什么边界停调度？NPC 短动作会不会停玩家？
- **备选**：A：任何 blocking 边界都停（NPC 1 秒动作 → 玩家每秒被拉回，"不得 1"直接违反）；B：blocking 暂停只认 `player_actor_ids`（Spec §7.3 会话持有者；MVP 单一玩家会话）；NPC 边界一律非阻塞 → `BoundaryReport.npc_notices` + 入队 `ActorWakeup`。
- **选择**：B。
- **理由**："不得 1"的正面实现；Spec §7.4（MVP one active player session）给出 `player_actor_ids` 的 MVP 取值；NPC 决策权保留（wakeup 照常发生），只是不占用玩家时间轴。
- **一致性**：`actor_wakeups` 字段（`state.py:222`）获得 P3 侧执行者；对抗 M1 可执行化（§5.5）。

### D-P3-11 与 P2 kernel 集成（producer 语义 / R1 / 每轮 guard）

- **问题**：scheduler 如何改世界？写屏障武装点在哪补？guard 何时刷新？
- **备选**：A：scheduler 直调 `commit_transaction`（绕过 cascade 武装点，R1 敞开）；B：统一经 `CascadeExecutor`（武装点 `cascade.py:810`），装配期再加恒武装断言。
- **选择**：B，三落点：① **提交路径**——fast-forward 内全部世界写入 = `ProposedEffect → Authority → Validation → Conflict → Transaction → Reducer`（G2 移交 3 原管道）；事件/触发/完成效果一律以 effect 进入，scheduler 不直接触碰 WorldState（K2）。② **R1 落地**——`Scheduler.__init__(assert_barrier_armed=True)` → `write_barrier_installed()` 假即 `SchedulerConfigurationError`（G2 §6 R1 "P3：装配期恒武装断言 + 回归测试"原文落位）+ 回归测试（断言进程内武装态贯穿 P3 测试全生命周期；武装态下的状态深拷贝口径 = `deep_copy_via_roundtrip`（serialization.py:135，走序列化 round-trip、不经写屏障四逃逸路径；`write_barrier_exempt()`（reducer.py:1065）仅受控测试例外备路，§5.5-M3a））。③ **每轮重新 guard**——刻后求值与 hook 调用一律使用**当刻** `guard(world)` 新视图（guard 语义 = guard() 时刻深冻结快照，跨 commit 不反映新状态——G2 移交 2 原文）；禁止跨刻复用 guard token。
- **producer 归属**（K6 溯源，统一口径 F2-01）：**凡触发器（含 `completion_trigger`）求值产生的 effect → `Provenance(producer_id=该触发器注册时声明的 producer)`**（Gate fixture 两触发器注册为 `origin_scenario`，§5.1；游戏系统问责）；`kind="event"` 显式 effects 批形态 → payload 声明的 `producer` 键；`"scheduler"` 作为已注册 producer **不产世界 effect**（纯簿记，authority 配置无需授予世界写域）。迁移至 COMPLETED 是 scheduler 簿记（**非世界 effect，不经 authority**，§5.3 A4）。producer 身份必须与 `AuthorityPolicy` 放行面对齐（closed-by-default，D-P2-09）：放行面显式构造见 §5.1（D-P3-23）；不对齐 = authority 阶段 DENY（可检查，不静默）。`ActionSpec.executor` 字段保留供 P4/P5 执行层归属使用（§3.5），P3 effect 侧 producer 口径不引用该字段。
- **一致性**：G2 移交 1/2/3 逐条闭合；经 CascadeExecutor 提交的事务/事件 `logical_tick` 恒 None（D-P2-18：`run()` 无 tick 参数，`cascade.py:867-874`，内部 commit 未传，`cascade.py:1171-1180`）——逻辑时刻归属由权威时钟 + `due_tick`/`at_tick` + outcome tick 水位承载（D-P3-20）；权威装配面 = `authority_policy` 必填构造参数（D-P3-23）。

### D-P3-12 模块切分（7 模块）与命名

- **问题**：P3 行为代码放哪几个文件？
- **备选**：A：单一大文件 `scheduler.py`（6 类职责混杂，任务包并行不可行）；B：按依赖层切 7 模块（时间原语 / 队列 / 注册表 / 生命周期 / 中断边界 / revalidation / 编排）。
- **选择**：B（§3.1 命名论证 + §3.2 无环依赖图）。
- **理由**：P2 六模块"按行为域分文件"先例；7 模块使 T01/T02/T07 三波次真正并行；错误基类置于依赖叶 `clock.py` 避免环（P2 错误族随宿主模块的同款纪律）。
- **一致性**：子模块 19→26、`__all__` 196→249 纯增量；closeout 三锚点机械同步（§3.11，披露模式）。

### D-P3-13 TimePolicy 的 P3 落地形态

- **问题**：Spec §50 Spec B 列了 `TimePolicy` 协议；P3 需要多少？
- **备选**：A：完整策略协议（含 mode 联动、叙事压缩曲线——P4/P9 语义）；B：最小契约模型 4 字段（fast_forward 开关 / checkpoint 间隔 / step 上限 / 边界暂停）+ 六层时间映射表文档化。
- **选择**：B（`TimePolicy` 为 ContractModel 而非 Protocol：值可序列化 → 进 `scheduler_fingerprint`，回放同构可检）。
- **理由**：P3 消费面就这 4 个决定；mode 联动归 P4（§1.3 非目标 5）；tick↔分钟换算常数不在此（P5 内容层，D-P3-01）。
- **一致性**：Spec §50 清单的 P3 子集；`RuntimeLifecycle.STEPPING`（`state.py:126`）由 `Scheduler.step()` 承载。

### D-P3-14 Actor wakeup hook / callback 协议

- **问题**：NPC 决策接缝的形态与失败处置？
- **备选**：A：hook 可直接返回效果/写状态（耦合 + K2 风险）；B：`WakeupHook` Protocol——同步纯函数，入参 `guard` 视图 + `LogicalClock`，出参 `ActionProposal` 列表；提案仍走 `submit_proposal` 全管道。
- **选择**：B；确定性顺序 = `actor_wakeups` 队列序（写时稳定排序）；失败处置 = hook 抛任何异常 → `SchedulerWakeupError(actor_id, …)` + **整刻原子回退**（返回刻前状态对，不可变值 = 免费回滚）——部分提交不可见，G3-4 顺序一致性不被污染。
- **理由**：K2（hook 物理上拿不到写路径——guard 视图 + 提案出口是唯一通道，P2 `guard` 机制先例）；同步纯函数 = 可回放（P4 的 LLM policy 在 hook 外异步决策，结果以提案回流——P2 §13 非目标 7 的 P3 侧闭环）；玩家无 hook（MVP 玩家经 `submit_proposal` 外部驱动，Spec §7.3）。
- **一致性**：`ActorWakeup`（`state.py:158-166`）字段全消费；Spec §50 `BehaviorPolicy` 的接缝留口（P4 实现该 Protocol）；`Scheduler.__init__` `wakeup_hooks` 缺省 `None` → 空 `WakeupHookRegistry`：wakeup 条目命中时无 hook 可调 → 仅输出诊断（TraceRecord，SYSTEM）、不崩溃、不影响簿记（§3.8，R7-S4 风险1，E-P3-39⑤）。

### D-P3-15 调度状态序列化与回放

- **问题**：回放（G3-4 "replay event order 一致"）的判据与机制？
- **备选**：A：P3 自建调度快照信封（与 P1 `Snapshot` 双源）；B：调度状态全部在 `RuntimeState`（K7 设计后果）→ 直接复用 P1 `snapshot`/`restore_snapshot`/`dump_json`；回放同构性用 `scheduler_fingerprint` 校验配置。
- **选择**：B。判据（可执行化，G3-4）：① 同一 `restore_snapshot` 产物 + 同指纹 config + 同提案流，两次 `fast_forward` → 逐事件相同：逐事件比较键 `(event_type, world_revision, 事件发生刻)` 序列相等——位置 = 该次调用 `outcome.events` 元组序（commit 序，1:1 于已提交 effect，D-P3-18）；`事件发生刻` = 该事件所属事务在该次调用中提交时的刻（由 scenario/config/state 纯函数决定，两次运行的 tick 水位 `ticks_processed` 相等且与 §5.2/§5.3 表交叉验证）；`event.logical_tick` 恒 None（D-P2-18/D-P3-20）**不入键**；`event_id`/`transaction_id`/`entry_id` 为 uuid4 运行内唯一标识（`ids.py` 工厂、`transaction_executor.py:232` 预分配），判据 = 数量相等 / 运行内唯一 / 前缀正确（`evt_`/`txn_`/`sch_`）/ 与 committed effect 位置同构（D-P2-12），**不跨运行比原值**；② 中途（t=12 暂停点）snapshot → restore → 继续 → 与无 snapshot 路径的逐事件键序列逐字一致；③ 事务流回放：CommittedEffect 序列取自 `outcome.transactions[i].effects`（D-P3-18）→ 经 `apply_committed_effects`（`reducer.py:843`）→ 同一 `WorldState`（含 revision 值）。
- **理由**：不新建信封 = 不碰 P1；config 指纹把"配置漂移"从静默风险变成显式拒绝（指纹不等 → 回放中止 + 诊断，不静默）。
- **一致性**：P1 `snapshot.py`（`Snapshot` 收 RuntimeState 全字段，§6.3）、`serialization.py` 零改动；G2 移交 4（P1 冻结）。

### D-P3-16 错误与诊断分类（可检查不静默）

- **问题**：P3 的失败如何暴露——异常、数据结果，还是静默跳过？
- **选择**（全部落 §3 各模块代码块）：8 类失败双轨暴露。① 7 异常型 `UnknownActionError`/`IllegalTransitionError`/`QueueInvariantError`/`ClockRollbackError`/`UnknownConditionError`/`SchedulerConfigurationError`/`SchedulerWakeupError`——继承基类 `SchedulerError(ValueError)`（置 `clock.py` 依赖叶，无环，§3.3），各于其点抛出（调度点/入队点/求值点/构造点/hook；`ClockRollbackError` 下 restore 是唯一合法回退通道；`SchedulerWakeupError` 伴随整刻原子回退）；未注册动作另双轨：抛错 + 生命周期 FAILED 记录（`result_summary.reason="unknown_action"`）。② stale 提案 / 边界命中 = **数据结果**（`RevalidationDecision` REJECT / `BoundaryReport` / 生命周期 FAILED）——正常判定路径，非异常、不新增类型（复用 P1 词表），可序列化可断言（Spec §9 revalidation 四值词表先例）。"可检查不静默" = 每类失败要么抛可捕获异常、要么落在可序列化记录里，无第三条路。
- **一致性**：P2 异常族体例（`reducer.py` ReducerError 族 / `validation.py` ValidationError）；G3 对抗清单 A1–A8 逐类有测试（§6.3）。

### D-P3-17 事件条件 kind 重定义（event_kind → event_type）

- **问题**：原稿内置事件匹配条件 `event_kind` 匹配"DomainEvent kind 字面量"，但 `DomainEvent` 无 `kind` 字段（`events.py:131-141`：event_id/event_type/world_revision/logical_tick/transaction_id/payload/cause_ids/source_system/provenance/cascade/wall_time）；`transaction_executor.py:146` 定死 `event_type = effect.effect_type`（事件类型恒等于 effect 类型），结构 effect 词表全为 `core.*`（`reducer.py:216-222`）→ Gate fixture 触发器 `create_entity` 只能发 `event_type="core.create_entity"` 的事件，原 C1（`kind="event_kind", parameters={"kind": "encounter"}`）按字面永不命中，G3-1 不可达成（R2 BLOCK-1）。
- **备选**：A：保留 `event_kind` 仅改 fixture 匹配值（条件仍指向不存在的字段，不可实现）；B：kind 重定义为 `event_type`、匹配 `DomainEvent.event_type`（真实字段，P3 自持词表内定）；C：P3 给 `DomainEvent` 增 `kind` 字段（P1 源改动，禁止）。
- **选择**：B。`CONDITION_KINDS = {"event_type", "world_variable", "entity_component", "time"}`；`parameters = {"event_type": str}`；内置 resolver 语义 = 本刻提交事件流中存在 `event_type` 等于 `parameters["event_type"]` 的事件即命中。
- **理由**：落在 `DomainEvent` 真实字段上，匹配规则可检查可回放；场景语义（"encounter"）由触发器 id `scenario.encounter_12` 与队列 payload 命名 `ev_enc` 承载（D-P3-04 声明式 payload），条件层不需要私有词表；队列条目 `ScheduledEvent.kind`（7-kind 词表，§2.5）是**另一个类型**，不受本重定义影响。
- **一致性**：§3.7 词表/docstring/内置 resolver、§5.1 fixture C1、§5.2 S6/S7、§5.5、§6.1、G3-1 断言全部同步；P1 零改动（P3 自持词表）；G3-1 恢复可达成（t=12 C1 命中 → B1 fired → 暂停，Spec §48 Scenario D / Plan §12 Gate 闭合）。

### D-P3-18 SchedulerOutcome 承载级联管道完整产出（按调用作用域）

- **问题**：G3-4 要求每次 `fast_forward` 的事件序列与 CommittedEffect 回放比较（③ `apply_committed_effects`），M2b 要求 AUTHORITY/VALIDATION/TRANSACTION 的 trace 记录，A3/A4 要求处理序与 trace 序逐字一致——但原稿 outcome 仅有 `events_processed: int` / `transactions: list[TransactionId]`（R2 BLOCK-2），且聚合 scope 未定义：§5.2 S8"transitions 三条"与 §5.3 A5"transactions=[txn_2]"在两种口径下互斥。
- **备选**：A：outcome 只持计数/id，事件由测试侧从全局存储取——WorldState/RuntimeState 均无事件存储字段（`state.py:246-` / `217-227`），`trace.py` 仅数据类型无全局存储，无处可取；B：outcome = 按调用值对象，承载 `CascadeResult`（`cascade.py:678-702`）对应面，调度器自身不存储事件。
- **选择**：B。`transactions: tuple[Transaction, ...]`（完整对象、**含 ABORTED**、commit 序——`Transaction.effects` 即回放所需 CommittedEffect 序列）；新增 `events: tuple[DomainEvent, ...]`（本次调用全部发射事件，1:1 于已提交 effect，commit 序，D-P2-12）；新增 `trace_records: tuple[TraceRecord, ...]`（追加序）；**删除**冗余计数 `events_processed`（计数可从 `len(events)` 导出，不设独立计数字段——二选一取删除，此处写明）；**聚合作用域显式声明 = 按调用**（本次 fast_forward/step 开始至返回，与 A5 `transactions=[txn_2]` 口径一致）。
- **理由**：K1——事件不是世界状态组成部分，调度器不得另立第二存储；outcome 是调用观察值、纯值对象（全 ContractModel 字段），round-trip 可测；字段与 `CascadeResult` 逐一对应（final_state → 返回的 world，transactions/events/trace_records 1:1 承载，deferred/diagnostics 折入 `errors`/诊断串），**不新增任何 P2 符号**。
- **一致性**：G3-4a-c、M2b（trace 记录取 `outcome.trace_records`）、M3a、A3/A4 全部可测；`start_action` 的 2 条复合记录在 `submit_proposal` 侧产出、不入 ff outcome（D-P3-19）；S8 outcome 相应改为 `transitions=[S7 (INTERRUPTED@12)]` 一条（§5.2；R7-S3 补充1，E-P3-39①）。

### D-P3-19 start_action 两跳复合 2 记录与 G3-1 计数口径

- **问题**：原 `start_action` 签名返回单个 `LifecycleTransition`，但按迁移表（`LIFECYCLE_TRANSITIONS`，§3.6）PROPOSED→VALIDATING→ACTIVE 三态复合必须两次查表（VALIDATION_ACCEPTED 边 + SCHEDULED 边）→ 2 条记录；计数规则未写明，§5.2 S8 将 S2 计入"三条"，G3-1"18 条"基数不闭合（9+5+4，其中"5 条"与 §5.3 实际列举的 4 条断言矛盾）。
- **备选**：A：只返回终边记录（VALIDATION_ACCEPTED 记录丢失，不可检查）；B：返回 `tuple[LifecycleTransition, ...]`（恒 2 条，迁移序）；C：单记录 + 旁路列表（双源）。
- **选择**：B。`start_action(...) -> tuple[WorldState, RuntimeState, tuple[LifecycleTransition, ...]]`，恒 2 条（`VALIDATION_ACCEPTED@at_tick` + `SCHEDULED@at_tick`）；SchedulerOutcome 按调用作用域（D-P3-18）→ S8 outcome `transitions = [S7 (INTERRUPTED@12)]` 一条——S4 的 CHECKPOINT 迁移为 `apply_checkpoint` 内部簿记（E-P3-12② 签名 `tuple[RuntimeState, TraceRecord | None]` 不携带迁移记录、§2.4 伪代码 checkpoint 分支无捕获点），不出现在 outcome.transitions；可在模块级直调层断言（§6.1 action_lifecycle 用例已覆盖）（R7-S3 补充1，E-P3-39①）；start 的 2 条记录在 `submit_proposal` 侧产出（不在任何 ff outcome 内）。
- **理由**：迁移表是唯一权威（D-P3-07），复合边不得折叠（每跳独立可断言：from/to/event/at_tick）；按调用作用域与 A5 `transactions=[txn_2]` 及 K7"队列任意时刻可检"纪律一致。
- **一致性**：G3-1 统一为**列举断言口径**：暂停点 9 条（§5.2 断言 1–9）+ 分支 A 4 条（§5.3 实际列举：progress 单调序列 / 位置恰在 `txn_2` 首变 dest / 总事务数=2 / `completed_at==30`）+ 分支 B 4 条（§5.4 实际列举）= **17 条**；§6.2 G3-1 行与 §7 行同步；§6.1 `start_action` 用例改为断言 2 条返回。

### D-P3-20 逻辑时刻不打戳于事务/事件（归属口径）

- **问题**：原稿四处宣称（§2.3 末条、§5.2 S6、§5.3 A4、本 D-P3-11 一致性行）"事务经 `commit_transaction(..., logical_tick=t)` 透传打戳"，但唯一提交路径（D-P3-11 ①）`CascadeExecutor.run` 无 tick 参数（`cascade.py:867-874`），内部 `commit_transaction` 调用未传 `logical_tick`（`cascade.py:1171-1180`，恒 None，D-P2-18；`cascade.py:103` Trace 坐标约定同口径）；直调 `commit_transaction` 路线已被 D-P3-11 否决，P2 源码禁改（本任务边界）→ 原宣称不可实现（T08 按表行断言即失败）。
- **备选**：A：保留宣称待 P2 变更（违背 P2 源不改边界，构成隐性预期）；B：改真实口径——经 CascadeExecutor 提交的事务/事件 `logical_tick=None`（P2 不拥有时钟，D-P2-18），逻辑时刻归属由 `RuntimeState.logical_tick`（唯一权威时钟）+ `ScheduledEvent.due_tick` + `LifecycleTransition.at_tick` + outcome 按调用 tick 水位（`ticks_processed`）承载；若 Gate 确需打戳事件，须先经 **P2 勘误流程**（`CascadeExecutor.run` 增 tick 参数 + 新 D 项、重推 R1、同步任务包白名单），P3 范围外、不作为隐性预期。
- **选择**：B。
- **理由**：四载体全为冻结字段 / P3 值类型，零改动；"事件发生在哪一刻"是 (scenario, config, state) 的纯函数，可回放；G3-4a 比较键在 `event.logical_tick` 恒 None 前提下显式重定义（D-P3-15 ①：逐事件键 `(event_type, world_revision, 事件发生刻)`，位置 = `outcome.events` 元组序；`event_id`/`transaction_id`/`entry_id` 为 uuid4 运行内唯一标识——`ids.py` 工厂（uuid4 hex，ids.py:232-265，覆盖 `new_event_id` L232-234 / `new_transaction_id` L237-239 / `new_scheduled_entry_id` L263-265，E-P3-37）、`transaction_executor.py:232` 预分配——按数量/唯一性/前缀/位置同构比较，不跨运行比原值）。
- **一致性**：§2.3 末条 / S6 / A4 / D-P3-11 四处同步改写；§5.5-M3b、§6.2 G3-4a、§6.3 A4 的"(event_id, logical_tick, 批内序)"与"(event_id 序列 + tick 序列)"措辞全部改为上述键口径；D-P2-18 下游兑现方式改为"归属口径"而非"打戳"。

### D-P3-21 条件求值增补 tick 入参

- **问题**：内置 `time` kind 需要当前逻辑刻（`parameters {"tick": int}`，op 缺省 gte），但原 `ConditionResolver.evaluate(condition, view, events)` 与 `evaluate_condition(condition, view, events, registry)` 均无 tick 入参；view 为 `GuardedWorldState`（世界态视图，WorldState 无 `logical_tick` 字段，`state.py:246-`），级联事件 `logical_tick` 又恒 None（D-P3-20）→ time kind 在给定 API 下不可求值，§6.1"time gte 边界 `==` 命中"测试不可执行。
- **备选**：A：把 tick 放进 view（世界态视图加时钟字段 = 改 P2 `guard` 视图类型，禁止）；B：两签名增补 `tick: int`（`evaluate_boundaries` 已有 tick 入参，直接透传）。
- **选择**：B。`ConditionResolver.evaluate(self, condition, view, events, *, tick: int)`；`evaluate_condition(condition, view, events, *, tick: int, registry)`。
- **理由**：刻后求值唯一调用点 `evaluate_boundaries` 天然持有当前刻，透传即得；显式入参保持 resolver 纯函数性（无隐式全局/时钟读取）；P5/P9 自定义 resolver 受同一协议约束，确定性不降级。
- **一致性**：§3.7 协议注释与 `evaluate_condition` docstring 同步；§6.1 time kind 测试口径 = 显式传 tick 的命中/不命中各一（`tick == parameters.tick` → gte 命中；`tick - 1` → 不命中）；`ScheduledEvent.due_tick` 等既有 tick 消费点不受影响。

### D-P3-22 scheduled 边界的确定性入队机制（循环前播种）

- **问题**：`kind="decision_boundary"` 队列条目已定词表/payload 契约与 no-op match 分支（§2.4/§2.5），但全文无任何函数写入该 kind 条目——Scheduler 构造只持 boundaries 配置、不触碰 RuntimeState 队列（K7：门面不是真相），`make_scheduled_event` 只校验不产生 → scheduled 边界不入队则时钟永不停在其刻，"scheduled 边界仅 `due_tick <= tick` 时参评"（§3.7）无法触发，T01/T05 纯执行实现者无落点。
- **备选**：A：构造期入队（构造器触碰 RuntimeState 队列——构造时根本没有状态，K7 违背）；B：首次 `fast_forward`/`step` 调用时的循环前步骤，为 `due_tick > current_tick` 的 scheduled 边界补入 `kind="decision_boundary"` 条目（按 `boundary_id` 去重、`entry_id` 经 `new_scheduled_entry_id()` 签发），重复调用幂等不重复补入；C：scheduled 边界不入队、直接参评（时钟无停靠点，"刻到即停"不可实现）。
- **选择**：B。
- **理由**：入队时点 = 首次携带状态的调用，确定性（同状态 + 同配置 → 同一补入集合）；幂等可检查（查队列中既有 `kind="decision_boundary"` 条目的 `boundary_id`，已存在即跳过）；条目本身只是时钟停靠点（无 payload effect，match 分支 no-op），边界是否 fired 仍由刻后求值判定——机制层与语义层分离；`decision_boundary` payload 契约固定为 `{"boundary_id", "actor_id"}`（§2.5 表，`boundary_id` 为去重键）。
- **一致性**：§2.4 伪代码循环前步骤 + match 分支注、§3.8 `fast_forward` docstring、§6.1 scheduler 测试口径（scheduled 边界刻到 → 时钟停在其刻并参评；重复 `fast_forward` 不重复入队）同步；`entry_id` 为 uuid4 运行内唯一标识（D-P3-20 比较键口径，`ids.py:263` 签发）。

### D-P3-23 权威装配（AuthorityPolicy 为构造器必填面）

- **问题**：`CascadeExecutor` 是全部世界写入唯一通道（D-P3-11 ①），其构造参数 `policy: AuthorityPolicy` 必填（`cascade.py:800`，`__init__` L797-814），且 AuthorityPolicy **closed-by-default**（`default_decision` 缺省 DENY、空 rules = 完全封闭，`authority.py`，D-P2-09；rule 需 ≥1 `allowed_writers`）——原 Scheduler 草图与 §5.1 fixture 从未构造 `AuthorityPolicy`、未授予任何实际产 effect 的 producer → Gate 世界事务（S6 `create_entity`、A4 `set_component`）全部被 authority 阶段 DENY，G3-1 不可达成（"世界 rev 恰 +1 / 唯一位置变更事务"等精确断言无法成立）。
- **备选**：A：Scheduler 接收预装配的 `CascadeExecutor` 实例（装配责任泄漏给调用方，fixture 须自行构造执行器，纯执行实现者易错）；B：Scheduler 构造器增 `authority_policy: AuthorityPolicy`（必填）+ `component_registry`/`producer_registry`（可选透传）+ 既有 `trigger_registry`，内部构造唯一 `CascadeExecutor`。
- **选择**：B。
- **理由**：closed-by-default = "默认无权、显式授予"（K3/K4），Gate fixture 必须显式列出授予面——§5.1 的 `AP` 授予 `core.create_entity` 与 `core.set_component`（component_type=`movement.position`）给场景测试 origin `origin_scenario`（两触发器所产 effect 的 producer 身份与之对齐，`ProducerId` 无随机段名字型，`ids.py:189-198`），其余 effect 类型保持 DENY（最小授予面，不过度授权）；scheduler 自身仍不产世界 effect（D-P3-11 producer 归属），`"scheduler"` producer 无需授予。
- **一致性**：§3.8 构造器草图、§5.1 fixture、D-P3-11 管道描述同步；G3-1 的 `txn_1`/`txn_2` 可被授权提交；R1 恒武装断言与武装点（`cascade.py:810`）不变。

### D-P3-24 未响应暂停幂等重报（入口首检）与原子刻错误路径 outcome 口径

- **问题**：§6.3 A7 要求"B1 命中暂停后不调用 resume/abort，直接对暂停态再 `fast_forward` → 返回同一暂停结果（时钟不前进、队列不变、不静默跳过边界、不崩溃，幂等可检查）"，但 §2.4 主循环无任何重入规则：按字面重入，`take_due` 取走 cp@20 → 时钟 12→20 前进（违反"时钟不前进"），`apply_checkpoint` 对 INTERRUPTED 实例的 CHECKPOINT 自迁移为表外迁移（`LIFECYCLE_TRANSITIONS` 的 INTERRUPTED 出边仅 RESUMED/ABORTED）→ `IllegalTransitionError`（违反"不崩溃"）；即便跳过，B1 的条件（event_type 命中本刻事件流）在 t=20 无法再命中且 K1 纪律下 t=12 事件流不可再取 → 边界被静默跳过（违反"不静默跳过"）。"未响应暂停"这一事实不在 (WorldState, RuntimeState, config) 中——状态机无"待决暂停"位（K7：无隐藏控制流），重入行为必须是纯派生 + 显式口径；另单刻处理中的错误路径（任何 P3 错误）outcome 形状未定义——§2.4 确定性论证 5（原子刻）只说"返回刻前状态对"，未说 `SchedulerOutcome` 取何值。R3 盲审三处独立指出（S1-补充3、S2-补充1、S4-补充1）；风险点 S2-RP1 另要求落定后复核 G3-4a 回放口径不被新入口路径破坏。
- **备选**：A：状态新增"待决暂停"持久字段（Scheduler 存暂停记录）——K1 违背（事件/状态不是世界状态组成部分，调度器不另立第二真相）且 K7 违背（新增字段即隐藏控制流）；B：**入口首检 + 纯派生**——`fast_forward`/`step` 主循环前（循环前播种之前，重入零副作用）检查 ∃ a ∈ `runtime.active_actions.values()`：`a.status == INTERRUPTED` 且 ∃ b ∈ boundaries：`b.blocking` 且 `b.actor_id == a.actor_id` 且 `a.actor_id ∈ player_actor_ids` → 立即返回同一暂停（不推进时钟、不消费队列、不发事件）；外部调用方执行 resume/abort（status 离开 INTERRUPTED）后规则自动失效，无需"清除"步骤；C：暂停期间禁止外部调用（入口 raise）——把簿记责任推给调用方，A7"幂等重报"不可达。
- **选择**：B。精确处置：
  1. 首检条件是 **纯 (WorldState, RuntimeState, config) 派生**（active_actions 状态 + boundaries 注册 + `player_actor_ids`），不引入任何新持久状态，重入零副作用（置于循环前 scheduled 边界播种之前，D-P3-22）；
  2. 返回的暂停与首次暂停同构：`paused=True`、`pause_reason` 按注册序取首个命中边界（boundary_id 重新推导，多边界命中仍唯一）、`tick = ticks_processed = 当前 logical_tick`（时钟不前进）、`transactions`/`events`/`transitions`/`errors` 全空；队列条目（cp@20/end@30 等）不处理；
  3. **自动失效**：resume（INTERRUPTED→ACTIVE）或 abort（INTERRUPTED→FAILED）后首检条件自然不满足、后续调用正常推进——"未响应暂停"的重报保证**限定于该行动仍处 INTERRUPTED（玩家未响应）期间**（幂等、外部可检查），调用方不持簿记状态；无 INTERRUPTED 背书的边缘（玩家 blocking 边界命中但无行动被中断）见第 6 项边缘声明；
  4. **原子刻错误路径 outcome 口径**（单刻原子性，§2.4 确定性论证 5）：单刻处理中任何 P3 错误 → 返回刻前状态对 + `SchedulerOutcome(paused=False, pause_reason=None, ticks_processed=<刻前 logical_tick>, transactions=(), events=(), trace_records=(), transitions=(), errors=<非空诊断串>)`——不崩溃、部分提交不可见（不可变值 = 天然回滚）、无部分状态泄漏给调用方；
  5. `step` 与 `fast_forward` 同口径（入口首检与错误路径相同）；
  6. **边缘声明（R5/F4-02）**：玩家 blocking 边界命中但**无行动进入 INTERRUPTED**（玩家无活动行动、或该行动 `interruptible=False`）：暂停**仅返回一次**（边界 fired 记录 + trace 留痕，已送达调用方），重入 `fast_forward` 正常推进、该边界不重检（一次性事件，非"静默跳过"——其暂停效应已交付）；本决策入口重报规则**仅在 `TimePolicy.pause_on_player_boundary=True` 且存在 INTERRUPTED 背书时生效**（Gate 场景 act_1 可中断 → 背书存在，不受影响）。
- **理由**：(1) 新增持久字段 = 隐藏控制流（K7 违背）——暂停是可重派生的观察值，不是存储事实；(2) 注册序首个命中确定（config 顺序稳定），多边界命中时重入结果唯一；(3) 自动失效使"未响应暂停 → 重报 → 响应 → 继续"成闭环、无清除协议，纯执行实现者无歧义；(4) 错误路径钉死为"不崩溃 + 非空诊断 + 刻前状态"，与正常路径 outcome 同构，§6.1 刻原子性用例可直接断言。
- **一致性**：§2.4 主循环伪代码（入口首检步骤，置于播种之前）+ 确定性论证 5、§3.8 `fast_forward`/`step` docstring（幂等重报 + 原子刻错误路径）、§3.6 `apply_checkpoint` 非 ACTIVE 守卫（第二道防线，F2-02——第一道防线为本首检）、§6.1 scheduler 测试口径（幂等重报用例 + 刻原子性用例）、§6.3 A7 同步；G3-1 的 17 条断言不变，G3-4a E1/E2/E3 事件键序列不变（S2-RP1 复核：重入路径零事件零事务、tick 水位不前进，两次运行逐事件键序列同构）；`LIFECYCLE_TRANSITIONS` 边不变。

### D-P3-25 中断不剪除队列条目（剪除仅终态）与 NPC 非阻塞中断收敛边界

- **问题**：(1) 原 `resume_action` docstring 写"若下一 checkpoint 条目已被剪除则补入队"，但全文唯一已定义的剪除点是终态迁移（COMPLETED/FAILED）——可被 resume 的实例处于 INTERRUPTED（非终态），其条目按现行规则永不被剪除，该句引用了当前规则下**不可达**的剪除情形（悬空机制引用），会诱导实现者发明未定义的剪除路径；resume 时"重复入队与否"口径未钉死。(2) NPC（非玩家）行动被 `interrupt=True`（缺省值）的非阻塞边界命中迁 INTERRUPTED 后：时钟不暂停（非阻塞，D-P3-10），但该行动后续 checkpoint 刻条目（cp@k）在后续 `fast_forward` 中命中非 ACTIVE 实例——簿记口径、诊断串与收敛路径（谁恢复该行动？调度器是否自动处置？）原稿未定义。R3 盲审三处独立指出（S2-补充2、S1-补充7、S3-补充3）；风险点 S2-RP2 要求在 §6.3 增加对应用例。
- **备选**：剪除口径：A：**剪除仅发生于进入终态（COMPLETED/FAILED）**——INTERRUPTED 保留全部条目，resume 从原条目继续求值（不重复入队）；"resume 时条目缺失"为防御分支（正常流程不应发生），发生则补入队并输出诊断 `checkpoint_requeued_after_defect`（簿记可修复、不静默跳过）；B：离开 ACTIVE 即剪除 + resume 重新入队（入队时点判断有误则重复条目 → 非确定，且需"已入队"标记——又是隐藏状态）。NPC 非阻塞中断收敛：(a) **P3 声明收敛边界**：不崩溃、簿记确定、不静默跳过——INTERRUPTED 行动与残留条目留在状态中、任意时刻可序列化可检查；`apply_checkpoint` 守卫 no-op + 唯一诊断 `checkpoint_skipped_interrupted`；最终收敛交给 P4/P5（`WakeupHook` 重新提案）或外部 abort（actor ∈ `player_actor_ids`）；(b) Scheduler 对 NPC 中断行动自动 ABORT（P3 自收敛，但自动中止是语义策略判断——哪个行动值得放弃，P3 无策略输入、不可从 (state, config) 派生）。
- **选择**：剪除口径 A + 收敛 (a)。
  1. **队列条目剪除规则（全文唯一剪除点）**：仅当行动进入终态（COMPLETED/FAILED，`transition_action` 终态分支）时剪除该实例剩余队列条目（action_checkpoint/action_end/deadline，确定性簿记）；INTERRUPTED 为**非终态**，其全部条目保留；resume（INTERRUPTED→ACTIVE，RESUMED 边）从原条目继续求值、**不重复入队**（与 §5.3 A1"cp@20 已在队列 → 不重复入队"同口径）；"resume 时条目缺失"为防御分支：命中则补入队并输出诊断 `checkpoint_requeued_after_defect`（正常流程不应发生；发生即簿记缺陷，可观察、可修复，不违背 K1/K7——补入队是 (state, config) 派生的簿记修复，非新隐藏状态）；
  2. **NPC 非阻塞中断收敛边界**：非阻塞边界（blocking=False）命中且 interrupt=True（缺省）→ 该 actor 的 ACTIVE interruptible 行动迁 INTERRUPTED（不暂停、时钟继续，**不进入 D-P3-24 入口首检**——首检只看 blocking 边界）；其后 checkpoint 刻 `apply_checkpoint` 命中非 ACTIVE 实例 → no-op（F2-02 第二道防线守卫）、时钟继续、发唯一诊断 `checkpoint_skipped_interrupted` 入 `outcome.trace_records`（TraceKind.SYSTEM，§3.6）；**P3 收敛边界声明（三项）**：不崩溃（无未捕获异常）、簿记确定（INTERRUPTED + 残留条目任意时刻完整可序列化可检查、两次运行同构）、不静默跳过（每处 skip 均出诊断）；最终收敛路径 = actor 的 `WakeupHook` 重新提案（P4/P5 范围）或外部 abort（actor ∈ `player_actor_ids` 时外部调用方可随时 `abort_action`；纯 NPC actor 在 P3 无外部中止面，收敛依赖 wakeup）。
- **理由**：(a) 对 (b)：自动中止是语义策略（哪个行动值得放弃）——P3 纯执行、不做策略推断（P4/P5 持策略、P3 持执行的层级划分），任何自动 ABORT 都是任意裁断；(a) 把判断交给策略层，P3 只保证簿记不变量（不崩溃/确定/不静默跳过），与 K7 可序列化真相同构。剪除仅终态使 resume 成为纯续接（无状态重建、无重复入队风险），悬空引用按 S1-补充7/S3-补充3 要求改写消除；诊断名归 `checkpoint_*` 前缀族（与 `checkpoint_skipped_terminal`，F2-02，同族）。
- **一致性**：§2.4 match 分支（action_checkpoint/action_end 处理与守卫注）、§3.6 `transition_action` docstring（终态剪除）、`apply_checkpoint` 非 ACTIVE 守卫 + docstring（INTERRUPTED → `checkpoint_skipped_interrupted`）、`resume_action` docstring（中断不剪除、不重复入队、防御分支 `checkpoint_requeued_after_defect`）、§3.7 `DecisionBoundary.interrupt` 注释（非阻塞命中收敛见 D-P3-25）、§6.1 `action_lifecycle`/`scheduler` 用例 + §6.3 A2（NPC 非阻塞中断方向用例，S2-RP2）同步；G3-1 的 17 条断言不变（Gate 场景不含 NPC 非阻塞中断，属对抗测试范围）；`LIFECYCLE_TRANSITIONS` 状态/边不变（本决策是队列条目与诊断规则，非状态机边）。

### D-P3-26 触发器点名求值映射的数据来源（`named_triggers` 显式构造参数）

- **问题**：F2-13 自相矛盾——§3.8 原稿称 scheduler 的 `trigger_id→trigger` 映射构造时即由注册表已注册集合建好（并自述为配置级读取、无运行时状态），而 E-P3-23① 原因段引 K7"不得以私有字段访问补位"：`CascadeTriggerRegistry` 公开 API 仅 `register`/`evaluate_all`/`trigger_ids`（cascade.py:589-644）、`_triggers` 为 `__slots__` 私有（cascade.py:584）——纯执行者无合规取数途径，两处口径矛盾（R4 盲审 S3 补充1）。
- **备选**：A：构造时读私有 `_triggers` 一次性（**弃**：私有字段访问，K7 直接违背，且对 P2 内部结构脆弱）；B：`evaluate_all` + filter（**弃**：求值面扩大——`evaluate_all` 对当前视图全量求值**全部**触发器，语义偏离"点名"（单触发器定向求值），引入本不需要的求值面）；C：**显式构造参数** `named_triggers`（**选择**）。
- **选择**：C。`Scheduler.__init__` 新增**必填**参数 `named_triggers: frozenset[tuple[str, CascadeTrigger]]`：`trigger_id→trigger` 映射**由该参数建立**（不可变；查找按 trigger_id 键、确定性；可序列化描述 = trigger_id 投影）；fixture 将注册进 `trigger_registry` 的**同一批触发器对象**显式传入（fixture 持有两者、无额外状态，§5.1；**R5 注记**：Gate fixture 由 D-P3-27 单路化——`trigger_registry` 装配为显式空注册表、stub 仅存在于 `named_triggers`，本"同一批"表述适用于将触发器注册进注册表的 fixture，E-P3-30）；缺参 → `TypeError`（必填构造参数，与 `authority_policy` 同口径，D-P3-23）；空集 → 无命名触发器可点名，`kind="event"` 仅 effects 形态可用，`trigger_id` 形态（名字不在映射中）→ `QueueInvariantError`（可检查不静默；经原子刻错误路径返回，§2.4 论证 5 / F2-03；§6.1 构造用例）。
- **理由**：显式参数把"装配方已知晓哪些命名触发器将被点名"从隐性（依赖注册表内部集合快照）变为构造期显式契约——K7 零私有访问（现方案零私有字段读取）、确定性（映射内容 = 构造输入，无注册时序依赖）、与 D-P3-23"装配显式化"纪律同款；构造参数非新导出符号，`__all__` 249 不变。
- **一致性**：§3.8 `Scheduler.__init__` 签名与 docstring（触发器名称解析段改写）、§5.1 调度器构造行（`named_triggers` 传同一批对象；R5 由 D-P3-27 改写为单路，E-P3-30）、§6.1 `scheduler.py` 构造用例（缺参/空集行为）、E-P3-23① 内容/原因段同步（R4 取代、留痕）；G3-1 的 17 条断言不变、`LIFECYCLE_TRANSITIONS` 边不变、P1 13 模块字节冻结不变。（R4 出处：S3 补充1。）

### D-P3-27 Gate fixture 单路化（`trigger_registry` 空注册表）与触发器产出通用契约（cause_ids 口径）

- **问题**：原 §5.1 调度器构造行让 `trigger_registry` 持两个命名触发器并装配进唯一 `CascadeExecutor`、`named_triggers` 传同一批对象——双路求值：点名求值（单触发器）与级联回合再求值（每回合 COMMITTED 后对注册表全量再求值，cascade.py:969-981）命中同一 stub。F3-01 stub 状态守卫（E-P3-24）只抑制"effect 已生效后重发"（`ent_bandit` 已存在 / `position` 已到 `dest`），不抑制 `movement.arrival` 在 t=12 级联回合再求值时的**完成前首次求值**（该刻 `position (0,0) ≠ dest` → 守卫不触发 → stub 产出 `set_component`）——该产出是否提交取决于全文未钉的 cause_ids 策略：协议合规产出（`cause_ids` 回指本回合事件，`CascadeTrigger` 协议义务，cascade.py:481-483）通过因果闭合检查于 t=12 提交 → 位置 t=12 变更、暂停点 rev=R2 而非 R1、分支 A 总事务数变 3，G3-1 断言 #2/#9/M2(b) 全破；无事件引用的产出被闭包检查丢弃（cascade.py:1267-1316，`trigger_output_dropped` 诊断）→ 场景成立。"纯执行"实现者无选择依据。R5 盲审指出（S1 补充1）。
- **备选**：A：**Gate fixture 单路化**——`trigger_registry` 显式装配**空注册表** `CascadeTriggerRegistry()`，`enc_stub`/`arr_stub` 只存在于 `named_triggers`（D-P3-26）；Gate 场景全部世界 effect 产出走 scheduler 点名求值单路（ev_enc@12 队列条目 → `encounter_12` 点名 → create_entity → txn_1；t=30 completion → `arrival` 点名 → set_component → txn_2）；CascadeExecutor 注册表为空 → 级联回合再求值面为空（`evaluate_all` 返回空，无重发、无 `trigger_output_dropped`）→ §5.2 S8 `transactions=(txn_1,)` 与 G3-1 分支 A 总事务数 = 2、M2(b)"唯一位置变更事务"**由构造成立**，Gate 判据不依赖闭包过滤行为（选择）；B：保留双路 + 钉死 cause_ids 策略（stub 回指本回合事件则通过闭包提交 → 破 Gate 场景；或产出空 `cause_ids` 依赖闭包检查确定性丢弃 → 场景成立但 Gate 判据依赖闭包过滤行为、实现面更复杂）（弃）。
- **选择**：A。`trigger_registry=CascadeTriggerRegistry()`（显式空注册表；`None` 缺省等价，cascade.py:852），§5.1 stub 状态守卫文本重定位为**通用契约**（适用于 fixture 向注册表注册触发器的情形，Gate 场景不用）：守卫抑制"effect 已生效后重发"；另补 `cause_ids` 通用口径：注册表触发器 stub 的产出 `cause_ids` **必须回指本回合事件 ID**（`CascadeTrigger` 协议义务，cascade.py:481-483）；无法回指时产出空 `cause_ids` → 被因果闭合检查确定性丢弃（cascade.py:1267-1316，`trigger_output_dropped` 诊断，不静默）——两种写法结果均确定。
- **理由**：单路化使 Gate 场景全部世界 effect 产出经唯一可判定的点名求值路径（§3.8 docstring 口径已钉死），"双路求值"不再构成语义面——Gate 判据由构造成立、不依赖闭包过滤行为，纯执行实现者无选择歧义；通用契约（守卫 + `cause_ids` 口径）保留为 fixture 向注册表注册触发器情形的钉死口径（A3 对抗独立 fixture 不受 Gate 空注册表影响、适用该通用契约，§6.3）。
- **一致性**：§5.1 调度器构造行与触发器 bullet 改写、§3.8 `Scheduler.__init__` 签名与 docstring（`trigger_registry` 参数语义钉死：`None` 缺省 = 空注册表、点名求值不受影响；注册表非空时级联再求值命中注册触发器，幂等与 `cause_ids` 口径见 §5.1 通用契约）、§5.2 S6/S8、§5.3 A4、§5.5 M2(b) 相关行口径注记同步（"守卫"→"单路（D-P3-27，由构造成立）"，断言值不变）、§6.1 scheduler 构造用例补（"`trigger_registry=None` 缺省行为 + fixture 装配断言 `trigger_registry` 为空"）、E-P3-24 R5 注记补录、E-P3-30 留痕；G3-1 的 17 条断言不变（双路→单路不改断言值、仅去除对闭包行为的依赖）、`LIFECYCLE_TRANSITIONS` 边不变、`__all__` 249 不变（无新导出符号）、P1 13 模块字节冻结不变。（R5 出处：S1 补充1。）

---

## 5. 核心 Gate 场景精确时序

> Plan §12 原文场景：`Player starts 30 min travel → t = 12 min encounter → scheduler stops fast-forward → ActiveAction progress == 12/30 → player decision boundary → action may resume / abort`。Spec §48 Scenario D 同构（L2524-2536）。本节给出**伪代码级时序表**，P3-T08 测试逐行断言。

### 5.1 前置设定（fixture，全场景共用）

- **实体/组件**：`ent_player`（组件 `movement.position = {x:0, y:0}`）、`ent_dest`（坐标 `{x:30, y:0}`）；世界 revision `R0`（`INITIAL_WORLD_REVISION`）。
- **注册表**（`ActionRegistry`，P5 在此生产，测试直接构造）：
  `ActionSpec(action_id="travel", executor="movement.travel_system", parameters={"destination": ParameterSpec(type="entity", required=True)}, duration_policy=DurationPolicy(kind="hint", hint_scale=1.0), interruptible=True, completion_trigger="movement.arrival")`
- **触发器**（P2 `CascadeTrigger` 协议（cascade.py:473；同步形态 `SyncTrigger`，cascade.py:503；注册表 `CascadeTriggerRegistry`，cascade.py:573，别名 `TriggerRegistry`），命名注册；**注册时声明的 producer = `origin_scenario`**（D-P3-11 统一口径，F2-01））：`scenario.encounter_12` → `create_entity(ent_bandit)`；`movement.arrival` → `set_component(ent_player, movement.position, {x:30, y:0})`。**stub 必须幂等（状态守卫，R4/E-P3-24；R5 重定位为通用契约，D-P3-27/E-P3-30）**：重求值时查 `guard(state)` 视图——目标实体已存在（`encounter_12` → `ent_bandit` 已在世界）或目标组件已到达值（`movement.arrival` → `movement.position == destination`）→ 返回空 effect 列表、不重发（守卫抑制"effect 已生效后重发"）；fixture 可用闭包变量记录已发集（属测试局部 fixture 状态、非引擎状态）。**通用契约（适用于 fixture 向注册表注册触发器的情形；Gate 场景不用——Gate 已单路化，D-P3-27）**：级联回合再求值（`CascadeExecutor.run` 每回合 COMMITTED 后对全部注册触发器再求值，cascade.py:969-981）命中注册表内 stub 时，守卫对其幂等；另补 `cause_ids` 通用口径：注册表触发器 stub 的产出 `cause_ids` **必须回指本回合事件 ID**（`CascadeTrigger` 协议义务，cascade.py:481-483）；无法回指时产出空 `cause_ids` → 被因果闭合检查确定性丢弃（cascade.py:1267-1316，`trigger_output_dropped` 诊断，不静默）——两种写法结果均确定。**Gate 场景验收判据（单路，由构造成立）**：全部世界 effect 产出经 scheduler 点名求值单路（ev_enc@12 队列条目 → `encounter_12` 点名 → create_entity → txn_1；t=30 completion → `arrival` 点名 → set_component → txn_2），级联回合再求值面为空（注册表空，`evaluate_all` 返回空，无重发、无 `trigger_output_dropped`）——§5.2 S8 `transactions=(txn_1,)` 与 G3-1 分支 A 总事务数 = 2 逐行成立（D-P3-27）。**『注册时声明』的 producer 载体** = stub 的 `evaluate` 产出 effect 时写入 `ProposedEffect.source`（effects.py:219 必填 `ProducerId`），经 `transaction_executor.py:156-157` 流入事件 provenance（`source_system=effect.source`、`provenance=Provenance(producer_id=effect.source)`）——P2 注册表 API 无 producer 存储位（L3-01）。
- **边界**：`B1 = DecisionBoundary(boundary_id="B1", actor_id=ent_player, kind="condition", condition=InterruptCondition(condition_id="C1", kind="event_type", parameters={"event_type": "core.create_entity"}), blocking=True, interrupt=True, reason="encounter")`（事件匹配条件匹配 `DomainEvent.event_type`，D-P3-17；场景语义 "encounter" 保留在触发器 id `scenario.encounter_12` 与队列 payload 命名 `ev_enc` 中——条件层不再引入私有 "encounter" 词）。
- **权威策略**（显式构造，D-P3-23/D-P2-09）：`AP = AuthorityPolicy(rules=[AuthorityRule(selector=AuthoritySelector(effect_type="core.create_entity"), allowed_writers=[origin_scenario]), AuthorityRule(selector=AuthoritySelector(effect_type="core.set_component", component_type="movement.position"), allowed_writers=[origin_scenario])])`——closed-by-default（`default_decision` 保持缺省 DENY，其余 effect 类型完全封闭）；`origin_scenario` = 场景测试 origin（`ProducerId` 无随机段名字型，`ids.py:189-198`）；触发器 `scenario.encounter_12`/`movement.arrival` **注册时声明的 producer**（＝其所产全部 effect 的 producer，含 completion_trigger 求值产物）均对齐 `origin_scenario`（D-P3-11 producer 归属统一口径，F2-01）。
- **初始队列**（剧本预排）：`[ev_enc@12]`（`kind="event"`, `payload={"trigger_id": "scenario.encounter_12"}`）。
- **调度器**：`Scheduler(registry, authority_policy=AP, time_policy=TimePolicy(checkpoint_interval_ticks=10), boundaries=[B1], player_actor_ids={ent_player}, trigger_registry=CascadeTriggerRegistry(), named_triggers=frozenset({("scenario.encounter_12", enc_stub), ("movement.arrival", arr_stub)}), assert_barrier_armed=True)`（屏障已 `install_write_barrier()`——R1 断言通过；`wakeup_hooks` 参数省略 → 走空注册表缺省（R7-S4 风险1，E-P3-39⑤）；`trigger_registry` = **显式装配的空注册表**（R5/D-P3-27 Gate fixture 单路化：`enc_stub`/`arr_stub` 只存在于 `named_triggers`、为点名求值唯一数据来源，级联回合再求值面为空——旧双路装配表述由本条取代，勘误留痕 E-P3-30）；内部装配进唯一 `CascadeExecutor`（其注册表为空），D-P3-23；`named_triggers` 传入的两个 stub 由 fixture 持有、无额外状态，D-P3-26；run()-级 origin 口径（R6/F5-01，E-P3-34）：Gate fixture 的 `CascadeExecutor.run` 提交一律以 `Provenance(producer_id=origin_scenario, origin=OriginKind.SCENARIO)` 构造（provenance.py:41-53，§3.8 F2-15 段）。
- 记号：`R0/R1/…` = 世界 revision 序列；`act_1` = travel 的 `ActionInstanceId`（`act_` 前缀）——构造时经 `new_action_instance_id()`（`ids.py:255`，`act_` + uuid4 hex）签发，此处速记（F2-14）；`cp@k`/`end@k` = kind 为 `action_checkpoint`/`action_end` 的队列条目。

### 5.2 主时序（提交 → fast-forward → 暂停）

| 步 | 操作 | 时钟 | 队列（操作后） | act_1 状态 / progress | 世界 rev | 事务 / 事件 |
|---|---|---|---|---|---|---|
| S0 | 初始态（见 §5.1） | 0 | `[ev_enc@12]` | — | R0 | — |
| S1 | `submit_proposal(P1)`：`P1 = ActionProposal(actor_id=ent_player, action_id="travel", arguments={"destination": ent_dest}, timing=ActionTiming(duration_hint_ticks=30), base_world_revision=R0, provenance=…)`；revalidation：`is_stale(R0, R0)` 假 → **ACCEPT**；入 `pending_proposals`，生命周期 **PROPOSED** | 0 | `[ev_enc@12]` | PROPOSED / — | R0 | —（簿记） |
| S2 | 调度：`validate_arguments` 过；`resolve_duration(hint×1.0, 30) = 30`；`start_action`：PROPOSED→VALIDATING→ACTIVE 两跳复合（2 条记录 `VALIDATION_ACCEPTED@0` + `SCHEDULED@0`，D-P3-19）；写 `ActiveAction`（start_tick=0, expected_end_tick=30, interruptible=True, base_world_revision=R0）；入队 `cp@10`（间隔 10）、`end@30` | 0 | `[cp@10, ev_enc@12, end@30]` | ACTIVE / 0.0（last_trans=0） | R0 | —（**开始时刻无世界 effect**，M2） |
| S3 | `fast_forward`：`take_due` → 批 `[cp@10]`，t=10 > 0 → `set_logical_tick(10)`（跳变） | 10 | `[ev_enc@12, end@30]` | ACTIVE | R0 | — |
| S4 | 处理 `cp@10`：`apply_checkpoint`（CHECKPOINT 自迁移）：progress=10/30≈0.3333，next=20 → 入队 `cp@20`，`base_world_revision` re-anchor（当前仍 R0），`last_transition_tick=10`；**不提交事务**（D-5 簿记） | 10 | `[ev_enc@12, cp@20, end@30]` | ACTIVE / 0.3333 | R0 | — |
| S5 | `take_due` → 批 `[ev_enc@12]`，t=12 > 10 → 时钟跳至 12 | 12 | `[cp@20, end@30]` | ACTIVE | R0 | — |
| S6 | 处理 `ev_enc@12`：点名求值单路（D-P3-27：注册表空 → 级联回合再求值面为空、无重发）——trigger `scenario.encounter_12` → `create_entity(ent_bandit)` → **CascadeExecutor 提交**（事件 `logical_tick=None`，D-P2-18；逻辑时刻由本刻 due_tick + `at_tick` 定位，D-P3-20） | 12 | `[cp@20, end@30]` | ACTIVE | R1 | `txn_1`；`evt_enc`（`event_type="core.create_entity"`，`logical_tick=None`（D-P2-18）） |
| S7 | **刻后求值 @12**（当刻新 `guard(world)` 视图，G2 移交 2）：`C1` 命中（本刻事件流含 `event_type=core.create_entity` 的事件，D-P3-17）→ `B1` fired（interrupt=True）：act_1 **ACTIVE→INTERRUPTED**（at_tick=12）：`progress=(12-0)/30 = 0.4 == 12/30`，`last_transition_tick=12`，`base_world_revision` re-anchor 至 R1（§2.4 中断分支 updates，D-P3-08） | 12 | `[cp@20, end@30]` | INTERRUPTED / 0.4 | R1 | —（生命周期簿记） |
| S8 | `B1.blocking` ∧ `ent_player ∈ player_actor_ids` → **PAUSE**：返回 `SchedulerOutcome(paused=True, pause_reason=PauseReason("decision_boundary", boundary_id="B1", tick=12), ticks_processed=12, transactions=(txn_1,)（单路，D-P3-27，由构造成立），events=(evt_enc,), transitions=[S7 (INTERRUPTED@12)] 一条（按调用作用域，D-P3-18；S4 的 CHECKPOINT 迁移为 apply_checkpoint 内部簿记（E-P3-12② 签名不携带迁移记录、伪代码 checkpoint 分支无捕获点），不出现在 outcome.transitions——可在模块级直调层断言，§6.1 action_lifecycle 用例已覆盖；start_action 的 2 条记录在 submit_proposal 侧产出，D-P3-19）)`。**玩家收回控制**（Spec Scenario D "player regain control"） | 12 | `[cp@20, end@30]` | INTERRUPTED / 0.4 | R1 | — |

**暂停点 G3 精确断言**（`test_gate_scenario_travel_interrupt`，逐条可执行）：

1. `runtime.logical_tick == 12`；
2. `world.world_revision == R0.next()`（恰 +1，encounter 事务唯一）；
3. `act_1.status is ActionLifecycleStatus.INTERRUPTED`；
4. `act_1.progress == 12/30`（**精确相等**——推导式 `(12-0)/(30-0)`，浮点同构可断言 `== 0.4`）；
5. `act_1.start_tick == 0` 且 `act_1.expected_end_tick == 30`（暂停不改时间预算）；
6. `act_1.base_world_revision == R1` 且 `act_1.last_transition_tick == 12`；
7. `runtime.scheduler_queue` 恰为 `[cp@20, end@30]`（条目类型/`sch_` 前缀/`due_tick` 逐一断言）；
8. `outcome.paused is True` 且 `outcome.pause_reason.boundary_id == "B1"`；
9. 玩家位置组件仍为 `{x:0, y:0}`（M2：暂停时位置未动）。

### 5.3 分支 A —— resume（恢复）

| 步 | 操作 | 时钟 | 队列（操作后） | act_1 状态 / progress | 世界 rev | 事务 / 事件 |
|---|---|---|---|---|---|---|
| A1 | 玩家恢复：`scheduler.resume_action(act_1)` → **INTERRUPTED→ACTIVE**（RESUMED，at_tick=12）：start_tick=0/expected_end_tick=30 **不变**（progress 连续，暂停不消耗逻辑时间，D-P3-08）；`base_world_revision` re-anchor 至 R1；`cp@20` 已在队列 → 不重复入队 | 12 | `[cp@20, end@30]` | ACTIVE / 0.4 | R1 | — |
| A2 | `fast_forward`：批 `[cp@20]` → 时钟 20；`apply_checkpoint`：progress=20/30≈0.6667，next=30 → 入队 `cp@30`；re-anchor（当前 R1） | 20 | `[end@30, cp@30]`（稳定序：`end@30` 先入队） | ACTIVE / 0.6667 | R1 | — |
| A3 | 批 `[end@30, cp@30]`（同刻批，稳定 FIFO，D-P3-05）→ 时钟 30 | 30 | `[]` | ACTIVE | R1 | — |
| A4 | 处理 `end@30`：到点且 ACTIVE → `complete_action`：`movement.arrival` 触发器点名求值单路（D-P3-27：注册表空 → 级联再求值面为空、无重发）→ `set_component(position, dest)` 经 **CascadeExecutor 提交**（事件 `logical_tick=None`，D-P2-18；逻辑时刻由本刻 due_tick + `at_tick` 定位，D-P3-20）；**ACTIVE→COMPLETED**（result_summary `{"completed_at": 30}`）；终态迁移剪除 `cp@30`；随后批内 `cp@30` 命中已终态实例 → no-op（诊断 `checkpoint_skipped_terminal`） | 30 | `[]` | COMPLETED / 1.0 | R2 | `txn_2`（**唯一**位置变更事务，恰在 t=30）；`evt_arrived`（`event_type="core.set_component"`，`logical_tick=None`（D-P2-18）） |
| A5 | `take_due` → None → **terminal**：`SchedulerOutcome(paused=False, pause_reason=PauseReason("terminal", tick=30), ticks_processed=30, transactions=(txn_2,), events=(evt_arrived,))`（按调用作用域 = 本 ff 调用，D-P3-18） | 30 | `[]` | COMPLETED / 1.0 | R2 | — |

分支 A 断言：`progress` 沿时序单调 `0.0 → 0.3333 → 0.4 → 0.6667 → 1.0`；位置组件恰在 `txn_2` 首次变为 dest；总事务数 = 2（`txn_1`@R1、`txn_2`@R2）；`act_1.result_summary["completed_at"] == 30`。

### 5.4 分支 B —— abort（中止，从 S8 暂停点分叉）

| 步 | 操作 | 时钟 | 队列 | act_1 | 世界 rev | 事务 |
|---|---|---|---|---|---|---|
| B1 | 玩家中止：`scheduler.abort_action(act_1)` → **INTERRUPTED→FAILED**（ABORTED，at_tick=12）：result_summary `{"reason": "aborted", "tick": 12, "progress": 0.4}`；终态迁移剪除 `cp@20`/`end@30` | 12 | `[]` | FAILED | R1 | — |
| B2 | `fast_forward`：`take_due` → None → terminal（时钟**停在 12**——中止后无调度工作，无时间推进） | 12 | `[]` | FAILED | R1 | 无（**到达 effect 永不提交**，M2） |

分支 B 断言：位置恒为起点；revision 停在 R1；`act_1.status is FAILED`；终态记录**保留**在 `runtime.active_actions[act_1]`（D-P3-08 可检查性，清理归 P8）。

### 5.5 三条"不得"的可测试表述（Plan §12 原文逐条 → 断言）

- **M1（不得 1：NPC 1 秒动作不强迫玩家每秒操作）**：fixture 追加 NPC `ent_npc`，动作 `npc.blink`（`duration_policy=fixed(1)`——剧本声明 1 秒 ≈ 1/60 min，子 tick 钳制为 1 tick + 诊断，D-P3-01）；NPC 策略在 t=0..199 每 tick 排一次 blink（**200 个队列条目**，区间含端点 199-0+1=200——该 fixture 数字全文唯一口径，§1.2 表同）。断言：(a) t<12 期间 `SchedulerOutcome.paused` 恒 False（一次 ff 直达 B1，NPC 活动零暂停）；(b) `ent_player` 的 `ActorWakeup`/`kind="wakeup"` 条目数 == 0；(c) 暂停前 NPC blink 已完成 ≥12 次（NPC 照常后台推进——"不强迫玩家"≠"NPC 冻结"）；(d) 全程玩家侧暂停恰 1 次（B1）。
- **M2（不得 2：不得以"position 直接设到终点"伪装长动作）**：断言 (a) S4/S7/A2 各观察点玩家位置组件恒为起点（world 读，非 trace 猜测）；(b) 首个也是唯一的位置变更事务 = 分支 A 的 `txn_2` @ t=30（单路，D-P3-27，由构造成立），且经完整管道（`outcome.trace_records` 含该 effect 的 `kind=authority_decision`/`validation_decision` 记录，且对应 `transaction` 记录 status 为 COMMITTED；TraceKind 词表 `trace.py:91-110`（`SYSTEM` 在 L110））；(c) 暂停点 `progress == 0.4` 而非 1.0（完成不可伪造）；(d) `progress_of` 为纯时钟推导——对同一 `ActiveAction` 伪造"更大 progress"存储值不影响后续派生（对抗探针：改副本存储值，重算恒等）。
- **M3（不得 3：不得用不可检查 coroutine 作为唯一 scheduler truth）**：断言 (a) **纯性**：同一 `(world, runtime)` 的 `deep_copy_via_roundtrip` 副本（serialization.py:135，走序列化 round-trip、**不经写屏障四逃逸路径**——武装态下 `__copy__`/`__deepcopy__`/`model_copy`/`model_construct` 抛 `WriteBarrierError`，reducer.py:1098-1105；无需开 `write_barrier_exempt()` 窗口（reducer.py:1065，仅受控例外备路），D-P3-11②）上两次 `fast_forward` → `SchedulerOutcome`（transactions/events/trace_records/transitions）逐项相等（逐事件比较键口径 D-P3-15①/D-P3-20；深拷贝口径 D-P3-11②）；(b) **快照等价**：S8 暂停点 `snapshot(world, runtime)` → `restore_snapshot` → 继续 ff（分支 A）→ 与无快照路径的逐事件键 `(event_type, world_revision, 事件发生刻)` 序列逐字一致（D-P3-15①；`event.logical_tick` 恒 None（D-P2-18），不入键）；(c) **静态**：七模块无 `asyncio`/`datetime`/`time`/`random` import（`test_import_boundary.py` P3 专项谓词仅作用于 7 个新模块，§6.4/§8.5-D4）；(d) `RuntimeState` 全部字段 `assert_json_clean` 通过（无 continuation/闭包可驻留——K7 的程序化表达）。

---

## 6. 测试规格（P3-T08，GFlash）

> 布局（P2 勘误 E4 沿袭）：全部位于 `tests/engine_v2/core/`。`conftest.py` 由 P3-T08 创建（§5.1 fixture 工厂：world/registry/triggers/authority_policy/boundary/scheduler 装配）；全部用例**无网络、无 LLM、无 API key**（stub hook/trigger 为纯 Python 函数，G3-5）。既有 1491 测试纯增量、**既有断言零修改**（G2 移交 5）；唯一触碰既有测试文件的是 §3.11 三锚点（两个 19 模块列表一行级元组修订 + 一个 `__all__` 196 规模锚点一行级修订）+ §6.4 P3 专项 import 黑名单作用域机制（多行结构性修订），均预披露（§8.5-D4/D5）。

### 6.1 每模块单测要点

- **`clock.py`**（`test_clock.py`）：`set_logical_tick` 向后 → `ClockRollbackError`（信息含 from/to）；`LogicalClock.of` 投影与 `logical_tick` 恒等；`advanced(0)/advanced(-1)`（后者抛）；`elapsed` 下界 0；`rebuild_runtime` 重跑键一致性 validator（构造 `active_actions` 键不符的输入 → `ValidationError`）；`LogicalClock`/`RuntimeState` round-trip 恒等（`dump_json`/`load_json`，tick 值保持）。
- **`event_queue.py`**（`test_event_queue.py`）：`make_scheduled_event` 词表外 kind → `QueueInvariantError`；逐 kind 缺必填 payload 键 → 抛（7 kind × 缺键矩阵）；`due_tick<0` → 抛；过去调度（`due_tick < clock`）→ 抛；`entry_id` 重复 → 抛；**同刻稳定 FIFO**：同 due_tick 依序入队 A,B,C → `take_due` 批序 A,B,C；交错入队（t=5, t=1, t=5）→ 队列 `[t1, t5(A), t5(B)]`（单键稳定排序）；`take_due` 抽整批（批后队列前移）；队列 `dump_json` round-trip：`sch_` 前缀重建、`assert_json_clean`、`==` 恒等（G3-2 单元层）。
- **`action_registry.py`**（`test_action_registry.py`）：`validate_arguments` 矩阵（缺必填 / 未知键 / `entity` 型给字符串 / `number` 越界 min/max / `enum_values` 不匹配 → 各自 issue 串）；未注册 `action_id` → `UnknownActionError`；`resolve_duration`（fixed 直出 / hint 缺失 → None / `hint_scale×30` 取整 / 结果 0.2 → 钳 1 + 诊断 / none → None）；`validate_timing`（deadline < earliest → issue；hint 0 → issue）；registry 键一致性（`spec.action_id != key` → 构造期拒绝）；`ActionRegistry` round-trip 恒等。
- **`action_lifecycle.py`**（`test_action_lifecycle.py`）：**迁移矩阵全表**——6 状态 × 9 事件 = 54 格，逐格断言"期望目标态"或 `IllegalTransitionError`（信息含 from/to/event）；不存在实例 → 抛；`progress_of`（`expected_end_tick=None` → None；单调；`clock > end` → clamp 1.0；伪造存储 progress 不影响推导）；`apply_checkpoint`（progress 重算 + `next_checkpoint_tick` 前进 + 下刻入队 + base re-anchor + **无世界事务/revision 不变**）；`start_action`（两跳复合返回 2 条记录 VALIDATION_ACCEPTED + SCHEDULED，D-P3-19 + 三类队列条目入队 + 开始无 effect）；`resume_action`（start_tick/expected_end 不变 + re-anchor + 不重复入队已有 checkpoint）；`abort_action`/`fail_action`（result_summary 字段 + 终态剪除队列条目）；`complete_action`（纯函数只出 effect 不写世界——世界侧由 scheduler 测试覆盖）。
- **`interrupt.py`**（`test_interrupt.py`）：4 内置 kind 逐 kind 命中/不命中各一（`event_type` 匹配 `DomainEvent.event_type`——本刻事件流含触发器 effect 类型事件即命中，D-P3-17；`world_variable` gt/eq；`entity_component` field_path 取值；`time` gte 边界 `==` 命中，显式传 `tick` 的命中/不命中各一（D-P3-21））；未知 kind 且未注册 resolver → `UnknownConditionError`；命名 resolver 注册后生效（扩展位可用）；**阻塞规则**（D-P3-10）：同一定时边界，`actor ∈ player_actor_ids` → `player_blocking=True`，`actor ∉` → False 且入 `npc_notices`，scheduler 对 `report.npc_notices` 逐 `(boundary_id, actor_id)` → `enqueue_actor_wakeup`（§2.4 伪代码 npc 分支，F3-04）：`actor_wakeups` +1 条且同刻入队一条 `kind="wakeup"` 队列条目（两条记录 (actor_id, due_tick) 一致，payload 仅 actor_id、reason 不入 payload，§2.5 尾注）；`interrupt=False` 的边界不中断行动（仍 fired）；`scheduled` 边界 `due_tick > tick` 不参评；`evaluate_boundaries` 注册序稳定（两边界同刻命中 → fired 序 = 注册序）；**非阻塞 NPC 中断（D-P3-25）**：NPC 边界（actor ∉ `player_actor_ids`）`interrupt=True` 命中 ACTIVE interruptible 行动 → 迁 INTERRUPTED 不暂停；其后 checkpoint 刻 `fast_forward` 不抛错（守卫 no-op，§3.6），诊断 `checkpoint_skipped_interrupted` 唯一且入 `outcome.trace_records`，簿记确定（收敛 = actor wakeup 重新提案，P4/P5 范围）。
- **`revalidation.py`**（`test_revalidation.py`）：`base == current` → ACCEPT；`base < current` → REJECT `stale_revision`（details 含两 revision 值）；`current == valid_until` → 不陈旧（ACCEPT，`revision.py:82` 口径边界）；`current > valid_until` → REJECT `valid_until_expired`；两条件同时满足（`base<current` ∧ `current>valid_until`）→ 报 `valid_until_expired`（F2-05 过期优先，§3.9 步骤 1）；actor 缺失 → REJECT `actor_missing`；`actor_alive_check` 假 → REJECT `actor_not_alive`；`allow_rebase=True` + actor 存活 → REBASE 且 `rebased_proposal.base_world_revision == current`、其余字段逐字保持；`actor_state_revision` 陈旧 → 仅 details 诊断不 REJECT（D-12 口径）；**单一实现**：`revalidate_proposal` 对 NPC/LLM/玩家三类 `provenance` 行为一致（producer 无关断言）；effect 侧复用探针：构造 stale effect 批 → `check_transaction_references`（P2）报 `stale_revision` 与 P3 提案级 REJECT 口径一致（`is_stale` 单源）；**REPAIR 范围口径（R4/E-P3-26）**：P3 测试**不得把结果域钉死为三值集合**（不得断言 结果域 == {accept,rebase,reject} 为词表不变量）；REPAIR 范围见 §3.9 声明。
- **`scheduler.py`**（`test_scheduler.py`）：**R1 回归（F2-06，断言时刻前置条件成立）**：负例在**未武装环境**（新进程；测试先断言 `write_barrier_installed() is False`）执行 → `Scheduler(assert_barrier_armed=True)` → `SchedulerConfigurationError`（检查为 `__init__` 第一步、未武装不构造执行器，§3.8/F2-06）；正例：conftest 预武装后构造成功且套件全生命周期 `write_barrier_installed() is True`（武装态不卸载，D-P3-11②）；**权威装配（D-P3-23）**：`authority_policy` 缺参 → `TypeError`（必填构造参数）；空 rules（closed-by-default）下任何世界写入 → authority 阶段 DENY（无 txn、诊断可查）；§5.1 型显式授予面 → `create_entity`/`set_component` 可提交；**触发器点名映射（D-P3-26/R4）**：`named_triggers` 缺参 → `TypeError`（必填构造参数，与 `authority_policy` 同口径）；空集 → 无命名触发器可点名，`kind="event"` 仅 effects 形态可用、`trigger_id` 形态（不可解析）→ `QueueInvariantError`（§3.8/§3.10 口径）；§5.1 fixture 装配口径（R5/D-P3-27）：`trigger_registry` = 显式空注册表（装配断言 `trigger_ids()` 为空）、`named_triggers` 两 stub 为点名求值唯一数据来源——Gate 场景世界 effect 产出走单路，级联回合再求值零新事务（由构造成立）：§5.2 S8 `transactions=(txn_1,)`、G3-1 分支 A 总事务数 = 2 逐行成立（E-P3-24/E-P3-30）；`trigger_registry=None` 缺省行为（cascade.py:852：等价空注册表——点名求值正常、注册表再求值面空、无 `trigger_output_dropped`）；**producer 口径（D-P3-11 统一，F2-01）**：完成 effect 的 producer = 触发器注册时声明的 producer（fixture `origin_scenario`），P3 effect 侧不引用 `spec.executor` 字段；`fast_forward` 空队列 → terminal（时钟不动）；**未响应暂停幂等重报（D-P3-24）**：blocking 边界暂停后不调 resume/abort 直接再 `fast_forward` → 返回同一暂停（`paused=True`、同 `boundary_id`、`tick`/`ticks_processed` = 当前 logical_tick）、时钟/队列不变、零 events/transactions/transitions/errors（入口首检纯派生，重入零副作用）；显式 abort 后规则自动失效（后续 ff 正常推进）；**边缘探针（D-P3-24⑥，R5/F4-02）**：玩家 blocking 边界命中但无行动进入 INTERRUPTED（无活动行动 / `interruptible=False`）→ 首次 ff 暂停一次（fired 记录 + trace 留痕）、第二次 ff 正常推进（一次性事件、不重报）；**`pause_on_player_boundary=False` 探针（R5/F4-03；R6/F5-03 record-only，E-P3-36）**：§5.1 同 fixture 仅 `time_policy=TimePolicy(checkpoint_interval_ticks=10, pause_on_player_boundary=False)` → t=12 B1 命中：边界 fired（`report.fired` 非空 + trace 留痕）、act_1 仍 ACTIVE（无 INTERRUPTED）、不返回暂停 → cp@20 正常处理（progress = 20/30 = 0.6667）→ end@30 正常处理 → act_1 COMPLETED（`completed_at==30`）、队列耗尽、ff 推进至 terminal、全程 `paused` 恒 False、D-P3-24 入口重报不生效（无 INTERRUPTED 背书）；G3-1（True 路径）17 条断言全部不变（本探针为独立 fixture 变体，不动主场景）；**scheduled 边界播种（D-P3-22）**：scheduled 边界刻到 → 时钟停在其刻并参评（边界 fired）；重复 `fast_forward` 不重复入队（`boundary_id` 去重、幂等）；`max_tick` 边界（批 due > max_tick → `PauseReason("bounded")`，队列保留）；`step()` 单批 + 强制暂停；**outcome 按调用聚合（D-P3-18）**：两次连续 ff 的 outcome.transactions/events 各自只含本调用提交（不累计）；**刻原子性**：wakeup hook 在刻中抛错 → 返回刻前状态对（world/runtime 与入参 `==`），`SchedulerWakeupError` 携带 actor_id，且返回 `SchedulerOutcome(paused=False, pause_reason=None, ticks_processed=<刻前 logical_tick>, 空 transactions/events/transitions, 非空 errors)`（原子刻错误路径口径，F2-03，§3.8 `fast_forward` docstring）；`submit_proposal` REJECT 路径（FAILED 轨迹 + 诊断，无崩溃）；`resume_action`/`abort_action` 从非 INTERRUPTED 态调用 → `IllegalTransitionError`；`enqueue_actor_wakeup` 双记录 (actor_id, due_tick) 一致（payload 仅 actor_id、reason 不入 payload，§2.5 尾注）；`scheduler_fingerprint`（同 (registry, time_policy, boundaries) 恒等 / 三项各篡改一字段变指纹——三条探针，与 G3-4(d) 同口径，R7-S4 补充2）。

### 6.2 G3 端到端断言清单（Plan §12 G3 五条逐条可执行化）

| # | G3 判据 | 测试 | 断言（可执行口径） |
|---|---|---|---|
| G3-1 | 场景精确通过 | `test_gate_scenario_travel_interrupt`（§5.2 全表） | §5.2 暂停点 9 条断言 + 分支 A 4 条 + 分支 B 4 条（§5.3/§5.4）= **17 条列举断言**（D-P3-19 计数口径），全部精确值断言（== / is / 列表恒等），无近似容差 |
| G3-2 | scheduler queue 可 serialize | `test_queue_serialization` | `dump_json(runtime)` → `assert_json_clean` → `load_json` 重建 `RuntimeState`：`scheduler_queue` 逐条目 `==`（含 `entry_id` 前缀 `sch_` 类型保持）；`active_actions`/`actor_wakeups`/`logical_tick` 同步恒等；恢复态上继续 ff 与原始态 ff 事件序列一致 |
| G3-3 | interruption 后 progress 正确 | `test_progress_across_interrupt` | 暂停点 `progress == 12/30`；resume 后 checkpoint 序列 `0.4 → 0.6667 → 1.0` 单调；中止分支 `result_summary["progress"] == 0.4` 且终态记录保留；snapshot round-trip 后 progress 重算恒等（不依赖存储值） |
| G3-4 | replay event order 一致 | `test_replay_determinism` | (a) 同 (snapshot, config, 提案流) 两次运行（各从同一快照产物 restore 起步；武装态副本经 `deep_copy_via_roundtrip`（serialization.py:135），不开 `write_barrier_exempt()` 窗口，D-P3-11②）→ 逐事件键 `(event_type, world_revision, 事件发生刻)` 序列相等（D-P3-15①/D-P3-20）且 tick 水位（`ticks_processed`）相等；(b) t=12 暂停点 snapshot/restore/继续 → 与无快照路径逐字一致（同键口径）；(c) CommittedEffect 序列取自 `outcome.transactions[i].effects`（D-P3-18）经 `apply_committed_effects`（`reducer.py:843`）回放 → 同一 `WorldState`（revision 值 + 组件值）；(d) `registry`/`TimePolicy`/`boundaries` 各篡改一字段 → `scheduler_fingerprint` 不等 → 回放显式拒绝（不静默；三条探针，输入面含 boundaries，R7-S4 补充2/E-P3-39③） |
| G3-5 | no LLM required | 全部 P3 测试 | stub `WakeupHook`/`CascadeTrigger`/`actor_alive_check` 为纯 Python 函数；**P3 新增测试文件全量集合**无 provider/llm import——9 个 `test_*.py`（`test_clock`/`test_event_queue`/`test_action_registry`/`test_action_lifecycle`/`test_interrupt`/`test_revalidation`/`test_scheduler`/`test_p3_gate_scenario`/`test_p3_adversarial`）+ `conftest.py`，机械口径 = `test_import_boundary.py` 新增 `P3_TEST_FILES` 元组（10 个新增测试文件逐一列举）逐文件核验（与 `P3_SUBMODULES` 同按集合分流的作用域机制，§6.4/§8.5-D4 预披露结构性修订；替代原稿"ruff + 人工清单"口径——ruff 规则粒度无法表达 provider/llm 名称黑名单，备选弃用）；场景在零网络（pytest 进程无 socket 依赖）下完整跑通 |

### 6.3 对抗方向清单（`test_p3_adversarial.py`，8 类）

- **A1 —— fast-forward 后的 stale 提案**：`P1`（base R0）提交前，先经其他事件把世界推到 R5（**5 个** encounter 类事件提交——`INITIAL_WORLD_REVISION=Revision(0)`（revision.py:70）+ 每次 commit 恰 +1（`transaction_executor.py:227-228`）→ R5，与"revision 停在 R5"自洽，F2-05）；再 `submit_proposal(P1)`（无 `valid_until`）→ REJECT `stale_revision`；断言：`act_1` 不进入 ACTIVE、`pending_proposals` 仍含该提案（REJECT 留痕 = 仍在列表 + `RevalidationDecision` REJECT 记录，F2-12）、世界零额外变更、revision 停在 R5。变体：`valid_until=R4` 提前过期（`base<current` 与 `current>valid_until` 同时满足）→ REJECT `valid_until_expired`（F2-05 过期优先规则，§3.9 步骤 1）。
- **A2 —— 中断/恢复/中止边界矩阵**：非法迁移探针集：COMPLETED→RESUMED、FAILED→RESUMED、ACTIVE→ABORTED（表外）、INTERRUPTED→INTERRUPTED（双中断）、resume 后 abort（合法路径对照组——合法序列以 `LIFECYCLE_TRANSITIONS` 为唯一权威：resume → 再中断 → abort（ABORTED 边仅出自 INTERRUPTED；ACTIVE 无直接 ABORTED 边，表外探针已单列））——逐格 `IllegalTransitionError`（信息含 from/to/event）或期望迁移；终态后一切操作 no-op 拒绝。**非阻塞 NPC 中断方向（D-P3-25）**：NPC 边界（actor ∉ `player_actor_ids`）`interrupt=True` 命中 ACTIVE interruptible 行动 → 该行动迁 INTERRUPTED（不暂停、时钟继续）；其后 checkpoint 刻 `fast_forward` 不抛错（`apply_checkpoint` 守卫 no-op，§3.6），发出唯一诊断 `checkpoint_skipped_interrupted` 入 `outcome.trace_records`，簿记确定（收敛路径 = actor wakeup 重新提案，P4/P5 范围）。
- **A3 —— 同刻事件序**：三个 producer 同刻（t=5）各排一个 `kind="event"`（批内序 A,B,C 由入队序定）；另在 t=5 批处理中由 trigger 派生新 `due_tick=5` 条目 D → D 排批尾（A,B,C,D）；断言处理序与 `outcome.trace_records` 序（追加序，D-P3-18）逐字一致、两次运行恒同（逐事件键 D-P3-15①）。
- **A4 —— 回放确定性**：分支 A 全跑一遍取事件键序列 E1；t=12 暂停点 snapshot → restore → 续跑取 E2；另独立进程（新 fixture）重跑取 E3；断言 E1 后缀 == E2 == E3（D-P3-15① 逐事件键序列 + tick 水位；uuid4 标识按数量/唯一性/前缀/位置同构比较，D-P3-20）。
- **A5 —— 未注册动作**：提案 `action_id="flying"`（未注册）→ `UnknownActionError` 被 `submit_proposal` 捕获转为 FAILED 轨迹（result_summary `reason="unknown_action"`）；断言无崩溃、队列零残留、世界零变更、诊断串含 action_id。
- **A6 —— 非法迁移**：直调 `transition_action(runtime, act_1, LifecycleEvent.RESUMED, …)` 于 PROPOSED 态 → `IllegalTransitionError`；`updates` 携带冻结契约外字段名 → `ValidationError`（rebuild 走 `model_validate`，`extra=forbid`）——双防线均断言。
- **A7 —— 边界无响应者**：B1 命中暂停后，**不**调用 resume/abort，直接对暂停态再 `fast_forward`：入口首检命中（act_1 INTERRUPTED + B1 blocking + `ent_player` ∈ `player_actor_ids`，D-P3-24）→ 断言返回同一暂停结果（`paused=True, boundary B1, tick=12`，`ticks_processed=12`，`transactions`/`events`/`transitions`/`errors` 全空）——时钟**不前进**、队列不变（`[cp@20, end@30]`）、不静默跳过边界、不崩溃（幂等可检查）；显式 abort 后规则自动失效、世界方可继续（B 分支）。
- **A8 —— 时钟/队列不变量**：`set_logical_tick` 回退 → `ClockRollbackError`；`enqueue` 过去刻/负刻/重复 entry_id/词表外 kind/payload 缺键 → `QueueInvariantError`（5 探针）；`due_tick` 跳变后 `next_due_tick` 与队列最小值恒等（不变量探针）。

### 6.4 复跑口径（与 G2 一致）

`.venv/bin/python -m pytest tests/ -q`（1491 既有 + P3 新增全绿）、`.venv/bin/python -m ruff check src/engine_v2 tests/engine_v2`（clean）；`test_import_boundary.py` 口径：B1 静态扫描（`CORE_DIR/*.py` 全部文件）继续施加**既有三类全局谓词**（provider SDK / v1 包 / 网络进程 IO），保持不变；P3 专项黑名单（`datetime`/`time`/`random`/`asyncio`）**仅作用于 7 个新模块**——可执行机制 = 该文件新增 `P3_SUBMODULES` 元组（7 个 P3 模块名）+ 仅对该集合文件生效的 P3 专项谓词（按模块分流的作用域实现，谓词结构多行修订）+ 同文件新增 `P3_TEST_FILES` 元组（10 个 P3 新增测试文件逐一列举：9 个 `test_*.py` + `conftest.py`），P3 新增测试文件无 provider/llm import 逐文件核验（G3-5 机械口径，与 `P3_SUBMODULES` 同作用域机制，替代原稿"ruff + 人工清单"口径）；B2 运行时扫描（fresh import 后 `sys.modules` 增量）维持原三类谓词——3 个 P1 冻结模块（`trace.py:46`/`events.py:36`/`snapshot.py:44`）已含 `from datetime import datetime`（诊断性 `wall_time`，P1 铁律 3，字节冻结不可改源），属**预期带入、不判违规**。此结构性测试修订为预披露（多行、非一行级）：列入 P3-T08 写入白名单（§3.10）、Gate 报告偏差登记披露（与 D-P3-12 同披露模式，§8.5-D4）。

---

## 7. G3 判据映射表（Plan §12 G3 五条 → 实现点）

| G3 判据（原文） | 机制 | 实现/测试落点 |
|---|---|---|
| 场景精确通过 | §5.2 主时序 + §5.3/§5.4 分支 A/B 的逐步时钟/队列/迁移/事务/revision 状态表 | P3-T08 `test_gate_scenario_travel_interrupt`（G3-1，§6.2：17 条精确断言，列举口径 9+4+4，D-P3-19）；状态机迁移表 D-P3-07、progress 推导 D-P3-08、fast-forward §2.4 |
| scheduler queue 可 serialize | 队列条目 = P1 冻结 `ScheduledEvent`（`state.py:143`），序列化走 P1 `serialization.py` 唯一出入口（`dump_json`/`load_json`/`assert_json_clean`） | `event_queue.py`（§3.4）+ G3-2 `test_queue_serialization`（§6.2）；单元层 round-trip 口径见 §6.1 `event_queue` 末条 |
| interruption 后 progress 正确 | progress 由时钟纯推导（D-P3-08）；INTERRUPTED 保留 `start_tick`/`expected_end_tick`；RESUMED 边连续（D-P3-07） | §5.2 S7（progress==12/30）+ §5.3 A1（resume 不重置）+ G3-3 `test_progress_across_interrupt`（§6.2） |
| replay event order 一致 | 五要素确定性论证（§2.4）+ 快照复用 P1 `Snapshot`（D-P3-15）+ `scheduler_fingerprint` 配置同构校验 + outcome 承载级联完整产出（D-P3-18） | G3-4 `test_replay_determinism`（§6.2，逐事件键 D-P3-15①/D-P3-20 + `apply_committed_effects` 事务回放路径，CommittedEffect 取自 `outcome.transactions[].effects`）；对抗 A3/A4 加固（§6.3） |
| no LLM required | import 边界（core 无 provider/llm 依赖，G2 静态核查机制沿用）+ stub hook/trigger 全纯 Python | G3-5（§6.2）：全部 P3 测试零 provider import、零网络；`WakeupHook` Protocol 留 P4 真策略接缝但不依赖之 |

---

## 8. 约束符合性自查

### 8.1 P1 零改动（G2 移交 4；基线 `603535e`）

P3 对 13 个冻结契约模块**零源改动**。逐字段复用对齐表（"零改名零新增"的可检查声明）：

| P1 冻结物 | P3 消费方式 | 改动 |
|---|---|---|
| `ActiveAction` 14 字段（`actions.py:231-244`） | 生命周期迁移/progress/checkpoint/re-anchor/resume 全部经 `updates` 重建写回既有字段 | 0 |
| `ActionProposal` 13 字段（`actions.py:174-188`） | `submit_proposal`/revalidation 全字段消费（`base_world_revision` 必填口径、`valid_until` 经 `is_stale` 消费） | 0 |
| `ActionLifecycleStatus` 6 值（`actions.py:191-204`） | 迁移表状态集 = 该枚举全集（D-P3-07） | 0 |
| `ActionTiming` 3 字段（`actions.py:129-131`） | `validate_timing` + `resolve_duration` 消费 | 0 |
| `ScheduledEvent` 4 字段（`state.py:152-155`） | kind 词表/payload 契约填进既有 `str`/`dict` 开放度（D-P3-04） | 0 |
| `ActorWakeup` 3 字段（`state.py:164-166`） | `enqueue_actor_wakeup` 写入，与 `kind="wakeup"` 条目 (actor_id, due_tick) 一致（payload 仅 actor_id、reason 不入 payload） | 0 |
| `RuntimeState` 11 字段（`state.py:217-227`） | `logical_tick`（时钟唯一权威）、`scheduler_queue`、`active_actions`、`actor_wakeups`、`pending_proposals` 全消费；`active_modes`/`mode_context`/`backend_refs`/`rng_state` 不读不写（P4/P5/P8 域） | 0 |
| `RuntimeLifecycle` 5 值（`state.py:115-127`） | `STEPPING` 语义由 `Scheduler.step()` 承载（值本身不改） | 0 |
| `Revision`/`is_stale`/`RevalidationOutcome`（`revision.py`） | revalidation 单源口径（D-P3-16 ② 复用 P1 四值词表、不新增类型） | 0 |
| `ScheduledEntryId`（`sch_`）/`ActionInstanceId`（`act_`）/`ProducerId`（`ids.py`） | 条目/实例签发、producer 名字复用既有前缀体系 | 0 |

P3 新类型（`LogicalClock`/`ParameterSpec`/`DurationPolicy`/`ActionSpec`/`ActionRegistry`/`InterruptCondition`/`DecisionBoundary`/`BoundaryReport`/`RevalidationDecision`/`TimePolicy`/`PauseReason`/`SchedulerOutcome`/`LifecycleTransition` 等）**全部落 7 个新文件**，不进任何 P1 文件；`ActionSpec` 等与 P1 `actions.py` 的分工 = 类型词表（P1 数据）vs 注册语义（P3 行为），同 P2"契约/行为分文件"纪律（D-P2-02）。

### 8.2 `__all__` 纯增量（196 → 249）

新增 53 符号（§3.11 逐模块计数：clock 6 / event_queue 5 / action_registry 7 / action_lifecycle 12 / interrupt 10 / revalidation 3 / scheduler 10）；既有 196 成员零删零改；字母序插入；closeout **三锚点**（两个 19 模块列表：`test_closeout.py::_CORE_SUBMODULE_NAMES` L92 / `test_import_boundary.py::CORE_SUBMODULES`，19→26；一个规模锚点：`test_closeout.py` L184 含注释块，196→249）一行级机械修订（D-P3-12，已知披露偏差模式，P2 D-P2-19 先例，§3.11/§8.5-D5）。

### 8.3 无 LLM / 无网络 / 无 wall clock

- **import 边界**（`test_import_boundary.py` AST + fresh-import 扫描）：core 七模块只 import stdlib + pydantic + 同包 `src.engine_v2`；既有三类全局黑名单（provider SDK / v1 包 / 网络进程 IO）对 core 全部文件不变；P3 专项黑名单 `datetime`/`time`/`random`/`asyncio` **仅作用于 7 个新模块**（作用域机制：`P3_SUBMODULES` 元组 + 按模块分流谓词，B2 运行时增量维持三类、`datetime` 由 3 个冻结模块带入属预期——§6.4；预披露的结构性测试修订——多行、非一行级，§8.5-D4）。
- **墙钟排除的结构性理由**：时钟唯一写点 `set_logical_tick`（单调、逻辑值）；暂停不消耗逻辑时间（§2.3）；`RngState`（`state.py:130-140`）为唯一随机性载体且 P3 核心不消费（触发器如用随机须显式经 `rng_state` 更新，归 P5 触发器实现，测试口径：P3 套件全程零随机调用）。
- **LLM 排除**：`WakeupHook` 是 Protocol 接缝（P4 实现 LLM policy），P3 自身与全部测试只用 stub（G3-5）；提案的 LLM 来源在 P3 视野外——`ActionProposal.provenance`（P1 K6）保留溯源，revalidation 对 producer 无关（§6.1 `revalidation` 末条）。

### 8.4 G2 移交六条逐条对应（`docs/v2/gates/G2-gate-report.md` §7）

| # | G2 移交原文要点 | P3 对应 |
|---|---|---|
| 1 | 武装入口：P3 调度器统一经 `CascadeExecutor`；R1 加固（恒武装断言）随装配落地 | D-P3-11：fast-forward 全部世界写入经 `CascadeExecutor`（武装点 `cascade.py:810` 不变）；`Scheduler.__init__(assert_barrier_armed=True)` → `write_barrier_installed()`（`reducer.py:1150`）假即 `SchedulerConfigurationError`；回归测试见 §6.1 `scheduler` 首条 |
| 2 | guard 语义：producer/trigger 只获 `guard(state)` 视图；跨 commit 持 guard 不反映新状态 → P3 每轮重新 guard | D-P3-11 落点 3：刻后求值与 hook 入参一律**当刻**新 `guard(world)`（`reducer.py:1590`）；禁止跨刻复用 guard token（测试：§6.1 `scheduler` 刻原子性用例覆盖视图新鲜度） |
| 3 | 提交协议：状态变更全走管道；P3-T07 revalidation 复用 `check_transaction_references` 与 L1/L2，不另起校验源 | D-P3-11 落点 1 + §3.9：提案级 = `revalidate_proposal`（`is_stale` 单源，`revision.py:78`）；effect 级 = P2 L1（`validation._stage_staleness`）+ L2（`check_transaction_references`，`validation.py:857`）原样复用，P3 零新校验源 |
| 4 | P1 冻结：13 模块字节级冻结；`__all__` 196 纯增量 | §8.1 对齐表 + §8.2 |
| 5 | 测试基线 1491 / ruff clean；P3 纯增量、既有断言零修改 | §6 开头（既有断言零修改；唯一触碰既有测试文件的是 §3.11 三锚点（两个 19 模块列表 + 一个 `__all__` 196 规模锚点，一行级修订）+ §6.4 P3 专项黑名单作用域机制（多行结构性修订），均预披露机械修订，§8.5-D4/D5） |
| 6 | G0 遗留（T04 真 LLM 转录待 API key）非阻塞 | 与 P3 零依赖（§8.3：P3 全链路 no LLM） |

### 8.5 披露偏差清单

| # | 偏差 | 性质与裁定 |
|---|---|---|
| D1 | 任务书预期"ScheduledEvent 新类型"；P1 已在 `state.py:143` 冻结 `ScheduledEvent`（+ `ids.py:171` `sch_`），新类型与冻结字段 `scheduler_queue: list[ScheduledEvent]` 类型冲突 | **澄清性偏差**（非 Spec/计划矛盾）：P1 零改动为最高约束，P1 docstring 原文已把 kind 词表决定权让渡 P3 → 采用 D-P3-04 复用方案；若任务书坚持新类型，须先经 Gate 解冻 P1（Plan §10 口径），P3 不建议 |
| D2 | Spec §11.4"建议"状态机无 `INTERRUPTED→ACTIVE` 返回边；Plan §12 Gate 要求 resume | **Spec"建议"级 vs Plan Gate 级**：Plan Gate 为 G3 判据来源（更高执行效力）→ 新增 RESUMED 边（D-P3-07）；P1 枚举含 INTERRUPTED 态，无冻结物被改。已在 §4-D-P3-07 留痕，Gate 报告可复核 |
| D3 | 子 tick 动作（如 NPC 1 秒动作）钳制为 1 tick：Spec 未规定亚 tick 处置 | **补充规则**（非矛盾）：事件驱动模型下无亚 tick 表达位（全冻结字段 int tick）；钳制 + 诊断（D-P3-01/§3.5）保持"不得 1"可执行化（M1 的 fixture 恰用此规则） |
| D4 | `test_import_boundary.py` 的 B1/B2 为全包单一谓词，P3 专项黑名单（`datetime/time/random/asyncio`）须限定作用于 7 个新模块；3 个 P1 冻结模块（trace/events/snapshot）已 import `datetime`（诊断性 `wall_time`，P1 铁律 3，字节冻结不可改源）→ 全包"一行级"扩展将击碎 1491 基线，原稿"若现有规则结构无需改动则此项不触发"兜底不可达 | **预披露的结构性测试修订**（多行、按模块分流的作用域实现，非一行级）：`test_import_boundary.py` 新增 `P3_SUBMODULES` 元组 + 仅对该集合文件生效的 P3 专项谓词 + `P3_TEST_FILES` 元组（10 个新增测试文件列举，G3-5 逐文件核验口径，同作用域机制）；B1 既有三类全局谓词（provider SDK / v1 包 / 网络进程 IO）保持不变；B2 维持三类谓词（`datetime` 由既有冻结模块带入属预期、不判违规）；3 个冻结模块保留诊断性 `datetime` import、不受 P3 专项约束；列入 P3-T08 写入白名单（§3.10）、Gate 报告偏差登记披露（与 D-P3-12 同披露模式，§6.4） |
| D5 | `test_closeout.py` L184 规模锚点硬断言 `assert len(core_pkg.__all__) == 196`（含注释块 L164-183）与 P3 `__all__` 196→249 冲突 | **预披露的规模锚点机械同步**（与 19→26 模块清单同类：一行级机械同步，含注释块，非 BLOCK、非结构性修订）：§3.11 三锚点之 ③（D-P3-12 锚点清单）；列入 P3-T01 写入白名单（§3.10）；R3 盲审补录（E-P3-17）——R2 时点口径为"两锚点"（E-P3-10 ④ 留痕，不回改） |

---

## 9. 勘误

> 沿用 P2 约定（`P2-kernel-pipeline-design.md` 勘误节首注）：本章节为**纯追加**，不改动上文既有正文；正文与本勘误不一致处，以本勘误为准。P3 补充开发/G3 门禁若产生机制变更，按 `E1`/`E2`/… 编号追加于此，并同步 Gate 报告摘录（P2 E5 先例）。

以下 E-P3-01 ~ E-P3-10 为 R2 盲审（Leader 合并清单 F-01 ~ F-15）落定的勘误条目；E-P3-11 ~ E-P3-23 为 R3 盲审（Leader 合并清单 F2-01 ~ F2-16）落定的补充勘误条目（F2-01~F2-04 单列，F2-13~F2-16 合并一条）；E-P3-24 ~ E-P3-29 为 R4 盲审（Leader 核验清单 F3-01 ~ F3-06 + 轻量项 L3-01 ~ L3-07）落定的补充勘误条目（F3-01~F3-05 单列——E-P3-24 含 L3-01 留痕，L3 轻量项与 F3-06 合并为 E-P3-29 一条，列明覆盖项）；E-P3-30 ~ E-P3-32 为 R5 盲审（Leader 核验清单 F4-01 ~ F4-03 + 轻量项 L4-01）落定的补充勘误条目（F4-01、F4-02 单列，F4-03 与 L4-01 合并为 E-P3-32 一条，列明覆盖项）；E-P3-33 ~ E-P3-36 为 R6 盲审（Leader 核验清单 F5-01 ~ F5-03 + 轻量项 L5-01）落定的补充勘误条目（L5-01 单列为 E-P3-33 轻量注记——就地更正 E-P3-32②(b) 的 ids.py 工厂组区间；F5-01 ~ F5-03 单列为 E-P3-34 ~ E-P3-36，其中 E-P3-36 重裁 E-P3-32① 的中断部分、留痕）；E-P3-37 ~ E-P3-39 为 R7 盲审（收尾轮，Leader 核验清单 F7-01 ~ F7-06 + R7-01 ~ R7-05）落定的补充勘误条目（F7-01 单列为 E-P3-37——就地更正 D-P3-20 理由段 ids.py 工厂区间、取代 E-P3-21/E-P3-33 该处裁定；F7-04 单列为 E-P3-38——F2-15 `causal_root_id` 偏离披露；F7-02/F7-03/F7-05/F7-06 与 R7-01 ~ R7-05 合并为 E-P3-39 一条，列明九项覆盖项）。每条给出**内容**（原稿错在何处、现正文已改为何口径）与**原因**（代码/契约依据 + 盲审出处槽位-项号）。正文相应位置已同步修改，两处若仍冲突，以本勘误为准（同条内 R4 注优先于 R3 原文）。

### E-P3-01（BLOCK，F-01）中断条件虚构字段 `event_kind` → `event_type`
- **内容**：原稿 C1 中断条件写作 `kind="event_kind"`（parameters 取 `event_kind`），且示例载荷命名沿用 `kind=encounter` 一类词汇；§3.7 `CONDITION_KINDS`、§5.1 fixture、§5.2 S6/S7、§6.1 相应行同步纠正为 `kind="event_type"`、`parameters={"event_type": "core.create_entity"}`，"encounter" 语义仅保留在触发器 id `scenario.encounter_12` 与事件名 `ev_enc` 的命名层（D-P3-17）。
- **原因**：P1 冻结事实——`DomainEvent`（`events.py:131-141`）**没有 `kind` 字段**，判别字段为 `event_type`；`transaction_executor.py:146` 以 `event_type=effect.effect_type` 构造事件；reducer effect 词汇表全部 `core.*`（`reducer.py:216-222`，7 类，含 `core.create_entity`）。`event_kind`/`encounter` 不存在于任何 P1 契约，照原稿实现必然 AttributeError 或永不命中。

### E-P3-02（BLOCK，F-02）SchedulerOutcome 字段集错误 → 按调用聚合、对齐 CascadeResult 的完整字段集
- **内容**：原稿 `SchedulerOutcome` 缺 `events`/`trace_records`、`transactions` 语义不明、含计数字段 `events_processed`、聚合范围未定义；现正文 §3.8 改为：`transactions: tuple[Transaction, ...]`（含 ABORTED、提交序）、`events: tuple[DomainEvent, ...]`（与已提交 effect 1:1）、`trace_records: tuple[TraceRecord, ...]`（本次调用产生）、`ticks_processed: int`（= 本次调用达到的 tick 水位 = 结果 RuntimeState.logical_tick）、`transitions: tuple[LifecycleTransition, ...]`（仅本次调用记录）、`errors`；`events_processed` **删除**（计数即 `len(events)`，D-P3-18）。§5.2 S8、§5.3 A5 等示例行同步。
- **原因**：P2 事实——`CascadeResult`（`cascade.py:678-702`）为 `final_state/transactions/events/trace_records/deferred/diagnostics`，`events` 与已提交 effect 1:1、`transactions` 含 ABORTED；`commit_transaction`（`transaction_executor.py:162-173`）返回元组。原稿字段集与 P2 出口对不齐，G3-4 逐项相等比对（M3）无对象可比；`events_processed` 计数与 `len(events)` 冗余且诱导"全局累计"误读（A5 `transactions=[txn_2]` 实际是按调用聚合，原稿未声明）。

### E-P3-03（F-09）事件 `logical_tick` 归属口径 → 恒为 `None`，发生刻由位置承载
- **内容**：原稿 §5.2 S6 / §5.3 A4 等行给事件标 `logical_tick=12`/`logical_tick=30`；现正文改为：经 `CascadeExecutor` 产出的 `DomainEvent.logical_tick` **恒为 `None`**（§2.3 末条、S6、A4 行），"事件发生刻"由该事件在本次调用 `outcome.events` 元组中的位置（提交序）+ `ticks_processed` 水位承载；跨运行可比对键改为逐事件 `(event_type, world_revision, 事件发生刻)`（D-P3-20，G3-4 判据同步，D-P3-15① 重写）。
- **原因**：P2 事实——`CascadeExecutor.run`（`cascade.py:867-874`）无 tick 参数、内部 commit（`cascade.py:1171-1180`）不传 `logical_tick`，代码注释明确 `logical_tick=None`（`cascade.py:103`，D-P2-18）。原稿标注与冻结代码行为直接矛盾；uuid4 生成的 `event_id/transaction_id` 跨运行不可等值比对（`ids.py:232-234`（`new_event_id`）/ `ids.py:237-239`（`new_transaction_id`）），故比对键不含原始 id。

### E-P3-04（F-03）G3-1 断言计数与 start_action 返回值 → 17 条列举 / 2 条记录
- **内容**：原稿 G3-1 写"18 条/三条"之类模糊计数，§5.2 S2 行 `start_action` 返回未定义；现正文统一为 **17 条列举断言 = §5.2 暂停点 9 条 + §5.3 分支 A 4 条 + §5.4 分支 B 4 条**（§6.2 G3-1 行、§7 行 1）；`start_action` 返回 `tuple[WorldState, RuntimeState, tuple[LifecycleTransition, ...]]`，恒为 **2 条**记录（VALIDATION_ACCEPTED + SCHEDULED，同 `at_tick`），S2 行与 §3.6/§6.1 同步（D-P3-19）。
- **原因**：Gate 判据要求可逐条勾选的精确计数，模糊计数使 G3-1 不可验收；生命周期记录数由 `transition_action` 语义决定，必须在契约层钉死，否则 §5.2 表格的 transitions 列无法断言。

### E-P3-05（F-06/F-07）INTERRUPTED re-anchor 与 fail_action 文档串 → 显式 re-anchor / 仅 ACTIVE→FAILED
- **内容**：原稿 §2.4 伪代码 INTERRUPTED 迁移未带 `base_world_revision` 更新，§3.6 `fail_action` 文档串允许 VALIDATING→FAILED；现正文改为：INTERRUPTED 迁移经 `transition_action(..., updates={'base_world_revision': world.world_revision})` **显式 re-anchor**（§2.4、§3.6，D-P3-08 口径）；`fail_action` 文档串限定 **仅 ACTIVE→FAILED**（VALIDATING 被拒走 VALIDATION_REJECTED，submit_proposal REJECT 路径）。
- **原因**：resume 语义要求中断后的 `base_world_revision` 指向中断刻的世界版本，否则 revalidation 基线漂移；VALIDATING 态的 proposal 尚未入活跃动作集，"失败"语义属校验拒绝而非动作失败，文档串放宽会诱导错误的迁移实现。

### E-P3-06（F-10/F-11）条件求值缺 tick 参数 / 决策边界未播种
- **内容**：原稿 `ConditionResolver.evaluate`/`evaluate_condition` 无 tick 入参，`kind="time"` 条件无从求值；§2.4 主循环未对 `due_tick > current_tick` 的 scheduled 边界播种；现正文改为：两函数均显式 `*, tick: int`（§3.7，D-P3-21）；§2.4 主循环**前**增加播种步骤——对 `kind="scheduled"` 且 `due_tick > current_tick` 的边界入队 `kind="decision_boundary"` 条目（按 `boundary_id` 去重、`entry_id` 用 `new_scheduled_entry_id()`、幂等），payload 键 `boundary_id`/`actor_id`（§2.4 注释、§2.5 行、§3.8 文档串，D-P3-22）。
- **原因**：`kind="time"` 条件的求值依赖当前 tick，P2 无"隐式时钟"可依赖，必须显式传参；decision_boundary 条目是调度器感知"该停"的唯一机制，若不播种，首次 fast_forward/step 将直接冲过决策边界，Gate 场景的暂停点全部落空。

### E-P3-07（F-12）深拷贝口径 → `deep_copy_via_roundtrip` 为唯一默认
- **内容**：原稿 §5.5 M3 / §6.3 A3/A4 写"deep copy 备份"未定实现；现正文统一为 `deep_copy_via_roundtrip`（`serialization.py:135`）为**唯一默认口径**，`write_barrier_exempt()`（`reducer.py:1065`）仅受控例外备用（§2.3 末条、§5.5 M3(a)、§6.3 A3/A4、D-P3-11② 口径注）。
- **原因**：P2 事实——写屏障在 armed 时 4 条逃逸路径抛 `WriteBarrierError`（`reducer.py` 约 1098-1105），"绕屏障原地改"不成立；roundtrip 深拷贝是 P2 已交付的无屏障窗口复制手段，M3 逐项相等比对必须钉死同一实现才可比。

### E-P3-08（F-13）P3 专项 import 黑名单作用域 → 限定 7 新模块，结构性预披露
- **内容**：原稿 §6.4/§8.3 写"扫描面自动覆盖新模块""一行级扩展"；现正文改为：P3 专项黑名单（`datetime`/`time`/`random`/`asyncio`）**仅作用于 7 个新模块**，机制为 `test_import_boundary.py` 新增 `P3_SUBMODULES` 元组 + 按模块分流谓词；B1 既有三类全局谓词（provider SDK / v1 包 / 网络进程 IO）不变；B2 维持三类（`datetime` 由 3 个冻结模块带入属预期）；§8.5-D4 改写为**多行结构性修订**预披露，列入 P3-T08 白名单（§3.2、§3.10、§6.4、§8.3、§8.4 行 5、§8.5-D4）。
- **原因**：P2 事实——`test_import_boundary.py` B1（L198）/B2（L218）为**单一全局谓词** `_blacklist_category`（L146）、三类范畴；`trace.py:46`/`events.py:36`/`snapshot.py:44` 三个 P1 冻结模块已 import `datetime`（诊断性 `wall_time`，P1 铁律 3 字节冻结）。全包"一行级"扩展必然击碎 1491 测试基线，原稿"若无改动则不触发"兜底不可达。

### E-P3-09（F-14）Scheduler 权威装配缺失 → `authority_policy` 必填 + fixture 授权规则
- **内容**：原稿 §3.8 `Scheduler.__init__` 无权威入参、§5.1 fixture 无授权策略；现正文改为：`Scheduler.__init__` 以 `authority_policy: AuthorityPolicy` **必填**（连同 `component_registry`/`producer_registry`）装配 `CascadeExecutor`（其 `__init__` 亦必填，`cascade.py:797-814`/L800，L810 `install_write_barrier`）；§5.1 新增权威策略 bullet：`AuthorityPolicy` 含 2 条 `AuthorityRule`，分别授予 `core.create_entity` 与 `core.set_component`/`movement.position` 给 origin scenario（D-P3-23，§3.8、§6.1 同步）。
- **原因**：P2 事实——`authority.py` 默认拒绝（`default_decision=DENY`，L257；空规则 = sealed，D-P2-09）。不装配授权的调度器里任何事务提交都会被拒，Gate 场景整体不成立；授权规则必须进 fixture 且进测试 probe（§6.1）。

### E-P3-10（F-04/F-05/F-08/F-15）事实性引用与措辞批量勘误
- **内容**：① `ActiveAction` 字段数 16→**14**（`actions.py:231-244`，§0 L14 与 §8.1 表两处）；② §0 serialization 行改为 def 行号引用（`dump_json` L54 / `load_json` L67 / `assert_json_clean` L82 / `deep_copy_via_roundtrip` L135，`__all__` 块 L41-46）；③ M1 fixture 数字口径统一：t=0..199 每 tick 一次 = **200 个队列条目**（§1.2 表 ×100→×200、§5.5 M1 行，消除 t=0..100/101≠200 矛盾）；④ "既有测试零修改/一行级"措辞修正为"既有**断言**零修改；唯一触碰既有测试文件的是 §3.11 三锚点（两个 19 模块列表 + 一个 `__all__` 196 规模锚点，一行级修订）+ §6.4 P3 专项黑名单作用域机制（多行结构性修订，§8.5-D4/D5）"（§6 开头、§8.4 行 5）。注：其中规模锚点（`test_closeout.py` L184，196→249）R2 漏列、R3 盲审补录（见 E-P3-17）；本条 R2 时点原文措辞为"两锚点（一行级元组）"，现按 E-P3-17 同步为三锚点口径，修订性质（一行级机械同步）不变。
- **原因**：逐条经 `.venv` 只读 probe 验证（14 个 `model_fields`；serialization def 行号；1491 基线下 M1 口径唯一性；§6/§8.4 措辞与 E-P3-08 的结构性修订事实矛盾）。

### E-P3-11（F2-01）完成 effect producer 归属统一 → 触发器注册时声明的 producer
- **内容**：原 D-P3-11 producer 归属句与 §3.8 `fast_forward` docstring 写"完成 effect → `Provenance(producer_id=spec.executor)`"，但完成 effect 由 `spec.completion_trigger='movement.arrival'` 触发器求值产生，按该句 producer=`movement.travel_system`；而 §5.1 fixture 的 `AuthorityPolicy` 仅授予 `origin_scenario` 对 `core.set_component`（movement.position）的写权（D-P3-23）→ Gate 关键路径 A4 的位置变更 effect 将被 authority 阶段一律 DENY，G3-1"唯一位置变更事务（恰在 t=30）"不可达成。现全文统一：**凡触发器（含 `completion_trigger`）求值产生的 effect → producer = 该触发器注册时声明的 producer**（Gate fixture 两触发器均注册为 `origin_scenario`）；`kind="event"` 显式 effects 批形态 → payload 声明的 `producer` 键；`ActionSpec.executor` 字段保留供 P4/P5 执行层归属使用，P3 effect 侧 producer 口径不引用该字段（D-P3-11 ①、§3.8 docstring、§3.5 字段注、§5.1 fixture、§6.1 同步）。
- **原因**：producer 身份必须与 `AuthorityPolicy` 放行面对齐（closed-by-default，D-P2-09），不对齐 = DENY（可检查、不静默）；原稿同一场景两处口径互斥（规则句 vs fixture 授权面），照实现 G3-1 必败。（R3 出处：S1-补充1。）

### E-P3-12（F2-02）`apply_checkpoint` 缺非 ACTIVE 守卫 → 双道守卫 + `checkpoint_skipped_terminal`
- **内容**：Gate 分支 A 必然产生 `[end@30, cp@30]` 同刻批（`checkpoint_interval_ticks=10`、start=0、duration=30 ⇒ checkpoint 在 10/20/30、end 在 30）；原 §2.4 `action_checkpoint` match 分支无守卫（相邻 `action_end`/`deadline` 分支均有"若仍 ACTIVE"）、§3.6 `apply_checkpoint` 无非 ACTIVE 条款 → 按字面实现对 COMPLETED 实例做 CHECKPOINT 自迁移（表外迁移）必 `IllegalTransitionError`。现：① §2.4 match 分支加守卫——实例非 ACTIVE（INTERRUPTED 或终态）→ 跳过该条目 + 诊断（终态 `checkpoint_skipped_terminal`；INTERRUPTED `checkpoint_skipped_interrupted`，D-P3-25），时钟继续；② §3.6 `apply_checkpoint` 加非 ACTIVE 守卫（第二道防线），返回签名 `-> tuple[RuntimeState, TraceRecord | None]`；③ 批内处理序稳定 FIFO（入队序，D-P3-05；§5.3 A2/A3）：end@30 先处理 → 终态迁移剪除 cp@30 → 随后 cp@30 命中已终态实例 → no-op（诊断 `checkpoint_skipped_terminal` 入 `outcome.trace_records`，TraceKind.SYSTEM）。G3-1 分支 A 总事务 = 2（`txn_1` create_entity@12 + `txn_2` set_component@30）、revision R0→R2 口径不变。
- **原因**：`LIFECYCLE_TRANSITIONS` 的 COMPLETED/FAILED 出边为空（终态），CHECKPOINT 自迁移必为表外迁移（`IllegalTransitionError` 必然发生）；守卫诊断名归 `checkpoint_*` 前缀族；TraceKind 取既有词表 `SYSTEM`（`trace.py:110`）。（R3 出处：S1-补充2。）

### E-P3-13（F2-03）未响应暂停重入行为未定义 → D-P3-24 入口首检 + 原子刻错误路径 outcome 口径
- **内容**：原 §2.4 主循环无重入规则：对暂停态（act_1 INTERRUPTED、队列 `[cp@20, end@30]`、tick=12）再 `fast_forward` 按字面 → `take_due` 取 cp@20 时钟 12→20 前进（违反 §6.3 A7"时钟不前进"）→ `apply_checkpoint` 表外迁移崩溃（违反"不崩溃"）→ 或边界被静默跳过（B1 条件 t=20 无法再命中、K1 纪律下 t=12 事件流不可再取）。现新增 **D-P3-24**：入口首检（置于循环前播种之前，重入零副作用，纯 (WorldState, RuntimeState, config) 派生）——∃ active 行动 INTERRUPTED 且 ∃ blocking 边界同 actor 且 actor ∈ `player_actor_ids` → 立即返回同一暂停（`paused=True`、`pause_reason` 按注册序首个命中、`tick=ticks_processed=当前 logical_tick`、`transactions`/`events`/`transitions`/`errors` 全空）；resume/abort 后规则自动失效；原子刻错误路径 outcome 口径钉死：单刻任何 P3 错误 → 返回刻前状态对 + `SchedulerOutcome(paused=False, pause_reason=None, ticks_processed=<刻前 logical_tick>, 全空元组, errors=<非空诊断串>)`。§2.4 伪代码、§3.8 docstring、§6.1（幂等重报 + 刻原子性用例）、§6.3 A7 同步。
- **原因**："未响应暂停"不在 (WorldState, RuntimeState, config) 中，状态机无待决暂停位（K7 无隐藏控制流），重入行为必须纯派生 + 显式口径；新增持久字段 = 隐藏控制流（K1/K7 双重违背）。（R3 出处：S1-补充3、S2-补充1、S4-补充1 三处独立；S2-RP1 复核要求已落实：重入路径零事件零事务、tick 水位不前进，G3-4a E1/E2/E3 逐事件键序列同构、17 条断言不变。）

### E-P3-14（F2-04）剪除口径悬空引用 + NPC 非阻塞中断未定义 → D-P3-25
- **内容**：① 原 `resume_action` docstring"若下一 checkpoint 条目已被剪除则补入队"引用了当前规则下**不可达**的剪除情形（全文唯一剪除点 = 终态迁移 COMPLETED/FAILED，INTERRUPTED 非终态、条目永不被剪除）→ 诱导实现者发明未定义剪除路径；现改写为"**中断不剪除队列条目**：resume 时下一 checkpoint 条目必然仍在队列（不重复入队，与 §5.3 A1 同口径）；若因缺陷缺失则补入队并输出诊断 `checkpoint_requeued_after_defect`"（防御分支，正常流程不应发生）。② NPC 非阻塞（blocking=False、interrupt=True 缺省）中断行动的后续 checkpoint 刻簿记与收敛路径原稿未定义；现 D-P3-25：`apply_checkpoint` 守卫 no-op + 唯一诊断 `checkpoint_skipped_interrupted`（TraceKind.SYSTEM）+ **三项收敛边界声明（不崩溃 / 簿记确定 / 不静默跳过）**，最终收敛 = `WakeupHook` 重新提案（P4/P5 范围）或外部 abort（actor ∈ `player_actor_ids`）；Scheduler 自动 ABORT 备选 (b) 被弃（自动中止是语义策略，P3 无策略输入、不可从 (state, config) 派生）。§3.6 各 docstring、§3.7 `interrupt` 注释、§6.1 `interrupt`/`scheduler` 用例、§6.3 A2（NPC 非阻塞中断方向，S2-RP2）同步。
- **原因**：悬空机制引用与守卫语义冲突（剪除只在终态发生，resume 实例条目必然在队列）；NPC 非阻塞中断在 Gate 场景内不可达、P4/P5 集成期注册任何 NPC 边界即立即可达（孤儿 checkpoint 条目将致 `IllegalTransitionError` 硬失败），须预先钉死簿记口径与收敛边界。（R3 出处：S2-补充2、S1-补充7、S3-补充3 三处独立；S2-RP2 用例要求落实于 §6.3 A2 矩阵扩展。）

### E-P3-15（F2-05）A1 revision 算术不一致 → R5（方案 α）+ REJECT 原因优先级（过期优先）
- **内容**：原 §6.3 A1 写"先经其他事件把世界推到 R5（3 个 encounter 类事件提交）"，算术不闭合——`INITIAL_WORLD_REVISION=Revision(0)`（`revision.py:70`）+ 每次 commit 恰 +1（`transaction_executor.py:227-228` `commit_revision=base_revision.next()`）→ 5 次提交 = R5（方案 α）；方案 β（3 提交 = R3）会破坏变体 `valid_until=R4`（R3 ≤ 4 未过期，`valid_until_expired` 断言不可达）。现钉死 **5 个** encounter 类事件提交 → R5；同条钉死 REJECT 原因优先级：`valid_until` 非 None 且 `current > valid_until` → `valid_until_expired`；否则 → `stale_revision`（两条件同时满足时**过期优先**，不随实现顺序漂移）。§3.9 步骤 1、§6.1 revalidation 用例、§6.3 A1 及变体同步。
- **原因**：Gate 断言要求修订号算术可复核（"revision 停在 R5"与提交次数必须互推）；两条件重叠时原因字符串不定值会破坏跨运行逐字比对（D-P3-15① 口径）。（R3 出处：S1-补充4。）

### E-P3-16（F2-06）屏障断言次序 → 先检查后构造（R1 回归可观察）
- **内容**：原 §3.8 `Scheduler.__init__` docstring 操作次序为"先内部构造唯一 `CascadeExecutor`、后执行 `assert_barrier_armed` 检查"——但 `CascadeExecutor.__init__` 自身无条件 `install_write_barrier()`（`cascade.py:810`，幂等），按字面次序检查点时刻屏障恒已武装 → 断言恒真（死断言），§6.1"未武装环境 `Scheduler(assert_barrier_armed=True)` → `SchedulerConfigurationError`"不可实现。现次序钉死：`assert_barrier_armed=True` 时**先** `write_barrier_installed()`（`reducer.py:1150`）检查（假 → `SchedulerConfigurationError`，不构造执行器），**后**内部构造唯一 `CascadeExecutor`；该检查为 `__init__` 第一步。§6.1 R1 回归用例重排：负例在**未武装环境**（新进程，测试先断言 `write_barrier_installed() is False`）执行；正例 conftest 预武装后构造成功且套件全生命周期 `write_barrier_installed() is True`（武装态不卸载，D-P3-11②）。
- **原因**：G2 移交 1（Scheduler 运行入口武装断言）的语义只有"先检查后构造"次序下才可观察；.venv 探针实测：干净进程构造 `CascadeExecutor` 后立即 `write_barrier_installed() is True`。（R3 出处：S1-补充5、S3-补充2 两处独立。）

### E-P3-17（F2-07）锚点清单漏规模锚点 → 三锚点（196→249）
- **内容**：原 D-P3-12 锚点清单 / §3.10 T01 白名单 / §8.2 只列"closeout 两锚点"（`test_closeout.py::_CORE_SUBMODULE_NAMES` L92 与 `test_import_boundary.py::CORE_SUBMODULES`，19→26），但设计自身强制包 `__all__` 196→249（53 个新符号），而 `test_closeout.py` L184（含注释块 L164-183）存在硬断言 `assert len(core_pkg.__all__) == 196`（1491 基线全绿即含此断言）——按原白名单实施的 T01 必打破基线断言，与"既有断言零修改、唯一触碰既有测试文件的是两锚点 + §6.4 机制"声明自相矛盾。现全文统一为**三锚点**：①② 两个 19 模块清单 19→26 + ③ 规模锚点 L184（含注释块）196→249；§3.10 T01 白名单、§3.11、§8.2、§8.4 行 5、§6 开头、§8.5-D5（新增披露偏差条目，预披露的规模锚点机械同步，一行级、非 BLOCK）同步；E-P3-10 ④ 保留 R2 时点"两锚点"记录并加注（不回改）。
- **原因**：性质与 19→26 同类的一行级机械同步（披露偏差类别，非 BLOCK），但 R2 未披露、不在白名单内——按最高约束（1491 基线既有断言零修改）必须预先列明。（R3 出处：S3-补充1；该槽实跑 pytest 确认 1491 passed。）

### E-P3-18（F2-08）G3-5 测试文件口径 → `P3_TEST_FILES` 全量清单逐文件核验
- **内容**：原 §6.2 G3-5 用 glob `test_p3_*.py` + "import 边界扫描覆盖 src，测试文件靠 ruff + 本清单人工口径"——glob 仅覆盖 9 个新增测试文件中的 2 个（`test_p3_gate_scenario`/`test_p3_adversarial`），其余（`test_clock`/`test_event_queue`/`test_action_registry`/`test_action_lifecycle`/`test_interrupt`/`test_revalidation`/`test_scheduler` + `conftest.py`）无 provider/llm import 核验的机械口径；"ruff + 人工清单"备选弃用（ruff 规则粒度无法表达 provider/llm 名称黑名单）。现 G3-5 行列举**全量集合**（9 个 `test_*.py` + `conftest.py`），机械口径 = `test_import_boundary.py` 新增 `P3_TEST_FILES` 元组（10 个新增测试文件逐一列举）逐文件核验（与 `P3_SUBMODULES` 同按集合分流的作用域机制，§6.4/§8.5-D4 预披露结构性修订）；§3.10 T08 白名单、§6.4、§8.5-D4 同步。
- **原因**：G3-5（no LLM required）是 Plan §12 判据之一，必须可机械核验而非人工口径；口径落在既有预披露的结构性修订文件内，不新增触碰面。（R3 出处：S1-补充6。）

### E-P3-19（F2-09）revalidation 依赖图边过标 → 仅测试口径一致性复用，不入运行时路径
- **内容**：原 §3.2 依赖图将 `revalidation.py` 依赖写作"P1: revision/actions + P2 `validation.check_transaction_references`"，但 §3.9 `revalidate_proposal` 算法并不调用该函数——`check_transaction_references` 输入为 `(state, Transaction)`（`validation.py:857`），与提案级 revalidation 的输入不匹配，图边与算法正文矛盾；该函数实际仅出现于 §6.1 effect 侧复用探针（P2 L2 检查器口径一致性）。现图边标注改为"P2 `validation.check_transaction_references` 仅测试口径一致性复用（§6.1），不入运行时路径"。
- **原因**：§3.2 依赖图是 T07 实现者的 import 依据，过标会诱导实现期 import 该函数（无调用点即死 import）或伪造"复用"实现；G3-2 import 边界对死 import 无豁免。（R3 出处：S1 风险点 1 + S1 引用错误 2。）

### E-P3-20（F2-10）P2 触发器类型名不存在 → `CascadeTrigger`/`SyncTrigger`/`CascadeTriggerRegistry`
- **内容**：原三处引用 P2 触发器类型用不存在的名称：§3.8 Scheduler 构造器草图 `trigger_registry: TriggerRegistry`、§2.5 与 §5.1 的"P2 `Trigger` 协议"。P2 实际类型：`CascadeTrigger`（Protocol，`cascade.py:473`）、`SyncTrigger`（`cascade.py:503`）、`CascadeTriggerRegistry`（`cascade.py:573`，公开 API 仅 `register`/`evaluate_all`/`trigger_ids`，`:589-644`），别名 `TriggerRegistry = CascadeTriggerRegistry`（`cascade.py:650`），三者均经 core `__init__` 导出。现三处统一更正为实际名称（含别名标注）；另 G3-5 行（F2-08 修订时同线）stub 类型名 `Trigger` 一并同步为 `CascadeTrigger`。
- **原因**：与 E-P3-10 事实引用更正同类，但该三处未被 R2 勘误清单覆盖，属未披露引用错误——照原稿实现者查无此名（`Trigger` 协议不存在、裸 `TriggerRegistry` 仅在别名处存在），import 即失败。（R3 出处：S4-补充2 + S4 引用错误 1/2。）

### E-P3-21（F2-11）E-P3-03 引用不精确 `ids.py:232/263` → `232-234`/`237-239`
- **内容**：E-P3-03"原因"段以"ids.py:232/263"标注 `event_id`/`transaction_id` 的 uuid4 工厂位置；实际 `ids.py` L232-234 为 `new_event_id`（正确）、L237-239 为 `new_transaction_id`、L263-264 为 `new_scheduled_entry_id`（entry_id 工厂）——"263"指向 entry_id 而非 transaction_id。现更正为"`ids.py:232-234`（`new_event_id`）/ `ids.py:237-239`（`new_transaction_id`）"；D-P3-20 规范正文"ids.py 工厂（uuid4 hex，`ids.py:223-234`）"区间有效，不改。
- **原因**：勘误留痕段自身的次要引用瑕疵，不影响实现，但勘误引用须精确（勘误之勘误）。（R3 出处：S1 引用错误 1。）

### E-P3-22（F2-12）`pending_proposals` 簿记口径未定义 → ACCEPT 于 start_action 成功时移出 / REJECT 留痕
- **内容**：原稿只钉死 REJECT 提案在 `pending_proposals` 留痕（§6.3 A1），未定义 ACCEPT 提案何时移出/标记（`start_action` 时？进入 ACTIVE 时？）。现 §3.8 `submit_proposal` docstring 钉死：**ACCEPT 提案于 `start_action` 成功时（与 PROPOSED→VALIDATING→ACTIVE 迁移完成同刻）移出 `pending_proposals`**；REJECT/REBASE 留痕——REJECT 留痕 = 提案仍在列表 + `RevalidationDecision` REJECT 记录（注：`ActionProposal`（`actions.py:145-188`）**无 status 字段**，留痕不得断言为状态变化）；REBASE 留痕 = 原提案替换为 `rebased_proposal`（§3.9）。
- **原因**：§5.2 无断言依赖该字段中间态（无 Gate 影响），但 T04（QMax）与 T08（GFlash）实现/测试侧必须有唯一簿记口径，否则对抗用例的"pending_proposals 残留"断言无依据、T04 实现可自由裁量（K7 违背）。（R3 出处：S1 风险点 4 + S4 风险点 1。）

### E-P3-23（F2-13/F2-14/F2-15/F2-16）触发器名称解析 / S1 fixture 速记缺 `proposal_id` / 提交参数钉死 / start 迁移记录观察出口
- **内容**：①（F2-13）原稿让调度器按队列 payload `trigger_id`（如 `scenario.encounter_12`）在指定刻经注册表点名触发器，但 `CascadeTriggerRegistry` 公开 API 仅 `register`/`evaluate_all`/`trigger_ids`（`cascade.py:589-644`，`_triggers` 经 `__slots__` 私有），无按 trigger_id 查询单个触发器的方法——照原稿实现者被迫触碰私有字段或发明查询 API；现 §3.8 docstring 钉死：**scheduler 自持 `trigger_id→trigger` 映射**（R4 修正 D-P3-26/E-P3-25：由必填构造参数 `named_triggers` 建立——原"由注册表已注册集合建立、纯配置级读取"口径与 K7 私有访问禁令矛盾、纯执行者无合规取数途径，由显式参数方案取代；不新增运行时状态、零私有访问），`kind="event"` 的 `trigger_id` payload 与 `completion_trigger` 到点时由 scheduler 经该映射直接点名求值（不经注册表查询）。②（F2-14）S1 fixture 速记 `ActionProposal(actor_id=…, action_id=…, …)` 漏写必填且无默认值的 `proposal_id`（`actions.py:174`，P1 D-3 要求提案创建即按序签发）——逐字复制该 fixture 构造即抛错；现 §5.1 记号行加注：`act_1` 构造时经 `new_action_instance_id()`（`ids.py:255`，`act_` + uuid4 hex）签发，速记省略。③（F2-15）原稿未钉死 `CascadeExecutor.run` 必填参数口径；现 §3.8 docstring 钉死：每次 run 提交 `causal_root_id` = 驱动该批的队列条目 `entry_id` 字符串（本刻批首条 entry），`origin` = 所产 effect 的 producer 之 `Provenance`（确定性值，不自由裁量；run 守卫 `cascade.py:906-914`：`causal_root_id` 非空 str + `origin` 为 Provenance）；P2 冻结 docstring（`cascade.py:882-884`）对 P3 用法的示例性表述（『以 action 实例为根』）被本 `entry_id` 口径取代——偏离披露详见 E-P3-38（R7-S4 补充1）。④（F2-16）`start_action` 的 2 条 `LifecycleTransition` 记录（PROPOSED→VALIDATING→ACTIVE，§3.6 明确"落 2 条记录"）在 `submit_proposal` 侧产生，但 `submit_proposal` 返回签名 `(WorldState, RuntimeState, RevalidationDecision)` 无 transitions 观察出口；现范围声明（§3.8 docstring）：2 条记录**不入任何 `fast_forward` 调用的 outcome**（按调用聚合，D-P3-18/19），测试侧观察出口 = §6.1 `start_action` 单测直接断言迁移层返回的 2 条记录（不经 `submit_proposal` 返回值）。
- **原因**：① 无公开查询 API 且不得以私有字段访问补位（K7）时，点名求值的合规取数途径 = 显式构造参数 `named_triggers`（R4/D-P3-26 取代原"由注册表已注册集合读取"口径，现方案零私有访问，见 E-P3-25）；② fixture 是 T08 的装配基准，缺必填字段 = 测试不可实现；③ run 守卫为 P1 冻结行为，参数自由裁量 = 因果链不确定（K7 违背）且 `causal_root_id` 空串直接触发守卫抛错；④ 无范围声明则实现者要么把 transitions 塞入 outcome（破坏按调用聚合口径）、要么丢失 2 条记录的断言面。（R3 出处：S3 风险点 1/2/3/4，四条合并留痕。）
- **R6 注记**：③（F2-15）run()-级 `origin` 的 `OriginKind` 取值现钉死于 §3.8 F2-15 段 + §5.1 调度器构造行：Gate fixture 一律构造 `Provenance(producer_id=origin_scenario, origin=OriginKind.SCENARIO)`（provenance.py:41-53；通用口径 = fixture 声明 producer 时一并声明其 `OriginKind`，缺省 SCENARIO）；事件级 provenance 仍由 P2 承载（transaction_executor.py:156-157），本注只钉 scheduler 的 run() 参数，详见 E-P3-34。（R6 出处：S3 补充1。）

### E-P3-24（F3-01，含 L3-01 留痕）触发器 stub 级联回合再求值幂等性未钉死 → 状态守卫 + 双路求值口径
- **内容**：原稿 §5.1 触发器 bullet 仅有"触发器 → effect"速记，未钉 stub 在级联回合重求值（入参 = 本回合已提交事件 + 已提交后视图）时的行为；无状态常发 stub 将在 t=12 深度 1 回合重发 `encounter_12` → `create_entity(ent_bandit)` 目标已存在 → 该回合事务 ABORTED（transaction.py:13-14：ABORTED ⇒ effects==[]）→ 违反 §5.2 S8 `transactions=(txn_1,)` 与 G3-1 分支 A"总事务数 = 2"；`arrival` 重发若存活则 t=12 位置变更 → 违反 G3-1 断言 9（位置未动）与 M2(b)"唯一位置变更事务 = txn_2 @ t=30"。现 §5.1 钉死：**stub 必须幂等（状态守卫）**——重求值查 `guard(state)` 视图，目标实体已存在（`encounter_12` → `ent_bandit` 已在世界）或目标组件已到达值（`movement.arrival` → `movement.position == destination`）→ 返回空 effect 列表、不重发；fixture 可用闭包变量记录已发集（测试局部 fixture 状态、非引擎状态）；**双路求值口径**——点名求值（scheduler 自持映射，§3.8）与级联回合再求值（`CascadeExecutor.run` 每回合 COMMITTED 后对全部注册触发器再求值，cascade.py:969-981）命中同一 stub，守卫对两路均幂等，验收判据 = S8 `transactions=(txn_1,)` 与 G3-1 分支 A 总事务数 = 2 逐行成立。另（L3-01，并入本条编辑点）：§5.1 补『注册时声明』producer 载体注记 = stub `evaluate` 产出 effect 时写入 `ProposedEffect.source`（effects.py:219 必填 `ProducerId`），经 `transaction_executor.py:156-157` 流入事件 provenance（`source_system=effect.source`、`provenance=Provenance(producer_id=effect.source)`）——P2 注册表 API 无 producer 存储位（§3.8 `fast_forward` docstring / D-P3-11 同款措辞处加指引）。
- **原因**：cascade.py:969-981——每回合 COMMITTED 后 `if outcome.events: pending.extend(self._collect_trigger_outputs(outcome.events, current, depth, …))` 对全部注册触发器再求值，scheduler 另经自持映射点名求值（§3.8）——双路求值下无守卫的常发 stub 必发重复 effect（R4 双 slot 共识）。（R4 出处：S4 补充1、S3 风险0；L3-01 出处：S4 风险1。）
- **R5 注记**：Gate fixture 由 D-P3-27 重推为**单路**——`trigger_registry` 显式空注册表、`enc_stub`/`arr_stub` 只存在于 `named_triggers`、级联回合再求值面为空；Gate 判据不再依赖双路守卫（本条状态守卫与 `cause_ids` 口径保留为 fixture 向注册表注册触发器情形的**通用契约**；重推留痕见 E-P3-30）。（R5 出处：S1 补充1。）

### E-P3-25（F3-02）F2-13 自相矛盾：`trigger_id→trigger` 映射取数机制无合规途径 → `named_triggers` 显式构造参数（D-P3-26）
- **内容**：§3.8 原稿称映射"构造时由注册表已注册集合建立、纯配置级读取"，而 E-P3-23① 原因段引 K7"不得以私有字段访问补位"——`CascadeTriggerRegistry` 公开 API 仅 `register`/`evaluate_all`/`trigger_ids`（cascade.py:589-644）、`_triggers` 为 `__slots__` 私有（cascade.py:584），纯执行者无合规取数途径，两处口径矛盾。现按显式构造参数方案修正（D-P3-26）：`Scheduler.__init__` 新增必填参数 `named_triggers: frozenset[tuple[str, CascadeTrigger]]`（不可变、确定性、零私有访问、可序列化描述 = trigger_id 投影），映射由该参数建立；fixture 传入与注册进 `trigger_registry` 的同一批触发器对象（fixture 持有两者、无额外状态）；§3.8 签名/docstring、§5.1 构造行、§6.1 构造用例（缺参 → `TypeError`、空集 → `kind="event"` 仅 effects 形态可用、`trigger_id` 形态 → `QueueInvariantError`）同步；E-P3-23① 内容/原因段随之更正（见该条 R4 注）。
- **原因**：两处口径矛盾使 F2-13 落定不可执行；弃"读私有 `_triggers` 一次性"（K7 违背）与"evaluate_all + filter"（求值面扩大、语义偏离点名），选显式参数（D-P3-26 备选段）。（R4 出处：S3 补充1。）

### E-P3-26（F3-03）§3.9 REPAIR 范围未声明（"repair" 全文 0 出现）→ P3 结果域 {ACCEPT, REBASE, REJECT} + P4 保留 REPAIR
- **内容**：P1 冻结 `RevalidationOutcome` 四值 ACCEPT/REBASE/REPAIR/REJECT（revision.py:91-101，docstring"判定行为属 P2（Plan P2-T04）；P1 只落数据词表"），Spec §9 列 REPAIR、Spec Scenario G（L2579）"revalidation reject/repair"；P3 `revalidate_proposal`（§3.9）只产三值、"repair" 全文 0 出现——范围未声明。现 §3.9 结果映射处（`revalidate_proposal` docstring 末尾）补声明：**REPAIR（`RevalidationOutcome.REPAIR`）不产生于 P3 同步 tick 循环 revalidation**——REPAIR 属 Spec §9 异步结果 revalidation 语境（P4 携带 base_world_revision/observation_id/actor_state_revision/valid_until 的异步结果路径）；P3 `revalidate_proposal` 结果域 = {ACCEPT, REBASE, REJECT}，P4 异步路径保留 REPAIR 产出能力（词表已冻结，P3 不扩展不缩减）。§6.1 revalidation 用例行补口径：P3 测试不得把结果域钉死为三值集合（不得断言 结果域 == {accept,rebase,reject} 为词表不变量）；REPAIR 范围见 §3.9 声明。
- **原因**：词表已冻结四值而 P3 只产三值，无范围声明则实现者要么误把三值当词表不变量钉死测试、要么自行裁量 REPAIR（K7 违背）。（R4 出处：S2 补充1。）

### E-P3-27（F3-04）npc_notices → ActorWakeup 入队调用点缺失 → §2.4 伪代码补调用（D-P3-10 选 B 不变）
- **内容**：D-P3-10 选 B 含"非阻塞命中 → 记录 `BoundaryReport.npc_notices` + 入队 `ActorWakeup`（与 D-P3-14 唤醒钩子收敛）；fast-forward 不因 NPC 中断"，但 §2.4 fast-forward 伪代码只消费 `report.fired` + `report.player_blocking`，无 `npc_notices → enqueue_actor_wakeup` 调用点，Gate M1 无 NPC 边界 → 无覆盖。现 §2.4 伪代码 npc 分支补：对 `report.npc_notices` 逐 `(boundary_id, actor_id)` → `enqueue_actor_wakeup(actor_id, due_tick=当前刻, reason=boundary_id)`（收敛路径 D-P3-25：P4/P5 actor 重新提案；P3 层只入队不执行），与 §2.5 `actor_wakeups` 双记录口径（wakeup 记录 + `kind="wakeup"` 队列条目、逐字段一致）对齐；§6.1 `interrupt.py` 阻塞规则用例增补断言：`npc_notices` 非空 → `actor_wakeups` +1 条且同刻入队一条 `kind="wakeup"` 队列条目（两条记录逐字段一致）。
- **原因**：决策（D-P3-10）承诺的行为在主循环伪代码无落点 = 契约层缺口（与 F2-02 同类：§4 承诺、§3 未写），纯执行者无从接线。（R4 出处：S4 补充2。）

### E-P3-28（F3-05）INTERRUPTED 迁移 progress 镜像更新未承诺 → §3.6 `transition_action` docstring 补契约
- **内容**：G3-1 断言 4 对存储字段断言 `act_1.progress == 12/30`；D-P3-08 定位存储 progress"仅作快照镜像…在 checkpoint/restore/interrupt/resume 重算"，但 §3.6 `transition_action` docstring 未承诺更新 progress 镜像（仅 updates 合并 / `last_transition_tick` / INTERRUPTED re-anchor / 终态剪除）→ 契约层缺口（与 F2-02 同类：§4 承诺、§3 没写）。现 §3.6 docstring 补：**INTERRUPTED 与 RESUMED 迁移在 updates 中同步更新 progress 镜像字段**（`progress_of(action, at_tick)`，D-P3-08：纯派生、不累加、不可被 effect 篡改）；运行时权威值恒为派生，镜像供快照/restore/trace 观察——此口径使 G3-1 断言 4（t=12 INTERRUPTED 迁移后 `act_1.progress == 0.4`）在契约层成立。§5.2 S7 行与 §6.2 G3-3 行口径核对一致（G3-3"snapshot round-trip 后 progress 重算恒等（不依赖存储值）"不变）。
- **原因**：G3-1 断言 4 在契约层无依据（存储镜像无人写）——T03 实现可自由裁量是否写镜像（K7 违背）。（R4 出处：S4 补充3。）

### E-P3-29（L3-02/L3-03/L3-04/L3-05/F3-06/L3-06/L3-07 合并）轻量项七则
- **内容**：①（L3-02）§3.8 `step()` docstring 钉死强制暂停 outcome 形态：`paused=True`、`pause_reason` kind="bounded"（`PauseReason` 词表 "decision_boundary" | "bounded" | "terminal"）、tick = 本步到达刻（`ticks_processed` 同刻）。②（L3-03）§6.3 A2"resume 后 abort（合法路径对照组）"补注：合法序列以 `LIFECYCLE_TRANSITIONS` 为唯一权威 = resume → 再中断 → abort（ABORTED 边仅出自 INTERRUPTED；ACTIVE 无直接 ABORTED 边，表外探针已单列）。③（L3-04）§3.2 依赖图 `clock.py`/`action_registry.py` 边注补 P1 entity 模块（`ContractModel` 基类，entity.py:51；两模块类型均为其子类）。④（L3-05）`trace.py:113-138` 锚点 → `trace.py:113-139`（`payload` 开放 dict 字段在 L139；全文唯一引用，已同步）。⑤（F3-06，与 L3-05 合并留痕）§3.2 `action_lifecycle.py` 边注原稿"P2 commit 路径类型"过标 → 按 §3.6 各函数实际引用改注 "P1：actions/state/revision/ids/trace/effects/entity + stdlib + pydantic"（该模块纯函数不消费 P2 符号；`apply_checkpoint` 返回的 `TraceRecord` 是 P1 trace.py 类型、transition 簿记不触 P2）。⑥（L3-06）§8.1 表内 revalidation 单一源行交叉引用 "(D-P3-09 一致性)"系误引（D-P3-09 实为中断条件词表决策）→ 改引 D-P3-16 ②（revalidation 结果 = 数据、复用 P1 四值词表、不新增类型）。⑦（L3-07）§3.10 P3-T01 白名单处补实现期核验注记：实现完成后须以 diff/哈希核验——`core/__init__.py` 相对基线纯增量（既有 196 条目顺序/内容零改动）、13 个 P1 契约模块 `.py` 与 `603535e` 逐字节一致、53 新导出名与既有 196 名及 26 子模块名零撞名（closeout 规模锚点 249 为机械兜底）。
- **原因**：均 R4 盲审轻量风险/注记项，逐条 Leader 核验属实；不改任何 Gate 断言、`__all__` 249、17 条断言、`LIFECYCLE_TRANSITIONS` 边集。（R4 出处：L3-02 S3 风险2、L3-03 S3 风险1、L3-04 S4 风险0、L3-05 S3 风险4、F3-06 S4 补充4、L3-06 S4 注、L3-07 S2 风险1。）

### E-P3-30（F4-01）Gate fixture 双路求值判据依赖闭包过滤行为 → 单路化：`trigger_registry` 显式空注册表（D-P3-27）
- **内容**：原 §5.1 调度器构造行让 `trigger_registry` 持两个命名触发器并装配进唯一 `CascadeExecutor`、`named_triggers` 传同一批对象——点名求值（单触发器）与级联回合再求值（每回合 COMMITTED 后对注册表全量再求值，cascade.py:969-981）双路命中同一 stub；Gate 判据（S8 `transactions=(txn_1,)`、G3-1 分支 A 总事务数 = 2、M2(b) 唯一位置变更事务）隐式依赖 stub 状态守卫（E-P3-24）+ 闭包 `cause_ids` 过滤行为，二者均非本文档钉死口径（纯执行裁量缺口，K7）。现按 **D-P3-27** 单路化：`trigger_registry = CascadeTriggerRegistry()` 显式空注册表（装配断言 `trigger_ids()` 为空），`enc_stub`/`arr_stub` 只存在于 `named_triggers`（D-P3-26）、为点名求值唯一数据来源；Gate 场景全部世界 effect 产出走 scheduler 点名求值单路（ev_enc@12 → `encounter_12` 点名 → create_entity → txn_1；t=30 completion → `arrival` 点名 → set_component → txn_2）；`CascadeExecutor` 注册表为空 → 级联回合再求值面为空（无重发、无 `trigger_output_dropped`）→ 判据**由构造成立**，不依赖闭包行为。同步：§5.1 调度器构造行 + 触发器 bullet（stub 幂等守卫重定位为**通用契约**——适用于向注册表注册触发器的任意 fixture，Gate 下不触发；新增 `cause_ids` 口径：必须引用本回合事件 ID（cascade.py:481-483），空 `cause_ids` → 确定性丢弃 + SYSTEM 诊断 `trigger_output_dropped`（cascade.py:1267-1316）；Gate 验收判据改注"单路，由构造成立"）；§3.8 `trigger_registry` 参数语义钉死（`None` 缺省 = 空注册表，cascade.py:852；点名求值不受该参数影响）+ docstring 新增 **`trigger_registry` 参数语义** 段；§5.2 S6/S8、§5.3 A4、§5.5 M2(b) 标注由"守卫"改"单路（D-P3-27，由构造成立）"（断言值全部不变）；§6.1 scheduler bullet 增 `trigger_registry=None` 缺省行为用例 + fixture 断言注册表为空；E-P3-24 追加 R5 注记（重推单路、通用契约保留）。
- **原因**：双路求值下 Gate 判据的正确性落在实现侧裁量（守卫/闭包过滤）而非设计口径，违背"纯执行"纪律；单路化后判据由构造成立；级联再求值机制（cascade.py:969-981）与 `cause_ids` 口径（cascade.py:1267-1316、479-481）为只读探针核验事实，通用契约保留供注册触发器进注册表的非 Gate fixture 使用。G3-1 的 17 条断言不变（双路→单路不改断言值、仅去除对闭包行为的依赖）、`__all__` 249 不变（构造参数非新导出符号）、`LIFECYCLE_TRANSITIONS` 边不变、P1 13 模块字节冻结不变。（R5 出处：S1 补充1。）

### E-P3-31（F4-02）D-P3-24"恒可重报"概括在无 INTERRUPTED 背书边缘不成立 → 重报保证限定 + 边缘一次性声明（D-P3-24③ 改写、⑥ 新增）
- **内容**：D-P3-24 原选择段把"未响应暂停"概括为恒可重报，但入口首检条件是纯派生——依赖 ∃ 行动处 INTERRUPTED 的背书；玩家 blocking 边界命中但**无行动进入 INTERRUPTED**（玩家无活动行动、或该行动 `interruptible=False`）时无背书，首检条件不满足，重报规则不适用，原概括为假。现 D-P3-24 第 3 项改写：重报保证**限定于该行动仍处 INTERRUPTED（玩家未响应）期间**（幂等、外部可检查）；新增第 6 项**边缘声明**：该边缘下暂停**仅返回一次**（边界 fired 记录 + trace 留痕、已送达调用方），重入 `fast_forward` 正常推进、该边界不重检——一次性事件，非"静默跳过"（其暂停效应已交付）；且入口重报规则**仅在 `TimePolicy.pause_on_player_boundary=True` 且存在 INTERRUPTED 背书时生效**（Gate 场景 act_1 可中断 → 背书存在，不受影响）。同步：§2.4 伪代码入口首检注释（保证期间限定 + 边缘一次性 + 标志前置）、§3.8 `fast_forward` docstring（同口径）、§6.1 scheduler bullet 新增**边缘探针**（首次 ff 暂停一次（fired + trace）、第二次 ff 正常推进、不重报）。
- **原因**：原概括越过首检条件本身（纯 (WorldState, RuntimeState, config) 派生，无"待决暂停"位，K7）——无背书时状态机无从重报；一次性口径保住"不静默跳过"（fired 记录 + trace 交付即非静默），不引入重检（重检需持久化"已暂停"事实，K1/K7 违背）。（R5 出处：F4-02，Leader 核验清单。）

### E-P3-32（F4-03/L4-01 合并）`pause_on_player_boundary=False` 语义未定义落定 + 引用修正两则
- **内容**：①（F4-03）`TimePolicy.pause_on_player_boundary` 字段已定义但仅 True 路径（Gate 缺省）出现于正文，False 路径纯执行裁量缺口。现字段位钉死（§3.8）：False → 边界**仍 fired**（`BoundaryReport.fired` + trace 留痕）且**仍按 `boundary.interrupt` 中断**（INTERRUPTED，D-P3-25 口径不变），但 `fast_forward` **不返回暂停**、继续推进至本次调用终点（max_tick/terminal）；D-P3-24 入口重报规则**不生效**（以本标志为前置，见 D-P3-24⑥）；由调用方显式驱动 resume/abort。缺省 True = 现口径（Gate），D-P3-24/§5.2 全部不变。同步：§3.8 字段位注释、§2.4 伪代码入口首检注释（标志前置）+ `if report.player_blocking` 行注释、§3.8 `fast_forward` docstring。②（L4-01）引用修正两则：(a) `trace.py:100-108`（TraceKind 引用）→ `trace.py:91-110`（TraceKind 枚举完整范围，`SYSTEM = "system"` 实位于 L110）——§5.5 M2(b)（全文唯一引用，已核）；(b) ids.py 工厂组 `223-234` → `222-265`：核验全文仅两处出现——D-P3-20 理由段（E-P3-21 裁定"有效，不改"，保留）与 E-P3-21 自身内容（历史记录，保留）→ 正文无需改动（只读探针核验事实：`new_entity_id` L222、`new_event_id` L232、`new_transaction_id` L237、`new_action_instance_id` L255、`new_scheduled_entry_id` L263，正确范围为 `222-265`）。
- **原因**：① 字段定义而语义只半边落定，实现侧对 False 分支无口径可依（K7 裁量缺口）；False 口径由 D-P3-10（player_blocking 判定）/D-P3-25（中断行为独立于暂停）/D-P3-24⑥（重报规则前置）推出，与 §2.4 伪代码自洽复核无新冲突；② 引用行号与源码不符，逐行只读探针核验。（R5 出处：F4-03、L4-01，Leader 核验清单。）

### E-P3-33（L5-01）E-P3-32②(b) ids.py 工厂组引用区间 off-by-one → `222-265`（就地更正勘误正文，轻量注记）
- **内容**：E-P3-32②(b)（L4-01 引用修正）将 ids.py uuid4 工厂组区间起点误记为 L223（末点 L265 无误）——与只读探针事实不符：工厂组首 `new_entity_id` 位于 `ids.py:222`（def L222、docstring L223、return L224），末 `new_scheduled_entry_id` 止于 L265（def L263、docstring L264、return L265）——正确区间为 `222-265`（原记起点 223，比首个 def 行少 1 行）。现 E-P3-32②(b) 正文两处（"`223-234` → …"更正目标与"正确范围为 …"表述）就地更正为 `222-265`；D-P3-20 理由段"223-234"（E-P3-21 已裁定"有效，不改"）与 E-P3-21 自身内容为历史记录，保留不动。
- **原因**：R5 勘误留痕自身的聚合范围 off-by-one（逐项行号经 R6 逐一 grep 实测全部正确）；区间更正为机械引用修正，正文 D-P3-20/E-P3-21 属历史裁定记录，按 §9 纯追加约定不回改，仅本条就地更正。（R6 出处：S4 citations_wrong，轻量项 L5-01。）

### E-P3-34（F5-01）run()-级 origin 的 OriginKind 未钉死 → Gate fixture 钉死 `OriginKind.SCENARIO` + 通用口径
- **内容**：原 §3.8 F2-15 段"origin = 所产 effect 的 producer 之 Provenance（确定性值，不自由裁量）"未钉死构造 run()-级 `Provenance` 时取哪个 `OriginKind`——但 `Provenance`（`provenance.py:71-72`）`producer_id`/`origin` 双必填无默认（缺 origin 即 ValidationError，探针构造验证），"不自由裁量"无来源，纯执行者须自决一个文档未钉的值。现 §3.8 F2-15 段钉死：Gate fixture 的 run()-级 origin 一律构造为 `Provenance(producer_id=origin_scenario, origin=OriginKind.SCENARIO)`（`OriginKind` 冻结词表 provenance.py:41-53，SCENARIO ∈）；通用口径 = fixture 声明 producer 时一并声明其 `OriginKind`（缺省 SCENARIO），随 named_triggers/fixture 装配显式传入，不自由裁量。同步：§5.1 调度器构造行补 origin 口径注；E-P3-23③ 补 R6 注记。事件级 `DomainEvent.provenance` 仍由 P2 承载（`transaction_executor.py:156-157`：`provenance=Provenance(producer_id=effect.source, origin=origin)`，origin 经 `producer_registry.origin_of` 解析、缺省 `OriginKind.SYSTEM`（transaction_executor.py:139-143）——事务级/事件级两个 origin 面区分），本条只钉 scheduler 的 run() 参数。
- **原因**：`Provenance` 双必填字段无默认（探针：缺 origin 的 `Provenance(producer_id=…)` 即 ValidationError；`Provenance(producer_id="origin_scenario", origin=OriginKind.SCENARIO)` 构造合法，JSON 值 `"scenario"`）；`OriginKind.SCENARIO` 为冻结词表成员（对应 Spec §16.2 writer 家族 QuestSystem(scenario)，与 producer `origin_scenario` 归属一致）；取值不钉死即 K7 裁量缺口，因果链跨运行不可复现。（R6 出处：S3 补充1。）

### E-P3-35（F5-02）actor wakeup 双记录"逐字段一致"表述与 P1 冻结真相比不成立 → 改写为 (actor_id, due_tick) 一致口径
- **内容**：原 §2.4 伪代码（npc 分支注释）、§2.5 尾注、§3.8 `enqueue_actor_wakeup` docstring、§6.1 `interrupt.py`/`scheduler.py` 用例与 §8.1 复用对齐表均以"两条记录逐字段一致"表述 actor wakeup 双记录（wakeup 记录 + `kind="wakeup"` 队列条目）——但两种记录形态不同：P1 冻结 `ActorWakeup`（`state.py:158-166`）= `actor_id`/`due_tick`/`reason` 三字段（`reason` 可空，`state.py:166`），而 §2.5 表钉死的 `kind="wakeup"` 队列条目必填 payload 键 = 仅 `actor_id`——"逐字段一致"字面不成立（`reason` 不在 payload 中）。现改写为与 P1 冻结现实精确一致的口径：两条记录在 `(actor_id, due_tick)` 上一致；`kind="wakeup"` 队列条目 payload 仅携带 `actor_id`（§2.5 表不变），`ActorWakeup.reason` 仅存于 `actor_wakeups` 记录侧、不入 payload。同步：§2.4 伪代码注释、§2.5 尾注、§3.8 docstring、§6.1 两用例、§8.1 `ActorWakeup` 行。P1 源码零改动：P1 docstring 不含双记录规则条款——`RuntimeState` 类 docstring 的 `actor_wakeups` 项（`state.py:203`）仅"占位（P4 语义）"声明、`ActorWakeup` 类 docstring（state.py:158-162）仅钉 `actor_id` 为 `EntityId`（Spec §12.1）——口径钉死责任在 P3 新契约侧，§2.5 表与 P1 冻结字段无矛盾，均保留。
- **原因**：探针事实：`ActorWakeup`（state.py:164-166）= `actor_id: EntityId` / `due_tick: int` / `reason: str | None = None`；`RuntimeState.actor_wakeups: list[ActorWakeup]`（state.py:222）；`ScheduledEvent` 队列条目 payload 契约为 P3 自定词表（§2.5，`make_scheduled_event` 入队点强制校验）。"逐字段一致"口径下须把 `reason` 塞入 payload（违背 §2.5 表、破坏 `make_scheduled_event` 必填键校验口径）或视两条记录同构（与冻结字段集矛盾），纯执行者无实现依据；改写后 §6.1 测试口径可机械断言（两条记录 `(actor_id, due_tick)` 相等 + payload 键集 `{"actor_id"}`）。（R6 出处：S3 补充2。）

### E-P3-36（F5-03）`pause_on_player_boundary=False` 重裁为 record-only（消解僵尸路径；重裁 E-P3-32① 中断部分）
- **内容**：重裁 F4-03/E-P3-32① 的中断部分：原 False 口径"仍按 `boundary.interrupt` 中断（INTERRUPTED）+ 不暂停继续推进"推演产生僵尸路径——t=12 边界中断 act_1（INTERRUPTED）→ ff 继续 → t=20 cp@20 被 `apply_checkpoint` 非 ACTIVE 守卫 no-op 消费（`checkpoint_skipped_interrupted`，不重入队）→ t=30 end@30 被"到点且 ACTIVE"守卫跳过消费 → 队列耗尽 → act_1 永久滞留（INTERRUPTED 无锚点；若玩家 resume，end 条目已消费且无重入队规则 → 永久 ACTIVE、`progress_of` 钳制 1.0、永不 COMPLETED），而 `resume_action` 防御分支只补 checkpoint 不补 end。现重裁为 **record-only**：`pause_on_player_boundary=False` → 玩家 blocking 边界命中仍 fired（`BoundaryReport.fired` + trace 留痕）但**不中断**可中断行动（行动生命周期照常推进：checkpoint/end 条目正常处理、行动正常 COMPLETED），且不返回暂停、继续推进至本次调用终点（max_tick/terminal）；D-P3-24 入口重报规则不生效（以本标志为前置）；缺省 True = 现口径（Gate 场景，D-P3-24 全部行为不变）。僵尸路径由构造消解：False 路径下行动永不被中断、其条目全部正常消费。同步：§3.8 `TimePolicy` 字段位注释改写；§2.4 伪代码重构（玩家 blocking 分支的中断迁移与 paused 返回**同受** `time_policy.pause_on_player_boundary` 门控——True = 中断 + 暂停，False = 跳过两者；边界 fired 记录 + trace 照常；npc 分支不受辖制）；§2.4 入口首检注释与 §3.8 `fast_forward` docstring 的标志前置表述补"不中断"；§6.1 `scheduler.py` 用例补 flag=False 探针（边界 fired + 行动仍 ACTIVE + cp@20/end@30 正常处理 + COMPLETED + 无暂停 + ff 推进至 terminal）；§0 文档地位行 R6 注记。G3-1 的 17 条断言（9+4+4）、Gate（True 路径）全部时序与断言、A7 幂等重报全部不变；D-P3-25 NPC 非阻塞中断口径不受本标志辖制、不变。
- **原因**：原裁定（R5/F4-03）把"不返回暂停"等同于"照常推进"，未计及 INTERRUPTED 行动的 cp/end 条目被守卫消费后**无重入队规则**——队列条目剪除仅发生于进入终态（D-P3-25），守卫 no-op 是"消费不重入队"路径而非剪除路径，僵尸（INTERRUPTED 无锚点 / resume 后 end 条目已消费 → 永久 ACTIVE 永不 COMPLETED）为必然结局，`resume_action` 防御分支 `checkpoint_requeued_after_defect` 只补 checkpoint 不补 end；重裁 record-only 把"中断"移出 False 路径，行动生命周期与队列消费自然对齐（僵尸路径构造上不存在），Gate 场景（缺省 True）全不受影响。本条为规则层重裁（规格补全性质不变、无新增决策、§4 27 项不变）。（R6 出处：S3 补充3。）

### E-P3-37（F7-01）D-P3-20 理由段 ids.py 工厂区间 `223-234` → `232-265`（就地更正；取代 E-P3-21/E-P3-33 该处裁定）
- **内容**：D-P3-20 理由段把 `event_id`/`transaction_id`/`entry_id` 三个 uuid4 工厂统引为「`ids.py` 工厂（uuid4 hex，ids.py:223-234）」——该区间客观不覆盖被点名的 `new_transaction_id`（L237-239）与 `new_scheduled_entry_id`（L263-265）：点名却不含其行号，R3（E-P3-21）/R5（E-P3-32②(b)）/R7（S1 补充1）三轮被独立标记。现就地更正为 `ids.py:232-265`（覆盖该句点名的三个工厂：`new_event_id` L232-234、`new_transaction_id` L237-239、`new_scheduled_entry_id` L263-265，ids.py 行号经只读探针核验）。**本条取代 E-P3-21「D-P3-20 规范正文『ids.py:223-234』区间有效，不改」与 E-P3-33「D-P3-20 理由段『223-234』……保留不动」两处裁定**——当时按 §9 纯追加约定不回改的是勘误条目体内的历史记录裁定，而该处为**现行正文的规范性引用**、区间不完整属实（非历史记录），故现时更正成立；E-P3-21 条目自身内容（其对 E-P3-03 的引用更正记录）其余部分不动、不回改。
- **原因**：规范性引用区间必须覆盖其所点名工厂的行号，否则纯执行者核验引用即撞不一致（三轮独立标记为证）；更正对象为正文规范引用而非勘误留痕，属正文同步修改（§9 约定「正文相应位置已同步修改，两处若仍冲突，以本勘误为准」），与 E-P3-33 就地更正 E-P3-32②(b) 的机制同类。（R7 出处：S1 补充1；S3 风险1 为同处非致命注记。）

### E-P3-38（F7-04）`causal_root_id` P2 冻结 docstring（cascade.py:882-884）与 F2-15 `entry_id` 口径的偏离披露
- **内容**：F2-15 钉死「`causal_root_id` = 驱动该批的队列条目 `entry_id` 字符串（`sch_` 前缀）」（§3.8）；P2 冻结面 `cascade.py:882-884` docstring（原文核验）为「causal_root_id: **必填**（Spec §21.3）——级联根（调用方传入 ActionInstanceId / EventId 的字符串形态；执行器自身不发明根身份，P3 调度器启动级联时以 action 实例为根）」——系对 P3 用法的示例性表述，原设计文档从未声明该表述被取代（本条补披露）。现钉死：**docstring 示例表述（『以 action 实例为根』）被 F2-15 的 `entry_id` 口径取代**——`entry_id` 覆盖全部条目 kind（kind=event 无 action 实例可指，action 实例根表述对其不可适用）；该 docstring 属 P2 冻结面不可修改；run 守卫（cascade.py:906-914）仅要求非空 str + origin 为 Provenance → `sch_` entry_id 合规，因果链仍经 cause_ids/trace 确定性闭合；无任何 Gate 断言依赖 `causal_root_id` 的值。同步：§3.8 F2-15 段补偏离披露句、E-P3-23③ 补交叉引用。
- **原因**：F2-15 口径与冻结 docstring 示例表述并存且无取代声明——纯执行者读 P2 docstring 可能选『以 action 实例为根』，而 kind=event 条目（Gate 场景 t=12 encounter 正是 `kind="event"`）无 action 实例可指，将无执行依据（K7 违背）；披露后唯一口径 = F2-15。（R7 出处：S4 补充1。）

### E-P3-39（F7-02/F7-03/F7-05/F7-06 + R7-01 ~ R7-05 合并）九项文档级口径（transitions 承诺 / Spec 锚点 / 指纹签名与输入面 / BUILTIN 缺省注记 / wakeup 缺省 / 门面返回类型 / event payload 互斥 / submit_proposal 次序 / cause_ids 引用区间）
- **内容**：①（F7-02）S8 outcome.transitions 承诺与 `apply_checkpoint` 钉死签名矛盾——`apply_checkpoint -> tuple[RuntimeState, TraceRecord | None]`（L430-432/E-P3-12②）不携带迁移记录、§2.4 伪代码 checkpoint 分支无捕获点，S4 的 CHECKPOINT 迁移在钉死契约下无法进入 outcome.transitions；现三处正文（§5.2 S8 行、D-P3-19 选择、D-P3-18 一致性）统一改为「`transitions=[S7 (INTERRUPTED@12)]` 一条」，并在 S8 行/D-P3-19 注明：S4 的 CHECKPOINT 迁移为 `apply_checkpoint` 内部簿记、不出现在 outcome.transitions，可在模块级直调层断言（§6.1 action_lifecycle 用例已覆盖）。D-P3-19「start_action 恒 2 条记录」口径与此无关、保持不变；17 条 G3-1 断言不引用 outcome.transitions（已核验）、事务计数/revision 口径全部不变。②（F7-03）`DecisionBoundary` 两处「Spec §23.3 单列概念」锚点错位——Spec §23.3（L1310-1318）显式清单仅 ScheduledEvent/ActiveAction/ActorWakeup/Deadline/InterruptCondition 五项、不含 DecisionBoundary；术语出处为 §23.2 L1305（『→ player decision boundary』）；现两处（§3.1 命名表 interrupt.py 行、§3.7 类注释）均改为「Spec §23.2 decision boundary 概念（Spec L1305）；DecisionBoundary 为 P3 新增单列类型、定位为 §23.3 SHOULD 显式状态清单的扩展项（清单为 SHOULD 非穷举，扩展不构成违背）」；D-P3-09「Spec §23.3（InterruptCondition 单列）」引用正确、不动。③（F7-05）`scheduler_fingerprint` 参数无类型、输入面未钉——现签名钉死 `scheduler_fingerprint(registry: ActionRegistry, time_policy: TimePolicy, boundaries: tuple[DecisionBoundary, ...]) -> str`（替换无类型 `config` 单参；不新增导出符号、53 分解不变）；输入面钉死 registry + TimePolicy + boundaries 三项（原 L599 注释「registry + TimePolicy」遗漏 boundaries——若不含 boundaries，篡改边界字段不改变指纹、G3-4(d) 对该字段不可满足）；规范化 JSON 口径钉死：按各 Pydantic 模型 `model_fields` 顺序做纯 dict 投影 → `json.dumps(sort_keys=True, ensure_ascii=False, separators=(",", ":"))` → sha256 hex（唯一、确定性，K7）；排除面显式声明：named_triggers/trigger_registry（callable/SyncTrigger 闭包，非可序列化）不入指纹——Gate fixture 触发器为确定性纯函数、G3-4 判据在测试层机械可验证（已披露设计选择）；§6.2 G3-4(d) 行同步为「registry/TimePolicy/boundaries 各篡改一字段 → 指纹不等 → 回放显式拒绝（三条探针）」、§6.1 scheduler 测试行同步。④（F7-06）`BUILTIN_CONDITION_RESOLVERS` 共享缺省实例防御注记：共享缺省实例为 Final；对共享缺省实例调用 register 属配置错误（实现方须自建 registry 传入）；Gate fixture 全部显式构造、不受影响。⑤（R7-01）`wakeup_hooks` 缺省占位 `WakeupHookRegistry = ...` 未钉——现 §3.8 签名改 `wakeup_hooks: WakeupHookRegistry | None = None`：缺省 None → 空 `WakeupHookRegistry`；wakeup 条目命中时无 hook 可调 → 仅输出诊断（TraceRecord，SYSTEM）、不崩溃、不影响簿记；D-P3-14 一致性段同步、§5.1 Gate fixture 省略该参数处补注「走空注册表缺省」。⑥（R7-02）门面 `resume_action`/`abort_action` `-> ...` 与模块级完整签名对齐：`resume_action -> tuple[WorldState, RuntimeState, LifecycleTransition]`、`abort_action -> RuntimeState`（模块级 L454-455/L462-463 已核验）。⑦（R7-03）`kind="event"` payload 的 `trigger_id`/`effects`「二选一」但错误规则仅覆盖「两者皆缺」——现钉死：缺 `trigger_id` 且无 `effects`，或两者同时存在 → `QueueInvariantError`（互斥，唯一口径）；§2.5 表行改「恰居其一（互斥，均声明式）」。⑧（R7-04）`submit_proposal` 内部次序钉死（§3.8 docstring）：1) registry 查找（未注册 action_id → `UnknownActionError` → FAILED 轨迹，reason="unknown_action"，D-P3-16/A5 口径，错误路径不创建 PROPOSED 记录）；2) revalidate_proposal（§3.9）；3) ACCEPT → 创建 PROPOSED ActiveAction 记录 + start_action 复合 2 条迁移（D-P3-19）——确保 A5 错误路径不产生悬空 PROPOSED 记录。⑨（R7-05）全文「cascade.py:479-481」（cause_ids 协议义务）→「cascade.py:481-483」（义务条款实际位于 L481-483，只读探针核验）——D-P3-27 问题/选择与 §5.1 通用契约共三处同步。
- **原因**：九项均为文档级口径/引用修正：① 三处承诺在钉死契约下不可同时满足（17 条断言不引用该字段，属局部修正，Leader 裁定选 b：不改钉死签名、只改承诺口径）；② 锚点错位（清单不含该类型、术语出处为 §23.2）；③ 无输入面则 G3-4(d) 对边界字段不可满足、无签名则纯执行者无指纹实现依据（K7）；④ 共享可变缺省可跨实例泄漏（防御注记，Gate 不受影响）；⑤ `...` 占位非可执行缺省值；⑥ 占位返回类型与模块级钉死签名不一致；⑦ 双在形态错误规则未覆盖（声明式 payload 校验缺口，违「可检查不静默」）；⑧ 次序未钉、纯执行者被迫选择（先落 PROPOSED 则 A5 错误路径留悬空记录）；⑨ 引用区间与源码行号不符（引用机械核验为 P3 惯例）。全部不触碰 17 条 Gate 断言（9+4+4）、249/53 符号分解、M1 200 条、progress 序列、迁移边集与三锚点。（R7 出处：S3 补充1（①）、S3 补充2（②）、S4 补充2（③）、S2 风险2（④）、S4 风险1（⑤）、S4 风险2（⑥）、S4 风险3（⑦）、S4 风险4（⑧）、S4 风险5（⑨）。）

**勘误合计**：E-P3-01 ~ E-P3-39 共 **39 条**（BLOCK 2 条单列；R2 措辞/事实类合并为 E-P3-10 一条；R3 补充轮 E-P3-11 ~ E-P3-23 共 13 条，F2-01~F2-04 单列、F2-13~F2-16 合并一条；R4 补充轮 E-P3-24 ~ E-P3-29 共 6 条，F3-01~F3-05 单列（E-P3-24 含 L3-01 留痕）、L3 轻量项与 F3-06 合并为 E-P3-29 一条；R5 补充轮 E-P3-30 ~ E-P3-32 共 3 条，F4-01（E-P3-30，含 E-P3-24 R5 注记补录）、F4-02（E-P3-31）单列、F4-03 与 L4-01 合并为 E-P3-32 一条，列明覆盖项；R6 补充轮 E-P3-33 ~ E-P3-36 共 4 条，L5-01（E-P3-33，就地更正 E-P3-32②(b) 区间）单列轻量注记、F5-01（E-P3-34）、F5-02（E-P3-35）、F5-03（E-P3-36，重裁 E-P3-32① 中断部分）单列，留痕；R7 收尾轮 E-P3-37 ~ E-P3-39 共 3 条，F7-01（E-P3-37，就地更正 D-P3-20 理由段工厂区间、取代 E-P3-21/E-P3-33 该处裁定）、F7-04（E-P3-38，F2-15 `causal_root_id` 偏离披露）单列，F7-02/F7-03/F7-05/F7-06 与 R7-01 ~ R7-05 合并为 E-P3-39 一条、列明九项覆盖项，留痕）。本勘误落定后 §9 无"暂无"遗留项。

---

## 10. 未决问题

**无。**

裁定说明（供 Gate 复核，均已在正文留痕，不构成 Spec/计划/P1 硬性矛盾）：

1. 任务书"ScheduledEvent 新类型"预期 vs P1 冻结现实——按最高约束（P1 零改动）裁定为复用（§8.5-D1，D-P3-04）；如需新类型须先走 P1 解冻流程，属 Gate 职权而非 P3 设计裁量；
2. Spec §11.4 建议图示 vs Plan Gate resume 要求——按效力层级（Gate 判据 > 建议图示）裁定新增 RESUMED 边（§8.5-D2，D-P3-07）；
3. 时间单位 1 tick = 1 分钟——Spec/计划均未固定单位（Spec §23.1 只要求"区分"六层），Plan Gate 数字（30/12/12/30）直接支持该默认映射，P5 内容层可随时以换算常数覆盖（D-P3-01），不构成未决项。

---

*文档完。本设计不改变任何已冻结 P1 public contract 与 P2 已交付行为；实现过程中若出现与本文档的偏差，须按 Plan §10「public contract 修改必须经 Gate review」披露。P3 各任务包以本文档为唯一执行依据。*
