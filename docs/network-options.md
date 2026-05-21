# 组网方案配置参考：蒲公英、ZeroTier、VPS + WireGuard

本文面向 GitHub 技术文档，重点给出三种三层组网方案的配置路径、互通测试方法和排错边界。

目标是让几台不在同一真实局域网里的电脑获得可互通的虚拟网 IPv4，然后配合 Civ6 三层局域网房间发现助手使用。

## 总体要求

无论使用哪种组网方案，都建议满足这些条件：

1. 每台玩家电脑都有一个虚拟网 IPv4；
2. 虚拟网 IPv4 最好落在普通私网段：
   - `10.0.0.0/8`
   - `172.16.0.0/12`
   - `192.168.0.0/16`
3. 双方虚拟网 IP 能互相 `ping` 通；
4. 房主侧允许接收文明 6 的 UDP 流量；
5. 客户端能访问房主虚拟网 IP 的 UDP `62900`；
6. 进入房间后，双方 UDP `62056` 会话流量能互通。

本项目只负责补齐文明 6 的房间发现：

```text
客户端虚拟网 IP:文明6临时端口 -> 房主虚拟网 IP:62900
```

如果虚拟网络本身不通，或者后续 `62056` 被防火墙拦截，本工具无法单独解决。

## 方案一：蒲公英

蒲公英是本文最推荐给普通用户的方案。

原因很简单：

- 客户端和网页后台是中文；
- 不需要自己买 VPS；
- 不需要写 WireGuard 配置；
- 三层组网的小规模免费名额通常够文明 6 小队测试；
- 对不熟悉网络的朋友比较友好。

蒲公英体验版/免费名额的具体规则可能会随官方调整变化。按目前公开资料，蒲公英体验版有 3 个访问端成员数量。实际使用时请以官方页面为准。

### 适合场景

适合：

- 2 到 3 个玩家的小队；
- 参与者不太懂网络；
- 希望尽量少改系统设置；
- 希望用中文客户端完成组网；
- 主要目标就是让文明 6 能跨地区联机。

不太适合：

- 人数很多；
- 需要更高带宽或更多高级功能；
- 想完全掌控中继、路由和服务器配置；
- 已经有 VPS 并熟悉 WireGuard。

### 基本配置步骤

1. 安装蒲公英客户端。
2. 登录同一个贝锐/蒲公英账号，或按官方方式添加访问端成员。
3. 在蒲公英管理后台创建或进入一个异地组网。
4. 把参与文明 6 联机的电脑加入同一个网络。
5. 确认每台电脑都获得了一个蒲公英虚拟 IP。
6. 在每台电脑上测试互通。

假设蒲公英分配了：

```text
客户端 A: 172.16.1.101
房主 B:   172.16.1.102
```

在 A 上测试：

```powershell
ping 172.16.1.102
```

在 B 上测试：

```powershell
ping 172.16.1.101
```

如果双方都能 ping 通，再启动文明 6 和本工具。

### 配合本工具使用

假设客户端 A 搜索房主 B 的房间：

```text
客户端 A: 172.16.1.101
房主 B:   172.16.1.102
```

工具中填写：

```text
本机 IP = 172.16.1.101
房主 IP = 172.16.1.102
```

然后：

1. 房主 B 创建文明 6 局域网房间；
2. 客户端 A 打开本工具并开始监听；
3. 客户端 A 刷新文明 6 局域网房间列表；
4. 如果日志出现 `SEND ok`，说明 discovery 包已经发出。

### 蒲公英排错要点

如果互相 ping 不通：

- 确认双方都在同一个蒲公英网络中；
- 确认蒲公英成员在线；
- 检查是否使用了正确的虚拟 IP；
- 检查 Windows 防火墙是否阻止虚拟网流量；
- 检查蒲公英后台成员权限。

如果能看到房间但进不去：

- 重点检查 Windows 防火墙；
- 重点检查文明 6 后续 `62056` UDP 会话；
- 确认游戏版本、DLC、模组一致；
- 确认房主和客户端都没有被安全软件拦截。

## 方案二：ZeroTier

ZeroTier 适合愿意稍微排错、希望先免费尝试的用户。

如果 ZeroTier 能在双方之间建立直连，效果通常很好。  
如果只能走 relay，中继质量和延迟就不一定适合游戏。本文作者目前没有对 ZeroTier relay 场景下的文明 6 联机效果做充分测试，所以这里只建议把它作为“能直连则优先”的方案。

### 适合场景

适合：

- 想先免费试；
- 玩家能接受网页后台授权；
- 能看懂基本 IP 和 ping 测试；
- 双方网络环境有机会建立直连。

不太适合：

- 完全小白；
- 不想注册英文后台；
- 双方网络很受限，只能走 relay；
- 希望有中文客户端和更直观的后台。

### 基本配置步骤

1. 注册并登录 ZeroTier Central。
2. 创建一个 Network。
3. 记录 Network ID。
4. 建议给网络分配普通私网 IPv4，例如：
   - `10.147.17.0/24`
   - `10.88.66.0/24`
   - `192.168.191.0/24`
5. 每台电脑安装 ZeroTier 客户端。
6. 每台电脑加入同一个 Network ID。
7. 回到 ZeroTier Central，在 Members 页面授权设备。
8. 确认每台电脑获得一个虚拟网 IP。

Windows 命令行加入网络：

```powershell
zerotier-cli join <你的Network ID>
```

查看节点和连接状态：

```powershell
zerotier-cli peers
```

如果两个玩家之间显示 `DIRECT`，说明双方之间是直连。  
如果显示 `RELAY`，说明流量在走中继。中继能不能流畅玩文明 6，需要按实际延迟和丢包测试。

### 测试互通

假设：

```text
客户端 A: 10.147.17.2
房主 B:   10.147.17.3
```

在 A 上：

```powershell
ping 10.147.17.3
```

在 B 上：

```powershell
ping 10.147.17.2
```

如果 ping 不通，先检查：

- ZeroTier 客户端是否在线；
- 网页后台是否授权；
- 是否加入同一个 Network ID；
- ZeroTier IP 是否与本机其他网段冲突；
- Windows 防火墙是否阻止 ZeroTier 虚拟网。

### 配合本工具使用

客户端 A 填：

```text
本机 IP = 10.147.17.2
房主 IP = 10.147.17.3
```

之后由房主创建文明 6 局域网房间，客户端打开工具并刷新局域网列表。

### ZeroTier 注意点

- ZeroTier 是三层虚拟网络，不会自动解决文明 6 局域网广播；
- 所以仍然需要本项目这种 discovery helper；
- 能直连时更适合游戏；
- relay 场景本文没有充分测试，不建议作为首选稳定方案；
- 建议使用普通私网 IPv4；
- 不建议使用与本地 Wi-Fi、校园网、公司网冲突的网段；
- 同一个 ZeroTier Network 内成员互通通常不需要额外配置 Managed Routes；
- Managed Routes 更常用于“通过某个节点访问它背后的物理局域网”。

## 方案三：VPS + WireGuard

VPS + WireGuard 是最可控的方案，但也最不适合小白。

会配 VPS 的用户通常已经知道如何开放端口、写配置、查路由和看防火墙。因此本文只给最小配置框架，不展开完整保姆教程。

### 适合场景

适合：

- 已经有 VPS；
- 熟悉 Linux；
- 知道云厂商安全组怎么放行端口；
- 想自己控制虚拟网段；
- 想让所有玩家经固定 VPS 中继互通。

不太适合：

- 完全小白；
- 只想临时玩一局；
- 不想维护服务器；
- 不知道如何排查 Linux 防火墙和转发规则。

### 服务端最小配置框架

以 Ubuntu VPS 为例。

安装：

```bash
sudo apt update
sudo apt install wireguard -y
```

开启 IPv4 转发：

```bash
sudo sysctl -w net.ipv4.ip_forward=1
```

持久化可写入 `/etc/sysctl.conf`：

```conf
net.ipv4.ip_forward=1
```

服务端 `/etc/wireguard/wg0.conf` 示例：

```ini
[Interface]
Address = 10.88.66.1/24
ListenPort = 51820
PrivateKey = SERVER_PRIVATE_KEY_HERE

PostUp = iptables -A FORWARD -i %i -o %i -s 10.88.66.0/24 -d 10.88.66.0/24 -j ACCEPT
PostDown = iptables -D FORWARD -i %i -o %i -s 10.88.66.0/24 -d 10.88.66.0/24 -j ACCEPT

[Peer]
# client-a
PublicKey = CLIENT_A_PUBLIC_KEY_HERE
AllowedIPs = 10.88.66.2/32

[Peer]
# client-b
PublicKey = CLIENT_B_PUBLIC_KEY_HERE
AllowedIPs = 10.88.66.3/32
```

启动：

```bash
sudo systemctl enable wg-quick@wg0
sudo systemctl start wg-quick@wg0
sudo wg
```

同时需要在云厂商安全组中放行 UDP `51820`。

### Windows 客户端配置框架

客户端 A：

```ini
[Interface]
PrivateKey = CLIENT_A_PRIVATE_KEY_HERE
Address = 10.88.66.2/32

[Peer]
PublicKey = SERVER_PUBLIC_KEY_HERE
Endpoint = VPS_PUBLIC_IP:51820
AllowedIPs = 10.88.66.0/24
PersistentKeepalive = 25
```

客户端 B：

```ini
[Interface]
PrivateKey = CLIENT_B_PRIVATE_KEY_HERE
Address = 10.88.66.3/32

[Peer]
PublicKey = SERVER_PUBLIC_KEY_HERE
Endpoint = VPS_PUBLIC_IP:51820
AllowedIPs = 10.88.66.0/24
PersistentKeepalive = 25
```

### 测试互通

A 上：

```powershell
ping 10.88.66.1
ping 10.88.66.3
```

B 上：

```powershell
ping 10.88.66.1
ping 10.88.66.2
```

如果 A/B 都能 ping 通 VPS，但 A/B 互相 ping 不通，优先检查：

- VPS 是否开启 IPv4 转发；
- `FORWARD` 规则是否正确；
- 云厂商安全组是否影响 UDP；
- 客户端 `AllowedIPs` 是否包含 `10.88.66.0/24`；
- Windows 防火墙是否阻止 WireGuard 网卡流量。

### 配合本工具使用

客户端 A 搜索房主 B：

```text
本机 IP = 10.88.66.2
房主 IP = 10.88.66.3
```

### WireGuard 注意点

- `AllowedIPs = 10.88.66.0/24` 只让 WireGuard 小网走隧道；
- 不要随手写 `0.0.0.0/0`，否则可能把全部流量都导到 VPS；
- WireGuard 网段不要和家庭 Wi-Fi、校园网、公司网冲突；
- 如果能看到房间但进不去，重点排查 `62056` 和 Windows 防火墙；
- VPS 所在地区和线路会影响延迟、丢包和游戏体验。

## 推荐顺序

对于本项目的目标用户，建议顺序是：

```text
蒲公英 -> ZeroTier -> VPS + WireGuard
```

理由：

1. 蒲公英对小白更友好，3 用户免费名额通常够小队测试；
2. ZeroTier 免费试错成本低，直连时效果好，但 relay 场景稳定性需要实测；
3. VPS + WireGuard 最可控，但面向已经会配服务器的用户，不适合作为普通玩家第一选择。

## 和本工具的关系

组网方案负责：

```text
让玩家之间的虚拟网 IP 互通
```

本工具负责：

```text
让文明 6 的房间发现包到达房主
```

后续能不能顺利进入房间，还取决于：

- `62056` UDP 会话；
- Windows 防火墙；
- 虚拟网络是否允许双方互通；
- 游戏版本、DLC、模组；
- 房主和客户端的实际网络质量。
