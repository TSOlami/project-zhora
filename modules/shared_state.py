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
    """Shared, thread-safe status + pending-confirmation state for the engine, UI, and voice/terminal confirmation channels."""

    def __init__(self):
        self.status = "idle"
        self.status_queue = queue.Queue()
        self.pending_confirmation = None
        self._lock = threading.Lock()

    def set_status(self, status, detail=None):
        self.status = status
        self.status_queue.put({"status": status, "detail": detail, "ts": time.time()})

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
