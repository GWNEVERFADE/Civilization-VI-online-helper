from __future__ import annotations

import os
import select
import socket
import threading
import time
from dataclasses import dataclass
from typing import Callable

from .network_utils import disable_udp_connreset, tune_udp_buffers
from .p2p_node import P2PNode
from .win_civ6 import (
    DISCOVERY_PAYLOAD,
    DISCOVERY_PORT,
    SESSION_PORT,
    find_civ6_processes,
    format_civ6_processes,
    inspect_civ6_state,
    read_civ6_candidates,
)

IDLE_MS = 500
BURST_MS = 3000
BURST_INTERVAL_MS = 20
PID_REFRESH_MS = 2000


def _now_ms() -> int:
    return int(time.monotonic() * 1000)


def _hex_bytes(data: bytes) -> str:
    return " ".join(f"{b:02x}" for b in data)


@dataclass
class BridgeStats:
    active: bool = False
    mode: str = ""
    fake_host_ip: str = "127.0.127.1"
    disc_reqs: int = 0
    disc_resps: int = 0
    session_tx_pkts: int = 0
    session_rx_pkts: int = 0
    session_tx_bytes: int = 0
    session_rx_bytes: int = 0
    last_activity_desc: str = "等待文明6流量..."


class HostCiv6Bridge:

    def __init__(
        self,
        p2p_node: P2PNode,
        log_cb: Callable[[str, str], None] | None = None,
        target_host_ip: str = "127.0.0.1",
        target_disc_port: int = DISCOVERY_PORT,
        target_session_port: int = SESSION_PORT,
        local_session_bind_port: int = SESSION_PORT,
    ) -> None:
        self.p2p = p2p_node
        self._log_cb = log_cb
        self.target_host_ip = target_host_ip
        self.target_disc_port = int(target_disc_port)
        self.target_session_port = int(target_session_port)
        self.local_session_bind_port = int(local_session_bind_port)

        self._lock = threading.RLock()
        self._running = False
        self._stop_event = threading.Event()
        self._peer_sess_socks: dict[str, tuple[socket.socket, str]] = {}
        self._sock_to_peer: dict[socket.socket, str] = {}
        self._sess_thread: threading.Thread | None = None
        self._stats = BridgeStats(active=False, mode="host")

    @property
    def running(self) -> bool:
        return self._running

    def _log(self, level: str, msg: str) -> None:
        if self._log_cb:
            try:
                self._log_cb(level, msg)
            except Exception:
                pass

    def get_stats(self) -> BridgeStats:
        with self._lock:
            return BridgeStats(**self._stats.__dict__)

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self._stop_event.clear()
            self._running = True
            self._stats = BridgeStats(active=True, mode="host", last_activity_desc="房主桥接已启动，等待好友发现房间...")

        self.p2p.set_civ6_callbacks(
            on_disc_req=self._on_disc_req,
            on_disc_resp=None,
            on_session=self._on_session_from_peer,
            on_peer_offline=self.release_peer,
        )
        self._sess_thread = threading.Thread(target=self._session_recv_loop, name="civ6-host-sess", daemon=True)
        self._sess_thread.start()
        self._log("ok", f"房主文明6桥接已启动 (转发至本机 {self.target_host_ip}:{self.target_disc_port} / {self.target_session_port})")

    def stop(self) -> None:
        with self._lock:
            if not self._running:
                return
            self._running = False
            self._stop_event.set()
            self._stats.active = False
            socks = [s for s, _ in self._peer_sess_socks.values()]
            self._peer_sess_socks.clear()
            self._sock_to_peer.clear()

        self.p2p.set_civ6_callbacks(on_disc_req=None, on_disc_resp=None, on_session=None, on_peer_offline=None)
        for s in socks:
            try:
                s.close()
            except OSError:
                pass
        if self._sess_thread is not None and self._sess_thread.is_alive():
            self._sess_thread.join(timeout=1.0)
        self._log("info", "房主文明6桥接已停止。")

    def _resolve_local_civ6_target(self, port_kind: str) -> tuple[str, int]:
        if self.target_host_ip != "127.0.0.1" or self.target_disc_port != DISCOVERY_PORT:
            port = self.target_disc_port if port_kind == "disc" else self.target_session_port
            return self.target_host_ip, port

        state = inspect_civ6_state()
        if port_kind == "disc":
            ip = state.discovery_bind_addr if state.has_discovery_port else "127.0.0.1"
            return ip, self.target_disc_port
        else:
            ip = state.session_bind_addr if state.has_session_port else "127.0.0.1"
            return ip, self.target_session_port

    def _on_disc_req(self, peer_key: str, ephem_port: int, req_id: int, raw_payload: bytes) -> None:
        if not self._running:
            return
        with self._lock:
            self._stats.disc_reqs += 1
            self._stats.last_activity_desc = f"收到 {peer_key} 的房间发现请求"
        t = threading.Thread(
            target=self._relay_discovery_worker,
            args=(peer_key, ephem_port, req_id, raw_payload),
            daemon=True,
        )
        t.start()

    def _relay_discovery_worker(self, peer_key: str, ephem_port: int, req_id: int, raw_payload: bytes) -> None:
        peer = self.p2p.get_peer(peer_key)
        fake_ip = peer.fake_ip if peer else "127.0.127.1"
        target_ip, target_port = self._resolve_local_civ6_target("disc")

        s = None
        replied_count = 0
        total_bytes = 0
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            disable_udp_connreset(s)
            try:
                s.bind((fake_ip, 0))
            except OSError:
                s.bind(("127.0.0.1", 0))

            s.sendto(raw_payload or DISCOVERY_PAYLOAD, (target_ip, target_port))

            deadline = time.monotonic() + 0.65
            while time.monotonic() < deadline and not self._stop_event.is_set():
                wait_s = 0.15 if replied_count > 0 else min(0.45, max(0.05, deadline - time.monotonic()))
                s.settimeout(wait_s)
                try:
                    data, _ = s.recvfrom(8192)
                except socket.timeout:
                    if replied_count > 0:
                        break
                    continue
                except ConnectionResetError:
                    break

                replied_count += 1
                total_bytes += len(data)
                self.p2p.send_civ6_disc_resp(peer_key, ephem_port, req_id, data)
                with self._lock:
                    self._stats.disc_resps += 1
                    self._stats.last_activity_desc = f"已向 {peer_key} 转发房间信息 ({replied_count}包/{total_bytes}B)"

            if replied_count > 0:
                self._log(
                    "civ6",
                    f"[房主发现转发] 收到本机文明6房间响应 {replied_count} 包 ({total_bytes}B) -> 已发给 {peer_key}",
                )
            else:
                self._log(
                    "warn",
                    f"[房主发现转发] 向本机 {target_ip}:{target_port} 发送发现包后未收到响应，请确认本机文明6已创建局域网房间！",
                )
        except OSError as e:
            self._log("warn", f"[房主发现转发] 失败: {e}")
        finally:
            if s is not None:
                try:
                    s.close()
                except OSError:
                    pass

    def release_peer(self, peer_key: str) -> None:
        sock_to_close: socket.socket | None = None
        released_ip = ""
        with self._lock:
            entry = self._peer_sess_socks.pop(peer_key, None)
            if entry is not None:
                sock_to_close, released_ip = entry
                self._sock_to_peer.pop(sock_to_close, None)
        if sock_to_close is not None:
            try:
                sock_to_close.close()
            except OSError:
                pass
            self._log("info", f"[房主会话] 已释放离线玩家 {peer_key} 的本地会话通道 ({released_ip}:{self.local_session_bind_port})")

    def _get_or_create_peer_session_sock(self, peer_key: str) -> socket.socket | None:
        stale_socks: list[socket.socket] = []
        with self._lock:
            entry = self._peer_sess_socks.get(peer_key)
            if entry is not None:
                return entry[0]
            peer = self.p2p.get_peer(peer_key)
            if peer is None:
                return None
            fake_ip = peer.fake_ip

            for old_key, (old_sock, old_ip) in list(self._peer_sess_socks.items()):
                if old_ip == fake_ip and old_key != peer_key:
                    self._peer_sess_socks.pop(old_key, None)
                    self._sock_to_peer.pop(old_sock, None)
                    stale_socks.append(old_sock)

        for old_sock in stale_socks:
            try:
                old_sock.close()
            except OSError:
                pass

        with self._lock:
            entry = self._peer_sess_socks.get(peer_key)
            if entry is not None:
                return entry[0]

            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            try:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                disable_udp_connreset(s)
                tune_udp_buffers(s)
                s.bind((fake_ip, self.local_session_bind_port))
            except OSError as e:
                s.close()
                self._log("error", f"[房主会话] 无法绑定 {fake_ip}:{self.local_session_bind_port}: {e}")
                return None

            self._peer_sess_socks[peer_key] = (s, fake_ip)
            self._sock_to_peer[s] = peer_key
            self._log("ok", f"[房主会话] 已为 {peer.nickname} ({peer_key}) 创建本地会话通道 {fake_ip}:{self.local_session_bind_port}")
            return s

    def _on_session_from_peer(self, peer_key: str, raw_payload: bytes) -> None:
        if not self._running:
            return
        sock = self._get_or_create_peer_session_sock(peer_key)
        if sock is None:
            return
        target_ip, target_port = self._resolve_local_civ6_target("session")
        try:
            sent = sock.sendto(raw_payload, (target_ip, target_port))
            with self._lock:
                self._stats.session_rx_pkts += 1
                self._stats.session_rx_bytes += sent
                self._stats.last_activity_desc = f"62056 会话活跃中 (收 {self._stats.session_rx_pkts} / 发 {self._stats.session_tx_pkts})"
        except OSError as e:
            self._log("warn", f"[房主会话] 转发至本机文明6失败: {e}")

    def _session_recv_loop(self) -> None:
        while not self._stop_event.is_set():
            with self._lock:
                socks = list(self._sock_to_peer.keys())
            if not socks:
                self._stop_event.wait(0.05)
                continue

            try:
                readable, _, _ = select.select(socks, [], [], 0.1)
            except (OSError, ValueError):
                continue

            for s in readable:
                with self._lock:
                    peer_key = self._sock_to_peer.get(s)
                if not peer_key:
                    continue
                try:
                    data, _ = s.recvfrom(65535)
                except ConnectionResetError:
                    continue
                except OSError:
                    continue

                if self.p2p.send_civ6_session(peer_key, data):
                    with self._lock:
                        self._stats.session_tx_pkts += 1
                        self._stats.session_tx_bytes += len(data)
                        self._stats.last_activity_desc = (
                            f"62056 会话活跃中 (收 {self._stats.session_rx_pkts} / 发 {self._stats.session_tx_pkts})"
                        )


class ClientCiv6Bridge:

    def __init__(
        self,
        p2p_node: P2PNode,
        host_peer_key: str,
        log_cb: Callable[[str, str], None] | None = None,
        fake_host_ip: str = "127.0.127.1",
        local_disc_port: int = DISCOVERY_PORT,
        local_session_port: int = SESSION_PORT,
        client_civ6_ip: str = "127.0.0.1",
        client_civ6_session_port: int = SESSION_PORT,
        enable_windows_watcher: bool = True,
        enable_broadcast_sniffer: bool = True,
    ) -> None:
        self.p2p = p2p_node
        self.host_peer_key = host_peer_key
        self._log_cb = log_cb
        self.fake_host_ip = fake_host_ip
        self.local_disc_port = int(local_disc_port)
        self.local_session_port = int(local_session_port)
        self.client_civ6_ip = client_civ6_ip
        self.client_civ6_session_port = int(client_civ6_session_port)
        self.enable_windows_watcher = enable_windows_watcher and (os.name == "nt")
        self.enable_broadcast_sniffer = enable_broadcast_sniffer

        self._lock = threading.RLock()
        self._running = False
        self._stop_event = threading.Event()

        self._disc_fake_sock: socket.socket | None = None
        self._sess_fake_sock: socket.socket | None = None
        self._bcast_sniff_sock: socket.socket | None = None

        self._client_civ6_sess_addr: tuple[str, int] = (self.client_civ6_ip, self.client_civ6_session_port)
        self._req_id_seq = 0
        self._recent_ephem_sent: dict[int, float] = {}

        self._probe_lock = threading.Lock()
        self._probe_req_id: int | None = None
        self._probe_pkts: list[bytes] = []
        self._probe_event = threading.Event()

        self._threads: list[threading.Thread] = []
        self._stats = BridgeStats(active=False, mode="client", fake_host_ip=self.fake_host_ip)

    @property
    def running(self) -> bool:
        return self._running

    def _log(self, level: str, msg: str) -> None:
        if self._log_cb:
            try:
                self._log_cb(level, msg)
            except Exception:
                pass

    def get_stats(self) -> BridgeStats:
        with self._lock:
            return BridgeStats(**self._stats.__dict__)

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self._stop_event.clear()

            disc_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            disc_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            disable_udp_connreset(disc_sock)
            disc_sock.bind((self.fake_host_ip, self.local_disc_port))

            sess_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            try:
                sess_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                disable_udp_connreset(sess_sock)
                tune_udp_buffers(sess_sock)
                sess_sock.bind((self.fake_host_ip, self.local_session_port))
            except OSError:
                disc_sock.close()
                sess_sock.close()
                raise

            bcast_sock = None
            if self.enable_broadcast_sniffer:
                try:
                    bs = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
                    bs.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    disable_udp_connreset(bs)
                    bs.bind(("0.0.0.0", self.local_disc_port))
                    bcast_sock = bs
                except OSError:
                    bcast_sock = None

            self._disc_fake_sock = disc_sock
            self._sess_fake_sock = sess_sock
            self._bcast_sniff_sock = bcast_sock
            self._running = True
            self._stats = BridgeStats(
                active=True,
                mode="client",
                fake_host_ip=self.fake_host_ip,
                last_activity_desc="已就绪，请进入或刷新文明6局域网房间列表",
            )

        self.p2p.set_civ6_callbacks(
            on_disc_req=None,
            on_disc_resp=self._on_disc_resp_from_host,
            on_session=self._on_session_from_host,
        )

        self._threads = [
            threading.Thread(target=self._local_io_loop, name="civ6-client-io", daemon=True),
        ]
        if self.enable_windows_watcher:
            self._threads.append(
                threading.Thread(target=self._windows_ephem_watch_loop, name="civ6-ephem-watch", daemon=True)
            )
        for t in self._threads:
            t.start()

        sniff_msg = " + 广播直捕已启用" if self._bcast_sniff_sock else ""
        self._log(
            "ok",
            f"加入者文明6辅助已启动 -> 房主 {self.host_peer_key} | 本地虚拟房主 {self.fake_host_ip}:{self.local_disc_port}/{self.local_session_port}{sniff_msg}",
        )

    def stop(self) -> None:
        with self._lock:
            if not self._running:
                return
            self._running = False
            self._stop_event.set()
            self._stats.active = False
            socks = [self._disc_fake_sock, self._sess_fake_sock, self._bcast_sniff_sock]
            self._disc_fake_sock = None
            self._sess_fake_sock = None
            self._bcast_sniff_sock = None

        self.p2p.set_civ6_callbacks(on_disc_req=None, on_disc_resp=None, on_session=None)
        for s in socks:
            if s is not None:
                try:
                    s.close()
                except OSError:
                    pass
        for t in self._threads:
            if t.is_alive():
                t.join(timeout=1.0)
        self._threads.clear()
        self._log("info", "加入者文明6辅助已停止。")

    def trigger_discovery_for_port(self, ephem_port: int, payload: bytes = DISCOVERY_PAYLOAD, source: str = "watcher") -> bool:
        if not self._running:
            return False
        now = time.monotonic()
        with self._lock:
            last = self._recent_ephem_sent.get(ephem_port, 0.0)
            if (now - last) < 0.4:
                return False
            self._recent_ephem_sent[ephem_port] = now
            if len(self._recent_ephem_sent) > 64:
                self._recent_ephem_sent = {k: v for k, v in self._recent_ephem_sent.items() if (now - v) < 5.0}
            self._req_id_seq = (self._req_id_seq + 1) & 0xFFFF
            if self._req_id_seq == 0:
                self._req_id_seq = 1
            req_id = self._req_id_seq
            self._stats.disc_reqs += 1
            self._stats.last_activity_desc = f"已向房主转发房间发现请求 (端口 {ephem_port})"

        ok = self.p2p.send_civ6_disc_req(self.host_peer_key, ephem_port, req_id, payload)
        if ok:
            self._log("civ6", f"[加入者发现/{source}] 捕获文明6临时端口 {ephem_port} -> 通过 P2P 向房主请求房间信息")
        return ok

    def probe_host_room(self, timeout_s: float = 1.5) -> tuple[bool, int, int]:
        if not self._running:
            raise RuntimeError("请先启动加入者文明6联机辅助")

        with self._lock:
            self._req_id_seq = (self._req_id_seq + 1) & 0xFFFF
            if self._req_id_seq == 0:
                self._req_id_seq = 1
            req_id = self._req_id_seq

        with self._probe_lock:
            self._probe_req_id = req_id
            self._probe_pkts = []
            self._probe_event.clear()

        self.p2p.send_civ6_disc_req(self.host_peer_key, 0, req_id, DISCOVERY_PAYLOAD)

        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            remaining = max(0.05, deadline - time.monotonic())
            if self._probe_event.wait(timeout=min(0.25, remaining)):
                time.sleep(0.18)
                break

        with self._probe_lock:
            pkts = list(self._probe_pkts)
            self._probe_req_id = None

        count = len(pkts)
        total_bytes = sum(len(p) for p in pkts)
        if count > 0:
            self._log("ok", f"[房主房间探测] 成功收到房主文明6房间信息：{count} 个包，共 {total_bytes} 字节！现在去文明6局域网刷新即可看到房间。")
            return True, count, total_bytes
        else:
            self._log("warn", "[房主房间探测] 未收到房主文明6响应。请确认：1) 房主已启动「房主联机桥接」；2) 房主已在文明6创建局域网房间。")
            return False, 0, 0

    def _on_disc_resp_from_host(self, peer_key: str, ephem_port: int, req_id: int, raw_payload: bytes) -> None:
        if not self._running:
            return

        with self._probe_lock:
            if self._probe_req_id is not None and req_id == self._probe_req_id:
                self._probe_pkts.append(raw_payload)
                self._probe_event.set()

        with self._lock:
            self._stats.disc_resps += 1
            disc_sock = self._disc_fake_sock

        if ephem_port == 0 or disc_sock is None:
            return

        try:
            disc_sock.sendto(raw_payload, (self.client_civ6_ip, ephem_port))
            with self._lock:
                self._stats.last_activity_desc = f"已注入房主房间信息 ({len(raw_payload)}B) -> 文明6端口 {ephem_port}"
            self._log(
                "ok",
                f"[加入者发现] 注入房主房间信息: {self.fake_host_ip}:{self.local_disc_port} -> {self.client_civ6_ip}:{ephem_port} ({len(raw_payload)}B)",
            )
        except OSError as e:
            self._log("warn", f"[加入者发现] 注入回包到端口 {ephem_port} 失败: {e}")

    def _on_session_from_host(self, peer_key: str, raw_payload: bytes) -> None:
        if not self._running:
            return
        with self._lock:
            sess_sock = self._sess_fake_sock
            target_addr = self._client_civ6_sess_addr
        if sess_sock is None:
            return

        try:
            sent = sess_sock.sendto(raw_payload, target_addr)
            with self._lock:
                self._stats.session_rx_pkts += 1
                self._stats.session_rx_bytes += sent
                self._stats.last_activity_desc = (
                    f"62056 游戏会话活跃中 (发 {self._stats.session_tx_pkts} / 收 {self._stats.session_rx_pkts})"
                )
        except OSError as e:
            self._log("warn", f"[加入者会话] 转发至本机文明6失败: {e}")

    def _local_io_loop(self) -> None:
        while not self._stop_event.is_set():
            with self._lock:
                socks = [s for s in (self._sess_fake_sock, self._disc_fake_sock, self._bcast_sniff_sock) if s is not None]
                sess_sock = self._sess_fake_sock
                disc_sock = self._disc_fake_sock
                bcast_sock = self._bcast_sniff_sock

            if not socks:
                break

            try:
                readable, _, _ = select.select(socks, [], [], 0.1)
            except (OSError, ValueError):
                continue

            for s in readable:
                try:
                    data, addr = s.recvfrom(65535)
                except ConnectionResetError:
                    continue
                except OSError:
                    continue

                if s is sess_sock:
                    with self._lock:
                        self._client_civ6_sess_addr = (addr[0], int(addr[1]))
                    if self.p2p.send_civ6_session(self.host_peer_key, data):
                        with self._lock:
                            self._stats.session_tx_pkts += 1
                            self._stats.session_tx_bytes += len(data)
                            self._stats.last_activity_desc = (
                                f"62056 游戏会话活跃中 (发 {self._stats.session_tx_pkts} / 收 {self._stats.session_rx_pkts})"
                            )
                elif s is disc_sock or s is bcast_sock:
                    if data == DISCOVERY_PAYLOAD or len(data) == 4:
                        self.trigger_discovery_for_port(int(addr[1]), data, source="broadcast")

    def _windows_ephem_watch_loop(self) -> None:
        civ6_processes: dict[int, str] = {}
        last_pid_refresh = 0
        known: dict[tuple[int, int], int] = {}
        baseline_ready = False
        burst_until = 0

        while not self._stop_event.is_set():
            t = _now_ms()
            if t - last_pid_refresh >= PID_REFRESH_MS:
                last_pid_refresh = t
                new_procs = find_civ6_processes()
                if new_procs != civ6_processes:
                    civ6_processes = new_procs
                    self._log("civ6", f"检测到本机文明6进程: {format_civ6_processes(civ6_processes)}")
                    known.clear()
                    baseline_ready = False
                    burst_until = t + BURST_MS

            if not civ6_processes:
                self._stop_event.wait(IDLE_MS / 1000.0)
                continue

            try:
                candidates = read_civ6_candidates(civ6_processes)
            except Exception as e:
                self._log("warn", f"读取本机 UDP 端口表失败: {e}")
                self._stop_event.wait(IDLE_MS / 1000.0)
                continue

            current_keys = set(candidates.keys())
            if not baseline_ready:
                for key in current_keys:
                    known[key] = t
                baseline_ready = True
                self._log("civ6", f"端口基线已建立 (当前临时端口 {len(candidates)} 个)，等待刷新局域网列表...")
                sleep_ms = BURST_INTERVAL_MS if _now_ms() < burst_until else IDLE_MS
                self._stop_event.wait(sleep_ms / 1000.0)
                continue

            known_keys = set(known.keys())
            new_keys = current_keys - known_keys
            gone_keys = known_keys - current_keys

            if new_keys or gone_keys:
                burst_until = t + BURST_MS

            for key in sorted(new_keys):
                ep = candidates[key]
                known[key] = t
                self.trigger_discovery_for_port(ep.local_port, DISCOVERY_PAYLOAD, source="udp-table")

            for key in gone_keys:
                known.pop(key, None)

            sleep_ms = BURST_INTERVAL_MS if _now_ms() < burst_until else IDLE_MS
            self._stop_event.wait(sleep_ms / 1000.0)
