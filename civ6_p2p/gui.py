from __future__ import annotations

import queue
import socket
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

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


class Civ6P2PApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()

        self.title("CV6 online helper")
        self.geometry("1040x800")
        self.minsize(920, 720)
        try:
            from .glass_gui import _find_app_icon_path

            ico = _find_app_icon_path()
            if ico is not None:
                self.iconbitmap(str(ico))
        except Exception:
            pass

        self.log_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self.ui_queue: queue.Queue[tuple[str, object]] = queue.Queue()

        self.net_info: LocalNetworkInfo = LocalNetworkInfo()
        self.stun_info: dict[str, tuple[str, int]] = {}
        self.local_civ6_state: Civ6LocalState = Civ6LocalState()
        self._civ6_state_lock = threading.Lock()
        self._last_civ6_poll = 0.0

        self.p2p_node: P2PNode | None = None
        self.easytier_session: EasyTierSession | None = None
        self.host_bridge: HostCiv6Bridge | None = None
        self.client_bridge: ClientCiv6Bridge | None = None
        self._last_gate: Step2GateState = evaluate_step2_gate(False, [])

        default_nick = socket.gethostname()[:16] or "Player"
        self.role_var = tk.StringVar(value="client")
        self.nickname_var = tk.StringVar(value=default_nick)
        self.port_var = tk.StringVar(value=str(DEFAULT_P2P_PORT))
        self.room_key_var = tk.StringVar(value=DEFAULT_ROOM_KEY)
        self.conn_mode_var = tk.StringVar(value="p2p_ipv6")

        self.advertise_ip_var = tk.StringVar()
        self.invite_code_var = tk.StringVar(value="启动本机节点后自动生成连接码")
        self.peer_input_var = tk.StringVar()

        self._vps_store = VpsNodeStore()
        self._vps_label_to_id: dict[str, str] = {}
        self._et_preset_labels: list[str] = []
        self.et_node_var = tk.StringVar(value="")
        self.et_room_var = tk.StringVar(value=DEFAULT_RELAY_ROOM)
        self.et_status_var = tk.StringVar(value="⚪ 未连接 VPS 中继（请先添加或输入自建 VPS 节点）")
        self._relay_active_kind: str = ""

        self.badge_ipv6_var = tk.StringVar(value="IPv6: 检测中...")
        self.badge_node_var = tk.StringVar(value="节点: 未启动")
        self.badge_online_var = tk.StringVar(value="在线: 0 人")
        self.badge_civ6_var = tk.StringVar(value="本机文明6: 未运行")

        self.step1_banner_var = tk.StringVar(
            value="请先启动本机联机节点，选择「IPv6/P2P 直连」或「服务器中继」连上好友（至少 2 人在线）并测试连通通过，才能解锁第二步。"
        )

        self.target_host_var = tk.StringVar()
        self.preflight_node_var = tk.StringVar(value="❌ 本机节点未启动")
        self.preflight_peer_var = tk.StringVar(value="❌ 在线人数不足 2 人")
        self.preflight_local_civ6_var = tk.StringVar(value="⚪ 本机文明6未运行")
        self.preflight_remote_civ6_var = tk.StringVar(value="⚪ 等待对端在线同步状态")
        self.bridge_status_var = tk.StringVar(value="未启动")
        self.bridge_activity_var = tk.StringVar(value="已通过第一步连接验证，可以开启文明6联机辅助。")
        self.stat_disc_var = tk.StringVar(value="62900 发现: 请求 0 / 房主回包 0")
        self.stat_sess_tx_var = tk.StringVar(value="62056 发送: 0 包 (0 B)")
        self.stat_sess_rx_var = tk.StringVar(value="62056 接收: 0 包 (0 B)")

        self._addr_display_to_ip: dict[str, str] = {}
        self._peer_label_to_key: dict[str, str] = {}

        self._build_style()
        self._build_ui()
        self._refresh_network_info()
        self._apply_step2_gate(self._last_gate)

        self.after(120, self._ui_tick)
        self.protocol("WM_DELETE_WINDOW", self._on_close)


    def _build_style(self) -> None:
        self.configure(bg="#f1f5f9")
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("Root.TFrame", background="#f1f5f9")
        style.configure("Card.TFrame", background="#ffffff", relief="flat")
        style.configure("SubCard.TFrame", background="#f8fafc", relief="flat")
        style.configure("Banner.TFrame", background="#eff6ff", relief="flat")
        style.configure("BannerOk.TFrame", background="#ecfdf5", relief="flat")

        style.configure("Title.TLabel", background="#f1f5f9", foreground="#0f172a", font=("Microsoft YaHei UI", 16, "bold"))
        style.configure("Sub.TLabel", background="#f1f5f9", foreground="#475569", font=("Microsoft YaHei UI", 9))
        style.configure("Badge.TLabel", background="#e2e8f0", foreground="#1e293b", font=("Microsoft YaHei UI", 9, "bold"), padding=(8, 4))
        style.configure("BadgeOk.TLabel", background="#dcfce7", foreground="#166534", font=("Microsoft YaHei UI", 9, "bold"), padding=(8, 4))
        style.configure("BadgeWarn.TLabel", background="#fef3c7", foreground="#92400e", font=("Microsoft YaHei UI", 9, "bold"), padding=(8, 4))

        style.configure("CardTitle.TLabel", background="#ffffff", foreground="#0f172a", font=("Microsoft YaHei UI", 10, "bold"))
        style.configure("Body.TLabel", background="#ffffff", foreground="#334155", font=("Microsoft YaHei UI", 9))
        style.configure("Hint.TLabel", background="#ffffff", foreground="#64748b", font=("Microsoft YaHei UI", 9))
        style.configure("Mono.TLabel", background="#ffffff", foreground="#0f172a", font=("Consolas", 9, "bold"))
        style.configure("SubBody.TLabel", background="#f8fafc", foreground="#334155", font=("Microsoft YaHei UI", 9))
        style.configure("SubHint.TLabel", background="#f8fafc", foreground="#64748b", font=("Microsoft YaHei UI", 9))
        style.configure("SubMono.TLabel", background="#f8fafc", foreground="#0f172a", font=("Consolas", 9, "bold"))
        style.configure("Banner.TLabel", background="#eff6ff", foreground="#1e40af", font=("Microsoft YaHei UI", 9, "bold"))
        style.configure("BannerOk.TLabel", background="#ecfdf5", foreground="#065f46", font=("Microsoft YaHei UI", 9, "bold"))

        style.configure("TNotebook", background="#f1f5f9", borderwidth=0)
        style.configure("TNotebook.Tab", padding=(16, 7), font=("Microsoft YaHei UI", 9, "bold"))
        style.configure("Accent.TButton", padding=(12, 6), font=("Microsoft YaHei UI", 9, "bold"))
        style.configure("Soft.TButton", padding=(10, 5), font=("Microsoft YaHei UI", 9))
        style.configure("Treeview", rowheight=26, font=("Microsoft YaHei UI", 9))
        style.configure("Treeview.Heading", font=("Microsoft YaHei UI", 9, "bold"))

    def _build_ui(self) -> None:
        root = ttk.Frame(self, style="Root.TFrame", padding=14)
        root.pack(fill="both", expand=True)

        header = ttk.Frame(root, style="Root.TFrame")
        header.pack(fill="x", pady=(0, 10))
        header.columnconfigure(0, weight=1)

        left_hdr = ttk.Frame(header, style="Root.TFrame")
        left_hdr.grid(row=0, column=0, sticky="w")
        ttk.Label(left_hdr, text="CV6 online helper", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            left_hdr,
            text="第一步：IPv6/P2P 直连 或 自定义 VPS 中继联通测速（至少 2 人在线） → 第二步：解锁文明6联机辅助",
            style="Sub.TLabel",
        ).pack(anchor="w")

        right_hdr = ttk.Frame(header, style="Root.TFrame")
        right_hdr.grid(row=0, column=1, sticky="e")
        self.badge_ipv6_lbl = ttk.Label(right_hdr, textvariable=self.badge_ipv6_var, style="Badge.TLabel")
        self.badge_ipv6_lbl.pack(side="left", padx=3)
        self.badge_node_lbl = ttk.Label(right_hdr, textvariable=self.badge_node_var, style="Badge.TLabel")
        self.badge_node_lbl.pack(side="left", padx=3)
        self.badge_online_lbl = ttk.Label(right_hdr, textvariable=self.badge_online_var, style="Badge.TLabel")
        self.badge_online_lbl.pack(side="left", padx=3)
        self.badge_civ6_lbl = ttk.Label(right_hdr, textvariable=self.badge_civ6_var, style="Badge.TLabel")
        self.badge_civ6_lbl.pack(side="left", padx=3)

        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill="both", expand=True)

        self.tab_step1 = ttk.Frame(self.notebook, style="Root.TFrame", padding=10)
        self.tab_step2 = ttk.Frame(self.notebook, style="Root.TFrame", padding=10)

        self.notebook.add(self.tab_step1, text="  第一步 · 联机联通（IPv6/P2P · VPS 中继）  ")
        self.notebook.add(self.tab_step2, text="  第二步 · 文明6 联机辅助（🔒 待第一步连通解锁）  ", state="disabled")

        self._build_tab_step1()
        self._build_tab_step2()

        log_card = ttk.Frame(root, style="Card.TFrame", padding=10)
        log_card.pack(fill="x", pady=(10, 0))
        log_card.columnconfigure(0, weight=1)

        log_top = ttk.Frame(log_card, style="Card.TFrame")
        log_top.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        log_top.columnconfigure(0, weight=1)
        ttk.Label(log_top, text="运行日志", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Button(log_top, text="复制日志", style="Soft.TButton", command=self._copy_log).grid(row=0, column=1, padx=(0, 6))
        ttk.Button(log_top, text="清空", style="Soft.TButton", command=self._clear_log).grid(row=0, column=2)

        log_box = tk.Frame(log_card, bg="#0f172a")
        log_box.grid(row=1, column=0, sticky="ew")
        log_box.columnconfigure(0, weight=1)

        self.log_text = tk.Text(
            log_box,
            height=7,
            bg="#0f172a",
            fg="#e2e8f0",
            insertbackground="#e2e8f0",
            relief="flat",
            padx=10,
            pady=6,
            wrap="word",
            font=("Consolas", 9),
        )
        self.log_text.grid(row=0, column=0, sticky="ew")
        scroll = ttk.Scrollbar(log_box, command=self.log_text.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scroll.set)

        self.log_text.tag_configure("info", foreground="#cbd5e1")
        self.log_text.tag_configure("ok", foreground="#86efac")
        self.log_text.tag_configure("warn", foreground="#fde68a")
        self.log_text.tag_configure("error", foreground="#fca5a5")
        self.log_text.tag_configure("p2p", foreground="#93c5fd")
        self.log_text.tag_configure("civ6", foreground="#c4b5fd")

        self._append_log("info", "欢迎使用 CV6 online helper！请先在第一步通过「IPv6/P2P 直连」或「服务器中继」连上好友并测试通过（至少 2 人在线），即可解锁第二步。")

    def _build_tab_step1(self) -> None:
        c1 = ttk.Frame(self.tab_step1, style="Card.TFrame", padding=10)
        c1.pack(fill="x", pady=(0, 8))
        c1.columnconfigure(7, weight=1)

        ttk.Label(c1, text="1. 本机联机节点", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=8, sticky="w", pady=(0, 6))

        ttk.Label(c1, text="角色:", style="Body.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 4))
        role_box = ttk.Frame(c1, style="Card.TFrame")
        role_box.grid(row=1, column=1, sticky="w", padx=(0, 12))
        self.rb_host = ttk.Radiobutton(role_box, text="房主", value="host", variable=self.role_var, command=self._on_role_changed)
        self.rb_host.pack(side="left", padx=(0, 6))
        self.rb_client = ttk.Radiobutton(role_box, text="加入者", value="client", variable=self.role_var, command=self._on_role_changed)
        self.rb_client.pack(side="left")

        ttk.Label(c1, text="昵称:", style="Body.TLabel").grid(row=1, column=2, sticky="w", padx=(0, 4))
        self.nick_entry = ttk.Entry(c1, textvariable=self.nickname_var, width=13)
        self.nick_entry.grid(row=1, column=3, sticky="w", padx=(0, 10))

        ttk.Label(c1, text="端口:", style="Body.TLabel").grid(row=1, column=4, sticky="w", padx=(0, 4))
        self.port_entry = ttk.Entry(c1, textvariable=self.port_var, width=7)
        self.port_entry.grid(row=1, column=5, sticky="w", padx=(0, 10))

        ttk.Label(c1, text="房间口令:", style="Body.TLabel").grid(row=1, column=6, sticky="w", padx=(0, 4))
        key_ctrl = ttk.Frame(c1, style="Card.TFrame")
        key_ctrl.grid(row=1, column=7, sticky="ew")
        key_ctrl.columnconfigure(0, weight=1)
        self.key_entry = ttk.Entry(key_ctrl, textvariable=self.room_key_var, width=12)
        self.key_entry.grid(row=0, column=0, sticky="w", padx=(0, 10))

        node_btns = ttk.Frame(key_ctrl, style="Card.TFrame")
        node_btns.grid(row=0, column=1, sticky="e")
        self.start_node_btn = ttk.Button(node_btns, text="启动节点", style="Accent.TButton", command=self._start_p2p_node)
        self.start_node_btn.pack(side="left", padx=(0, 6))
        self.stop_node_btn = ttk.Button(node_btns, text="停止", style="Soft.TButton", command=self._stop_p2p_node, state="disabled")
        self.stop_node_btn.pack(side="left")

        c2 = ttk.Frame(self.tab_step1, style="Card.TFrame", padding=10)
        c2.pack(fill="x", pady=(0, 8))
        c2.columnconfigure(0, weight=1)

        mode_hdr = ttk.Frame(c2, style="Card.TFrame")
        mode_hdr.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(mode_hdr, text="2. 联机方式:", style="CardTitle.TLabel").pack(side="left", padx=(0, 14))
        ttk.Radiobutton(
            mode_hdr,
            text="方式一：IPv6 / P2P 直连（公网 IPv6 与 UDP 打洞）",
            value="p2p_ipv6",
            variable=self.conn_mode_var,
            command=self._switch_conn_mode,
        ).pack(side="left", padx=(0, 18))
        ttk.Radiobutton(
            mode_hdr,
            text="方式二：自定义 VPS 中继（EasyTier VPS · 轻量 UDP 中继）",
            value="relay",
            variable=self.conn_mode_var,
            command=self._switch_conn_mode,
        ).pack(side="left")

        self.mode_container = ttk.Frame(c2, style="SubCard.TFrame", padding=10)
        self.mode_container.grid(row=1, column=0, sticky="ew")
        self.mode_container.columnconfigure(0, weight=1)

        self.panel_p2p = ttk.Frame(self.mode_container, style="SubCard.TFrame")
        self.panel_p2p.columnconfigure(1, weight=1)

        ttk.Label(self.panel_p2p, text="本机对外地址:", style="SubBody.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=3)
        self.addr_combo = ttk.Combobox(self.panel_p2p, textvariable=self.advertise_ip_var, width=42)
        self.addr_combo.grid(row=0, column=1, sticky="ew", padx=(0, 8), pady=3)
        self.addr_combo.bind("<<ComboboxSelected>>", lambda _e: self._update_invite_code())

        p2p_addr_btns = ttk.Frame(self.panel_p2p, style="SubCard.TFrame")
        p2p_addr_btns.grid(row=0, column=2, sticky="e", pady=3)
        ttk.Button(p2p_addr_btns, text="刷新地址", style="Soft.TButton", command=self._refresh_network_info).pack(side="left", padx=(0, 6))
        self.stun_btn = ttk.Button(p2p_addr_btns, text="STUN公网检测", style="Soft.TButton", command=self._run_stun_probe)
        self.stun_btn.pack(side="left")

        ttk.Label(self.panel_p2p, text="我的连接码:", style="SubBody.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=3)
        self.invite_entry = ttk.Entry(self.panel_p2p, textvariable=self.invite_code_var, state="readonly")
        self.invite_entry.grid(row=1, column=1, sticky="ew", padx=(0, 8), pady=3)
        ttk.Button(self.panel_p2p, text="复制我的连接码", style="Soft.TButton", command=self._copy_invite_code).grid(
            row=1, column=2, sticky="e", pady=3
        )

        ttk.Label(self.panel_p2p, text="对方连接码/IP:", style="SubBody.TLabel").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=(5, 2))
        self.peer_entry = ttk.Entry(self.panel_p2p, textvariable=self.peer_input_var)
        self.peer_entry.grid(row=2, column=1, sticky="ew", padx=(0, 8), pady=(5, 2))
        self.peer_entry.bind("<Return>", lambda _e: self._add_peer())
        ttk.Button(self.panel_p2p, text="添加并连接 / 打洞", style="Accent.TButton", command=self._add_peer).grid(
            row=2, column=2, sticky="e", pady=(5, 2)
        )

        self.panel_relay = ttk.Frame(self.mode_container, style="SubCard.TFrame")
        self.panel_relay.columnconfigure(1, weight=2)
        self.panel_relay.columnconfigure(3, weight=1)

        ttk.Label(self.panel_relay, text="VPS 节点:", style="SubBody.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 6), pady=3)
        self.et_node_combo = ttk.Combobox(self.panel_relay, textvariable=self.et_node_var, values=self._et_preset_labels, width=38)
        self.et_node_combo.grid(row=0, column=1, sticky="ew", padx=(0, 6), pady=3)

        ttk.Label(self.panel_relay, text="房间名:", style="SubBody.TLabel").grid(row=0, column=2, sticky="w", padx=(0, 6), pady=3)
        self.et_room_entry = ttk.Entry(self.panel_relay, textvariable=self.et_room_var, width=14)
        self.et_room_entry.grid(row=0, column=3, sticky="ew", padx=(0, 8), pady=3)

        r_act = ttk.Frame(self.panel_relay, style="SubCard.TFrame")
        r_act.grid(row=0, column=4, sticky="e", pady=3)
        self.et_add_vps_btn = ttk.Button(r_act, text="+ 添加VPS", style="Soft.TButton", command=self._prompt_add_vps_node)
        self.et_add_vps_btn.pack(side="left", padx=(0, 6))
        self.et_del_vps_btn = ttk.Button(r_act, text="删除", style="Soft.TButton", command=self._delete_selected_vps_node)
        self.et_del_vps_btn.pack(side="left", padx=(0, 6))
        self.et_conn_btn = ttk.Button(r_act, text="连接 VPS 房间", style="Accent.TButton", command=self._connect_easytier)
        self.et_conn_btn.pack(side="left", padx=(0, 6))
        self.et_disc_btn = ttk.Button(r_act, text="断开", style="Soft.TButton", command=self._disconnect_easytier, state="disabled")
        self.et_disc_btn.pack(side="left")

        ttk.Label(self.panel_relay, textvariable=self.et_status_var, style="SubMono.TLabel").grid(
            row=1, column=0, columnspan=5, sticky="w", pady=(5, 3)
        )
        guide_bar = ttk.Frame(self.panel_relay, style="SubCard.TFrame")
        guide_bar.grid(row=2, column=0, columnspan=5, sticky="w", pady=(2, 0))
        ttk.Button(guide_bar, text="P2P 使用说明", style="Soft.TButton", command=self._show_p2p_guide).pack(side="left", padx=(0, 6))
        ttk.Button(guide_bar, text="VPS 使用说明", style="Soft.TButton", command=self._show_vps_guide).pack(side="left")
        self._reload_vps_choices()

        self._switch_conn_mode()

        c3 = ttk.Frame(self.tab_step1, style="Card.TFrame", padding=10)
        c3.pack(fill="both", expand=True)
        c3.columnconfigure(0, weight=1)
        c3.rowconfigure(1, weight=1)

        list_hdr = ttk.Frame(c3, style="Card.TFrame")
        list_hdr.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        list_hdr.columnconfigure(0, weight=1)
        ttk.Label(list_hdr, text="3. 在线成员与连通测试（至少 2 人在线且测试通过后解锁第二步）", style="CardTitle.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        t_btns = ttk.Frame(list_hdr, style="Card.TFrame")
        t_btns.grid(row=0, column=1, sticky="e")
        self.test_peer_btn = ttk.Button(t_btns, text="测试选中连接", style="Accent.TButton", command=self._test_selected_peer)
        self.test_peer_btn.pack(side="left", padx=(0, 6))
        ttk.Button(t_btns, text="移除选中", style="Soft.TButton", command=self._remove_selected_peer).pack(side="left")

        tree_frame = ttk.Frame(c3, style="Card.TFrame")
        tree_frame.grid(row=1, column=0, sticky="nsew")
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)

        cols = ("nickname", "role", "transport", "endpoint", "status", "rtt", "loss", "civ6", "test", "fake_ip")
        self.peer_tree = ttk.Treeview(tree_frame, columns=cols, show="headings", height=5)
        headings = [
            ("nickname", "昵称", 90),
            ("role", "角色", 56),
            ("transport", "连接方式", 92),
            ("endpoint", "对方地址 / 节点", 175),
            ("status", "在线状态", 88),
            ("rtt", "延迟", 60),
            ("loss", "丢包", 50),
            ("civ6", "对方文明6", 110),
            ("test", "连通测试", 140),
            ("fake_ip", "虚拟IP", 82),
        ]
        for cid, text, width in headings:
            self.peer_tree.heading(cid, text=text)
            self.peer_tree.column(cid, width=width, anchor="center" if cid not in ("endpoint", "test") else "w")

        self.peer_tree.grid(row=0, column=0, sticky="nsew")
        t_scroll = ttk.Scrollbar(tree_frame, command=self.peer_tree.yview)
        t_scroll.grid(row=0, column=1, sticky="ns")
        self.peer_tree.configure(yscrollcommand=t_scroll.set)

        self.peer_tree.tag_configure("online", foreground="#15803d")
        self.peer_tree.tag_configure("connecting", foreground="#b45309")
        self.peer_tree.tag_configure("offline", foreground="#b91c1c")

        self.step1_banner = ttk.Frame(c3, style="Banner.TFrame", padding=(10, 8))
        self.step1_banner.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        self.step1_banner.columnconfigure(0, weight=1)

        self.step1_banner_lbl = ttk.Label(self.step1_banner, textvariable=self.step1_banner_var, style="Banner.TLabel")
        self.step1_banner_lbl.grid(row=0, column=0, sticky="w")
        self.goto_step2_btn = ttk.Button(
            self.step1_banner,
            text="进入第二步 · 文明6 联机辅助 →",
            style="Accent.TButton",
            command=self._goto_step2,
            state="disabled",
        )
        self.goto_step2_btn.grid(row=0, column=1, sticky="e", padx=(10, 0))

    def _build_tab_step2(self) -> None:
        c1 = ttk.Frame(self.tab_step2, style="Card.TFrame", padding=12)
        c1.pack(fill="x", pady=(0, 8))
        c1.columnconfigure(1, weight=1)
        c1.columnconfigure(3, weight=1)

        ttk.Label(c1, text="联机状态检查（需至少 2 人在线且连通测试通过）", style="CardTitle.TLabel").grid(
            row=0, column=0, columnspan=4, sticky="w", pady=(0, 8)
        )

        ttk.Label(c1, text="本机节点:", style="Body.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=3)
        ttk.Label(c1, textvariable=self.preflight_node_var, style="Mono.TLabel").grid(row=1, column=1, sticky="w", pady=3)

        ttk.Label(c1, text="在线与测试:", style="Body.TLabel").grid(row=1, column=2, sticky="w", padx=(16, 8), pady=3)
        ttk.Label(c1, textvariable=self.preflight_peer_var, style="Mono.TLabel").grid(row=1, column=3, sticky="w", pady=3)

        ttk.Label(c1, text="本机文明6:", style="Body.TLabel").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=3)
        ttk.Label(c1, textvariable=self.preflight_local_civ6_var, style="Mono.TLabel").grid(row=2, column=1, sticky="w", pady=3)

        ttk.Label(c1, text="对端文明6:", style="Body.TLabel").grid(row=2, column=2, sticky="w", padx=(16, 8), pady=3)
        ttk.Label(c1, textvariable=self.preflight_remote_civ6_var, style="Mono.TLabel").grid(row=2, column=3, sticky="w", pady=3)

        c2 = ttk.Frame(self.tab_step2, style="Card.TFrame", padding=12)
        c2.pack(fill="x", pady=(0, 8))
        c2.columnconfigure(1, weight=1)

        ttk.Label(c2, text="文明6 联机辅助控制", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 6))
        self.civ6_mode_desc_lbl = ttk.Label(
            c2,
            text="当前角色：加入者。选择已连通测试通过的房主节点并启动辅助后，回文明6「多人游戏 → 局域网」刷新即可看到房间并直接加入。",
            style="Hint.TLabel",
            wraplength=900,
        )
        self.civ6_mode_desc_lbl.grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 10))

        self.target_host_lbl = ttk.Label(c2, text="目标房主节点:", style="Body.TLabel")
        self.target_host_lbl.grid(row=2, column=0, sticky="w", padx=(0, 8), pady=4)
        self.target_host_combo = ttk.Combobox(c2, textvariable=self.target_host_var, state="readonly", width=50)
        self.target_host_combo.grid(row=2, column=1, sticky="ew", padx=(0, 10), pady=4)

        self.probe_room_btn = ttk.Button(c2, text="探测房主文明6房间", style="Soft.TButton", command=self._probe_host_room, state="disabled")
        self.probe_room_btn.grid(row=2, column=2, sticky="e", pady=4)

        act = ttk.Frame(c2, style="Card.TFrame")
        act.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(10, 2))
        act.columnconfigure(2, weight=1)

        self.start_bridge_btn = ttk.Button(
            act, text="启动文明6联机辅助", style="Accent.TButton", command=self._start_civ6_bridge, state="disabled"
        )
        self.start_bridge_btn.grid(row=0, column=0, padx=(0, 8))
        self.stop_bridge_btn = ttk.Button(act, text="停止辅助", style="Soft.TButton", command=self._stop_civ6_bridge, state="disabled")
        self.stop_bridge_btn.grid(row=0, column=1)
        ttk.Label(act, textvariable=self.bridge_status_var, style="CardTitle.TLabel").grid(row=0, column=2, sticky="e")

        c3 = ttk.Frame(self.tab_step2, style="Card.TFrame", padding=12)
        c3.pack(fill="both", expand=True)
        c3.columnconfigure(0, weight=1)
        c3.columnconfigure(1, weight=1)
        c3.columnconfigure(2, weight=1)

        ttk.Label(c3, text="实时联机流量与诊断", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))
        ttk.Label(c3, textvariable=self.stat_disc_var, style="Mono.TLabel").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Label(c3, textvariable=self.stat_sess_tx_var, style="Mono.TLabel").grid(row=1, column=1, sticky="w", pady=4)
        ttk.Label(c3, textvariable=self.stat_sess_rx_var, style="Mono.TLabel").grid(row=1, column=2, sticky="w", pady=4)

        ttk.Label(c3, textvariable=self.bridge_activity_var, style="Body.TLabel", wraplength=900).grid(
            row=2, column=0, columnspan=3, sticky="w", pady=(8, 4)
        )
        ttk.Label(
            c3,
            text="使用要点：① 房主在文明6创建局域网房间并点「启动房主联机桥接」；② 加入者选择已通过测试的房主并点「启动加入者联机辅助」；③ 可先点「探测房主文明6房间」确认收到房间信息，再切回文明6局域网刷新加入。",
            style="Hint.TLabel",
            wraplength=900,
        ).grid(row=3, column=0, columnspan=3, sticky="w", pady=(6, 0))

    def _switch_conn_mode(self) -> None:
        if self.conn_mode_var.get() == "relay":
            self.panel_p2p.grid_forget()
            self.panel_relay.grid(row=0, column=0, sticky="ew")
        else:
            self.panel_relay.grid_forget()
            self.panel_p2p.grid(row=0, column=0, sticky="ew")


    def _refresh_network_info(self) -> None:
        self.net_info = detect_local_network_info()
        self._populate_address_choices()

        if self.net_info.has_public_ipv6:
            self.badge_ipv6_var.set("IPv6: 公网就绪 ✅")
            self.badge_ipv6_lbl.configure(style="BadgeOk.TLabel")
            self._append_log("ok", f"检测到本机公网 IPv6: {self.net_info.default_ipv6 or self.net_info.global_ipv6[0]}")
        else:
            self.badge_ipv6_var.set("IPv6: 无公网")
            self.badge_ipv6_lbl.configure(style="BadgeWarn.TLabel")
            self._append_log("warn", "未检测到公网 IPv6 地址（仍可使用 P2P/STUN 或切换「方式二：服务器中继」）。")

    def _populate_address_choices(self) -> None:
        self._addr_display_to_ip.clear()
        display_values: list[str] = []

        if "ipv6" in self.stun_info:
            ip, port = self.stun_info["ipv6"]
            label = f"{ip}  [STUN公网IPv6 :{port}]"
            self._addr_display_to_ip[label] = ip
            display_values.append(label)
        if "ipv4" in self.stun_info:
            ip, port = self.stun_info["ipv4"]
            label = f"{ip}  [STUN公网IPv4 :{port}]"
            self._addr_display_to_ip[label] = ip
            display_values.append(label)

        for ip, desc in self.net_info.all_candidates():
            label = f"{ip}  [{desc}]"
            if label not in self._addr_display_to_ip:
                self._addr_display_to_ip[label] = ip
                display_values.append(label)

        self.addr_combo["values"] = display_values
        if display_values:
            cur = self.advertise_ip_var.get().strip()
            if not cur or cur not in display_values:
                self.advertise_ip_var.set(display_values[0])
        self._update_invite_code()

    def _selected_advertise_host_port(self) -> tuple[str, int]:
        raw_sel = self.advertise_ip_var.get().strip()
        ip = self._addr_display_to_ip.get(raw_sel, raw_sel.split()[0] if raw_sel else "::1")

        port = self.p2p_node.actual_port if (self.p2p_node and self.p2p_node.running) else self._parse_port_safe()
        if "[STUN公网IPv6" in raw_sel and "ipv6" in self.stun_info:
            port = self.stun_info["ipv6"][1]
        elif "[STUN公网IPv4" in raw_sel and "ipv4" in self.stun_info:
            port = self.stun_info["ipv4"][1]
        return ip, port

    def _parse_port_safe(self) -> int:
        try:
            p = int(self.port_var.get().strip())
            return p if 1 <= p <= 65535 else DEFAULT_P2P_PORT
        except ValueError:
            return DEFAULT_P2P_PORT

    def _update_invite_code(self) -> None:
        if not (self.p2p_node and self.p2p_node.running):
            self.invite_code_var.set("启动本机节点后自动生成连接码")
            return
        try:
            ip, port = self._selected_advertise_host_port()
            code = build_invite_code(
                host=ip,
                port=port,
                nickname=self.nickname_var.get().strip(),
                role=self.role_var.get().strip(),
                room_key=self.room_key_var.get().strip(),
            )
            self.invite_code_var.set(code)
        except Exception:
            self.invite_code_var.set("请选择有效的本机 IP 地址")

    def _copy_invite_code(self) -> None:
        if not (self.p2p_node and self.p2p_node.running):
            messagebox.showinfo("提示", "请先点击「启动节点」。")
            return
        self._update_invite_code()
        code = self.invite_code_var.get().strip()
        self.clipboard_clear()
        self.clipboard_append(code)
        self._append_log("ok", f"已复制本机连接码: {code}")

    def _run_stun_probe(self) -> None:
        if not (self.p2p_node and self.p2p_node.running):
            messagebox.showinfo("提示", "请先点击「启动节点」，再进行 STUN 公网检测。")
            return
        self.stun_btn.configure(state="disabled")
        self._append_log("p2p", "正在通过当前套接字向公网 STUN 服务器检测外部 IPv6 / IPv4 映射地址...")

        def worker() -> None:
            try:
                res = self.p2p_node.probe_stun() if self.p2p_node else {}
                self.ui_queue.put(("stun_done", res))
            except Exception as e:
                self.ui_queue.put(("stun_err", str(e)))

        threading.Thread(target=worker, daemon=True).start()


    def _on_role_changed(self) -> None:
        role = self.role_var.get()
        if self.p2p_node and self.p2p_node.running:
            self.p2p_node.update_identity(nickname=self.nickname_var.get(), role=role)
            self._update_invite_code()

        if role == "host":
            self.civ6_mode_desc_lbl.configure(
                text="当前角色：房主。在文明6创建「局域网」房间后，点「启动房主联机桥接」即可服务所有在线好友（至少 2 人在线方可开启）。"
            )
            self.target_host_lbl.configure(text="当前模式:")
            self.target_host_combo.configure(state="disabled")
            self.target_host_var.set("房主模式（自动服务所有已在线好友）")
            self.probe_room_btn.configure(state="disabled")
            self.start_bridge_btn.configure(text="启动房主联机桥接")
        else:
            self.civ6_mode_desc_lbl.configure(
                text="当前角色：加入者。选择已连通测试通过的房主节点并启动辅助后，回文明6「多人游戏 → 局域网」刷新即可看到房间并直接加入。"
            )
            self.target_host_lbl.configure(text="目标房主节点:")
            self.target_host_combo.configure(state="readonly")
            self.start_bridge_btn.configure(text="启动加入者联机辅助")
            self._sync_target_host_combo()

    def _get_local_civ6_status_dict(self) -> dict:
        with self._civ6_state_lock:
            return self.local_civ6_state.to_status_dict()

    def _start_p2p_node(self) -> None:
        if self.p2p_node and self.p2p_node.running:
            return
        try:
            port = int(self.port_var.get().strip())
            if not (0 <= port <= 65535):
                raise ValueError
        except ValueError:
            messagebox.showerror("端口错误", "监听端口必须是 0-65535 之间的整数（推荐 38666）。")
            return

        node = P2PNode(
            nickname=self.nickname_var.get().strip() or "Player",
            role=self.role_var.get(),
            listen_port=port,
            room_key=self.room_key_var.get().strip(),
            log_cb=self._thread_log,
            local_civ6_status_fn=self._get_local_civ6_status_dict,
        )
        try:
            actual_port = node.start()
        except OSError as e:
            messagebox.showerror("启动失败", f"无法绑定 UDP 端口 {port}：\n{e}\n\n可更换端口后重试。")
            return

        self.p2p_node = node
        self.port_var.set(str(actual_port))
        self.start_node_btn.configure(state="disabled")
        self.stop_node_btn.configure(state="normal")
        self.port_entry.configure(state="disabled")
        self.key_entry.configure(state="disabled")

        self.badge_node_var.set(f"节点: 运行中 :{actual_port}")
        self.badge_node_lbl.configure(style="BadgeOk.TLabel")
        self._update_invite_code()
        self._on_role_changed()
        self._refresh_peer_table()

    def _stop_p2p_node(self) -> None:
        self._stop_civ6_bridge()
        self._stop_easytier_only()
        if self.p2p_node is not None:
            self.p2p_node.stop()
            self.p2p_node = None
        self.stun_info.clear()
        self._populate_address_choices()
        self.start_node_btn.configure(state="normal")
        self.stop_node_btn.configure(state="disabled")
        self.port_entry.configure(state="normal")
        self.key_entry.configure(state="normal")
        self.rb_host.configure(state="normal")
        self.rb_client.configure(state="normal")
        self.badge_node_var.set("节点: 未启动")
        self.badge_node_lbl.configure(style="Badge.TLabel")
        self.et_conn_btn.configure(state="normal")
        self.et_disc_btn.configure(state="disabled")
        self.et_node_combo.configure(state="normal")
        self.et_room_entry.configure(state="normal")
        self._relay_active_kind = ""
        self.et_status_var.set("⚪ 未连接 VPS 中继（请先添加或输入自建 VPS 节点）")
        self._update_invite_code()
        self._refresh_peer_table()

    def _add_peer(self) -> None:
        raw = self.peer_input_var.get().strip()
        try:
            parsed = parse_peer_input(raw, default_port=DEFAULT_P2P_PORT)
        except ValueError as e:
            messagebox.showerror(
                "地址格式错误",
                f"{e}\n\n支持格式：\n• c6p2://[IPv6]:38666?...\n• [240e::1]:38666\n• 240e::1\n• 192.168.1.5:38666",
            )
            return

        if parsed.room_key is not None and parsed.room_key != self.room_key_var.get().strip():
            if not (self.p2p_node and self.p2p_node.running):
                self.room_key_var.set(parsed.room_key)
                self._append_log("info", f"已自动同步对方连接码中的房间口令: {parsed.room_key}")
            else:
                if messagebox.askyesno(
                    "房间口令不一致",
                    f"对方连接码口令为「{parsed.room_key}」，与本机「{self.room_key_var.get().strip()}」不同。\n\n是否重启本机节点以同步口令？",
                ):
                    self._stop_p2p_node()
                    self.room_key_var.set(parsed.room_key)

        if not (self.p2p_node and self.p2p_node.running):
            self._start_p2p_node()
            if not (self.p2p_node and self.p2p_node.running):
                return

        assert self.p2p_node is not None
        peer = self.p2p_node.add_peer(
            host=parsed.host,
            port=parsed.port,
            nickname=parsed.nickname,
            role=parsed.role,
        )
        self.peer_input_var.set("")
        self._refresh_peer_table()
        if self.peer_tree.exists(peer.peer_key):
            self.peer_tree.selection_set(peer.peer_key)

    def _show_p2p_guide(self) -> None:
        messagebox.showinfo(
            "P2P 使用说明",
            "【IPv6 / P2P 直连使用说明】\n\n"
            "1. 房主选「房主」、加入者选「加入者」，填写相同的「房间口令」并点击「启动节点」。\n"
            "2. 有公网 IPv6 时优先选择 [首选公网 IPv6]；无公网 IPv6 可点「STUN 公网检测」。\n"
            "3. 点击「复制我的连接码」发给好友，双方互填对方连接码并点「添加并连接 / 打洞」。\n"
            "4. 在线人数 ≥ 2 且状态显示在线后，点击「测试选中连接」，通过即解锁第二步。\n\n"
            "若处于对称 NAT / 校园网无法打洞，请切换「方式二 · 自定义 VPS 中继」。",
        )

    def _show_vps_guide(self) -> None:
        messagebox.showinfo(
            "VPS 使用说明",
            "【自定义 VPS 中继使用说明】\n\n"
            "方案一 · EasyTier 自建 VPS（推荐，端口 TCP/UDP 11010）：\n"
            "  VPS 运行：./easytier-core --no-tun -l tcp://0.0.0.0:11010 -l udp://0.0.0.0:11010\n"
            "  客户端点「+ 添加VPS」选 EasyTier，填入 tcp://你的VPS公网IP:11010\n\n"
            "方案二 · 轻量 UDP 中继（civ6_relay_server，端口 UDP 38668）：\n"
            "  VPS 运行：python3 civ6_relay_server.py --port 38668\n"
            "  客户端点「+ 添加VPS」选 轻量 UDP 中继，填入 你的VPS公网IP:38668\n\n"
            "连接步骤：双方选中同一 VPS 节点并填相同「房间名」和「房间口令」，点击「连接 VPS 房间」，在线后测试连接即可解锁第二步。",
        )

    def _reload_vps_choices(self, select_label: str | None = None) -> None:
        nodes = self._vps_store.list_nodes()
        self._vps_label_to_id = {n.display_label(): n.id for n in nodes}
        labels = [n.display_label() for n in nodes]
        self._et_preset_labels = labels
        self.et_node_combo["values"] = labels
        if select_label is not None:
            self.et_node_var.set(select_label)
        elif not self.et_node_var.get().strip() and labels:
            self.et_node_var.set(labels[0])

    def _prompt_add_vps_node(self) -> None:
        dlg = tk.Toplevel(self)
        dlg.title("添加自定义 VPS 节点")
        dlg.transient(self)
        dlg.grab_set()
        dlg.resizable(False, False)

        frm = ttk.Frame(dlg, padding=14)
        frm.pack(fill="both", expand=True)

        kind_var = tk.StringVar(value="easytier")
        name_var = tk.StringVar()
        addr_var = tk.StringVar()

        ttk.Label(frm, text="节点类型:").grid(row=0, column=0, sticky="w", pady=4)
        kbox = ttk.Frame(frm)
        kbox.grid(row=0, column=1, sticky="w", pady=4)
        ttk.Radiobutton(kbox, text="EasyTier VPS (11010)", value="easytier", variable=kind_var).pack(side="left", padx=(0, 8))
        ttk.Radiobutton(kbox, text="轻量 UDP 中继 (38668)", value="udp_relay", variable=kind_var).pack(side="left")

        ttk.Label(frm, text="备注名称:").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(frm, textvariable=name_var, width=36).grid(row=1, column=1, sticky="ew", pady=4)

        ttk.Label(frm, text="节点地址:").grid(row=2, column=0, sticky="w", pady=4)
        addr_ent = ttk.Entry(frm, textvariable=addr_var, width=36)
        addr_ent.grid(row=2, column=1, sticky="ew", pady=4)
        addr_ent.focus_set()

        def save() -> None:
            try:
                item = self._vps_store.add_node(name_var.get(), addr_var.get(), kind_var.get())
            except ValueError as e:
                messagebox.showerror("VPS 节点格式错误", str(e), parent=dlg)
                return
            self._reload_vps_choices(select_label=item.display_label())
            self._append_log("ok", f"已保存自定义 VPS 节点: {item.name} ({item.address})")
            dlg.destroy()

        btns = ttk.Frame(frm)
        btns.grid(row=3, column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(btns, text="取消", command=dlg.destroy).pack(side="left", padx=(0, 6))
        ttk.Button(btns, text="保存节点", command=save).pack(side="left")

    def _delete_selected_vps_node(self) -> None:
        cur = self.et_node_var.get().strip()
        nid = self._vps_label_to_id.get(cur)
        if not nid:
            messagebox.showinfo("提示", "当前未选中已保存的 VPS 节点。")
            return
        if self._vps_store.remove_node(nid):
            remaining = self._vps_store.list_nodes()
            self._reload_vps_choices(select_label=remaining[0].display_label() if remaining else "")
            self._append_log("info", f"已删除自定义 VPS 节点: {cur}")

    def _stop_easytier_only(self) -> None:
        if self.easytier_session is not None:
            self.easytier_session.stop()
            self.easytier_session = None

    def _connect_easytier(self) -> None:
        raw_nodes = self.et_node_var.get().strip()
        room_name = self.et_room_var.get().strip()
        if not room_name:
            messagebox.showerror("参数错误", "请填写中继房间名（房主与好友填相同的房间名与房间口令）。")
            return
        try:
            kind, norm_addr, display_name = resolve_relay_input(raw_nodes, self._vps_store.list_nodes())
        except ValueError as e:
            messagebox.showerror("VPS 节点格式错误", str(e))
            return

        if not (self.p2p_node and self.p2p_node.running):
            self._start_p2p_node()
            if not (self.p2p_node and self.p2p_node.running):
                return

        if kind == "udp_relay":
            assert self.p2p_node is not None
            try:
                self.p2p_node.connect_relay(
                    norm_addr,
                    room_name,
                    default_port=DEFAULT_RELAY_PORT,
                    transport_name="VPS UDP 中继",
                )
            except Exception as e:
                messagebox.showerror("连接 VPS UDP 中继失败", str(e))
                return
            self._relay_active_kind = "udp_relay"
            self.et_conn_btn.configure(state="disabled")
            self.et_disc_btn.configure(state="normal")
            self.et_node_combo.configure(state="disabled")
            self.et_room_entry.configure(state="disabled")
            self.et_status_var.set(f"🟡 正在连接 VPS UDP 中继 [{display_name}]（房间 [{room_name}]）...")
            return

        peer_uris = parse_easytier_peers(norm_addr)
        role = self.role_var.get()
        room_key = self.room_key_var.get().strip()
        nick = self.nickname_var.get().strip() or "Player"

        self._relay_active_kind = "easytier"
        self.et_conn_btn.configure(state="disabled")
        self.et_node_combo.configure(state="disabled")
        self.et_room_entry.configure(state="disabled")
        self.rb_host.configure(state="disabled")
        self.rb_client.configure(state="disabled")
        self.et_status_var.set(f"🟡 正在连接自定义 VPS [{display_name}] 并加入房间 [{room_name}]...")

        def worker() -> None:
            try:
                self._stop_easytier_only()
                session = EasyTierSession(
                    role=role,
                    room_name=room_name,
                    room_secret=room_key,
                    peer_uris=peer_uris,
                    hostname=nick,
                    log_cb=self._thread_log,
                )
                local_addr = session.start()
                self.ui_queue.put(("et_started", (session, local_addr, room_name)))
            except Exception as e:
                self.ui_queue.put(("et_failed", str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def _disconnect_easytier(self) -> None:
        if self.client_bridge is not None:
            self._stop_civ6_bridge()
        if self.p2p_node is not None:
            self.p2p_node.disconnect_relay()
        self._stop_easytier_only()
        self._relay_active_kind = ""
        self.et_conn_btn.configure(state="normal")
        self.et_disc_btn.configure(state="disabled")
        self.et_node_combo.configure(state="normal")
        self.et_room_entry.configure(state="normal")
        if not self._has_active_bridge():
            self.rb_host.configure(state="normal")
            self.rb_client.configure(state="normal")
        self.et_status_var.set("⚪ 已断开 VPS 中继")
        self._refresh_peer_table()

    def _get_selected_peer_key(self) -> str | None:
        sel = self.peer_tree.selection()
        if sel:
            return sel[0]
        children = self.peer_tree.get_children()
        return children[0] if len(children) == 1 else None

    def _test_selected_peer(self) -> None:
        if not (self.p2p_node and self.p2p_node.running):
            messagebox.showinfo("提示", "请先启动本机节点并连上好友。")
            return
        peer_key = self._get_selected_peer_key()
        if not peer_key:
            messagebox.showinfo("提示", "请先在成员列表中选中一个要测试的节点。")
            return

        self.test_peer_btn.configure(state="disabled")
        self._append_log("p2p", f"开始对 {peer_key} 执行连通测试（3x64B 延迟 + 2x1150B 大包检测）...")
        node = self.p2p_node

        def worker() -> None:
            try:
                res = node.run_connectivity_test(peer_key, count=5, timeout_s=2.0)
                self.ui_queue.put(("test_done", res))
            except Exception as e:
                self.ui_queue.put(("test_err", str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def _remove_selected_peer(self) -> None:
        if not self.p2p_node:
            return
        peer_key = self._get_selected_peer_key()
        if not peer_key:
            return
        self.p2p_node.remove_peer(peer_key)
        self._refresh_peer_table()


    def _has_active_bridge(self) -> bool:
        return bool(
            (self.host_bridge and self.host_bridge.running)
            or (self.client_bridge and self.client_bridge.running)
        )

    def _apply_step2_gate(self, gate: Step2GateState) -> None:
        self._last_gate = gate
        active_bridge = self._has_active_bridge()
        step2_unlocked = gate.can_enter_step2 or active_bridge

        self.badge_online_var.set(f"在线: {gate.total_online} 人")
        if gate.total_online >= 2:
            self.badge_online_lbl.configure(style="BadgeOk.TLabel")
        elif gate.total_online == 1:
            self.badge_online_lbl.configure(style="BadgeWarn.TLabel")
        else:
            self.badge_online_lbl.configure(style="Badge.TLabel")

        self.step1_banner_var.set(gate.reason)
        if gate.can_enter_step2:
            self.step1_banner.configure(style="BannerOk.TFrame")
            self.step1_banner_lbl.configure(style="BannerOk.TLabel")
            self.goto_step2_btn.configure(state="normal")
        else:
            self.step1_banner.configure(style="Banner.TFrame")
            self.step1_banner_lbl.configure(style="Banner.TLabel")
            self.goto_step2_btn.configure(state="normal" if active_bridge else "disabled")

        if step2_unlocked:
            self.notebook.tab(
                self.tab_step2,
                state="normal",
                text=f"  第二步 · 文明6 联机辅助（✅ 在线 {gate.total_online} 人）  ",
            )
        else:
            if str(self.notebook.select()) == str(self.tab_step2):
                self.notebook.select(self.tab_step1)
                self._append_log("warn", "在线人数不足 2 人或尚未测试通过，第二步已重新锁定。")
            self.notebook.tab(
                self.tab_step2,
                state="disabled",
                text="  第二步 · 文明6 联机辅助（🔒 待第一步连通解锁）  ",
            )

        if not active_bridge:
            can_start = gate.can_enter_step2
            if can_start and self.role_var.get() == "client":
                sel_label = self.target_host_var.get()
                host_key = self._peer_label_to_key.get(sel_label)
                target_peer = next((p for p in gate.verified_online_peers if p.peer_key == host_key), None)
                can_start = target_peer is not None
            self.start_bridge_btn.configure(state="normal" if can_start else "disabled")

    def _goto_step2(self) -> None:
        if not (self._last_gate.can_enter_step2 or self._has_active_bridge()):
            messagebox.showwarning("第一步尚未完成", self._last_gate.reason)
            return
        self._on_role_changed()
        self.notebook.select(self.tab_step2)


    def _start_civ6_bridge(self) -> None:
        peers = self.p2p_node.list_peers() if self.p2p_node else []
        gate = evaluate_step2_gate(bool(self.p2p_node and self.p2p_node.running), peers)
        self._apply_step2_gate(gate)

        if not gate.can_enter_step2:
            messagebox.showwarning("无法开启联机辅助", gate.reason)
            return

        assert self.p2p_node is not None
        role = self.role_var.get()

        if role == "host":
            if self.host_bridge and self.host_bridge.running:
                return
            bridge = HostCiv6Bridge(self.p2p_node, log_cb=self._thread_log)
            try:
                bridge.start()
            except OSError as e:
                messagebox.showerror("启动失败", f"启动房主桥接失败：\n{e}")
                return
            self.host_bridge = bridge
            self.bridge_status_var.set("运行中 (房主桥接)")
            self.start_bridge_btn.configure(state="disabled")
            self.stop_bridge_btn.configure(state="normal")
            self.rb_host.configure(state="disabled")
            self.rb_client.configure(state="disabled")
        else:
            if self.client_bridge and self.client_bridge.running:
                return
            sel_label = self.target_host_var.get()
            host_key = self._peer_label_to_key.get(sel_label)
            if not host_key:
                messagebox.showwarning("请选择房主", "请先选择一个在线且测试通过的房主节点。")
                return
            peer = self.p2p_node.get_peer(host_key)
            if peer is None or peer.status != "online" or not peer.verified:
                messagebox.showwarning("目标房主未就绪", "目标房主必须处于「🟢 在线」且已在第一步通过连通测试。")
                return

            bridge = ClientCiv6Bridge(
                self.p2p_node,
                host_peer_key=host_key,
                fake_host_ip=peer.fake_ip,
                log_cb=self._thread_log,
            )
            try:
                bridge.start()
            except OSError as e:
                messagebox.showerror("启动失败", f"绑定本地虚拟房主端口 ({peer.fake_ip}:62900/62056) 失败：\n{e}")
                return
            self.client_bridge = bridge
            self.bridge_status_var.set(f"运行中 (虚拟房主 {peer.fake_ip})")
            self.start_bridge_btn.configure(state="disabled")
            self.stop_bridge_btn.configure(state="normal")
            self.probe_room_btn.configure(state="normal")
            self.target_host_combo.configure(state="disabled")
            self.rb_host.configure(state="disabled")
            self.rb_client.configure(state="disabled")

    def _stop_civ6_bridge(self) -> None:
        if self.host_bridge is not None:
            self.host_bridge.stop()
            self.host_bridge = None
        if self.client_bridge is not None:
            self.client_bridge.stop()
            self.client_bridge = None

        self.bridge_status_var.set("已停止")
        self.stop_bridge_btn.configure(state="disabled")
        self.probe_room_btn.configure(state="disabled")
        if self.easytier_session is None:
            self.rb_host.configure(state="normal")
            self.rb_client.configure(state="normal")
        if self.role_var.get() == "client":
            self.target_host_combo.configure(state="readonly")
        self._apply_step2_gate(self._last_gate)

    def _probe_host_room(self) -> None:
        if not (self.client_bridge and self.client_bridge.running):
            return
        self.probe_room_btn.configure(state="disabled")
        self._append_log("civ6", "正在向房主发送文明6房间探测包 (8d e8 fc 70)...")
        bridge = self.client_bridge

        def worker() -> None:
            try:
                res = bridge.probe_host_room(timeout_s=1.8)
                self.ui_queue.put(("probe_done", res))
            except Exception as e:
                self.ui_queue.put(("probe_err", str(e)))

        threading.Thread(target=worker, daemon=True).start()


    def _ui_tick(self) -> None:
        try:
            while True:
                level, line = self.log_queue.get_nowait()
                self.log_text.insert("end", line + "\n", level)
                self.log_text.see("end")
        except queue.Empty:
            pass

        try:
            while True:
                ev, payload = self.ui_queue.get_nowait()
                self._handle_ui_event(ev, payload)
        except queue.Empty:
            pass

        now = time.monotonic()
        if now - self._last_civ6_poll >= 2.0:
            self._last_civ6_poll = now
            threading.Thread(target=self._poll_local_civ6_bg, daemon=True).start()

        self._refresh_peer_table()
        self._refresh_step2_status()

        self.after(200, self._ui_tick)

    def _poll_local_civ6_bg(self) -> None:
        st = inspect_civ6_state()
        with self._civ6_state_lock:
            self.local_civ6_state = st

    def _handle_ui_event(self, ev: str, payload: object) -> None:
        if ev == "stun_done":
            self.stun_btn.configure(state="normal")
            res = payload if isinstance(payload, dict) else {}
            self.stun_info = res
            if res:
                parts = [f"{k.upper()}={format_endpoint(v[0], v[1])}" for k, v in res.items()]
                self._append_log("ok", "STUN 公网检测成功: " + " | ".join(parts))
                self._populate_address_choices()
            else:
                self._append_log("warn", "STUN 检测未收到响应（可直接使用网卡 IPv6 或改用「方式二：服务器中继」）。")
        elif ev == "stun_err":
            self.stun_btn.configure(state="normal")
            self._append_log("error", f"STUN 检测出错: {payload}")
        elif ev == "test_done":
            self.test_peer_btn.configure(state="normal")
            res = payload
            self._refresh_peer_table()
            if getattr(res, "passed", False):
                if messagebox.askyesno(
                    "第一步连接测试成功",
                    f"已与 {res.peer_key} 连通测试通过！\n\n"
                    f"测试结果: {res.summary}\n"
                    f"当前在线人数: {self._last_gate.total_online} 人（满足 ≥ 2 人要求）\n\n"
                    "「第二步 · 文明6 联机辅助」已解锁，是否立即进入？",
                ):
                    self._goto_step2()
            else:
                messagebox.showwarning(
                    "连接测试未通过",
                    f"目标 {res.peer_key} 连通测试失败：\n{res.summary}\n\n"
                    "排查建议：\n"
                    "1. 确认双方节点均已启动且房间口令一致；\n"
                    "2. IPv6/P2P 模式下，双方互填连接码并点击连接可穿透大部分防火墙；\n"
                    "3. 如仍无法打洞，请切换「方式二：服务器中继」。",
                )
        elif ev == "test_err":
            self.test_peer_btn.configure(state="normal")
            messagebox.showerror("测试失败", str(payload))
        elif ev == "probe_done":
            if self.client_bridge and self.client_bridge.running:
                self.probe_room_btn.configure(state="normal")
            ok, cnt, total_bytes = payload
            if ok:
                messagebox.showinfo(
                    "探测成功",
                    f"成功收到房主文明6房间信息！\n({cnt} 个 UDP 包，共 {total_bytes} 字节)\n\n现在切回文明6「多人游戏 → 局域网」点刷新即可看到房间并加入！",
                )
            else:
                messagebox.showwarning(
                    "未收到房主房间响应",
                    "网络已连通，但房主文明6的 62900 端口没有回复房间信息。\n\n"
                    "请确认房主：\n1. 已在软件第二步点击「启动房主联机桥接」；\n2. 已在文明6中创建了「局域网」房间。",
                )
        elif ev == "et_started":
            session, local_addr, room_name = payload
            self.easytier_session = session
            if self.p2p_node and self.p2p_node.running:
                try:
                    self.p2p_node.connect_relay(
                        local_addr,
                        room_name,
                        default_port=DEFAULT_RELAY_PORT,
                        transport_name="EasyTier 中继",
                    )
                    self.et_disc_btn.configure(state="normal")
                    role_tip = "房主已就绪，等待好友加入" if self.role_var.get() == "host" else "正在经 EasyTier 寻找房主"
                    self.et_status_var.set(f"🟡 EasyTier 已启动 ({role_tip}，房间 [{room_name}])...")
                except Exception as e:
                    self._disconnect_easytier()
                    messagebox.showerror("接入 EasyTier 通道失败", str(e))
            else:
                session.stop()
        elif ev == "et_failed":
            self._disconnect_easytier()
            messagebox.showerror("启动 EasyTier 失败", str(payload))
        elif ev == "probe_err":
            if self.client_bridge and self.client_bridge.running:
                self.probe_room_btn.configure(state="normal")
            messagebox.showerror("探测出错", str(payload))

    def _refresh_peer_table(self) -> None:
        node_running = bool(self.p2p_node and self.p2p_node.running)
        peers: list[PeerState] = self.p2p_node.list_peers() if self.p2p_node else []
        existing_ids = set(self.peer_tree.get_children())
        new_ids = {p.peer_key for p in peers}

        for old_id in existing_ids - new_ids:
            self.peer_tree.delete(old_id)

        for p in peers:
            if p.status == "online":
                status_txt = "🟢 在线"
            elif p.status == "connecting":
                status_txt = "🟡 连接中" if p.transport == "relay" else "🟡 打洞连接中"
            else:
                status_txt = "🔴 离线"

            role_txt = {"host": "房主", "client": "加入者"}.get(p.role, "未知")
            rtt_txt = f"{p.rtt_ms:.0f} ms" if p.rtt_ms is not None else "-"
            loss_txt = f"{p.loss_pct:.0f}%" if p.status == "online" else "-"
            values = (
                p.nickname,
                role_txt,
                p.transport_label(),
                p.peer_key,
                status_txt,
                rtt_txt,
                loss_txt,
                p.remote_civ6_summary(),
                p.last_test_summary,
                p.fake_ip,
            )
            if self.peer_tree.exists(p.peer_key):
                self.peer_tree.item(p.peer_key, values=values, tags=(p.status,))
            else:
                self.peer_tree.insert("", "end", iid=p.peer_key, values=values, tags=(p.status,))

        if node_running and self.p2p_node is not None:
            rst = self.p2p_node.get_relay_status()
            if self.easytier_session is not None:
                if not self.easytier_session.running:
                    self.et_status_var.set("🔴 VPS EasyTier 进程意外退出，请检查日志后重连")
                elif rst.enabled and rst.connected:
                    self.et_status_var.set(
                        f"🟢 VPS EasyTier 已连接 | 房间 [{rst.room_id}] 当前 {rst.room_members} 人在线（自动打洞/中继）"
                    )
                elif rst.enabled:
                    role_tip = "等待 VPS 通道就绪" if self.role_var.get() == "client" else "正在初始化房间"
                    self.et_status_var.set(f"🟡 VPS EasyTier 运行中 ({role_tip}，房间 [{rst.room_id}])...")
            elif self._relay_active_kind == "udp_relay" and rst.enabled:
                if rst.connected:
                    self.et_status_var.set(
                        f"🟢 VPS UDP 中继已连接 | 房间 [{rst.room_id}] 当前 {rst.room_members} 人在线"
                    )
                else:
                    self.et_status_var.set(f"🟡 正在连接 VPS UDP 中继（房间 [{rst.room_id}]）...")

        self._sync_target_host_combo(peers)
        gate = evaluate_step2_gate(node_running, peers)
        self._apply_step2_gate(gate)

    def _sync_target_host_combo(self, peers: list[PeerState] | None = None) -> None:
        if self.role_var.get() != "client":
            return
        if peers is None:
            peers = self.p2p_node.list_peers() if self.p2p_node else []
        self._peer_label_to_key.clear()
        labels: list[str] = []
        verified_online = sorted(
            [p for p in peers if p.status == "online" and p.verified],
            key=lambda p: (0 if p.role == "host" else 1, p.peer_key),
        )
        for p in verified_online:
            lbl = f"{p.nickname} [{p.transport_label()} · 在线✅] ({p.peer_key})"
            self._peer_label_to_key[lbl] = p.peer_key
            labels.append(lbl)

        self.target_host_combo["values"] = labels
        cur = self.target_host_var.get()
        if labels and cur not in labels:
            self.target_host_var.set(labels[0])
        elif not labels:
            self.target_host_var.set("")

    def _refresh_step2_status(self) -> None:
        with self._civ6_state_lock:
            st = self.local_civ6_state
        summary = st.human_summary()
        self.badge_civ6_var.set(f"本机文明6: {summary}")
        if st.running:
            self.badge_civ6_lbl.configure(style="BadgeOk.TLabel")
            self.preflight_local_civ6_var.set(f"✅ {summary}")
        else:
            self.badge_civ6_lbl.configure(style="Badge.TLabel")
            self.preflight_local_civ6_var.set("⚪ 未检测到文明6进程")

        if self.p2p_node and self.p2p_node.running:
            self.preflight_node_var.set(f"✅ 运行中 (UDP :{self.p2p_node.actual_port})")
        else:
            self.preflight_node_var.set("❌ 尚未启动")

        gate = self._last_gate
        if gate.can_enter_step2:
            p0 = gate.verified_online_peers[0]
            rtt = f"{p0.rtt_ms:.0f}ms" if p0.rtt_ms is not None else "-"
            self.preflight_peer_var.set(f"✅ 共 {gate.total_online} 人在线 ({p0.nickname} {rtt} 已通过测试)")
        else:
            self.preflight_peer_var.set(f"❌ 共 {gate.total_online} 人在线（未满足开启条件）")

        if gate.online_peers:
            parts = [f"{p.nickname}: {p.remote_civ6_summary()}" for p in gate.online_peers[:2]]
            self.preflight_remote_civ6_var.set(" | ".join(parts))
        else:
            self.preflight_remote_civ6_var.set("⚪ 等待对端在线同步状态")

        bridge = (
            self.host_bridge
            if (self.host_bridge and self.host_bridge.running)
            else (self.client_bridge if (self.client_bridge and self.client_bridge.running) else None)
        )
        if bridge is not None:
            bs = bridge.get_stats()
            self.stat_disc_var.set(f"62900 发现: 请求 {bs.disc_reqs} / 房主回包 {bs.disc_resps}")
            self.stat_sess_tx_var.set(f"62056 发送: {bs.session_tx_pkts} 包 ({_fmt_bytes(bs.session_tx_bytes)})")
            self.stat_sess_rx_var.set(f"62056 接收: {bs.session_rx_pkts} 包 ({_fmt_bytes(bs.session_rx_bytes)})")
            if gate.total_online < 2:
                self.bridge_activity_var.set("⚠️ 当前在线不足 2 人，等待好友重新上线...")
            else:
                self.bridge_activity_var.set(f"当前状态: {bs.last_activity_desc}")


    def _thread_log(self, level: str, msg: str) -> None:
        ts = time.strftime("%H:%M:%S")
        self.log_queue.put((level, f"{ts} {msg}"))

    def _append_log(self, level: str, msg: str) -> None:
        ts = time.strftime("%H:%M:%S")
        self.log_text.insert("end", f"{ts} {msg}\n", level)
        self.log_text.see("end")

    def _clear_log(self) -> None:
        self.log_text.delete("1.0", "end")

    def _copy_log(self) -> None:
        content = self.log_text.get("1.0", "end-1c")
        self.clipboard_clear()
        self.clipboard_append(content)
        self._append_log("info", "已复制日志到剪贴板。")

    def _on_close(self) -> None:
        try:
            self._stop_p2p_node()
        finally:
            self.destroy()


def run_gui() -> None:
    try:
        from .glass_gui import run_glass_gui

        run_glass_gui()
        return
    except Exception:
        pass

    app = Civ6P2PApp()
    app.mainloop()
