#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CV6 online helper - Xiaomi HyperOS 4 "Soft-Glow Glass (柔光玻璃)" Desktop UI.

Uses Windows native Edge WebView2 (via pywebview) with Windows 11 DWM rounded
corners and synchronized caption tinting, backed by a thread-safe controller
sharing 100% of the P2P, EasyTier (--no-tun), and Civilization VI tunnel engine.
"""

from __future__ import annotations

import base64
import ctypes
import os
import socket
import sys
import tempfile
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

from .civ6_tunnel import ClientCiv6Bridge, HostCiv6Bridge
from .easytier_manager import (
    EasyTierSession,
    parse_easytier_peers,
)
from .network_utils import LocalNetworkInfo, detect_local_network_info, format_endpoint
from .p2p_node import P2PNode, PeerState, Step2GateState, evaluate_step2_gate
from .protocol import (
    DEFAULT_P2P_PORT,
    DEFAULT_RELAY_PORT,
    DEFAULT_RELAY_ROOM,
    DEFAULT_ROOM_KEY,
    build_invite_code,
    parse_peer_input,
)
from .vps_store import VpsNodeStore, resolve_relay_input
from .win_civ6 import Civ6LocalState, inspect_civ6_state


def _fmt_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.2f} MB"


def _set_windows_clipboard(text: str) -> bool:
    """Copy UTF-16 text to Windows clipboard using pure Win32 ctypes."""
    if os.name != "nt":
        return False
    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalUnlock.restype = ctypes.c_int
    kernel32.GlobalFree.argtypes = [ctypes.c_void_p]
    kernel32.GlobalFree.restype = ctypes.c_void_p
    user32.OpenClipboard.argtypes = [ctypes.c_void_p]
    user32.OpenClipboard.restype = ctypes.c_int
    user32.EmptyClipboard.argtypes = []
    user32.EmptyClipboard.restype = ctypes.c_int
    user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
    user32.SetClipboardData.restype = ctypes.c_void_p
    user32.CloseClipboard.argtypes = []
    user32.CloseClipboard.restype = ctypes.c_int

    data = (text + "\x00").encode("utf-16-le")
    hmem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
    if not hmem:
        return False
    ptr = kernel32.GlobalLock(hmem)
    if not ptr:
        kernel32.GlobalFree(hmem)
        return False
    try:
        ctypes.memmove(ptr, data, len(data))
    finally:
        kernel32.GlobalUnlock(hmem)

    opened = False
    for _ in range(5):
        if user32.OpenClipboard(None):
            opened = True
            break
        time.sleep(0.02)
    if not opened:
        kernel32.GlobalFree(hmem)
        return False
    try:
        user32.EmptyClipboard()
        if not user32.SetClipboardData(CF_UNICODETEXT, hmem):
            kernel32.GlobalFree(hmem)
            return False
        return True
    finally:
        user32.CloseClipboard()


def _rgb_to_colorref(r: int, g: int, b: int) -> int:
    return (b << 16) | (g << 8) | r


def _apply_win11_dwm_style(hwnd: int, theme: str = "light") -> None:
    """Apply Windows 11 DWM rounded corners and matching soft-glass caption tint."""
    if os.name != "nt" or not hwnd:
        return
    try:
        dwmapi = ctypes.windll.dwmapi
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        DWMWA_WINDOW_CORNER_PREFERENCE = 33
        DWMWA_BORDER_COLOR = 34
        DWMWA_CAPTION_COLOR = 35
        DWMWA_TEXT_COLOR = 36

        is_dark = theme == "dark"

        corner = ctypes.c_int(2)  # DWMWCP_ROUND
        dwmapi.DwmSetWindowAttribute(
            ctypes.c_void_p(hwnd),
            DWMWA_WINDOW_CORNER_PREFERENCE,
            ctypes.byref(corner),
            ctypes.sizeof(corner),
        )

        dark_flag = ctypes.c_int(1 if is_dark else 0)
        dwmapi.DwmSetWindowAttribute(
            ctypes.c_void_p(hwnd),
            DWMWA_USE_IMMERSIVE_DARK_MODE,
            ctypes.byref(dark_flag),
            ctypes.sizeof(dark_flag),
        )

        if is_dark:
            caption_color = ctypes.c_uint32(_rgb_to_colorref(12, 18, 31))
            text_color = ctypes.c_uint32(_rgb_to_colorref(236, 243, 255))
            border_color = ctypes.c_uint32(_rgb_to_colorref(42, 58, 86))
        else:
            caption_color = ctypes.c_uint32(_rgb_to_colorref(237, 243, 250))
            text_color = ctypes.c_uint32(_rgb_to_colorref(22, 32, 51))
            border_color = ctypes.c_uint32(_rgb_to_colorref(208, 222, 240))

        dwmapi.DwmSetWindowAttribute(
            ctypes.c_void_p(hwnd),
            DWMWA_CAPTION_COLOR,
            ctypes.byref(caption_color),
            ctypes.sizeof(caption_color),
        )
        dwmapi.DwmSetWindowAttribute(
            ctypes.c_void_p(hwnd),
            DWMWA_TEXT_COLOR,
            ctypes.byref(text_color),
            ctypes.sizeof(text_color),
        )
        dwmapi.DwmSetWindowAttribute(
            ctypes.c_void_p(hwnd),
            DWMWA_BORDER_COLOR,
            ctypes.byref(border_color),
            ctypes.sizeof(border_color),
        )
    except Exception:
        pass


def _find_ui_dir() -> Path:
    """Locate the bundled HTML/CSS/JS ui asset folder in dev and PyInstaller builds."""
    candidates: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "civ6_p2p" / "ui")
        candidates.append(Path(meipass) / "ui")
    candidates.append(Path(__file__).resolve().parent / "ui")
    for p in candidates:
        if (p / "index.html").is_file():
            return p
    raise FileNotFoundError("未找到柔光玻璃 UI 资源目录 (civ6_p2p/ui/index.html)")


def _find_app_icon_path() -> Path | None:
    try:
        ico = _find_ui_dir() / "app_icon.ico"
        return ico if ico.is_file() else None
    except Exception:
        return None


def _apply_win_window_icon(hwnd: int) -> None:
    """Set both small (titlebar) and big (taskbar/Alt+Tab) Win32 window icons."""
    if os.name != "nt" or not hwnd:
        return
    ico = _find_app_icon_path()
    if ico is None:
        return
    try:
        user32 = ctypes.windll.user32
        IMAGE_ICON = 1
        LR_LOADFROMFILE = 0x0010
        WM_SETICON = 0x0080
        ICON_SMALL = 0
        ICON_BIG = 1

        user32.LoadImageW.argtypes = [
            ctypes.c_void_p,
            ctypes.c_wchar_p,
            ctypes.c_uint,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_uint,
        ]
        user32.LoadImageW.restype = ctypes.c_void_p
        user32.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
        user32.SendMessageW.restype = ctypes.c_void_p

        h_small = user32.LoadImageW(None, str(ico), IMAGE_ICON, 32, 32, LR_LOADFROMFILE)
        h_big = user32.LoadImageW(None, str(ico), IMAGE_ICON, 256, 256, LR_LOADFROMFILE)
        if h_small:
            user32.SendMessageW(ctypes.c_void_p(hwnd), WM_SETICON, ctypes.c_void_p(ICON_SMALL), ctypes.c_void_p(h_small))
        if h_big:
            user32.SendMessageW(ctypes.c_void_p(hwnd), WM_SETICON, ctypes.c_void_p(ICON_BIG), ctypes.c_void_p(h_big))
    except Exception:
        pass


def load_glass_html() -> str:
    """Load index.html and inline local style.css, app.js, and app_logo.png for zero-server WebView2 startup."""
    ui_dir = _find_ui_dir()
    html = (ui_dir / "index.html").read_text(encoding="utf-8")
    css = (ui_dir / "style.css").read_text(encoding="utf-8")
    js = (ui_dir / "app.js").read_text(encoding="utf-8")
    logo_path = ui_dir / "app_logo.png"
    logo_uri = ""
    if logo_path.is_file():
        b64 = base64.b64encode(logo_path.read_bytes()).decode("ascii")
        logo_uri = f"data:image/png;base64,{b64}"
    html = html.replace("__APP_LOGO_DATA_URI__", logo_uri)
    html = html.replace("/*__INLINE_CSS__*/", css)
    html = html.replace("/*__INLINE_JS__*/", js)
    return html


class GlassAppController:
    """
    Thread-safe application controller backing the HyperOS 4 Soft-Glow Glass UI.
    Preserves strict 2-step gating, IPv6/P2P direct + EasyTier (--no-tun), and Civ6 tunneling.
    """

    def __init__(
        self,
        start_bg_poller: bool = True,
        vps_store_path: Path | None = None,
    ) -> None:
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._window: Any = None
        self._hwnd: int = 0
        self._theme: str = "light"

        # Identity & form state
        default_nick = socket.gethostname()[:16] or "Player"
        self.role: str = "client"
        self.nickname: str = default_nick
        self.port_text: str = str(DEFAULT_P2P_PORT)
        self.room_key: str = DEFAULT_ROOM_KEY
        self.conn_mode: str = "p2p_ipv6"  # "p2p_ipv6" | "relay"

        # P2P address state
        self.net_info: LocalNetworkInfo = LocalNetworkInfo()
        self.stun_info: dict[str, tuple[str, int]] = {}
        self.address_choices: list[dict[str, str]] = []
        self._addr_display_to_ip: dict[str, str] = {}
        self.selected_address: str = ""

        # Custom VPS Relay state (no hardcoded public/community nodes)
        self._vps_store = VpsNodeStore(path=vps_store_path)
        saved_nodes = self._vps_store.list_nodes()
        self.et_node: str = saved_nodes[0].display_label() if saved_nodes else ""
        self.et_room: str = DEFAULT_RELAY_ROOM
        self.et_status: str = "未连接 VPS 中继（请先点击「添加 VPS」配置自建节点，或直接输入节点地址）"
        self.et_status_level: str = "idle"  # idle | connecting | connected | error
        self.et_connecting: bool = False
        self.relay_active_kind: str = ""  # "" | "easytier" | "udp_relay"
        self.relay_active_name: str = ""

        # Async action busy flags
        self.stun_busy: bool = False
        self.test_busy: bool = False
        self.probe_busy: bool = False

        # Engines
        self.p2p_node: P2PNode | None = None
        self.easytier_session: EasyTierSession | None = None
        self.host_bridge: HostCiv6Bridge | None = None
        self.client_bridge: ClientCiv6Bridge | None = None
        self.local_civ6_state: Civ6LocalState = Civ6LocalState()
        self.target_host_key: str = ""
        self.bridge_status_text: str = "未启动"
        self.bridge_activity_text: str = "已通过第一步连接验证，可以开启文明6联机辅助。"
        self._last_gate: Step2GateState = evaluate_step2_gate(False, [])

        # Logs & UI events
        self._log_seq: int = 0
        self._logs: deque[dict[str, Any]] = deque(maxlen=600)
        self._event_seq: int = 0
        self._events: deque[dict[str, Any]] = deque(maxlen=80)

        self._append_log(
            "info",
            "欢迎使用 CV6 online helper！请先在第一步通过「IPv6/P2P 直连」或「自定义 VPS 中继」连上好友并测试通过（至少 2 人在线），即可解锁第二步。",
        )
        self.refresh_network_info()

        self._poller_thread: threading.Thread | None = None
        if start_bg_poller:
            self._poller_thread = threading.Thread(
                target=self._civ6_poll_loop, name="glass-civ6-poll", daemon=True
            )
            self._poller_thread.start()

    def attach_window(self, window: Any) -> None:
        self._window = window

    def resolve_and_style_hwnd(self) -> None:
        hwnd = 0
        try:
            if self._window is not None and getattr(self._window, "native", None) is not None:
                hwnd = int(self._window.native.Handle.ToInt64())
        except Exception:
            hwnd = 0
        if not hwnd and os.name == "nt":
            try:
                hwnd = int(ctypes.windll.user32.FindWindowW(None, "CV6 online helper") or 0)
            except Exception:
                hwnd = 0
        if hwnd:
            self._hwnd = hwnd
            _apply_win11_dwm_style(hwnd, self._theme)
            _apply_win_window_icon(hwnd)

    def set_theme(self, theme: str) -> dict[str, Any]:
        clean = "dark" if str(theme).strip().lower() == "dark" else "light"
        with self._lock:
            self._theme = clean
        if self._hwnd:
            _apply_win11_dwm_style(self._hwnd, clean)
        else:
            self.resolve_and_style_hwnd()
        return {"ok": True, "theme": clean}

    # ----------------------------
    # Internal Logging & Events
    # ----------------------------

    def _append_log(self, level: str, msg: str) -> None:
        ts = time.strftime("%H:%M:%S")
        with self._lock:
            self._log_seq += 1
            self._logs.append({"id": self._log_seq, "ts": ts, "level": level, "msg": str(msg)})

    def _push_event(self, kind: str, payload: dict[str, Any]) -> None:
        with self._lock:
            self._event_seq += 1
            self._events.append({"id": self._event_seq, "kind": kind, "payload": payload})

    def _civ6_poll_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                st = inspect_civ6_state()
                with self._lock:
                    self.local_civ6_state = st
            except Exception:
                pass
            self._stop_event.wait(2.0)

    def _get_local_civ6_status_dict(self) -> dict[str, Any]:
        with self._lock:
            return self.local_civ6_state.to_status_dict()

    def _has_active_bridge(self) -> bool:
        return bool(
            (self.host_bridge and self.host_bridge.running)
            or (self.client_bridge and self.client_bridge.running)
        )

    def _parse_port_safe(self, port_text: str | None = None) -> int:
        raw = self.port_text if port_text is None else port_text
        try:
            p = int(str(raw).strip())
            return p if 1 <= p <= 65535 else DEFAULT_P2P_PORT
        except ValueError:
            return DEFAULT_P2P_PORT

    def _selected_advertise_host_port(self) -> tuple[str, int]:
        raw_sel = self.selected_address.strip()
        ip = self._addr_display_to_ip.get(raw_sel, raw_sel.split()[0] if raw_sel else "::1")
        port = (
            self.p2p_node.actual_port
            if (self.p2p_node and self.p2p_node.running)
            else self._parse_port_safe()
        )
        if "[STUN公网IPv6" in raw_sel and "ipv6" in self.stun_info:
            port = self.stun_info["ipv6"][1]
        elif "[STUN公网IPv4" in raw_sel and "ipv4" in self.stun_info:
            port = self.stun_info["ipv4"][1]
        return ip, port

    def _compute_invite_code(self) -> str:
        if not (self.p2p_node and self.p2p_node.running):
            return "启动本机节点后自动生成连接码"
        try:
            ip, port = self._selected_advertise_host_port()
            return build_invite_code(
                host=ip,
                port=port,
                nickname=self.nickname.strip(),
                role=self.role.strip(),
                room_key=self.room_key.strip(),
            )
        except Exception:
            return "请选择有效的本机 IP 地址"

    def _populate_address_choices(self) -> None:
        self._addr_display_to_ip.clear()
        choices: list[dict[str, str]] = []

        if "ipv6" in self.stun_info:
            ip, port = self.stun_info["ipv6"]
            label = f"{ip}  [STUN公网IPv6 :{port}]"
            self._addr_display_to_ip[label] = ip
            choices.append({"label": label, "ip": ip, "tag": f"STUN IPv6 :{port}"})
        if "ipv4" in self.stun_info:
            ip, port = self.stun_info["ipv4"]
            label = f"{ip}  [STUN公网IPv4 :{port}]"
            self._addr_display_to_ip[label] = ip
            choices.append({"label": label, "ip": ip, "tag": f"STUN IPv4 :{port}"})

        for ip, desc in self.net_info.all_candidates():
            label = f"{ip}  [{desc}]"
            if label not in self._addr_display_to_ip:
                self._addr_display_to_ip[label] = ip
                choices.append({"label": label, "ip": ip, "tag": desc})

        self.address_choices = choices
        labels = [c["label"] for c in choices]
        if labels:
            cur = self.selected_address.strip()
            if not cur or cur not in labels:
                self.selected_address = labels[0]

    # ----------------------------
    # State Snapshot for UI
    # ----------------------------

    def get_state(self, last_log_id: int = 0, last_event_id: int = 0) -> dict[str, Any]:
        with self._lock:
            node_running = bool(self.p2p_node and self.p2p_node.running)
            actual_port = self.p2p_node.actual_port if (self.p2p_node and node_running) else None
            peers: list[PeerState] = self.p2p_node.list_peers() if self.p2p_node else []
            gate = evaluate_step2_gate(node_running, peers)
            self._last_gate = gate
            active_bridge = self._has_active_bridge()
            step2_unlocked = gate.can_enter_step2 or active_bridge

            # VPS Relay dynamic status (supports both EasyTier VPS & direct UDP Relay VPS)
            et_status = self.et_status
            et_level = self.et_status_level
            et_alive = bool(self.easytier_session is not None and self.easytier_session.running)
            relay_connected_or_running = bool(
                et_alive
                or self.et_connecting
                or self.relay_active_kind == "udp_relay"
            )
            if node_running and self.p2p_node is not None:
                rst = self.p2p_node.get_relay_status()
                node_tag = f" [{self.relay_active_name}]" if self.relay_active_name else ""
                if self.easytier_session is not None:
                    if not et_alive:
                        et_status = f"VPS EasyTier 进程意外退出{node_tag}，可直接重新点击连接"
                        et_level = "error"
                    elif rst.enabled and rst.connected:
                        et_status = (
                            f"VPS EasyTier 已连接{node_tag} · 房间 [{rst.room_id}] 当前 {rst.room_members} 人在线（自动打洞/中继）"
                        )
                        et_level = "connected"
                    elif rst.enabled:
                        role_tip = "等待 VPS 通道就绪" if self.role == "client" else "正在初始化房间"
                        et_status = f"VPS EasyTier 运行中{node_tag}（{role_tip}，房间 [{rst.room_id}]）..."
                        et_level = "connecting"
                elif self.relay_active_kind == "udp_relay" and rst.enabled:
                    if rst.connected:
                        et_status = (
                            f"VPS UDP 中继已连接{node_tag} · 房间 [{rst.room_id}] 当前 {rst.room_members} 人在线"
                        )
                        et_level = "connected"
                    else:
                        et_status = f"正在连接 VPS UDP 中继{node_tag}（房间 [{rst.room_id}]）..."
                        et_level = "connecting"

            # Peers list serialization
            peer_rows: list[dict[str, Any]] = []
            for p in peers:
                if p.status == "online":
                    status_txt = "在线"
                elif p.status == "connecting":
                    status_txt = "连接中" if p.transport == "relay" else "打洞连接中"
                else:
                    status_txt = "离线"
                peer_rows.append(
                    {
                        "peer_key": p.peer_key,
                        "nickname": p.nickname or "未命名",
                        "role": p.role,
                        "role_label": {"host": "房主", "client": "加入者"}.get(p.role, "未知"),
                        "transport": p.transport,
                        "transport_label": p.transport_label(),
                        "status": p.status,
                        "status_label": status_txt,
                        "verified": p.verified,
                        "rtt_text": f"{p.rtt_ms:.0f} ms" if p.rtt_ms is not None else "-",
                        "rtt_ms": p.rtt_ms,
                        "loss_text": f"{p.loss_pct:.0f}%" if p.status == "online" else "-",
                        "civ6_summary": p.remote_civ6_summary(),
                        "test_summary": p.last_test_summary,
                        "fake_ip": p.fake_ip,
                    }
                )

            # Target host options (verified online peers)
            verified_online = sorted(
                [p for p in peers if p.status == "online" and p.verified],
                key=lambda p: (0 if p.role == "host" else 1, p.peer_key),
            )
            target_hosts = [
                {
                    "peer_key": p.peer_key,
                    "label": f"{p.nickname} [{p.transport_label()} · 在线✅] ({p.peer_key})",
                }
                for p in verified_online
            ]
            valid_keys = {h["peer_key"] for h in target_hosts}
            if self.role == "client":
                if target_hosts and self.target_host_key not in valid_keys:
                    self.target_host_key = target_hosts[0]["peer_key"]
                elif not target_hosts:
                    self.target_host_key = ""

            can_start_bridge = False
            if not active_bridge:
                can_start_bridge = gate.can_enter_step2
                if can_start_bridge and self.role == "client":
                    can_start_bridge = self.target_host_key in valid_keys

            # Local & remote Civ6 preflight
            st = self.local_civ6_state
            civ6_summary = st.human_summary()
            preflight_local_civ6 = f"已检测到：{civ6_summary}" if st.running else "未检测到文明6进程"
            preflight_local_civ6_ok = st.running

            if node_running:
                preflight_node = f"运行中 (UDP :{actual_port})"
            else:
                preflight_node = "尚未启动"

            if gate.can_enter_step2:
                p0 = gate.verified_online_peers[0]
                rtt = f"{p0.rtt_ms:.0f}ms" if p0.rtt_ms is not None else "-"
                preflight_peer = f"共 {gate.total_online} 人在线 ({p0.nickname} {rtt} 已通过测试)"
            else:
                preflight_peer = f"共 {gate.total_online} 人在线（未满足开启条件）"

            if gate.online_peers:
                parts = [f"{p.nickname}: {p.remote_civ6_summary()}" for p in gate.online_peers[:2]]
                preflight_remote_civ6 = " | ".join(parts)
                preflight_remote_civ6_ok = any(p.remote_civ6_running for p in gate.online_peers)
            else:
                preflight_remote_civ6 = "等待对端在线同步状态"
                preflight_remote_civ6_ok = False

            # Bridge telemetry
            bridge = (
                self.host_bridge
                if (self.host_bridge and self.host_bridge.running)
                else (self.client_bridge if (self.client_bridge and self.client_bridge.running) else None)
            )
            disc_reqs = 0
            disc_resps = 0
            tx_pkts = 0
            tx_bytes_text = "0 B"
            rx_pkts = 0
            rx_bytes_text = "0 B"
            activity_text = self.bridge_activity_text
            if bridge is not None:
                bs = bridge.get_stats()
                disc_reqs = bs.disc_reqs
                disc_resps = bs.disc_resps
                tx_pkts = bs.session_tx_pkts
                tx_bytes_text = _fmt_bytes(bs.session_tx_bytes)
                rx_pkts = bs.session_rx_pkts
                rx_bytes_text = _fmt_bytes(bs.session_rx_bytes)
                if gate.total_online < 2:
                    activity_text = "⚠️ 当前在线不足 2 人，等待好友重新上线..."
                else:
                    activity_text = bs.last_activity_desc

            # Incremental logs & events
            new_logs = [entry for entry in self._logs if entry["id"] > last_log_id]
            new_events = [ev for ev in self._events if ev["id"] > last_event_id]

            role_locked = active_bridge or et_alive or self.et_connecting

            vps_nodes = [n.to_dict() for n in self._vps_store.list_nodes()]

            return {
                "theme": self._theme,
                "role": self.role,
                "role_locked": role_locked,
                "nickname": self.nickname,
                "port_text": self.port_text,
                "room_key": self.room_key,
                "conn_mode": self.conn_mode,
                "node_running": node_running,
                "actual_port": actual_port,
                "ipv6_ready": self.net_info.has_public_ipv6,
                "ipv6_badge": "公网就绪" if self.net_info.has_public_ipv6 else "无公网",
                "civ6_running": st.running,
                "civ6_room_ready": st.has_discovery_port,
                "civ6_summary": civ6_summary,
                "address_choices": list(self.address_choices),
                "selected_address": self.selected_address,
                "invite_code": self._compute_invite_code(),
                "stun_busy": self.stun_busy,
                "vps_nodes": vps_nodes,
                "et_node": self.et_node,
                "et_room": self.et_room,
                "et_connected_or_running": relay_connected_or_running,
                "et_connecting": self.et_connecting,
                "et_status": et_status,
                "et_status_level": et_level,
                "peers": peer_rows,
                "test_busy": self.test_busy,
                "gate": {
                    "node_running": gate.node_running,
                    "total_online": gate.total_online,
                    "can_enter_step2": gate.can_enter_step2,
                    "step2_unlocked": step2_unlocked,
                    "reason": gate.reason,
                },
                "step2": {
                    "preflight_node": preflight_node,
                    "preflight_node_ok": node_running,
                    "preflight_peer": preflight_peer,
                    "preflight_peer_ok": gate.can_enter_step2,
                    "preflight_local_civ6": preflight_local_civ6,
                    "preflight_local_civ6_ok": preflight_local_civ6_ok,
                    "preflight_remote_civ6": preflight_remote_civ6,
                    "preflight_remote_civ6_ok": preflight_remote_civ6_ok,
                    "target_hosts": target_hosts,
                    "target_host_key": self.target_host_key,
                    "active_bridge": active_bridge,
                    "bridge_mode": (
                        "host"
                        if (self.host_bridge and self.host_bridge.running)
                        else ("client" if (self.client_bridge and self.client_bridge.running) else "")
                    ),
                    "can_start_bridge": can_start_bridge,
                    "can_probe_room": bool(
                        self.client_bridge and self.client_bridge.running and not self.probe_busy
                    ),
                    "probe_busy": self.probe_busy,
                    "bridge_status": self.bridge_status_text,
                    "bridge_activity": activity_text,
                    "disc_reqs": disc_reqs,
                    "disc_resps": disc_resps,
                    "tx_pkts": tx_pkts,
                    "tx_bytes": tx_bytes_text,
                    "rx_pkts": rx_pkts,
                    "rx_bytes": rx_bytes_text,
                },
                "logs": new_logs,
                "last_log_id": self._log_seq,
                "events": new_events,
                "last_event_id": self._event_seq,
            }

    # ----------------------------
    # Actions Exposed to Frontend
    # ----------------------------

    def update_form(self, fields: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            if "role" in fields:
                new_role = str(fields["role"]).strip().lower()
                if new_role in ("host", "client") and not (
                    self._has_active_bridge() or self.easytier_session is not None or self.et_connecting
                ):
                    self.role = new_role
                    if self.p2p_node and self.p2p_node.running:
                        self.p2p_node.update_identity(nickname=self.nickname, role=self.role)
            if "nickname" in fields:
                self.nickname = str(fields["nickname"])[:32]
                if self.p2p_node and self.p2p_node.running:
                    self.p2p_node.update_identity(nickname=self.nickname, role=self.role)
            if "port_text" in fields and not (self.p2p_node and self.p2p_node.running):
                self.port_text = str(fields["port_text"]).strip()[:6]
            if "room_key" in fields and not (self.p2p_node and self.p2p_node.running):
                self.room_key = str(fields["room_key"])[:64]
            if "conn_mode" in fields:
                m = str(fields["conn_mode"]).strip()
                if m in ("p2p_ipv6", "relay"):
                    self.conn_mode = m
            if "selected_address" in fields:
                self.selected_address = str(fields["selected_address"]).strip()
            if "et_node" in fields and not (
                self.easytier_session is not None
                or self.et_connecting
                or self.relay_active_kind == "udp_relay"
            ):
                self.et_node = str(fields["et_node"])
            if "et_room" in fields and not (
                self.easytier_session is not None
                or self.et_connecting
                or self.relay_active_kind == "udp_relay"
            ):
                self.et_room = str(fields["et_room"])[:64]
            if "target_host_key" in fields and not self._has_active_bridge():
                self.target_host_key = str(fields["target_host_key"])

            return {"ok": True, "invite_code": self._compute_invite_code()}

    def refresh_network_info(self) -> dict[str, Any]:
        info = detect_local_network_info()
        with self._lock:
            self.net_info = info
            self._populate_address_choices()
        if info.has_public_ipv6:
            self._append_log(
                "ok", f"检测到本机公网 IPv6: {info.default_ipv6 or info.global_ipv6[0]}"
            )
        else:
            self._append_log(
                "warn", "未检测到公网 IPv6 地址（仍可使用 P2P/STUN 或切换「方式二：自定义 VPS 中继」）。"
            )
        return {"ok": True, "has_public_ipv6": info.has_public_ipv6}

    def copy_text(self, text: str, log_msg: str = "") -> dict[str, Any]:
        ok = _set_windows_clipboard(str(text))
        if log_msg:
            self._append_log("ok" if ok else "info", log_msg)
        return {"ok": ok}

    def copy_invite_code(self) -> dict[str, Any]:
        with self._lock:
            if not (self.p2p_node and self.p2p_node.running):
                return {"ok": False, "title": "提示", "message": "请先点击「启动节点」。"}
            code = self._compute_invite_code()
        _set_windows_clipboard(code)
        self._append_log("ok", f"已复制本机连接码: {code}")
        return {"ok": True, "code": code}

    def start_node(
        self,
        role: str | None = None,
        nickname: str | None = None,
        port_text: str | None = None,
        room_key: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            if self.p2p_node and self.p2p_node.running:
                return {"ok": True, "actual_port": self.p2p_node.actual_port}
            if role in ("host", "client"):
                self.role = role
            if nickname is not None:
                self.nickname = str(nickname).strip()[:32] or "Player"
            if port_text is not None:
                self.port_text = str(port_text).strip()
            if room_key is not None:
                self.room_key = str(room_key).strip()

            try:
                port = int(self.port_text)
                if not (0 <= port <= 65535):
                    raise ValueError
            except ValueError:
                return {
                    "ok": False,
                    "title": "端口错误",
                    "message": "监听端口必须是 0-65535 之间的整数（推荐 38666）。",
                }

            node = P2PNode(
                nickname=self.nickname or "Player",
                role=self.role,
                listen_port=port,
                room_key=self.room_key,
                log_cb=self._append_log,
                local_civ6_status_fn=self._get_local_civ6_status_dict,
            )
            try:
                actual_port = node.start()
            except OSError as e:
                return {
                    "ok": False,
                    "title": "启动失败",
                    "message": f"无法绑定 UDP 端口 {port}：\n{e}\n\n可更换端口后重试。",
                }

            self.p2p_node = node
            self.port_text = str(actual_port)
            return {"ok": True, "actual_port": actual_port, "invite_code": self._compute_invite_code()}

    def _stop_easytier_only(self) -> None:
        if self.easytier_session is not None:
            try:
                self.easytier_session.stop()
            finally:
                self.easytier_session = None

    def stop_node(self) -> dict[str, Any]:
        with self._lock:
            self.stop_civ6_bridge()
            self._stop_easytier_only()
            if self.p2p_node is not None:
                self.p2p_node.stop()
                self.p2p_node = None
            self.stun_info.clear()
            self._populate_address_choices()
            self.et_connecting = False
            self.relay_active_kind = ""
            self.relay_active_name = ""
            self.et_status = "未连接 VPS 中继（请先点击「添加 VPS」配置自建节点，或直接输入节点地址）"
            self.et_status_level = "idle"
        return {"ok": True}

    def add_vps_node(self, name: str, address: str, kind: str = "easytier") -> dict[str, Any]:
        with self._lock:
            try:
                item = self._vps_store.add_node(name=name, address=address, kind=kind)
            except ValueError as e:
                return {"ok": False, "title": "VPS 节点格式错误", "message": str(e)}
            self.et_node = item.display_label()
            node_dict = item.to_dict()
        self._append_log(
            "ok", f"已保存自定义 VPS 节点: {item.name} ({item.kind_label()} · {item.address})"
        )
        return {"ok": True, "node": node_dict}

    def remove_vps_node(self, node_id: str) -> dict[str, Any]:
        with self._lock:
            existing = next((n for n in self._vps_store.list_nodes() if n.id == node_id), None)
            removed = self._vps_store.remove_node(node_id)
            if removed:
                remaining = self._vps_store.list_nodes()
                if existing and self.et_node == existing.display_label():
                    self.et_node = remaining[0].display_label() if remaining else ""
        if removed and existing:
            self._append_log("info", f"已删除自定义 VPS 节点: {existing.name} ({existing.address})")
        return {"ok": removed}

    def run_stun_probe(self) -> dict[str, Any]:
        with self._lock:
            if not (self.p2p_node and self.p2p_node.running):
                return {
                    "ok": False,
                    "title": "提示",
                    "message": "请先点击「启动节点」，再进行 STUN 公网检测。",
                }
            if self.stun_busy:
                return {"ok": True, "busy": True}
            self.stun_busy = True
            node = self.p2p_node

        self._append_log("p2p", "正在通过当前套接字向公网 STUN 服务器检测外部 IPv6 / IPv4 映射地址...")

        def worker() -> None:
            try:
                res = node.probe_stun() if node else {}
                with self._lock:
                    self.stun_busy = False
                    self.stun_info = res if isinstance(res, dict) else {}
                    if self.stun_info:
                        self._populate_address_choices()
                if res:
                    parts = [f"{k.upper()}={format_endpoint(v[0], v[1])}" for k, v in res.items()]
                    msg = "STUN 公网检测成功: " + " | ".join(parts)
                    self._append_log("ok", msg)
                    self._push_event("toast", {"level": "ok", "message": msg})
                else:
                    msg = "STUN 检测未收到响应（可直接使用网卡 IPv6 或改用「方式二：自定义 VPS 中继」）。"
                    self._append_log("warn", msg)
                    self._push_event("toast", {"level": "warn", "message": "STUN 未收到响应，可直接使用 IPv6 或自定义 VPS 中继"})
            except Exception as e:
                with self._lock:
                    self.stun_busy = False
                self._append_log("error", f"STUN 检测出错: {e}")
                self._push_event("toast", {"level": "error", "message": f"STUN 检测出错: {e}"})

        threading.Thread(target=worker, daemon=True).start()
        return {"ok": True}

    def add_peer(self, raw_input: str, force_sync_key: bool = False) -> dict[str, Any]:
        raw = str(raw_input).strip()
        try:
            parsed = parse_peer_input(raw, default_port=DEFAULT_P2P_PORT)
        except ValueError as e:
            return {
                "ok": False,
                "title": "地址格式错误",
                "message": (
                    f"{e}\n\n支持格式：\n"
                    "• c6p2://[IPv6]:38666?...\n"
                    "• [240e::1]:38666\n"
                    "• 240e::1\n"
                    "• 192.168.1.5:38666"
                ),
            }

        with self._lock:
            if parsed.room_key is not None and parsed.room_key != self.room_key.strip():
                if not (self.p2p_node and self.p2p_node.running):
                    self.room_key = parsed.room_key
                    self._append_log("info", f"已自动同步对方连接码中的房间口令: {parsed.room_key}")
                elif not force_sync_key:
                    return {
                        "ok": False,
                        "need_confirm_key": True,
                        "remote_key": parsed.room_key,
                        "local_key": self.room_key.strip(),
                    }
                else:
                    self.stop_node()
                    self.room_key = parsed.room_key
                    self._append_log("info", f"已重启节点并同步房间口令: {parsed.room_key}")

            if not (self.p2p_node and self.p2p_node.running):
                res = self.start_node()
                if not res.get("ok"):
                    return res

            assert self.p2p_node is not None
            peer = self.p2p_node.add_peer(
                host=parsed.host,
                port=parsed.port,
                nickname=parsed.nickname,
                role=parsed.role,
            )
            return {"ok": True, "peer_key": peer.peer_key}

    def connect_easytier(self, raw_nodes: str, room_name: str) -> dict[str, Any]:
        raw_nodes = str(raw_nodes).strip()
        room_name = str(room_name).strip()
        if not room_name:
            return {
                "ok": False,
                "title": "参数错误",
                "message": "请填写中继房间名（房主与好友填相同的房间名与房间口令）。",
            }

        with self._lock:
            saved_nodes = self._vps_store.list_nodes()
        try:
            kind, norm_addr, display_name = resolve_relay_input(raw_nodes, saved_nodes)
        except ValueError as e:
            return {"ok": False, "title": "VPS 节点格式错误", "message": str(e)}

        with self._lock:
            self.et_node = raw_nodes
            self.et_room = room_name
            if not (self.p2p_node and self.p2p_node.running):
                start_res = self.start_node()
                if not start_res.get("ok"):
                    return start_res

            # Direct civ6_relay_server.py UDP VPS node
            if kind == "udp_relay":
                self._stop_easytier_only()
                self.et_connecting = False
                assert self.p2p_node is not None
                try:
                    self.p2p_node.connect_relay(
                        norm_addr,
                        room_name,
                        default_port=DEFAULT_RELAY_PORT,
                        transport_name="VPS UDP 中继",
                    )
                except Exception as e:
                    return {"ok": False, "title": "连接 VPS UDP 中继失败", "message": str(e)}
                self.relay_active_kind = "udp_relay"
                self.relay_active_name = display_name
                self.et_status = f"正在连接 VPS UDP 中继 [{display_name}]（房间 [{room_name}]）..."
                self.et_status_level = "connecting"
                return {"ok": True, "kind": "udp_relay"}

            # Self-hosted EasyTier VPS node (--no-tun)
            peer_uris = parse_easytier_peers(norm_addr)
            role = self.role
            room_key = self.room_key.strip()
            nick = self.nickname.strip() or "Player"
            self.et_connecting = True
            self.relay_active_kind = "easytier"
            self.relay_active_name = display_name
            self.et_status = f"正在连接自定义 VPS [{display_name}] 并加入房间 [{room_name}]..."
            self.et_status_level = "connecting"

        def worker() -> None:
            try:
                with self._lock:
                    self._stop_easytier_only()
                session = EasyTierSession(
                    role=role,
                    room_name=room_name,
                    room_secret=room_key,
                    peer_uris=peer_uris,
                    hostname=nick,
                    log_cb=self._append_log,
                )
                local_addr = session.start()
                with self._lock:
                    self.et_connecting = False
                    if self.p2p_node and self.p2p_node.running:
                        self.easytier_session = session
                        try:
                            self.p2p_node.connect_relay(
                                local_addr,
                                room_name,
                                default_port=DEFAULT_RELAY_PORT,
                                transport_name="VPS EasyTier",
                            )
                            role_tip = "房主已就绪，等待好友加入" if self.role == "host" else "正在经自建 VPS 寻找房主"
                            self.et_status = f"VPS EasyTier 已启动 [{display_name}]（{role_tip}，房间 [{room_name}]）..."
                            self.et_status_level = "connecting"
                        except Exception as e:
                            self.disconnect_easytier()
                            self._push_event(
                                "modal",
                                {"level": "error", "title": "接入 VPS 中继通道失败", "message": str(e)},
                            )
                    else:
                        session.stop()
            except Exception as e:
                with self._lock:
                    self.et_connecting = False
                self.disconnect_easytier()
                self._push_event(
                    "modal",
                    {"level": "error", "title": "启动 VPS EasyTier 失败", "message": str(e)},
                )

        threading.Thread(target=worker, daemon=True).start()
        return {"ok": True, "kind": "easytier"}

    def disconnect_easytier(self) -> dict[str, Any]:
        with self._lock:
            # On client side, stop stale client bridge bound to old host_peer_key so rejoining works cleanly
            if self.client_bridge is not None:
                self.stop_civ6_bridge()
            if self.p2p_node is not None:
                self.p2p_node.disconnect_relay()
            self._stop_easytier_only()
            self.et_connecting = False
            self.relay_active_kind = ""
            self.relay_active_name = ""
            self.et_status = "已断开 VPS 中继"
            self.et_status_level = "idle"
        return {"ok": True}

    def test_peer(self, peer_key: str | None = None) -> dict[str, Any]:
        with self._lock:
            if not (self.p2p_node and self.p2p_node.running):
                return {"ok": False, "title": "提示", "message": "请先启动本机节点并连上好友。"}
            peers = self.p2p_node.list_peers()
            target_key = peer_key or (peers[0].peer_key if len(peers) == 1 else "")
            if not target_key:
                return {
                    "ok": False,
                    "title": "提示",
                    "message": "请先在成员列表中选中一个要测试的节点。",
                }
            if self.test_busy:
                return {"ok": True, "busy": True}
            self.test_busy = True
            node = self.p2p_node

        self._append_log("p2p", f"开始对 {target_key} 执行连通测试（3x64B 延迟 + 2x1150B 大包检测）...")

        def worker() -> None:
            try:
                res = node.run_connectivity_test(target_key, count=5, timeout_s=2.0)
                with self._lock:
                    self.test_busy = False
                    peers_now = self.p2p_node.list_peers() if self.p2p_node else []
                    gate = evaluate_step2_gate(bool(self.p2p_node and self.p2p_node.running), peers_now)
                    self._last_gate = gate
                if res.passed:
                    self._push_event(
                        "test_passed",
                        {
                            "peer_key": res.peer_key,
                            "summary": res.summary,
                            "total_online": gate.total_online,
                            "can_enter_step2": gate.can_enter_step2,
                        },
                    )
                else:
                    self._push_event(
                        "modal",
                        {
                            "level": "warn",
                            "title": "连接测试未通过",
                            "message": (
                                f"目标 {res.peer_key} 连通测试失败：\n{res.summary}\n\n"
                                "排查建议：\n"
                                "1. 确认双方节点均已启动且房间口令一致；\n"
                                "2. IPv6/P2P 模式下，双方互填连接码并点击连接可穿透大部分防火墙；\n"
                                "3. 如仍无法打洞，请切换「方式二：自定义 VPS 中继」。"
                            ),
                        },
                    )
            except Exception as e:
                with self._lock:
                    self.test_busy = False
                self._push_event(
                    "modal",
                    {"level": "error", "title": "测试失败", "message": str(e)},
                )

        threading.Thread(target=worker, daemon=True).start()
        return {"ok": True}

    def remove_peer(self, peer_key: str) -> dict[str, Any]:
        with self._lock:
            if not self.p2p_node or not peer_key:
                return {"ok": False}
            self.p2p_node.remove_peer(peer_key)
        return {"ok": True}

    # ----------------------------
    # Step 2: Civ6 Bridge Actions
    # ----------------------------

    def start_civ6_bridge(self, target_host_key: str | None = None) -> dict[str, Any]:
        with self._lock:
            peers = self.p2p_node.list_peers() if self.p2p_node else []
            gate = evaluate_step2_gate(bool(self.p2p_node and self.p2p_node.running), peers)
            self._last_gate = gate

            if not gate.can_enter_step2:
                return {"ok": False, "title": "无法开启联机辅助", "message": gate.reason}

            assert self.p2p_node is not None
            if self.role == "host":
                if self.host_bridge and self.host_bridge.running:
                    return {"ok": True}
                bridge = HostCiv6Bridge(self.p2p_node, log_cb=self._append_log)
                try:
                    bridge.start()
                except OSError as e:
                    return {"ok": False, "title": "启动失败", "message": f"启动房主桥接失败：\n{e}"}
                self.host_bridge = bridge
                self.bridge_status_text = "运行中 · 房主桥接"
                return {"ok": True, "mode": "host"}

            # Client mode
            if self.client_bridge and self.client_bridge.running:
                return {"ok": True}
            host_key = (target_host_key or self.target_host_key).strip()
            if not host_key:
                return {
                    "ok": False,
                    "title": "请选择房主",
                    "message": "请先选择一个在线且测试通过的房主节点。",
                }
            peer = self.p2p_node.get_peer(host_key)
            if peer is None or peer.status != "online" or not peer.verified:
                return {
                    "ok": False,
                    "title": "目标房主未就绪",
                    "message": "目标房主必须处于「在线」且已在第一步通过连通测试。",
                }
            self.target_host_key = host_key
            bridge = ClientCiv6Bridge(
                self.p2p_node,
                host_peer_key=host_key,
                fake_host_ip=peer.fake_ip,
                log_cb=self._append_log,
            )
            try:
                bridge.start()
            except OSError as e:
                return {
                    "ok": False,
                    "title": "启动失败",
                    "message": f"绑定本地虚拟房主端口 ({peer.fake_ip}:62900/62056) 失败：\n{e}",
                }
            self.client_bridge = bridge
            self.bridge_status_text = f"运行中 · 虚拟房主 {peer.fake_ip}"
            return {"ok": True, "mode": "client", "fake_ip": peer.fake_ip}

    def stop_civ6_bridge(self) -> dict[str, Any]:
        with self._lock:
            if self.host_bridge is not None:
                self.host_bridge.stop()
                self.host_bridge = None
            if self.client_bridge is not None:
                self.client_bridge.stop()
                self.client_bridge = None
            self.bridge_status_text = "已停止"
            self.probe_busy = False
        return {"ok": True}

    def probe_host_room(self) -> dict[str, Any]:
        with self._lock:
            if not (self.client_bridge and self.client_bridge.running):
                return {"ok": False, "title": "提示", "message": "请先启动加入者联机辅助。"}
            if self.probe_busy:
                return {"ok": True, "busy": True}
            self.probe_busy = True
            bridge = self.client_bridge

        self._append_log("civ6", "正在向房主发送文明6房间探测包 (8d e8 fc 70)...")

        def worker() -> None:
            try:
                ok, cnt, total_bytes = bridge.probe_host_room(timeout_s=1.8)
                with self._lock:
                    self.probe_busy = False
                if ok:
                    self._push_event(
                        "modal",
                        {
                            "level": "ok",
                            "title": "探测成功",
                            "message": (
                                f"成功收到房主文明6房间信息！\n({cnt} 个 UDP 包，共 {total_bytes} 字节)\n\n"
                                "现在切回文明6「多人游戏 → 局域网」点刷新即可看到房间并加入！"
                            ),
                        },
                    )
                else:
                    self._push_event(
                        "modal",
                        {
                            "level": "warn",
                            "title": "未收到房主房间响应",
                            "message": (
                                "网络已连通，但房主文明6的 62900 端口没有回复房间信息。\n\n"
                                "请确认房主：\n"
                                "1. 已在软件第二步点击「启动房主联机桥接」；\n"
                                "2. 已在文明6中创建了「局域网」房间。"
                            ),
                        },
                    )
            except Exception as e:
                with self._lock:
                    self.probe_busy = False
                self._push_event(
                    "modal",
                    {"level": "error", "title": "探测出错", "message": str(e)},
                )

        threading.Thread(target=worker, daemon=True).start()
        return {"ok": True}

    def clear_logs(self) -> dict[str, Any]:
        with self._lock:
            self._logs.clear()
        return {"ok": True}

    def copy_all_logs(self) -> dict[str, Any]:
        with self._lock:
            text = "\n".join(f"{e['ts']} {e['msg']}" for e in self._logs)
        ok = _set_windows_clipboard(text)
        self._append_log("info", "已复制日志到剪贴板。")
        return {"ok": ok}

    def shutdown(self) -> None:
        self._stop_event.set()
        try:
            self.stop_node()
        except Exception:
            pass


class GlassApi:
    """Thin public JS API exposed cleanly to window.pywebview.api (no private attributes leaked)."""

    def __init__(self, controller: GlassAppController) -> None:
        self._ctrl = controller

    def get_state(self, last_log_id: int = 0, last_event_id: int = 0) -> dict[str, Any]:
        return self._ctrl.get_state(int(last_log_id), int(last_event_id))

    def set_theme(self, theme: str) -> dict[str, Any]:
        return self._ctrl.set_theme(theme)

    def update_form(self, fields: dict[str, Any]) -> dict[str, Any]:
        return self._ctrl.update_form(fields if isinstance(fields, dict) else {})

    def refresh_network_info(self) -> dict[str, Any]:
        return self._ctrl.refresh_network_info()

    def copy_invite_code(self) -> dict[str, Any]:
        return self._ctrl.copy_invite_code()

    def copy_text(self, text: str, log_msg: str = "") -> dict[str, Any]:
        return self._ctrl.copy_text(text=text, log_msg=log_msg)

    def start_node(
        self,
        role: str = "client",
        nickname: str = "",
        port_text: str = "",
        room_key: str = "",
    ) -> dict[str, Any]:
        return self._ctrl.start_node(role=role, nickname=nickname, port_text=port_text, room_key=room_key)

    def stop_node(self) -> dict[str, Any]:
        return self._ctrl.stop_node()

    def run_stun_probe(self) -> dict[str, Any]:
        return self._ctrl.run_stun_probe()

    def add_peer(self, raw_input: str, force_sync_key: bool = False) -> dict[str, Any]:
        return self._ctrl.add_peer(raw_input=raw_input, force_sync_key=bool(force_sync_key))

    def add_vps_node(self, name: str = "", address: str = "", kind: str = "easytier") -> dict[str, Any]:
        return self._ctrl.add_vps_node(name=name, address=address, kind=kind)

    def remove_vps_node(self, node_id: str) -> dict[str, Any]:
        return self._ctrl.remove_vps_node(node_id=node_id)

    def connect_easytier(self, raw_nodes: str, room_name: str) -> dict[str, Any]:
        return self._ctrl.connect_easytier(raw_nodes=raw_nodes, room_name=room_name)

    def disconnect_easytier(self) -> dict[str, Any]:
        return self._ctrl.disconnect_easytier()

    def test_peer(self, peer_key: str = "") -> dict[str, Any]:
        return self._ctrl.test_peer(peer_key=peer_key or None)

    def remove_peer(self, peer_key: str) -> dict[str, Any]:
        return self._ctrl.remove_peer(peer_key=peer_key)

    def start_civ6_bridge(self, target_host_key: str = "") -> dict[str, Any]:
        return self._ctrl.start_civ6_bridge(target_host_key=target_host_key or None)

    def stop_civ6_bridge(self) -> dict[str, Any]:
        return self._ctrl.stop_civ6_bridge()

    def probe_host_room(self) -> dict[str, Any]:
        return self._ctrl.probe_host_room()

    def clear_logs(self) -> dict[str, Any]:
        return self._ctrl.clear_logs()

    def copy_all_logs(self) -> dict[str, Any]:
        return self._ctrl.copy_all_logs()


def run_glass_gui() -> None:
    """Launch the Xiaomi HyperOS 4 Soft-Glow Glass desktop window via WebView2."""
    import webview

    html = load_glass_html()
    controller = GlassAppController(start_bg_poller=True)
    api = GlassApi(controller)

    webview.settings["ALLOW_DOWNLOADS"] = False
    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True

    storage_root = Path(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()) / "CV6OnlineHelper" / "WebView2"
    try:
        storage_root.mkdir(parents=True, exist_ok=True)
    except OSError:
        storage_root = Path(tempfile.gettempdir()) / "CV6OnlineHelper_WV2"

    window = webview.create_window(
        title="CV6 online helper",
        html=html,
        js_api=api,
        width=1120,
        height=860,
        min_size=(960, 740),
        resizable=True,
        background_color="#EDF3FA",
        text_select=True,
    )
    controller.attach_window(window)

    def _on_shown() -> None:
        controller.resolve_and_style_hwnd()

    def _on_closed() -> None:
        controller.shutdown()

    window.events.shown += _on_shown
    window.events.closed += _on_closed

    ico_path = _find_app_icon_path()
    try:
        webview.start(
            gui="edgechromium",
            private_mode=False,
            storage_path=str(storage_root),
            icon=str(ico_path) if ico_path else None,
            debug=False,
        )
    finally:
        controller.shutdown()
