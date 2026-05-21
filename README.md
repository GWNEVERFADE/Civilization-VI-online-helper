# Civ6 L3 Discovery Helper

一个简单的 Civilization VI 局域网房间发现辅助工具。

适用于 WireGuard、蒲公英等三层虚拟网络场景。  
它会在搜索端监听 Civ6 新建的 UDP 临时端口，并从该端口向房主的 62900 端口发送 Civ6 LAN discovery payload。

## 特性

- Windows only
- 无需管理员权限
- 无需 WinDivert
- 无需房主端运行 helper
- 无第三方 Python 依赖
- 简单 GUI，只需要填写本机虚拟网卡 IP 和房主 IP

## 使用方法

1. 安装 Python 3。
2. 启动 Civilization VI。
3. 运行：

```powershell
python civ6_l3_discovery_gui.py