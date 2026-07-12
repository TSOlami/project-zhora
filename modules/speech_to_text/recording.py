import numpy as np
import sounddevice as sd

import config
from modules.shared_state import engine_state

SAMPLE_RATE = 16000
CHUNK_DURATION = 0.05  # seconds per chunk analyzed for silence
MAX_DURATION = 15  # hard cap on recording length, seconds


def record_until_silence(should_abort=None, on_chunk=None):
    """Raw 16-bit PCM mono bytes from the mic, from first sound until a
    trailing silence gap (or MAX_DURATION).

    on_chunk(chunk_bytes), if given, is called with each chunk as it's
    captured - lets a streaming backend feed its recognizer live without
    duplicating this silence-detection loop.
    """
    silence_threshold = config.STT_SILENCE_THRESHOLD
    chunk_samples = int(SAMPLE_RATE * CHUNK_DURATION)
    silence_chunks_needed = int(config.STT_SILENCE_DURATION / CHUNK_DURATION)
    max_chunks = int(MAX_DURATION / CHUNK_DURATION)

    frames = []
    silent_chunks = 0
    started = False

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16") as stream:
        for _ in range(max_chunks):
            if should_abort is not None and should_abort():
                break
            chunk, _ = stream.read(chunk_samples)
            frames.append(chunk.copy())
            if on_chunk is not None:
                on_chunk(chunk.tobytes())

            volume = np.abs(chunk).mean()
            engine_state.push_amplitude(float(volume))
            if volume > silence_threshold:
                started = True
                silent_chunks = 0
            elif started:
                silent_chunks += 1
                if silent_chunks >= silence_chunks_needed:
                    break

    if not frames:
        return None
    audio_data = np.concatenate(frames, axis=0)
    return audio_data.tobytes()
