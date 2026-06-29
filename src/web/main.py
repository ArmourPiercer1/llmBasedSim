"""Run the browser-based UI development server."""

import argparse
import ipaddress
import socket
import sys
from dataclasses import dataclass

from src.web.app import run


@dataclass
class _IPInfo:
    ip: str
    label: str = ""
    private: bool = False


def _is_private_ipv4(ip: str) -> bool:
    try:
        return ipaddress.ip_address(ip).is_private
    except ValueError:
        return False


def _classify_ip(ip: str) -> str:
    if ip.startswith("192.168.137."):
        return "移动热点虚拟网卡"
    if ip.startswith("192.168."):
        return "局域网 (Wi-Fi/以太网)"
    if ip.startswith("10.") or (ip.startswith("172.") and 16 <= int(ip.split(".")[1]) <= 31):
        return "私有子网"
    return "公网/其他"


def _detect_all_ips() -> list[_IPInfo]:
    """Detect all non-loopback IPv4 addresses on this machine."""
    seen: set[str] = set()
    results: list[_IPInfo] = []

    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP):
            ip = info[4][0]
            if ip.startswith("127.") or ip in seen:
                continue
            seen.add(ip)
            is_private = _is_private_ipv4(ip)
            results.append(_IPInfo(ip=ip, label=_classify_ip(ip), private=is_private))
    except OSError:
        pass

    # Sort: hotspot first, then other private IPs, then public
    def _sort_key(info: _IPInfo) -> tuple[int, int, str]:
        hotspot = 0 if info.ip.startswith("192.168.137.") else 1
        priv = 0 if info.private else 1
        return (hotspot, priv, info.ip)

    results.sort(key=_sort_key)
    return results


def _detect_best_lan_ip() -> str | None:
    """Return the best private LAN IP to bind to. Only considers private subnets."""
    ips = _detect_all_ips()
    if not ips:
        return None
    # 1) Hotspot adapter (phone connects via this)
    for info in ips:
        if info.ip.startswith("192.168.137."):
            return info.ip
    # 2) Any 192.168.x.x (most common LAN)
    for info in ips:
        if info.ip.startswith("192.168."):
            return info.ip
    # 3) Other private IPs (10.x.x.x, 172.16-31.x.x)
    for info in ips:
        if info.private:
            return info.ip
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="LLM Simulation Game WebUI")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Bind port (default: 8000)")
    parser.add_argument("--lan", action="store_true", help="仅绑定到局域网 IP（比 0.0.0.0 更安全，不会暴露到虚拟网卡）")
    parser.add_argument("--list-ips", action="store_true", help="列出所有可用的局域网 IP 后退出")
    args = parser.parse_args()

    if args.list_ips:
        ips = _detect_all_ips()
        if not ips:
            print("未检测到非本机 IP 地址。请确认已连接网络或开启热点。")
        else:
            print(f"检测到 {len(ips)} 个可用地址：")
            for info in ips:
                tag = "  ← 推荐用于 --lan" if info.private else ""
                print(f"  {info.ip:20s} — {info.label}{tag}")
        sys.exit(0)

    if args.lan:
        best_ip = _detect_best_lan_ip()
        if not best_ip:
            print("错误: 未能检测到局域网 IP 地址。请确认已连接网络或开启热点。")
            print("提示: 使用 --list-ips 查看所有可用地址，或使用 --host 手动指定。")
            sys.exit(1)
        host = best_ip
        ips = _detect_all_ips()
        print("已绑定到局域网接口（仅允许本地子网访问）。")
        print("手机/其他设备可通过以下地址访问：")
        for info in ips:
            if info.private:
                tag = "  ← 推荐使用此地址" if info.ip == best_ip else ""
                print(f"  http://{info.ip}:{args.port}  ({info.label}){tag}")
        print()
    else:
        host = args.host

    run(host=host, port=args.port)


if __name__ == "__main__":
    main()
