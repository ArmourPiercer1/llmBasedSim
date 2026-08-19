"""v2 适配层 adapters（占位，Phase 8/10/11 填充）。

职责：将 v2 Runtime 暴露给外部入口的适配——cli / web / dsh。
适配层只做协议翻译，不持有 authoritative state（K1）。

对应 Spec 章节：§35 DSH Integration、§44 推荐源码目录 adapters/、
Phase 10（Presentation / Web）与 Phase 11（DSH / Agent-native）。
"""
