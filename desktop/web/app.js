let api = null;
let activeChatId = null;
let streamingRow = null;
let pendingToolNames = null;

const chatListEl = document.getElementById("chat-list");
const messagesEl = document.getElementById("messages");
const inputForm = document.getElementById("input-form");
const inputBox = document.getElementById("input-box");
const micBtn = document.getElementById("mic-btn");
const voiceOrb = document.getElementById("voice-orb");
const statusText = document.getElementById("status-text");

function setStatus(status) {
  voiceOrb.className = status;
  statusText.textContent = status.replace(/_/g, " ");
  micBtn.classList.toggle("recording", status === "listening_for_command");
}

function setAmplitude(value) {
  // Rough int16-amplitude-to-scale mapping; clamps so quiet rooms don't look dead
  // and loud input doesn't blow past a sane visual ceiling.
  const scale = 1 + Math.min(value / 4000, 1) * 0.6;
  voiceOrb.style.transform = `scale(${scale.toFixed(2)})`;
}

function makeSpeakButton(text) {
  const btn = document.createElement("button");
  btn.className = "speak-btn";
  btn.title = "Read aloud";
  btn.textContent = "🔊";
  btn.onclick = () => api.speak_message(text);
  return btn;
}

function addMessageRow(role, content, toolNames) {
  const row = document.createElement("div");
  row.className = "message-row " + (role === "user" ? "user" : "assistant");

  if (toolNames && toolNames.length) {
    const annotation = document.createElement("div");
    annotation.className = "tool-annotation";
    annotation.textContent = "Used " + toolNames.join(", ");
    row.appendChild(annotation);
  }

  const wrap = document.createElement("div");
  wrap.className = "bubble-wrap";

  const bubble = document.createElement("div");
  bubble.className = "bubble " + (role === "user" ? "user" : "assistant");
  bubble.textContent = content;
  wrap.appendChild(bubble);

  if (role === "assistant") {
    wrap.appendChild(makeSpeakButton(content));
  }

  row.appendChild(wrap);
  messagesEl.appendChild(row);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return { row, bubble, wrap };
}

async function loadChatList() {
  const chats = await api.list_chats();
  chatListEl.innerHTML = "";
  if (chats.length === 0) {
    await createChat();
    return;
  }
  chats.forEach((chat) => {
    const item = document.createElement("div");
    item.className = "chat-item" + (chat.id === activeChatId ? " active" : "");
    item.textContent = chat.title;
    item.onclick = () => switchChat(chat.id);
    chatListEl.appendChild(item);
  });
  if (!activeChatId) {
    await switchChat(chats[0].id);
  }
}

async function createChat() {
  const chatId = await api.create_chat("New chat");
  await loadChatList();
  await switchChat(chatId);
}

async function switchChat(chatId) {
  activeChatId = chatId;
  streamingRow = null;
  await api.switch_chat(chatId);
  const messages = await api.get_messages(chatId);
  messagesEl.innerHTML = "";
  messages.forEach((m) => addMessageRow(m.role, m.content));
  const mode = await api.get_chat_mode(chatId);
  document.getElementById("mode-select").value = mode;
  await loadChatList();
}

async function sendMessage(text) {
  if (!activeChatId) {
    await createChat();
  }
  addMessageRow("user", text);
  await api.send_message(activeChatId, text);
}

inputForm.addEventListener("submit", (e) => {
  e.preventDefault();
  const text = inputBox.value.trim();
  if (!text) return;
  inputBox.value = "";
  sendMessage(text);
});

document.getElementById("new-chat-btn").onclick = () => createChat();

document.getElementById("mode-select").onchange = async (e) => {
  if (!activeChatId) return;
  await api.set_chat_mode(activeChatId, e.target.value);
};

micBtn.onclick = async () => {
  if (!activeChatId) await createChat();
  const result = await api.start_voice_input(activeChatId);
  if (!result.ok) {
    statusText.textContent = result.error || "Busy";
  }
};

document.getElementById("engine-start").onclick = () => api.start_engine();
document.getElementById("engine-stop").onclick = () => api.stop_engine();
document.getElementById("engine-restart").onclick = () => api.restart_engine();

// --- Confirmation modal ---
const confirmModal = document.getElementById("confirmation-modal");
document.getElementById("confirm-approve").onclick = () => {
  api.approve_call();
  confirmModal.classList.add("hidden");
};
document.getElementById("confirm-deny").onclick = () => {
  api.deny_call();
  confirmModal.classList.add("hidden");
};

function showConfirmation(detail) {
  document.getElementById("confirm-function").textContent = `Tool: ${detail.function_name}`;
  document.getElementById("confirm-args").textContent = JSON.stringify(detail.arguments, null, 2);
  confirmModal.classList.remove("hidden");
}

// --- Settings modal ---
const settingsModal = document.getElementById("settings-modal");
document.getElementById("settings-btn").onclick = async () => {
  const settings = await api.get_settings();
  const models = await api.list_installed_models();
  const select = document.getElementById("model-select");
  select.innerHTML = "";
  models.forEach((m) => {
    const opt = document.createElement("option");
    opt.value = m;
    opt.textContent = m;
    if (m === settings.ollama_model) opt.selected = true;
    select.appendChild(opt);
  });
  document.getElementById("wake-word-path").value = settings.wake_word_model_path;
  document.getElementById("require-confirmation").checked = settings.require_tool_confirmation;
  document.getElementById("auto-speak").checked = settings.auto_speak_responses;
  settingsModal.classList.remove("hidden");
};
document.getElementById("settings-close").onclick = () => settingsModal.classList.add("hidden");
document.getElementById("settings-save").onclick = async () => {
  const model = document.getElementById("model-select").value;
  const wakeWordPath = document.getElementById("wake-word-path").value;
  const requireConfirmation = document.getElementById("require-confirmation").checked;
  const autoSpeak = document.getElementById("auto-speak").checked;
  await api.set_current_model(model);
  await api.set_setting("WAKE_WORD_MODEL_PATH", wakeWordPath);
  await api.set_setting("REQUIRE_TOOL_CONFIRMATION", requireConfirmation ? "true" : "false");
  await api.set_setting("AUTO_SPEAK_RESPONSES", autoSpeak ? "true" : "false");
  settingsModal.classList.add("hidden");
};
document.getElementById("create-shortcut-btn").onclick = async () => {
  const btn = document.getElementById("create-shortcut-btn");
  const result = await api.create_desktop_shortcut();
  btn.textContent = result.ok ? "Shortcut created!" : "Failed - see console";
  setTimeout(() => (btn.textContent = "Create Desktop Shortcut"), 2000);
};

// --- Tools modal ---
const toolsModal = document.getElementById("tools-modal");

async function refreshToolsList() {
  const tools = await api.list_tools();
  const list = document.getElementById("tools-list");
  list.innerHTML = "";
  tools.forEach((tool) => {
    const row = document.createElement("div");
    row.className = "tool-item";
    const badge = tool.always_confirm ? '<span class="tool-badge">always confirms</span>' : "";
    const removeBtn = tool.kind === "mcp" ? '<button class="mcp-remove" title="Remove server">✕</button>' : "";
    row.innerHTML = `
      <div>
        <div class="tool-label">${tool.label}${badge}</div>
        <div class="tool-desc">${tool.description}</div>
      </div>
      <div style="display:flex; align-items:center; gap:8px;">
        <input type="checkbox" ${tool.enabled ? "checked" : ""} data-tool-id="${tool.id}" />
        ${removeBtn}
      </div>
    `;
    row.querySelector("input").onchange = (e) => {
      api.set_tool_enabled(tool.id, e.target.checked);
    };
    const removeEl = row.querySelector(".mcp-remove");
    if (removeEl) {
      removeEl.onclick = async () => {
        await api.remove_mcp_server(tool.id.replace(/^mcp:/, ""));
        refreshToolsList();
      };
    }
    list.appendChild(row);
  });
}

document.getElementById("tools-btn").onclick = async () => {
  await refreshToolsList();
  toolsModal.classList.remove("hidden");
};
document.getElementById("tools-close").onclick = () => toolsModal.classList.add("hidden");
document.getElementById("mcp-add-btn").onclick = async () => {
  const label = document.getElementById("mcp-label").value.trim();
  const command = document.getElementById("mcp-command").value.trim();
  if (!label || !command) return;
  await api.add_mcp_server(label, command);
  document.getElementById("mcp-label").value = "";
  document.getElementById("mcp-command").value = "";
  await refreshToolsList();
};

// --- Canvas panel ---
const canvasPanel = document.getElementById("canvas-panel");
const canvasCode = document.getElementById("canvas-code");
let canvasRawText = "";

const CODE_BLOCK_RE = /```(\w*)\n([\s\S]*?)```/g;
const KEYWORDS = new Set([
  "def", "class", "return", "if", "elif", "else", "for", "while", "import", "from",
  "function", "const", "let", "var", "async", "await", "try", "except", "catch",
  "finally", "with", "as", "in", "not", "and", "or", "true", "false", "none", "null",
  "public", "private", "static", "void", "new",
]);

function highlight(code) {
  const escaped = code
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

  const lines = escaped.split("\n").map((line) => {
    let tokenized = line.replace(/(#.*|\/\/.*)/, '<span class="tok-comment">$1</span>');
    tokenized = tokenized.replace(/(&quot;.*?&quot;|'.*?'|".*?")/g, '<span class="tok-string">$1</span>');
    tokenized = tokenized.replace(/\b(\d+(\.\d+)?)\b/g, '<span class="tok-number">$1</span>');
    tokenized = tokenized.replace(
      new RegExp(`\\b(${[...KEYWORDS].join("|")})\\b`, "gi"),
      '<span class="tok-keyword">$1</span>'
    );
    return tokenized;
  });
  return lines.join("\n");
}

function showCanvasFromResponse(text) {
  const matches = [...text.matchAll(CODE_BLOCK_RE)];
  if (matches.length === 0) return;
  const last = matches[matches.length - 1];
  canvasRawText = last[2];
  canvasCode.innerHTML = highlight(canvasRawText);
  canvasPanel.classList.remove("hidden");
  const canvasDot = document.getElementById("canvas-dot");
  if (canvasDot) canvasDot.classList.remove("hidden");
}

document.getElementById("canvas-btn").onclick = () => canvasPanel.classList.toggle("hidden");
document.getElementById("canvas-close").onclick = () => canvasPanel.classList.add("hidden");
document.getElementById("canvas-copy").onclick = () => navigator.clipboard.writeText(canvasRawText);

// --- Engine event pump (pushed from Python via window.evaluate_js) ---
window.onZhoraEvent = (event) => {
  if (event.status === "amplitude") {
    setAmplitude(event.detail.value);
    return;
  }

  setStatus(event.status);

  if (event.status === "awaiting_confirmation" && event.detail) {
    showConfirmation(event.detail);
  } else {
    confirmModal.classList.add("hidden");
  }

  if (event.status === "tool_calls" && event.detail && event.detail.chat_id === activeChatId) {
    pendingToolNames = event.detail.tool_calls.map((t) => t.name);
  }

  if (event.status === "responding" && event.detail && event.detail.chat_id === activeChatId) {
    streamingRow = addMessageRow("assistant", "", pendingToolNames);
    pendingToolNames = null;
  }

  if (
    event.status === "streaming_chunk" &&
    event.detail &&
    event.detail.chat_id === activeChatId &&
    streamingRow
  ) {
    streamingRow.bubble.textContent += event.detail.delta;
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  if (event.status === "idle" && event.detail && event.detail.response) {
    if (event.detail.chat_id === activeChatId) {
      if (streamingRow) {
        streamingRow.bubble.textContent = event.detail.response;
        streamingRow = null;
      } else {
        addMessageRow("assistant", event.detail.response);
      }
      showCanvasFromResponse(event.detail.response);
    }
  }
};

window.addEventListener("pywebviewready", async () => {
  api = window.pywebview.api;
  const status = await api.get_status();
  setStatus(status.status);
  await loadChatList();
});
