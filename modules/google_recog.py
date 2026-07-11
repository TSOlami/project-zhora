import numpy as np
import sounddevice as sd
import speech_recognition as sr

SAMPLE_RATE = 16000
CHUNK_DURATION = 0.05  # seconds per chunk analyzed for silence
SILENCE_THRESHOLD = 500  # int16 amplitude below which audio is considered silence
SILENCE_DURATION = 1.5  # seconds of trailing silence that ends recording
MAX_DURATION = 15  # hard cap on recording length, seconds


def _record_until_silence():
    chunk_samples = int(SAMPLE_RATE * CHUNK_DURATION)
    silence_chunks_needed = int(SILENCE_DURATION / CHUNK_DURATION)
    max_chunks = int(MAX_DURATION / CHUNK_DURATION)

    frames = []
    silent_chunks = 0
    started = False

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16") as stream:
        for _ in range(max_chunks):
            chunk, _ = stream.read(chunk_samples)
            frames.append(chunk.copy())

            volume = np.abs(chunk).mean()
            if volume > SILENCE_THRESHOLD:
                started = True
                silent_chunks = 0
            elif started:
                silent_chunks += 1
                if silent_chunks >= silence_chunks_needed:
                    break

    audio_data = np.concatenate(frames, axis=0)
    return audio_data.tobytes()


def recognize_speech_from_microphone():
    recognizer = sr.Recognizer()

    print("Listening...")
    raw_audio = _record_until_silence()
    audio = sr.AudioData(raw_audio, SAMPLE_RATE, 2)

    try:
        text = recognizer.recognize_google(audio)
        print(f"Recognized: {text}")
        return text
    except sr.UnknownValueError:
        print("Google Speech Recognition could not understand audio")
        return None
    except sr.RequestError as e:
        print(f"Could not request results from Google Speech Recognition service; {e}")
        return None
