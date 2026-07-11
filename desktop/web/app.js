let api = null;
let activeChatId = null;

const chatListEl = document.getElementById("chat-list");
const messagesEl = document.getElementById("messages");
const inputForm = document.getElementById("input-form");
const inputBox = document.getElementById("input-box");
const statusDot = document.getElementById("status-dot");
const statusText = document.getElementById("status-text");

function setStatus(status) {
  statusDot.className = "dot " + status;
  statusText.textContent = status.replace(/_/g, " ");
}

function addBubble(role, content) {
  const bubble = document.createElement("div");
  bubble.className = "bubble " + (role === "user" ? "user" : "assistant");
  bubble.textContent = content;
  messagesEl.appendChild(bubble);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return bubble;
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
  await api.switch_chat(chatId);
  const messages = await api.get_messages(chatId);
  messagesEl.innerHTML = "";
  messages.forEach((m) => addBubble(m.role, m.content));
  Array.from(chatListEl.children).forEach((el, i) => {});
  await loadChatList();
}

async function sendMessage(text) {
  if (!activeChatId) {
    await createChat();
  }
  addBubble("user", text);
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
  settingsModal.classList.remove("hidden");
};
document.getElementById("settings-close").onclick = () => settingsModal.classList.add("hidden");
document.getElementById("settings-save").onclick = async () => {
  const model = document.getElementById("model-select").value;
  const wakeWordPath = document.getElementById("wake-word-path").value;
  const requireConfirmation = document.getElementById("require-confirmation").checked;
  await api.set_current_model(model);
  await api.set_setting("WAKE_WORD_MODEL_PATH", wakeWordPath);
  await api.set_setting("REQUIRE_TOOL_CONFIRMATION", requireConfirmation ? "true" : "false");
  settingsModal.classList.add("hidden");
};

// --- Tools modal ---
const toolsModal = document.getElementById("tools-modal");
document.getElementById("tools-btn").onclick = async () => {
  const tools = await api.list_tools();
  const list = document.getElementById("tools-list");
  list.innerHTML = "";
  tools.forEach((tool) => {
    const row = document.createElement("div");
    row.className = "tool-item";
    row.innerHTML = `
      <div>
        <div class="tool-label">${tool.label}</div>
        <div class="tool-desc">${tool.description}</div>
      </div>
      <input type="checkbox" ${tool.enabled ? "checked" : ""} data-tool-id="${tool.id}" />
    `;
    row.querySelector("input").onchange = (e) => {
      api.set_tool_enabled(tool.id, e.target.checked);
    };
    list.appendChild(row);
  });
  toolsModal.classList.remove("hidden");
};
document.getElementById("tools-close").onclick = () => toolsModal.classList.add("hidden");

// --- Engine event pump (pushed from Python via window.evaluate_js) ---
window.onZhoraEvent = (event) => {
  setStatus(event.status);

  if (event.status === "awaiting_confirmation" && event.detail) {
    showConfirmation(event.detail);
  } else {
    confirmModal.classList.add("hidden");
  }

  if (event.status === "idle" && event.detail && event.detail.response) {
    if (event.detail.chat_id === activeChatId) {
      addBubble("assistant", event.detail.response);
    }
  }
};

window.addEventListener("pywebviewready", async () => {
  api = window.pywebview.api;
  const status = await api.get_status();
  setStatus(status.status);
  await loadChatList();
});
