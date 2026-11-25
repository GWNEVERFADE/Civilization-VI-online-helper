# Civilization-VI-online-helper

**CV6 online helper** — Tired of desyncs, high ping, and LAN lobbies that never show up? This tool fixes the weak-network headaches that plague Civilization VI multiplayer.

- **One-click custom VPS relay nodes** — EasyTier (`--no-tun`) & lightweight UDP relay (`civ6_relay_server.py`), no port forwarding or public IP required
- **IPv6 / P2P direct connection** — Dual-stack IPv6/IPv4 with STUN probe & bidirectional UDP hole-punching for lowest latency
- **Zero-privilege, driver-free Civ VI LAN bridge** — No admin rights, no virtual NIC driver, no game process injection, supports mid-game disconnect & rejoin
- **Bilingual (中文 / English) Soft-Glow Glass UI** — Light & Dark frosted glass themes with built-in interactive P2P & VPS setup guides

---

## Features / 核心特性

1. **Mode 1 · IPv6 / P2P Direct（方式一 · IPv6 / P2P 直连）**
   - Supports direct public IPv6, STUN public IPv4 mapping probe, and bidirectional UDP hole-punching.
   - Share `c6p2://` invite codes to connect without any relay server.
2. **Mode 2 · Custom VPS Relay（方式二 · 自定义 VPS 中继）**
   - Add and persist your own custom VPS nodes:
     - **EasyTier VPS (`11010`)**: Embedded `easytier-core --no-tun` attempts P2P hole-punching first and falls back to your VPS automatically.
     - **Lightweight UDP Relay (`38668`)**: Run `python3 civ6_relay_server.py --port 38668` on any VPS with zero third-party dependencies.
   - Supports mid-game disconnect and hot-rejoin into ongoing sessions.
3. **Strict Two-Step Workflow（严格两步式联机流程）**
   - **Step 1 · Connect & Verify**: Start local node, connect via P2P or custom VPS relay, and run the connectivity & 1150B MTU test (2+ players online required).
   - **Step 2 · Civ VI Helper**: Host creates a Civ VI Local Network lobby and starts Host Bridge; Clients start Client Helper (with optional 62900 room probe) and refresh Civ VI → Multiplayer → Local Network.

---

## Quick Start / 快速开始

### Run from Source / 源码运行

```powershell
# Install GUI dependency (falls back to Tkinter if pywebview is unavailable)
pip install pywebview

# Launch CV6 online helper
python civ6_p2p_helper.py
```

### Build Windows Executable / 打包单文件 EXE

```powershell
pip install pyinstaller pywebview pillow
pyinstaller --noconfirm --clean "CV6 online helper.spec"
```

### Run Unit Tests / 运行单元测试

```powershell
python -m unittest discover -s tests -v
```

### Self-Hosted VPS Deployment / 自建 VPS 中继部署

- **EasyTier VPS (`TCP / UDP 11010`)**:
  ```bash
  docker run -d --name easytier --restart always --network host easytier/easytier:latest --no-tun -l tcp://0.0.0.0:11010 -l udp://0.0.0.0:11010
  ```
- **Lightweight UDP Relay (`UDP 38668`)**:
  ```bash
  python3 civ6_relay_server.py --port 38668
  ```

---

## Documentation / 更多文档

- [详细中文说明 (README_P2P.md)](README_P2P.md)
- [组网方案参考 (docs/network-options.md)](docs/network-options.md)
- [进阶原理说明 (docs/advanced.md)](docs/advanced.md)

## Acknowledgements & License / 致谢与协议

Built upon [Frwere/civ6-l3-discovery-helper](https://github.com/Frwere/civ6-l3-discovery-helper) and inspired by [xaxys/injciv6](https://github.com/xaxys/injciv6).

Licensed under the [MIT License](LICENSE).
