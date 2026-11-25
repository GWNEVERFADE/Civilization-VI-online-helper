#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EasyTier (--no-tun) embedded session manager for CV6 online helper.

Architecture (Zero VPS, Zero Admin, Zero Virtual NIC):
  - Host:
      1. Runs in-process RelayServer on 127.0.0.1:38668
      2. Launches bundled easytier-core.exe in --no-tun mode with fixed virtual IP 10.144.144.1,
         joining the EasyTier network (--network-name / --network-secret) via public or custom EasyTier nodes.
      3. Host's P2PNode connects locally to 127.0.0.1:38668.
  - Client:
      1. Picks a free local UDP port `fwd_port`.
      2. Launches bundled easytier-core.exe in --no-tun -d (DHCP) mode with:
           --port-forward udp://127.0.0.1:<fwd_port>/10.144.144.1:38668
      3. Client's P2PNode connects locally to 127.0.0.1:<fwd_port>, which EasyTier tunnels
         (via P2P hole-punching or EasyTier public relay) straight to Host's RelayServer!
"""

from __future__ import annotations

import atexit
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Callable

from .protocol import DEFAULT_RELAY_PORT
from .relay_server import RelayServer

EASYTIER_HOST_VIP = "10.144.144.1"
EASYTIER_HOST_CIDR = f"{EASYTIER_HOST_VIP}/16"
EASYTIER_HOST_RELAY_PORT = DEFAULT_RELAY_PORT  # 38668

# Custom VPS nodes only — public/community relay presets intentionally removed.
DEFAULT_EASYTIER_NODE_PRESETS: list[tuple[str, str]] = []


def _pick_random_client_cidr() -> str:
    """
    Pick a unique virtual IP in 10.144.X.Y/16 (excluding 10.144.144.x) per session.
    Avoids EasyTier DHCP reusing 10.144.144.2 when a player disconnects and rejoins
    mid-game, which otherwise collides with the Host's stale --no-tun UDP NAT mapping.
    """
    while True:
        oct3 = 1 + secrets.randbelow(254)
        if oct3 == 144:
            continue
        oct4 = 2 + secrets.randbelow(253)
        return f"10.144.{oct3}.{oct4}/16"

_ACTIVE_SESSIONS: set["EasyTierSession"] = set()
_SESSIONS_LOCK = threading.Lock()


def _cleanup_all_sessions() -> None:
    with _SESSIONS_LOCK:
        sessions = list(_ACTIVE_SESSIONS)
    for s in sessions:
        try:
            s.stop()
        except Exception:
            pass


atexit.register(_cleanup_all_sessions)


def find_easytier_core() -> Path:
    """Locate bundled or system easytier-core executable."""
    exe_name = "easytier-core.exe" if os.name == "nt" else "easytier-core"
    candidates: list[Path] = []

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "bin" / exe_name)
        candidates.append(Path(meipass) / exe_name)

    pkg_root = Path(__file__).resolve().parent.parent
    candidates.append(pkg_root / "bin" / exe_name)
    candidates.append(Path(sys.executable).resolve().parent / "bin" / exe_name)
    candidates.append(Path(sys.executable).resolve().parent / exe_name)

    for cand in candidates:
        if cand.is_file():
            return cand

    found = shutil.which(exe_name)
    if found:
        return Path(found)

    raise FileNotFoundError(
        f"未找到 EasyTier 核心程序 ({exe_name})。请确认 bin/{exe_name} 存在。"
    )


def parse_easytier_peers(raw: str) -> list[str]:
    """Parse one or more EasyTier peer URIs separated by comma/semicolon/whitespace."""
    text = raw.strip()
    if not text:
        raise ValueError("EasyTier 节点地址不能为空")

    # Strip friendly label suffix like "  [EasyTier 官方...]" if selected from combobox
    if "  [" in text:
        text = text.split("  [", 1)[0].strip()

    tokens = [t.strip() for t in re.split(r"[,;\s]+", text) if t.strip()]
    if not tokens:
        raise ValueError("EasyTier 节点地址不能为空")

    uris: list[str] = []
    for tok in tokens:
        if "://" not in tok:
            tok = f"tcp://{tok}"
        uris.append(tok)
    return uris


def _pick_free_udp_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])
    finally:
        s.close()


class EasyTierSession:
    """Manages an embedded easytier-core (--no-tun) subprocess + Host in-process RelayServer."""

    def __init__(
        self,
        role: str,
        room_name: str,
        room_secret: str,
        peer_uris: list[str],
        hostname: str = "",
        host_relay_port: int = EASYTIER_HOST_RELAY_PORT,
        extra_listeners: list[str] | None = None,
        log_cb: Callable[[str, str], None] | None = None,
    ) -> None:
        self.role = role.strip().lower()
        if self.role not in ("host", "client"):
            raise ValueError(f"无效角色: {role}")
        self.room_name = room_name.strip()[:64]
        if not self.room_name:
            raise ValueError("EasyTier 房间名不能为空")
        self.room_secret = room_secret.strip()[:64]
        self.peer_uris = list(peer_uris)
        self.hostname = (hostname.strip() or ("civ6-host" if self.role == "host" else "civ6-client"))[:32]
        self.host_relay_port = int(host_relay_port)
        self.extra_listeners = list(extra_listeners) if extra_listeners is not None else []
        self._log_cb = log_cb

        self._lock = threading.RLock()
        self._running = False
        self._proc: subprocess.Popen | None = None
        self._relay_server: RelayServer | None = None
        self._local_relay_addr: str = ""
        self._log_thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        with self._lock:
            return self._running and (self._proc is not None) and (self._proc.poll() is None)

    @property
    def local_relay_addr(self) -> str:
        return self._local_relay_addr

    def _log(self, level: str, msg: str) -> None:
        if self._log_cb:
            try:
                self._log_cb(level, msg)
            except Exception:
                pass

    def start(self) -> str:
        """
        Start EasyTier session (and Host in-process RelayServer if role == 'host').
        Returns the local '127.0.0.1:<port>' address for P2PNode.connect_relay().
        """
        with self._lock:
            if self._running:
                return self._local_relay_addr

            exe_path = find_easytier_core()
            machine_id = str(uuid.uuid4())
            client_cidr = ""

            cmd: list[str] = [
                str(exe_path),
                "--no-tun",
                "--machine-id",
                machine_id,
                "--network-name",
                self.room_name,
                "--network-secret",
                self.room_secret or "civ6",
                "--hostname",
                self.hostname,
                "-r",
                "0",
            ]

            if self.extra_listeners:
                for lst in self.extra_listeners:
                    cmd.extend(["-l", lst])
            else:
                # Ephemeral random listeners allow EasyTier P2P hole-punching without port 11010 collisions
                cmd.extend(["-l", "tcp://0.0.0.0:0", "-l", "udp://0.0.0.0:0"])

            for uri in self.peer_uris:
                cmd.extend(["-p", uri])

            if self.role == "host":
                # Start embedded RelayServer on fixed port 38668 inside Host process
                srv = RelayServer(listen_port=self.host_relay_port, log_cb=self._log_cb)
                actual_relay_port = srv.start()
                self._relay_server = srv
                self._local_relay_addr = f"127.0.0.1:{actual_relay_port}"
                cmd.extend(["-i", EASYTIER_HOST_CIDR])
            else:
                fwd_port = _pick_free_udp_port()
                client_cidr = _pick_random_client_cidr()
                self._local_relay_addr = f"127.0.0.1:{fwd_port}"
                cmd.extend(
                    [
                        "-i",
                        client_cidr,
                        "--port-forward",
                        f"udp://127.0.0.1:{fwd_port}/{EASYTIER_HOST_VIP}:{self.host_relay_port}",
                    ]
                )

            creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            try:
                proc = subprocess.Popen(
                    cmd,
                    cwd=str(exe_path.parent),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=creationflags,
                )
            except Exception:
                if self._relay_server is not None:
                    self._relay_server.stop()
                    self._relay_server = None
                raise

            self._proc = proc
            self._running = True

        with _SESSIONS_LOCK:
            _ACTIVE_SESSIONS.add(self)

        self._log_thread = threading.Thread(target=self._watch_stdout, name="easytier-log", daemon=True)
        self._log_thread.start()

        # Quick startup sanity check (catch immediate exit like bad args / missing DLL)
        time.sleep(0.35)
        if proc.poll() is not None:
            rc = proc.returncode
            self.stop()
            raise RuntimeError(f"EasyTier 核心进程启动后立即退出 (退出码={rc})，请查看日志排查节点参数。")

        role_cn = f"房主 ({EASYTIER_HOST_VIP})" if self.role == "host" else f"加入者 ({client_cidr.split('/')[0]} + UDP端口转发)"
        self._log(
            "ok",
            f"[EasyTier] 已启动 ({role_cn}) | 房间={self.room_name} | 节点={', '.join(self.peer_uris) or '本地监听'}",
        )
        return self._local_relay_addr

    def stop(self) -> None:
        with self._lock:
            proc = self._proc
            srv = self._relay_server
            was_running = self._running
            self._proc = None
            self._relay_server = None
            self._running = False

        with _SESSIONS_LOCK:
            _ACTIVE_SESSIONS.discard(self)

        if proc is not None:
            try:
                if proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=1.5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=1.0)
            except Exception:
                pass
            if proc.stdout is not None:
                try:
                    proc.stdout.close()
                except Exception:
                    pass

        if srv is not None:
            try:
                srv.stop()
            except Exception:
                pass

        if was_running:
            self._log("info", "[EasyTier] 会话已停止。")

    def _watch_stdout(self) -> None:
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        last_err_sig = ""
        last_err_ts = 0.0
        try:
            for raw_line in proc.stdout:
                line = raw_line.strip()
                if not line:
                    continue
                low = line.lower()
                if "port forward added" in low:
                    self._log("p2p", "[EasyTier] 本地 UDP 转发通道已建立")
                elif "new peer" in low or "connected to peer" in low or ("peer_conn" in low and "add" in low):
                    self._log("ok", "[EasyTier] 已接入 EasyTier 中继网络")
                elif "hole punch" in low and ("succ" in low or "ok" in low):
                    self._log("ok", "[EasyTier] 已成功打洞升级为直连！")
                elif "error" in low and "addrnotavailable" not in low:
                    short = line[:360]
                    # Deduplicate identical error messages spamming every second
                    err_sig = short.split("connect to peer error", 1)[-1] if "connect to peer error" in short else short
                    now = time.monotonic()
                    if err_sig != last_err_sig or (now - last_err_ts) >= 5.0:
                        last_err_sig = err_sig
                        last_err_ts = now
                        self._log("warn", f"[EasyTier] {short}")
        except Exception:
            pass
