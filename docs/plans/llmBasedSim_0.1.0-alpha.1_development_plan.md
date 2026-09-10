# llmBasedSim 0.1.0-alpha.1 详细开发计划

> 目标：在不超过 12 小时的开发预算内，将当前 `architecture-v2` 推进到一个可发布、可用于真实 GameProject 验证的 `0.1.0-alpha.1`。
>
> 本文只规定“针对引擎本身需要执行什么开发任务”。不规定、也不假设用于验收的具体游戏题材、玩法、数值、角色、物品或物理模型。

---

## 1. 版本定位

`0.1.0-alpha.1` 不是完整 Architecture v2 的实现，也不是 RC。

它是第一个要求满足以下条件的可用版本：

1. GameProject 中已有的核心作者数据能够被正确物化为 tick-0 authoritative `WorldState`；
2. 项目能够注册并执行自定义 ActionExecutor；
3. 项目能够注册并执行自定义 DynamicsBackend / 数值后端；
4. 自定义逻辑只能通过 `ProposedEffect → Authority → Transaction → Reducer` 修改 authoritative state；
5. component 写入与 Kernel state-domain 写入都能通过正确的 authority grant；
6. 项目能够维护独立于 `logical_tick` 的游戏世界时间，并允许世界时间推进速率由当前状态决定；
7. 存在一个 production-only 的最小运行入口和 E2E 验收路径；
8. 可以从干净环境安装并重复运行。

本版本优先验证 Kernel/runtime extension seam 是否真正可用于游戏开发，而不是补齐完整产品面。

---

## 2. 12 小时约束

### 2.1 总预算

| 工作包 | 预算上限 |
|---|---:|
| M1 — 初始状态物化修复 | 2.5 h |
| M2 — state-domain authority grant 修复 | 1.0 h |
| M3 — runtime extension seam 收口与必要测试 | 2.0 h |
| M4 — production-only E2E / runner | 2.5 h |
| M5 — alpha release closure | 1.0 h |
| 调试与回归缓冲 | 3.0 h |
| **总计** | **12.0 h** |

时间预算是 scope guard。某项任务超时，应优先缩小实现，而不是自动扩大 alpha.1 范围。

---

# 3. M1 — 修复 tick-0 initial-state materialization

## 3.1 当前问题

当前 `GameProject → ProjectIR → materialize_world()` 链路只物化了部分作者数据。

已有 P5 schema 中已经存在：

- Player attributes；
- Player inventory；
- Character attributes；
- Character starting inventory；
- Character relationships 等作者数据；
- Item/Object 的 `state`；
- Item/Object 的 `properties`；
- item identity / description / type 等基础信息。

但 production materializer 没有把这些数据完整投影到 authoritative WorldState。

当前 reference example 通过 executor / dynamics 的“首次访问自举”绕过该缺口。这种方式不能作为 alpha.1 的正式能力边界。

## 3.2 必须实现

修改 production materialization，使已有 P5 authoring data 在 tick 0 直接形成 authoritative components。

至少需要稳定以下投影：

### A. Attributes component

Player 和 Character 的作者数值字段进入统一 component。

建议 canonical component id：

```text
attributes
```

要求：

- 保留 JSON-clean 数据；
- 不引入 RPG 专属字段；
- engine 不解释字段语义；
- 空值行为确定；
- materialization deterministic。

### B. Inventory component

Player / Character 的初始 inventory 进入统一 component。

建议 canonical component id：

```text
inventory
```

要求：

- inventory 引用必须落为 authoritative entity ID；
- 不在 WorldState 内同时保留 authoring slug 与 authoritative id 两套身份；
- materialization 时解析不存在的 item reference 必须形成明确 diagnostic，而不是静默丢弃；
- engine 不规定 inventory 容量、堆叠、装备槽等玩法语义。

### C. Item/Object component

ObjectSpec / Item 的作者数据进入统一 component。

建议 canonical component id：

```text
item
```

至少允许承载：

```text
name
description
object_type
state
properties
```

其中 `state` / `properties` 作为开放 JSON 数据保存。

要求：

- engine 不理解 `properties` 内部业务含义；
- 不为攻击、防御、耐久、价格、重量等预定义字段；
- custom executor / numerical backend 可以读取这些字段自行解释。

## 3.3 明确不做

alpha.1 不新增任意：

```yaml
components:
  ...
```

形式的通用 component authoring DSL。

原因：现有 P5 数据字段已足够验证 runtime seam。通用任意 component authoring 属后续 authoring ergonomics，而不是本版本 Kernel blocker。

同样不实现：

- derived attributes；
- attribute lock rules；
- inventory stack；
- equipment slots；
- item container nesting；
- generic relationship runtime；
- item lifecycle framework。

## 3.4 测试

新增/修订 materialize tests，至少覆盖：

1. Player attributes 正确进入 WorldState；
2. Character attributes 正确进入 WorldState；
3. Player inventory 正确解析为 entity IDs；
4. Character starting inventory 正确解析为 entity IDs；
5. Item `state` / `properties` 不丢失；
6. 同一项目两次 materialize 得到结构相同的 WorldState；
7. dangling item reference 产生稳定 diagnostic；
8. JSON round-trip 不改变上述内容。

## 3.5 完成标准

禁止继续依赖“首次 interaction 时初始化 component”的 workaround 才能得到完整初始世界。

---

# 4. M2 — 修复 state-domain authority grant

## 4.1 当前问题

当前 runtime assembly 将 extension / dynamics 的 grant 统一解释成：

```text
AuthoritySelector(component_type=...)
```

但 `StateDomainTarget` 的 authority matching 不能匹配 `component_type` selector。

因此对以下 Kernel state domain 的正式写入存在 production gap：

```text
world_variables
scenario_state
```

最终可能导致合法的：

```text
DynamicsBackend
→ ProposedEffect(core.set_world_variable)
→ Authority
→ DENY
```

## 4.2 必须实现

在 runtime assembly 的 grant → AuthorityRule 转换层明确区分：

### Component domain

生成：

```text
AuthoritySelector(component_type=<component>)
```

### Kernel state domain

若 grant domain 属于 `KERNEL_STATE_DOMAINS`，生成：

```text
AuthoritySelector(domain_tag=<state-domain>)
```

不得通过修改 `match_selector()` 放宽规则来掩盖 assembly 错误。

## 4.3 必须保持

- Authority 继续 closed-by-default；
- 未声明 writer 不自动获得权限；
- 不降低 selector specificity；
- 不引入 broad allow-all rule；
- 不绕过 Cascade / Transaction；
- 不因 alpha convenience 改为 permissive runtime。

## 4.4 测试

至少增加：

1. extension executor 对普通 component 的合法写入仍可 commit；
2. dynamics backend 对普通 component 的合法写入仍可 commit；
3. dynamics backend 对 `world_variables` 的合法写入可 commit；
4. 未获授权 producer 写 `world_variables` 必须被 deny；
5. component grant 不应意外获得 state-domain 写权限；
6. state-domain grant 不应意外获得普通 component 写权限。

## 4.5 完成标准

正式 production assembly 下：

```text
custom producer
→ StateDomainTarget
→ Authority ALLOW
→ Transaction COMMITTED
→ Reducer
```

链路成立。

---

# 5. M3 — 收口 alpha.1 所需 runtime extension seam

本工作包不新增新的 extension architecture，只确认并修复当前公开 seam 中会直接阻断真实 GameProject 的问题。

## 5.1 ActionExecutor

必须保证：

```text
ActionProposal
+ read-only WorldState
→ ExecutorResult
```

能够稳定支持：

- 读取任意现有 component；
- 读取 item/object properties；
- 返回 0..N 个 ProposedEffect；
- 一个 action 产生多个跨实体 / 跨组件 effect；
- failure 返回零 authoritative mutation；
- deterministic execution。

## 5.2 Custom physics / numerical solver

引擎不内置游戏物理语义。

alpha.1 只要求 ActionExecutor 可以调用项目侧任意纯 Python solver，例如：

```text
ActionExecutor
    ↓
custom solver
    ↓
structured outcome
    ↓
ProposedEffect(s)
```

solver 必须仍遵守：

- 不直接写 WorldState；
- 不持有 authoritative mutable reference；
- authoritative outcome 必须转换为 ProposedEffect；
- effect 继续经过 Authority / Validation / Conflict Resolution / Transaction / Reducer。

不实现 Action → Stimulus → DynamicsBackend 的完整事件路由。

## 5.3 DynamicsBackend

必须确认 project extension 可以注册 custom dynamics backend，并且：

```text
WorldSnapshot
+ DynamicsContext
→ ProposedEffect(s)
```

在 production `EngineInstance.advance()` 中工作。

允许 backend：

- 读取 arbitrary components；
- 读取 world variables；
- 做确定性数值积分；
- 写 component；
- 写获授权的 Kernel state domain。

## 5.4 Dynamic world-time

alpha.1 必须支持项目把：

```text
logical_tick
```

和

```text
world_time
```

视为不同概念。

实现要求：

- Kernel `logical_tick` 继续保持单调离散步；
- world time 存在于 authoritative WorldState；
- DynamicsBackend 可以根据当前 WorldState 决定本 logical tick 对应多少 world-time increment；
- engine 不硬编码 day/night、分钟/小时等语义。

禁止为了此功能改造 P3 Scheduler。

## 5.5 Extension contract 验证

新增一个通用测试 extension，不绑定具体玩法，用于验证：

- custom executor 注册；
- custom dynamics 注册；
- producer grant；
- component write；
- state-domain write；
- multi-effect transaction；
- deterministic repeatability。

---

# 6. M4 — Production-only E2E 与最小运行入口

## 6.1 目标

必须有至少一个路径能够真正调用：

```text
load_project
→ build_ir
→ validate_project
→ materialize_world
→ load_extensions
→ bind_actions
→ bind_dynamics
→ authority assembly
→ EngineInstance
→ submit_action / advance
```

不得以 test-only helper 拼装 WorldInstance 来冒充 production E2E。

## 6.2 Runner

实现一个最小 alpha runner。

可以是：

```text
scripts/...
```

或轻量 CLI 子命令。

必须支持最少：

- 指定 project root；
- `trust_python` 显式开启；
- assemble project；
- 提交一个 action；
- advance runtime；
- 输出当前 world state / scene / trace 中足以验证执行结果的信息。

不要求：

- TUI；
- Web；
- 游戏菜单；
- 完整 command grammar；
- LLM；
- interactive narrative；
- hot reload。

## 6.3 E2E 必须覆盖的能力形状

测试内容应使用中性测试数据，不绑定某一具体游戏题材。

必须证明：

1. 作者数值进入 tick-0 world；
2. 初始 item entities 与 inventory 成功建立；
3. item properties 可供 executor 读取；
4. custom action 可以调用独立 solver；
5. solver outcome 可以产生多条 ProposedEffect；
6. 多条合法 effect 可以通过 authority；
7. effect 通过 transaction/reducer 后改变 authoritative state；
8. dynamics 能修改普通 component；
9. dynamics 能修改 world variables；
10. world-time increment 可以由当前 WorldState 动态选择；
11. action failure 不改变 WorldState；
12. authority deny 不改变 WorldState；
13. 相同初始项目 + 相同 action/advance 序列得到相同最终状态；
14. production E2E 不 import tests。

---

# 7. M5 — Release Closure

## 7.1 Version

Python package 使用 PEP 440：

```toml
version = "0.1.0a1"
```

Git tag / release display name可使用：

```text
v0.1.0-alpha.1
```

不要混淆 package version 与人读 tag。

## 7.2 README

增加 alpha.1 capability boundary：

必须明确：

- 这是 alpha；
- 支持什么；
- 暂不支持什么；
- Python extension 需要 trust flag；
- 最小安装方法；
- validate 方法；
- run / smoke 方法；
- extension contract 的最简入口。

## 7.3 Clean-install smoke

从全新 virtual environment：

```text
install
→ import
→ llmsim validate
→ alpha runner
→ production E2E
```

全部成功。

## 7.4 Regression

至少运行：

- engine_v2 core tests；
- runtime tests；
- materialization tests；
- extension tests；
- alpha-specific E2E。

如果完整历史测试可在预算内完成，则运行全套；但不得为了修复与 alpha.1 无关的历史测试耗尽 12 小时预算。

---

# 8. 明确延期到 alpha.1 之后

以下内容不得自动进入本版本：

- ProjectIR declarative Authority 完整 wiring；
- P5 DSL → WorldRule translator；
- P3 Scheduler production integration；
- long action lifecycle；
- action → dynamics Stimulus routing；
- dynamic logical-tick duration；
- generic arbitrary component authoring DSL；
- 完整 P9 Attributes runtime integration；
- 完整 P9 Inventory runtime integration；
- equipment framework；
- relationship framework；
- LLM NPC 作为 release gate；
- Web presentation；
- DSH integration；
- agent-native control plane；
- persistence；
- save/load UX；
- replay UI；
- branching；
- graphical debugger；
- scenario framework 完整 integration；
- dependency/license 全面治理；
- v1 删除；
- default branch 最终迁移。

---

# 9. Scope Stop Rules

开发过程中出现以下情况时，不得直接扩 scope：

### Rule 1

若某功能似乎要求修改 P3 Scheduler：

> 先证明它不能用 `logical_tick + world_time state` 表达。

### Rule 2

若某玩法似乎要求修改 Kernel：

> 先证明它不能通过 custom component + ActionExecutor + DynamicsBackend + ProposedEffect 表达。

### Rule 3

若需要新的 authoring syntax：

> 先证明现有 P5 fields 与 extension-side interpretation 无法表达 alpha 验收数据。

### Rule 4

若要补 LLM / Web / DSH：

> 直接延期，除非它阻断 headless GameProject production runtime。

### Rule 5

reference project 不得靠 test helper、私有 state mutation 或 runtime monkey patch 才能工作。

---

# 10. alpha.1 Release Gate

只有以下全部成立，才允许标记 `0.1.0-alpha.1`：

- [ ] GameProject 可以形成足够完整的 tick-0 authoritative WorldState；
- [ ] attributes / inventory / item authoring data 不依赖首次访问自举；
- [ ] item references 已转换为 authoritative entity IDs；
- [ ] custom ActionExecutor production binding 正常；
- [ ] custom numerical/physics solver 可由 executor 调用；
- [ ] 一个 action 可以返回多个 ProposedEffect；
- [ ] custom DynamicsBackend production binding 正常；
- [ ] component grant 正常；
- [ ] Kernel state-domain grant 正常；
- [ ] world variables 可经正式 authority pipeline 修改；
- [ ] world-time increment 可依赖当前 WorldState；
- [ ] authoritative state 不存在 extension 直接写路径；
- [ ] failure / deny 路径不改变 authoritative state；
- [ ] deterministic replay-by-input 最少通过一次 E2E 验证；
- [ ] production E2E 不依赖 tests；
- [ ] clean install smoke 通过；
- [ ] package version 与 alpha tag 正确；
- [ ] README 明确 alpha capability boundary。

如果上述条件满足，即使完整 Architecture v2 仍有大量未实现项，也应发布 alpha.1，而不是继续扩大版本范围。
