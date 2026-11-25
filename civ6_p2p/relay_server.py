from __future__ import annotations

import hmac
import select
import socket
import threading
import time
from dataclasses import dataclass
from typing import Callable

from .network_utils import canonicalize_ip, create_dualstack_udp_socket, format_endpoint, to_sockaddr
from .protocol import (
    DEFAULT_RELAY_PORT,
    MsgType,
    compute_relay_auth_token,
    pack_json_packet,
    pack_relay_forward,
    unpack_json_payload,
    unpack_packet,
    unpack_relay_forward,
)


@dataclass
class RelayClientEntry:
    node_id: str
    nickname: str
    role: str
    host: str
    port: int
    room_id: str
    room_tag: bytes
    civ6: dict
    last_seen: float

    def public_info(self) -> dict:
        return {
            "node_id": self.node_id,
            "nickname": self.nickname,
            "role": self.role,
            "civ6": self.civ6,
        }


@dataclass
class RelayServerStats:
    running: bool = False
    listen_port: int = 0
    is_ipv6: bool = True
    room_count: int = 0
    client_count: int = 0
    fwd_packets: int = 0
    fwd_bytes: int = 0


class RelayServer:

    def __init__(
        self,
        listen_port: int = DEFAULT_RELAY_PORT,
        idle_timeout_s: float = 15.0,
        auth_password: str = "",
        log_cb: Callable[[str, str], None] | None = None,
    ) -> None:
        self.listen_port = int(listen_port)
        self.idle_timeout_s = float(idle_timeout_s)
        self._auth_token = compute_relay_auth_token(auth_password)
        self._log_cb = log_cb

        self._sock: socket.socket | None = None
        self._is_ipv6 = True
        self._actual_port = 0
        self._running = False
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()

        self._rooms: dict[tuple[str, bytes], dict[str, RelayClientEntry]] = {}
        self._fwd_packets = 0
        self._fwd_bytes = 0

    @property
    def running(self) -> bool:
        return self._running

    @property
    def actual_port(self) -> int:
        return self._actual_port

    def _log(self, level: str, msg: str) -> None:
        if self._log_cb:
            try:
                self._log_cb(level, msg)
            except Exception:
                pass

    def get_stats(self) -> RelayServerStats:
        with self._lock:
            room_cnt = len(self._rooms)
            client_cnt = sum(len(members) for members in self._rooms.values())
            return RelayServerStats(
                running=self._running,
                listen_port=self._actual_port,
                is_ipv6=self._is_ipv6,
                room_count=room_cnt,
                client_count=client_cnt,
                fwd_packets=self._fwd_packets,
                fwd_bytes=self._fwd_bytes,
            )

    def start(self) -> int:
        with self._lock:
            if self._running:
                return self._actual_port
            sock, is_v6, actual_port = create_dualstack_udp_socket(self.listen_port)
            self._sock = sock
            self._is_ipv6 = is_v6
            self._actual_port = actual_port
            self._stop_event.clear()
            self._running = True

        self._thread = threading.Thread(target=self._serve_loop, name="civ6-relay-server", daemon=True)
        self._thread.start()
        mode = "IPv6/IPv4 双栈 [::]" if self._is_ipv6 else "IPv4 0.0.0.0"
        auth_tag = " (已启用连接密码)" if self._auth_token else ""
        self._log("ok", f"[中继服务端] 已启动监听 {mode}:{self._actual_port}{auth_tag}")
        return self._actual_port

    def stop(self) -> None:
        with self._lock:
            if not self._running:
                return
            self._running = False
            self._stop_event.set()
            sock = self._sock
            self._sock = None
            self._rooms.clear()

        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._log("info", "[中继服务端] 已停止。")

    def _send_to(self, host: str, port: int, data: bytes) -> bool:
        sock = self._sock
        if sock is None or not self._running:
            return False
        try:
            sock.sendto(data, to_sockaddr(host, port, self._is_ipv6))
            return True
        except OSError:
            return False

    def _broadcast_room_peers(self, room_key_tuple: tuple[str, bytes]) -> None:
        room_id, room_tag = room_key_tuple
        with self._lock:
            members = self._rooms.get(room_key_tuple)
            if not members:
                return
            peer_infos = [m.public_info() for m in members.values()]
            targets = [(m.host, m.port) for m in members.values()]

        pkt = pack_json_packet(
            MsgType.RELAY_PEERS,
            room_tag,
            {
                "room_id": room_id,
                "server_time_ms": int(time.monotonic() * 1000),
                "peers": peer_infos,
            },
        )
        for h, p in targets:
            self._send_to(h, p, pkt)

    def _evict_expired(self) -> None:
        now = time.monotonic()
        changed_rooms: list[tuple[str, bytes]] = []
        removed_logs: list[str] = []

        with self._lock:
            for rkey in list(self._rooms.keys()):
                members = self._rooms[rkey]
                expired = [nid for nid, entry in members.items() if (now - entry.last_seen) > self.idle_timeout_s]
                if expired:
                    for nid in expired:
                        ent = members.pop(nid)
                        removed_logs.append(f"{ent.nickname}({nid[:6]}) 离开房间 [{rkey[0]}] (超时)")
                    if not members:
                        self._rooms.pop(rkey, None)
                    else:
                        changed_rooms.append(rkey)

        for msg in removed_logs:
            self._log("info", f"[中继服务端] {msg}")
        for rkey in changed_rooms:
            self._broadcast_room_peers(rkey)

    def _serve_loop(self) -> None:
        last_cleanup = time.monotonic()
        while not self._stop_event.is_set():
            sock = self._sock
            if sock is None:
                break

            now = time.monotonic()
            if (now - last_cleanup) >= 2.0:
                last_cleanup = now
                self._evict_expired()

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

            parsed = unpack_packet(raw)
            if parsed is None:
                continue
            msg_type, room_tag, payload = parsed

            try:
                src_ip, _ = canonicalize_ip(addr[0])
                src_port = int(addr[1])
            except Exception:
                continue

            if msg_type == MsgType.RELAY_FORWARD:
                self._handle_forward(room_tag, payload, src_ip, src_port)
            elif msg_type == MsgType.RELAY_REGISTER:
                self._handle_register(room_tag, payload, src_ip, src_port)
            elif msg_type == MsgType.RELAY_UNREGISTER:
                self._handle_unregister(room_tag, payload)

    def _handle_register(self, room_tag: bytes, payload: bytes, src_ip: str, src_port: int) -> None:
        data = unpack_json_payload(payload)
        if data is None:
            return
        room_id = str(data.get("room_id", "")).strip()[:64]
        node_id = str(data.get("node_id", "")).strip()[:32]
        if not room_id or not node_id:
            return
        if self._auth_token:
            got_auth = str(data.get("auth", "")).strip()
            if not hmac.compare_digest(got_auth, self._auth_token):
                err_pkt = pack_json_packet(
                    MsgType.RELAY_PEERS,
                    room_tag,
                    {"room_id": room_id, "auth_error": True, "peers": []},
                )
                self._send_to(src_ip, src_port, err_pkt)
                return
        nickname = str(data.get("nickname", "")).strip()[:32] or f"Player-{node_id[:4]}"
        role = str(data.get("role", "client")).strip().lower()
        if role not in ("host", "client"):
            role = "client"
        civ6 = data.get("civ6") if isinstance(data.get("civ6"), dict) else {}

        rkey = (room_id, room_tag)
        now = time.monotonic()
        is_new = False
        changed_meta = False

        with self._lock:
            members = self._rooms.setdefault(rkey, {})
            existing = members.get(node_id)
            if existing is None:
                is_new = True
                members[node_id] = RelayClientEntry(
                    node_id=node_id,
                    nickname=nickname,
                    role=role,
                    host=src_ip,
                    port=src_port,
                    room_id=room_id,
                    room_tag=room_tag,
                    civ6=civ6,
                    last_seen=now,
                )
            else:
                if (
                    existing.nickname != nickname
                    or existing.role != role
                    or existing.civ6 != civ6
                    or existing.host != src_ip
                    or existing.port != src_port
                ):
                    changed_meta = True
                existing.nickname = nickname
                existing.role = role
                existing.host = src_ip
                existing.port = src_port
                existing.civ6 = civ6
                existing.last_seen = now

            peer_infos = [m.public_info() for m in members.values()]

        if is_new:
            self._log(
                "ok",
                f"[中继服务端] 成员加入房间 [{room_id}]: {nickname} ({role}, {format_endpoint(src_ip, src_port)})",
            )
            self._broadcast_room_peers(rkey)
        elif changed_meta:
            self._broadcast_room_peers(rkey)
        else:
            pkt = pack_json_packet(
                MsgType.RELAY_PEERS,
                room_tag,
                {"room_id": room_id, "server_time_ms": int(time.monotonic() * 1000), "peers": peer_infos},
            )
            self._send_to(src_ip, src_port, pkt)

    def _handle_unregister(self, room_tag: bytes, payload: bytes) -> None:
        data = unpack_json_payload(payload)
        if data is None:
            return
        if self._auth_token:
            got_auth = str(data.get("auth", "")).strip()
            if not hmac.compare_digest(got_auth, self._auth_token):
                return
        room_id = str(data.get("room_id", "")).strip()[:64]
        node_id = str(data.get("node_id", "")).strip()[:32]
        if not room_id or not node_id:
            return

        rkey = (room_id, room_tag)
        removed: RelayClientEntry | None = None
        should_broadcast = False
        with self._lock:
            members = self._rooms.get(rkey)
            if members and node_id in members:
                removed = members.pop(node_id)
                if not members:
                    self._rooms.pop(rkey, None)
                else:
                    should_broadcast = True

        if removed is not None:
            self._log("info", f"[中继服务端] 成员主动离开房间 [{room_id}]: {removed.nickname}")
        if should_broadcast:
            self._broadcast_room_peers(rkey)

    def _handle_forward(self, room_tag: bytes, payload: bytes, src_ip: str, src_port: int) -> None:
        parsed = unpack_relay_forward(payload)
        if parsed is None:
            return
        room_id, src_node_id, dst_node_id, inner_pkt = parsed
        rkey = (room_id, room_tag)

        with self._lock:
            members = self._rooms.get(rkey)
            if not members:
                return
            sender = members.get(src_node_id)
            target = members.get(dst_node_id)
            if sender is None or target is None:
                return
            sender.host = src_ip
            sender.port = src_port
            sender.last_seen = time.monotonic()
            dst_host, dst_port = target.host, target.port

        fwd_pkt = pack_relay_forward(room_tag, room_id, src_node_id, dst_node_id, inner_pkt)
        if self._send_to(dst_host, dst_port, fwd_pkt):
            with self._lock:
                self._fwd_packets += 1
                self._fwd_bytes += len(fwd_pkt)
