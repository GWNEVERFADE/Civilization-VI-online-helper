from __future__ import annotations

import ctypes
import os
import socket
import struct
from ctypes import wintypes
from dataclasses import dataclass, field

CIV6_PROCESS_NAMES = {
    "civilizationvi_dx12.exe",
    "civilizationvi.exe",
}

DISCOVERY_PORT = 62900
SESSION_PORT = 62056
DISCOVERY_PAYLOAD = bytes.fromhex("8de8fc70")

WINDOWS_DYNAMIC_PORT_MIN = 49152
WINDOWS_DYNAMIC_PORT_MAX = 65535

AF_INET = 2
ERROR_INSUFFICIENT_BUFFER = 122
NO_ERROR = 0
TH32CS_SNAPPROCESS = 0x00000002
MAX_PATH = 260
UDP_TABLE_OWNER_PID = 1

ULONG_PTR = ctypes.c_uint64 if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_uint32

_kernel32 = None
_iphlpapi = None


if os.name == "nt":
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


@dataclass
class Civ6LocalState:
    running: bool = False
    processes: dict[int, str] = field(default_factory=dict)
    has_discovery_port: bool = False
    discovery_bind_addr: str = "127.0.0.1"
    has_session_port: bool = False
    session_bind_addr: str = "127.0.0.1"
    candidates: dict[tuple[int, int], UdpEndpoint] = field(default_factory=dict)

    def to_status_dict(self) -> dict:
        return {
            "running": self.running,
            "room_ready": self.has_discovery_port,
            "session_ready": self.has_session_port,
        }

    def human_summary(self) -> str:
        if not self.running:
            return "未运行"
        if self.has_discovery_port and self.has_session_port:
            return "已开房 (62900+62056就绪)"
        if self.has_discovery_port:
            return "已开房 (62900就绪)"
        if self.has_session_port:
            return "运行中 (62056就绪)"
        return "运行中"


def init_windows_api() -> None:
    global _kernel32, _iphlpapi

    if os.name != "nt":
        raise RuntimeError("Windows API 仅支持 Windows 系统。")

    if _kernel32 is not None and _iphlpapi is not None:
        return

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _iphlpapi = ctypes.WinDLL("iphlpapi", use_last_error=True)

    _kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    _kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE

    _kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    _kernel32.Process32FirstW.restype = wintypes.BOOL

    _kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    _kernel32.Process32NextW.restype = wintypes.BOOL

    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.CloseHandle.restype = wintypes.BOOL

    _iphlpapi.GetExtendedUdpTable.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.ULONG),
        wintypes.BOOL,
        wintypes.ULONG,
        wintypes.ULONG,
        wintypes.ULONG,
    ]
    _iphlpapi.GetExtendedUdpTable.restype = wintypes.DWORD


def list_processes() -> dict[int, str]:
    if os.name != "nt":
        return {}
    init_windows_api()

    result: dict[int, str] = {}
    snapshot = _kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    invalid_handle = ctypes.c_void_p(-1).value
    if snapshot == invalid_handle or snapshot is None:
        raise ctypes.WinError(ctypes.get_last_error())

    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        ok = _kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while ok:
            result[int(entry.th32ProcessID)] = str(entry.szExeFile)
            ok = _kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        _kernel32.CloseHandle(snapshot)

    return result


def find_civ6_processes() -> dict[int, str]:
    try:
        processes = list_processes()
    except Exception:
        return {}
    return {
        pid: name
        for pid, name in processes.items()
        if name.lower() in CIV6_PROCESS_NAMES
    }


def _ipv4_from_dword(value: int) -> str:
    return socket.inet_ntoa(struct.pack("<L", int(value) & 0xFFFFFFFF))


def _port_from_dword(value: int) -> int:
    return socket.ntohs(int(value) & 0xFFFF)


def read_udp4_table() -> list[UdpEndpoint]:
    if os.name != "nt":
        return []
    init_windows_api()

    size = wintypes.ULONG(0)
    ret = _iphlpapi.GetExtendedUdpTable(
        None, ctypes.byref(size), False, AF_INET, UDP_TABLE_OWNER_PID, 0
    )
    if ret not in (ERROR_INSUFFICIENT_BUFFER, NO_ERROR):
        raise OSError(f"GetExtendedUdpTable size query failed: ret={ret}")

    buf = ctypes.create_string_buffer(size.value)
    ret = _iphlpapi.GetExtendedUdpTable(
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
                local_addr=_ipv4_from_dword(row.dwLocalAddr),
                local_port=_port_from_dword(row.dwLocalPort),
                pid=int(row.dwOwningPid),
            )
        )
    return endpoints


def is_discovery_candidate(ep: UdpEndpoint) -> bool:
    if ep.local_addr != "0.0.0.0":
        return False
    if ep.local_port in (DISCOVERY_PORT, SESSION_PORT):
        return False
    return WINDOWS_DYNAMIC_PORT_MIN <= ep.local_port <= WINDOWS_DYNAMIC_PORT_MAX


def read_civ6_candidates(civ6_processes: dict[int, str]) -> dict[tuple[int, int], UdpEndpoint]:
    if not civ6_processes:
        return {}
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
        if is_discovery_candidate(named):
            candidates[(named.pid, named.local_port)] = named
    return candidates


def inspect_civ6_state(civ6_processes: dict[int, str] | None = None) -> Civ6LocalState:
    procs = find_civ6_processes() if civ6_processes is None else civ6_processes
    state = Civ6LocalState(running=bool(procs), processes=dict(procs))
    if not procs:
        return state

    try:
        udp = read_udp4_table()
    except Exception:
        return state

    for ep in udp:
        if ep.pid not in procs:
            continue
        named = UdpEndpoint(
            local_addr=ep.local_addr,
            local_port=ep.local_port,
            pid=ep.pid,
            process_name=procs[ep.pid],
        )
        if ep.local_port == DISCOVERY_PORT:
            state.has_discovery_port = True
            state.discovery_bind_addr = "127.0.0.1" if ep.local_addr == "0.0.0.0" else ep.local_addr
        elif ep.local_port == SESSION_PORT:
            state.has_session_port = True
            state.session_bind_addr = "127.0.0.1" if ep.local_addr == "0.0.0.0" else ep.local_addr
        elif is_discovery_candidate(named):
            state.candidates[(named.pid, named.local_port)] = named

    return state


def format_civ6_processes(civ6: dict[int, str]) -> str:
    if not civ6:
        return "none"
    return ", ".join(f"{name}(pid={pid})" for pid, name in sorted(civ6.items()))
