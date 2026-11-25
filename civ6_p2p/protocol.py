from __future__ import annotations

import hashlib
import ipaddress
import json
import struct
from dataclasses import dataclass
from enum import IntEnum
from urllib.parse import parse_qs, quote, unquote, urlparse

MAGIC = b"C6P2"
PROTO_VERSION = 1
HEADER_FMT = "!4sBB4s"
HEADER_SIZE = struct.calcsize(HEADER_FMT)

DEFAULT_P2P_PORT = 38666
DEFAULT_RELAY_PORT = 38668
DEFAULT_ROOM_KEY = "civ6"
DEFAULT_RELAY_ROOM = "civ6-room"
INVITE_SCHEME = "c6p2"


class MsgType(IntEnum):
    HELLO = 0x01
    HELLO_ACK = 0x02
    PING = 0x03
    PONG = 0x04
    TEST_REQ = 0x05
    TEST_RESP = 0x06
    BYE = 0x07

    CIV6_DISC_REQ = 0x10
    CIV6_DISC_RESP = 0x11
    CIV6_SESSION = 0x12

    RELAY_REGISTER = 0x20
    RELAY_PEERS = 0x21
    RELAY_UNREGISTER = 0x22
    RELAY_FORWARD = 0x23


def compute_room_tag(room_key: str) -> bytes:
    key = (room_key or "").strip()
    digest = hashlib.sha256(f"civ6-p2p-v1:{key}".encode("utf-8")).digest()
    return digest[:4]


def pack_packet(msg_type: MsgType, room_tag: bytes, payload: bytes = b"") -> bytes:
    return struct.pack(HEADER_FMT, MAGIC, PROTO_VERSION, int(msg_type), room_tag) + payload


def pack_json_packet(msg_type: MsgType, room_tag: bytes, data: dict) -> bytes:
    body = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return pack_packet(msg_type, room_tag, body)


def unpack_packet(raw: bytes) -> tuple[MsgType, bytes, bytes] | None:
    if len(raw) < HEADER_SIZE:
        return None
    magic, version, msg_type_val, room_tag = struct.unpack_from(HEADER_FMT, raw, 0)
    if magic != MAGIC or version != PROTO_VERSION:
        return None
    try:
        msg_type = MsgType(msg_type_val)
    except ValueError:
        return None
    return msg_type, room_tag, raw[HEADER_SIZE:]


def unpack_json_payload(payload: bytes) -> dict | None:
    try:
        obj = json.loads(payload.decode("utf-8"))
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


TEST_REQ_FMT = "!IHQ"
TEST_REQ_HDR_SIZE = struct.calcsize(TEST_REQ_FMT)

TEST_RESP_FMT = "!IHQH"
TEST_RESP_HDR_SIZE = struct.calcsize(TEST_RESP_FMT)

CIV6_DISC_FMT = "!HH"
CIV6_DISC_HDR_SIZE = struct.calcsize(CIV6_DISC_FMT)


def pack_test_req(room_tag: bytes, test_id: int, seq: int, ts_ms: int, total_payload_size: int = 64) -> bytes:
    pad_len = max(0, total_payload_size - TEST_REQ_HDR_SIZE)
    payload = struct.pack(TEST_REQ_FMT, test_id & 0xFFFFFFFF, seq & 0xFFFF, ts_ms) + (b"\xAA" * pad_len)
    return pack_packet(MsgType.TEST_REQ, room_tag, payload)


def unpack_test_req(payload: bytes) -> tuple[int, int, int, int] | None:
    if len(payload) < TEST_REQ_HDR_SIZE:
        return None
    test_id, seq, ts_ms = struct.unpack_from(TEST_REQ_FMT, payload, 0)
    return test_id, seq, ts_ms, len(payload)


def pack_test_resp(room_tag: bytes, test_id: int, seq: int, ts_ms: int, orig_len: int) -> bytes:
    payload = struct.pack(TEST_RESP_FMT, test_id & 0xFFFFFFFF, seq & 0xFFFF, ts_ms, orig_len & 0xFFFF)
    return pack_packet(MsgType.TEST_RESP, room_tag, payload)


def unpack_test_resp(payload: bytes) -> tuple[int, int, int, int] | None:
    if len(payload) < TEST_RESP_HDR_SIZE:
        return None
    return struct.unpack_from(TEST_RESP_FMT, payload, 0)


def pack_civ6_disc(msg_type: MsgType, room_tag: bytes, ephem_port: int, req_id: int, raw_civ6: bytes) -> bytes:
    payload = struct.pack(CIV6_DISC_FMT, ephem_port & 0xFFFF, req_id & 0xFFFF) + raw_civ6
    return pack_packet(msg_type, room_tag, payload)


def unpack_civ6_disc(payload: bytes) -> tuple[int, int, bytes] | None:
    if len(payload) < CIV6_DISC_HDR_SIZE:
        return None
    ephem_port, req_id = struct.unpack_from(CIV6_DISC_FMT, payload, 0)
    return ephem_port, req_id, payload[CIV6_DISC_HDR_SIZE:]


def pack_relay_forward(
    room_tag: bytes,
    room_id: str,
    src_node_id: str,
    dst_node_id: str,
    inner_packet: bytes,
) -> bytes:
    r_b = room_id.encode("utf-8")[:64]
    s_b = src_node_id.encode("ascii")[:32]
    d_b = dst_node_id.encode("ascii")[:32]
    body = (
        struct.pack("!B", len(r_b))
        + r_b
        + struct.pack("!B", len(s_b))
        + s_b
        + struct.pack("!B", len(d_b))
        + d_b
        + inner_packet
    )
    return pack_packet(MsgType.RELAY_FORWARD, room_tag, body)


def unpack_relay_forward(payload: bytes) -> tuple[str, str, str, bytes] | None:
    try:
        idx = 0
        if idx + 1 > len(payload):
            return None
        r_len = payload[idx]
        idx += 1
        if idx + r_len + 1 > len(payload):
            return None
        room_id = payload[idx : idx + r_len].decode("utf-8")
        idx += r_len

        s_len = payload[idx]
        idx += 1
        if idx + s_len + 1 > len(payload):
            return None
        src_node_id = payload[idx : idx + s_len].decode("ascii")
        idx += s_len

        d_len = payload[idx]
        idx += 1
        if idx + d_len > len(payload):
            return None
        dst_node_id = payload[idx : idx + d_len].decode("ascii")
        idx += d_len

        return room_id, src_node_id, dst_node_id, payload[idx:]
    except Exception:
        return None


def parse_server_address(text: str, default_port: int = DEFAULT_RELAY_PORT) -> tuple[str, int]:
    raw = text.strip().replace("［", "[").replace("］", "]")
    if not raw:
        raise ValueError("中继服务器地址不能为空")

    if raw.startswith("["):
        end_idx = raw.find("]")
        if end_idx == -1:
            raise ValueError("IPv6 服务器地址缺少 ']'")
        host = raw[1:end_idx].strip()
        rest = raw[end_idx + 1 :].strip().replace("：", ":")
        if not rest:
            port = default_port
        elif rest.startswith(":"):
            port = _parse_port(rest[1:])
        else:
            raise ValueError(f"无法解析端口: {rest}")
        if not host:
            raise ValueError("服务器地址不能为空")
        return host, port

    cleaned = raw.replace("：", ":")
    colon_cnt = cleaned.count(":")
    if colon_cnt == 0:
        return cleaned, default_port
    if colon_cnt == 1:
        host, port_str = cleaned.split(":", 1)
        host = host.strip()
        if not host:
            raise ValueError("服务器地址不能为空")
        return host, _parse_port(port_str)

    ip_obj = ipaddress.ip_address(cleaned.split("%", 1)[0])
    return ip_obj.compressed, default_port


@dataclass(frozen=True)
class ParsedPeerInput:
    host: str
    port: int
    ip_version: int
    nickname: str = ""
    role: str = ""
    room_key: str | None = None


def build_invite_code(
    host: str,
    port: int,
    nickname: str = "",
    role: str = "host",
    room_key: str = "",
) -> str:
    ip_obj = ipaddress.ip_address(host.strip())
    if ip_obj.version == 6:
        host_part = f"[{ip_obj.compressed}]"
    else:
        host_part = ip_obj.compressed

    params: list[str] = []
    if nickname.strip():
        params.append(f"name={quote(nickname.strip(), safe='')}")
    if role.strip():
        params.append(f"role={quote(role.strip(), safe='')}")
    if room_key.strip():
        params.append(f"key={quote(room_key.strip(), safe='')}")

    query = f"?{'&'.join(params)}" if params else ""
    return f"{INVITE_SCHEME}://{host_part}:{int(port)}{query}"


def parse_peer_input(text: str, default_port: int = DEFAULT_P2P_PORT) -> ParsedPeerInput:
    raw = text.strip()
    if not raw:
        raise ValueError("对方地址或连接码不能为空")

    raw = raw.replace("［", "[").replace("］", "]")

    nickname = ""
    role = ""
    room_key: str | None = None

    if "://" in raw:
        parsed = urlparse(raw)
        if parsed.scheme.lower() != INVITE_SCHEME:
            raise ValueError(f"不支持的连接码协议: {parsed.scheme}")
        host_str = parsed.hostname
        if not host_str:
            raise ValueError("连接码中缺少有效 IP 地址")
        port = parsed.port if parsed.port is not None else default_port
        qs = parse_qs(parsed.query, keep_blank_values=True)
        if "name" in qs and qs["name"]:
            nickname = unquote(qs["name"][0]).strip()
        if "role" in qs and qs["role"]:
            role = unquote(qs["role"][0]).strip().lower()
        if "key" in qs and qs["key"]:
            room_key = unquote(qs["key"][0]).strip()
    else:
        if raw.startswith("["):
            end_idx = raw.find("]")
            if end_idx == -1:
                raise ValueError("IPv6 地址缺少右括号 ']'")
            host_str = raw[1:end_idx].strip()
            rest = raw[end_idx + 1 :].strip().replace("：", ":")
            if not rest:
                port = default_port
            elif rest.startswith(":"):
                port = _parse_port(rest[1:])
            else:
                raise ValueError(f"无法解析端口部分: {rest}")
        else:
            cleaned = raw.replace("：", ":")
            if cleaned.count(":") == 0:
                host_str = cleaned
                port = default_port
            elif cleaned.count(":") == 1:
                host_str, port_str = cleaned.split(":", 1)
                port = _parse_port(port_str)
            else:
                host_str = cleaned
                port = default_port

    if "%" in host_str:
        host_str = host_str.split("%", 1)[0]

    try:
        ip_obj = ipaddress.ip_address(host_str)
    except ValueError:
        raise ValueError(f"不是合法的 IPv6 或 IPv4 地址: {host_str}") from None

    if not (1 <= port <= 65535):
        raise ValueError(f"端口必须在 1-65535 之间: {port}")

    return ParsedPeerInput(
        host=ip_obj.compressed,
        port=port,
        ip_version=ip_obj.version,
        nickname=nickname,
        role=role,
        room_key=room_key,
    )


def _parse_port(port_str: str) -> int:
    try:
        port = int(port_str.strip())
    except ValueError:
        raise ValueError(f"端口不是有效数字: {port_str}") from None
    if not (1 <= port <= 65535):
        raise ValueError(f"端口超出范围 (1-65535): {port}")
    return port
