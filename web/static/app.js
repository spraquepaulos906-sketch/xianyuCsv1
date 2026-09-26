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
loadKnowledge().catch(() => {});
loadBadcases().catch(() => {});
loadStrategy().catch(() => {});
setInterval(() => {
  loadConfig().catch(() => {});
  loadCookie().catch(() => {});
  loadConversations().catch(() => {});
  loadNetwork().catch(() => {});
}, 5000);

// ---------- 知识库（RAG） ----------
let knowledge = [];
let editingKbId = null;

async function loadKnowledge() {
  const data = await api("/api/knowledge");
  knowledge = data.entries || [];
  renderKnowledge();
}

function renderKnowledge() {
  const list = $("#kb-list");
  if (!knowledge.length) {
    list.innerHTML = `<div class="empty">知识库为空，添加 FAQ 条目后机器人回答更有据可依。</div>`;
    return;
  }
  list.innerHTML = knowledge
    .map((e) => {
      const disabled = !e.enabled;
      const tags = [];
      if (e.category) tags.push("分类：" + escapeHtml(e.category));
      if (e.keywords) tags.push("关键词：" + escapeHtml(e.keywords));
      return `
      <div class="card kb-item ${disabled ? "disabled" : ""}">
        <div class="qa">
          <div class="q">${escapeHtml(e.question)}</div>
          <div class="a">${escapeHtml(e.answer)}</div>
          ${tags.length ? `<div class="tags">${tags.join(" · ")}</div>` : ""}
        </div>
        <div class="card-actions">
          <button class="btn small" data-act="kb-edit" data-id="${e.id}">编辑</button>
          <button class="btn small" data-act="kb-toggle" data-id="${e.id}" data-enabled="${e.enabled}">${e.enabled ? "停用" : "启用"}</button>
          <button class="btn small danger" data-act="kb-del" data-id="${e.id}">删除</button>
        </div>
      </div>`;
    })
    .join("");
}

$("#kb-add-btn").addEventListener("click", async () => {
  const question = $("#kb-question").value.trim();
  const answer = $("#kb-answer").value.trim();
  if (!question || !answer) {
    alert("请填写问题与答案");
    return;
  }
  const payload = {
    question,
    answer,
    keywords: $("#kb-keywords").value.trim(),
    category: $("#kb-category").value.trim(),
  };
  try {
    if (editingKbId) {
      await api(`/api/knowledge/${editingKbId}`, { method: "PUT", body: JSON.stringify(payload) });
      editingKbId = null;
      $("#kb-add-btn").textContent = "+ 添加条目";
    } else {
      await api("/api/knowledge", { method: "POST", body: JSON.stringify(payload) });
    }
    $("#kb-question").value = "";
    $("#kb-answer").value = "";
    $("#kb-keywords").value = "";
    $("#kb-category").value = "";
    await loadKnowledge();
  } catch (err) {
    alert(err.message);
  }
});

$("#kb-list").addEventListener("click", async (e) => {
  const btn = e.target.closest("button[data-act]");
  if (!btn) return;
  const { act, id } = btn.dataset;
  try {
    if (act === "kb-edit") {
      const entry = knowledge.find((x) => x.id === Number(id));
      if (!entry) return;
      editingKbId = entry.id;
      $("#kb-question").value = entry.question;
      $("#kb-answer").value = entry.answer;
      $("#kb-keywords").value = entry.keywords || "";
      $("#kb-category").value = entry.category || "";
      $("#kb-add-btn").textContent = "保存修改";
      $("#kb-question").scrollIntoView({ behavior: "smooth", block: "center" });
    } else if (act === "kb-toggle") {
      const enabled = btn.dataset.enabled === "1" ? 0 : 1;
      await api(`/api/knowledge/${id}`, { method: "PUT", body: JSON.stringify({ enabled }) });
      await loadKnowledge();
    } else if (act === "kb-del") {
      if (!confirm("确认删除该知识条目？")) return;
      await api(`/api/knowledge/${id}`, { method: "DELETE" });
      await loadKnowledge();
    }
  } catch (err) {
    alert(err.message);
  }
});

$("#kb-refresh-btn").addEventListener("click", () =>
  loadKnowledge().catch((err) => alert("刷新失败：" + err.message))
);

// ---------- Badcase 复盘 ----------
let badcases = [];
const BADCASE_CATEGORIES = ["意图误判", "回复机械", "买家质疑", "其他"];

async function loadBadcases() {
  const data = await api("/api/badcases");
  badcases = data.badcases || [];
  renderBadcases();
}

function renderBadcases() {
  const list = $("#badcase-list");
  if (!badcases.length) {
    list.innerHTML = `<div class="empty">暂无 badcase。买家负面情绪会自动记录到这里。</div>`;
    return;
  }
  list.innerHTML = badcases
    .map((b) => {
      const statusBadge =
        b.status === "resolved"
          ? '<span class="badge green">已处理</span>'
          : '<span class="badge amber">待处理</span>';
      const sentBadge =
        b.sentiment === "negative"
          ? '<span class="badge red">负面</span>'
          : `<span class="badge gray">${escapeHtml(b.sentiment || "无情绪")}</span>`;
      const catOptions = BADCASE_CATEGORIES.map(
        (c) => `<option value="${c}" ${c === b.category ? "selected" : ""}>${c}</option>`
      ).join("");
      return `
      <div class="card bc-item">
        <div class="bc-head">
          ${statusBadge}
          <span class="badge gray">${escapeHtml(b.category || "其他")}</span>
          ${sentBadge}
          <span class="badge">${escapeHtml(b.intent || "无意图")}</span>
          <span class="card-meta" style="margin-left:auto">${escapeHtml(b.source || "")} · ${escapeHtml(formatTime(b.created_at))}</span>
        </div>
        <div class="bc-body">
          <div class="bc-line bc-user">👤 买家：${escapeHtml(b.user_msg)}</div>
          <div class="bc-line bc-bot">🤖 回复：${escapeHtml(b.bot_reply)}</div>
          ${b.note ? `<div class="bc-note">备注：${escapeHtml(b.note)}</div>` : ""}
        </div>
        <div class="bc-actions">
          <select class="bc-cat" data-id="${b.id}">
            <option value="">归类…</option>
            ${catOptions}
          </select>
          <input class="bc-note-input" data-id="${b.id}" placeholder="补充备注" value="${escapeHtml(b.note || "")}">
          <button class="btn small" data-act="bc-note" data-id="${b.id}">存备注</button>
          ${b.status !== "resolved" ? `<button class="btn small" data-act="bc-resolve" data-id="${b.id}">标记已处理</button>` : ""}
          <button class="btn small danger" data-act="bc-del" data-id="${b.id}">删除</button>
        </div>
      </div>`;
    })
    .join("");
}

$("#badcase-list").addEventListener("click", async (e) => {
  const btn = e.target.closest("button[data-act]");
  if (!btn) return;
  const { act, id } = btn.dataset;
  try {
    if (act === "bc-resolve") {
      await api(`/api/badcases/${id}`, { method: "PUT", body: JSON.stringify({ status: "resolved" }) });
      await loadBadcases();
    } else if (act === "bc-note") {
      const input = $(`.bc-note-input[data-id="${id}"]`);
      await api(`/api/badcases/${id}`, { method: "PUT", body: JSON.stringify({ note: input.value }) });
      await loadBadcases();
    } else if (act === "bc-del") {
      if (!confirm("确认删除该 badcase？")) return;
      await api(`/api/badcases/${id}`, { method: "DELETE" });
      await loadBadcases();
    }
  } catch (err) {
    alert(err.message);
  }
});

$("#badcase-list").addEventListener("change", async (e) => {
  if (!e.target.classList.contains("bc-cat")) return;
  const category = e.target.value;
  if (!category) return;
  try {
    await api(`/api/badcases/${e.target.dataset.id}`, {
      method: "PUT",
      body: JSON.stringify({ category }),
    });
    await loadBadcases();
  } catch (err) {
    alert(err.message);
  }
});

$("#badcase-refresh-btn").addEventListener("click", () =>
  loadBadcases().catch((err) => alert("刷新失败：" + err.message))
);

// ---------- 议价策略 / 行为开关 ----------
let bargainStrategy = null;
let behavior = null;

async function loadStrategy() {
  const data = await api("/api/strategy");
  bargainStrategy = data.bargain_strategy;
  behavior = data.behavior;
  renderStrategy();
}

function renderStrategy() {
  $("#bargain-enabled").checked = !!bargainStrategy.enabled;
  $("#bargain-max-ratio").value = bargainStrategy.max_discount_ratio;
  $("#auto-manual-negative").checked = !!behavior.auto_manual_on_negative;
  renderTiers();
}

function renderTiers() {
  const tiers = bargainStrategy.tiers || [];
  $("#tiers-list").innerHTML = tiers
    .map(
      (t, i) => `
    <div class="tier-row" data-idx="${i}">
      <span>第 ${escapeHtml(String(t.round))} 轮</span>
      <input type="number" step="0.01" min="0" max="1" class="tier-ratio" value="${Number(t.ratio)}" data-idx="${i}">
      <button class="btn small danger" data-act="tier-del" data-idx="${i}">删除</button>
    </div>`
    )
    .join("");
}

$("#tier-add-btn").addEventListener("click", () => {
  const tiers = bargainStrategy.tiers || [];
  const nextRound = tiers.length ? Math.max(...tiers.map((t) => t.round)) + 1 : 1;
  tiers.push({ round: nextRound, ratio: 0 });
  bargainStrategy.tiers = tiers;
  renderTiers();
});

$("#tiers-list").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-act='tier-del']");
  if (!btn) return;
  bargainStrategy.tiers.splice(Number(btn.dataset.idx), 1);
  renderTiers();
});

$("#strategy-save-btn").addEventListener("click", async () => {
  bargainStrategy.enabled = $("#bargain-enabled").checked;
  bargainStrategy.max_discount_ratio = Number($("#bargain-max-ratio").value);
  document.querySelectorAll(".tier-ratio").forEach((inp) => {
    bargainStrategy.tiers[Number(inp.dataset.idx)].ratio = Number(inp.value);
  });
  behavior.auto_manual_on_negative = $("#auto-manual-negative").checked;
  try {
    await api("/api/strategy/bargain", {
      method: "PUT",
      body: JSON.stringify(bargainStrategy),
    });
    await api("/api/strategy/behavior", {
      method: "PUT",
      body: JSON.stringify({ auto_manual_on_negative: behavior.auto_manual_on_negative }),
    });
    await loadStrategy();
    alert("策略已保存");
  } catch (err) {
    alert(err.message);
  }
});
