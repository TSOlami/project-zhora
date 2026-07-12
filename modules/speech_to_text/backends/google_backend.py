import logging

import speech_recognition as sr

logger = logging.getLogger(__name__)


def recognize(audio_bytes, sample_rate):
    recognizer = sr.Recognizer()
    audio = sr.AudioData(audio_bytes, sample_rate, 2)
    try:
        return recognizer.recognize_google(audio)
    except sr.UnknownValueError:
        return None
    except sr.RequestError as e:
        logger.error("Could not request results from Google Speech Recognition service: %s", e)
        return None
