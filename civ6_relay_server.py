#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Civ6 P2P 独立中继服务器（可部署在任意 Linux / Windows VPS，零第三方依赖）

用法示例:
    python3 civ6_relay_server.py --port 38668

安全组/防火墙:
    只需在云服务器放行 UDP 38668（或自定义端口）即可，同时支持 IPv4 与 IPv6 客户端混合接入。
"""

from __future__ import annotations

import argparse
import signal
import time

from civ6_p2p.protocol import DEFAULT_RELAY_PORT
from civ6_p2p.relay_server import RelayServer


def main() -> None:
    parser = argparse.ArgumentParser(description="Civ6 IPv6/IPv4 联机助手 - 独立 UDP 中继服务器")
    parser.add_argument("--port", type=int, default=DEFAULT_RELAY_PORT, help=f"监听 UDP 端口 (默认: {DEFAULT_RELAY_PORT})")
    parser.add_argument("--idle-timeout", type=float, default=15.0, help="客户端心跳超时秒数 (默认: 15)")
    args = parser.parse_args()

    def log_cb(level: str, msg: str) -> None:
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{ts}] [{level.upper()}] {msg}", flush=True)

    server = RelayServer(listen_port=args.port, idle_timeout_s=args.idle_timeout, log_cb=log_cb)
    actual_port = server.start()
    print(f"中继服务器运行中 (UDP :{actual_port})，按 Ctrl+C 停止...", flush=True)

    stop = False

    def _handle_sig(_signum, _frame) -> None:
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, _handle_sig)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _handle_sig)

    last_stat = time.monotonic()
    try:
        while not stop:
            time.sleep(0.5)
            now = time.monotonic()
            if now - last_stat >= 60.0:
                last_stat = now
                st = server.get_stats()
                log_cb(
                    "info",
                    f"状态统计: 活跃房间={st.room_count}, 在线成员={st.client_count}, 转发包={st.fwd_packets}, 转发字节={st.fwd_bytes}",
                )
    finally:
        server.stop()


if __name__ == "__main__":
    main()
