import logging

import numpy as np
import sounddevice as sd

logger = logging.getLogger(__name__)

_SAMPLE_RATE = 16000


def _tone(freq, duration, fade=0.008):
    """A sine-wave tone with a short fade in/out so it doesn't click at the edges."""
    t = np.linspace(0, duration, int(_SAMPLE_RATE * duration), endpoint=False)
    wave = np.sin(2 * np.pi * freq * t)
    fade_samples = int(_SAMPLE_RATE * fade)
    envelope = np.ones_like(wave)
    envelope[:fade_samples] = np.linspace(0, 1, fade_samples)
    envelope[-fade_samples:] = np.linspace(1, 0, fade_samples)
    return (wave * envelope).astype(np.float32)


def play_wake_ack():
    """A short two-tone chime confirming the wake word was heard - the same
    instant-tone convention as Alexa/Google Home, rather than a spoken
    acknowledgment, which would take an extra beat to synthesize.
    """
    gap = np.zeros(int(_SAMPLE_RATE * 0.02), dtype=np.float32)
    chime = np.concatenate([_tone(880.0, 0.09), gap, _tone(1318.5, 0.11)]) * 0.2
    try:
        sd.play(chime, samplerate=_SAMPLE_RATE, blocking=True)
    except Exception:
        logger.exception("Failed to play wake-word chime")
