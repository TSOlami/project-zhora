import os

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
os.makedirs(DATA_DIR, exist_ok=True)

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "taozhiyuai/llama-3-8b-lexi-uncensored:f16")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")

# Speech-to-text backend: "vosk" (default - fully offline, no network calls)
# or "google" (Google's free Web Speech API - needs internet, no model
# download). See modules/speech_to_text/base.py for how to add another one.
# Frozen at import time like OLLAMA_MODEL above since backends lazily load/
# cache their model on first use - switching engines needs an app restart.
STT_ENGINE = os.getenv("STT_ENGINE", "vosk").lower()

# Only read by the vosk backend. Defaults to the small English model's
# expected location under data/models/ (see the setup guide for the
# download link) - override if you put it, or a different Vosk model,
# somewhere else.
VOSK_MODEL_PATH = os.getenv("VOSK_MODEL_PATH") or os.path.join(DATA_DIR, "models", "vosk-model-small-en-us-0.15")

# How much trailing silence (seconds) ends a voice recording, and how loud
# (int16 amplitude) counts as "not silence". Lower duration = feels snappier
# but risks cutting off speech during a mid-sentence pause; too low a
# threshold picks up room noise/breath as speech and never detects silence at
# all (recording then runs until MAX_DURATION in recording.py instead).
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
