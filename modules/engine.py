import logging
import queue
import threading

from config import get_auto_speak_responses
from models.create_model_instance import create_wakeword_model
from modules import storage
from modules.audio_feedback import play_wake_ack
from modules.command_processing import process_command
from modules.google_recog import recognize_speech_from_microphone
from modules.model_interaction import force_remember_if_triggered, stream_response_from_model
from modules.shared_state import engine_state
from modules.text_to_speech import speak_text
from modules.trigger_word_detection import listen_for_trigger_word

logger = logging.getLogger(__name__)


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
            logger.exception("Failed to load wake-word model")

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

            logger.info("Wake word detected")
            play_wake_ack()
            self.state.set_status("listening_for_command")
            self._cancel_voice_event.clear()
            command = recognize_speech_from_microphone(
                should_abort=lambda: self._stop_event.is_set() or self._cancel_voice_event.is_set()
            )
            if self._cancel_voice_event.is_set():
                continue  # user started typing mid-recording; the typed prompt is already queued
            if command:
                self._process_turn(command, self._active_chat_id, concise=True)

        self.state.set_status("idle")

    def _process_turn(self, text, chat_id, concise=False):
        self._ensure_active_chat()
        chat_id = chat_id or self._active_chat_id
        mode = storage.get_chat_mode(chat_id)
        new_title = storage.maybe_autotitle_chat(chat_id, text)
        if new_title is not None:
            self.state.set_status("chat_renamed", {"chat_id": chat_id, "title": new_title})
        force_remember_if_triggered(text)
        self.state.set_status("thinking")
        processed = process_command(text)

        run_id = None
        tool_calls = []
        response = ""
        started_responding = False
        try:
            for kind, *payload in stream_response_from_model(processed, chat_id=chat_id, concise=concise, mode=mode):
                if kind == "started":
                    run_id = payload[0]
                elif kind == "tool_call":
                    tool_calls.append(payload[0])
                    self.state.set_status("tool_calls", {"chat_id": chat_id, "tool_calls": tool_calls})
                elif kind == "chunk":
                    if not started_responding:
                        # user_text lets the UI render the prompt bubble for
                        # voice-originated turns too, since those never went
                        # through the typed send path that renders it
                        # optimistically.
                        self.state.set_status(
                            "responding", {"chat_id": chat_id, "run_id": run_id, "user_text": text}
                        )
                        started_responding = True
                    self.state.set_status("streaming_chunk", {"chat_id": chat_id, "delta": payload[0]})
                elif kind == "done":
                    response, tool_calls, run_id = payload
        except Exception as e:
            logger.exception("Model response streaming failed")
            self.state.set_status("error", str(e))
            return

        if not started_responding:
            # Nothing ever streamed (e.g. an empty/failed response) - the UI
            # still needs a "responding" event before "idle" to clear the
            # thinking indicator and create a row to replace.
            self.state.set_status("responding", {"chat_id": chat_id, "run_id": run_id, "user_text": text})

        if get_auto_speak_responses():
            self.state.set_status("speaking")
            self._cancel_voice_event.clear()
            # Backgrounded so a slow CPU-bound TTS pass doesn't delay "idle" -
            # the turn is done once the text is ready, speech just plays
            # alongside it (same as the existing interrupt-on-type behavior,
            # which already treats speech as freely interruptible).
            #
            # Wrapped in its own try/except (rather than left to the global
            # threading.excepthook safety net) so a TTS failure logs with
            # actual context and shows up as a clearly-labeled chat bubble,
            # not just "Thread-7: <error>".
            def _speak_and_report():
                try:
                    speak_text(response, should_abort=self._cancel_voice_event.is_set)
                except Exception as e:
                    logger.exception("Text-to-speech failed")
                    self.state.set_status("error", f"Text-to-speech failed: {e}")

            threading.Thread(target=_speak_and_report, daemon=True).start()

        self.state.set_status("idle", {"chat_id": chat_id, "response": response, "run_id": run_id})


engine = ZhoraEngine()
