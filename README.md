# Civ6 L3 Discovery Helper

一个简单的 Civilization VI 局域网房间发现辅助工具。

适用于 WireGuard、蒲公英等三层虚拟网络场景。  
它会在搜索端监听 Civ6 新建的 UDP 临时端口，并从该端口向房主的 `62900` 端口发送 Civ6 LAN discovery payload。

## 特性

- Windows only
- 简单 GUI
- 搜索端运行即可
- 无需管理员权限
- 无需 WinDivert
- 无需房主端运行 helper
- 无第三方 Python 依赖

## 下载与使用

### 方式一：直接下载 exe，推荐萌新使用

进入右侧或页面上方的 **Releases**，下载：

```text
Civ6L3DiscoveryHelper.exe
```

然后双击运行即可，不需要安装 Python。

使用步骤：

1. 启动 Civilization VI。
2. 运行 `Civ6L3DiscoveryHelper.exe`。
3. 填写：
   - **本机 IP**：本机在 WireGuard / 蒲公英等虚拟网卡上的 IP
   - **房主 IP**：房主在同一虚拟网络中的 IP
4. 点击 **开始监听**。
5. 进入或刷新 Civ6 局域网房间列表。

### 方式二：运行源码，适合不放心 exe 的用户

如果你不想运行未签名 exe，也可以直接运行源码版本。

需要先安装 Python 3，然后在项目目录中运行：

```powershell
python civ6_l3_discovery_gui.py
```

源码版本和 exe 版本功能一致。

## Windows SmartScreen 提示

由于 exe 是个人构建的未签名程序，Windows 可能会提示：

```text
Microsoft Defender SmartScreen 阻止了无法识别的应用启动
发布者：未知
```

这是个人开源小工具常见情况。  
如果你不放心，可以不要运行 exe，改用上面的源码方式运行：

```powershell
python civ6_l3_discovery_gui.py
```

## 原理

Civilization VI 的局域网房间发现依赖 UDP discovery。  
普通三层 VPN 通常不会转发局域网广播，因此搜索端可能看不到房主。

本工具在搜索端检测 Civ6 新建的高位 UDP 临时端口，然后从该端口向房主的 `62900` 端口发送 discovery payload：

```text
8d e8 fc 70
```

房主端 Civ6 收到后会按正常流程返回房间信息。

## 注意事项

本工具只辅助 Civilization VI 在三层虚拟网络上的 LAN 房间发现。

实际进入房间和游戏会话仍要求：

- 双方三层 IP 可达；
- 防火墙允许 Civ6 流量；
- WireGuard / 蒲公英 / 路由规则配置正确；
- 游戏会话端口能够正常互通。

本工具不负责 VPN、路由表、防火墙规则的自动配置。

## License

MIT