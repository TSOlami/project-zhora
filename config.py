import os

from dotenv import load_dotenv

load_dotenv()

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "taozhiyuai/llama-3-8b-lexi-uncensored:f16")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")

WAKE_WORD_NAME = os.getenv("WAKE_WORD_NAME", "hey_jarvis_v0.1")
WAKE_WORD_MODEL_PATH = os.getenv("WAKE_WORD_MODEL_PATH") or None
WAKE_WORD_THRESHOLD = float(os.getenv("WAKE_WORD_THRESHOLD", "0.5"))

# Fail-closed by default: every tool call must be explicitly approved.
REQUIRE_TOOL_CONFIRMATION = os.getenv("REQUIRE_TOOL_CONFIRMATION", "true").lower() not in ("false", "0", "no")
