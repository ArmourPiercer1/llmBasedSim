const state = {
  current: null,
  storyKeys: new Set(),
  saves: [],
  settings: loadSettings(),
};

const commands = [
  { cmd: "/help", label: "查看帮助" },
  { cmd: "/status", label: "数值状态" },
  { cmd: "/idid", label: "本回合行为" },
  { cmd: "/see", label: "视觉信息" },
  { cmd: "/hear", label: "听觉信息" },
  { cmd: "/feel", label: "触觉/嗅觉" },
  { cmd: "/save ", label: "保存进度" },
  { cmd: "/stop", label: "终止长行动" },
];

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

const els = {
  app: $("#app"),
  worldTitle: $("#worldTitle"),
  worldSubtitle: $("#worldSubtitle"),
  timeDisplay: $("#timeDisplay"),
  weatherDisplay: $("#weatherDisplay"),
  tickDisplay: $("#tickDisplay"),
  startScreen: $("#startScreen"),
  storyStream: $("#storyStream"),
  loadingPanel: $("#loadingPanel"),
  commandForm: $("#commandForm"),
  commandInput: $("#commandInput"),
  sendButton: $("#sendButton"),
  slashMenu: $("#slashMenu"),
  rightPanel: $("#rightPanel"),
  toggleStatus: $("#toggleStatus"),
  playerName: $("#playerName"),
  attributeList: $("#attributeList"),
  npcList: $("#npcList"),
  eventLog: $("#eventLog"),
  debugCard: $("#debugCard"),
  modalBackdrop: $("#modalBackdrop"),
  modalTitle: $("#modalTitle"),
  modalBody: $("#modalBody"),
  closeModal: $("#closeModal"),
  settingsDrawer: $("#settingsDrawer"),
  closeSettings: $("#closeSettings"),
};

init();

async function init() {
  applySettings();
  bindEvents();
  const data = await api("/api/state");
  if (data.started) {
    renderState(data, { appendStory: true });
  } else {
    els.app.classList.remove("is-loading");
  }
}

function bindEvents() {
  $$('[data-start-mode]').forEach((button) => {
    button.addEventListener("click", () => startGame(button.dataset.startMode));
  });

  els.commandForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const text = els.commandInput.value.trim();
    if (!text) return;
    await sendAction(text);
  });

  els.commandInput.addEventListener("input", () => {
    autoGrow(els.commandInput);
    updateSlashMenu();
  });

  els.commandInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      els.commandForm.requestSubmit();
    }
    if (event.key === "Escape") {
      hideSlashMenu();
    }
  });

  $$('[data-command]').forEach((button) => {
    button.addEventListener("click", () => sendAction(button.dataset.command));
  });

  els.toggleStatus.addEventListener("click", () => {
    const collapsed = !els.rightPanel.classList.toggle("collapsed");
    state.settings.statusExpanded = collapsed;
    saveSettings();
  });

  $("#quickSave").addEventListener("click", () => promptSave());
  $("#openSaveList").addEventListener("click", () => showSaveList());
  $("#startFromSave").addEventListener("click", () => showSaveList());
  $("#openSettings").addEventListener("click", () => els.settingsDrawer.classList.remove("hidden"));
  $("#openHelp").addEventListener("click", () => showHelp());
  els.closeSettings.addEventListener("click", () => els.settingsDrawer.classList.add("hidden"));
  els.closeModal.addEventListener("click", closeModal);
  els.modalBackdrop.addEventListener("click", (event) => {
    if (event.target === els.modalBackdrop) closeModal();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeModal();
      els.settingsDrawer.classList.add("hidden");
    }
  });

  bindSetting("fontSize", "fontSize", Number);
  bindSetting("lineHeight", "lineHeight", Number);
  bindSetting("storyWidth", "storyWidth", Number);
  bindSetting("showAttributes", "showAttributes", Boolean);
  bindSetting("showSensors", "showSensors", Boolean);
  bindSetting("debugMode", "debugMode", Boolean);
  bindSetting("simpleMode", "simpleMode", Boolean);
}

function bindSetting(id, key, caster) {
  const el = $("#" + id);
  if (!el) return;
  if (el.type === "checkbox") {
    el.checked = Boolean(state.settings[key]);
    el.addEventListener("change", () => {
      state.settings[key] = el.checked;
      saveSettings();
      applySettings();
      if (state.current) renderState(state.current, { appendStory: false });
    });
  } else {
    el.value = state.settings[key];
    el.addEventListener("input", () => {
      state.settings[key] = caster(el.value);
      saveSettings();
      applySettings();
    });
  }
}

async function startGame(mode, savePath = null) {
  setBusy(true);
  try {
    const data = await api("/api/start", {
      method: "POST",
      body: JSON.stringify({ mode, save_path: savePath }),
    });
    state.storyKeys.clear();
    els.storyStream.innerHTML = "";
    renderState(data, { appendStory: true });
  } catch (error) {
    showModal("启动失败", [error.message]);
  } finally {
    setBusy(false);
  }
}

async function sendAction(text) {
  if (!state.current?.started && !text.startsWith("/")) {
    showModal("游戏尚未开始", ["请先从左侧菜单或启动页选择一个开局。"]);
    return;
  }
  setBusy(true);
  hideSlashMenu();
  try {
    const data = await api("/api/action", {
      method: "POST",
      body: JSON.stringify({ input: text }),
    });
    els.commandInput.value = "";
    autoGrow(els.commandInput);
    renderState(data, { appendStory: !text.startsWith("/") });
    if (data.modal) showModal(data.modal.title, data.modal.items);
    if (data.message) showToast(data.message);
  } catch (error) {
    showModal("操作失败", [error.message]);
  } finally {
    setBusy(false);
  }
}

function renderState(data, { appendStory }) {
  state.current = data;
  els.app.classList.remove("is-loading");
  els.startScreen.classList.toggle("hidden", data.started);

  els.worldTitle.textContent = data.world_name || "互动模拟游戏";
  els.worldSubtitle.textContent = data.world_description || "多 Agent 推演世界";
  els.tickDisplay.textContent = data.tick ?? 0;
  els.timeDisplay.textContent = formatGameTime(data);
  els.weatherDisplay.textContent = [data.time_of_day, data.weather, formatTemperature(data.temperature_c)].filter(Boolean).join(" · ") || "环境未知";
  els.playerName.textContent = data.player?.name || "玩家";

  renderAttributes(data.player_attributes || []);
  renderNpcs(data.npc_dynamics || []);
  renderEvents(data.recent_events || []);

  if (appendStory && data.narrative) {
    appendStoryEntry(data);
  }

  els.sendButton.disabled = !data.can_continue;
  els.commandInput.disabled = !data.can_continue;
  if (!data.can_continue && data.started) {
    els.commandInput.placeholder = "游戏已结束";
  }
}

function appendStoryEntry(data) {
  const key = `${data.tick}:${data.narrative}`;
  if (state.storyKeys.has(key)) return;
  state.storyKeys.add(key);
  const template = $("#storyTemplate");
  const fragment = template.content.cloneNode(true);
  fragment.querySelector(".entry-meta").textContent = `TURN ${data.tick} · ${formatGameTime(data)}`;
  fragment.querySelector(".entry-text").textContent = data.narrative;
  els.storyStream.appendChild(fragment);
  requestAnimationFrame(() => window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" }));
}

function renderAttributes(attributes) {
  els.attributeList.innerHTML = "";
  if (!state.settings.showAttributes) {
    els.attributeList.innerHTML = '<div class="npc-action">已在显示设置中隐藏。</div>';
    return;
  }
  if (!attributes.length) {
    els.attributeList.innerHTML = '<div class="npc-action">暂无可见数值。</div>';
    return;
  }
  for (const attr of attributes) {
    const row = document.createElement("div");
    row.className = "attribute-item";
    row.innerHTML = `<span>${escapeHtml(attr.name)}</span><span class="attribute-value">${escapeHtml(formatAttribute(attr))}</span>`;
    els.attributeList.appendChild(row);
  }
}

function renderNpcs(npcs) {
  els.npcList.innerHTML = "";
  if (!npcs.length) {
    els.npcList.innerHTML = '<div class="npc-action">附近没有 NPC 动态。</div>';
    return;
  }
  for (const npc of npcs) {
    const item = document.createElement("div");
    item.className = "npc-item";
    item.innerHTML = `<div class="npc-name">${escapeHtml(npc.name)}</div><div class="npc-action">${escapeHtml(npc.action)}</div>`;
    els.npcList.appendChild(item);
  }
}

function renderEvents(events) {
  els.debugCard.classList.toggle("hidden", !state.settings.debugMode);
  els.eventLog.textContent = events.join("\n");
}

function formatAttribute(attr) {
  const value = formatNumber(attr.value);
  const max = attr.max === null || attr.max === undefined ? "" : `/${formatNumber(attr.max)}`;
  const unit = attr.unit ? ` ${attr.unit}` : "";
  return `${value}${max}${unit}`;
}

function formatNumber(value) {
  const number = Number(value);
  if (Number.isFinite(number)) return Number.isInteger(number) ? String(number) : number.toFixed(1).replace(/\.0$/, "");
  return String(value ?? "");
}

function formatGameTime(data) {
  const gt = data.game_time || {};
  if (typeof gt.hour === "number" && typeof gt.minute === "number") {
    return `第 ${data.tick ?? 0} 回合 · ${String(gt.hour).padStart(2, "0")}:${String(gt.minute).padStart(2, "0")}`;
  }
  return `第 ${data.tick ?? 0} 回合`;
}

function formatTemperature(value) {
  if (value === null || value === undefined || value === "") return "";
  return `${formatNumber(value)}°C`;
}

async function showSaveList() {
  try {
    const data = await api("/api/saves");
    state.saves = data.saves || [];
    if (!state.saves.length) {
      showModal("读取存档", ["当前没有可读取的存档。"]);
      return;
    }
    const container = document.createElement("div");
    container.className = "modal-body";
    for (const save of state.saves) {
      const button = document.createElement("button");
      button.className = "menu-item";
      button.innerHTML = `${escapeHtml(save.name)}<br><span class="npc-action">${escapeHtml(save.world_name || "未知世界")} · 第 ${save.tick} 回合 · ${formatSaveTime(save.game_time)}</span>`;
      button.addEventListener("click", () => {
        closeModal();
        startGame("save", save.path);
      });
      container.appendChild(button);
    }
    showModalNode("读取存档", container);
  } catch (error) {
    showModal("读取失败", [error.message]);
  }
}

function formatSaveTime(gameTime) {
  if (!gameTime || typeof gameTime.hour !== "number") return "时间未知";
  return `${String(gameTime.hour).padStart(2, "0")}:${String(gameTime.minute || 0).padStart(2, "0")}`;
}

async function promptSave() {
  if (!state.current?.started) {
    showModal("无法保存", ["游戏尚未开始。"]);
    return;
  }
  const name = window.prompt("存档名（字母、数字、下划线、短横线）", `save_${state.current.tick || 0}`);
  if (!name) return;
  setBusy(true);
  try {
    const data = await api("/api/save", {
      method: "POST",
      body: JSON.stringify({ name }),
    });
    renderState(data, { appendStory: false });
    showToast(data.message || "保存成功");
  } catch (error) {
    showModal("保存失败", [error.message]);
  } finally {
    setBusy(false);
  }
}

function updateSlashMenu() {
  const value = els.commandInput.value;
  if (!value.startsWith("/")) {
    hideSlashMenu();
    return;
  }
  const matched = commands.filter((item) => item.cmd.startsWith(value) || item.label.includes(value.slice(1)));
  if (!matched.length) {
    hideSlashMenu();
    return;
  }
  els.slashMenu.innerHTML = "";
  for (const item of matched) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = `${item.cmd}  ${item.label}`;
    button.addEventListener("click", () => {
      els.commandInput.value = item.cmd;
      els.commandInput.focus();
      autoGrow(els.commandInput);
      hideSlashMenu();
    });
    els.slashMenu.appendChild(button);
  }
  els.slashMenu.classList.remove("hidden");
}

function hideSlashMenu() {
  els.slashMenu.classList.add("hidden");
}

function showHelp() {
  showModal("帮助", commands.map((item) => `${item.cmd} — ${item.label}`));
}

function showModal(title, items) {
  const body = document.createElement("div");
  body.className = "modal-body";
  for (const item of items.length ? items : ["没有可显示的内容。"] ) {
    const div = document.createElement("div");
    div.className = "modal-item";
    div.textContent = String(item);
    body.appendChild(div);
  }
  showModalNode(title, body);
}

function showModalNode(title, node) {
  els.modalTitle.textContent = title;
  els.modalBody.innerHTML = "";
  els.modalBody.appendChild(node);
  els.modalBackdrop.classList.remove("hidden");
}

function closeModal() {
  els.modalBackdrop.classList.add("hidden");
}

function showToast(message) {
  showModal("提示", [message]);
}

function setBusy(busy) {
  els.loadingPanel.classList.toggle("hidden", !busy);
  els.sendButton.disabled = busy;
  els.commandInput.disabled = busy;
}

function autoGrow(textarea) {
  textarea.style.height = "auto";
  textarea.style.height = Math.min(textarea.scrollHeight, 140) + "px";
}

function loadSettings() {
  const defaults = {
    statusExpanded: false,
    fontSize: 16,
    lineHeight: 1.8,
    storyWidth: 680,
    showAttributes: true,
    showSensors: true,
    debugMode: false,
    simpleMode: false,
  };
  try {
    return { ...defaults, ...JSON.parse(localStorage.getItem("llm-sim-webui-settings") || "{}") };
  } catch {
    return defaults;
  }
}

function saveSettings() {
  localStorage.setItem("llm-sim-webui-settings", JSON.stringify(state.settings));
}

function applySettings() {
  document.documentElement.style.setProperty("--font-size", `${state.settings.fontSize}px`);
  document.documentElement.style.setProperty("--line-height", state.settings.lineHeight);
  document.documentElement.style.setProperty("--story-width", `${state.settings.storyWidth}px`);
  els.rightPanel.classList.toggle("collapsed", !state.settings.statusExpanded);
  document.body.classList.toggle("simple-mode", state.settings.simpleMode);
  $$(".quick-actions, .sensor-card").forEach((el) => el.classList.toggle("hidden", !state.settings.showSensors));
  const controls = {
    fontSize: $("#fontSize"),
    lineHeight: $("#lineHeight"),
    storyWidth: $("#storyWidth"),
    showAttributes: $("#showAttributes"),
    showSensors: $("#showSensors"),
    debugMode: $("#debugMode"),
    simpleMode: $("#simpleMode"),
  };
  Object.entries(controls).forEach(([key, el]) => {
    if (!el) return;
    if (el.type === "checkbox") el.checked = Boolean(state.settings[key]);
    else el.value = state.settings[key];
  });
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  let data = null;
  const text = await response.text();
  if (text) {
    try { data = JSON.parse(text); } catch { data = text; }
  }
  if (!response.ok) {
    const detail = typeof data === "object" && data?.detail ? data.detail : `HTTP ${response.status}`;
    throw new Error(detail);
  }
  return data;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
