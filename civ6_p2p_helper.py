#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CV6 online helper - 主启动入口

两步式文明6联机辅助工具（纯 Python 标准库，免虚拟网卡、免管理员权限、免注入）：
  第一步：通过「IPv6 / P2P 直连」或「服务器中继」连上好友，实时查看在线人数/延迟并完成连通测试；
  第二步：只有第一步连接成功且至少 2 人在线时自动解锁，提供文明 6 62900 房间发现与 62056 会话桥接。
"""

from civ6_p2p.gui import run_gui


if __name__ == "__main__":
    run_gui()
