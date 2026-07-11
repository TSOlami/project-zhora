import os

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
os.makedirs(DATA_DIR, exist_ok=True)

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "taozhiyuai/llama-3-8b-lexi-uncensored:f16")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")

WAKE_WORD_NAME = os.getenv("WAKE_WORD_NAME")  # unset until a custom "Hey Zhora" model is trained
WAKE_WORD_MODEL_PATH = os.getenv("WAKE_WORD_MODEL_PATH") or None
WAKE_WORD_THRESHOLD = float(os.getenv("WAKE_WORD_THRESHOLD", "0.5"))

# Fail-closed by default: every tool call must be explicitly approved.
REQUIRE_TOOL_CONFIRMATION = os.getenv("REQUIRE_TOOL_CONFIRMATION", "true").lower() not in ("false", "0", "no")
