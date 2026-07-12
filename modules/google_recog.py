import logging

import numpy as np
import sounddevice as sd
import speech_recognition as sr

from modules.shared_state import engine_state

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000
CHUNK_DURATION = 0.05  # seconds per chunk analyzed for silence
SILENCE_THRESHOLD = 500  # int16 amplitude below which audio is considered silence
SILENCE_DURATION = 1.5  # seconds of trailing silence that ends recording
MAX_DURATION = 15  # hard cap on recording length, seconds


def _record_until_silence(should_abort=None):
    chunk_samples = int(SAMPLE_RATE * CHUNK_DURATION)
    silence_chunks_needed = int(SILENCE_DURATION / CHUNK_DURATION)
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

            volume = np.abs(chunk).mean()
            engine_state.push_amplitude(float(volume))
            if volume > SILENCE_THRESHOLD:
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


def recognize_speech_from_microphone(should_abort=None):
    recognizer = sr.Recognizer()

    logger.info("Listening...")
    raw_audio = _record_until_silence(should_abort=should_abort)
    if raw_audio is None:
        return None
    audio = sr.AudioData(raw_audio, SAMPLE_RATE, 2)

    try:
        text = recognizer.recognize_google(audio)
        logger.info("Recognized: %s", text)
        return text
    except sr.UnknownValueError:
        logger.info("Google Speech Recognition could not understand audio")
        return None
    except sr.RequestError as e:
        logger.error("Could not request results from Google Speech Recognition service: %s", e)
        return None
