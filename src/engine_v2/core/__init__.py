"""v2 Kernel 核心契约（占位，Phase 1 填充）。

职责：单一 authoritative state 的数据语言——Entity / typed Component、
WorldState / RuntimeState 分离、Revision、Action（Registry / Proposal /
Lifecycle）、ProposedEffect、Authority、Validation、Conflict Resolution、
Transaction / Reducer、DomainEvent（含 provenance）。

对应 Spec 章节：§4 Kernel 强制不变量（K1–K8）、§8 State Model、
§9 Revision Model、§10 Entity / Component Contract、§11 Action Contract、
§16 Effect Contract、§17 Authority Contract、§18 Effect Validation、
§19 Conflict Resolution、§20 Transaction / Reducer、§21 Event Contract。

此包禁止 import LangGraph / OpenAI（G1 门禁），且完全不接 LLM（Spec §47
Phase 1 验收：core tests 无网络、无 LLM 可完整运行）。
"""
