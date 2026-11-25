from __future__ import annotations

import secrets
import select
import socket
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable

from .network_utils import (
    DEFAULT_STUN_SERVERS,
    build_stun_binding_request,
    canonicalize_ip,
    create_dualstack_udp_socket,
    format_endpoint,
    is_stun_packet,
    parse_stun_binding_response,
    to_sockaddr,
)
from .protocol import (
    DEFAULT_P2P_PORT,
    DEFAULT_RELAY_PORT,
    DEFAULT_ROOM_KEY,
    MsgType,
    compute_room_tag,
    pack_civ6_disc,
    pack_json_packet,
    pack_packet,
    pack_relay_forward,
    pack_test_req,
    pack_test_resp,
    parse_server_address,
    unpack_civ6_disc,
    unpack_json_payload,
    unpack_packet,
    unpack_relay_forward,
    unpack_test_req,
    unpack_test_resp,
)

HEARTBEAT_INTERVAL_S = 1.5
OFFLINE_TIMEOUT_S = 6.0
PUNCH_FAST_INTERVAL_S = 0.5
PUNCH_FAST_DURATION_S = 10.0
PUNCH_SLOW_INTERVAL_S = 2.0
RELAY_REGISTER_INTERVAL_S = 3.0
RELAY_RETRY_INTERVAL_S = 1.0
RELAY_TIMEOUT_S = 10.0


def _now_ms() -> int:
    return int(time.monotonic() * 1000)


@dataclass
class RelayClientStatus:
    enabled: bool = False
    connected: bool = False
    server_display: str = ""
    room_id: str = ""
    room_members: int = 0


@dataclass
class PeerState:
    peer_key: str
    host: str
    port: int
    ip_version: int
    fake_ip: str
    transport: str = "direct"
    transport_name: str = ""
    nickname: str = ""
    role: str = "unknown"
    node_id: str = ""
    status: str = "connecting"
    verified: bool = False
    last_test_summary: str = "未测试"

    rtt_ms: float | None = None
    min_rtt_ms: float | None = None
    jitter_ms: float | None = None
    loss_pct: float = 0.0

    added_at: float = field(default_factory=time.monotonic)
    last_seen: float = 0.0
    last_ping_sent: float = 0.0
    last_punch_sent: float = 0.0
    connected_since: float | None = None

    remote_civ6_running: bool = False
    remote_civ6_room_ready: bool = False
    remote_civ6_session_ready: bool = False

    tx_packets: int = 0
    rx_packets: int = 0
    tx_bytes: int = 0
    rx_bytes: int = 0

    _ping_seq: int = 0
    _recent_pings: deque = field(default_factory=lambda: deque(maxlen=20), repr=False)
    _acked_seqs: set = field(default_factory=set, repr=False)

    def transport_label(self) -> str:
        if self.transport == "relay":
            return self.transport_name or "EasyTier 中继"
        return "IPv6/P2P 直连" if self.ip_version == 6 else "IPv4/P2P 直连"

    def copy_snapshot(self) -> "PeerState":
        return PeerState(
            peer_key=self.peer_key,
            host=self.host,
            port=self.port,
            ip_version=self.ip_version,
            fake_ip=self.fake_ip,
            transport=self.transport,
            transport_name=self.transport_name,
            nickname=self.nickname,
            role=self.role,
            node_id=self.node_id,
            status=self.status,
            verified=self.verified,
            last_test_summary=self.last_test_summary,
            rtt_ms=self.rtt_ms,
            min_rtt_ms=self.min_rtt_ms,
            jitter_ms=self.jitter_ms,
            loss_pct=self.loss_pct,
            added_at=self.added_at,
            last_seen=self.last_seen,
            last_ping_sent=self.last_ping_sent,
            last_punch_sent=self.last_punch_sent,
            connected_since=self.connected_since,
            remote_civ6_running=self.remote_civ6_running,
            remote_civ6_room_ready=self.remote_civ6_room_ready,
            remote_civ6_session_ready=self.remote_civ6_session_ready,
            tx_packets=self.tx_packets,
            rx_packets=self.rx_packets,
            tx_bytes=self.tx_bytes,
            rx_bytes=self.rx_bytes,
        )

    def remote_civ6_summary(self) -> str:
        if self.status != "online":
            return "-"
        if not self.remote_civ6_running:
            return "未运行"
        if self.remote_civ6_room_ready:
            return "已开房 (62900就绪)"
        if self.remote_civ6_session_ready:
            return "运行中 (62056)"
        return "运行中"


@dataclass
class Step2GateState:
    node_running: bool
    total_online: int
    online_peers: list[PeerState]
    verified_online_peers: list[PeerState]
    can_enter_step2: bool
    reason: str


def evaluate_step2_gate(node_running: bool, peers: list[PeerState]) -> Step2GateState:
    online_peers = [p for p in peers if p.status == "online"]
    verified_online = [p for p in online_peers if p.verified]
    total_online = (1 if node_running else 0) + len(online_peers)

    if not node_running:
        return Step2GateState(
            node_running=False,
            total_online=0,
            online_peers=[],
            verified_online_peers=[],
            can_enter_step2=False,
            reason="请先启动本机联机节点，再与好友建立连接。",
        )
    if total_online < 2:
        return Step2GateState(
            node_running=True,
            total_online=total_online,
            online_peers=online_peers,
            verified_online_peers=verified_online,
            can_enter_step2=False,
            reason=f"当前仅 {total_online} 人在线（至少需要 2 人在线才能进入第二步并开启联机辅助）。",
        )
    if not verified_online:
        return Step2GateState(
            node_running=True,
            total_online=total_online,
            online_peers=online_peers,
            verified_online_peers=verified_online,
            can_enter_step2=False,
            reason=f"当前共 {total_online} 人在线，请选中在线好友并点击「测试选中连接」，测试通过后即可解锁第二步！",
        )
    names = "、".join(p.nickname for p in verified_online)
    return Step2GateState(
        node_running=True,
        total_online=total_online,
        online_peers=online_peers,
        verified_online_peers=verified_online,
        can_enter_step2=True,
        reason=f"✅ 第一步连接成功（当前共 {total_online} 人在线，已与 {names} 连通测试通过）！现在可以进入第二步开启文明6联机辅助。",
    )


@dataclass
class ConnectivityTestResult:
    peer_key: str
    passed: bool
    sent: int
    received: int
    loss_pct: float
    avg_rtt_ms: float | None
    min_rtt_ms: float | None
    max_rtt_ms: float | None
    jitter_ms: float | None
    large_pkt_ok: bool
    summary: str


class P2PNode:

    def __init__(
        self,
        nickname: str = "Player",
        role: str = "client",
        listen_port: int = DEFAULT_P2P_PORT,
        room_key: str = DEFAULT_ROOM_KEY,
        log_cb: Callable[[str, str], None] | None = None,
        local_civ6_status_fn: Callable[[], dict] | None = None,
    ) -> None:
        self.node_id = secrets.token_hex(6)
        self.nickname = nickname.strip() or "Player"
        self.role = role.strip().lower() if role.strip().lower() in ("host", "client") else "client"
        self.listen_port = int(listen_port)
        self.room_key = room_key.strip()
        self.room_tag = compute_room_tag(self.room_key)

        self._log_cb = log_cb
        self._local_civ6_status_fn = local_civ6_status_fn

        self._sock: socket.socket | None = None
        self._is_ipv6_sock: bool = True
        self._actual_port: int = 0
        self._running = False
        self._stop_event = threading.Event()
        self._recv_thread: threading.Thread | None = None
        self._maint_thread: threading.Thread | None = None

        self._lock = threading.RLock()
        self._peers: dict[str, PeerState] = {}
        self._used_fake_ips: set[str] = set()

        self._on_civ6_disc_req: Callable[[str, int, int, bytes], None] | None = None
        self._on_civ6_disc_resp: Callable[[str, int, int, bytes], None] | None = None
        self._on_civ6_session: Callable[[str, bytes], None] | None = None
        self._on_peer_offline: Callable[[str], None] | None = None

        self._test_lock = threading.Lock()
        self._test_results: dict[int, dict[int, tuple[float, int]]] = {}
        self._test_events: dict[int, threading.Event] = {}

        self._stun_lock = threading.Lock()
        self._stun_results: dict[bytes, tuple[str, int]] = {}
        self._stun_events: dict[bytes, threading.Event] = {}

        self._relay_enabled: bool = False
        self._relay_connected: bool = False
        self._relay_ip: str = ""
        self._relay_port: int = 0
        self._relay_ip_ver: int = 4
        self._relay_server_display: str = ""
        self._relay_room_id: str = ""
        self._relay_transport_name: str = "EasyTier 中继"
        self._relay_room_members: int = 0
        self._relay_last_seen: float = 0.0
        self._relay_last_reg_sent: float = 0.0

    @property
    def running(self) -> bool:
        return self._running

    @property
    def actual_port(self) -> int:
        return self._actual_port

    @property
    def is_ipv6_socket(self) -> bool:
        return self._is_ipv6_sock

    def _log(self, level: str, msg: str) -> None:
        if self._log_cb:
            try:
                self._log_cb(level, msg)
            except Exception:
                pass

    def set_civ6_callbacks(
        self,
        on_disc_req: Callable[[str, int, int, bytes], None] | None = None,
        on_disc_resp: Callable[[str, int, int, bytes], None] | None = None,
        on_session: Callable[[str, bytes], None] | None = None,
        on_peer_offline: Callable[[str], None] | None = None,
    ) -> None:
        with self._lock:
            self._on_civ6_disc_req = on_disc_req
            self._on_civ6_disc_resp = on_disc_resp
            self._on_civ6_session = on_session
            self._on_peer_offline = on_peer_offline

    def _notify_peer_offline(self, peer_keys: list[str]) -> None:
        if not peer_keys:
            return
        with self._lock:
            cb = self._on_peer_offline
        if cb is None:
            return
        for pkey in peer_keys:
            try:
                cb(pkey)
            except Exception:
                pass

    def update_identity(self, nickname: str | None = None, role: str | None = None) -> None:
        with self._lock:
            if nickname is not None and nickname.strip():
                self.nickname = nickname.strip()
            if role is not None and role.strip().lower() in ("host", "client"):
                self.role = role.strip().lower()

    def start(self) -> int:
        with self._lock:
            if self._running:
                return self._actual_port
            sock, is_v6, actual_port = create_dualstack_udp_socket(self.listen_port)
            self._sock = sock
            self._is_ipv6_sock = is_v6
            self._actual_port = actual_port
            self._stop_event.clear()
            self._running = True

        self._recv_thread = threading.Thread(target=self._recv_loop, name="p2p-recv", daemon=True)
        self._maint_thread = threading.Thread(target=self._maint_loop, name="p2p-maint", daemon=True)
        self._recv_thread.start()
        self._maint_thread.start()

        mode_str = "IPv6/IPv4 双栈 [::]" if self._is_ipv6_sock else "IPv4 0.0.0.0"
        self._log("ok", f"P2P 节点已启动: {mode_str}:{self._actual_port} | 角色={self.role} | 昵称={self.nickname}")
        return self._actual_port

    def stop(self) -> None:
        with self._lock:
            if not self._running:
                return
            peers_copy = list(self._peers.values())
            relay_active = self._relay_enabled
            relay_room = self._relay_room_id
            relay_ip = self._relay_ip
            relay_port = self._relay_port

        bye_pkt = pack_json_packet(MsgType.BYE, self.room_tag, {"node_id": self.node_id})
        for p in peers_copy:
            if p.status == "online":
                self._send_to_peer(p.peer_key, bye_pkt)

        if relay_active and relay_ip:
            unreg_pkt = pack_json_packet(
                MsgType.RELAY_UNREGISTER,
                self.room_tag,
                {"room_id": relay_room, "node_id": self.node_id},
            )
            self._send_raw(relay_ip, relay_port, unreg_pkt)

        with self._lock:
            self._running = False
            self._relay_enabled = False
            self._relay_connected = False
            self._relay_room_members = 0
            self._stop_event.set()
            sock = self._sock
            self._sock = None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass

        for t in (self._recv_thread, self._maint_thread):
            if t is not None and t.is_alive():
                t.join(timeout=1.0)

        with self._lock:
            for p in self._peers.values():
                p.status = "offline"
                p.rtt_ms = None

        self._log("info", "P2P 节点已停止。")

    def _allocate_fake_ip_locked(self) -> str:
        for idx in range(1, 101):
            cand = f"127.0.127.{idx}"
            if cand not in self._used_fake_ips:
                self._used_fake_ips.add(cand)
                return cand
        offline_relay = sorted(
            [p for p in self._peers.values() if p.transport == "relay" and p.status == "offline"],
            key=lambda p: p.last_seen,
        )
        if offline_relay:
            stale = offline_relay[0]
            self._peers.pop(stale.peer_key, None)
            reclaimed = stale.fake_ip
            self._used_fake_ips.add(reclaimed)
            return reclaimed
        raise RuntimeError("虚拟映射地址池 (127.0.127.1-100) 已满")

    def add_peer(self, host: str, port: int, nickname: str = "", role: str = "") -> PeerState:
        ip_str, ver = canonicalize_ip(host)
        port = int(port)
        peer_key = format_endpoint(ip_str, port)

        with self._lock:
            existing = self._peers.get(peer_key)
            if existing is not None:
                if nickname:
                    existing.nickname = nickname
                if role in ("host", "client"):
                    existing.role = role
                existing.added_at = time.monotonic()
                if existing.status == "offline":
                    existing.status = "connecting"
                peer = existing
            else:
                fake_ip = self._allocate_fake_ip_locked()
                peer = PeerState(
                    peer_key=peer_key,
                    host=ip_str,
                    port=port,
                    ip_version=ver,
                    fake_ip=fake_ip,
                    nickname=nickname or f"节点-{ip_str[:12]}",
                    role=role if role in ("host", "client") else "unknown",
                    status="connecting",
                )
                self._peers[peer_key] = peer
            snap = peer.copy_snapshot()

        if self._running:
            self._send_hello(peer_key)
            self._log("p2p", f"开始连接/打洞目标: {peer_key} (IPv{ver}, 虚拟IP={snap.fake_ip})")
        return snap

    def remove_peer(self, peer_key: str) -> None:
        with self._lock:
            peer = self._peers.get(peer_key)
        if peer is not None and self._running:
            bye_pkt = pack_json_packet(MsgType.BYE, self.room_tag, {"node_id": self.node_id})
            self._send_to_peer(peer_key, bye_pkt)
        with self._lock:
            removed = self._peers.pop(peer_key, None)
            if removed is not None:
                self._used_fake_ips.discard(removed.fake_ip)
        if removed is not None:
            self._notify_peer_offline([peer_key])
            if self._running:
                self._log("info", f"已移除对端节点: {peer_key}")

    def connect_relay(
        self,
        server_addr: str,
        room_id: str,
        default_port: int = DEFAULT_RELAY_PORT,
        transport_name: str = "EasyTier 中继",
    ) -> tuple[str, int]:
        if not self._running:
            raise RuntimeError("请先启动本机节点")
        room_clean = room_id.strip()[:64]
        if not room_clean:
            raise ValueError("中继房间号不能为空")

        host_input, port = parse_server_address(server_addr, default_port=default_port)
        resolved_ip = ""
        resolved_ver = 4
        families = (socket.AF_UNSPEC,) if self._is_ipv6_sock else (socket.AF_INET,)
        last_err: Exception | None = None
        for af in families:
            try:
                infos = socket.getaddrinfo(host_input, port, af, socket.SOCK_DGRAM)
                if infos:
                    chosen = infos[0]
                    for info in infos:
                        if info[0] == socket.AF_INET6 and self._is_ipv6_sock:
                            chosen = info
                            break
                    resolved_ip, resolved_ver = canonicalize_ip(chosen[4][0])
                    break
            except OSError as e:
                last_err = e

        if not resolved_ip:
            raise OSError(f"无法解析中继服务器地址 {host_input}:{port}: {last_err}")

        if self._relay_enabled:
            self.disconnect_relay()

        with self._lock:
            self._relay_enabled = True
            self._relay_connected = False
            self._relay_ip = resolved_ip
            self._relay_port = port
            self._relay_ip_ver = resolved_ver
            self._relay_server_display = format_endpoint(resolved_ip, port)
            self._relay_room_id = room_clean
            self._relay_transport_name = transport_name.strip() or "EasyTier 中继"
            self._relay_room_members = 0
            self._relay_last_seen = 0.0
            self._relay_last_reg_sent = 0.0

        self._send_relay_register()
        self._log("p2p", f"[中继] 正在连接中继服务器 {self._relay_server_display}，房间号={room_clean} ...")
        return resolved_ip, port

    def disconnect_relay(self) -> None:
        with self._lock:
            if not self._relay_enabled:
                return
            relay_ip = self._relay_ip
            relay_port = self._relay_port
            room_id = self._relay_room_id
            relay_peer_keys = [k for k, p in self._peers.items() if p.transport == "relay"]

        if self._running and relay_ip:
            bye_pkt = pack_json_packet(MsgType.BYE, self.room_tag, {"node_id": self.node_id})
            for k in relay_peer_keys:
                self._send_to_peer(k, bye_pkt)
            unreg = pack_json_packet(
                MsgType.RELAY_UNREGISTER,
                self.room_tag,
                {"room_id": room_id, "node_id": self.node_id},
            )
            self._send_raw(relay_ip, relay_port, unreg)

        with self._lock:
            self._relay_enabled = False
            self._relay_connected = False
            self._relay_room_members = 0
            for k in relay_peer_keys:
                p = self._peers.pop(k, None)
                if p is not None:
                    self._used_fake_ips.discard(p.fake_ip)

        self._notify_peer_offline(relay_peer_keys)
        self._log("info", "[中继] 已断开中继服务器。")

    def get_relay_status(self) -> RelayClientStatus:
        with self._lock:
            return RelayClientStatus(
                enabled=self._relay_enabled,
                connected=self._relay_connected,
                server_display=self._relay_server_display,
                room_id=self._relay_room_id,
                room_members=self._relay_room_members,
            )

    def _send_relay_register(self) -> None:
        with self._lock:
            if not self._relay_enabled:
                return
            relay_ip = self._relay_ip
            relay_port = self._relay_port
            room_id = self._relay_room_id
            self._relay_last_reg_sent = time.monotonic()

        pkt = pack_json_packet(
            MsgType.RELAY_REGISTER,
            self.room_tag,
            {
                "room_id": room_id,
                "node_id": self.node_id,
                "nickname": self.nickname,
                "role": self.role,
                "civ6": self._get_local_civ6_status(),
            },
        )
        self._send_raw(relay_ip, relay_port, pkt)

    def list_peers(self) -> list[PeerState]:
        with self._lock:
            return [p.copy_snapshot() for p in self._peers.values()]

    def get_peer(self, peer_key: str) -> PeerState | None:
        with self._lock:
            p = self._peers.get(peer_key)
            return p.copy_snapshot() if p else None

    def _get_local_civ6_status(self) -> dict:
        if self._local_civ6_status_fn is not None:
            try:
                return self._local_civ6_status_fn()
            except Exception:
                pass
        return {"running": False, "room_ready": False, "session_ready": False}

    def _send_raw(self, host: str, port: int, data: bytes, track_peer: str | None = None) -> bool:
        sock = self._sock
        if sock is None or not self._running:
            return False
        try:
            addr = to_sockaddr(host, port, self._is_ipv6_sock)
            sent = sock.sendto(data, addr)
            if track_peer:
                with self._lock:
                    p = self._peers.get(track_peer)
                    if p is not None:
                        p.tx_packets += 1
                        p.tx_bytes += sent
            return True
        except OSError as e:
            self._log("warn", f"发送 UDP 到 {format_endpoint(host, port)} 失败: {e}")
            return False

    def _send_to_peer(self, peer_key: str, inner_pkt: bytes) -> bool:
        with self._lock:
            peer = self._peers.get(peer_key)
            if peer is None:
                return False
            transport = peer.transport
            host = peer.host
            port = peer.port
            dst_node_id = peer.node_id
            relay_enabled = self._relay_enabled
            relay_ip = self._relay_ip
            relay_port = self._relay_port
            relay_room = self._relay_room_id

        if transport == "relay":
            if not relay_enabled or not dst_node_id or not relay_ip:
                return False
            wrapped = pack_relay_forward(self.room_tag, relay_room, self.node_id, dst_node_id, inner_pkt)
            return self._send_raw(relay_ip, relay_port, wrapped, track_peer=peer_key)
        return self._send_raw(host, port, inner_pkt, track_peer=peer_key)

    def _send_hello(self, peer_key: str) -> None:
        with self._lock:
            peer = self._peers.get(peer_key)
            if peer is None:
                return
            peer.last_punch_sent = time.monotonic()

        pkt = pack_json_packet(
            MsgType.HELLO,
            self.room_tag,
            {
                "node_id": self.node_id,
                "nickname": self.nickname,
                "role": self.role,
                "civ6": self._get_local_civ6_status(),
            },
        )
        self._send_to_peer(peer_key, pkt)

    def _send_hello_ack(self, peer_key: str, fake_ip: str) -> None:
        pkt = pack_json_packet(
            MsgType.HELLO_ACK,
            self.room_tag,
            {
                "node_id": self.node_id,
                "nickname": self.nickname,
                "role": self.role,
                "accepted": True,
                "assigned_fake_ip": fake_ip,
                "civ6": self._get_local_civ6_status(),
            },
        )
        self._send_to_peer(peer_key, pkt)

    def _send_ping(self, peer_key: str) -> None:
        with self._lock:
            peer = self._peers.get(peer_key)
            if peer is None:
                return
            peer._ping_seq = (peer._ping_seq + 1) & 0xFFFFFFFF
            seq = peer._ping_seq
            peer._recent_pings.append(seq)
            peer.last_ping_sent = time.monotonic()

        pkt = pack_json_packet(
            MsgType.PING,
            self.room_tag,
            {
                "node_id": self.node_id,
                "nickname": self.nickname,
                "role": self.role,
                "seq": seq,
                "ts_ms": _now_ms(),
                "civ6": self._get_local_civ6_status(),
            },
        )
        self._send_to_peer(peer_key, pkt)

    def send_civ6_disc_req(self, peer_key: str, ephem_port: int, req_id: int, raw_payload: bytes) -> bool:
        pkt = pack_civ6_disc(MsgType.CIV6_DISC_REQ, self.room_tag, ephem_port, req_id, raw_payload)
        return self._send_to_peer(peer_key, pkt)

    def send_civ6_disc_resp(self, peer_key: str, ephem_port: int, req_id: int, raw_payload: bytes) -> bool:
        pkt = pack_civ6_disc(MsgType.CIV6_DISC_RESP, self.room_tag, ephem_port, req_id, raw_payload)
        return self._send_to_peer(peer_key, pkt)

    def send_civ6_session(self, peer_key: str, raw_payload: bytes) -> bool:
        pkt = pack_packet(MsgType.CIV6_SESSION, self.room_tag, raw_payload)
        return self._send_to_peer(peer_key, pkt)

    def run_connectivity_test(
        self, peer_key: str, count: int = 5, timeout_s: float = 1.5
    ) -> ConnectivityTestResult:
        with self._lock:
            peer = self._peers.get(peer_key)
            if peer is None:
                raise ValueError(f"未找到节点: {peer_key}")

        if not self._running:
            raise RuntimeError("P2P 节点未启动")

        test_id = secrets.randbits(32)
        ev = threading.Event()
        with self._test_lock:
            self._test_results[test_id] = {}
            self._test_events[test_id] = ev

        sizes = [64, 64, 64, 1150, 1150] if count == 5 else ([64] * max(1, count - 2) + [1150, 1150])[:count]
        sent = len(sizes)
        try:
            for seq, sz in enumerate(sizes, start=1):
                pkt = pack_test_req(self.room_tag, test_id, seq, _now_ms(), total_payload_size=sz)
                self._send_to_peer(peer_key, pkt)
                time.sleep(0.10)

            deadline = time.monotonic() + timeout_s
            while time.monotonic() < deadline:
                with self._test_lock:
                    if len(self._test_results.get(test_id, {})) >= sent:
                        break
                ev.wait(timeout=0.05)
                ev.clear()

            with self._test_lock:
                got = dict(self._test_results.get(test_id, {}))
        finally:
            with self._test_lock:
                self._test_results.pop(test_id, None)
                self._test_events.pop(test_id, None)

        received = len(got)
        loss_pct = ((sent - received) / sent) * 100.0 if sent > 0 else 100.0
        rtts = [val[0] for val in got.values()]
        large_ok = any(val[1] >= 1100 for val in got.values())

        if rtts:
            avg_rtt = sum(rtts) / len(rtts)
            min_rtt = min(rtts)
            max_rtt = max(rtts)
            if len(rtts) >= 2:
                diffs = [abs(rtts[i] - rtts[i - 1]) for i in range(1, len(rtts))]
                jitter = sum(diffs) / len(diffs)
            else:
                jitter = 0.0
        else:
            avg_rtt = min_rtt = max_rtt = jitter = None

        min_needed = max(1, (sent + 1) // 2)
        passed = received >= min_needed and large_ok

        if passed:
            summary = f"通过 | {avg_rtt:.1f}ms | 丢包{loss_pct:.0f}% | 大包OK"
        elif received > 0 and not large_ok:
            summary = f"部分通 | 大包(1200B)丢包"
        else:
            summary = f"失败 (0/{sent})"

        with self._lock:
            p = self._peers.get(peer_key)
            if p is not None:
                p.verified = passed
                p.last_test_summary = summary
                if avg_rtt is not None:
                    p.rtt_ms = avg_rtt

        level = "ok" if passed else "warn"
        self._log(level, f"连接测试 [{peer_key}]: {summary} (收到 {received}/{sent})")
        return ConnectivityTestResult(
            peer_key=peer_key,
            passed=passed,
            sent=sent,
            received=received,
            loss_pct=loss_pct,
            avg_rtt_ms=avg_rtt,
            min_rtt_ms=min_rtt,
            max_rtt_ms=max_rtt,
            jitter_ms=jitter,
            large_pkt_ok=large_ok,
            summary=summary,
        )

    def probe_stun(
        self,
        servers: list[tuple[str, int]] = DEFAULT_STUN_SERVERS,
        timeout_s: float = 2.0,
    ) -> dict[str, tuple[str, int]]:
        if not self._running or self._sock is None:
            raise RuntimeError("请先启动 P2P 节点后再进行 STUN 公网检测")

        results: dict[str, tuple[str, int]] = {}
        pending: dict[str, list[bytes]] = {"ipv6": [], "ipv4": []}

        for family_name, af in (("ipv6", socket.AF_INET6), ("ipv4", socket.AF_INET)):
            if family_name == "ipv6" and not self._is_ipv6_sock:
                continue
            for host, port in servers:
                try:
                    infos = socket.getaddrinfo(host, port, af, socket.SOCK_DGRAM)
                except OSError:
                    continue
                if not infos:
                    continue
                target_ip = infos[0][4][0]
                pkt, tx_id = build_stun_binding_request()
                ev = threading.Event()
                with self._stun_lock:
                    self._stun_events[tx_id] = ev
                pending[family_name].append(tx_id)
                self._send_raw(target_ip, port, pkt)

        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            with self._stun_lock:
                for fam in ("ipv6", "ipv4"):
                    if fam not in results:
                        for tx_id in pending[fam]:
                            if tx_id in self._stun_results:
                                results[fam] = self._stun_results[tx_id]
                                break
            if ("ipv6" in results or not pending["ipv6"]) and ("ipv4" in results or not pending["ipv4"]):
                break
            time.sleep(0.05)

        with self._stun_lock:
            for fam_list in pending.values():
                for tx_id in fam_list:
                    self._stun_events.pop(tx_id, None)
                    self._stun_results.pop(tx_id, None)

        return results


    def _recv_loop(self) -> None:
        while not self._stop_event.is_set():
            sock = self._sock
            if sock is None:
                break
            try:
                readable, _, _ = select.select([sock], [], [], 0.2)
            except (OSError, ValueError):
                break
            if not readable:
                continue

            try:
                raw, addr = sock.recvfrom(65535)
            except ConnectionResetError:
                continue
            except OSError:
                if self._stop_event.is_set():
                    break
                continue

            if is_stun_packet(raw):
                stun_parsed = parse_stun_binding_response(raw)
                if stun_parsed is not None:
                    tx_id, mapped_ip, mapped_port = stun_parsed
                    with self._stun_lock:
                        if tx_id in self._stun_events:
                            self._stun_results[tx_id] = (mapped_ip, mapped_port)
                            self._stun_events[tx_id].set()
                continue

            parsed = unpack_packet(raw)
            if parsed is None:
                continue
            msg_type, room_tag, payload = parsed
            if room_tag != self.room_tag:
                continue

            try:
                src_ip, ver = canonicalize_ip(addr[0])
                src_port = int(addr[1])
            except Exception:
                continue

            if msg_type == MsgType.RELAY_PEERS:
                self._handle_relay_peers(payload, src_ip, src_port)
                continue

            if msg_type == MsgType.RELAY_FORWARD:
                self._handle_relay_forward(payload, src_ip, src_port)
                continue

            peer_key = format_endpoint(src_ip, src_port)
            self._handle_packet(msg_type, payload, peer_key, src_ip, src_port, ver, len(raw), transport="direct")

    def _handle_relay_peers(self, payload: bytes, src_ip: str, src_port: int) -> None:
        with self._lock:
            if not self._relay_enabled or src_ip != self._relay_ip or src_port != self._relay_port:
                return
            expected_room = self._relay_room_id

        data = unpack_json_payload(payload)
        if data is None or data.get("room_id") != expected_room:
            return

        peers_list = data.get("peers")
        if not isinstance(peers_list, list):
            return

        now = time.monotonic()
        newly_seen_keys: list[str] = []
        active_relay_ids: set[str] = set()
        offline_notify_keys: list[str] = []
        just_connected = False

        for item in peers_list:
            if isinstance(item, dict):
                nid = str(item.get("node_id", "")).strip()
                if nid and nid != self.node_id:
                    active_relay_ids.add(nid)

        with self._lock:
            if not self._relay_connected:
                just_connected = True
            self._relay_connected = True
            self._relay_last_seen = now
            self._relay_room_members = len(peers_list)

            for item in peers_list:
                if not isinstance(item, dict):
                    continue
                nid = str(item.get("node_id", "")).strip()
                if not nid or nid == self.node_id:
                    continue
                pkey = f"relay://{nid}"
                nick = str(item.get("nickname") or f"节点-{nid[:6]}")
                role = str(item.get("role") or "unknown")
                p = self._peers.get(pkey)
                if p is None:
                    for old_key, old_p in list(self._peers.items()):
                        if (
                            old_p.transport == "relay"
                            and old_p.status == "offline"
                            and old_p.node_id not in active_relay_ids
                            and old_p.nickname == nick
                            and old_p.role == role
                        ):
                            self._peers.pop(old_key, None)
                            self._used_fake_ips.discard(old_p.fake_ip)
                            offline_notify_keys.append(old_key)
                    fake_ip = self._allocate_fake_ip_locked()
                    p = PeerState(
                        peer_key=pkey,
                        host=self._relay_ip,
                        port=self._relay_port,
                        ip_version=self._relay_ip_ver,
                        fake_ip=fake_ip,
                        transport="relay",
                        transport_name=self._relay_transport_name,
                        nickname=nick,
                        role=role,
                        node_id=nid,
                        status="connecting",
                    )
                    self._peers[pkey] = p
                    newly_seen_keys.append(pkey)
                else:
                    if item.get("nickname"):
                        p.nickname = str(item["nickname"])
                    if item.get("role") in ("host", "client"):
                        p.role = str(item["role"])
                    if p.status == "offline":
                        p.status = "connecting"
                        p.added_at = now
                        newly_seen_keys.append(pkey)

                civ6 = item.get("civ6")
                if isinstance(civ6, dict):
                    p.remote_civ6_running = bool(civ6.get("running", False))
                    p.remote_civ6_room_ready = bool(civ6.get("room_ready", False))
                    p.remote_civ6_session_ready = bool(civ6.get("session_ready", False))

            left_peers: list[str] = []
            for pkey, p in self._peers.items():
                if p.transport == "relay" and p.node_id not in active_relay_ids and p.status != "offline":
                    p.status = "offline"
                    p.rtt_ms = None
                    p.remote_civ6_running = False
                    p.remote_civ6_room_ready = False
                    p.remote_civ6_session_ready = False
                    left_peers.append(f"{p.nickname} ({pkey})")
                    offline_notify_keys.append(pkey)

        self._notify_peer_offline(offline_notify_keys)
        if just_connected:
            self._log("ok", f"[中继] 已连入中继服务器 {self._relay_server_display} 房间 [{expected_room}]（当前房间 {len(peers_list)} 人）")
        for lp in left_peers:
            self._log("warn", f"[中继] 成员已离开中继房间: {lp}")
        for pkey in newly_seen_keys:
            self._send_hello(pkey)

    def _handle_relay_forward(self, payload: bytes, src_ip: str, src_port: int) -> None:
        with self._lock:
            if not self._relay_enabled or src_ip != self._relay_ip or src_port != self._relay_port:
                return
            expected_room = self._relay_room_id
            relay_ver = self._relay_ip_ver

        unwrapped = unpack_relay_forward(payload)
        if unwrapped is None:
            return
        room_id, src_node_id, dst_node_id, inner_raw = unwrapped
        if room_id != expected_room or dst_node_id != self.node_id or not src_node_id:
            return

        inner_parsed = unpack_packet(inner_raw)
        if inner_parsed is None:
            return
        inner_type, inner_room_tag, inner_payload = inner_parsed
        if inner_room_tag != self.room_tag:
            return

        with self._lock:
            self._relay_last_seen = time.monotonic()
            self._relay_connected = True

        peer_key = f"relay://{src_node_id}"
        self._handle_packet(
            inner_type,
            inner_payload,
            peer_key,
            src_ip,
            src_port,
            relay_ver,
            len(inner_raw),
            transport="relay",
            remote_node_id=src_node_id,
        )

    def _ensure_peer_from_inbound(
        self,
        peer_key: str,
        src_ip: str,
        src_port: int,
        ver: int,
        data: dict | None = None,
        transport: str = "direct",
        remote_node_id: str = "",
    ) -> PeerState:
        now = time.monotonic()
        with self._lock:
            peer = self._peers.get(peer_key)
            if peer is None and transport == "direct":
                node_id = (data or {}).get("node_id", "") if data else ""
                if node_id:
                    for old_key, old_peer in list(self._peers.items()):
                        if old_peer.transport == "direct" and old_peer.node_id == node_id and old_key != peer_key:
                            self._peers.pop(old_key)
                            old_peer.peer_key = peer_key
                            old_peer.host = src_ip
                            old_peer.port = src_port
                            old_peer.ip_version = ver
                            self._peers[peer_key] = old_peer
                            peer = old_peer
                            self._log("p2p", f"节点 {old_peer.nickname} 地址更新为 {peer_key}")
                            break

            if peer is None:
                fake_ip = self._allocate_fake_ip_locked()
                nid = remote_node_id or ((data or {}).get("node_id", "") if data else "")
                peer = PeerState(
                    peer_key=peer_key,
                    host=src_ip,
                    port=src_port,
                    ip_version=ver,
                    fake_ip=fake_ip,
                    transport=transport,
                    transport_name=self._relay_transport_name if transport == "relay" else "",
                    node_id=str(nid),
                    nickname=(data or {}).get("nickname") or f"节点-{nid[:6] or src_ip[:12]}",
                    role=(data or {}).get("role") or "unknown",
                    status="online",
                    last_seen=now,
                    connected_since=now,
                )
                self._peers[peer_key] = peer
                self._log("ok", f"新节点连入: {peer.nickname} ({peer.transport_label()}, 虚拟IP={fake_ip})")

            was_online = peer.status == "online"
            peer.last_seen = now
            peer.status = "online"
            if remote_node_id and not peer.node_id:
                peer.node_id = remote_node_id
            if not was_online:
                peer.connected_since = now
                self._log("ok", f"节点已上线: {peer.nickname} ({peer.transport_label()})")

            if data:
                if data.get("node_id"):
                    peer.node_id = str(data["node_id"])
                if data.get("nickname"):
                    peer.nickname = str(data["nickname"])
                if data.get("role") in ("host", "client"):
                    peer.role = str(data["role"])
                civ6 = data.get("civ6")
                if isinstance(civ6, dict):
                    peer.remote_civ6_running = bool(civ6.get("running", False))
                    peer.remote_civ6_room_ready = bool(civ6.get("room_ready", False))
                    peer.remote_civ6_session_ready = bool(civ6.get("session_ready", False))
            return peer

    def _handle_packet(
        self,
        msg_type: MsgType,
        payload: bytes,
        peer_key: str,
        src_ip: str,
        src_port: int,
        ver: int,
        raw_len: int,
        transport: str = "direct",
        remote_node_id: str = "",
    ) -> None:
        if msg_type == MsgType.CIV6_SESSION:
            with self._lock:
                peer = self._peers.get(peer_key)
                cb = self._on_civ6_session
                if peer is not None:
                    peer.last_seen = time.monotonic()
                    peer.rx_packets += 1
                    peer.rx_bytes += raw_len
                    if peer.status != "online":
                        peer.status = "online"
            if peer is not None and cb is not None:
                cb(peer_key, payload)
            return

        if msg_type == MsgType.CIV6_DISC_REQ:
            parsed = unpack_civ6_disc(payload)
            if parsed is None:
                return
            ephem_port, req_id, raw_civ6 = parsed
            with self._lock:
                peer = self._peers.get(peer_key)
                cb = self._on_civ6_disc_req
                if peer is not None:
                    peer.last_seen = time.monotonic()
                    peer.rx_packets += 1
                    peer.rx_bytes += raw_len
            if peer is not None and cb is not None:
                cb(peer_key, ephem_port, req_id, raw_civ6)
            return

        if msg_type == MsgType.CIV6_DISC_RESP:
            parsed = unpack_civ6_disc(payload)
            if parsed is None:
                return
            ephem_port, req_id, raw_civ6 = parsed
            with self._lock:
                peer = self._peers.get(peer_key)
                cb = self._on_civ6_disc_resp
                if peer is not None:
                    peer.last_seen = time.monotonic()
                    peer.rx_packets += 1
                    peer.rx_bytes += raw_len
            if peer is not None and cb is not None:
                cb(peer_key, ephem_port, req_id, raw_civ6)
            return

        if msg_type == MsgType.TEST_REQ:
            parsed = unpack_test_req(payload)
            if parsed is None:
                return
            test_id, seq, ts_ms, orig_len = parsed
            peer = self._ensure_peer_from_inbound(
                peer_key, src_ip, src_port, ver, transport=transport, remote_node_id=remote_node_id
            )
            with self._lock:
                peer.rx_packets += 1
                peer.rx_bytes += raw_len
            resp = pack_test_resp(self.room_tag, test_id, seq, ts_ms, orig_len)
            self._send_to_peer(peer_key, resp)
            return

        if msg_type == MsgType.TEST_RESP:
            parsed = unpack_test_resp(payload)
            if parsed is None:
                return
            test_id, seq, sent_ts_ms, orig_len = parsed
            rtt = max(0.0, float(_now_ms() - sent_ts_ms))
            with self._lock:
                p = self._peers.get(peer_key)
                if p is not None:
                    p.last_seen = time.monotonic()
                    p.rx_packets += 1
                    p.rx_bytes += raw_len
            with self._test_lock:
                if test_id in self._test_results:
                    self._test_results[test_id][seq] = (rtt, orig_len)
                    ev = self._test_events.get(test_id)
                    if ev is not None:
                        ev.set()
            return

        data = unpack_json_payload(payload)
        if data is None:
            return

        if msg_type == MsgType.HELLO:
            peer = self._ensure_peer_from_inbound(
                peer_key, src_ip, src_port, ver, data, transport=transport, remote_node_id=remote_node_id
            )
            with self._lock:
                peer.rx_packets += 1
                peer.rx_bytes += raw_len
                fake_ip = peer.fake_ip
            self._send_hello_ack(peer_key, fake_ip)
            return

        if msg_type == MsgType.HELLO_ACK:
            peer = self._ensure_peer_from_inbound(
                peer_key, src_ip, src_port, ver, data, transport=transport, remote_node_id=remote_node_id
            )
            with self._lock:
                peer.rx_packets += 1
                peer.rx_bytes += raw_len
            self._send_ping(peer_key)
            return

        if msg_type == MsgType.PING:
            peer = self._ensure_peer_from_inbound(
                peer_key, src_ip, src_port, ver, data, transport=transport, remote_node_id=remote_node_id
            )
            with self._lock:
                peer.rx_packets += 1
                peer.rx_bytes += raw_len
            pong = pack_json_packet(
                MsgType.PONG,
                self.room_tag,
                {
                    "node_id": self.node_id,
                    "nickname": self.nickname,
                    "role": self.role,
                    "seq": data.get("seq", 0),
                    "ts_ms": data.get("ts_ms", 0),
                    "civ6": self._get_local_civ6_status(),
                },
            )
            self._send_to_peer(peer_key, pong)
            return

        if msg_type == MsgType.PONG:
            peer = self._ensure_peer_from_inbound(
                peer_key, src_ip, src_port, ver, data, transport=transport, remote_node_id=remote_node_id
            )
            seq = int(data.get("seq", 0))
            sent_ts_ms = int(data.get("ts_ms", 0))
            rtt = max(0.0, float(_now_ms() - sent_ts_ms)) if sent_ts_ms > 0 else 0.0
            with self._lock:
                peer.rx_packets += 1
                peer.rx_bytes += raw_len
                if peer.rtt_ms is None:
                    peer.rtt_ms = rtt
                    peer.jitter_ms = 0.0
                else:
                    diff = abs(rtt - peer.rtt_ms)
                    peer.jitter_ms = diff if peer.jitter_ms is None else (peer.jitter_ms * 0.7 + diff * 0.3)
                    peer.rtt_ms = peer.rtt_ms * 0.6 + rtt * 0.4
                peer.min_rtt_ms = rtt if peer.min_rtt_ms is None else min(peer.min_rtt_ms, rtt)
                peer._acked_seqs.add(seq)
                recent_set = set(peer._recent_pings)
                peer._acked_seqs &= recent_set
                if len(peer._recent_pings) >= 2:
                    completed = list(peer._recent_pings)[:-1]
                    acked = sum(1 for s in completed if s in peer._acked_seqs)
                    peer.loss_pct = ((len(completed) - acked) / len(completed)) * 100.0
            return

        if msg_type == MsgType.BYE:
            went_down = False
            with self._lock:
                peer = self._peers.get(peer_key)
                if peer is not None and peer.status != "offline":
                    peer.status = "offline"
                    peer.rtt_ms = None
                    peer.remote_civ6_running = False
                    peer.remote_civ6_room_ready = False
                    peer.remote_civ6_session_ready = False
                    went_down = True
                    self._log("warn", f"对方主动断开连接: {peer.nickname} ({peer_key})")
            if went_down:
                self._notify_peer_offline([peer_key])
            return

    def _maint_loop(self) -> None:
        while not self._stop_event.wait(0.25):
            now = time.monotonic()
            to_punch: list[str] = []
            to_ping: list[str] = []
            went_offline: list[tuple[str, str]] = []
            need_relay_reg = False
            relay_timed_out = False

            with self._lock:
                if self._relay_enabled:
                    if self._relay_connected and self._relay_last_seen > 0 and (now - self._relay_last_seen) > RELAY_TIMEOUT_S:
                        self._relay_connected = False
                        self._relay_room_members = 0
                        relay_timed_out = True
                    reg_interval = RELAY_REGISTER_INTERVAL_S if self._relay_connected else RELAY_RETRY_INTERVAL_S
                    if (now - self._relay_last_reg_sent) >= reg_interval:
                        need_relay_reg = True

                for key, p in self._peers.items():
                    if p.status == "online":
                        if p.last_seen > 0 and (now - p.last_seen) > OFFLINE_TIMEOUT_S:
                            p.status = "offline"
                            p.rtt_ms = None
                            p.remote_civ6_running = False
                            p.remote_civ6_room_ready = False
                            p.remote_civ6_session_ready = False
                            went_offline.append((key, p.nickname))
                        elif (now - p.last_ping_sent) >= HEARTBEAT_INTERVAL_S:
                            to_ping.append(key)
                    else:
                        if p.transport == "relay" and (not self._relay_connected or p.status == "offline"):
                            continue
                        elapsed = now - p.added_at
                        interval = PUNCH_FAST_INTERVAL_S if elapsed < PUNCH_FAST_DURATION_S else PUNCH_SLOW_INTERVAL_S
                        if (now - p.last_punch_sent) >= interval:
                            to_punch.append(key)

            if relay_timed_out:
                self._log("warn", f"[中继] 与中继服务器 {self._relay_server_display} 心跳超时，正在自动重连...")
            if need_relay_reg:
                self._send_relay_register()
            if went_offline:
                self._notify_peer_offline([key for key, _ in went_offline])
            for key, nick in went_offline:
                self._log("warn", f"节点心跳超时，已离线: {nick} ({key})")
            for key in to_ping:
                self._send_ping(key)
            for key in to_punch:
                self._send_hello(key)
