"""Run the browser-based UI development server."""

import argparse
import socket

from src.web.app import run


def _detect_lan_ip() -> str:
    """Return the primary LAN IP address, or '0.0.0.0' if undetectable."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return ""


def main() -> None:
    parser = argparse.ArgumentParser(description="LLM Simulation Game WebUI")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Bind port (default: 8000)")
    parser.add_argument("--lan", action="store_true", help="Shortcut for --host 0.0.0.0")
    args = parser.parse_args()

    host = "0.0.0.0" if args.lan else args.host

    if host in ("0.0.0.0", "::"):
        lan_ip = _detect_lan_ip()
        print("已绑定到所有网络接口。手机/其他设备可通过以下地址访问：")
        if lan_ip:
            print(f"  http://{lan_ip}:{args.port}")
        print(f"  http://<本机IP>:{args.port}")
        print()

    run(host=host, port=args.port)


if __name__ == "__main__":
    main()
