const PROVIDERS = {
  deepseek: { label: "DeepSeek", base_url: "https://api.deepseek.com/v1", model_name: "deepseek-chat" },
  qwen: { label: "通义千问(Qwen)", base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1", model_name: "qwen-max" },
  kimi: { label: "Kimi(Moonshot)", base_url: "https://api.moonshot.cn/v1", model_name: "moonshot-v1-8k" },
  custom: { label: "自定义", base_url: "", model_name: "" },
};

let models = [];
let editingId = null;
let conversations = [];
let selectedChatId = null;

const $ = (sel) => document.querySelector(sel);

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `请求失败 (${res.status})`);
  }
  return res.json();
}

async function loadConfig() {
  const data = await api("/api/config");
  models = data.models;
  renderModels();
  renderStatus(data.status, data.current_id);
}

function renderStatus(status, currentId) {
  const dot = $("#status-dot");
  const text = $("#status-text");
  if (status.connected) {
    dot.className = "dot online";
    text.textContent = "闲鱼已连接";
  } else {
    dot.className = "dot offline";
    text.textContent = "闲鱼未连接";
  }
  const cur = models.find((m) => m.id === currentId);
  $("#current-model").textContent = cur
    ? `当前模型：${cur.provider} / ${cur.model_name}`
    : "未选择模型";
}

function renderModels() {
  const list = $("#models-list");
  if (!models.length) {
    list.innerHTML = `<div class="empty">还没有配置模型，点击右上角“添加模型”开始。</div>`;
    return;
  }
  list.innerHTML = models
    .map((m) => {
      const isCurrent = m.is_current;
      return `
      <div class="card ${isCurrent ? "current" : ""}">
        <div class="card-main">
          <div class="card-title">
            <span class="provider">${escapeHtml(m.provider)}</span>
            ${isCurrent ? '<span class="badge">当前使用</span>' : ""}
          </div>
          <div class="card-meta">
            <span>模型：${escapeHtml(m.model_name)}</span>
            <span class="mono">${escapeHtml(m.base_url)}</span>
          </div>
          <div class="card-key">Key：${escapeHtml(m.api_key_masked || "未设置")}</div>
        </div>
        <div class="card-actions">
          ${isCurrent ? "" : `<button class="btn small" data-act="activate" data-id="${m.id}">设为当前</button>`}
          <button class="btn small" data-act="edit" data-id="${m.id}">编辑</button>
          <button class="btn small danger" data-act="delete" data-id="${m.id}">删除</button>
        </div>
      </div>`;
    })
    .join("");
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );
}

// ---------- 闲鱼 Cookie ----------
async function loadCookie() {
  const data = await api("/api/cookie");
  const status = $("#cookie-status");
  status.textContent = data.is_set ? "已配置" : "未配置";
  status.className = "cookie-status " + (data.is_set ? "ok" : "warn");
  $("#cookie-masked").textContent = data.is_set ? `当前：${data.cookie_masked}` : "";
}

$("#cookie-save-btn").addEventListener("click", async () => {
  const cookies_str = $("#cookie-input").value.trim();
  if (!cookies_str) {
    alert("请先粘贴 Cookie");
    return;
  }
  try {
    await api("/api/cookie", { method: "POST", body: JSON.stringify({ cookies_str }) });
    $("#cookie-input").value = "";
    await loadCookie();
    alert("已保存，正在连接闲鱼…");
  } catch (err) {
    alert(err.message);
  }
});

// ---------- 自动连接闲鱼 ----------
async function pollAutoStatus() {
  try {
    const st = await api("/api/cookie/auto/status");
    const msg = $("#auto-msg");
    if (st.message) {
      msg.style.display = "block";
      msg.textContent = st.message;
    }
    if (!st.running && st.done) {
      $("#cookie-auto-btn").disabled = false;
      if (st.ok) {
        msg.textContent = "✅ 已自动连接闲鱼";
        await loadCookie();
        setTimeout(() => (msg.style.display = "none"), 4000);
      } else {
        msg.textContent = "❌ " + st.message;
        alert("自动连接失败：" + st.message);
      }
      return;
    }
    setTimeout(pollAutoStatus, 1500);
  } catch (err) {
    $("#cookie-auto-btn").disabled = false;
    alert("查询自动连接状态失败：" + err.message);
  }
}

$("#cookie-auto-btn").addEventListener("click", async () => {
  try {
    await api("/api/cookie/auto", { method: "POST" });
    $("#cookie-auto-btn").disabled = true;
    const msg = $("#auto-msg");
    msg.style.display = "block";
    msg.textContent = "正在启动浏览器…请在弹出的 Edge 窗口登录闲鱼";
    pollAutoStatus();
  } catch (err) {
    alert(err.message);
  }
});

// ---------- 弹窗 ----------
function fillProviderOptions() {
  const sel = $("#provider-select");
  sel.innerHTML = Object.entries(PROVIDERS)
    .map(([k, v]) => `<option value="${k}">${v.label}</option>`)
    .join("");
  sel.value = "deepseek";
  applyPreset();
}

function applyPreset() {
  const key = $("#provider-select").value;
  const preset = PROVIDERS[key];
  if (preset.base_url) $("#base-url").value = preset.base_url;
  if (preset.model_name) $("#model-name").value = preset.model_name;
  if (!$("#provider").dataset.touched) {
    $("#provider").value = preset.label === "自定义" ? "" : preset.label;
  }
}

function openModal(model) {
  editingId = model ? model.id : null;
  $("#modal-title").textContent = model ? "编辑模型" : "添加模型";
  $("#provider").value = model ? model.provider : "";
  $("#api-key").value = "";
  $("#api-key").placeholder = model ? "留空则不修改" : "sk-...";
  $("#base-url").value = model ? model.base_url : "";
  $("#model-name").value = model ? model.model_name : "";
  delete $("#provider").dataset.touched;
  if (!model) fillProviderOptions();
  else {
    // 编辑时也填充预设下拉，但不覆盖已填值
    fillProviderOptions();
  }
  $("#modal").classList.remove("hidden");
}

function closeModal() {
  $("#modal").classList.add("hidden");
  editingId = null;
}

// ---------- 事件 ----------
$("#add-btn").addEventListener("click", () => openModal(null));
$("#cancel-btn").addEventListener("click", closeModal);
$("#modal").addEventListener("click", (e) => {
  if (e.target === $("#modal")) closeModal();
});
$("#provider-select").addEventListener("change", applyPreset);
$("#provider").addEventListener("input", () => {
  $("#provider").dataset.touched = "1";
});

$("#model-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const payload = {
    provider: $("#provider").value.trim(),
    api_key: $("#api-key").value.trim(),
    base_url: $("#base-url").value.trim(),
    model_name: $("#model-name").value.trim(),
  };
  try {
    if (editingId) {
      await api(`/api/models/${editingId}`, { method: "PUT", body: JSON.stringify(payload) });
    } else {
      await api("/api/models", { method: "POST", body: JSON.stringify(payload) });
    }
    closeModal();
    await loadConfig();
  } catch (err) {
    alert(err.message);
  }
});

$("#models-list").addEventListener("click", async (e) => {
  const btn = e.target.closest("button[data-act]");
  if (!btn) return;
  const { act, id } = btn.dataset;
  try {
    if (act === "activate") {
      await api(`/api/models/${id}/activate`, { method: "POST" });
      await loadConfig();
    } else if (act === "edit") {
      openModal(models.find((m) => m.id === id));
    } else if (act === "delete") {
      if (!confirm("确认删除该模型？")) return;
      await api(`/api/models/${id}`, { method: "DELETE" });
      await loadConfig();
    }
  } catch (err) {
    alert(err.message);
  }
});

// ---------- 对话日志 ----------
function formatTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

async function loadConversations() {
  const data = await api("/api/conversations");
  conversations = data.conversations || [];
  renderConversations();
}

function renderConversations() {
  const list = $("#conversations-list");
  if (!conversations.length) {
    list.innerHTML = `<div class="empty">暂无对话记录。有买家发消息后会自动记录。</div>`;
    return;
  }
  list.innerHTML = conversations
    .map((c) => {
      const isSelected = c.chat_id === selectedChatId;
      return `
      <div class="card conv-card ${isSelected ? "current" : ""}" data-chat="${escapeHtml(c.chat_id)}">
        <div class="card-main">
          <div class="card-title">
            <span class="provider">${escapeHtml(c.item_title || "未知商品")}</span>
            <span class="badge">${c.message_count} 条</span>
          </div>
          <div class="card-meta">
            <span>买家：${escapeHtml(c.user_id || "未知")}</span>
            <span>最近：${escapeHtml(formatTime(c.last_time))}</span>
          </div>
        </div>
        <button class="btn small" data-act="view" data-chat="${escapeHtml(c.chat_id)}">查看</button>
      </div>`;
    })
    .join("");
}

async function loadConversationDetail(chatId) {
  const data = await api(`/api/conversations/${encodeURIComponent(chatId)}`);
  selectedChatId = chatId;
  renderConversationDetail(data);
  renderConversations();
}

function renderConversationDetail(data) {
  const box = $("#conversation-detail");
  box.classList.remove("hidden");
  const msgs = data.messages || [];
  if (!msgs.length) {
    box.innerHTML = `
      <div class="detail-head"><button class="btn small" data-act="close-detail">← 返回列表</button></div>
      <div class="empty">该会话暂无消息</div>`;
    return;
  }
  const body = msgs
    .map((m) => {
      const isUser = m.role === "user";
      const who = isUser ? "买家" : "卖家/机器人";
      return `
      <div class="msg ${isUser ? "user" : "assistant"}">
        <div class="msg-meta">${who} · ${escapeHtml(formatTime(m.timestamp))}</div>
        <div class="msg-bubble">${escapeHtml(m.content)}</div>
      </div>`;
    })
    .join("");
  box.innerHTML = `
    <div class="detail-head"><button class="btn small" data-act="close-detail">← 返回列表</button></div>
    <div class="msg-list">${body}</div>`;
}

$("#logs-refresh-btn").addEventListener("click", () => {
  loadConversations().catch((err) => alert("刷新失败：" + err.message));
});

$("#conversations-list").addEventListener("click", async (e) => {
  const viewBtn = e.target.closest("button[data-act='view']");
  const card = e.target.closest(".conv-card");
  const chatId = (viewBtn && viewBtn.dataset.chat) || (card && card.dataset.chat);
  if (!chatId) return;
  try {
    await loadConversationDetail(chatId);
  } catch (err) {
    alert("加载会话失败：" + err.message);
  }
});

$("#conversation-detail").addEventListener("click", (e) => {
  if (e.target.closest("button[data-act='close-detail']")) {
    selectedChatId = null;
    $("#conversation-detail").classList.add("hidden");
    renderConversations();
  }
});

// ---------- 网络访问 ----------
async function loadNetwork() {
  const data = await api("/api/network");
  $("#lan-toggle").checked = data.lan_enabled;
  const status = $("#network-status");
  status.textContent = data.lan_enabled ? "局域网已开启" : "仅本机";
  status.className = "cookie-status " + (data.lan_enabled ? "ok" : "warn");
  const url = $("#lan-url");
  if (data.lan_enabled && data.lan_url) {
    url.style.display = "block";
    url.textContent = "局域网访问地址：" + data.lan_url;
  } else {
    url.style.display = "none";
  }
}

$("#lan-toggle").addEventListener("change", async (e) => {
  const lan_enabled = e.target.checked;
  try {
    const res = await api("/api/network", {
      method: "POST",
      body: JSON.stringify({ lan_enabled }),
    });
    if (res.changed) {
      alert(
        lan_enabled
          ? `已开启局域网访问，其他设备可通过 ${res.lan_url || "本机 IP"} 访问`
          : "已关闭局域网访问，仅本机可访问"
      );
    }
    await loadNetwork();
  } catch (err) {
    e.target.checked = !lan_enabled;
    alert("切换失败：" + err.message);
  }
});

// 首次加载 + 定期刷新状态
loadConfig().catch((err) => alert("加载失败：" + err.message));
loadCookie().catch(() => {});
loadConversations().catch(() => {});
loadNetwork().catch(() => {});
setInterval(() => {
  loadConfig().catch(() => {});
  loadCookie().catch(() => {});
  loadConversations().catch(() => {});
  loadNetwork().catch(() => {});
}, 5000);
