from __future__ import annotations

import ctypes
import ipaddress
import os
import secrets
import socket
import struct
from dataclasses import dataclass, field


SIO_UDP_CONNRESET = 0x9800000C
STUN_MAGIC_COOKIE = 0x2112A442
STUN_BINDING_REQUEST = 0x0001
STUN_BINDING_SUCCESS = 0x0101
STUN_ATTR_MAPPED_ADDRESS = 0x0001
STUN_ATTR_XOR_MAPPED_ADDRESS = 0x0020

DEFAULT_STUN_SERVERS: list[tuple[str, int]] = [
    ("stun.miwifi.com", 3478),
    ("stun.chat.bilibili.com", 3478),
    ("stun.cloudflare.com", 3478),
    ("stun.l.google.com", 19302),
]


@dataclass
class LocalNetworkInfo:
    default_ipv6: str = ""
    global_ipv6: list[str] = field(default_factory=list)
    ula_ipv6: list[str] = field(default_factory=list)
    link_local_ipv6: list[str] = field(default_factory=list)
    default_ipv4: str = ""
    ipv4: list[str] = field(default_factory=list)

    @property
    def has_public_ipv6(self) -> bool:
        return bool(self.default_ipv6 or self.global_ipv6)

    def preferred_address(self) -> str:
        if self.default_ipv6:
            return self.default_ipv6
        if self.global_ipv6:
            return self.global_ipv6[0]
        if self.ula_ipv6:
            return self.ula_ipv6[0]
        if self.default_ipv4:
            return self.default_ipv4
        if self.ipv4:
            return self.ipv4[0]
        return "::1"

    def all_candidates(self) -> list[tuple[str, str]]:
        items: list[tuple[str, str]] = []
        seen: set[str] = set()

        def add(ip: str, label: str) -> None:
            if ip and ip not in seen:
                seen.add(ip)
                items.append((ip, label))

        if self.default_ipv6:
            add(self.default_ipv6, "首选公网 IPv6")
        for ip in self.global_ipv6:
            add(ip, "公网 IPv6")
        for ip in self.ula_ipv6:
            add(ip, "私网 IPv6 (ULA)")
        if self.default_ipv4:
            add(self.default_ipv4, "首选 IPv4")
        for ip in self.ipv4:
            add(ip, "本机 IPv4")
        for ip in self.link_local_ipv6:
            add(ip, "本地链路 IPv6 (仅同局域网)")
        add("::1", "本机回环 IPv6 (仅单机自测)")
        return items


def disable_udp_connreset(sock: socket.socket) -> bool:
    if os.name != "nt":
        return True
    try:
        ws2_32 = ctypes.WinDLL("ws2_32")
        flag = ctypes.c_uint32(0)
        bytes_ret = ctypes.c_uint32(0)
        ret = ws2_32.WSAIoctl(
            sock.fileno(),
            SIO_UDP_CONNRESET,
            ctypes.byref(flag),
            ctypes.sizeof(flag),
            None,
            0,
            ctypes.byref(bytes_ret),
            None,
            None,
        )
        return ret == 0
    except Exception:
        return False


def tune_udp_buffers(sock: socket.socket, size: int = 1024 * 1024) -> None:
    for opt in (socket.SO_RCVBUF, socket.SO_SNDBUF):
        try:
            sock.setsockopt(socket.SOL_SOCKET, opt, size)
        except OSError:
            pass


def create_dualstack_udp_socket(port: int) -> tuple[socket.socket, bool, int]:
    try:
        sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        try:
            sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        except OSError:
            pass
        disable_udp_connreset(sock)
        tune_udp_buffers(sock)
        sock.bind(("::", port))
        actual_port = sock.getsockname()[1]
        return sock, True, actual_port
    except OSError:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        disable_udp_connreset(sock)
        tune_udp_buffers(sock)
        sock.bind(("0.0.0.0", port))
        actual_port = sock.getsockname()[1]
        return sock, False, actual_port


def canonicalize_ip(host: str) -> tuple[str, int]:
    clean = host.strip()
    if "%" in clean:
        clean = clean.split("%", 1)[0]
    ip_obj = ipaddress.ip_address(clean)
    if isinstance(ip_obj, ipaddress.IPv6Address) and ip_obj.ipv4_mapped is not None:
        v4 = ip_obj.ipv4_mapped
        return v4.compressed, 4
    return ip_obj.compressed, ip_obj.version


def format_endpoint(host: str, port: int) -> str:
    ip_str, ver = canonicalize_ip(host)
    if ver == 6:
        return f"[{ip_str}]:{port}"
    return f"{ip_str}:{port}"


def to_sockaddr(host: str, port: int, is_ipv6_sock: bool) -> tuple:
    ip_str, ver = canonicalize_ip(host)
    if is_ipv6_sock:
        if ver == 4:
            return (f"::ffff:{ip_str}", int(port), 0, 0)
        return (ip_str, int(port), 0, 0)
    else:
        if ver == 6:
            raise OSError(f"当前 P2P 套接字仅支持 IPv4，无法发送到 IPv6 地址: {ip_str}")
        return (ip_str, int(port))


def detect_local_network_info() -> LocalNetworkInfo:
    info = LocalNetworkInfo()
    g_v6: set[str] = set()
    ula_v6: set[str] = set()
    ll_v6: set[str] = set()
    v4_set: set[str] = set()

    for probe_target in ("2400:3200::1", "2001:4860:4860::8888"):
        s = None
        try:
            s = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
            s.connect((probe_target, 53))
            cand, ver = canonicalize_ip(s.getsockname()[0])
            if ver == 6:
                ip_obj = ipaddress.ip_address(cand)
                if ip_obj.is_global and not ip_obj.is_private:
                    info.default_ipv6 = cand
                    g_v6.add(cand)
                    break
        except OSError:
            pass
        finally:
            if s is not None:
                try:
                    s.close()
                except Exception:
                    pass

    for probe_target in ("223.5.5.5", "8.8.8.8"):
        s = None
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect((probe_target, 53))
            cand = s.getsockname()[0]
            if cand and not cand.startswith("127."):
                info.default_ipv4 = cand
                v4_set.add(cand)
                break
        except OSError:
            pass
        finally:
            if s is not None:
                try:
                    s.close()
                except Exception:
                    pass

    try:
        hostname = socket.gethostname()
        for item in socket.getaddrinfo(hostname, None):
            fam = item[0]
            raw_ip = item[4][0]
            try:
                ip_str, ver = canonicalize_ip(raw_ip)
                ip_obj = ipaddress.ip_address(ip_str)
            except ValueError:
                continue
            if ver == 6:
                if ip_obj.is_loopback:
                    continue
                if ip_obj.is_link_local:
                    ll_v6.add(ip_str)
                elif ip_obj.is_global and not ip_obj.is_private:
                    g_v6.add(ip_str)
                else:
                    ula_v6.add(ip_str)
            elif ver == 4:
                if not ip_obj.is_loopback:
                    v4_set.add(ip_str)
    except OSError:
        pass

    info.global_ipv6 = sorted(g_v6)
    info.ula_ipv6 = sorted(ula_v6)
    info.link_local_ipv6 = sorted(ll_v6)
    info.ipv4 = sorted(v4_set)
    return info


def build_stun_binding_request() -> tuple[bytes, bytes]:
    tx_id = secrets.token_bytes(12)
    pkt = struct.pack("!HHI12s", STUN_BINDING_REQUEST, 0, STUN_MAGIC_COOKIE, tx_id)
    return pkt, tx_id


def parse_stun_binding_response(raw: bytes) -> tuple[bytes, str, int] | None:
    if len(raw) < 20:
        return None
    msg_type, msg_len, cookie, tx_id = struct.unpack_from("!HHI12s", raw, 0)
    if msg_type != STUN_BINDING_SUCCESS or cookie != STUN_MAGIC_COOKIE:
        return None
    if len(raw) < 20 + msg_len:
        return None

    offset = 20
    end = 20 + msg_len
    fallback_mapped: tuple[str, int] | None = None

    while offset + 4 <= end:
        attr_type, attr_len = struct.unpack_from("!HH", raw, offset)
        offset += 4
        if offset + attr_len > end:
            break
        val = raw[offset : offset + attr_len]
        offset += (attr_len + 3) & ~3

        if attr_type == STUN_ATTR_XOR_MAPPED_ADDRESS and len(val) >= 8:
            family = val[1]
            xport = struct.unpack_from("!H", val, 2)[0] ^ (STUN_MAGIC_COOKIE >> 16)
            if family == 0x01 and len(val) >= 8:
                cookie_bytes = struct.pack("!I", STUN_MAGIC_COOKIE)
                ip_bytes = bytes(b ^ c for b, c in zip(val[4:8], cookie_bytes))
                return tx_id, socket.inet_ntop(socket.AF_INET, ip_bytes), xport
            elif family == 0x02 and len(val) >= 20:
                mask = struct.pack("!I", STUN_MAGIC_COOKIE) + tx_id
                ip_bytes = bytes(b ^ c for b, c in zip(val[4:20], mask))
                ip_str = ipaddress.IPv6Address(ip_bytes).compressed
                return tx_id, ip_str, xport

        elif attr_type == STUN_ATTR_MAPPED_ADDRESS and len(val) >= 8:
            family = val[1]
            mport = struct.unpack_from("!H", val, 2)[0]
            if family == 0x01 and len(val) >= 8:
                fallback_mapped = (socket.inet_ntop(socket.AF_INET, val[4:8]), mport)
            elif family == 0x02 and len(val) >= 20:
                ip_str = ipaddress.IPv6Address(val[4:20]).compressed
                fallback_mapped = (ip_str, mport)

    if fallback_mapped is not None:
        return tx_id, fallback_mapped[0], fallback_mapped[1]
    return None


def is_stun_packet(raw: bytes) -> bool:
    if len(raw) < 20:
        return False
    return (raw[0] & 0xC0) == 0 and struct.unpack_from("!I", raw, 4)[0] == STUN_MAGIC_COOKIE
