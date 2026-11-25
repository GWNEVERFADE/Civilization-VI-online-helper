(() => {
  "use strict";

  const I18N = {
    zh: {
      brandEdition: "IPv6 · VPS 中继",
      brandSub: "第一步：IPv6/P2P 或 VPS 中继联通 → 第二步：文明6 联机辅助",
      checking: "检测中...",
      badgeNode: "节点",
      notStarted: "未启动",
      badgeOnline: "在线",
      badgeCiv6: "文明6",
      notRunning: "未运行",
      langToggleTitle: "切换中英文 / Switch Language",
      themeToggleTitle: "切换柔光晨曦 / 柔光暮夜材质",
      themeLight: "晨曦",
      themeDark: "暮夜",
      step1Title: "第一步 · 联机联通",
      step1Sub: "IPv6/P2P 直连 · 自定义 VPS 中继",
      step2Title: "第二步 · 文明6 联机辅助",
      step2LockedSub: "🔒 待第一步连通解锁",
      step2UnlockedSub: (n) => `✅ 在线 ${n} 人 · 已解锁`,
      step2LockedChip: "未解锁",
      step2UnlockedChip: (n) => `在线 ${n} 人`,
      onlineCount: (n) => `${n} 人`,
      nodeRunning: (p) => `运行中 :${p}`,
      ipv6Ready: "公网就绪",
      ipv6None: "无公网",
      card1Title: "本机联机节点",
      btnStartNode: "启动节点",
      btnStop: "停止",
      lblRole: "角色",
      roleHost: "房主",
      roleClient: "加入者",
      lblNickname: "昵称",
      phNickname: "输入游戏昵称",
      lblPort: "UDP 端口",
      lblRoomKey: "房间口令",
      phRoomKey: "双方填写相同口令",
      card2Title: "联机方式",
      btnGuideP2P: "P2P 使用说明",
      btnGuideVPS: "VPS 使用说明",
      modeP2P: "方式一 · IPv6 / P2P 直连",
      modeRelay: "方式二 · 自定义 VPS 中继",
      lblAdvAddr: "本机对外地址",
      phAdvAddr: "选择或输入本机 IPv6 / IPv4 地址",
      btnRefreshNet: "刷新地址",
      btnStun: "STUN 公网检测",
      btnStunBusy: "STUN 检测中...",
      lblInviteCode: "我的连接码",
      btnCopyInvite: "复制我的连接码",
      lblPeerAddr: "对方连接码 / IP",
      phPeerAddr: "粘贴好友的 c6p2:// 连接码，或输入 [IPv6]:端口 / IPv4:端口",
      btnAddPeer: "添加并连接 / 打洞",
      lblVpsNode: "自定义 VPS 节点",
      phVpsNode: "点击「+ 添加 VPS」或输入 tcp://你的VPS:11010",
      btnAddVps: "+ 添加 VPS",
      titleAddVps: "添加并保存自定义 VPS 节点",
      lblRoomName: "房间名",
      lblVpsPassword: "连接密码（选填）",
      phVpsPassword: "无密码留空",
      togglePwTitle: "显示 / 隐藏密码",
      btnConnectVps: "连接 VPS 房间",
      btnConnectVpsBusy: "正在连接 VPS...",
      btnDisconnect: "断开",
      card3Title: "在线成员与连通测试",
      card3Sub: "至少 2 人在线且测试通过后解锁第二步",
      btnTestPeer: "测试选中连接",
      btnTestPeerBusy: "测试中...",
      btnRemovePeer: "移除选中",
      thNick: "昵称",
      thRole: "角色",
      thTransport: "连接方式",
      thEndpoint: "对方地址 / 节点",
      thStatus: "在线状态",
      thRtt: "延迟",
      thLoss: "丢包",
      thCiv6: "对方文明6",
      thTest: "连通测试",
      thFakeIp: "虚拟IP",
      peerEmpty: "暂无联机成员 · 启动节点后通过上方「IPv6/P2P 直连」或「自定义 VPS 中继」添加好友",
      btnGotoStep2: "进入第二步 · 文明6 联机辅助",
      s2Card1Title: "联机状态检查",
      s2Card1Sub: "需至少 2 人在线且连通测试通过",
      pfLocalNode: "本机节点",
      pfOnlineTest: "在线与测试",
      pfLocalCiv6: "本机文明6",
      pfRemoteCiv6: "对端文明6",
      s2Card2Title: "文明6 联机辅助控制",
      hostModeDesc: "当前角色：房主。在文明6创建「局域网」房间后，点「启动房主联机桥接」即可服务所有在线好友（至少 2 人在线方可开启）。",
      clientModeDesc: "当前角色：加入者。选择已连通测试通过的房主节点并启动辅助后，回文明6「多人游戏 → 局域网」刷新即可看到房间并直接加入。",
      lblCurrentMode: "当前模式",
      lblTargetHost: "目标房主节点",
      hostModeOption: "房主模式（自动服务所有已在线好友）",
      noVerifiedHost: "暂无已通过测试的在线房主",
      btnStartHostBridge: "启动房主联机桥接",
      btnStartClientBridge: "启动加入者联机辅助",
      btnStopBridge: "停止辅助",
      btnProbeRoom: "探测房主文明6房间",
      btnProbeRoomBusy: "正在探测房间...",
      s2Card3Title: "实时联机流量与诊断",
      teleDisc: "62900 房间发现",
      teleTx: "62056 会话发送",
      teleRx: "62056 会话接收",
      statDiscFmt: (req, resp) => `请求 ${req} / 回包 ${resp}`,
      statPktFmt: (pkts, bytes) => `${pkts} 包 (${bytes})`,
      activityTag: "状态",
      s2Tips: "使用要点：① 房主在文明6创建「局域网」房间并点「启动房主联机桥接」；② 加入者选择已通过测试的房主并点「启动加入者联机辅助」；③ 可先点「探测房主文明6房间」确认收到房间信息，再切回文明6局域网刷新加入。",
      logTitle: "运行日志",
      btnCollapse: "收起",
      btnExpand: "展开",
      btnCopyLog: "复制日志",
      btnClearLog: "清空",
      btnGotIt: "我知道了",
      btnOk: "确定",
      btnCancel: "取消",
      btnSaveSelect: "保存并选中",
      modalDefaultTitle: "提示",
      apiErrorTitle: "调用异常",
      vpsModalTitle: "添加自定义 VPS 节点",
      vpsKindLabel: "中继节点类型",
      vpsKindET: "EasyTier VPS (11010)",
      vpsKindUDP: "轻量 UDP 中继 (38668)",
      vpsNameLabel: "节点备注名（选填）",
      phVpsName: "例如：香港轻量 VPS / 东京自建节点",
      vpsAddrLabel: "VPS 节点地址",
      phVpsAddrET: "tcp://1.2.3.4:11010 或 udp://vps.example.com:11010",
      phVpsAddrUDP: "1.2.3.4:38668 或 relay.example.com:38668 或 [240e::1]:38668",
      hintVpsET: "支持 <code>tcp://ip:11010</code>、<code>udp://ip:11010</code>、<code>ip:11010</code>，或多个备用 VPS 用逗号分隔；未填端口默认 11010。",
      hintVpsUDP: "适配 <code>civ6_relay_server.py</code> 轻量 UDP 中继，支持 IPv4 / IPv6 / 域名，未填端口默认 38668。",
      vpsPwLabel: "VPS 连接密码（选填）",
      phVpsModalPw: "无密码留空",
      hintVpsPwET: "若 VPS 启用了 <code>--private-mode</code> / <code>--network-secret</code> 密码保护请填写；留空默认使用上方房间口令。",
      hintVpsPwUDP: "若 <code>civ6_relay_server.py</code> 启动时设置了 <code>--password</code> 请填写；无密码留空即可。",
      vpsLockBadge: "密码",
      vpsEmptyDrop: "尚未保存自定义 VPS 节点，请先添加您的自建节点",
      vpsEmptyDropBtn: "+ 立即添加 VPS 节点",
      vpsDeleteTitle: "删除该自定义 VPS 节点",
      vpsInvalidAddr: "请输入有效的 VPS 节点地址",
      guideTitleP2P: "P2P 直连使用说明",
      guideTitleVPS: "VPS 中继使用说明",
      toastStep2Locked: "请先完成第一步连接测试并确保至少 2 人在线",
      toastStep2Relocked: "在线人数不足 2 人或尚未测试通过，第二步已重新锁定",
      toastNodeStarted: (p) => `节点已启动，监听 UDP :${p}`,
      toastNodeStopped: "已停止本机节点",
      toastInviteCopied: "已复制本机连接码到剪贴板",
      toastStunRunning: "正在执行 STUN 公网地址检测...",
      toastPeerEmpty: "请输入或粘贴对方的连接码 / IP 地址",
      toastPeerAdded: (k) => `已添加节点 ${k}，正在发起连接...`,
      toastVpsEmpty: "请先添加或输入自建 VPS 节点地址",
      toastVpsConnecting: "正在连接自定义 VPS 中继通道...",
      toastVpsDisconnected: "已断开 VPS 中继连接",
      toastVpsSaved: (n) => `已保存 VPS 节点：${n}`,
      toastVpsDeleted: (n) => `已删除 VPS 节点：${n}`,
      toastTestRunning: "正在执行连通与 1150B 大包测试...",
      toastRemoveNeedSel: "请先在成员列表中选中要移除的节点",
      toastHostBridgeStarted: "房主文明6联机桥接已启动",
      toastClientBridgeStarted: "加入者文明6联机辅助已启动",
      toastBridgeStopped: "已停止文明6联机辅助",
      toastProbingRoom: "正在探测房主文明6房间...",
      toastNetRefreshed: "已刷新本机网络地址",
      toastLogCopied: "已复制运行日志到剪贴板",
      toastCmdCopied: "已复制部署命令到剪贴板",
      keyMismatchTitle: "房间口令不一致",
      keyMismatchMsg: (r, l) => `对方连接码口令为「${r}」，与本机「${l}」不同。\n\n是否重启本机节点以同步口令？`,
      keyMismatchConfirm: "重启并同步口令",
      testPassedTitle: "第一步连接测试成功",
      testPassedMsg: (k, s, n) =>
        `已与 ${k} 连通测试通过！\n\n测试结果：${s}\n当前在线人数：${n} 人（满足 ≥ 2 人要求）\n\n「第二步 · 文明6 联机辅助」已解锁，是否立即进入？`,
      testPassedConfirm: "立即进入第二步",
      testPassedCancel: "稍后",
      guideCopyBtn: "复制",
      guideP2PHtml: `
        <div class="guide-callout">
          <strong>适用场景：</strong>零服务器成本、延迟最低。适合双方（或房主端）拥有公网 IPv6，或处于普通家庭宽带（Cone NAT）可 UDP 打洞的网络环境。
        </div>
        <div class="guide-block">
          <h4 class="guide-h4">快速联机步骤</h4>
          <ol class="guide-steps">
            <li><strong>配置身份并启动节点：</strong>房主在顶部选「房主」、好友选「加入者」，填写昵称与<strong>相同的房间口令</strong>（默认端口 <code>38666</code>），点击 <strong>启动节点</strong>。</li>
            <li><strong>选择对外地址：</strong>顶部显示「IPv6 公网就绪」时，在「本机对外地址」优先选择 <code>[首选公网 IPv6]</code>；若没有公网 IPv6，可点击 <strong>STUN 公网检测</strong> 探测公网 IPv4 映射端口。</li>
            <li><strong>互换连接码并打洞：</strong>点击 <strong>复制我的连接码</strong> 发给好友；双方都在「对方连接码 / IP」中粘贴对方连接码并点击 <strong>添加并连接 / 打洞</strong>（双方互填可同时双向打洞，穿透率更高）。</li>
            <li><strong>连通测试解锁第二步：</strong>成员列表变为「在线」且在线人数 ≥ 2 后，选中好友点击 <strong>测试选中连接</strong>（校验延迟与 1150B 大包），通过后自动解锁 <strong>第二步 · 文明6 联机辅助</strong>。</li>
          </ol>
        </div>
        <div class="guide-block">
          <h4 class="guide-h4">常见问题排查</h4>
          <ul class="guide-list">
            <li><strong>一直显示「打洞连接中」：</strong>核对双方「房间口令」完全一致、双方均已添加对方地址，并在 Windows 防火墙弹窗中放行本程序 UDP 访问。</li>
            <li><strong>仍无法直连：</strong>若双方均为对称 NAT、移动数据热点、校园网或严格企业网且无公网 IPv6，请切换至 <strong>方式二 · 自定义 VPS 中继</strong>。</li>
          </ul>
        </div>
      `,
      guideVPSHtml: `
        <div class="guide-callout">
          <strong>适用场景：</strong>无公网 IPv6、对称 NAT、校园网或跨运营商直连丢包严重时，通过自建云服务器（VPS）自动中继或辅助打洞，无需互换 IP 即可同房互见。
        </div>
        <div class="guide-block">
          <h4 class="guide-h4">方案一 · EasyTier 自建 VPS 节点（推荐，默认端口 11010）</h4>
          <p class="guide-desc">客户端已内置 EasyTier 无虚拟网卡核心，会优先尝试 P2P 打洞，打洞不通自动经 VPS 中继。请先在云服务器安全组与系统防火墙放行 <code>TCP / UDP 11010</code>。</p>
          <div class="guide-cmd-box">
            <div class="guide-cmd-label">Linux / VPS 启动命令（已下载 easytier-core）</div>
            <div class="guide-cmd-row">
              <code class="guide-cmd-code">./easytier-core --no-tun -l tcp://0.0.0.0:11010 -l udp://0.0.0.0:11010</code>
              <button class="glass-btn btn-xs btn-soft light-interactive guide-copy-btn" type="button" data-copy="./easytier-core --no-tun -l tcp://0.0.0.0:11010 -l udp://0.0.0.0:11010">复制</button>
            </div>
          </div>
          <div class="guide-cmd-box">
            <div class="guide-cmd-label">Docker 一键部署命令（带密码保护可选加 --network-name civ6-room --network-secret 你的密码 --private-mode true）</div>
            <div class="guide-cmd-row">
              <code class="guide-cmd-code">docker run -d --name easytier --restart always --network host easytier/easytier:latest --no-tun -l tcp://0.0.0.0:11010 -l udp://0.0.0.0:11010</code>
              <button class="glass-btn btn-xs btn-soft light-interactive guide-copy-btn" type="button" data-copy="docker run -d --name easytier --restart always --network host easytier/easytier:latest --no-tun -l tcp://0.0.0.0:11010 -l udp://0.0.0.0:11010">复制</button>
            </div>
          </div>
          <p class="guide-desc">部署后点击 <strong>+ 添加 VPS</strong> → 类型选 <code>EasyTier VPS (11010)</code> → 地址填写 <code>tcp://你的VPS公网IP:11010</code>；若 VPS 启用了私有密码，将「房间名」设为与 <code>--network-name</code> 一致，并在「连接密码（选填）」中填入 <code>--network-secret</code>。</p>
        </div>
        <div class="guide-block">
          <h4 class="guide-h4">方案二 · 轻量 UDP 中继（civ6_relay_server，默认端口 38668）</h4>
          <p class="guide-desc">零第三方依赖，仅需 Python 3 即可在 VPS 运行，同时支持 IPv4 / IPv6 客户端混合接入。请在云服务器安全组放行 <code>UDP 38668</code>。</p>
          <div class="guide-cmd-box">
            <div class="guide-cmd-label">上传 civ6_relay_server.py 与 civ6_p2p 目录到 VPS 后运行（可选 --password 启用密码认证）</div>
            <div class="guide-cmd-row">
              <code class="guide-cmd-code">python3 civ6_relay_server.py --port 38668 --password 你的密码</code>
              <button class="glass-btn btn-xs btn-soft light-interactive guide-copy-btn" type="button" data-copy="python3 civ6_relay_server.py --port 38668 --password 你的密码">复制</button>
            </div>
          </div>
          <p class="guide-desc">无密码可省略 <code>--password</code>。部署后点击 <strong>+ 添加 VPS</strong> → 选 <code>轻量 UDP 中继 (38668)</code> → 填 <code>你的VPS公网IP:38668</code> 与可选密码。</p>
        </div>
        <div class="guide-block">
          <h4 class="guide-h4">客户端连接步骤</h4>
          <ol class="guide-steps">
            <li>房主在顶部选「房主」、好友选「加入者」，填写<strong>相同的「房间口令」</strong>。</li>
            <li>在「方式二 · 自定义 VPS 中继」中选中同一自建 VPS 节点并填写<strong>相同的「房间名」</strong>，点击 <strong>连接 VPS 房间</strong>。</li>
            <li>待成员列表出现好友并显示「在线」后，点击 <strong>测试选中连接</strong>，测试通过即可进入第二步开启文明 6 联机辅助。</li>
          </ol>
        </div>
      `,
    },
    en: {
      brandEdition: "IPv6 · VPS Relay",
      brandSub: "Step 1: P2P or VPS Relay → Step 2: Civ VI LAN Helper",
      checking: "Checking...",
      badgeNode: "Node",
      notStarted: "Stopped",
      badgeOnline: "Online",
      badgeCiv6: "Civ VI",
      notRunning: "Not Running",
      langToggleTitle: "Switch to Chinese / 切换中文",
      themeToggleTitle: "Toggle Light / Dark Soft-Glow Glass",
      themeLight: "Light",
      themeDark: "Dark",
      step1Title: "Step 1 · Connect & Verify",
      step1Sub: "IPv6/P2P Direct · Custom VPS Relay",
      step2Title: "Step 2 · Civ VI Helper",
      step2LockedSub: "🔒 Locked until Step 1 verified",
      step2UnlockedSub: (n) => `✅ ${n} Online · Unlocked`,
      step2LockedChip: "Locked",
      step2UnlockedChip: (n) => `${n} Online`,
      onlineCount: (n) => `${n}`,
      nodeRunning: (p) => `Running :${p}`,
      ipv6Ready: "Public Ready",
      ipv6None: "No Public",
      card1Title: "Local Node",
      btnStartNode: "Start Node",
      btnStop: "Stop",
      lblRole: "Role",
      roleHost: "Host",
      roleClient: "Client",
      lblNickname: "Nickname",
      phNickname: "Enter player nickname",
      lblPort: "UDP Port",
      lblRoomKey: "Room Key",
      phRoomKey: "Shared room secret",
      card2Title: "Connection Mode",
      btnGuideP2P: "P2P Guide",
      btnGuideVPS: "VPS Guide",
      modeP2P: "Mode 1 · IPv6 / P2P Direct",
      modeRelay: "Mode 2 · Custom VPS Relay",
      lblAdvAddr: "Public Address",
      phAdvAddr: "Select or enter local IPv6 / IPv4 address",
      btnRefreshNet: "Refresh",
      btnStun: "STUN Probe",
      btnStunBusy: "Probing...",
      lblInviteCode: "My Invite Code",
      btnCopyInvite: "Copy Code",
      lblPeerAddr: "Peer Code / IP",
      phPeerAddr: "Paste friend's c6p2:// code, or [IPv6]:port / IPv4:port",
      btnAddPeer: "Add & Connect",
      lblVpsNode: "Custom VPS Node",
      phVpsNode: "Click \"+ Add VPS\" or enter tcp://your-vps:11010",
      btnAddVps: "+ Add VPS",
      titleAddVps: "Add and save a custom VPS relay node",
      lblRoomName: "Room Name",
      lblVpsPassword: "Password (Opt.)",
      phVpsPassword: "Optional",
      togglePwTitle: "Show / Hide Password",
      btnConnectVps: "Connect VPS",
      btnConnectVpsBusy: "Connecting...",
      btnDisconnect: "Disconnect",
      card3Title: "Online Peers & Connectivity Test",
      card3Sub: "2+ online & verified to unlock Step 2",
      btnTestPeer: "Test Selected",
      btnTestPeerBusy: "Testing...",
      btnRemovePeer: "Remove",
      thNick: "Nickname",
      thRole: "Role",
      thTransport: "Transport",
      thEndpoint: "Endpoint / Node",
      thStatus: "Status",
      thRtt: "RTT",
      thLoss: "Loss",
      thCiv6: "Remote Civ VI",
      thTest: "Test Result",
      thFakeIp: "Virtual IP",
      peerEmpty: "No peers yet · Start your node and connect via IPv6/P2P Direct or Custom VPS Relay above",
      btnGotoStep2: "Proceed to Step 2 · Civ VI Helper",
      s2Card1Title: "Pre-flight Status Check",
      s2Card1Sub: "Requires 2+ online & verified connection",
      pfLocalNode: "Local Node",
      pfOnlineTest: "Online & Test",
      pfLocalCiv6: "Local Civ VI",
      pfRemoteCiv6: "Remote Civ VI",
      s2Card2Title: "Civ VI Multiplayer Helper Controls",
      hostModeDesc: "Role: Host. Create a Local Network lobby in Civ VI, then click \"Start Host Bridge\" to serve all online friends (2+ online required).",
      clientModeDesc: "Role: Client. Pick a verified Host peer and start the helper, then refresh Civ VI → Multiplayer → Local Network to see and join the lobby.",
      lblCurrentMode: "Current Mode",
      lblTargetHost: "Target Host Peer",
      hostModeOption: "Host Mode (automatically serves all online friends)",
      noVerifiedHost: "No verified online Host available",
      btnStartHostBridge: "Start Host Bridge",
      btnStartClientBridge: "Start Client Helper",
      btnStopBridge: "Stop Helper",
      btnProbeRoom: "Probe Host Lobby",
      btnProbeRoomBusy: "Probing Lobby...",
      s2Card3Title: "Live Traffic & Diagnostics",
      teleDisc: "62900 Discovery",
      teleTx: "62056 Session TX",
      teleRx: "62056 Session RX",
      statDiscFmt: (req, resp) => `Req ${req} / Resp ${resp}`,
      statPktFmt: (pkts, bytes) => `${pkts} pkts (${bytes})`,
      activityTag: "Status",
      s2Tips: "Quick Tips: 1) Host creates a Local Network lobby in Civ VI and clicks \"Start Host Bridge\"; 2) Clients choose the verified Host and click \"Start Client Helper\"; 3) Click \"Probe Host Lobby\" to confirm room info, then refresh Civ VI LAN list to join.",
      logTitle: "Runtime Log",
      btnCollapse: "Collapse",
      btnExpand: "Expand",
      btnCopyLog: "Copy Log",
      btnClearLog: "Clear",
      btnGotIt: "Got It",
      btnOk: "OK",
      btnCancel: "Cancel",
      btnSaveSelect: "Save & Select",
      modalDefaultTitle: "Notice",
      apiErrorTitle: "API Error",
      vpsModalTitle: "Add Custom VPS Node",
      vpsKindLabel: "Relay Protocol Type",
      vpsKindET: "EasyTier VPS (11010)",
      vpsKindUDP: "Lightweight UDP Relay (38668)",
      vpsNameLabel: "Node Remark (Optional)",
      phVpsName: "e.g. Tokyo VPS / Frankfurt Node",
      vpsAddrLabel: "VPS Node Address",
      phVpsAddrET: "tcp://1.2.3.4:11010 or udp://vps.example.com:11010",
      phVpsAddrUDP: "1.2.3.4:38668 or relay.example.com:38668 or [240e::1]:38668",
      hintVpsET: "Supports <code>tcp://ip:11010</code>, <code>udp://ip:11010</code>, <code>ip:11010</code>, or comma-separated nodes. Default port is 11010.",
      hintVpsUDP: "For <code>civ6_relay_server.py</code> lightweight UDP relay. Supports IPv4, IPv6, and domains. Default port is 38668.",
      vpsPwLabel: "VPS Password (Optional)",
      phVpsModalPw: "Leave blank if no password",
      hintVpsPwET: "Enter if your VPS uses <code>--private-mode</code> / <code>--network-secret</code>; leave blank to use Room Key.",
      hintVpsPwUDP: "Enter if <code>civ6_relay_server.py</code> uses <code>--password</code>; leave blank if none.",
      vpsLockBadge: "Auth",
      vpsEmptyDrop: "No custom VPS nodes saved yet. Add your own VPS node first.",
      vpsEmptyDropBtn: "+ Add VPS Node",
      vpsDeleteTitle: "Delete this saved VPS node",
      vpsInvalidAddr: "Please enter a valid VPS node address",
      guideTitleP2P: "P2P Direct Guide",
      guideTitleVPS: "Custom VPS Relay Guide",
      toastStep2Locked: "Complete Step 1 connectivity test with 2+ online first",
      toastStep2Relocked: "Fewer than 2 online or unverified; Step 2 has been re-locked",
      toastNodeStarted: (p) => `Local node started on UDP :${p}`,
      toastNodeStopped: "Local node stopped",
      toastInviteCopied: "Invite code copied to clipboard",
      toastStunRunning: "Running STUN public address probe...",
      toastPeerEmpty: "Please enter or paste your friend's invite code / IP",
      toastPeerAdded: (k) => `Added peer ${k}, initiating connection...`,
      toastVpsEmpty: "Please add or enter a custom VPS node address first",
      toastVpsConnecting: "Connecting to custom VPS relay...",
      toastVpsDisconnected: "Disconnected from VPS relay",
      toastVpsSaved: (n) => `Saved VPS node: ${n}`,
      toastVpsDeleted: (n) => `Deleted VPS node: ${n}`,
      toastTestRunning: "Running latency & 1150B MTU connectivity test...",
      toastRemoveNeedSel: "Please select a peer from the list to remove",
      toastHostBridgeStarted: "Host Civ VI bridge started",
      toastClientBridgeStarted: "Client Civ VI helper started",
      toastBridgeStopped: "Civ VI helper stopped",
      toastProbingRoom: "Probing Host Civ VI lobby...",
      toastNetRefreshed: "Local network addresses refreshed",
      toastLogCopied: "Logs copied to clipboard",
      toastCmdCopied: "Deployment command copied to clipboard",
      keyMismatchTitle: "Room Key Mismatch",
      keyMismatchMsg: (r, l) => `Peer invite code uses room key "${r}", which differs from your local key "${l}".\n\nRestart local node to sync the room key?`,
      keyMismatchConfirm: "Restart & Sync",
      testPassedTitle: "Step 1 Verification Passed",
      testPassedMsg: (k, s, n) =>
        `Connectivity test with ${k} passed!\n\nResult: ${s}\nOnline players: ${n} (meets 2+ requirement)\n\nStep 2 (Civ VI Helper) is now unlocked. Enter Step 2 now?`,
      testPassedConfirm: "Enter Step 2",
      testPassedCancel: "Later",
      guideCopyBtn: "Copy",
      guideP2PHtml: `
        <div class="guide-callout">
          <strong>Best for:</strong> Zero server cost and lowest latency when both peers (or Host) have public IPv6 or standard Cone NAT home broadband.
        </div>
        <div class="guide-block">
          <h4 class="guide-h4">Quick Steps</h4>
          <ol class="guide-steps">
            <li><strong>Start Local Node:</strong> Host picks "Host", friends pick "Client", set nicknames and the <strong>same Room Key</strong> (default port <code>38666</code>), then click <strong>Start Node</strong>.</li>
            <li><strong>Check Public Address:</strong> When IPv6 shows "Public Ready", keep <code>[Preferred Public IPv6]</code> selected; otherwise click <strong>STUN Probe</strong> to detect mapped IPv4.</li>
            <li><strong>Exchange Codes & Punch:</strong> Click <strong>Copy Code</strong> and send it to friends. Both sides paste each other's code into "Peer Code / IP" and click <strong>Add & Connect</strong> for simultaneous hole-punching.</li>
            <li><strong>Verify & Unlock Step 2:</strong> Once peers show "Online" (2+ total), select a peer and click <strong>Test Selected</strong> (latency + 1150B MTU check) to unlock <strong>Step 2 · Civ VI Helper</strong>.</li>
          </ol>
        </div>
        <div class="guide-block">
          <h4 class="guide-h4">Troubleshooting</h4>
          <ul class="guide-list">
            <li><strong>Stuck on "Punching":</strong> Verify both sides share the exact same Room Key, both added each other's code, and Windows Firewall allows UDP for this app.</li>
            <li><strong>Still cannot connect directly:</strong> If behind Symmetric NAT, campus/corporate firewall, or mobile hotspot without public IPv6, switch to <strong>Mode 2 · Custom VPS Relay</strong>.</li>
          </ul>
        </div>
      `,
      guideVPSHtml: `
        <div class="guide-callout">
          <strong>Best for:</strong> Symmetric NAT, campus networks, missing public IPv6, or cross-ISP packet loss. Route through your own VPS without exchanging player IPs.
        </div>
        <div class="guide-block">
          <h4 class="guide-h4">Option 1 · Self-hosted EasyTier VPS (Recommended, Port 11010)</h4>
          <p class="guide-desc">Embedded no-TUN EasyTier core attempts P2P hole-punching first and falls back to VPS relay automatically. Open <code>TCP / UDP 11010</code> on your VPS firewall.</p>
          <div class="guide-cmd-box">
            <div class="guide-cmd-label">Linux / VPS start command (with easytier-core binary)</div>
            <div class="guide-cmd-row">
              <code class="guide-cmd-code">./easytier-core --no-tun -l tcp://0.0.0.0:11010 -l udp://0.0.0.0:11010</code>
              <button class="glass-btn btn-xs btn-soft light-interactive guide-copy-btn" type="button" data-copy="./easytier-core --no-tun -l tcp://0.0.0.0:11010 -l udp://0.0.0.0:11010">Copy</button>
            </div>
          </div>
          <div class="guide-cmd-box">
            <div class="guide-cmd-label">Docker one-line deployment (optional auth: add --network-name civ6-room --network-secret YOUR_PASS --private-mode true)</div>
            <div class="guide-cmd-row">
              <code class="guide-cmd-code">docker run -d --name easytier --restart always --network host easytier/easytier:latest --no-tun -l tcp://0.0.0.0:11010 -l udp://0.0.0.0:11010</code>
              <button class="glass-btn btn-xs btn-soft light-interactive guide-copy-btn" type="button" data-copy="docker run -d --name easytier --restart always --network host easytier/easytier:latest --no-tun -l tcp://0.0.0.0:11010 -l udp://0.0.0.0:11010">Copy</button>
            </div>
          </div>
          <p class="guide-desc">Then click <strong>+ Add VPS</strong> → choose <code>EasyTier VPS (11010)</code> → enter <code>tcp://YOUR_VPS_IP:11010</code>. If private mode is enabled, match Room Name with <code>--network-name</code> and enter <code>--network-secret</code> in the optional password field.</p>
        </div>
        <div class="guide-block">
          <h4 class="guide-h4">Option 2 · Lightweight UDP Relay (civ6_relay_server, Port 38668)</h4>
          <p class="guide-desc">Zero third-party dependencies (Python 3 only) with dual-stack IPv4/IPv6 client support. Open <code>UDP 38668</code> on your VPS firewall.</p>
          <div class="guide-cmd-box">
            <div class="guide-cmd-label">Upload civ6_relay_server.py and civ6_p2p/ to your VPS and run (optional --password for auth)</div>
            <div class="guide-cmd-row">
              <code class="guide-cmd-code">python3 civ6_relay_server.py --port 38668 --password YOUR_PASS</code>
              <button class="glass-btn btn-xs btn-soft light-interactive guide-copy-btn" type="button" data-copy="python3 civ6_relay_server.py --port 38668 --password YOUR_PASS">Copy</button>
            </div>
          </div>
          <p class="guide-desc">Omit <code>--password</code> for open mode. Then click <strong>+ Add VPS</strong> → choose <code>Lightweight UDP Relay (38668)</code> → enter <code>YOUR_VPS_IP:38668</code> and optional password.</p>
        </div>
        <div class="guide-block">
          <h4 class="guide-h4">Client Connection Steps</h4>
          <ol class="guide-steps">
            <li>Host selects "Host", friends select "Client", and all players set the <strong>same Room Key</strong>.</li>
            <li>In "Mode 2 · Custom VPS Relay", choose the same VPS node and <strong>same Room Name</strong>, then click <strong>Connect VPS</strong>.</li>
            <li>Once friends appear "Online", click <strong>Test Selected</strong> to unlock Step 2 and start the Civ VI helper.</li>
          </ol>
        </div>
      `,
    },
  };

  const state = {
    lang: "zh",
    activeStep: "step1",
    selectedPeerKey: "",
    lastLogId: 0,
    lastEventId: 0,
    logCount: 0,
    theme: "light",
    latest: null,
    pollTimer: null,
    polling: false,
    initializedForm: false,
    syncedPrefs: false,
    modalResolve: null,
  };

  const $ = (id) => document.getElementById(id);

  function dict() {
    return I18N[state.lang] || I18N.zh;
  }

  function t(key, ...args) {
    const val = dict()[key];
    if (typeof val === "function") return val(...args);
    return val !== undefined ? val : key;
  }

  function api() {
    return window.pywebview && window.pywebview.api ? window.pywebview.api : null;
  }

  async function callApi(method, ...args) {
    const bridge = api();
    if (!bridge || typeof bridge[method] !== "function") {
      return null;
    }
    try {
      return await bridge[method](...args);
    } catch (err) {
      console.error("API call failed:", method, err);
      return { ok: false, title: t("apiErrorTitle"), message: String(err) };
    }
  }

  function bindGuideCopyButtons() {
    document.querySelectorAll(".guide-copy-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const cmd = btn.dataset.copy || "";
        if (!cmd) return;
        await callApi("copy_text", cmd, "");
        showToast(t("toastCmdCopied"), "ok");
      });
    });
  }

  function applyStaticI18n() {
    document.documentElement.lang = state.lang === "en" ? "en" : "zh-CN";

    document.querySelectorAll("[data-i18n]").forEach((el) => {
      el.textContent = t(el.dataset.i18n);
    });
    document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
      el.placeholder = t(el.dataset.i18nPlaceholder);
    });
    document.querySelectorAll("[data-i18n-title]").forEach((el) => {
      el.title = t(el.dataset.i18nTitle);
    });

    document.querySelectorAll("#lang-toggle .lang-opt").forEach((el) => {
      el.classList.toggle("is-active", el.dataset.langOpt === state.lang);
    });

    $("theme-label").textContent = state.theme === "dark" ? t("themeDark") : t("themeLight");
    const logCollapsed = $("log-dock").dataset.collapsed === "true";
    $("btn-toggle-log").textContent = logCollapsed ? t("btnExpand") : t("btnCollapse");

    $("guide-panel-p2p").innerHTML = t("guideP2PHtml");
    $("guide-panel-vps").innerHTML = t("guideVPSHtml");
    bindGuideCopyButtons();
    $("guide-modal-title").textContent = activeGuideTab === "vps" ? t("guideTitleVPS") : t("guideTitleP2P");
    syncVpsKindUi();

    requestAnimationFrame(() => syncAllThumbs(true));
  }

  async function applyLanguage(lang, persistBackend = false) {
    const clean = lang === "en" ? "en" : "zh";
    state.lang = clean;
    applyStaticI18n();
    if (persistBackend) {
      await callApi("set_lang", clean);
      await refreshState();
    } else if (state.latest) {
      renderState(state.latest);
    }
  }

  function initLightFieldPhysics() {
    document.addEventListener(
      "pointermove",
      (e) => {
        const card = e.target.closest(".glass-card");
        if (!card) return;
        const rect = card.getBoundingClientRect();
        const x = ((e.clientX - rect.left) / rect.width) * 100;
        const y = ((e.clientY - rect.top) / rect.height) * 100;
        card.style.setProperty("--mx", `${x.toFixed(1)}%`);
        card.style.setProperty("--my", `${y.toFixed(1)}%`);
      },
      { passive: true }
    );

    document.addEventListener(
      "pointerdown",
      (e) => {
        const target = e.target.closest(".light-interactive");
        if (!target || target.disabled) return;
        const rect = target.getBoundingClientRect();
        const bloom = document.createElement("span");
        bloom.className = "light-bloom";
        bloom.style.left = `${e.clientX - rect.left}px`;
        bloom.style.top = `${e.clientY - rect.top}px`;
        target.appendChild(bloom);
        window.setTimeout(() => bloom.remove(), 580);
      },
      { passive: true }
    );

    document.addEventListener("contextmenu", (e) => {
      if (e.target.closest("input, textarea, .log-body, .modal-message, .guide-scroll")) return;
      e.preventDefault();
    });
  }

  function positionThumb(container, thumb, activeBtn) {
    if (!container || !thumb || !activeBtn) return;
    const w = activeBtn.offsetWidth;
    const x = activeBtn.offsetLeft;
    if (w <= 0) return;
    const sig = `${x}:${w}`;
    if (thumb.dataset.pos === sig) return;
    thumb.dataset.pos = sig;
    thumb.style.width = `${w}px`;
    thumb.style.transform = `translate3d(${x}px, 0, 0)`;
  }

  function positionStepThumb() {
    const dock = document.querySelector(".step-dock");
    const thumb = $("step-thumb");
    const active = state.activeStep === "step2" ? $("tab-btn-step2") : $("tab-btn-step1");
    positionThumb(dock, thumb, active);
  }

  function syncAllThumbs(force = false) {
    if (force) {
      [$("step-thumb"), $("role-thumb"), $("mode-thumb"), $("guide-thumb"), $("vps-kind-thumb")].forEach((el) => {
        if (el) delete el.dataset.pos;
      });
    }
    positionStepThumb();
    const roleSeg = $("role-seg");
    positionThumb(roleSeg, $("role-thumb"), roleSeg.querySelector(".is-active"));
    const modeSeg = $("mode-seg");
    positionThumb(modeSeg, $("mode-thumb"), modeSeg.querySelector(".is-active"));
    if (!$("guide-modal-backdrop").hidden) {
      const gSeg = $("guide-seg");
      positionThumb(gSeg, $("guide-thumb"), gSeg.querySelector(".is-active"));
    }
    if (!$("vps-modal-backdrop").hidden) {
      const vSeg = $("vps-kind-seg");
      positionThumb(vSeg, $("vps-kind-thumb"), vSeg.querySelector(".is-active"));
    }
  }

  function showToast(message, level = "info") {
    const stack = $("toast-stack");
    const el = document.createElement("div");
    el.className = "glass-toast";
    el.dataset.level = level;
    el.innerHTML = `<span class="toast-dot"></span><span></span>`;
    el.lastElementChild.textContent = message;
    stack.appendChild(el);
    window.setTimeout(() => {
      el.classList.add("is-out");
      window.setTimeout(() => el.remove(), 260);
    }, 2600);
  }

  function showModal({ title, message = "", level = "info", confirmText, cancelText = "" }) {
    return new Promise((resolve) => {
      const backdrop = $("modal-backdrop");
      const badge = $("modal-badge");
      const cancelBtn = $("modal-cancel");
      const confirmBtn = $("modal-confirm");

      badge.dataset.level = level;
      badge.textContent = level === "ok" ? "✓" : level === "warn" ? "!" : level === "error" ? "×" : "i";
      $("modal-title").textContent = title || t("modalDefaultTitle");
      $("modal-message").textContent = message;
      confirmBtn.textContent = confirmText || t("btnOk");

      if (cancelText) {
        cancelBtn.textContent = cancelText;
        cancelBtn.hidden = false;
      } else {
        cancelBtn.hidden = true;
      }

      state.modalResolve = (val) => {
        backdrop.hidden = true;
        state.modalResolve = null;
        resolve(val);
      };
      backdrop.hidden = false;
      confirmBtn.focus();
    });
  }

  function initModalEvents() {
    $("modal-confirm").addEventListener("click", () => {
      if (state.modalResolve) state.modalResolve(true);
    });
    $("modal-cancel").addEventListener("click", () => {
      if (state.modalResolve) state.modalResolve(false);
    });
    $("modal-backdrop").addEventListener("click", (e) => {
      if (e.target === $("modal-backdrop") && !$("modal-cancel").hidden && state.modalResolve) {
        state.modalResolve(false);
      }
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && !$("modal-backdrop").hidden && state.modalResolve) {
        state.modalResolve(false);
      }
    });
  }

  function initCombo(wrapperId, inputId, onSelect) {
    const wrap = $(wrapperId);
    const input = $(inputId);
    const trigger = wrap.querySelector(".combo-trigger");
    const menu = wrap.querySelector(".combo-menu");

    function close() {
      wrap.classList.remove("is-open");
    }

    function toggle() {
      if (input.disabled) return;
      const open = !wrap.classList.contains("is-open");
      document.querySelectorAll(".combo-wrap.is-open").forEach((el) => el.classList.remove("is-open"));
      if (open) wrap.classList.add("is-open");
    }

    trigger.addEventListener("click", (e) => {
      e.stopPropagation();
      toggle();
    });

    document.addEventListener("click", (e) => {
      if (!wrap.contains(e.target)) close();
    });

    return {
      setItems(items, currentValue) {
        const keySig = state.lang + "|" + items.map((x) => `${x.label}:${x.tag || ""}`).join("||");
        if (menu.dataset.sig === keySig) {
          menu.querySelectorAll(".combo-item").forEach((btn) => {
            btn.classList.toggle("is-selected", btn.dataset.val === currentValue);
          });
          return;
        }
        menu.dataset.sig = keySig;
        menu.innerHTML = "";
        for (const item of items) {
          const btn = document.createElement("button");
          btn.type = "button";
          btn.className = "combo-item";
          btn.dataset.val = item.label;
          if (item.label === currentValue) btn.classList.add("is-selected");

          const mainSpan = document.createElement("span");
          mainSpan.textContent = item.ip || item.uri || item.label;
          const tagSpan = document.createElement("span");
          tagSpan.className = "combo-item-tag";
          tagSpan.textContent = item.tag || item.desc || "";

          btn.appendChild(mainSpan);
          if (tagSpan.textContent) btn.appendChild(tagSpan);

          btn.addEventListener("click", () => {
            input.value = item.label;
            close();
            onSelect(item.label);
          });
          menu.appendChild(btn);
        }
      },
      setDisabled(disabled) {
        input.disabled = disabled;
        trigger.disabled = disabled;
        if (disabled) close();
      },
    };
  }

  function initVpsCombo(wrapperId, inputId, { onSelect, onDelete, onAddNew }) {
    const wrap = $(wrapperId);
    const input = $(inputId);
    const trigger = wrap.querySelector(".combo-trigger");
    const menu = wrap.querySelector(".combo-menu");

    function close() {
      wrap.classList.remove("is-open");
    }

    function toggle() {
      if (input.disabled) return;
      const open = !wrap.classList.contains("is-open");
      document.querySelectorAll(".combo-wrap.is-open").forEach((el) => el.classList.remove("is-open"));
      if (open) wrap.classList.add("is-open");
    }

    trigger.addEventListener("click", (e) => {
      e.stopPropagation();
      toggle();
    });

    document.addEventListener("click", (e) => {
      if (!wrap.contains(e.target)) close();
    });

    return {
      setNodes(nodes, currentValue) {
        const list = Array.isArray(nodes) ? nodes : [];
        const sig = state.lang + "|" + JSON.stringify(list) + "|" + (currentValue || "");
        if (menu.dataset.sig === sig) return;
        menu.dataset.sig = sig;
        menu.innerHTML = "";

        if (list.length === 0) {
          const empty = document.createElement("div");
          empty.className = "combo-empty-vps";
          const tip = document.createElement("span");
          tip.textContent = t("vpsEmptyDrop");
          const addBtn = document.createElement("button");
          addBtn.type = "button";
          addBtn.className = "glass-btn btn-xs btn-accent light-interactive";
          addBtn.textContent = t("vpsEmptyDropBtn");
          addBtn.addEventListener("click", () => {
            close();
            onAddNew();
          });
          empty.appendChild(tip);
          empty.appendChild(addBtn);
          menu.appendChild(empty);
          return;
        }

        for (const node of list) {
          const row = document.createElement("div");
          row.className = "combo-item-vps" + (node.label === currentValue ? " is-selected" : "");

          const mainBtn = document.createElement("button");
          mainBtn.type = "button";
          mainBtn.className = "combo-vps-main";
          const lockHtml = node.has_password
            ? `<span class="vps-lock-pill">🔒 ${escapeHtml(t("vpsLockBadge"))}</span>`
            : "";
          mainBtn.innerHTML =
            `<span class="combo-vps-top">` +
            `<span class="combo-vps-name">${escapeHtml(node.name || node.address)}</span>` +
            `<span class="vps-kind-pill ${escapeHtml(node.kind || "easytier")}">${escapeHtml(node.kind_label || "EasyTier")}</span>` +
            lockHtml +
            `</span>` +
            `<span class="combo-vps-addr">${escapeHtml(node.address)}</span>`;
          mainBtn.addEventListener("click", () => {
            input.value = node.label;
            close();
            onSelect(node);
          });

          const delBtn = document.createElement("button");
          delBtn.type = "button";
          delBtn.className = "combo-vps-del";
          delBtn.title = t("vpsDeleteTitle");
          delBtn.setAttribute("aria-label", t("vpsDeleteTitle"));
          delBtn.textContent = "×";
          delBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            onDelete(node);
          });

          row.appendChild(mainBtn);
          row.appendChild(delBtn);
          menu.appendChild(row);
        }
      },
      setDisabled(disabled) {
        input.disabled = disabled;
        trigger.disabled = disabled;
        if (disabled) close();
      },
      close,
    };
  }

  let addrComboCtrl = null;
  let vpsComboCtrl = null;
  let vpsDraftKind = "easytier";
  let activeGuideTab = "p2p";

  function syncVpsKindUi() {
    const seg = $("vps-kind-seg");
    if (!seg) return;
    seg.querySelectorAll(".vps-kind-btn").forEach((btn) => {
      btn.classList.toggle("is-active", btn.dataset.kind === vpsDraftKind);
    });
    positionThumb(seg, $("vps-kind-thumb"), seg.querySelector(".is-active"));

    const addrInput = $("vps-input-address");
    const hint = $("vps-addr-hint");
    const pwHint = $("vps-pw-hint");
    if (vpsDraftKind === "udp_relay") {
      addrInput.placeholder = t("phVpsAddrUDP");
      hint.innerHTML = t("hintVpsUDP");
      if (pwHint) pwHint.innerHTML = t("hintVpsPwUDP");
    } else {
      addrInput.placeholder = t("phVpsAddrET");
      hint.innerHTML = t("hintVpsET");
      if (pwHint) pwHint.innerHTML = t("hintVpsPwET");
    }
  }

  function openAddVpsModal() {
    $("vps-input-name").value = "";
    $("vps-input-address").value = "";
    const pwEl = $("vps-input-password");
    pwEl.value = "";
    pwEl.type = "password";
    $("btn-toggle-vps-modal-pw").classList.remove("is-shown");
    const errEl = $("vps-form-error");
    errEl.hidden = true;
    errEl.textContent = "";
    vpsDraftKind = "easytier";
    $("vps-modal-backdrop").hidden = false;
    requestAnimationFrame(() => {
      delete $("vps-kind-thumb").dataset.pos;
      syncVpsKindUi();
      $("vps-input-address").focus();
    });
  }

  function closeAddVpsModal() {
    $("vps-modal-backdrop").hidden = true;
  }

  async function saveCustomVpsNode() {
    const name = $("vps-input-name").value.trim();
    const address = $("vps-input-address").value.trim();
    const password = $("vps-input-password").value.trim();
    const errEl = $("vps-form-error");
    errEl.hidden = true;

    const res = await callApi("add_vps_node", name, address, vpsDraftKind, password);
    if (!res || !res.ok) {
      errEl.textContent = (res && res.message) || t("vpsInvalidAddr");
      errEl.hidden = false;
      $("vps-input-address").focus();
      return;
    }
    closeAddVpsModal();
    if (res.node && res.node.label) {
      $("input-et-node").value = res.node.label;
      $("input-et-password").value = res.node.password || "";
    }
    showToast(t("toastVpsSaved", res.node ? res.node.name : address), "ok");
    await refreshState();
  }

  function bindPwToggle(btnId, inputId) {
    const btn = $(btnId);
    const inp = $(inputId);
    if (!btn || !inp) return;
    btn.addEventListener("click", () => {
      const show = inp.type === "password";
      inp.type = show ? "text" : "password";
      btn.classList.toggle("is-shown", show);
    });
  }

  function initAddVpsModalEvents() {
    bindPwToggle("btn-toggle-vps-modal-pw", "vps-input-password");
    $("vps-kind-seg").querySelectorAll(".vps-kind-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        vpsDraftKind = btn.dataset.kind;
        syncVpsKindUi();
      });
    });
    $("vps-modal-cancel").addEventListener("click", closeAddVpsModal);
    $("vps-modal-save").addEventListener("click", saveCustomVpsNode);
    $("vps-modal-backdrop").addEventListener("click", (e) => {
      if (e.target === $("vps-modal-backdrop")) closeAddVpsModal();
    });
    const onEnterSave = (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        void saveCustomVpsNode();
      }
    };
    $("vps-input-address").addEventListener("keydown", onEnterSave);
    $("vps-input-password").addEventListener("keydown", onEnterSave);
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && !$("vps-modal-backdrop").hidden) {
        closeAddVpsModal();
      }
    });
  }

  function switchGuideTab(tab) {
    activeGuideTab = tab === "vps" ? "vps" : "p2p";
    const seg = $("guide-seg");
    seg.querySelectorAll(".guide-seg-btn").forEach((btn) => {
      btn.classList.toggle("is-active", btn.dataset.guideTab === activeGuideTab);
    });
    positionThumb(seg, $("guide-thumb"), seg.querySelector(".is-active"));
    $("guide-panel-p2p").classList.toggle("is-active", activeGuideTab === "p2p");
    $("guide-panel-vps").classList.toggle("is-active", activeGuideTab === "vps");
    $("guide-modal-title").textContent = activeGuideTab === "vps" ? t("guideTitleVPS") : t("guideTitleP2P");
    const sc = document.querySelector(".guide-scroll");
    if (sc) sc.scrollTop = 0;
  }

  function openGuideModal(tab = "p2p") {
    $("guide-modal-backdrop").hidden = false;
    requestAnimationFrame(() => {
      delete $("guide-thumb").dataset.pos;
      switchGuideTab(tab);
    });
  }

  function closeGuideModal() {
    $("guide-modal-backdrop").hidden = true;
  }

  function initGuideModalEvents() {
    $("btn-guide-p2p").addEventListener("click", () => openGuideModal("p2p"));
    $("btn-guide-vps").addEventListener("click", () => openGuideModal("vps"));
    $("guide-seg").querySelectorAll(".guide-seg-btn").forEach((btn) => {
      btn.addEventListener("click", () => switchGuideTab(btn.dataset.guideTab));
    });
    $("guide-modal-close").addEventListener("click", closeGuideModal);
    $("guide-modal-backdrop").addEventListener("click", (e) => {
      if (e.target === $("guide-modal-backdrop")) closeGuideModal();
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && !$("guide-modal-backdrop").hidden) {
        closeGuideModal();
      }
    });
  }

  function switchStep(stepName, shakeIfLocked = true) {
    if (stepName === "step2") {
      const unlocked = state.latest && state.latest.gate && state.latest.gate.step2_unlocked;
      if (!unlocked) {
        if (shakeIfLocked) {
          const btn = $("tab-btn-step2");
          btn.classList.remove("shake");
          void btn.offsetWidth;
          btn.classList.add("shake");
          const reason = (state.latest && state.latest.gate && state.latest.gate.reason) || t("toastStep2Locked");
          showToast(reason, "warn");
        }
        return;
      }
    }
    state.activeStep = stepName;
    $("tab-btn-step1").classList.toggle("is-active", stepName === "step1");
    $("tab-btn-step2").classList.toggle("is-active", stepName === "step2");
    $("view-step1").classList.toggle("is-active", stepName === "step1");
    $("view-step2").classList.toggle("is-active", stepName === "step2");
    positionStepThumb();
  }

  async function applyTheme(theme, persistBackend = false) {
    const clean = theme === "dark" ? "dark" : "light";
    state.theme = clean;
    document.documentElement.classList.add("theme-switching");
    document.documentElement.setAttribute("data-theme", clean);
    $("theme-icon").textContent = clean === "dark" ? "☾" : "☀";
    $("theme-label").textContent = clean === "dark" ? t("themeDark") : t("themeLight");
    void document.documentElement.offsetHeight;
    document.documentElement.classList.remove("theme-switching");
    if (persistBackend) {
      await callApi("set_theme", clean);
    }
  }

  function setInputIfUnfocused(el, val) {
    if (!el || document.activeElement === el) return;
    if (el.value !== val) el.value = val;
  }

  function renderBadges(data) {
    const bIpv6 = $("badge-ipv6");
    bIpv6.dataset.tone = data.ipv6_ready ? "ok" : "warn";
    bIpv6.querySelector(".status-val").textContent = data.ipv6_ready ? t("ipv6Ready") : t("ipv6None");

    const bNode = $("badge-node");
    bNode.dataset.tone = data.node_running ? "ok" : "neutral";
    bNode.querySelector(".status-val").textContent = data.node_running
      ? t("nodeRunning", data.actual_port)
      : t("notStarted");

    const bOnline = $("badge-online");
    const total = data.gate.total_online;
    bOnline.dataset.tone = total >= 2 ? "ok" : total === 1 ? "warn" : "neutral";
    bOnline.querySelector(".status-val").textContent = t("onlineCount", total);

    const bCiv6 = $("badge-civ6");
    bCiv6.dataset.tone = data.civ6_running ? "ok" : "neutral";
    bCiv6.querySelector(".status-val").textContent = data.civ6_summary;

    let mood = "idle";
    if (data.step2.active_bridge) {
      mood = "active";
    } else if (data.gate.can_enter_step2) {
      mood = "unlocked";
    } else if (data.et_connecting || data.peers.some((p) => p.status === "connecting")) {
      mood = "connecting";
    }
    document.body.dataset.mood = mood;
  }

  function renderPeers(peers) {
    const tbody = $("peer-tbody");
    const empty = $("peer-empty");

    if (!peers || peers.length === 0) {
      tbody.innerHTML = "";
      empty.style.display = "flex";
      state.selectedPeerKey = "";
      return;
    }

    empty.style.display = "none";
    const keys = new Set(peers.map((p) => p.peer_key));
    if (!state.selectedPeerKey || !keys.has(state.selectedPeerKey)) {
      if (peers.length === 1) state.selectedPeerKey = peers[0].peer_key;
      else if (!keys.has(state.selectedPeerKey)) state.selectedPeerKey = "";
    }

    const sig = state.lang + "|" + JSON.stringify(peers) + "|" + state.selectedPeerKey;
    if (tbody.dataset.sig === sig) return;
    tbody.dataset.sig = sig;

    const frag = document.createDocumentFragment();
    for (const p of peers) {
      const tr = document.createElement("tr");
      tr.dataset.key = p.peer_key;
      tr.className = "light-interactive" + (p.peer_key === state.selectedPeerKey ? " is-selected" : "");
      tr.addEventListener("click", () => {
        state.selectedPeerKey = p.peer_key;
        tbody.querySelectorAll("tr").forEach((r) => r.classList.toggle("is-selected", r.dataset.key === p.peer_key));
      });
      tr.addEventListener("dblclick", () => {
        state.selectedPeerKey = p.peer_key;
        void handleTestPeer();
      });

      const cells = [
        { text: p.nickname, cls: "" },
        { html: `<span class="role-chip">${escapeHtml(p.role_label)}</span>` },
        { text: p.transport_label, cls: "" },
        { text: p.peer_key, cls: "mono", title: p.peer_key },
        { html: `<span class="peer-status-tag ${p.status}"><span class="status-dot"></span>${escapeHtml(p.status_label)}</span>` },
        { text: p.rtt_text, cls: "mono" },
        { text: p.loss_text, cls: "mono" },
        { text: p.civ6_summary, cls: "", title: p.civ6_summary },
        { text: p.test_summary, cls: "", title: p.test_summary },
        { text: p.fake_ip, cls: "mono" },
      ];

      for (const c of cells) {
        const td = document.createElement("td");
        if (c.cls) td.className = c.cls;
        if (c.title) td.title = c.title;
        if (c.html !== undefined) td.innerHTML = c.html;
        else td.textContent = c.text;
        tr.appendChild(td);
      }
      frag.appendChild(tr);
    }
    tbody.innerHTML = "";
    tbody.appendChild(frag);
  }

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function appendLogs(entries) {
    if (!entries || entries.length === 0) return;
    const box = $("log-body");
    const nearBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 36;
    const frag = document.createDocumentFragment();

    for (const item of entries) {
      const div = document.createElement("div");
      div.className = `log-line ${item.level || "info"}`;
      const ts = document.createElement("span");
      ts.className = "log-ts";
      ts.textContent = item.ts;
      const msg = document.createElement("span");
      msg.className = "log-msg";
      msg.textContent = item.msg;
      div.appendChild(ts);
      div.appendChild(msg);
      frag.appendChild(div);
      state.logCount += 1;
    }

    box.appendChild(frag);
    while (box.children.length > 450) {
      box.removeChild(box.firstChild);
    }
    $("log-count").textContent = String(box.children.length);
    if (nearBottom) {
      box.scrollTop = box.scrollHeight;
    }
  }

  async function processEvents(events) {
    if (!events || events.length === 0) return;
    for (const ev of events) {
      if (ev.kind === "toast") {
        showToast(ev.payload.message, ev.payload.level || "info");
      } else if (ev.kind === "modal") {
        await showModal({
          title: ev.payload.title || t("modalDefaultTitle"),
          message: ev.payload.message || "",
          level: ev.payload.level || "info",
        });
      } else if (ev.kind === "test_passed") {
        const p = ev.payload;
        const go = await showModal({
          title: t("testPassedTitle"),
          level: "ok",
          message: t("testPassedMsg", p.peer_key, p.summary, p.total_online),
          confirmText: t("testPassedConfirm"),
          cancelText: t("testPassedCancel"),
        });
        if (go) {
          await refreshState();
          switchStep("step2", false);
        }
      }
    }
  }

  function renderState(data) {
    if (!data) return;
    state.latest = data;

    if (!state.syncedPrefs) {
      state.syncedPrefs = true;
      if (data.theme && data.theme !== state.theme) {
        void applyTheme(data.theme, false);
      }
      if (data.lang && data.lang !== state.lang) {
        state.lang = data.lang;
        applyStaticI18n();
      }
    }

    if (!state.initializedForm) {
      state.initializedForm = true;
      $("input-nickname").value = data.nickname;
      $("input-port").value = data.port_text;
      $("input-room-key").value = data.room_key;
      $("input-adv-addr").value = data.selected_address;
      $("input-et-node").value = data.et_node;
      $("input-et-room").value = data.et_room;
      $("input-et-password").value = data.et_password || "";
    } else {
      setInputIfUnfocused($("input-port"), data.port_text);
      setInputIfUnfocused($("input-room-key"), data.room_key);
      setInputIfUnfocused($("input-adv-addr"), data.selected_address);
      setInputIfUnfocused($("input-et-node"), data.et_node);
      setInputIfUnfocused($("input-et-room"), data.et_room);
      setInputIfUnfocused($("input-et-password"), data.et_password || "");
    }

    renderBadges(data);

    const roleSeg = $("role-seg");
    roleSeg.querySelectorAll(".mini-seg-btn").forEach((btn) => {
      btn.classList.toggle("is-active", btn.dataset.role === data.role);
      btn.disabled = data.role_locked;
    });
    positionThumb(roleSeg, $("role-thumb"), roleSeg.querySelector(".is-active"));

    $("input-port").disabled = data.node_running;
    $("input-room-key").disabled = data.node_running;
    $("btn-start-node").disabled = data.node_running;
    $("btn-stop-node").disabled = !data.node_running;

    const modeSeg = $("mode-seg");
    modeSeg.querySelectorAll(".mode-seg-btn").forEach((btn) => {
      btn.classList.toggle("is-active", btn.dataset.mode === data.conn_mode);
    });
    positionThumb(modeSeg, $("mode-thumb"), modeSeg.querySelector(".is-active"));
    $("panel-p2p").classList.toggle("is-active", data.conn_mode === "p2p_ipv6");
    $("panel-relay").classList.toggle("is-active", data.conn_mode === "relay");

    addrComboCtrl.setItems(data.address_choices || [], data.selected_address);
    $("input-invite-code").value = data.invite_code || "";
    $("btn-stun-probe").disabled = data.stun_busy;
    $("btn-stun-probe").textContent = data.stun_busy ? t("btnStunBusy") : t("btnStun");

    vpsComboCtrl.setNodes(data.vps_nodes || [], data.et_node);
    vpsComboCtrl.setDisabled(data.et_connected_or_running);
    $("btn-open-add-vps").disabled = data.et_connected_or_running;
    $("input-et-room").disabled = data.et_connected_or_running;
    $("input-et-password").disabled = data.et_connected_or_running;
    $("btn-et-connect").disabled = data.et_connected_or_running;
    $("btn-et-connect").textContent = data.et_connecting ? t("btnConnectVpsBusy") : t("btnConnectVps");
    $("btn-et-disconnect").disabled = !data.et_connected_or_running;
    $("et-status-bar").dataset.level = data.et_status_level || "idle";
    $("et-status-text").textContent = data.et_status || "";

    $("btn-test-peer").disabled = data.test_busy;
    $("btn-test-peer").textContent = data.test_busy ? t("btnTestPeerBusy") : t("btnTestPeer");
    renderPeers(data.peers || []);

    const gate = data.gate;
    const step2Tab = $("tab-btn-step2");
    step2Tab.classList.toggle("is-locked", !gate.step2_unlocked);
    step2Tab.classList.toggle("is-unlocked", gate.step2_unlocked);
    $("step2-tab-sub").textContent = gate.step2_unlocked
      ? t("step2UnlockedSub", gate.total_online)
      : t("step2LockedSub");
    $("step2-lock-chip").textContent = gate.step2_unlocked
      ? t("step2UnlockedChip", gate.total_online)
      : t("step2LockedChip");

    if (!gate.step2_unlocked && state.activeStep === "step2") {
      switchStep("step1", false);
      showToast(t("toastStep2Relocked"), "warn");
    }

    const banner = $("gate-banner");
    banner.dataset.unlocked = String(Boolean(gate.can_enter_step2));
    $("gate-reason").textContent = gate.reason;
    $("btn-goto-step2").disabled = !gate.step2_unlocked;

    const s2 = data.step2;
    $("pf-tile-node").dataset.ok = String(Boolean(s2.preflight_node_ok));
    $("pf-node-val").textContent = s2.preflight_node;
    $("pf-tile-peer").dataset.ok = String(Boolean(s2.preflight_peer_ok));
    $("pf-peer-val").textContent = s2.preflight_peer;
    $("pf-tile-local-civ6").dataset.ok = String(Boolean(s2.preflight_local_civ6_ok));
    $("pf-local-civ6-val").textContent = s2.preflight_local_civ6;
    $("pf-tile-remote-civ6").dataset.ok = String(Boolean(s2.preflight_remote_civ6_ok));
    $("pf-remote-civ6-val").textContent = s2.preflight_remote_civ6;

    const hostSel = $("select-target-host");
    if (data.role === "host") {
      $("civ6-role-desc").textContent = t("hostModeDesc");
      $("target-host-label").textContent = t("lblCurrentMode");
      $("btn-start-bridge-text").textContent = t("btnStartHostBridge");
      hostSel.disabled = true;
      const hostSig = `host:${state.lang}`;
      if (hostSel.dataset.mode !== hostSig) {
        hostSel.dataset.mode = hostSig;
        hostSel.innerHTML = `<option value="">${escapeHtml(t("hostModeOption"))}</option>`;
      }
    } else {
      $("civ6-role-desc").textContent = t("clientModeDesc");
      $("target-host-label").textContent = t("lblTargetHost");
      $("btn-start-bridge-text").textContent = t("btnStartClientBridge");
      hostSel.disabled = s2.active_bridge;
      const hosts = s2.target_hosts || [];
      const hSig = `client:${state.lang}:${JSON.stringify(hosts)}`;
      if (hostSel.dataset.mode !== hSig) {
        hostSel.dataset.mode = hSig;
        hostSel.innerHTML = "";
        if (hosts.length === 0) {
          const opt = document.createElement("option");
          opt.value = "";
          opt.textContent = t("noVerifiedHost");
          hostSel.appendChild(opt);
        } else {
          for (const h of hosts) {
            const opt = document.createElement("option");
            opt.value = h.peer_key;
            opt.textContent = h.label;
            hostSel.appendChild(opt);
          }
        }
      }
      if (s2.target_host_key && hostSel.value !== s2.target_host_key) {
        hostSel.value = s2.target_host_key;
      }
    }

    $("btn-start-bridge").disabled = !s2.can_start_bridge;
    $("btn-stop-bridge").disabled = !s2.active_bridge;
    $("btn-probe-room").disabled = !s2.can_probe_room;
    $("btn-probe-room").textContent = s2.probe_busy ? t("btnProbeRoomBusy") : t("btnProbeRoom");

    $("bridge-status-pill").dataset.active = String(Boolean(s2.active_bridge));
    $("bridge-status-text").textContent = s2.bridge_status;
    $("stat-disc").textContent = t("statDiscFmt", s2.disc_reqs, s2.disc_resps);
    $("stat-tx").textContent = t("statPktFmt", s2.tx_pkts, s2.tx_bytes);
    $("stat-rx").textContent = t("statPktFmt", s2.rx_pkts, s2.rx_bytes);
    $("bridge-activity-text").textContent = s2.bridge_activity;

    if (data.logs && data.logs.length > 0) {
      appendLogs(data.logs);
    }
    state.lastLogId = data.last_log_id || state.lastLogId;

    if (data.events && data.events.length > 0) {
      state.lastEventId = data.last_event_id || state.lastEventId;
      void processEvents(data.events);
    }

    if (document.body.classList.contains("is-booting")) {
      syncAllThumbs(true);
      requestAnimationFrame(() => document.body.classList.remove("is-booting"));
    }
  }

  async function refreshState() {
    if (state.polling) return;
    state.polling = true;
    try {
      const data = await callApi("get_state", state.lastLogId, state.lastEventId);
      if (data) renderState(data);
    } finally {
      state.polling = false;
    }
  }

  async function handleStartNode() {
    const res = await callApi(
      "start_node",
      state.latest ? state.latest.role : "client",
      $("input-nickname").value,
      $("input-port").value,
      $("input-room-key").value
    );
    if (res && !res.ok) {
      await showModal({ title: res.title || t("modalDefaultTitle"), message: res.message || "", level: "error" });
    } else if (res && res.ok) {
      showToast(t("toastNodeStarted", res.actual_port), "ok");
    }
    await refreshState();
  }

  async function handleStopNode() {
    await callApi("stop_node");
    showToast(t("toastNodeStopped"), "info");
    await refreshState();
  }

  async function handleCopyInvite() {
    const res = await callApi("copy_invite_code");
    if (res && !res.ok) {
      await showModal({ title: res.title || t("modalDefaultTitle"), message: res.message || "", level: "info" });
    } else if (res && res.ok) {
      showToast(t("toastInviteCopied"), "ok");
    }
    await refreshState();
  }

  async function handleStunProbe() {
    const res = await callApi("run_stun_probe");
    if (res && !res.ok) {
      await showModal({ title: res.title || t("modalDefaultTitle"), message: res.message || "", level: "info" });
    } else {
      showToast(t("toastStunRunning"), "info");
    }
    await refreshState();
  }

  async function handleAddPeer() {
    const input = $("input-peer-addr");
    const raw = input.value.trim();
    if (!raw) {
      showToast(t("toastPeerEmpty"), "warn");
      input.focus();
      return;
    }
    await callApi("update_form", {
      nickname: $("input-nickname").value,
      port_text: $("input-port").value,
      room_key: $("input-room-key").value,
    });

    let res = await callApi("add_peer", raw, false);
    if (res && res.need_confirm_key) {
      const ok = await showModal({
        title: t("keyMismatchTitle"),
        level: "warn",
        message: t("keyMismatchMsg", res.remote_key, res.local_key),
        confirmText: t("keyMismatchConfirm"),
        cancelText: t("btnCancel"),
      });
      if (!ok) return;
      res = await callApi("add_peer", raw, true);
    }

    if (res && !res.ok) {
      await showModal({ title: res.title || t("modalDefaultTitle"), message: res.message || "", level: "error" });
    } else if (res && res.ok) {
      input.value = "";
      state.selectedPeerKey = res.peer_key || "";
      showToast(t("toastPeerAdded", res.peer_key), "ok");
    }
    await refreshState();
  }

  async function handleConnectEasyTier() {
    await callApi("update_form", {
      nickname: $("input-nickname").value,
      port_text: $("input-port").value,
      room_key: $("input-room-key").value,
    });
    const rawNode = $("input-et-node").value.trim();
    if (!rawNode) {
      showToast(t("toastVpsEmpty"), "warn");
      openAddVpsModal();
      return;
    }
    const res = await callApi(
      "connect_easytier",
      rawNode,
      $("input-et-room").value,
      $("input-et-password").value
    );
    if (res && !res.ok) {
      await showModal({ title: res.title || t("modalDefaultTitle"), message: res.message || "", level: "error" });
    } else if (res && res.ok) {
      showToast(t("toastVpsConnecting"), "info");
    }
    await refreshState();
  }

  async function handleDisconnectEasyTier() {
    await callApi("disconnect_easytier");
    showToast(t("toastVpsDisconnected"), "info");
    await refreshState();
  }

  async function handleTestPeer() {
    const res = await callApi("test_peer", state.selectedPeerKey || "");
    if (res && !res.ok) {
      await showModal({ title: res.title || t("modalDefaultTitle"), message: res.message || "", level: "info" });
    } else {
      showToast(t("toastTestRunning"), "info");
    }
    await refreshState();
  }

  async function handleRemovePeer() {
    if (!state.selectedPeerKey) {
      showToast(t("toastRemoveNeedSel"), "warn");
      return;
    }
    await callApi("remove_peer", state.selectedPeerKey);
    state.selectedPeerKey = "";
    await refreshState();
  }

  async function handleStartBridge() {
    const hostKey = $("select-target-host").value || "";
    const res = await callApi("start_civ6_bridge", hostKey);
    if (res && !res.ok) {
      await showModal({ title: res.title || t("modalDefaultTitle"), message: res.message || "", level: "warn" });
    } else if (res && res.ok) {
      showToast(res.mode === "host" ? t("toastHostBridgeStarted") : t("toastClientBridgeStarted"), "ok");
    }
    await refreshState();
  }

  async function handleStopBridge() {
    await callApi("stop_civ6_bridge");
    showToast(t("toastBridgeStopped"), "info");
    await refreshState();
  }

  async function handleProbeRoom() {
    const res = await callApi("probe_host_room");
    if (res && !res.ok) {
      await showModal({ title: res.title || t("modalDefaultTitle"), message: res.message || "", level: "info" });
    } else {
      showToast(t("toastProbingRoom"), "info");
    }
    await refreshState();
  }

  function bindUiEvents() {
    $("lang-toggle").addEventListener("click", () => {
      const next = state.lang === "en" ? "zh" : "en";
      void applyLanguage(next, true);
    });

    $("theme-toggle").addEventListener("click", () => {
      const next = state.theme === "dark" ? "light" : "dark";
      void applyTheme(next, true);
    });

    $("tab-btn-step1").addEventListener("click", () => switchStep("step1"));
    $("tab-btn-step2").addEventListener("click", () => switchStep("step2", true));
    $("btn-goto-step2").addEventListener("click", () => switchStep("step2", true));

    $("role-seg").querySelectorAll(".mini-seg-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        if (btn.disabled) return;
        await callApi("update_form", { role: btn.dataset.role });
        await refreshState();
      });
    });

    $("mode-seg").querySelectorAll(".mode-seg-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        await callApi("update_form", { conn_mode: btn.dataset.mode });
        await refreshState();
      });
    });

    const syncField = (el, key) => {
      const handler = async () => {
        await callApi("update_form", { [key]: el.value });
        if (key === "nickname" || key === "selected_address" || key === "room_key") {
          await refreshState();
        }
      };
      el.addEventListener("change", handler);
      if (key === "nickname") el.addEventListener("input", handler);
    };
    syncField($("input-nickname"), "nickname");
    syncField($("input-port"), "port_text");
    syncField($("input-room-key"), "room_key");
    syncField($("input-adv-addr"), "selected_address");
    syncField($("input-et-node"), "et_node");
    syncField($("input-et-room"), "et_room");
    syncField($("input-et-password"), "et_password");
    bindPwToggle("btn-toggle-et-pw", "input-et-password");

    $("btn-start-node").addEventListener("click", handleStartNode);
    $("btn-stop-node").addEventListener("click", handleStopNode);

    $("btn-refresh-net").addEventListener("click", async () => {
      await callApi("refresh_network_info");
      showToast(t("toastNetRefreshed"), "info");
      await refreshState();
    });
    $("btn-stun-probe").addEventListener("click", handleStunProbe);
    $("btn-copy-invite").addEventListener("click", handleCopyInvite);
    $("btn-add-peer").addEventListener("click", handleAddPeer);
    $("input-peer-addr").addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        void handleAddPeer();
      }
    });

    $("btn-open-add-vps").addEventListener("click", openAddVpsModal);
    $("btn-et-connect").addEventListener("click", handleConnectEasyTier);
    $("btn-et-disconnect").addEventListener("click", handleDisconnectEasyTier);

    $("btn-test-peer").addEventListener("click", handleTestPeer);
    $("btn-remove-peer").addEventListener("click", handleRemovePeer);

    $("select-target-host").addEventListener("change", async (e) => {
      await callApi("update_form", { target_host_key: e.target.value });
      await refreshState();
    });
    $("btn-start-bridge").addEventListener("click", handleStartBridge);
    $("btn-stop-bridge").addEventListener("click", handleStopBridge);
    $("btn-probe-room").addEventListener("click", handleProbeRoom);

    $("btn-toggle-log").addEventListener("click", () => {
      const dock = $("log-dock");
      const collapsed = dock.dataset.collapsed === "true";
      dock.dataset.collapsed = String(!collapsed);
      $("btn-toggle-log").textContent = collapsed ? t("btnCollapse") : t("btnExpand");
    });
    $("btn-copy-log").addEventListener("click", async () => {
      await callApi("copy_all_logs");
      showToast(t("toastLogCopied"), "ok");
      await refreshState();
    });
    $("btn-clear-log").addEventListener("click", async () => {
      await callApi("clear_logs");
      $("log-body").innerHTML = "";
      $("log-count").textContent = "0";
    });

    window.addEventListener("resize", () => syncAllThumbs(true));
  }

  function startApp() {
    initLightFieldPhysics();
    initModalEvents();
    initAddVpsModalEvents();
    initGuideModalEvents();

    addrComboCtrl = initCombo("combo-addr", "input-adv-addr", async (val) => {
      await callApi("update_form", { selected_address: val });
      await refreshState();
    });
    vpsComboCtrl = initVpsCombo("combo-et-node", "input-et-node", {
      onSelect: async (node) => {
        const pw = (node && node.password) || "";
        $("input-et-password").value = pw;
        await callApi("update_form", { et_node: node.label, et_password: pw });
        await refreshState();
      },
      onDelete: async (node) => {
        const res = await callApi("remove_vps_node", node.id);
        if (res && res.ok) {
          showToast(t("toastVpsDeleted", node.name || node.address), "info");
          await refreshState();
        }
      },
      onAddNew: () => openAddVpsModal(),
    });

    applyStaticI18n();
    bindUiEvents();
    requestAnimationFrame(() => syncAllThumbs(true));

    const startPolling = () => {
      void refreshState();
      if (!state.pollTimer) {
        state.pollTimer = window.setInterval(refreshState, 260);
      }
    };

    if (api()) {
      startPolling();
    } else {
      window.addEventListener("pywebviewready", startPolling, { once: true });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", startApp);
  } else {
    startApp();
  }
})();
