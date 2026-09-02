/* P10 Web 静态前端（SOT §3.9；零依赖纯 JS；textContent 单点渲染；
 * 零外部模块语法 / 零动态脚本写入；D2 行宽 <= 100；D3 零 0x5C 0x62；
 * K8 12 名闭集零命中；D6 零随机 / 零时钟状态）。W4 面 = 玩法页
 * state 轮询（间隔 <= 5s）+ inspector / workbench 一次性 GET 渲染；
 * S4 人工面 pending（S11）。图像面 = PPM 文本确定性解码 → canvas。 */
"use strict";

var pollTimerId = 0;
var currentSessionId = "";

function element(id) { return document.getElementById(id); }

function setText(id, text) {
  var node = element(id);
  if (node) { node.textContent = text; }
}

function sessionIdFromInput() {
  var input = element("session-input");
  return input ? input.value.trim() : "";
}

function stopPolling() {
  if (pollTimerId) { clearInterval(pollTimerId); pollTimerId = 0; }
}

function renderPpm(buffer) {
  var tokens = new TextDecoder().decode(buffer).trim().split(/\s+/);
  var img = element("image-view");
  if (!img || tokens[0] !== "P3") { return; }
  var width = parseInt(tokens[1], 10);
  var height = parseInt(tokens[2], 10);
  var canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  var ctx = canvas.getContext("2d");
  var data = ctx.createImageData(width, height);
  for (var i = 0; i < width * height; i += 1) {
    data.data[i * 4] = parseInt(tokens[4 + i * 3], 10);
    data.data[i * 4 + 1] = parseInt(tokens[4 + i * 3 + 1], 10);
    data.data[i * 4 + 2] = parseInt(tokens[4 + i * 3 + 2], 10);
    data.data[i * 4 + 3] = 255;
  }
  ctx.putImageData(data, 0, 0);
  img.src = canvas.toDataURL();
}

function renderImageSlot(snapshot) {
  var slot = snapshot.image_slot;
  var note = element("image-slot");
  var img = element("image-view");
  if (!slot) {
    if (note) { note.textContent = "无图像"; }
    if (img) { img.removeAttribute("src"); }
    return;
  }
  if (note) {
    note.textContent = "artifact " + slot.artifact_id +
      " rev " + slot.view_revision +
      (slot.stale ? "（stale）" : "") + " bytes " + slot.byte_length;
  }
  fetch("/api/sessions/" + encodeURIComponent(currentSessionId) + "/image")
    .then(function (response) {
      return response.ok ? response.arrayBuffer() : null;
    })
    .then(function (buffer) { if (buffer) { renderPpm(buffer); } })
    .catch(function () { /* 无图像面：保留 note 文本 */ });
}

function startPolling() {
  stopPolling();
  currentSessionId = sessionIdFromInput();
  if (!currentSessionId) {
    setText("state-box", "请输入会话 ID");
    return;
  }
  pollTimerId = setInterval(function () {
    fetch("/api/sessions/" + encodeURIComponent(currentSessionId) + "/state")
      .then(function (response) { return response.json(); })
      .then(function (payload) {
        if (payload.ok) {
          setText("state-box", JSON.stringify(payload.snapshot, null, 2));
          renderImageSlot(payload.snapshot);
        } else {
          setText("state-box", "错误：" + payload.error_message);
        }
      })
      .catch(function () {
        setText("state-box", "轮询失败（会话可能已关闭）");
      });
  }, 2000);
}

function submitAction(event) {
  event.preventDefault();
  var input = element("action-input");
  if (!currentSessionId) {
    setText("state-box", "请先连接会话");
    return;
  }
  fetch("/api/sessions/" + encodeURIComponent(currentSessionId) + "/action", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: input ? input.value : "" })
  })
    .then(function (response) { return response.json(); })
    .then(function (payload) {
      if (payload.ok) {
        setText("state-box", JSON.stringify(payload.snapshot, null, 2));
        renderImageSlot(payload.snapshot);
        if (input) { input.value = ""; }
      } else {
        setText("state-box", "错误：" + payload.error_message);
      }
    })
    .catch(function () { setText("state-box", "发送失败"); });
}

function renderSectionData(payload) {
  var sections = payload.sections || payload;
  var nodes = document.querySelectorAll("[data-section]");
  for (var i = 0; i < nodes.length; i += 1) {
    var name = nodes[i].getAttribute("data-section");
    var value = sections[name];
    nodes[i].textContent = value === undefined
      ? "-" : JSON.stringify(value, null, 2);
  }
  if (payload.prompt_history) {
    renderPromptHistory(payload.prompt_history);
  }
  var view = element("workbench-view");
  if (view) { view.textContent = JSON.stringify(payload, null, 2); }
}

function renderPromptHistory(history) {
  var body = element("prompt-history-body");
  if (!body) { return; }
  body.textContent = "";
  for (var i = 0; i < history.length; i += 1) {
    var row = body.appendChild(document.createElement("tr"));
    var source = history[i];
    var fields = [source.seq, source.logical_role, source.base_revision,
      source.model, source.prompt_metadata_ref, source.response_text];
    for (var c = 0; c < fields.length; c += 1) {
      var cell = row.appendChild(document.createElement("td"));
      cell.textContent = fields[c] === undefined ? "" : String(fields[c]);
    }
  }
}

function loadSection(url, fallbackId) {
  fetch(url)
    .then(function (response) { return response.json(); })
    .then(function (payload) {
      if (!payload.ok) {
        setText(fallbackId, "错误：" + payload.error_message);
        return;
      }
      renderSectionData(payload);
    })
    .catch(function () { setText(fallbackId, "取数失败"); });
}

function attachButton(buttonId, kind) {
  var button = element(buttonId);
  if (!button) { return; }
  button.addEventListener("click", function () {
    var id = sessionIdFromInput();
    if (!id) { return; }
    currentSessionId = id;
    var prefix = kind === "inspector" ? "/api/inspector/" : "/api/workbench/";
    var fallback = kind === "inspector" ? "state-box" : "workbench-view";
    loadSection(prefix + encodeURIComponent(id), fallback);
  });
}

function init() {
  var form = element("action-form");
  if (form) { form.addEventListener("submit", submitAction); }
  var connectBtn = element("connect-btn");
  if (connectBtn) { connectBtn.addEventListener("click", startPolling); }
  attachButton("inspector-btn", "inspector");
  attachButton("workbench-btn", "workbench");
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
