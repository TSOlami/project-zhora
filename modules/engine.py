import queue
import threading
import time

from config import AUTO_SPEAK_RESPONSES
from models.create_model_instance import create_wakeword_model
from modules import storage
from modules.command_processing import process_command
from modules.google_recog import recognize_speech_from_microphone
from modules.model_interaction import get_response_from_model
from modules.shared_state import engine_state
from modules.text_to_speech import speak_text
from modules.trigger_word_detection import listen_for_trigger_word

STREAM_REVEAL_WORDS_PER_CHUNK = 3
STREAM_REVEAL_DELAY_SECONDS = 0.02


class ZhoraEngine:
    """Controllable background service wrapping the wake-word -> STT -> LLM -> TTS loop.

    Runs on its own thread so a desktop UI can start/stop/restart it and poll
    engine_state for status, while also accepting typed prompts directly
    (bypassing wake-word + STT) for a chat-style interface. Typing at any
    point cancels an in-flight recording or TTS playback immediately, so
    switching from voice to text never means waiting out a timeout.
    """

    def __init__(self):
        self.state = engine_state
        self._stop_event = threading.Event()
        self._cancel_voice_event = threading.Event()
        self._typed_queue = queue.Queue()
        self._thread = None
        self._active_chat_id = None

    def start(self):
        if self.is_running():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self.state.set_status("stopped")

    def restart(self):
        self.stop()
        self.start()

    def is_running(self):
        return self._thread is not None and self._thread.is_alive()

    def set_active_chat(self, chat_id):
        self._active_chat_id = chat_id

    def submit_prompt(self, text, chat_id=None, source="typed"):
        self._cancel_voice_event.set()  # interrupt any in-flight recording/speaking
        self._typed_queue.put({"text": text, "chat_id": chat_id or self._active_chat_id, "source": source})

    def _ensure_active_chat(self):
        if self._active_chat_id is None:
            chats = storage.list_chats()
            self._active_chat_id = chats[0]["id"] if chats else storage.create_chat("Voice")

    def _run(self):
        self._ensure_active_chat()
        self.state.set_status("idle")

        wakeword_model = None
        wakeword_error = None
        try:
            wakeword_model = create_wakeword_model()
        except Exception as e:
            wakeword_error = str(e)

        while not self._stop_event.is_set():
            try:
                turn = self._typed_queue.get(timeout=0.2)
                self._process_turn(turn["text"], turn["chat_id"], concise=(turn.get("source") == "voice"))
                continue
            except queue.Empty:
                pass

            if wakeword_model is None:
                # No "Hey Zhora" model trained yet - typed chat still works,
                # just skip the voice loop instead of crashing it.
                if self.state.status != "voice_unavailable":
                    self.state.set_status("voice_unavailable", wakeword_error)
                continue

            self.state.set_status("listening_for_wake_word")
            detected = listen_for_trigger_word(
                model=wakeword_model,
                should_abort=lambda: self._stop_event.is_set() or not self._typed_queue.empty(),
            )
            if self._stop_event.is_set():
                break
            if not detected:
                continue  # interrupted by a typed prompt, or a transient error

            self.state.set_status("listening_for_command")
            self._cancel_voice_event.clear()
            command = recognize_speech_from_microphone(should_abort=self._cancel_voice_event.is_set)
            if self._cancel_voice_event.is_set():
                continue  # user started typing mid-recording; the typed prompt is already queued
            if command:
                self._process_turn(command, self._active_chat_id, concise=True)

        self.state.set_status("idle")

    def _process_turn(self, text, chat_id, concise=False):
        self._ensure_active_chat()
        chat_id = chat_id or self._active_chat_id
        mode = storage.get_chat_mode(chat_id)
        self.state.set_status("thinking")
        try:
            processed = process_command(text)
            response, tool_calls = get_response_from_model(processed, chat_id=chat_id, concise=concise, mode=mode)
        except Exception as e:
            self.state.set_status("error", str(e))
            return

        if tool_calls:
            self.state.set_status("tool_calls", {"chat_id": chat_id, "tool_calls": tool_calls})

        self.state.set_status("responding", {"chat_id": chat_id})
        for chunk in _reveal_chunks(response):
            self.state.set_status("streaming_chunk", {"chat_id": chat_id, "delta": chunk})
            time.sleep(STREAM_REVEAL_DELAY_SECONDS)

        if AUTO_SPEAK_RESPONSES:
            self.state.set_status("speaking")
            self._cancel_voice_event.clear()
            speak_text(response, should_abort=self._cancel_voice_event.is_set)

        self.state.set_status("idle", {"chat_id": chat_id, "response": response})


def _reveal_chunks(text, words_per_chunk=STREAM_REVEAL_WORDS_PER_CHUNK):
    """Split a completed response into word-groups for a simulated streaming
    reveal in the UI. Not real token-by-token LLM streaming (see README) -
    the model call itself is not streamed, only its already-complete result
    is drip-fed to the chat UI for the same growing-text visual effect.
    """
    words = text.split(" ")
    for i in range(0, len(words), words_per_chunk):
        piece = " ".join(words[i : i + words_per_chunk])
        if i + words_per_chunk < len(words):
            piece += " "
        yield piece


engine = ZhoraEngine()
