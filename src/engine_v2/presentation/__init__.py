"""v2 表现层 presentation（占位，Phase 10 填充）。

职责：WorldState → View 的派生渲染——text / image（实时图片）/ tactical
视图；表现层只读，不写 authoritative state（K1/K2）。

对应 Spec 章节：§8.5 ViewState、§32 Presentation Contract、
§46 MVP（realtime image 相关推迟项见「可以推迟」）、§44 推荐源码目录。
"""
