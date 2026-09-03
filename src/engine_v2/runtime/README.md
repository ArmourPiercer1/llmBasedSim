# engine_v2.runtime — production game path（12h closure，2026-09-04）

`GameProject → WorldInstance → EngineInstance` 的生产装配与运行层。本包是
P5 content / P2-P9 core 之上的 **composition 面**：零新框架、零 P5 schema
扩展、零第三方依赖；所有世界写只经 `ProposedEffect → Authority →
Transaction(commit_transaction) → Reducer`（K2）。

## 单入口

```python
from src.engine_v2.runtime import assemble_project, EngineInstance

result = assemble_project(
    "examples/complex_minimal",
    trust_python=True,                # False = 声明插件零 import（诊断显式）
    # deployment=DeploymentProfile(...),     # 缺省 = headless（LLM NPC 关，warning）
    # inference_backend=FakeInferenceBackend(...),
)
engine = result.engine                # 致命诊断 → None + result.diagnostics 全链
engine.advance(ticks=1)               # 五相位：due wakeups → policy/executor →
                                      # dynamics（同一提交管道）→ lifecycle → 时钟
engine.submit_action("ent_authoring_operator", "inject_heat", {})
engine.view()                         # derive_scene_view(committed world)
```

## 模块台账（T1–T9；导出 = `__init__.py` 台账）

| 模块 | 公开面 | 职责 |
|---|---|---|
| `assembly` | `assemble_project` / `AssemblyResult` | 唯一装配入口（13 步固定序） |
| `world_instance` | `WorldInstance` | 13 字段 frozen 装配面（seam） |
| `materialize` | `materialize_world` / `WorldMaterialization` / `CHARACTER_PROFILE_COMPONENT` | ProjectIR → WorldState + RuntimeState + SpaceRegistry + ComponentRegistry（grid 缺省） |
| `engine` | `EngineInstance` / `StepResult` | 生产 tick 循环；唯一提交管道（内部 CascadeExecutor） |
| `extensions` | `load_extensions` / `ExtensionBundle` / `ExtensionContext` / `ExtensionLoadResult` / `ProducerGrant` | 信任 Python 激活：`plugins/*/plugin.yaml` + IR descriptor 双源；`trust_python=False` 零 import；唯一动态 import 位点（P5 gate #6b 单点纪律） |
| `context` | `build_actor_context` / `build_actor_context_for_wakeup` | ActorDecisionContext：self/visible/local/global 分区；缺省 `global_entity_views=None` |
| `llm_binding` | `bind_llm_policies` / `LLMBindingResult` | P6 `build_llm_policy` 复用绑定（capability `npc_policy`）；`resolved_models` 审计面 |
| `action_binding` | `bind_actions` / `ActionBindingResult` | 标准面（register_standard_actions，仅 MoveExecutor）+ project 声明面 + extension executors 合并 + action 侧 ProducerGrant |
| `dynamics_binding` | `bind_dynamics` / `DynamicsBindingResult` | extension dynamics 透传 + metadata → grant 自动派生；P5 DSL 规则不投影（逐条 warning） |
| `observability` | `RuntimeTraceSink` / `InMemoryTraceSink` / `TraceEvent` | 生产内存 trace（= P6 TraceSink 三方法结构同形；零墙钟/uuid/IO） |

## 授权面（closed-by-default）

`AuthorityPolicy(default_decision=DENY)`；规则仅来自装配期显式
`ProducerGrant`（action 侧 T6 / dynamics 侧 T7 / extension 声明 T3）：
每 grant × 每 component_type 一条 `AuthorityRule`。IR 层 authority 声明
**不进**合并。producer 未注册 / 未授权 → `authority_denied` 诊断，世界不变。

## 确定性（K7）

同 GameProject + 同装配参数 + 同输入序列 → `dump_json(world)` 字节相等
（reference game 双跑实证；trace seq 自增，零时间戳）。LLM 侧确定性由
注入的 `InferenceBackend` 保证（CI/测试用 `FakeInferenceBackend` 脚本化）。

## 边界

- 生产路径零 `tests.*` import（E2E Gate C1 机械守卫）。
- 长动作生命周期（start/complete 两跳）、引擎相位级 trace 接线、P5 DSL
  规则 → WorldRule 翻译器 = 显式 follow-up（见各模块 docstring assumptions）。
- reference game：`examples/complex_minimal`（锅炉房值守；自定义 executor ×3
  + 数值热力学 backend + 中文 NPC）。
