from __future__ import annotations

import json
import os
import secrets
import select
import socket
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .easytier_manager import parse_easytier_peers
from .network_utils import canonicalize_ip, create_dualstack_udp_socket, to_sockaddr
from .protocol import (
    DEFAULT_RELAY_PORT,
    DEFAULT_ROOM_KEY,
    MsgType,
    compute_relay_auth_token,
    compute_room_tag,
    pack_json_packet,
    parse_server_address,
    unpack_json_payload,
    unpack_packet,
)

DEFAULT_EASYTIER_PORT = 11010
VALID_VPS_KINDS = ("easytier", "udp_relay")


@dataclass
class VpsNodeItem:
    id: str
    name: str
    address: str
    kind: str = "easytier"
    password: str = ""

    def kind_label(self) -> str:
        return "UDP中继" if self.kind == "udp_relay" else "EasyTier"

    def display_label(self) -> str:
        tag = f"{self.name} · {self.kind_label()}" if self.name else self.kind_label()
        return f"{self.address}  [{tag}]"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["kind_label"] = self.kind_label()
        d["label"] = self.display_label()
        d["has_password"] = bool(self.password)
        return d


def default_vps_store_path() -> Path:
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
        return Path(base) / "CV6OnlineHelper" / "vps_nodes.json"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "cv6-online-helper" / "vps_nodes.json"
    return Path.home() / ".config" / "cv6-online-helper" / "vps_nodes.json"


def normalize_vps_node_address(address: str, kind: str = "easytier") -> str:
    clean_kind = str(kind).strip().lower()
    if clean_kind not in VALID_VPS_KINDS:
        raise ValueError(f"不支持的 VPS 节点类型: {kind}")

    raw = str(address).strip()
    if not raw:
        raise ValueError("VPS 节点地址不能为空")

    if clean_kind == "udp_relay":
        stripped = raw
        for prefix in ("relay://", "civ6://", "udp://"):
            if stripped.lower().startswith(prefix):
                stripped = stripped[len(prefix) :].strip()
                break
        host, port = parse_server_address(stripped, default_port=DEFAULT_RELAY_PORT)
        if ":" in host and not host.startswith("["):
            return f"[{host}]:{port}"
        return f"{host}:{port}"

    uris = parse_easytier_peers(raw)
    normalized: list[str] = []
    for uri in uris:
        scheme, rest = uri.split("://", 1)
        if rest and not rest.startswith("[") and ":" not in rest and "/" not in rest:
            rest = f"{rest}:{DEFAULT_EASYTIER_PORT}"
        normalized.append(f"{scheme}://{rest}")
    return ", ".join(normalized)


def resolve_relay_node(
    raw_input: str, saved_nodes: list[VpsNodeItem]
) -> tuple[str, str, str, str]:
    text = str(raw_input).strip()
    if not text:
        raise ValueError("请先添加或输入自建 VPS 节点地址（例如 tcp://你的VPS:11010 或 relay://你的VPS:38668）。")

    for node in saved_nodes:
        if text in (node.id, node.display_label(), node.address):
            return node.kind, node.address, node.name or node.address, node.password

    clean = text.split("  [", 1)[0].strip() if "  [" in text else text
    for node in saved_nodes:
        if clean == node.address:
            return node.kind, node.address, node.name or node.address, node.password

    low = clean.lower()
    if low.startswith("relay://") or low.startswith("civ6://"):
        norm = normalize_vps_node_address(clean, kind="udp_relay")
        return "udp_relay", norm, norm, ""

    norm = normalize_vps_node_address(clean, kind="easytier")
    return "easytier", norm, norm, ""


def resolve_relay_input(
    raw_input: str, saved_nodes: list[VpsNodeItem]
) -> tuple[str, str, str]:
    kind, norm, name, _pw = resolve_relay_node(raw_input, saved_nodes)
    return kind, norm, name


class VpsNodeStore:

    def __init__(self, path: Path | None = None) -> None:
        self.path = path if path is not None else default_vps_store_path()
        self._nodes: list[VpsNodeItem] = []
        self.load()

    def load(self) -> list[VpsNodeItem]:
        items: list[VpsNodeItem] = []
        try:
            if self.path.is_file():
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(raw, list):
                    for entry in raw:
                        if not isinstance(entry, dict):
                            continue
                        addr = str(entry.get("address", "")).strip()
                        kind = str(entry.get("kind", "easytier")).strip().lower()
                        if not addr or kind not in VALID_VPS_KINDS:
                            continue
                        nid = str(entry.get("id", "")).strip() or secrets.token_hex(6)
                        name = str(entry.get("name", "")).strip()[:40]
                        pw = str(entry.get("password", "")).strip()[:128]
                        items.append(VpsNodeItem(id=nid, name=name, address=addr, kind=kind, password=pw))
        except Exception:
            items = []
        self._nodes = items
        return list(self._nodes)

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            data = []
            for n in self._nodes:
                row = {"id": n.id, "name": n.name, "address": n.address, "kind": n.kind}
                if n.password:
                    row["password"] = n.password
                data.append(row)
            self.path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass

    def list_nodes(self) -> list[VpsNodeItem]:
        return list(self._nodes)

    def add_node(self, name: str, address: str, kind: str = "easytier", password: str = "") -> VpsNodeItem:
        clean_kind = str(kind).strip().lower()
        if clean_kind not in VALID_VPS_KINDS:
            raise ValueError("节点类型必须是 EasyTier 或 UDP 中继")
        norm_addr = normalize_vps_node_address(address, kind=clean_kind)
        clean_name = str(name).strip()[:40]
        clean_pw = str(password or "").strip()[:128]
        if not clean_name:
            host_hint = norm_addr.split(",", 1)[0].strip()
            if "://" in host_hint:
                host_hint = host_hint.split("://", 1)[1]
            clean_name = host_hint[:32]

        for existing in self._nodes:
            if existing.kind == clean_kind and existing.address.lower() == norm_addr.lower():
                existing.name = clean_name
                existing.password = clean_pw
                self._save()
                return existing

        item = VpsNodeItem(
            id=secrets.token_hex(6),
            name=clean_name,
            address=norm_addr,
            kind=clean_kind,
            password=clean_pw,
        )
        self._nodes.insert(0, item)
        self._save()
        return item

    def remove_node(self, node_id: str) -> bool:
        target = str(node_id).strip()
        before = len(self._nodes)
        self._nodes = [n for n in self._nodes if n.id != target]
        if len(self._nodes) != before:
            self._save()
            return True
        return False


def default_ui_prefs_path() -> Path:
    return default_vps_store_path().parent / "ui_prefs.json"


class UiPrefsStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path if path is not None else default_ui_prefs_path()
        self.lang: str = "zh"
        self.theme: str = "light"
        self.load()

    def load(self) -> None:
        try:
            if self.path.is_file():
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    lang = str(raw.get("lang", "zh")).strip().lower()
                    if lang in ("zh", "en"):
                        self.lang = lang
                    theme = str(raw.get("theme", "light")).strip().lower()
                    if theme in ("light", "dark"):
                        self.theme = theme
        except Exception:
            pass

    def save(self, lang: str | None = None, theme: str | None = None) -> None:
        if lang in ("zh", "en"):
            self.lang = lang
        if theme in ("light", "dark"):
            self.theme = theme
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps({"lang": self.lang, "theme": self.theme}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass


@dataclass
class VpsProbeResult:
    ok: bool
    kind: str
    target: str
    rtt_ms: float | None
    auth_error: bool
    summary_zh: str
    summary_en: str
    detail_zh: str
    detail_en: str


def _probe_udp_relay_vps(
    norm_addr: str,
    password: str = "",
    room_key: str = DEFAULT_ROOM_KEY,
    timeout_s: float = 2.5,
) -> VpsProbeResult:
    host, port = parse_server_address(norm_addr, default_port=DEFAULT_RELAY_PORT)
    try:
        infos = socket.getaddrinfo(host, port, socket.AF_UNSPEC, socket.SOCK_DGRAM)
        if not infos:
            raise OSError("empty DNS result")
    except OSError as e:
        return VpsProbeResult(
            ok=False,
            kind="udp_relay",
            target=norm_addr,
            rtt_ms=None,
            auth_error=False,
            summary_zh=f"DNS 解析失败 ({host}): {e}",
            summary_en=f"DNS resolution failed ({host}): {e}",
            detail_zh=f"无法解析目标主机 {host}：{e}\n请检查域名或 IP 拼写及本机网络。",
            detail_en=f"Failed to resolve host {host}: {e}\nPlease verify the hostname/IP and network.",
        )

    sock, is_v6, _local_port = create_dualstack_udp_socket(0)
    chosen = infos[0]
    for info in infos:
        if info[0] == socket.AF_INET6 and is_v6:
            chosen = info
            break
    if not is_v6:
        for info in infos:
            if info[0] == socket.AF_INET:
                chosen = info
                break
    target_ip, _ver = canonicalize_ip(chosen[4][0])
    target_sockaddr = to_sockaddr(target_ip, port, is_v6)

    room_tag = compute_room_tag(room_key or DEFAULT_ROOM_KEY)
    probe_room = "__civ6_probe__"
    probe_node = f"probe-{secrets.token_hex(4)}"
    auth_tok = compute_relay_auth_token(password)

    reg_body: dict[str, Any] = {
        "room_id": probe_room,
        "node_id": probe_node,
        "nickname": "probe",
        "role": "client",
        "civ6": {},
    }
    if auth_tok:
        reg_body["auth"] = auth_tok
    reg_pkt = pack_json_packet(MsgType.RELAY_REGISTER, room_tag, reg_body)

    try:
        sock.sendto(reg_pkt, target_sockaddr)
        t_sent = time.monotonic()
        deadline = t_sent + max(0.8, float(timeout_s))
        retried = False
        while time.monotonic() < deadline:
            now = time.monotonic()
            if not retried and (now - t_sent) >= 1.0:
                retried = True
                sock.sendto(reg_pkt, target_sockaddr)
                t_sent = time.monotonic()
            rem = max(0.05, min(0.25, deadline - time.monotonic()))
            readable, _, _ = select.select([sock], [], [], rem)
            if not readable:
                continue
            try:
                raw, _addr = sock.recvfrom(65535)
            except ConnectionResetError:
                return VpsProbeResult(
                    ok=False,
                    kind="udp_relay",
                    target=norm_addr,
                    rtt_ms=None,
                    auth_error=False,
                    summary_zh=f"UDP {port} 端口不可达 (ICMP 拒绝)，请确认 civ6_relay_server.py 已启动",
                    summary_en=f"UDP port {port} unreachable (ICMP); check if civ6_relay_server.py is running",
                    detail_zh=f"目标 {norm_addr} ({target_ip}:{port}) 返回端口不可达。\n请确认 VPS 已运行 civ6_relay_server.py --port {port}。",
                    detail_en=f"Target {norm_addr} ({target_ip}:{port}) returned port unreachable.\nVerify civ6_relay_server.py --port {port} is running.",
                )
            parsed = unpack_packet(raw)
            if parsed is None:
                continue
            mtype, rtag, payload = parsed
            if mtype != MsgType.RELAY_PEERS or rtag != room_tag:
                continue
            data = unpack_json_payload(payload)
            if data is None or data.get("room_id") != probe_room:
                continue
            rtt_ms = max(0.1, (time.monotonic() - t_sent) * 1000.0)
            if data.get("auth_error"):
                return VpsProbeResult(
                    ok=False,
                    kind="udp_relay",
                    target=norm_addr,
                    rtt_ms=rtt_ms,
                    auth_error=True,
                    summary_zh=f"VPS UDP 中继可达 ({rtt_ms:.1f} ms)，但连接密码错误或未填写！",
                    summary_en=f"VPS UDP Relay reachable ({rtt_ms:.1f} ms), but password is wrong or missing!",
                    detail_zh=(
                        f"已收到服务端 {norm_addr} ({target_ip}:{port}) 响应（延迟 {rtt_ms:.1f} ms），但服务端拒绝了认证。\n\n"
                        "请在「连接密码（选填）」中填写与服务端 --password 一致的密码后重试。"
                    ),
                    detail_en=(
                        f"Server {norm_addr} ({target_ip}:{port}) responded ({rtt_ms:.1f} ms), but rejected authentication.\n\n"
                        "Enter the matching server --password in Password (Opt.) and try again."
                    ),
                )
            unreg_body: dict[str, Any] = {"room_id": probe_room, "node_id": probe_node}
            if auth_tok:
                unreg_body["auth"] = auth_tok
            try:
                sock.sendto(pack_json_packet(MsgType.RELAY_UNREGISTER, room_tag, unreg_body), target_sockaddr)
            except OSError:
                pass
            auth_zh = " · 密码认证通过" if auth_tok else ""
            auth_en = " · Auth OK" if auth_tok else ""
            return VpsProbeResult(
                ok=True,
                kind="udp_relay",
                target=norm_addr,
                rtt_ms=rtt_ms,
                auth_error=False,
                summary_zh=f"VPS UDP 中继连通正常 · 延迟 {rtt_ms:.1f} ms{auth_zh}",
                summary_en=f"VPS UDP Relay reachable · {rtt_ms:.1f} ms{auth_en}",
                detail_zh=(
                    f"目标节点：{norm_addr} ({target_ip}:{port})\n"
                    f"握手延迟：{rtt_ms:.1f} ms{auth_zh}\n\n"
                    "VPS 轻量 UDP 中继运行正常，可直接点击「连接 VPS 房间」。"
                ),
                detail_en=(
                    f"Target: {norm_addr} ({target_ip}:{port})\n"
                    f"Handshake RTT: {rtt_ms:.1f} ms{auth_en}\n\n"
                    "VPS lightweight UDP relay is healthy and ready to connect."
                ),
            )
    except OSError as e:
        return VpsProbeResult(
            ok=False,
            kind="udp_relay",
            target=norm_addr,
            rtt_ms=None,
            auth_error=False,
            summary_zh=f"探测 VPS UDP 中继失败: {e}",
            summary_en=f"VPS UDP Relay probe failed: {e}",
            detail_zh=f"向 {norm_addr} 发送探测包时出错：{e}",
            detail_en=f"Error probing {norm_addr}: {e}",
        )
    finally:
        try:
            sock.close()
        except OSError:
            pass

    return VpsProbeResult(
        ok=False,
        kind="udp_relay",
        target=norm_addr,
        rtt_ms=None,
        auth_error=False,
        summary_zh=f"VPS UDP 中继无响应 (>{timeout_s:.1f}s)，请检查安全组 UDP {port}",
        summary_en=f"VPS UDP Relay timed out (>{timeout_s:.1f}s); check firewall UDP {port}",
        detail_zh=(
            f"目标 {norm_addr} ({target_ip}:{port}) 在 {timeout_s:.1f} 秒内未响应。\n\n"
            f"排查建议：\n"
            f"1. 确认云服务器安全组及系统防火墙已放行 UDP {port}；\n"
            f"2. 确认 VPS 上已运行 python3 civ6_relay_server.py --port {port}；\n"
            f"3. 如本机开启代理/TUN 模式，尝试将 VPS IP 加入直连规则。"
        ),
        detail_en=(
            f"Target {norm_addr} ({target_ip}:{port}) did not respond within {timeout_s:.1f}s.\n\n"
            f"Checklist:\n"
            f"1. Open UDP {port} on your VPS security group & firewall.\n"
            f"2. Confirm python3 civ6_relay_server.py --port {port} is running.\n"
            f"3. Bypass your VPS IP if a local VPN/TUN proxy is enabled."
        ),
    )


def _probe_single_easytier_uri(uri: str, timeout_s: float = 3.0) -> tuple[bool, float | None, str, str]:
    parsed = urlparse(uri)
    scheme = (parsed.scheme or "tcp").lower()
    host = parsed.hostname or ""
    port = parsed.port or DEFAULT_EASYTIER_PORT
    if not host:
        return False, None, f"{uri}: 无法解析主机名", f"{uri}: invalid hostname"

    if scheme in ("udp", "quic", "wg"):
        try:
            infos = socket.getaddrinfo(host, port, socket.AF_UNSPEC, socket.SOCK_DGRAM)
            if not infos:
                raise OSError("empty DNS result")
        except OSError as e:
            return False, None, f"{uri}: DNS 解析失败 ({e})", f"{uri}: DNS failed ({e})"
        af, _stype, _proto, _canon, sockaddr = infos[0]
        resolved_ip = sockaddr[0]
        s = socket.socket(af, socket.SOCK_DGRAM)
        try:
            s.settimeout(0.45)
            s.connect(sockaddr)
            t0 = time.monotonic()
            s.send(b"\x00\x00\x00\x00")
            try:
                s.recv(64)
                rtt = max(0.1, (time.monotonic() - t0) * 1000.0)
                return (
                    True,
                    rtt,
                    f"{uri} ({resolved_ip}): UDP 响应正常 ({rtt:.1f} ms)",
                    f"{uri} ({resolved_ip}): UDP responded ({rtt:.1f} ms)",
                )
            except socket.timeout:
                return (
                    True,
                    None,
                    f"{uri} ({resolved_ip}): DNS 解析正常且无 ICMP 拒包（UDP 协议无法纯握手测延迟）",
                    f"{uri} ({resolved_ip}): DNS resolved, no ICMP reject (UDP probe)",
                )
            except ConnectionResetError:
                return (
                    False,
                    None,
                    f"{uri} ({resolved_ip}): UDP 端口 {port} 不可达 (ICMP 拒绝)",
                    f"{uri} ({resolved_ip}): UDP port {port} unreachable (ICMP)",
                )
        except OSError as e:
            return False, None, f"{uri}: UDP 探测出错 ({e})", f"{uri}: UDP probe error ({e})"
        finally:
            try:
                s.close()
            except OSError:
                pass

    try:
        infos = socket.getaddrinfo(host, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
        if not infos:
            raise OSError("empty DNS result")
    except OSError as e:
        return False, None, f"{uri}: DNS 解析失败 ({e})", f"{uri}: DNS failed ({e})"

    t0 = time.monotonic()
    s: socket.socket | None = None
    try:
        s = socket.create_connection((host, port), timeout=max(0.8, float(timeout_s)))
        rtt = max(0.1, (time.monotonic() - t0) * 1000.0)
        peer_ip = s.getpeername()[0]
        return (
            True,
            rtt,
            f"{uri} ({peer_ip}): TCP 连通 · 延迟 {rtt:.1f} ms",
            f"{uri} ({peer_ip}): TCP reachable · {rtt:.1f} ms",
        )
    except ConnectionRefusedError:
        return (
            False,
            None,
            f"{uri}: 端口 {port} 拒绝连接（VPS 上 EasyTier 未运行或端口不一致）",
            f"{uri}: Port {port} connection refused (EasyTier not running or wrong port)",
        )
    except (socket.timeout, TimeoutError):
        return (
            False,
            None,
            f"{uri}: TCP 连接超时 (>{timeout_s:.1f}s，请检查安全组/防火墙 TCP {port} 或确认协议是否为 udp://)",
            f"{uri}: TCP timed out (>{timeout_s:.1f}s; check firewall TCP {port} or try udp://)",
        )
    except OSError as e:
        return False, None, f"{uri}: 连接失败 ({e})", f"{uri}: connect failed ({e})"
    finally:
        if s is not None:
            try:
                s.close()
            except OSError:
                pass


def probe_vps_connectivity(
    kind: str,
    norm_addr: str,
    password: str = "",
    room_key: str = DEFAULT_ROOM_KEY,
    timeout_s: float = 3.0,
) -> VpsProbeResult:
    clean_kind = str(kind or "easytier").strip().lower()
    if clean_kind == "udp_relay":
        return _probe_udp_relay_vps(norm_addr, password=password, room_key=room_key, timeout_s=min(timeout_s, 2.5))

    uris = parse_easytier_peers(norm_addr)
    lines_zh: list[str] = []
    lines_en: list[str] = []
    ok_count = 0
    best_rtt: float | None = None
    for uri in uris:
        ok, rtt, zh_line, en_line = _probe_single_easytier_uri(uri, timeout_s=timeout_s)
        lines_zh.append(("✅ " if ok else "❌ ") + zh_line)
        lines_en.append(("✅ " if ok else "❌ ") + en_line)
        if ok:
            ok_count += 1
            if rtt is not None and (best_rtt is None or rtt < best_rtt):
                best_rtt = rtt

    if ok_count > 0:
        rtt_zh = f" · 延迟 {best_rtt:.1f} ms" if best_rtt is not None else ""
        rtt_en = f" · {best_rtt:.1f} ms" if best_rtt is not None else ""
        pw_zh = "\n提示：若 VPS 开启了 --private-mode，请确保「房间名」与「连接密码」与服务端一致。" if password else ""
        pw_en = "\nNote: If --private-mode is enabled on VPS, ensure Room Name & Password match." if password else ""
        return VpsProbeResult(
            ok=True,
            kind="easytier",
            target=norm_addr,
            rtt_ms=best_rtt,
            auth_error=False,
            summary_zh=f"VPS EasyTier 节点连通正常 ({ok_count}/{len(uris)} 可达){rtt_zh}",
            summary_en=f"VPS EasyTier reachable ({ok_count}/{len(uris)} OK){rtt_en}",
            detail_zh="\n".join(lines_zh) + pw_zh,
            detail_en="\n".join(lines_en) + pw_en,
        )

    return VpsProbeResult(
        ok=False,
        kind="easytier",
        target=norm_addr,
        rtt_ms=None,
        auth_error=False,
        summary_zh=f"VPS EasyTier 节点不可达 (0/{len(uris)} 可达)，请检查端口与防火墙",
        summary_en=f"VPS EasyTier unreachable (0/{len(uris)} OK); check port & firewall",
        detail_zh="\n".join(lines_zh),
        detail_en="\n".join(lines_en),
    )
