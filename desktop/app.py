import json
import os
import shutil
import subprocess
import threading

import webview

import config
from modules import storage, tool_registry
from modules.engine import engine
from modules.env_file import set_env_value
from modules.model_interaction import get_current_model, set_current_model
from modules.shared_state import engine_state

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

    def create_chat(self, title="New chat"):
        return storage.create_chat(title)

    def rename_chat(self, chat_id, title):
        storage.rename_chat(chat_id, title)

    def delete_chat(self, chat_id):
        storage.delete_chat(chat_id)

    def get_messages(self, chat_id):
        return storage.get_messages(chat_id)

    def switch_chat(self, chat_id):
        engine.set_active_chat(chat_id)

    # --- Messaging ---
    def send_message(self, chat_id, text):
        engine.set_active_chat(chat_id)
        engine.submit_prompt(text, chat_id=chat_id)
        return {"ok": True}

    # --- Tools ---
    def list_tools(self):
        return tool_registry.list_tools()

    def set_tool_enabled(self, tool_id, enabled):
        tool_registry.set_tool_enabled(tool_id, enabled)
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
            "require_tool_confirmation": config.REQUIRE_TOOL_CONFIRMATION,
        }

    def set_setting(self, key, value):
        allowed_keys = {"WAKE_WORD_MODEL_PATH", "WAKE_WORD_NAME", "REQUIRE_TOOL_CONFIRMATION", "WAKE_WORD_THRESHOLD"}
        if key not in allowed_keys:
            raise ValueError(f"Unknown setting: {key}")
        set_env_value(key, str(value))


def _pump_engine_events(window):
    while True:
        event = engine_state.status_queue.get()
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
