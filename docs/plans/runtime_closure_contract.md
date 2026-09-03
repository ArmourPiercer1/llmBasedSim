# Runtime Closure — Frozen Contract（Leader freeze 2026-09-03）

唯一接口权威（计划 §3 逐字 + seam facts）。不重做设计；发现 blocker =
停手 + ≤5 行 note 返回 Leader。本文件与计划同目录，勿改。

## 0. 纪律（全部 task）
- 新代码只写本 task 的 owned file + 对应 test file（§5 表）；需要动别人
  的 owned file → 停手 + note。
- **Leader-only hot files 禁碰**：`runtime/__init__.py`、`pyproject.toml`、
  `README.md`、`docs/**`。需要 export → handoff 列出，Leader 统一。
- **禁止 git 操作**。只跑 targeted：
  `PYTHONPATH=. .venv/bin/python -m pytest tests/engine_v2/runtime/test_<你>.py -q -p no:cacheprovider`
- `src/**` 零 `import tests` / `from tests`；零 `rglob("*.py")` / 项目树
  walk / exec 任意文件；零 P5 schema 扩展（`content/schemas.py` 不动）。
- NPC LLM 默认 capability = `npc_policy`（`DeploymentProfile.inference_profiles`
  键）。K2：一切世界写入只能经 ProposedEffect → Authority → Transaction →
  Reducer；零直写 WorldState。
- handoff ≤50 行：changed files / tests+result / public symbols /
  assumptions / blockers(≤5)。

## 1. WorldInstance（T1 产 WorldMaterialization；T9 组装；字段冻结）
```python
@dataclass
class WorldInstance:
    world_instance_id: str
    ir: ProjectIR
    world: WorldState
    runtime: RuntimeState
    spaces: SpaceRegistry
    action_registry: ActionRegistry
    executors: dict[str, ActionExecutor]
    policies: dict[str, BehaviorPolicy]
    dynamics: tuple[WorldDynamicsBackend, ...]
    component_registry: ComponentRegistry
    producer_registry: ProducerRegistry
    authority_policy: AuthorityPolicy
    trace_sink: RuntimeTraceSink
```
RuntimeTraceSink = T8 协议（`runtime/observability.py`：`record /
store_artifact / record_diagnostic`）。T1 的 `WorldMaterialization` 只含
`world / runtime / spaces / component_registry`（+ 诊断）；executor /
policy / dynamics / authority / producer / trace 由 T9 注入。

## 2. EngineInstance（T2；方法集冻结）
`instance` property；`submit_proposal(p: ActionProposal) -> StepResult`；
`submit_action(actor_id, action_id, arguments, *, intent=None) -> StepResult`；
`wake(actor_id, *, reason=None, due_tick=None) -> None`；
`advance(ticks: int = 1) -> StepResult`；`view() -> SceneView`
（= `derive_scene_view(world)`）。`StepResult` = runtime/engine.py 新
frozen dataclass（`ok: bool / world_revision: Revision / diagnostics:
tuple[str, ...]` 或等价最小面）。不做 session / server / image / async /
multiplayer。advance 相位：1 due wakeups → 2 policy→proposal→executor→
effects（cascade+commit_transaction）→ 3 dynamics（每 backend simulate→
同管道 commit）→ 4 action lifecycle 完成 → 5 logical_tick+1（RuntimeState
重建；world_revision 只经 commit 推进）。未注册 action = 显式诊断不静默。

## 3. Python extension contract（T3；冻结）
```python
@dataclass(frozen=True)
class ProducerGrant:
    producer_id: str
    component_types: tuple[str, ...]
    priority: int = 50

@dataclass(frozen=True)
class ExtensionBundle:
    action_executors: Mapping[str, ActionExecutor]
    dynamics_backends: tuple[WorldDynamicsBackend, ...] = ()
    policies: Mapping[str, BehaviorPolicy] = ()
    producer_grants: tuple[ProducerGrant, ...] = ()
```
`ExtensionContext` frozen（`project_root: Path` + `ir: ProjectIR`）。
`load_extensions(project_root, ir, *, trust_python: bool) -> ExtensionLoadResult`
（bundles tuple + diagnostics）。source：优先 `plugins/*/plugin.yaml`
（经 `plugins.manifest.parse_plugin_manifest`），其次
`ProjectIR.plugin_descriptors` 的 entrypoint；不造第三种。唯一 import 路：
`importlib.import_module(spec.module)` + `getattr`，entrypoint =
`module:build_extension`；`trust_python=True` 时临时 prepend project_root
到 sys.path，finally 恢复。dynamics grant 从 `metadata()` 自动派生；
executor 自定义 producer 必须显式 ProducerGrant。Gate：rogue.py 未声明
不 import；trust_python=False → 明确诊断；entrypoint 错型 → 明确诊断。

## 4. 任务所有权（owned file 一人一文件）
| Task | 写 | 测试 |
|---|---|---|
| T1 | runtime/materialize.py | tests/.../runtime/test_materialize.py |
| T2 | runtime/engine.py | test_engine.py |
| T3 | runtime/extensions.py | test_extensions.py |
| T4 | runtime/context.py | test_context.py |
| T5 | runtime/llm_binding.py | test_llm_binding.py |
| T6 | runtime/action_binding.py | test_action_binding.py |
| T7 | runtime/dynamics_binding.py | test_dynamics_binding.py |
| T8 | runtime/observability.py | test_observability.py |
| T9 | runtime/assembly.py | test_assembly.py |
| T10 | examples/complex_minimal/** | （T11 覆盖） |
| T11 | tests/.../runtime/test_complex_game_e2e.py | 自身 |
