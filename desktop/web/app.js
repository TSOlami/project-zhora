let api = null;
let activeChatId = null;
let streamingRow = null;
let pendingToolNames = null;
let pendingUserRow = null;
let thinkingRow = null;

// Shared icon set for message-action and toolbar buttons, matching the
// stroke-based icon style already used for send/mic/settings/canvas/tools.
const ICONS = {
  speaker:
    '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon><path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"></path></svg>',
  copy:
    '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>',
  check:
    '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>',
  retry:
    '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"></polyline><polyline points="1 20 1 14 7 14"></polyline><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path></svg>',
  edit:
    '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"></path></svg>',
  close:
    '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>',
  wrench:
    '<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"></path></svg>',
};

// --- Custom select widget -------------------------------------------------
// Replaces a native <select>'s appearance only. The native element stays in
// the DOM (hidden) and remains the actual source of truth for .value and
// 'change' events, so no other code that reads/writes a select's .value has
// to know this exists - it just also needs to call the returned .refresh()
// after setting .value programmatically, so the (closed) trigger's label
// text stays in sync. Follows the ARIA "select-only combobox" pattern:
// real DOM focus stays on the trigger button the whole time; the
// highlighted option is tracked via aria-activedescendant instead of
// moving focus into the listbox.
const CHEVRON_ICON =
  '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"></polyline></svg>';

const openCSelects = new Set();

function enhanceSelect(nativeSelect, opts) {
  opts = opts || {};
  nativeSelect.style.display = "none";
  nativeSelect.setAttribute("aria-hidden", "true");
  nativeSelect.tabIndex = -1;

  const trigger = document.createElement("button");
  trigger.type = "button";
  trigger.className = "cselect-trigger" + (opts.variant === "topbar" ? " cselect-trigger--topbar" : "");
  trigger.setAttribute("role", "combobox");
  trigger.setAttribute("aria-haspopup", "listbox");
  trigger.setAttribute("aria-expanded", "false");
  if (nativeSelect.title) trigger.title = nativeSelect.title;

  const valueSpan = document.createElement("span");
  valueSpan.className = "cselect-value";
  const chevron = document.createElement("span");
  chevron.className = "cselect-chevron";
  chevron.innerHTML = CHEVRON_ICON;
  trigger.appendChild(valueSpan);
  trigger.appendChild(chevron);

  const popupId = (nativeSelect.id || "cselect") + "-listbox";
  const popup = document.createElement("ul");
  popup.className = "cselect-popup hidden";
  popup.setAttribute("role", "listbox");
  popup.id = popupId;
  trigger.setAttribute("aria-controls", popupId);
  document.body.appendChild(popup);

  nativeSelect.insertAdjacentElement("afterend", trigger);

  let activeIndex = -1;

  function options() {
    return Array.from(nativeSelect.options);
  }

  function render() {
    const opts_ = options();
    popup.innerHTML = "";
    opts_.forEach((opt, i) => {
      const li = document.createElement("li");
      li.className = "cselect-option";
      li.setAttribute("role", "option");
      li.id = `${popupId}-opt-${i}`;
      li.textContent = opt.textContent;
      const selected = opt.value === nativeSelect.value;
      li.setAttribute("aria-selected", selected ? "true" : "false");
      if (selected) activeIndex = i;
      li.onclick = () => {
        selectIndex(i);
        close();
        trigger.focus();
      };
      popup.appendChild(li);
    });
    const current = opts_.find((o) => o.value === nativeSelect.value);
    valueSpan.textContent = current ? current.textContent : "";
  }

  function selectIndex(i) {
    const opts_ = options();
    if (i < 0 || i >= opts_.length) return;
    const changed = nativeSelect.value !== opts_[i].value;
    nativeSelect.value = opts_[i].value;
    render();
    highlight(i);
    if (changed) nativeSelect.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function highlight(i) {
    activeIndex = i;
    const items = popup.querySelectorAll(".cselect-option");
    items.forEach((el, idx) => el.classList.toggle("active", idx === i));
    trigger.setAttribute("aria-activedescendant", items[i] ? items[i].id : "");
    if (items[i]) items[i].scrollIntoView({ block: "nearest" });
  }

  function position() {
    const rect = trigger.getBoundingClientRect();
    popup.style.left = `${Math.round(rect.left)}px`;
    popup.style.top = `${Math.round(rect.bottom + 4)}px`;
    popup.style.minWidth = `${Math.round(rect.width)}px`;
  }

  function isOpen() {
    return !popup.classList.contains("hidden");
  }

  function open() {
    if (nativeSelect.disabled) return;
    openCSelects.forEach((close_) => close_ !== close && close_());
    render();
    position();
    popup.classList.remove("hidden");
    trigger.setAttribute("aria-expanded", "true");
    const opts_ = options();
    const idx = opts_.findIndex((o) => o.value === nativeSelect.value);
    highlight(idx >= 0 ? idx : 0);
    openCSelects.add(close);
    document.addEventListener("mousedown", onOutsideClick, true);
    window.addEventListener("resize", position);
  }

  function close() {
    popup.classList.add("hidden");
    trigger.setAttribute("aria-expanded", "false");
    openCSelects.delete(close);
    document.removeEventListener("mousedown", onOutsideClick, true);
    window.removeEventListener("resize", position);
  }

  function onOutsideClick(e) {
    if (!popup.contains(e.target) && e.target !== trigger) close();
  }

  let typeAheadBuffer = "";
  let typeAheadTimer = null;

  trigger.addEventListener("keydown", (e) => {
    const opts_ = options();
    if (!opts_.length) return;
    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        if (!isOpen()) open();
        else highlight(Math.min(activeIndex + 1, opts_.length - 1));
        break;
      case "ArrowUp":
        e.preventDefault();
        if (!isOpen()) open();
        else highlight(Math.max(activeIndex - 1, 0));
        break;
      case "Home":
        if (isOpen()) {
          e.preventDefault();
          highlight(0);
        }
        break;
      case "End":
        if (isOpen()) {
          e.preventDefault();
          highlight(opts_.length - 1);
        }
        break;
      case "Enter":
      case " ":
        e.preventDefault();
        if (isOpen()) {
          selectIndex(activeIndex);
          close();
        } else {
          open();
        }
        break;
      case "Escape":
        if (isOpen()) {
          e.preventDefault();
          close();
        }
        break;
      case "Tab":
        close();
        break;
      default:
        if (e.key.length === 1 && /\S/.test(e.key)) {
          typeAheadBuffer += e.key.toLowerCase();
          clearTimeout(typeAheadTimer);
          typeAheadTimer = setTimeout(() => (typeAheadBuffer = ""), 600);
          const match = opts_.findIndex((o) => o.textContent.toLowerCase().startsWith(typeAheadBuffer));
          if (match >= 0) {
            if (isOpen()) highlight(match);
            else selectIndex(match);
          }
        }
    }
  });

  trigger.addEventListener("click", () => {
    if (isOpen()) close();
    else open();
  });

  render();

  return { refresh: render };
}

const chatListEl = document.getElementById("chat-list");
const messagesEl = document.getElementById("messages");
const inputForm = document.getElementById("input-form");
const inputBox = document.getElementById("input-box");
const sendBtn = document.getElementById("send-btn");
const micBtn = document.getElementById("mic-btn");
const voiceOrb = document.getElementById("voice-orb");
const statusText = document.getElementById("status-text");

const modeSelectWidget = enhanceSelect(document.getElementById("mode-select"), { variant: "topbar" });
const closeBehaviorWidget = enhanceSelect(document.getElementById("close-behavior-select"));
const modelSelectWidget = enhanceSelect(document.getElementById("model-select"));

// Per-mode input placeholder + whether Code mode keeps Canvas open
// proactively, instead of only opening it once a code block actually shows
// up in a response - see MODE_UI usage in applyModeUI below.
const MODE_UI = {
  chat: { placeholder: "Message Zhora...", openCanvas: false },
  co_work: { placeholder: "Describe what you're building together...", openCanvas: false },
  code: { placeholder: "Describe the code task...", openCanvas: true },
};

function applyModeUI(mode) {
  const ui = MODE_UI[mode] || MODE_UI.chat;
  inputBox.placeholder = ui.placeholder;
  if (ui.openCanvas) {
    document.getElementById("canvas-panel").classList.remove("hidden");
  }
}

// Mirrors the backend's own busy check in Api.start_voice_input - keeping
// them in sync means the button's enabled state always matches whether a
// click would actually be accepted, instead of drifting out of sync and
// letting a second click race the first (see MIC_READY_STATUSES usage below).
const MIC_READY_STATUSES = new Set(["idle", "listening_for_wake_word", "voice_unavailable", "stopped"]);

function setStatus(status) {
  voiceOrb.className = status;
  statusText.textContent = status.replace(/_/g, " ");
  micBtn.classList.toggle("recording", status === "listening_for_command");
  if (!generating) {
    micBtn.disabled = !MIC_READY_STATUSES.has(status);
  }
}

function setAmplitude(value) {
  // Rough int16-amplitude-to-scale mapping; clamps so quiet rooms don't look dead
  // and loud input doesn't blow past a sane visual ceiling.
  const scale = 1 + Math.min(value / 4000, 1) * 0.6;
  voiceOrb.style.transform = `scale(${scale.toFixed(2)})`;
}

// --- Scroll handling: only auto-follow new content if the user is already
// near the bottom, so reading back through history doesn't get yanked away
// mid-response. ---
function isNearBottom() {
  return messagesEl.scrollHeight - messagesEl.scrollTop - messagesEl.clientHeight < 80;
}

function scrollToBottomIfNear(wasNearBottom) {
  if (wasNearBottom) {
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }
}

// --- Generating state: locks input and shows a typing indicator for the
// full round trip. Worth doing given CPU-only inference regularly takes
// 10-30s+ per turn - without this the input just sits there inviting a
// confusing double-send. Also gates edit/retry, since truncating a run that
// the engine is still mid-write on would race against its own upsert. ---
let generating = false;

function setGenerating(value) {
  generating = value;
  inputBox.disabled = value;
  sendBtn.disabled = value;
  micBtn.disabled = value;
  if (value) {
    showThinkingIndicator();
  } else {
    hideThinkingIndicator();
  }
}

function showThinkingIndicator() {
  if (thinkingRow) return;
  const row = document.createElement("div");
  row.className = "message-row assistant";
  const wrap = document.createElement("div");
  wrap.className = "bubble-wrap";
  const bubble = document.createElement("div");
  bubble.className = "bubble assistant thinking-bubble";
  bubble.innerHTML = '<span class="thinking-dot"></span><span class="thinking-dot"></span><span class="thinking-dot"></span>';
  wrap.appendChild(bubble);
  row.appendChild(wrap);
  const wasNearBottom = isNearBottom();
  messagesEl.appendChild(row);
  scrollToBottomIfNear(wasNearBottom);
  thinkingRow = row;
}

function hideThinkingIndicator() {
  if (thinkingRow) {
    thinkingRow.remove();
    thinkingRow = null;
  }
}

function makeSpeakButton(text) {
  const btn = document.createElement("button");
  btn.className = "msg-action-btn speak-btn";
  btn.title = "Read aloud";
  btn.innerHTML = ICONS.speaker;
  btn.onclick = () => api.speak_message(text);
  return btn;
}

function makeCopyButton(getText) {
  const btn = document.createElement("button");
  btn.className = "msg-action-btn copy-btn";
  btn.title = "Copy";
  btn.innerHTML = ICONS.copy;
  btn.onclick = () => {
    navigator.clipboard.writeText(getText());
    btn.innerHTML = ICONS.check;
    setTimeout(() => (btn.innerHTML = ICONS.copy), 1200);
  };
  return btn;
}

function truncateMessagesFrom(row) {
  let node = row;
  while (node) {
    const next = node.nextSibling;
    node.remove();
    node = next;
  }
}

// Only the most recent assistant reply can be retried - older ones are
// history, not the live end of the conversation.
function refreshRetryVisibility() {
  const assistantRows = messagesEl.querySelectorAll(".message-row.assistant");
  assistantRows.forEach((row, i) => {
    const retryBtn = row.querySelector(".retry-btn");
    if (retryBtn) retryBtn.classList.toggle("hidden", i !== assistantRows.length - 1);
  });
}

function makeRetryButton(row) {
  const btn = document.createElement("button");
  btn.className = "msg-action-btn retry-btn hidden";
  btn.title = "Retry";
  btn.innerHTML = ICONS.retry;
  btn.onclick = async () => {
    if (generating) return;
    truncateMessagesFrom(row);
    setGenerating(true);
    await api.retry_last_response(activeChatId);
  };
  return btn;
}

function makeEditButton(row, bubble, originalText) {
  const btn = document.createElement("button");
  btn.className = "msg-action-btn";
  btn.title = "Edit & resend";
  btn.innerHTML = ICONS.edit;
  btn.onclick = () => {
    if (generating) return;
    enterEditMode(row, bubble, originalText);
  };
  return btn;
}

function enterEditMode(row, bubble, originalText) {
  const rowActions = row.querySelector(".msg-actions");
  if (rowActions) rowActions.classList.add("hidden");

  const textarea = document.createElement("textarea");
  textarea.className = "edit-textarea";
  textarea.value = originalText;

  const actions = document.createElement("div");
  actions.className = "edit-actions";
  const cancelBtn = document.createElement("button");
  cancelBtn.type = "button";
  cancelBtn.textContent = "Cancel";
  cancelBtn.onclick = () => {
    textarea.replaceWith(bubble);
    actions.remove();
    if (rowActions) rowActions.classList.remove("hidden");
  };
  const saveBtn = document.createElement("button");
  saveBtn.type = "button";
  saveBtn.className = "primary";
  saveBtn.textContent = "Save & resend";
  saveBtn.onclick = async () => {
    const newText = textarea.value.trim();
    if (!newText) return;
    const runId = row.dataset.runId;
    saveBtn.disabled = true;
    truncateMessagesFrom(row);
    pendingUserRow = addMessageRow("user", newText);
    setGenerating(true);
    await api.edit_message_and_resend(activeChatId, runId, newText);
  };
  actions.appendChild(cancelBtn);
  actions.appendChild(saveBtn);

  bubble.replaceWith(textarea);
  row.appendChild(actions);
  textarea.focus();
  textarea.setSelectionRange(textarea.value.length, textarea.value.length);
}

function addMessageRow(role, content, toolNames, runId, options) {
  options = options || {};
  const row = document.createElement("div");
  row.className = "message-row " + (role === "user" ? "user" : "assistant");
  if (runId) row.dataset.runId = runId;

  if (toolNames && toolNames.length) {
    const annotation = document.createElement("div");
    annotation.className = "tool-annotation";
    const icon = document.createElement("span");
    icon.innerHTML = ICONS.wrench;
    const label = document.createElement("span");
    label.textContent = "Used " + toolNames.join(", ");
    annotation.appendChild(icon);
    annotation.appendChild(label);
    row.appendChild(annotation);
  }

  const wrap = document.createElement("div");
  wrap.className = "bubble-wrap";

  const bubble = document.createElement("div");
  bubble.className = "bubble " + (role === "user" ? "user" : "assistant");
  bubble.textContent = content;
  wrap.appendChild(bubble);
  row.appendChild(wrap);

  // All per-message actions (speak, copy, retry/edit) live in one grouped
  // bar so they read as a single toolbar instead of scattered controls.
  const actions = document.createElement("div");
  actions.className = "msg-actions";
  if (role === "assistant") {
    actions.appendChild(makeSpeakButton(content));
  }
  actions.appendChild(makeCopyButton(() => bubble.textContent));
  if (role === "user") {
    actions.appendChild(makeEditButton(row, bubble, content));
  } else if (!options.noRetry) {
    actions.appendChild(makeRetryButton(row));
  }
  row.appendChild(actions);

  const wasNearBottom = isNearBottom();
  messagesEl.appendChild(row);
  scrollToBottomIfNear(wasNearBottom);
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
  await switchChat(chatId);
}

async function switchChat(chatId) {
  activeChatId = chatId;
  streamingRow = null;
  pendingUserRow = null;
  thinkingRow = null;
  resetCanvas();
  await api.switch_chat(chatId);
  const messages = await api.get_messages(chatId);
  messagesEl.innerHTML = "";
  messages.forEach((m) => addMessageRow(m.role, m.content, null, m.run_id));
  refreshRetryVisibility();
  const mode = await api.get_chat_mode(chatId);
  document.getElementById("mode-select").value = mode;
  modeSelectWidget.refresh();
  applyModeUI(mode);
  await loadChatList();
}

async function sendMessage(text) {
  if (!activeChatId) {
    await createChat();
  }
  pendingUserRow = addMessageRow("user", text);
  setGenerating(true);
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
  applyModeUI(e.target.value);
  if (!activeChatId) return;
  await api.set_chat_mode(activeChatId, e.target.value);
};

micBtn.onclick = async () => {
  // Disable immediately rather than waiting for the backend's status to come
  // back over the event pump - without this, two clicks fired close enough
  // together both pass the backend's status check before either one's
  // "listening_for_command" transition lands, spawning two concurrent
  // recordings. A later real status event (via setStatus) re-syncs this if
  // it disagrees.
  if (micBtn.disabled) return;
  micBtn.disabled = true;
  if (!activeChatId) await createChat();
  const result = await api.start_voice_input(activeChatId);
  if (!result.ok) {
    statusText.textContent = result.error || "Busy";
    micBtn.disabled = false;
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
  modelSelectWidget.refresh();
  document.getElementById("wake-word-path").value = settings.wake_word_model_path;
  document.getElementById("auto-speak").checked = settings.auto_speak_responses;
  document.getElementById("close-behavior-select").value = settings.close_behavior;
  closeBehaviorWidget.refresh();
  document.getElementById("start-on-boot").checked = settings.start_on_boot;
  settingsModal.classList.remove("hidden");
};
document.getElementById("settings-close").onclick = () => settingsModal.classList.add("hidden");
document.getElementById("settings-save").onclick = async () => {
  const model = document.getElementById("model-select").value;
  const wakeWordPath = document.getElementById("wake-word-path").value;
  const autoSpeak = document.getElementById("auto-speak").checked;
  const closeBehavior = document.getElementById("close-behavior-select").value;
  const startOnBoot = document.getElementById("start-on-boot").checked;
  await api.set_current_model(model);
  await api.set_setting("WAKE_WORD_MODEL_PATH", wakeWordPath);
  await api.set_setting("AUTO_SPEAK_RESPONSES", autoSpeak ? "true" : "false");
  await api.set_setting("CLOSE_BEHAVIOR", closeBehavior);
  await api.set_start_on_boot(startOnBoot);
  settingsModal.classList.add("hidden");
};
document.getElementById("wake-word-browse").onclick = async () => {
  const path = await api.browse_wake_word_model();
  if (path) document.getElementById("wake-word-path").value = path;
};

// --- Close-window confirmation ---
// Python's on_closing() calls window.showCloseConfirm() (via evaluate_js)
// when CLOSE_BEHAVIOR is "ask" - the buttons here call back into Python to
// actually decide, since the native close was already cancelled to make
// room for this dialog.
const closeConfirmModal = document.getElementById("close-confirm-modal");
window.showCloseConfirm = () => {
  document.getElementById("close-remember").checked = false;
  closeConfirmModal.classList.remove("hidden");
};
document.getElementById("close-tray").onclick = () => {
  const remember = document.getElementById("close-remember").checked;
  closeConfirmModal.classList.add("hidden");
  api.resolve_close_choice("tray", remember);
};
document.getElementById("close-quit").onclick = () => {
  const remember = document.getElementById("close-remember").checked;
  closeConfirmModal.classList.add("hidden");
  api.resolve_close_choice("quit", remember);
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

    const info = document.createElement("div");
    const labelDiv = document.createElement("div");
    labelDiv.className = "tool-label";
    labelDiv.textContent = tool.label;
    if (tool.always_confirm) {
      const badge = document.createElement("span");
      badge.className = "tool-badge";
      badge.textContent = "always confirms";
      labelDiv.appendChild(badge);
    }
    const descDiv = document.createElement("div");
    descDiv.className = "tool-desc";
    descDiv.textContent = tool.description;
    info.appendChild(labelDiv);
    info.appendChild(descDiv);

    const controls = document.createElement("div");
    controls.className = "tool-item-controls";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.className = "switch-checkbox";
    checkbox.checked = !!tool.enabled;
    checkbox.dataset.toolId = tool.id;
    checkbox.onchange = (e) => api.set_tool_enabled(tool.id, e.target.checked);
    controls.appendChild(checkbox);

    if (tool.kind === "mcp") {
      const removeBtn = document.createElement("button");
      removeBtn.className = "mcp-remove";
      removeBtn.title = "Remove server";
      removeBtn.innerHTML = ICONS.close;
      removeBtn.onclick = async () => {
        await api.remove_mcp_server(tool.id.replace(/^mcp:/, ""));
        refreshToolsList();
      };
      controls.appendChild(removeBtn);
    }

    row.appendChild(info);
    row.appendChild(controls);
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
const canvasDot = document.getElementById("canvas-dot");
const CANVAS_EMPTY_HTML = canvasCode.innerHTML;
let canvasRawText = "";

function resetCanvas() {
  canvasPanel.classList.add("hidden");
  canvasRawText = "";
  canvasCode.innerHTML = CANVAS_EMPTY_HTML;
  if (canvasDot) canvasDot.classList.add("hidden");
}

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

  if (event.status === "thinking") {
    setGenerating(true);
  }

  if (event.status === "awaiting_confirmation" && event.detail) {
    showConfirmation(event.detail);
  } else {
    confirmModal.classList.add("hidden");
  }

  if (event.status === "tool_calls" && event.detail && event.detail.chat_id === activeChatId) {
    pendingToolNames = event.detail.tool_calls.map((t) => t.name);
  }

  if (event.status === "responding" && event.detail && event.detail.chat_id === activeChatId) {
    hideThinkingIndicator();
    if (pendingUserRow) {
      if (event.detail.run_id) pendingUserRow.row.dataset.runId = event.detail.run_id;
    } else if (event.detail.user_text) {
      // Voice-originated turns never render a user bubble on submit (there's
      // no typed text to render optimistically) - render it now instead of
      // leaving the user's spoken prompt missing from the transcript.
      addMessageRow("user", event.detail.user_text, null, event.detail.run_id);
    }
    pendingUserRow = null;
    streamingRow = addMessageRow("assistant", "", pendingToolNames, event.detail.run_id);
    pendingToolNames = null;
    refreshRetryVisibility();
  }

  if (
    event.status === "streaming_chunk" &&
    event.detail &&
    event.detail.chat_id === activeChatId &&
    streamingRow
  ) {
    const wasNearBottom = isNearBottom();
    streamingRow.bubble.textContent += event.detail.delta;
    scrollToBottomIfNear(wasNearBottom);
  }

  if (event.status === "idle" && event.detail && "response" in event.detail) {
    setGenerating(false);
    if (event.detail.chat_id === activeChatId) {
      // A falsy run_id means model_interaction swallowed an exception before
      // any run was persisted - there's nothing to regenerate, so don't
      // offer a retry that would silently redo an unrelated older turn.
      const failed = !event.detail.response && !event.detail.run_id;
      const finalText = event.detail.response || "(No response - something went wrong.)";
      if (streamingRow) {
        streamingRow.row.remove();
        streamingRow = null;
      }
      const { bubble } = addMessageRow("assistant", finalText, null, event.detail.run_id, { noRetry: failed });
      if (failed) bubble.classList.add("bubble-error");
      refreshRetryVisibility();
      if (event.detail.response) showCanvasFromResponse(event.detail.response);
    }
  }

  if (event.status === "error") {
    setGenerating(false);
    hideThinkingIndicator();
    if (streamingRow) {
      streamingRow.row.remove();
      streamingRow = null;
    }
    if (event.detail) {
      // noRetry: this path fires when a command failed before any model run
      // was created, so there's nothing in the session to regenerate - a
      // retry button here would silently regenerate an unrelated older reply.
      const { bubble } = addMessageRow("assistant", `Something went wrong: ${event.detail}`, null, null, {
        noRetry: true,
      });
      bubble.classList.add("bubble-error");
      refreshRetryVisibility();
    }
  }
};

window.addEventListener("pywebviewready", async () => {
  api = window.pywebview.api;
  const status = await api.get_status();
  setStatus(status.status);
  await loadChatList();
});
