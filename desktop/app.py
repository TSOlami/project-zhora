import json
import logging
import os
import shutil
import subprocess
import threading

import webview

import config
from desktop.shortcut import is_start_on_boot_enabled, set_start_on_boot
from modules import storage, tool_registry
from modules.audio_feedback import play_wake_ack
from modules.engine import engine
from modules.env_file import set_env_value
from modules.google_recog import recognize_speech_from_microphone
from modules.model_interaction import get_current_model, set_current_model
from modules.shared_state import engine_state
from modules.text_to_speech import speak_text

logger = logging.getLogger(__name__)

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")


def _speak_in_background(text, **kwargs):
    """Runs speak_text() on a daemon thread with its own error handling -
    a bare `threading.Thread(target=speak_text, ...)` swallows exceptions
    into the default thread excepthook, which is invisible in the windowed
    pythonw.exe build (no console), so a TTS failure looks like the speaker
    button silently doing nothing.
    """

    def _run():
        try:
            speak_text(text, **kwargs)
        except Exception:
            logger.exception("Text-to-speech failed")

    threading.Thread(target=_run, daemon=True).start()


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
        self._quit_callback = None

    def set_window(self, window):
        self._window = window

    def set_quit_callback(self, callback):
        self._quit_callback = callback

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
        from modules.model_interaction import truncate_from_run

        chat = storage.get_chat(chat_id)
        if chat is None:
            return {"ok": False, "error": "Chat not found"}
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

    # --- Memory ---
    def list_memories(self):
        from modules.model_interaction import list_memories

        return list_memories()

    def delete_memory(self, memory_id):
        from modules.model_interaction import delete_memory

        delete_memory(memory_id)

    def clear_memories(self):
        from modules.model_interaction import clear_memories

        clear_memories()

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
        _speak_in_background(text)

    # --- Push-to-talk ---
    def start_voice_input(self, chat_id):
        if engine_state.status not in ("idle", "listening_for_wake_word", "voice_unavailable", "stopped"):
            return {"ok": False, "error": "Zhora is busy right now."}
        threading.Thread(target=self._capture_voice_input, args=(chat_id,), daemon=True).start()
        return {"ok": True}

    def _capture_voice_input(self, chat_id):
        play_wake_ack()
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

    def browse_wake_word_model(self):
        """Opens the native Windows file picker for the wake-word .onnx file,
        instead of asking the user to type or paste a filesystem path by hand.
        """
        if not self._window:
            return None
        result = self._window.create_file_dialog(
            webview.FileDialog.OPEN,
            file_types=("ONNX model (*.onnx)", "All files (*.*)"),
        )
        return result[0] if result else None

    # --- Settings ---
    def get_settings(self):
        from modules.text_to_speech import get_engine_defaults

        return {
            "ollama_model": get_current_model(),
            "wake_word_model_path": config.WAKE_WORD_MODEL_PATH or "",
            "wake_word_name": config.WAKE_WORD_NAME or "",
            "auto_speak_responses": config.get_auto_speak_responses(),
            "close_behavior": config.get_close_behavior(),
            "start_on_boot": is_start_on_boot_enabled(),
            "voice_id": config.get_voice_id() or "",
            "voice_rate": config.get_voice_rate(),
            "voice_volume": config.get_voice_volume(),
            "voice_engine_defaults": get_engine_defaults(),
        }

    def list_voices(self):
        from modules.text_to_speech import list_voices

        return list_voices()

    def preview_voice(self, voice_id, rate, volume):
        _speak_in_background(
            "This is how I sound.",
            voice_id=voice_id or None,
            rate=int(rate) if rate else None,
            volume=float(volume) if volume not in (None, "") else None,
        )
        return {"ok": True}

    def set_setting(self, key, value):
        allowed_keys = {
            "WAKE_WORD_MODEL_PATH",
            "WAKE_WORD_NAME",
            "WAKE_WORD_THRESHOLD",
            "AUTO_SPEAK_RESPONSES",
            "CLOSE_BEHAVIOR",
            "VOICE_ID",
            "VOICE_RATE",
            "VOICE_VOLUME",
        }
        if key not in allowed_keys:
            raise ValueError(f"Unknown setting: {key}")
        set_env_value(key, str(value))

    def set_start_on_boot(self, enabled):
        try:
            set_start_on_boot(enabled)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # --- Close-window behavior ---
    def resolve_close_choice(self, action, remember):
        """Called from the in-app "close Zhora?" dialog (shown when
        CLOSE_BEHAVIOR is "ask") once the user picks keep-in-tray or quit.
        """
        if remember:
            set_env_value("CLOSE_BEHAVIOR", action)
        if action == "quit":
            if self._quit_callback:
                self._quit_callback()
        elif self._window:
            engine_state.set_window_visible(False)
            self._window.hide()


def _pump_engine_events(window):
    subscription = engine_state.subscribe()
    while True:
        event = subscription.get()
        try:
            window.evaluate_js(f"window.onZhoraEvent({json.dumps(event)})")
        except Exception:
            pass  # window may be closed/destroyed


def build_window(hidden=False):
    """Create the pywebview window and API bridge, and start the event pump.

    Does not start the engine or the blocking webview event loop - the caller
    (run_desktop.py) owns startup ordering so it can also wire up the tray icon.

    hidden=True starts the window unshown (used for the --background autostart
    launch, so signing in doesn't immediately pop a chat window open - it just
    starts listening in the tray, same as if you'd minimized it yourself).

    Returns (window, api) - the caller needs the api reference too, to wire
    set_quit_callback() once the tray (which owns the actual quit sequence)
    exists.
    """
    api = Api()
    window = webview.create_window(
        "Zhora",
        os.path.join(WEB_DIR, "index.html"),
        js_api=api,
        width=1100,
        height=750,
        min_size=(720, 480),
        hidden=hidden,
    )
    api.set_window(window)

    threading.Thread(target=_pump_engine_events, args=(window,), daemon=True).start()
    return window, api
