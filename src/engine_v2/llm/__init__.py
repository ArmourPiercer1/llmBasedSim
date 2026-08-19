"""v2 LLM Runtime / 推理路由（占位，Phase 6 填充）。

职责：provider-neutral 推理——structured inference、InferenceProfile /
capability routing、router 与 providers 抽象。本包是唯一允许触达
OpenAI / provider SDK 的位置；engine_v2.core 仍禁止 import 它们（G1）。

对应 Spec 章节：§5.5 游戏可声明的 Inference Capability、§31 LLM Runtime、
§46 MVP 第 22 条（provider-neutral inference profile）。
"""
