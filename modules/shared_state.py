import queue
import threading
import time


class ConfirmationRequest:
    """A pending tool-call approval, resolved by whichever channel answers first."""

    def __init__(self, function_name, arguments):
        self.function_name = function_name
        self.arguments = arguments
        self.event = threading.Event()
        self.result = None  # "approve" | "deny"

    def resolve(self, result):
        if self.event.is_set():
            return False
        self.result = result
        self.event.set()
        return True

    def wait(self, timeout):
        self.event.wait(timeout)
        return self.result


class EngineState:
    """Shared, thread-safe status + pending-confirmation state for the engine, UI, and voice/terminal confirmation channels.

    Events fan out to every subscriber (e.g. the tray icon AND the desktop
    window both need every event) - a single shared queue would only let one
    consumer win each item.
    """

    def __init__(self):
        self.status = "idle"
        self.pending_confirmation = None
        # Whether the chat window is currently shown vs. minimized to tray -
        # tracked here (rather than read off the pywebview Window object,
        # which exposes no such getter) so the tray's background-approval
        # notification (see tray.py) knows whether the user could actually
        # see a confirmation modal appear, or needs a toast instead.
        self.window_visible = True
        self._lock = threading.Lock()
        self._subscribers = []

    def subscribe(self):
        q = queue.Queue()
        with self._lock:
            self._subscribers.append(q)
        return q

    def _publish(self, event):
        with self._lock:
            subscribers = list(self._subscribers)
        for q in subscribers:
            q.put(event)

    def set_status(self, status, detail=None):
        self.status = status
        self._publish({"status": status, "detail": detail, "ts": time.time()})

    def set_window_visible(self, visible):
        self.window_visible = visible

    def push_amplitude(self, value):
        """Live mic volume during recording, for the voice-reactive UI animation.
        Does not change self.status - this is telemetry, not a state transition.
        """
        self._publish({"status": "amplitude", "detail": {"value": value}, "ts": time.time()})

    def push_partial_transcript(self, text):
        """Live interim STT guess for the "as you speak" caption. Telemetry,
        not a state transition - only fires for streaming-capable backends.
        """
        self._publish({"status": "partial_transcript", "detail": {"text": text}, "ts": time.time()})

    def begin_confirmation(self, function_name, arguments):
        req = ConfirmationRequest(function_name, arguments)
        with self._lock:
            self.pending_confirmation = req
        self.set_status("awaiting_confirmation", {"function_name": function_name, "arguments": arguments})
        return req

    def end_confirmation(self):
        with self._lock:
            self.pending_confirmation = None

    def resolve_confirmation(self, result):
        with self._lock:
            req = self.pending_confirmation
        if req is None:
            return False
        return req.resolve(result)


engine_state = EngineState()
