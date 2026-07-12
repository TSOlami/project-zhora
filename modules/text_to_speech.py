import threading

import pyttsx3

_engine = None
_engine_lock = threading.Lock()  # only one thread may be inside say()/runAndWait() at a time
_active_token = None  # identifies the most recent speak_text() call


def _get_engine():
    global _engine
    if _engine is None:
        _engine = pyttsx3.init()
    return _engine


def speak_text(text, should_abort=None):
    """Speaks text on the single shared pyttsx3 engine.

    pyttsx3's engine (SAPI5, on Windows) is a single COM object that isn't
    safe to drive from two threads at once - calling say()/runAndWait()
    concurrently (e.g. from rapid repeat clicks on a "read aloud" button,
    each of which runs on its own thread) raises RuntimeError or leaves the
    engine's internal state broken for later callers, including the normal
    auto-speak-after-response path. A newer call supersedes whatever is
    currently playing (interrupted via engine.stop()) rather than queuing
    behind it or racing it, so only the latest request is ever heard.
    """
    if not text:
        return

    global _active_token
    token = object()
    _active_token = token
    engine = _get_engine()

    def superseded():
        return _active_token is not token or (should_abort is not None and should_abort())

    with _engine_lock:
        if superseded():
            return

        watcher_stop = threading.Event()

        def _watch():
            while not watcher_stop.is_set():
                if superseded():
                    engine.stop()
                    return
                watcher_stop.wait(0.1)

        threading.Thread(target=_watch, daemon=True).start()
        engine.say(text)
        engine.runAndWait()
        watcher_stop.set()
