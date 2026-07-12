import logging

import config
from modules.speech_to_text.recording import SAMPLE_RATE, record_until_silence

logger = logging.getLogger(__name__)

# config.STT_ENGINE -> backend module import path. See base.py.
_BACKEND_MODULES = {
    "vosk": "modules.speech_to_text.backends.vosk_backend",
    "google": "modules.speech_to_text.backends.google_backend",
}

_backend_cache = {}


def _get_backend(name):
    if name not in _backend_cache:
        module_path = _BACKEND_MODULES.get(name)
        if module_path is None:
            raise ValueError(f"Unknown STT_ENGINE '{name}' - expected one of {sorted(_BACKEND_MODULES)}")
        import importlib

        _backend_cache[name] = importlib.import_module(module_path)
    return _backend_cache[name]


def recognize_speech_from_microphone(should_abort=None, on_partial=None):
    """on_partial(text), if given, gets the backend's interim guess while the
    user is still talking - only called by SUPPORTS_STREAMING backends.
    """
    logger.info("Listening...")
    backend = _get_backend(config.STT_ENGINE)

    if getattr(backend, "SUPPORTS_STREAMING", False):
        stream = backend.create_stream(SAMPLE_RATE)

        def _on_chunk(chunk_bytes):
            partial = stream.feed(chunk_bytes)
            if partial and on_partial is not None:
                on_partial(partial)

        record_until_silence(should_abort=should_abort, on_chunk=_on_chunk)
        text = stream.finish()
    else:
        raw_audio = record_until_silence(should_abort=should_abort)
        text = backend.recognize(raw_audio, SAMPLE_RATE) if raw_audio is not None else None

    if text:
        logger.info("Recognized: %s", text)
    else:
        logger.info("%s could not understand audio", config.STT_ENGINE)
    return text
