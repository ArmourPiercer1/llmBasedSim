"""P10 web 适配子包（T05；SOT §3.0 包树 / §11 白名单行 10）。

职责：web 会话层（session.py，SessionManager / WebSession，SOT §3.7）+
无状态请求 handler 层（api.py，SOT §3.8）+ 服务端渲染（views.py，
SOT §3.12）+ stdlib http.server 薄壳（server.py，SOT §3.12，测试零
调用）+ 零依赖静态前端（static/，SOT §3.9）。

纪律：web 层对 authoritative state 只读投影（K1）；零单例 / 零模块
级实例（P10-INV-4，A3 AST，43.2-8 移除落点）；会话隔离 = 独立 dict
槽（A12/t2）；错误族 = presentation 单一 PresentationError 族 + api
层 WebApiError 族（SOT §3.1/§3.8）；包级 docstring-only，零
re-export（W1 text/__init__.py 8 行先例，SOT §2.6）。
"""
