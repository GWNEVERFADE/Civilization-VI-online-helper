/* ==========================================================================
   CV6 online helper — HyperOS 4 Soft-Glow Glass Frontend Controller
   ========================================================================== */

(() => {
  "use strict";

  const state = {
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
    modalResolve: null,
  };

  // -------------------- Helpers --------------------
  const $ = (id) => document.getElementById(id);

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
      return { ok: false, title: "调用异常", message: String(err) };
    }
  }

  // -------------------- HyperOS 4 Light-Field Physics --------------------
  function initLightFieldPhysics() {
    // 1. Cursor-tracking specular light sheen on glass cards
    document.addEventListener("pointermove", (e) => {
      const card = e.target.closest(".glass-card");
      if (!card) return;
      const rect = card.getBoundingClientRect();
      const x = ((e.clientX - rect.left) / rect.width) * 100;
      const y = ((e.clientY - rect.top) / rect.height) * 100;
      card.style.setProperty("--mx", `${x.toFixed(1)}%`);
      card.style.setProperty("--my", `${y.toFixed(1)}%`);
    }, { passive: true });

    // 2. "点按有光" Luminous radial bloom on click
    document.addEventListener("pointerdown", (e) => {
      const target = e.target.closest(".light-interactive");
      if (!target || target.disabled) return;
      const rect = target.getBoundingClientRect();
      const bloom = document.createElement("span");
      bloom.className = "light-bloom";
      bloom.style.left = `${e.clientX - rect.left}px`;
      bloom.style.top = `${e.clientY - rect.top}px`;
      target.appendChild(bloom);
      window.setTimeout(() => bloom.remove(), 580);
    }, { passive: true });

    // Disable browser context menu outside editable inputs & logs
    document.addEventListener("contextmenu", (e) => {
      if (e.target.closest("input, textarea, .log-body, .modal-message")) return;
      e.preventDefault();
    });
  }

  // -------------------- Sliding Segmented Thumbs --------------------
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
      [$("step-thumb"), $("role-thumb"), $("mode-thumb")].forEach((t) => {
        if (t) delete t.dataset.pos;
      });
    }
    positionStepThumb();
    const roleSeg = $("role-seg");
    positionThumb(roleSeg, $("role-thumb"), roleSeg.querySelector(".is-active"));
    const modeSeg = $("mode-seg");
    positionThumb(modeSeg, $("mode-thumb"), modeSeg.querySelector(".is-active"));
  }

  // -------------------- Toast & Frosted Glass Modal --------------------
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

  function showModal({ title = "提示", message = "", level = "info", confirmText = "确定", cancelText = "" }) {
    return new Promise((resolve) => {
      const backdrop = $("modal-backdrop");
      const badge = $("modal-badge");
      const cancelBtn = $("modal-cancel");
      const confirmBtn = $("modal-confirm");

      badge.dataset.level = level;
      badge.textContent = level === "ok" ? "✓" : level === "warn" ? "!" : level === "error" ? "×" : "i";
      $("modal-title").textContent = title;
      $("modal-message").textContent = message;
      confirmBtn.textContent = confirmText;

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

  // -------------------- Custom Frosted Comboboxes --------------------
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
        const keySig = items.map((x) => x.label).join("||");
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
        const sig = JSON.stringify(list) + "|" + (currentValue || "");
        if (menu.dataset.sig === sig) return;
        menu.dataset.sig = sig;
        menu.innerHTML = "";

        if (list.length === 0) {
          const empty = document.createElement("div");
          empty.className = "combo-empty-vps";
          const tip = document.createElement("span");
          tip.textContent = "尚未保存自定义 VPS 节点，请先添加您的自建节点";
          const addBtn = document.createElement("button");
          addBtn.type = "button";
          addBtn.className = "glass-btn btn-xs btn-accent light-interactive";
          addBtn.textContent = "+ 立即添加 VPS 节点";
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
          mainBtn.innerHTML =
            `<span class="combo-vps-top">` +
            `<span class="combo-vps-name">${escapeHtml(node.name || node.address)}</span>` +
            `<span class="vps-kind-pill ${escapeHtml(node.kind || "easytier")}">${escapeHtml(node.kind_label || "EasyTier")}</span>` +
            `</span>` +
            `<span class="combo-vps-addr">${escapeHtml(node.address)}</span>`;
          mainBtn.addEventListener("click", () => {
            input.value = node.label;
            close();
            onSelect(node.label);
          });

          const delBtn = document.createElement("button");
          delBtn.type = "button";
          delBtn.className = "combo-vps-del";
          delBtn.title = "删除该自定义 VPS 节点";
          delBtn.setAttribute("aria-label", "删除节点");
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

  // -------------------- Add Custom VPS Modal --------------------
  let vpsDraftKind = "easytier";

  function syncVpsKindUi() {
    const seg = $("vps-kind-seg");
    seg.querySelectorAll(".vps-kind-btn").forEach((btn) => {
      btn.classList.toggle("is-active", btn.dataset.kind === vpsDraftKind);
    });
    positionThumb(seg, $("vps-kind-thumb"), seg.querySelector(".is-active"));

    const addrInput = $("vps-input-address");
    const hint = $("vps-addr-hint");
    if (vpsDraftKind === "udp_relay") {
      addrInput.placeholder = "1.2.3.4:38668 或 relay.example.com:38668 或 [240e::1]:38668";
      hint.innerHTML =
        "适配 <code>civ6_relay_server.py</code> 轻量 UDP 中继，支持 IPv4 / IPv6 / 域名，未填端口默认 38668。";
    } else {
      addrInput.placeholder = "tcp://1.2.3.4:11010 或 udp://vps.example.com:11010";
      hint.innerHTML =
        "支持 <code>tcp://ip:11010</code>、<code>udp://ip:11010</code>、<code>ip:11010</code>，或多个备用 VPS 用逗号分隔；未填端口默认 11010。";
    }
  }

  function openAddVpsModal() {
    $("vps-input-name").value = "";
    $("vps-input-address").value = "";
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
    const errEl = $("vps-form-error");
    errEl.hidden = true;

    const res = await callApi("add_vps_node", name, address, vpsDraftKind);
    if (!res || !res.ok) {
      errEl.textContent = (res && res.message) || "请输入有效的 VPS 节点地址";
      errEl.hidden = false;
      $("vps-input-address").focus();
      return;
    }
    closeAddVpsModal();
    if (res.node && res.node.label) {
      $("input-et-node").value = res.node.label;
    }
    showToast(`已保存 VPS 节点：${res.node ? res.node.name : address}`, "ok");
    await refreshState();
  }

  function initAddVpsModalEvents() {
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
    $("vps-input-address").addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        void saveCustomVpsNode();
      }
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && !$("vps-modal-backdrop").hidden) {
        closeAddVpsModal();
      }
    });
  }

  // -------------------- P2P & VPS Usage Guide Modal --------------------
  let activeGuideTab = "p2p";

  function switchGuideTab(tab) {
    activeGuideTab = tab === "vps" ? "vps" : "p2p";
    const seg = $("guide-seg");
    seg.querySelectorAll(".guide-seg-btn").forEach((btn) => {
      btn.classList.toggle("is-active", btn.dataset.guideTab === activeGuideTab);
    });
    positionThumb(seg, $("guide-thumb"), seg.querySelector(".is-active"));
    $("guide-panel-p2p").classList.toggle("is-active", activeGuideTab === "p2p");
    $("guide-panel-vps").classList.toggle("is-active", activeGuideTab === "vps");
    $("guide-modal-title").textContent = activeGuideTab === "vps" ? "VPS 中继使用说明" : "P2P 直连使用说明";
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
    document.querySelectorAll(".guide-copy-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const cmd = btn.dataset.copy || "";
        if (!cmd) return;
        await callApi("copy_text", cmd, "");
        showToast("已复制部署命令到剪贴板", "ok");
      });
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && !$("guide-modal-backdrop").hidden) {
        closeGuideModal();
      }
    });
  }

  // -------------------- Step Switching --------------------
  function switchStep(stepName, shakeIfLocked = true) {
    if (stepName === "step2") {
      const unlocked = state.latest && state.latest.gate && state.latest.gate.step2_unlocked;
      if (!unlocked) {
        if (shakeIfLocked) {
          const btn = $("tab-btn-step2");
          btn.classList.remove("shake");
          void btn.offsetWidth;
          btn.classList.add("shake");
          const reason = (state.latest && state.latest.gate && state.latest.gate.reason) || "请先完成第一步连接测试并确保至少 2 人在线";
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

  // -------------------- Theme Switching --------------------
  async function applyTheme(theme, persistBackend = false) {
    const clean = theme === "dark" ? "dark" : "light";
    state.theme = clean;
    document.documentElement.classList.add("theme-switching");
    document.documentElement.setAttribute("data-theme", clean);
    $("theme-icon").textContent = clean === "dark" ? "☾" : "☀";
    $("theme-label").textContent = clean === "dark" ? "暮夜" : "晨曦";
    void document.documentElement.offsetHeight;
    document.documentElement.classList.remove("theme-switching");
    if (persistBackend) {
      await callApi("set_theme", clean);
    }
  }

  // -------------------- Render State Snapshot --------------------
  function setInputIfUnfocused(el, val) {
    if (!el || document.activeElement === el) return;
    if (el.value !== val) el.value = val;
  }

  function renderBadges(data) {
    const bIpv6 = $("badge-ipv6");
    bIpv6.dataset.tone = data.ipv6_ready ? "ok" : "warn";
    bIpv6.querySelector(".status-val").textContent = data.ipv6_ready ? "公网就绪" : "无公网";

    const bNode = $("badge-node");
    bNode.dataset.tone = data.node_running ? "ok" : "neutral";
    bNode.querySelector(".status-val").textContent = data.node_running ? `运行中 :${data.actual_port}` : "未启动";

    const bOnline = $("badge-online");
    const total = data.gate.total_online;
    bOnline.dataset.tone = total >= 2 ? "ok" : total === 1 ? "warn" : "neutral";
    bOnline.querySelector(".status-val").textContent = `${total} 人`;

    const bCiv6 = $("badge-civ6");
    bCiv6.dataset.tone = data.civ6_running ? "ok" : "neutral";
    bCiv6.querySelector(".status-val").textContent = data.civ6_summary;

    // Update ambient light-field mood
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

    const sig = JSON.stringify(peers) + "|" + state.selectedPeerKey;
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
        handleTestPeer();
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
    // Keep DOM compact
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
          title: ev.payload.title || "提示",
          message: ev.payload.message || "",
          level: ev.payload.level || "info",
        });
      } else if (ev.kind === "test_passed") {
        const p = ev.payload;
        const go = await showModal({
          title: "第一步连接测试成功",
          level: "ok",
          message:
            `已与 ${p.peer_key} 连通测试通过！\n\n` +
            `测试结果：${p.summary}\n` +
            `当前在线人数：${p.total_online} 人（满足 ≥ 2 人要求）\n\n` +
            "「第二步 · 文明6 联机辅助」已解锁，是否立即进入？",
          confirmText: "立即进入第二步",
          cancelText: "稍后",
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

    if (!state.initializedForm) {
      state.initializedForm = true;
      $("input-nickname").value = data.nickname;
      $("input-port").value = data.port_text;
      $("input-room-key").value = data.room_key;
      $("input-adv-addr").value = data.selected_address;
      $("input-et-node").value = data.et_node;
      $("input-et-room").value = data.et_room;
    } else {
      setInputIfUnfocused($("input-port"), data.port_text);
      setInputIfUnfocused($("input-room-key"), data.room_key);
      setInputIfUnfocused($("input-adv-addr"), data.selected_address);
      setInputIfUnfocused($("input-et-node"), data.et_node);
      setInputIfUnfocused($("input-et-room"), data.et_room);
    }

    renderBadges(data);

    // Role switcher
    const roleSeg = $("role-seg");
    roleSeg.querySelectorAll(".mini-seg-btn").forEach((btn) => {
      btn.classList.toggle("is-active", btn.dataset.role === data.role);
      btn.disabled = data.role_locked;
    });
    positionThumb(roleSeg, $("role-thumb"), roleSeg.querySelector(".is-active"));

    // Node inputs & buttons
    $("input-port").disabled = data.node_running;
    $("input-room-key").disabled = data.node_running;
    $("btn-start-node").disabled = data.node_running;
    $("btn-stop-node").disabled = !data.node_running;

    // Mode switcher & panels
    const modeSeg = $("mode-seg");
    modeSeg.querySelectorAll(".mode-seg-btn").forEach((btn) => {
      btn.classList.toggle("is-active", btn.dataset.mode === data.conn_mode);
    });
    positionThumb(modeSeg, $("mode-thumb"), modeSeg.querySelector(".is-active"));
    $("panel-p2p").classList.toggle("is-active", data.conn_mode === "p2p_ipv6");
    $("panel-relay").classList.toggle("is-active", data.conn_mode === "relay");

    // P2P fields
    addrComboCtrl.setItems(data.address_choices || [], data.selected_address);
    $("input-invite-code").value = data.invite_code || "";
    $("btn-stun-probe").disabled = data.stun_busy;
    $("btn-stun-probe").textContent = data.stun_busy ? "STUN 检测中..." : "STUN 公网检测";

    // Custom VPS Relay fields
    vpsComboCtrl.setNodes(data.vps_nodes || [], data.et_node);
    vpsComboCtrl.setDisabled(data.et_connected_or_running);
    $("btn-open-add-vps").disabled = data.et_connected_or_running;
    $("input-et-room").disabled = data.et_connected_or_running;
    $("btn-et-connect").disabled = data.et_connected_or_running;
    $("btn-et-connect").textContent = data.et_connecting ? "正在连接 VPS..." : "连接 VPS 房间";
    $("btn-et-disconnect").disabled = !data.et_connected_or_running;
    $("et-status-bar").dataset.level = data.et_status_level || "idle";
    $("et-status-text").textContent = data.et_status || "";

    // Peer table & actions
    $("btn-test-peer").disabled = data.test_busy;
    $("btn-test-peer").textContent = data.test_busy ? "测试中..." : "测试选中连接";
    renderPeers(data.peers || []);

    // Strict Step 2 gate
    const gate = data.gate;
    const step2Tab = $("tab-btn-step2");
    step2Tab.classList.toggle("is-locked", !gate.step2_unlocked);
    step2Tab.classList.toggle("is-unlocked", gate.step2_unlocked);
    $("step2-tab-sub").textContent = gate.step2_unlocked
      ? `✅ 在线 ${gate.total_online} 人 · 已解锁`
      : "🔒 待第一步连通解锁";
    $("step2-lock-chip").textContent = gate.step2_unlocked ? `在线 ${gate.total_online} 人` : "未解锁";

    if (!gate.step2_unlocked && state.activeStep === "step2") {
      switchStep("step1", false);
      showToast("在线人数不足 2 人或尚未测试通过，第二步已重新锁定", "warn");
    }

    const banner = $("gate-banner");
    banner.dataset.unlocked = String(Boolean(gate.can_enter_step2));
    $("gate-reason").textContent = gate.reason;
    $("btn-goto-step2").disabled = !gate.step2_unlocked;

    // Step 2 details
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
      $("civ6-role-desc").textContent =
        "当前角色：房主。在文明6创建「局域网」房间后，点「启动房主联机桥接」即可服务所有在线好友（至少 2 人在线方可开启）。";
      $("target-host-label").textContent = "当前模式";
      $("btn-start-bridge-text").textContent = "启动房主联机桥接";
      hostSel.disabled = true;
      if (hostSel.dataset.mode !== "host") {
        hostSel.dataset.mode = "host";
        hostSel.innerHTML = `<option value="">房主模式（自动服务所有已在线好友）</option>`;
      }
    } else {
      $("civ6-role-desc").textContent =
        "当前角色：加入者。选择已连通测试通过的房主节点并启动辅助后，回文明6「多人游戏 → 局域网」刷新即可看到房间并直接加入。";
      $("target-host-label").textContent = "目标房主节点";
      $("btn-start-bridge-text").textContent = "启动加入者联机辅助";
      hostSel.disabled = s2.active_bridge;
      const hosts = s2.target_hosts || [];
      const hSig = "client:" + JSON.stringify(hosts);
      if (hostSel.dataset.mode !== hSig) {
        hostSel.dataset.mode = hSig;
        hostSel.innerHTML = "";
        if (hosts.length === 0) {
          const opt = document.createElement("option");
          opt.value = "";
          opt.textContent = "暂无已通过测试的在线房主";
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
    $("btn-probe-room").textContent = s2.probe_busy ? "正在探测房间..." : "探测房主文明6房间";

    $("bridge-status-pill").dataset.active = String(Boolean(s2.active_bridge));
    $("bridge-status-text").textContent = s2.bridge_status;
    $("stat-disc").textContent = `请求 ${s2.disc_reqs} / 回包 ${s2.disc_resps}`;
    $("stat-tx").textContent = `${s2.tx_pkts} 包 (${s2.tx_bytes})`;
    $("stat-rx").textContent = `${s2.rx_pkts} 包 (${s2.rx_bytes})`;
    $("bridge-activity-text").textContent = s2.bridge_activity;

    // Logs & events
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

  // -------------------- User Actions --------------------
  async function handleStartNode() {
    const res = await callApi(
      "start_node",
      state.latest ? state.latest.role : "client",
      $("input-nickname").value,
      $("input-port").value,
      $("input-room-key").value
    );
    if (res && !res.ok) {
      await showModal({ title: res.title || "启动失败", message: res.message || "", level: "error" });
    } else if (res && res.ok) {
      showToast(`节点已启动，监听 UDP :${res.actual_port}`, "ok");
    }
    await refreshState();
  }

  async function handleStopNode() {
    await callApi("stop_node");
    showToast("已停止本机节点", "info");
    await refreshState();
  }

  async function handleCopyInvite() {
    const res = await callApi("copy_invite_code");
    if (res && !res.ok) {
      await showModal({ title: res.title || "提示", message: res.message || "", level: "info" });
    } else if (res && res.ok) {
      showToast("已复制本机连接码到剪贴板", "ok");
    }
    await refreshState();
  }

  async function handleStunProbe() {
    const res = await callApi("run_stun_probe");
    if (res && !res.ok) {
      await showModal({ title: res.title || "提示", message: res.message || "", level: "info" });
    } else {
      showToast("正在执行 STUN 公网地址检测...", "info");
    }
    await refreshState();
  }

  async function handleAddPeer() {
    const input = $("input-peer-addr");
    const raw = input.value.trim();
    if (!raw) {
      showToast("请输入或粘贴对方的连接码 / IP 地址", "warn");
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
        title: "房间口令不一致",
        level: "warn",
        message: `对方连接码口令为「${res.remote_key}」，与本机「${res.local_key}」不同。\n\n是否重启本机节点以同步口令？`,
        confirmText: "重启并同步口令",
        cancelText: "取消",
      });
      if (!ok) return;
      res = await callApi("add_peer", raw, true);
    }

    if (res && !res.ok) {
      await showModal({ title: res.title || "地址格式错误", message: res.message || "", level: "error" });
    } else if (res && res.ok) {
      input.value = "";
      state.selectedPeerKey = res.peer_key || "";
      showToast(`已添加节点 ${res.peer_key}，正在发起连接...`, "ok");
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
      showToast("请先添加或输入自建 VPS 节点地址", "warn");
      openAddVpsModal();
      return;
    }
    const res = await callApi("connect_easytier", rawNode, $("input-et-room").value);
    if (res && !res.ok) {
      await showModal({ title: res.title || "参数错误", message: res.message || "", level: "error" });
    } else if (res && res.ok) {
      showToast("正在连接自定义 VPS 中继通道...", "info");
    }
    await refreshState();
  }

  async function handleDisconnectEasyTier() {
    await callApi("disconnect_easytier");
    showToast("已断开 VPS 中继连接", "info");
    await refreshState();
  }

  async function handleTestPeer() {
    const res = await callApi("test_peer", state.selectedPeerKey || "");
    if (res && !res.ok) {
      await showModal({ title: res.title || "提示", message: res.message || "", level: "info" });
    } else {
      showToast("正在执行连通与 1150B 大包测试...", "info");
    }
    await refreshState();
  }

  async function handleRemovePeer() {
    if (!state.selectedPeerKey) {
      showToast("请先在成员列表中选中要移除的节点", "warn");
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
      await showModal({ title: res.title || "无法开启联机辅助", message: res.message || "", level: "warn" });
    } else if (res && res.ok) {
      showToast(res.mode === "host" ? "房主文明6联机桥接已启动" : "加入者文明6联机辅助已启动", "ok");
    }
    await refreshState();
  }

  async function handleStopBridge() {
    await callApi("stop_civ6_bridge");
    showToast("已停止文明6联机辅助", "info");
    await refreshState();
  }

  async function handleProbeRoom() {
    const res = await callApi("probe_host_room");
    if (res && !res.ok) {
      await showModal({ title: res.title || "提示", message: res.message || "", level: "info" });
    } else {
      showToast("正在探测房主文明6房间...", "info");
    }
    await refreshState();
  }

  // -------------------- Bind Events --------------------
  function bindUiEvents() {
    // Theme toggle
    $("theme-toggle").addEventListener("click", () => {
      const next = state.theme === "dark" ? "light" : "dark";
      void applyTheme(next, true);
    });

    // Two-step dock
    $("tab-btn-step1").addEventListener("click", () => switchStep("step1"));
    $("tab-btn-step2").addEventListener("click", () => switchStep("step2", true));
    $("btn-goto-step2").addEventListener("click", () => switchStep("step2", true));

    // Role switcher
    $("role-seg").querySelectorAll(".mini-seg-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        if (btn.disabled) return;
        await callApi("update_form", { role: btn.dataset.role });
        await refreshState();
      });
    });

    // Mode switcher
    $("mode-seg").querySelectorAll(".mode-seg-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        await callApi("update_form", { conn_mode: btn.dataset.mode });
        await refreshState();
      });
    });

    // Identity inputs live sync
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

    // Node buttons
    $("btn-start-node").addEventListener("click", handleStartNode);
    $("btn-stop-node").addEventListener("click", handleStopNode);

    // P2P controls
    $("btn-refresh-net").addEventListener("click", async () => {
      await callApi("refresh_network_info");
      showToast("已刷新本机网络地址", "info");
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

    // Custom VPS Relay controls
    $("btn-open-add-vps").addEventListener("click", openAddVpsModal);
    $("btn-et-connect").addEventListener("click", handleConnectEasyTier);
    $("btn-et-disconnect").addEventListener("click", handleDisconnectEasyTier);

    // Peers controls
    $("btn-test-peer").addEventListener("click", handleTestPeer);
    $("btn-remove-peer").addEventListener("click", handleRemovePeer);

    // Step 2 controls
    $("select-target-host").addEventListener("change", async (e) => {
      await callApi("update_form", { target_host_key: e.target.value });
      await refreshState();
    });
    $("btn-start-bridge").addEventListener("click", handleStartBridge);
    $("btn-stop-bridge").addEventListener("click", handleStopBridge);
    $("btn-probe-room").addEventListener("click", handleProbeRoom);

    // Log controls
    $("btn-toggle-log").addEventListener("click", () => {
      const dock = $("log-dock");
      const collapsed = dock.dataset.collapsed === "true";
      dock.dataset.collapsed = String(!collapsed);
      $("btn-toggle-log").textContent = collapsed ? "收起" : "展开";
    });
    $("btn-copy-log").addEventListener("click", async () => {
      await callApi("copy_all_logs");
      showToast("已复制运行日志到剪贴板", "ok");
      await refreshState();
    });
    $("btn-clear-log").addEventListener("click", async () => {
      await callApi("clear_logs");
      $("log-body").innerHTML = "";
      $("log-count").textContent = "0";
    });

    window.addEventListener("resize", () => syncAllThumbs(true));
  }

  // -------------------- Bootstrap --------------------
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
      onSelect: async (val) => {
        await callApi("update_form", { et_node: val });
        await refreshState();
      },
      onDelete: async (node) => {
        const res = await callApi("remove_vps_node", node.id);
        if (res && res.ok) {
          showToast(`已删除 VPS 节点：${node.name || node.address}`, "info");
          await refreshState();
        }
      },
      onAddNew: () => openAddVpsModal(),
    });

    bindUiEvents();
    requestAnimationFrame(syncAllThumbs);

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
