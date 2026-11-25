from __future__ import annotations

import json
import os
import secrets
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .easytier_manager import parse_easytier_peers
from .protocol import DEFAULT_RELAY_PORT, parse_server_address

DEFAULT_EASYTIER_PORT = 11010
VALID_VPS_KINDS = ("easytier", "udp_relay")


@dataclass
class VpsNodeItem:
    id: str
    name: str
    address: str
    kind: str = "easytier"

    def kind_label(self) -> str:
        return "UDP中继" if self.kind == "udp_relay" else "EasyTier"

    def display_label(self) -> str:
        tag = f"{self.name} · {self.kind_label()}" if self.name else self.kind_label()
        return f"{self.address}  [{tag}]"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["kind_label"] = self.kind_label()
        d["label"] = self.display_label()
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


def resolve_relay_input(
    raw_input: str, saved_nodes: list[VpsNodeItem]
) -> tuple[str, str, str]:
    text = str(raw_input).strip()
    if not text:
        raise ValueError("请先添加或输入自建 VPS 节点地址（例如 tcp://你的VPS:11010 或 relay://你的VPS:38668）。")

    for node in saved_nodes:
        if text in (node.id, node.display_label(), node.address):
            return node.kind, node.address, node.name or node.address

    clean = text.split("  [", 1)[0].strip() if "  [" in text else text
    for node in saved_nodes:
        if clean == node.address:
            return node.kind, node.address, node.name or node.address

    low = clean.lower()
    if low.startswith("relay://") or low.startswith("civ6://"):
        norm = normalize_vps_node_address(clean, kind="udp_relay")
        return "udp_relay", norm, norm

    norm = normalize_vps_node_address(clean, kind="easytier")
    return "easytier", norm, norm


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
                        items.append(VpsNodeItem(id=nid, name=name, address=addr, kind=kind))
        except Exception:
            items = []
        self._nodes = items
        return list(self._nodes)

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            data = [
                {"id": n.id, "name": n.name, "address": n.address, "kind": n.kind}
                for n in self._nodes
            ]
            self.path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass

    def list_nodes(self) -> list[VpsNodeItem]:
        return list(self._nodes)

    def add_node(self, name: str, address: str, kind: str = "easytier") -> VpsNodeItem:
        clean_kind = str(kind).strip().lower()
        if clean_kind not in VALID_VPS_KINDS:
            raise ValueError("节点类型必须是 EasyTier 或 UDP 中继")
        norm_addr = normalize_vps_node_address(address, kind=clean_kind)
        clean_name = str(name).strip()[:40]
        if not clean_name:
            host_hint = norm_addr.split(",", 1)[0].strip()
            if "://" in host_hint:
                host_hint = host_hint.split("://", 1)[1]
            clean_name = host_hint[:32]

        for existing in self._nodes:
            if existing.kind == clean_kind and existing.address.lower() == norm_addr.lower():
                existing.name = clean_name
                self._save()
                return existing

        item = VpsNodeItem(
            id=secrets.token_hex(6),
            name=clean_name,
            address=norm_addr,
            kind=clean_kind,
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
