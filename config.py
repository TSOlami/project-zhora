import os

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
os.makedirs(DATA_DIR, exist_ok=True)

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "taozhiyuai/llama-3-8b-lexi-uncensored:f16")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")

# "vosk" (default, offline) or "google" (cloud). See speech_to_text/base.py.
STT_ENGINE = os.getenv("STT_ENGINE", "vosk").lower()

VOSK_MODEL_PATH = os.getenv("VOSK_MODEL_PATH") or os.path.join(DATA_DIR, "models", "vosk-model-small-en-us-0.15")

# Trailing silence (seconds) that ends a recording, and the int16 amplitude
# threshold for "not silence" - too low a threshold never detects silence at
# all (room noise keeps it "started"; recording then runs until MAX_DURATION).
STT_SILENCE_DURATION = float(os.getenv("STT_SILENCE_DURATION", "0.8"))
STT_SILENCE_THRESHOLD = int(os.getenv("STT_SILENCE_THRESHOLD", "500"))

WAKE_WORD_NAME = os.getenv("WAKE_WORD_NAME")  # unset until a custom "Hey Zhora" model is trained
WAKE_WORD_MODEL_PATH = os.getenv("WAKE_WORD_MODEL_PATH") or None
WAKE_WORD_THRESHOLD = float(os.getenv("WAKE_WORD_THRESHOLD", "0.5"))

# Whether responses are spoken automatically. When off, TTS is still available
# on-demand per message in the desktop app.
#
# This and the setting below are read fresh on every call (not frozen into a
# module-level constant at import time, unlike OLLAMA_MODEL/WAKE_WORD_* above)
# because both are toggled at runtime from the desktop app's Settings panel -
# a frozen constant would silently keep the value from whenever config.py
# first got imported, so the toggle would only take effect after a full app
# restart. WAKE_WORD_* getting frozen is fine since changing those already
# requires an explicit engine Restart to reload the model; a plain on/off
# speech toggle has no such reason to need one.
def get_auto_speak_responses():
    return os.getenv("AUTO_SPEAK_RESPONSES", "true").lower() not in ("false", "0", "no")


# What the desktop window's close (X) button does: "ask" shows an in-app
# dialog (the default - matches the Slack/Discord/Spotify pattern of asking
# once and remembering the choice), "tray" always minimizes to the tray
# without asking, "quit" always exits the app fully.
def get_close_behavior():
    value = os.getenv("CLOSE_BEHAVIOR", "ask").lower()
    return value if value in ("ask", "tray", "quit") else "ask"


# Voice/rate/volume overrides for TTS. Unset (None) means "use whatever
# pyttsx3/SAPI5 already defaults to" rather than baking in a guessed value -
# the actual default depends on which voices are installed on this Windows
# install, so text_to_speech.py reads it straight from the engine itself.
def get_voice_id():
    return os.getenv("VOICE_ID") or None


def get_voice_rate():
    value = os.getenv("VOICE_RATE")
    return int(value) if value else None


def get_voice_volume():
    value = os.getenv("VOICE_VOLUME")
    return float(value) if value else None
