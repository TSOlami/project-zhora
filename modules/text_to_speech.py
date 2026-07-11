import threading

import pyttsx3

_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        _engine = pyttsx3.init()
    return _engine


def speak_text(text, should_abort=None):
    if not text:
        return
    engine = _get_engine()

    watcher_stop = threading.Event()
    if should_abort is not None:
        def _watch():
            while not watcher_stop.is_set():
                if should_abort():
                    engine.stop()
                    return
                watcher_stop.wait(0.1)

        threading.Thread(target=_watch, daemon=True).start()

    engine.say(text)
    engine.runAndWait()
    watcher_stop.set()
