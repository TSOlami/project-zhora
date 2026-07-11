import numpy as np
import sounddevice as sd

from config import WAKE_WORD_THRESHOLD
from models.create_model_instance import create_wakeword_model
from modules.shared_state import engine_state

SAMPLE_RATE = 16000
CHUNK_SAMPLES = 1280  # 80ms at 16kHz, openWakeWord's recommended frame size


def listen_for_trigger_word(model=None, should_abort=None):
    """Blocks until the wake word is detected, or should_abort() returns True.

    Pass a pre-built `model` (from create_wakeword_model()) to avoid reloading
    it on every call - the engine reuses one across its whole listen loop.
    """
    try:
        if model is None:
            model = create_wakeword_model()

        print("Listening for trigger word...")

        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16") as stream:
            while True:
                if should_abort is not None and should_abort():
                    return False
                chunk, _ = stream.read(CHUNK_SAMPLES)
                audio_chunk = chunk.flatten()
                engine_state.push_amplitude(float(np.abs(audio_chunk).mean()))

                predictions = model.predict(audio_chunk)
                if any(score >= WAKE_WORD_THRESHOLD for score in predictions.values()):
                    return True

    except Exception as e:
        print(f"An error occurred: {e}")
        return False
