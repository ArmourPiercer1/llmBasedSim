"""P10 web 薄壳服务（T05；SOT §3.12；导出 2 名）。

来源 = D-P10-03（stdlib http.server 薄壳；socket 面零测试调用——
D-P10-03 裁定：测试 = handler 层纯函数面，零 socket）+ v1
``src/web/app.py`` 路由入口面**语义参照**（文字参照，零 import）；
Spec §35 web adapter。

纪律（P10-INV-4，D6，K8）：

- 导出 = 2 名（:func:`create_web_server` / :func:`run_web_server`，
  SOT §3.12 逐字）；
- **handler 类定义于 :func:`create_web_server` 函数作用域内**（闭包
  捕获 manager；零模块级类 / 零模块级实例——A3 AST 机械面：
  adapters/web 内零模块级 WorldState()/SessionManager()/WebSession()/
  Scheduler()/LogicalClock() 实例化）；
- 请求流 = stdlib http.server 解析 → 剥查询串（v1 urlparse 先例）→
  :func:`handle_web_request`（api 层纯函数）→ WebResponse 回写；
  POST 体 = Content-Length 字节 → json.loads（失败 → None → api 层
  400 信封）；
- 零模块级可变状态（P10-INV-4）；零日志面（log_message 置空——
  确定性面，宿主可自包）；
- **本文件 = 零测试调用面**（SOT §3.12：server 薄壳不进 P10 测试
  面，socket 面 = D-P10-03 隔离）。
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from src.engine_v2.adapters.web.api import handle_web_request
from src.engine_v2.adapters.web.session import SessionManager

__all__ = [
    "create_web_server",
    "run_web_server",
]


def create_web_server(
    manager: SessionManager, *, host: str = "127.0.0.1", port: int = 0
) -> ThreadingHTTPServer:
    """构造 web 服务（D-P10-03 薄壳；handler 类 = 本函数作用域闭包，
    捕获 manager；port=0 = 内核分配端口（宿主自读 server_address））。

    零模块级状态：本函数返回的 server 实例 = 调用方持有面（宿主 /
    人工面），模块层零引用。
    """

    class _WebShellHandler(BaseHTTPRequestHandler):
        """stdlib 薄壳 handler（闭包捕获 manager；GET / POST 双动词；
        请求 → handle_web_request 纯函数 → 回写）。"""

        def _respond(self, method: str) -> None:
            body: object = None
            if method == "POST":
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length > 0 else b""
                if raw:
                    try:
                        body = json.loads(raw.decode("utf-8"))
                    except (ValueError, UnicodeDecodeError):
                        body = None  # 坏体 → api 层 400 信封面
            response = handle_web_request(
                method, urlparse(self.path).path, body, manager=manager
            )
            payload = response.payload
            if isinstance(payload, str):
                payload = payload.encode("utf-8")
            self.send_response(response.status)
            self.send_header("Content-Type", response.content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self) -> None:
            self._respond("GET")

        def do_POST(self) -> None:
            self._respond("POST")

        def log_message(self, format: str, *args: object) -> None:
            """零日志面（确定性；宿主可自包 logging 消费）。"""
            return None

    return ThreadingHTTPServer((host, port), _WebShellHandler)


def run_web_server(
    manager: SessionManager, *, host: str = "127.0.0.1", port: int = 8000
) -> None:
    """阻塞运行（宿主主循环入口面；零测试调用，D-P10-03）。"""
    server = create_web_server(manager, host=host, port=port)
    server.serve_forever()
