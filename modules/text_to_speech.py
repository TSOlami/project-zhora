import pyttsx3

_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        _engine = pyttsx3.init()
    return _engine


def speak_text(text):
    if not text:
        return
    engine = _get_engine()
    engine.say(text)
    engine.runAndWait()
