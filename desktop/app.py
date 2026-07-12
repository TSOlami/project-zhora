import json
import os
import shutil
import subprocess
import threading

import webview

import config
from desktop.shortcut import create_desktop_shortcut
from modules import storage, tool_registry
from modules.engine import engine
from modules.env_file import set_env_value
from modules.google_recog import recognize_speech_from_microphone
from modules.model_interaction import get_current_model, set_current_model
from modules.shared_state import engine_state
from modules.text_to_speech import speak_text

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")


def _find_ollama_exe():
    found = shutil.which("ollama")
    if found:
        return found
    candidates = [
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe"),
        r"C:\Program Files\Ollama\ollama.exe",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return "ollama"  # last resort, will just fail cleanly if not found


class Api:
    def __init__(self):
        self._window = None

    def set_window(self, window):
        self._window = window

    # --- Chats ---
    def list_chats(self):
        return storage.list_chats()

    def create_chat(self, title="New chat", mode="chat"):
        return storage.create_chat(title, mode)

    def rename_chat(self, chat_id, title):
        storage.rename_chat(chat_id, title)

    def delete_chat(self, chat_id):
        storage.delete_chat(chat_id)

    def get_chat_mode(self, chat_id):
        return storage.get_chat_mode(chat_id)

    def set_chat_mode(self, chat_id, mode):
        storage.set_chat_mode(chat_id, mode)

    def get_messages(self, chat_id):
        return storage.get_messages(chat_id)

    def switch_chat(self, chat_id):
        engine.set_active_chat(chat_id)

    # --- Messaging ---
    def send_message(self, chat_id, text):
        engine.set_active_chat(chat_id)
        engine.submit_prompt(text, chat_id=chat_id)
        return {"ok": True}

    def retry_last_response(self, chat_id):
        from modules.model_interaction import regenerate_last_response

        text = regenerate_last_response(chat_id)
        if text is None:
            return {"ok": False, "error": "Nothing to retry"}
        engine.set_active_chat(chat_id)
        engine.submit_prompt(text, chat_id=chat_id)
        return {"ok": True}

    def edit_message_and_resend(self, chat_id, run_id, new_text):
        from modules.model_interaction import fork_conversation, truncate_from_run

        chat = storage.get_chat(chat_id)
        if chat is None:
            return {"ok": False, "error": "Chat not found"}
        forked_id = fork_conversation(chat_id)
        storage.register_forked_chat(forked_id, f"{chat['title']} (before edit)", chat["mode"])
        truncate_from_run(chat_id, run_id)
        engine.set_active_chat(chat_id)
        engine.submit_prompt(new_text, chat_id=chat_id)
        return {"ok": True}

    # --- Tools ---
    def list_tools(self):
        return tool_registry.list_tools()

    def set_tool_enabled(self, tool_id, enabled):
        tool_registry.set_tool_enabled(tool_id, enabled)
        from modules.model_interaction import refresh_tools

        refresh_tools()

    def add_mcp_server(self, label, command):
        import uuid

        from modules.mcp_registry import add_mcp_server

        server_id = uuid.uuid4().hex[:8]
        add_mcp_server(server_id, label, command)

    def remove_mcp_server(self, server_id):
        from modules.mcp_registry import remove_mcp_server

        remove_mcp_server(server_id)
        from modules.model_interaction import refresh_tools

        refresh_tools()

    # --- Model ---
    def get_current_model(self):
        return get_current_model()

    def list_installed_models(self):
        try:
            result = subprocess.run([_find_ollama_exe(), "list"], capture_output=True, text=True, timeout=5)
            lines = result.stdout.strip().splitlines()[1:]
            return [line.split()[0] for line in lines if line.strip()]
        except Exception:
            return [get_current_model()]

    def set_current_model(self, model_id):
        set_current_model(model_id)

    # --- Confirmation ---
    def approve_call(self):
        engine_state.resolve_confirmation("approve")

    def deny_call(self):
        engine_state.resolve_confirmation("deny")

    # --- On-demand TTS ---
    def speak_message(self, text):
        threading.Thread(target=speak_text, args=(text,), daemon=True).start()

    # --- Push-to-talk ---
    def start_voice_input(self, chat_id):
        if engine_state.status not in ("idle", "listening_for_wake_word", "voice_unavailable", "stopped"):
            return {"ok": False, "error": "Zhora is busy right now."}
        threading.Thread(target=self._capture_voice_input, args=(chat_id,), daemon=True).start()
        return {"ok": True}

    def _capture_voice_input(self, chat_id):
        engine_state.set_status("listening_for_command")
        command = recognize_speech_from_microphone()
        if command:
            engine.set_active_chat(chat_id)
            engine.submit_prompt(command, chat_id=chat_id, source="voice")
        else:
            engine_state.set_status("idle")

    # --- Engine control ---
    def start_engine(self):
        engine.start()

    def stop_engine(self):
        engine.stop()

    def restart_engine(self):
        engine.restart()

    def get_status(self):
        return {"status": engine_state.status, "running": engine.is_running()}

    # --- Settings ---
    def get_settings(self):
        return {
            "ollama_model": get_current_model(),
            "wake_word_model_path": config.WAKE_WORD_MODEL_PATH or "",
            "wake_word_name": config.WAKE_WORD_NAME or "",
            "auto_speak_responses": config.AUTO_SPEAK_RESPONSES,
        }

    def set_setting(self, key, value):
        allowed_keys = {
            "WAKE_WORD_MODEL_PATH",
            "WAKE_WORD_NAME",
            "WAKE_WORD_THRESHOLD",
            "AUTO_SPEAK_RESPONSES",
        }
        if key not in allowed_keys:
            raise ValueError(f"Unknown setting: {key}")
        set_env_value(key, str(value))

    def create_desktop_shortcut(self):
        try:
            path = create_desktop_shortcut()
            return {"ok": True, "path": path}
        except Exception as e:
            return {"ok": False, "error": str(e)}


def _pump_engine_events(window):
    subscription = engine_state.subscribe()
    while True:
        event = subscription.get()
        try:
            window.evaluate_js(f"window.onZhoraEvent({json.dumps(event)})")
        except Exception:
            pass  # window may be closed/destroyed


def build_window():
    """Create the pywebview window and API bridge, and start the event pump.

    Does not start the engine or the blocking webview event loop - the caller
    (run_desktop.py) owns startup ordering so it can also wire up the tray icon.
    """
    api = Api()
    window = webview.create_window(
        "Zhora",
        os.path.join(WEB_DIR, "index.html"),
        js_api=api,
        width=1100,
        height=750,
        min_size=(720, 480),
    )
    api.set_window(window)

    threading.Thread(target=_pump_engine_events, args=(window,), daemon=True).start()
    return window
