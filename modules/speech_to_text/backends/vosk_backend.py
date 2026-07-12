import json
import logging
import os

import vosk

import config

logger = logging.getLogger(__name__)

vosk.SetLogLevel(-1)  # silence Kaldi's own verbose stderr logging

_model = None  # loaded lazily, once, on first recognize() call


def _get_model():
    global _model
    if _model is None:
        if not os.path.isdir(config.VOSK_MODEL_PATH):
            raise FileNotFoundError(
                f"Vosk model not found at '{config.VOSK_MODEL_PATH}'. Download it (e.g. "
                "vosk-model-small-en-us-0.15 from https://alphacephei.com/vosk/models) and "
                "extract it to that path, or point VOSK_MODEL_PATH at wherever you put it."
            )
        logger.info("Loading Vosk model from %s", config.VOSK_MODEL_PATH)
        _model = vosk.Model(config.VOSK_MODEL_PATH)
    return _model


def recognize(audio_bytes, sample_rate):
    recognizer = vosk.KaldiRecognizer(_get_model(), sample_rate)
    recognizer.AcceptWaveform(audio_bytes)
    result = json.loads(recognizer.FinalResult())
    return result.get("text") or None


# Vosk is built for incremental use - unlike a batch cloud API, it can return
# its best-guess-so-far after every chunk, which is what powers the "text
# appears as you speak" live caption in the desktop UI. See
# speech_to_text/recognizer.py for how SUPPORTS_STREAMING is used.
SUPPORTS_STREAMING = True


class _Stream:
    def __init__(self, recognizer):
        self._recognizer = recognizer

    def feed(self, chunk_bytes):
        """Interim best-guess text so far, or None. Called once per audio chunk."""
        if self._recognizer.AcceptWaveform(chunk_bytes):
            # Vosk's own internal endpointer detected a completed segment
            # (e.g. a longer pause mid-command) - PartialResult() would be
            # empty right after this, so surface the segment that just
            # finished instead of letting the caption flicker back to blank.
            result = json.loads(self._recognizer.Result())
            return result.get("text") or None
        partial = json.loads(self._recognizer.PartialResult())
        return partial.get("partial") or None

    def finish(self):
        """The final transcript once recording has stopped."""
        result = json.loads(self._recognizer.FinalResult())
        return result.get("text") or None


def create_stream(sample_rate):
    return _Stream(vosk.KaldiRecognizer(_get_model(), sample_rate))
