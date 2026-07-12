import logging
import os
import threading

import sounddevice as sd
from piper.config import SynthesisConfig
from piper.voice import PiperVoice

import config

logger = logging.getLogger(__name__)

_voices_cache = {}
_voices_cache_lock = threading.Lock()


def _load_voice(model_path):
    if model_path not in _voices_cache:
        with _voices_cache_lock:
            if model_path not in _voices_cache:
                if not os.path.isfile(model_path):
                    raise FileNotFoundError(
                        f"Piper voice not found at '{model_path}'. Download a voice (e.g. via "
                        "`python -m piper.download_voices en_US-lessac-medium <dest_dir>`) or point "
                        "VOICE_ID/PIPER_MODEL_PATH at wherever you put one."
                    )
                logger.info("Loading Piper voice from %s", model_path)
                _voices_cache[model_path] = PiperVoice.load(model_path)
    return _voices_cache[model_path]


def list_voices():
    """[{"id": ..., "name": ...}, ...] for every *.onnx file alongside PIPER_MODEL_PATH."""
    voice_dir = os.path.dirname(config.PIPER_MODEL_PATH)
    if not os.path.isdir(voice_dir):
        return []
    return [
        {"id": os.path.join(voice_dir, f), "name": f[: -len(".onnx")]}
        for f in sorted(os.listdir(voice_dir))
        if f.endswith(".onnx")
    ]


def get_engine_defaults():
    return {"voice_id": config.PIPER_MODEL_PATH, "rate": 1.0, "volume": 1.0}


_active_token = None  # identifies the most recent speak_text() call


def speak_text(text, should_abort=None, voice_id=None, rate=None, volume=None):
    """Speaks text via a local Piper voice, playing the synthesized audio
    through sounddevice/PortAudio.

    A newer call supersedes whatever is currently playing (via sd.stop())
    rather than queuing behind it, so only the latest request is ever heard.

    voice_id/rate/volume override the persisted settings (config.get_voice_*)
    for this call only - used by the Settings panel's "Preview" button.
    """
    if not text:
        return

    global _active_token
    token = object()
    _active_token = token

    def superseded():
        return _active_token is not token or (should_abort is not None and should_abort())

    if superseded():
        return

    model_path = voice_id or config.get_voice_id() or config.PIPER_MODEL_PATH
    voice = _load_voice(model_path)
    syn_config = SynthesisConfig(
        length_scale=rate if rate is not None else (config.get_voice_rate() or 1.0),
        volume=volume if volume is not None else (config.get_voice_volume() if config.get_voice_volume() is not None else 1.0),
    )

    for chunk in voice.synthesize(text, syn_config=syn_config):
        if superseded():
            sd.stop()
            return
        sd.play(chunk.audio_float_array, chunk.sample_rate)
        stream = sd.get_stream()
        while stream is not None and stream.active:
            if superseded():
                sd.stop()
                return
            sd.sleep(50)
