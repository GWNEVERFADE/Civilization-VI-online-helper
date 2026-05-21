#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
civ6_l3_discovery_gui.py

Civilization VI L3/VPN LAN room discovery helper, A/searcher side only.

Normal user mode:
  - No WinDivert
  - No administrator privilege required
  - No B-side helper
  - No packet capture
  - No route/metric modification
  - Python standard library only

What it does:
  1. Watches Civilization VI UDP endpoints on this PC.
  2. When Civ6 creates a new Windows dynamic UDP endpoint, sends exactly one
     discovery packet from the same source port:

       local_ip:civ6_temp_port -> host_ip:62900
       payload = 8d e8 fc 70

Use:
  1. Start Civilization VI on the searcher/client PC.
  2. Run this GUI.
  3. Enter this PC's VPN/overlay IP as Local IP, e.g. 10.88.66.2.
  4. Enter host player's VPN/overlay IP as Host IP, e.g. 10.88.66.3.
  5. Click Start.
  6. Enter/refresh Civ6 LAN room list.
"""

from __future__ import annotations

import ctypes
import os
import queue
import socket
import struct
import threading
import time
import tkinter as tk
from dataclasses import dataclass
from ctypes import wintypes
from tkinter import messagebox, ttk


# ----------------------------
# Civ6 protocol constants
# ----------------------------

CIV6_PROCESS_NAMES = {
    "civilizationvi_dx12.exe",
    "civilizationvi.exe",
}

DISCOVERY_PORT = 62900
SESSION_PORT = 62056
DISCOVERY_PAYLOAD = bytes.fromhex("8de8fc70")

WINDOWS_DYNAMIC_PORT_MIN = 49152
WINDOWS_DYNAMIC_PORT_MAX = 65535


# ----------------------------
# Polling policy
# ----------------------------

IDLE_MS = 500
BURST_MS = 3000
BURST_INTERVAL_MS = 20
PID_REFRESH_MS = 2000


# ----------------------------
# Windows constants
# ----------------------------

AF_INET = 2
ERROR_INSUFFICIENT_BUFFER = 122
NO_ERROR = 0

TH32CS_SNAPPROCESS = 0x00000002
MAX_PATH = 260

UDP_TABLE_OWNER_PID = 1

ULONG_PTR = ctypes.c_uint64 if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_uint32

kernel32 = None
iphlpapi = None


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ULONG_PTR),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * MAX_PATH),
    ]


class MIB_UDPROW_OWNER_PID(ctypes.Structure):
    _fields_ = [
        ("dwLocalAddr", wintypes.DWORD),
        ("dwLocalPort", wintypes.DWORD),
        ("dwOwningPid", wintypes.DWORD),
    ]


@dataclass(frozen=True)
class UdpEndpoint:
    local_addr: str
    local_port: int
    pid: int
    process_name: str = ""


class StopRequested(Exception):
    pass


# ----------------------------
# Low-level Windows helpers
# ----------------------------


def now_ms() -> int:
    return int(time.monotonic() * 1000)


def hex_bytes(data: bytes) -> str:
    return " ".join(f"{b:02x}" for b in data)


def init_windows_api() -> None:
    global kernel32, iphlpapi

    if os.name != "nt":
        raise RuntimeError("This tool only supports Windows.")

    if kernel32 is not None and iphlpapi is not None:
        return

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    iphlpapi = ctypes.WinDLL("iphlpapi", use_last_error=True)

    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE

    kernel32.Process32FirstW.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(PROCESSENTRY32W),
    ]
    kernel32.Process32FirstW.restype = wintypes.BOOL

    kernel32.Process32NextW.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(PROCESSENTRY32W),
    ]
    kernel32.Process32NextW.restype = wintypes.BOOL

    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    iphlpapi.GetExtendedUdpTable.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.ULONG),
        wintypes.BOOL,
        wintypes.ULONG,
        wintypes.ULONG,
        wintypes.ULONG,
    ]
    iphlpapi.GetExtendedUdpTable.restype = wintypes.DWORD


def list_processes() -> dict[int, str]:
    init_windows_api()

    result: dict[int, str] = {}
    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    invalid_handle = ctypes.c_void_p(-1).value

    if snapshot == invalid_handle or snapshot is None:
        raise ctypes.WinError(ctypes.get_last_error())

    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        ok = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))

        while ok:
            result[int(entry.th32ProcessID)] = str(entry.szExeFile)
            ok = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)

    return result


def find_civ6_processes() -> dict[int, str]:
    processes = list_processes()
    return {
        pid: name
        for pid, name in processes.items()
        if name.lower() in CIV6_PROCESS_NAMES
    }


def ipv4_from_dword(value: int) -> str:
    return socket.inet_ntoa(struct.pack("<L", int(value) & 0xFFFFFFFF))


def port_from_dword(value: int) -> int:
    # Windows MIB UDP port is stored in network byte order.
    raw = int(value) & 0xFFFF
    return socket.ntohs(raw)


def read_udp4_table() -> list[UdpEndpoint]:
    init_windows_api()

    size = wintypes.ULONG(0)
    ret = iphlpapi.GetExtendedUdpTable(
        None,
        ctypes.byref(size),
        False,
        AF_INET,
        UDP_TABLE_OWNER_PID,
        0,
    )

    if ret not in (ERROR_INSUFFICIENT_BUFFER, NO_ERROR):
        raise OSError(f"GetExtendedUdpTable size query failed: ret={ret}")

    buf = ctypes.create_string_buffer(size.value)
    ret = iphlpapi.GetExtendedUdpTable(
        ctypes.cast(buf, ctypes.c_void_p),
        ctypes.byref(size),
        False,
        AF_INET,
        UDP_TABLE_OWNER_PID,
        0,
    )

    if ret != NO_ERROR:
        raise OSError(f"GetExtendedUdpTable failed: ret={ret}")

    count = struct.unpack_from("I", buf.raw, 0)[0]
    row_size = ctypes.sizeof(MIB_UDPROW_OWNER_PID)
    offset = 4

    endpoints: list[UdpEndpoint] = []
    for i in range(count):
        row = MIB_UDPROW_OWNER_PID.from_buffer_copy(buf, offset + i * row_size)
        endpoints.append(
            UdpEndpoint(
                local_addr=ipv4_from_dword(row.dwLocalAddr),
                local_port=port_from_dword(row.dwLocalPort),
                pid=int(row.dwOwningPid),
            )
        )

    return endpoints


def is_candidate(ep: UdpEndpoint) -> bool:
    if ep.local_addr != "0.0.0.0":
        return False
    if ep.local_port == DISCOVERY_PORT:
        return False
    if ep.local_port == SESSION_PORT:
        return False
    return WINDOWS_DYNAMIC_PORT_MIN <= ep.local_port <= WINDOWS_DYNAMIC_PORT_MAX


def read_civ6_candidates(civ6_processes: dict[int, str]) -> dict[tuple[int, int], UdpEndpoint]:
    udp = read_udp4_table()
    candidates: dict[tuple[int, int], UdpEndpoint] = {}

    for ep in udp:
        if ep.pid not in civ6_processes:
            continue

        named = UdpEndpoint(
            local_addr=ep.local_addr,
            local_port=ep.local_port,
            pid=ep.pid,
            process_name=civ6_processes[ep.pid],
        )

        if is_candidate(named):
            candidates[(named.pid, named.local_port)] = named

    return candidates


def format_civ6_processes(civ6: dict[int, str]) -> str:
    if not civ6:
        return "none"
    return ", ".join(f"{name}(pid={pid})" for pid, name in sorted(civ6.items()))


# ----------------------------
# Network sending
# ----------------------------


def validate_ipv4(value: str, field_name: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError(f"{field_name} 不能为空")
    try:
        socket.inet_aton(value)
    except OSError:
        raise ValueError(f"{field_name} 不是合法 IPv4: {value}") from None
    return value


def detect_route_local_ip(host_ip: str) -> str:
    """Ask Windows routing which local IPv4 would be used to reach host_ip."""
    host_ip = validate_ipv4(host_ip, "房主 IP")
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((host_ip, DISCOVERY_PORT))
        return s.getsockname()[0]
    finally:
        s.close()


def list_local_ipv4_best_effort() -> list[str]:
    """Best-effort local IPv4 list. VPN adapters may still need manual input."""
    ips: set[str] = set()
    try:
        hostname = socket.gethostname()
        for item in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = item[4][0]
            if ip and not ip.startswith("127."):
                ips.add(ip)
    except OSError:
        pass
    return sorted(ips)


def send_discovery(local_ip: str, local_port: int, host_ip: str, log) -> bool:
    s = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((local_ip, local_port))
        actual_ip, actual_port = s.getsockname()

        sent = s.sendto(DISCOVERY_PAYLOAD, (host_ip, DISCOVERY_PORT))
        log(
            "ok",
            "SEND ok: %s:%d -> %s:%d bytes=%d payload=%s",
            actual_ip,
            actual_port,
            host_ip,
            DISCOVERY_PORT,
            sent,
            hex_bytes(DISCOVERY_PAYLOAD),
        )
        return True

    except OSError as e:
        log(
            "warn",
            "SEND fail: %s:%d -> %s:%d errno=%s winerror=%s error=%r",
            local_ip,
            local_port,
            host_ip,
            DISCOVERY_PORT,
            getattr(e, "errno", None),
            getattr(e, "winerror", None),
            e,
        )
        return False

    finally:
        if s is not None:
            try:
                s.close()
            except Exception:
                pass


# ----------------------------
# Monitor worker
# ----------------------------


def sleep_or_stop(stop_event: threading.Event, ms: int) -> None:
    if stop_event.wait(ms / 1000.0):
        raise StopRequested


def monitor_worker(local_ip: str, host_ip: str, stop_event: threading.Event, log) -> None:
    if os.name != "nt":
        log("error", "This tool only supports Windows.")
        return

    log("info", "Civ6 L3 discovery helper started")
    log(
        "info",
        "target: %s:<civ6-temp-port> -> %s:%d payload=%s",
        local_ip,
        host_ip,
        DISCOVERY_PORT,
        hex_bytes(DISCOVERY_PAYLOAD),
    )
    log(
        "info",
        "policy: idle=%dms burst=%dms burst_interval=%dms pid_refresh=%dms send_per_new_port=1",
        IDLE_MS,
        BURST_MS,
        BURST_INTERVAL_MS,
        PID_REFRESH_MS,
    )

    civ6_processes: dict[int, str] = {}
    last_pid_refresh = 0
    known: dict[tuple[int, int], dict] = {}
    baseline_ready = False
    burst_until = 0

    try:
        while True:
            if stop_event.is_set():
                raise StopRequested

            t = now_ms()

            if t - last_pid_refresh >= PID_REFRESH_MS:
                last_pid_refresh = t
                new_civ6_processes = find_civ6_processes()

                if new_civ6_processes != civ6_processes:
                    civ6_processes = new_civ6_processes
                    log("info", "Civ6 process: %s", format_civ6_processes(civ6_processes))

                    known.clear()
                    baseline_ready = False
                    burst_until = t + BURST_MS

            if not civ6_processes:
                sleep_or_stop(stop_event, IDLE_MS)
                continue

            try:
                candidates = read_civ6_candidates(civ6_processes)
            except Exception as e:
                log("error", "snapshot failed: %r", e)
                sleep_or_stop(stop_event, IDLE_MS)
                continue

            current_keys = set(candidates.keys())

            # First snapshot after Civ6 PID appears/changes is baseline.
            # Baseline ports are usually old/background ports, not the short-lived discovery port.
            if not baseline_ready:
                for key, ep in candidates.items():
                    known[key] = {
                        "ep": ep,
                        "first_seen_ms": t,
                        "last_seen_ms": t,
                        "baseline": True,
                        "sent": False,
                    }

                log(
                    "info",
                    "baseline initialized: candidate_ports=%d. Waiting for newly-created endpoint...",
                    len(candidates),
                )
                baseline_ready = True

                sleep_ms = BURST_INTERVAL_MS if now_ms() < burst_until else IDLE_MS
                sleep_or_stop(stop_event, sleep_ms)
                continue

            known_keys = set(known.keys())
            new_keys = current_keys - known_keys
            gone_keys = known_keys - current_keys
            stayed_keys = current_keys & known_keys

            if new_keys or gone_keys:
                burst_until = t + BURST_MS

            for key in stayed_keys:
                known[key]["last_seen_ms"] = t

            for key in sorted(new_keys):
                ep = candidates[key]
                known[key] = {
                    "ep": ep,
                    "first_seen_ms": t,
                    "last_seen_ms": t,
                    "baseline": False,
                    "sent": True,
                }

                log(
                    "info",
                    "NEW candidate: %s pid=%d endpoint=%s:%d",
                    ep.process_name,
                    ep.pid,
                    ep.local_addr,
                    ep.local_port,
                )
                send_discovery(local_ip, ep.local_port, host_ip, log)

            for key in sorted(gone_keys):
                state = known.pop(key)
                ep = state["ep"]

                baseline = bool(state["baseline"])
                if not baseline:
                    lifetime_ms = t - int(state["first_seen_ms"])
                    since_last_seen_ms = t - int(state["last_seen_ms"])
                    log(
                        "info",
                        "GONE candidate: port=%d lifetime≈%dms since_last_seen=%dms sent=%s",
                        ep.local_port,
                        lifetime_ms,
                        since_last_seen_ms,
                        state["sent"],
                    )

            sleep_ms = BURST_INTERVAL_MS if now_ms() < burst_until else IDLE_MS
            sleep_or_stop(stop_event, sleep_ms)

    except StopRequested:
        log("info", "stopped")
    except Exception as e:
        log("error", "worker crashed: %r", e)


# ----------------------------
# Tkinter GUI
# ----------------------------


class Civ6DiscoveryApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()

        self.title("Civ6 L3 房间发现助手")
        self.geometry("780x560")
        self.minsize(720, 500)

        self.log_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self.worker_thread: threading.Thread | None = None
        self.stop_event: threading.Event | None = None

        self.local_ip_var = tk.StringVar()
        self.host_ip_var = tk.StringVar()
        self.status_var = tk.StringVar(value="未启动")
        self.hint_var = tk.StringVar(value="先填本机 VPN/虚拟网卡 IP 和房主 IP，然后点开始。")

        self._build_style()
        self._build_ui()
        self._load_local_ips()
        self.after(100, self._drain_log_queue)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_style(self) -> None:
        self.configure(bg="#f4f7fb")
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("Root.TFrame", background="#f4f7fb")
        style.configure("Card.TFrame", background="#ffffff", relief="flat")
        style.configure("Title.TLabel", background="#f4f7fb", foreground="#111827", font=("Microsoft YaHei UI", 18, "bold"))
        style.configure("Sub.TLabel", background="#f4f7fb", foreground="#6b7280", font=("Microsoft YaHei UI", 10))
        style.configure("CardTitle.TLabel", background="#ffffff", foreground="#111827", font=("Microsoft YaHei UI", 11, "bold"))
        style.configure("Body.TLabel", background="#ffffff", foreground="#374151", font=("Microsoft YaHei UI", 9))
        style.configure("Status.TLabel", background="#ffffff", foreground="#2563eb", font=("Microsoft YaHei UI", 10, "bold"))
        style.configure("Hint.TLabel", background="#ffffff", foreground="#6b7280", font=("Microsoft YaHei UI", 9))
        style.configure("TEntry", padding=8)
        style.configure("TCombobox", padding=8)
        style.configure("Accent.TButton", padding=(14, 9), font=("Microsoft YaHei UI", 10, "bold"))
        style.configure("Soft.TButton", padding=(12, 8), font=("Microsoft YaHei UI", 9))

    def _build_ui(self) -> None:
        root = ttk.Frame(self, style="Root.TFrame", padding=18)
        root.pack(fill="both", expand=True)

        ttk.Label(root, text="Civ6 L3 房间发现助手", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            root,
            text="A/搜索端使用：监听 Civ6 新建 UDP 临时端口，并向房主 62900 单播发现包。",
            style="Sub.TLabel",
        ).pack(anchor="w", pady=(4, 14))

        card = ttk.Frame(root, style="Card.TFrame", padding=18)
        card.pack(fill="x")
        card.columnconfigure(1, weight=1)

        ttk.Label(card, text="连接参数", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(
            card,
            text="本机 IP 要填 WireGuard / 蒲公英 / 其他三层网卡上的地址。房主 IP 填 B 端在同一三层网里的地址。",
            style="Body.TLabel",
            wraplength=700,
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 14))

        ttk.Label(card, text="本机 IP", style="Body.TLabel").grid(row=2, column=0, sticky="w", padx=(0, 12), pady=6)
        self.local_ip_box = ttk.Combobox(card, textvariable=self.local_ip_var, values=[], width=28)
        self.local_ip_box.grid(row=2, column=1, sticky="ew", pady=6)
        ttk.Button(card, text="刷新本机 IP", style="Soft.TButton", command=self._load_local_ips).grid(row=2, column=2, padx=(12, 0), pady=6)

        ttk.Label(card, text="房主 IP", style="Body.TLabel").grid(row=3, column=0, sticky="w", padx=(0, 12), pady=6)
        self.host_entry = ttk.Entry(card, textvariable=self.host_ip_var)
        self.host_entry.grid(row=3, column=1, sticky="ew", pady=6)
        ttk.Button(card, text="按房主 IP 自动选本机 IP", style="Soft.TButton", command=self._auto_pick_local_ip).grid(row=3, column=2, padx=(12, 0), pady=6)

        actions = ttk.Frame(card, style="Card.TFrame")
        actions.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(14, 2))
        actions.columnconfigure(2, weight=1)

        self.start_btn = ttk.Button(actions, text="开始监听", style="Accent.TButton", command=self.start_monitor)
        self.start_btn.grid(row=0, column=0, padx=(0, 10))
        self.stop_btn = ttk.Button(actions, text="停止", style="Soft.TButton", command=self.stop_monitor, state="disabled")
        self.stop_btn.grid(row=0, column=1)
        ttk.Label(actions, textvariable=self.status_var, style="Status.TLabel").grid(row=0, column=2, sticky="e")

        ttk.Label(card, textvariable=self.hint_var, style="Hint.TLabel", wraplength=700).grid(
            row=5, column=0, columnspan=3, sticky="w", pady=(10, 0)
        )

        log_card = ttk.Frame(root, style="Card.TFrame", padding=14)
        log_card.pack(fill="both", expand=True, pady=(16, 0))
        log_card.rowconfigure(1, weight=1)
        log_card.columnconfigure(0, weight=1)

        top_line = ttk.Frame(log_card, style="Card.TFrame")
        top_line.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        top_line.columnconfigure(0, weight=1)
        ttk.Label(top_line, text="日志", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Button(top_line, text="清空", style="Soft.TButton", command=self._clear_log).grid(row=0, column=1, sticky="e")

        log_frame = tk.Frame(log_card, bg="#111827")
        log_frame.grid(row=1, column=0, sticky="nsew")
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)

        self.log_text = tk.Text(
            log_frame,
            bg="#111827",
            fg="#d1d5db",
            insertbackground="#d1d5db",
            relief="flat",
            padx=12,
            pady=10,
            wrap="word",
            font=("Consolas", 10),
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scroll.set)

        self.log_text.tag_configure("info", foreground="#d1d5db")
        self.log_text.tag_configure("ok", foreground="#86efac")
        self.log_text.tag_configure("warn", foreground="#fde68a")
        self.log_text.tag_configure("error", foreground="#fca5a5")

        self._append_log("info", "准备就绪。建议：先开工具，再进 Civ6 局域网房间列表或按刷新。")

    def _load_local_ips(self) -> None:
        ips = list_local_ipv4_best_effort()
        self.local_ip_box["values"] = ips
        if ips and not self.local_ip_var.get().strip():
            self.local_ip_var.set(ips[0])
        if ips:
            self._append_log("info", "本机 IPv4 候选: %s", ", ".join(ips))
        else:
            self._append_log("warn", "没有自动列出本机 IPv4；可以手动填写 VPN/虚拟网卡 IP。")

    def _auto_pick_local_ip(self) -> None:
        try:
            host_ip = validate_ipv4(self.host_ip_var.get(), "房主 IP")
            local_ip = detect_route_local_ip(host_ip)
            self.local_ip_var.set(local_ip)
            self._append_log("ok", "按当前路由，到 %s 会使用本机 IP: %s", host_ip, local_ip)
        except Exception as e:
            messagebox.showerror("自动选择失败", str(e))
            self._append_log("error", "自动选择本机 IP 失败: %r", e)

    def start_monitor(self) -> None:
        if self.worker_thread and self.worker_thread.is_alive():
            return

        try:
            local_ip = validate_ipv4(self.local_ip_var.get(), "本机 IP")
            host_ip = validate_ipv4(self.host_ip_var.get(), "房主 IP")
        except ValueError as e:
            messagebox.showerror("参数错误", str(e))
            return

        self.stop_event = threading.Event()
        self.worker_thread = threading.Thread(
            target=monitor_worker,
            args=(local_ip, host_ip, self.stop_event, self._thread_log),
            daemon=True,
        )
        self.worker_thread.start()

        self.status_var.set("运行中")
        self.hint_var.set("现在进入或刷新 Civ6 局域网房间列表。看到 SEND ok 后，房间通常就该出现。")
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.local_ip_box.configure(state="disabled")
        self.host_entry.configure(state="disabled")

    def stop_monitor(self) -> None:
        if self.stop_event is not None:
            self.stop_event.set()
        self.status_var.set("正在停止")
        self.stop_btn.configure(state="disabled")
        self.after(150, self._refresh_running_state)

    def _refresh_running_state(self) -> None:
        running = bool(self.worker_thread and self.worker_thread.is_alive())
        if running:
            self.after(150, self._refresh_running_state)
            return

        self.status_var.set("已停止")
        self.hint_var.set("已停止。修改 IP 后可以重新开始监听。")
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self.local_ip_box.configure(state="normal")
        self.host_entry.configure(state="normal")

    def _thread_log(self, level: str, fmt: str, *args) -> None:
        text = fmt % args if args else fmt
        ts = time.strftime("%H:%M:%S")
        self.log_queue.put((level, f"{ts} {text}"))

    def _append_log(self, level: str, fmt: str, *args) -> None:
        text = fmt % args if args else fmt
        ts = time.strftime("%H:%M:%S")
        line = f"{ts} {text}"
        self.log_text.insert("end", line + "\n", level)
        self.log_text.see("end")

    def _drain_log_queue(self) -> None:
        try:
            while True:
                level, line = self.log_queue.get_nowait()
                self.log_text.insert("end", line + "\n", level)
                self.log_text.see("end")
        except queue.Empty:
            pass

        if self.worker_thread and not self.worker_thread.is_alive() and self.status_var.get() == "运行中":
            self._refresh_running_state()

        self.after(100, self._drain_log_queue)

    def _clear_log(self) -> None:
        self.log_text.delete("1.0", "end")

    def _on_close(self) -> None:
        if self.stop_event is not None:
            self.stop_event.set()
        self.destroy()


if __name__ == "__main__":
    app = Civ6DiscoveryApp()
    app.mainloop()
