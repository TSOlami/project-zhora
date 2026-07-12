# Zhora - Voice-Activated AI Assistant

Zhora is a personal, local-first AI assistant that listens for a wake word, understands your spoken commands, and responds using a local AI language model via Ollama — no cloud LLM, no account walls. The full pipeline (wake word, speech-to-text, LLM, text-to-speech) runs fully offline by default.

## What Zhora Can Do

- Listen for the wake word "Hey Zhora" (custom-trained openWakeWord model) to activate
- Convert your spoken commands to text, fully offline by default (Vosk) - or via Google's
  cloud speech recognition if you opt into that instead
- Process your commands
- Generate intelligent, unrestricted responses using a local AI model
- Take actions via tools (web search, calculator, more can be added) using the Agno agent framework
- Speak responses out loud (text-to-speech)
- Run as a full desktop app: system tray control, and a chat interface with multiple
  conversations, per-chat memory, model switching, and tool management

## Technologies Used

- **Python**: Main programming language
- **openWakeWord**: Free, local, account-free wake word detection
- **sounddevice**: Audio input processing
- **Vosk**: Free, local, offline speech-to-text (default engine)
- **SpeechRecognition**: Speech-to-text abstraction; also wraps the optional Google cloud backend
- **Ollama**: Running local AI models
- **Llama 3**: AI language model (default: `taozhiyuai/llama-3-8b-lexi-uncensored:f16`, configurable)
- **Agno**: Agent framework providing the tool-calling library (web search, calculator, and more installable toolkits) — successor to Phidata
- **pyttsx3**: Text-to-speech conversion

## Project Structure

- **main.py**: Plain CLI entry point - just the voice loop, no UI
- **run_desktop.py**: Desktop app entry point - tray icon + chat window
- **config.py**: Loads configuration from `.env`
- **modules/**: Contains the core functionality
  - **engine.py**: Controllable background service (start/stop/restart) wrapping
    the wake-word -> STT -> LLM -> TTS loop; also accepts typed prompts directly
  - **trigger_word_detection.py**: Listens for the wake word
  - **speech_to_text/**: Speech recognition behind a pluggable backend
    (`base.py` documents the interface; `backends/` holds `vosk_backend.py`
    (default, offline) and `google_backend.py` (opt-in via `STT_ENGINE=google`))
  - **command_processing.py**: Processes recognized commands
  - **model_interaction.py**: Interacts with the AI model via Ollama/Agno, with
    persistent per-chat memory
  - **tool_registry.py**: Known toolkits + which ones are enabled
  - **tool_confirmation.py**: The dual-mode (voice or button) approval gate
  - **shared_state.py**: Engine status + pending-confirmation state shared
    between the engine, the confirmation gate, and the desktop UI
  - **storage.py**: Chat list/history, backed by Agno's own session database
  - **text_to_speech.py**: Converts text to speech
- **models/**: Contains model-related code
  - **create_model_instance.py**: Creates the openWakeWord model instance
- **desktop/**: The desktop client
  - **app.py**: pywebview window + the JS-Python API bridge
  - **tray.py**: System tray icon (start/stop/restart/open/quit)
  - **web/**: The chat UI itself (HTML/CSS/JS)

## Required External Services/Software

- Ollama installed locally (for running the Llama 3 model)
- A downloaded Vosk model for offline speech-to-text (see Setup below) - or,
  if you set `STT_ENGINE=google` instead, an internet connection and no
  model download

No account or API key is required for wake word detection, or for the default
(Vosk) speech-to-text backend.

## How It Works

1. The system continuously listens for the wake word
2. When detected, it starts recording your command
3. Your spoken command is converted to text locally via Vosk (or Google's cloud
   speech recognition, if you opted into `STT_ENGINE=google`)
4. The text is processed and sent to the local Llama 3 model running on Ollama
5. The AI model generates a response, which is printed and spoken aloud

## Setup

1. Clone the repo
2. Create a virtual environment:
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install required packages:
   ```
   pip install -r requirements.txt
   ```
4. Copy `.env.example` to `.env` and adjust values if needed:
   ```
   cp .env.example .env  # On Windows: copy .env.example .env
   ```
   `WAKE_WORD_MODEL_PATH` must point to a trained "Hey Zhora" model before the
   wake word listener will run (see step 5) - there's no pretrained "Zhora" model
   to fall back on, and no other assistant's wake word is used as a placeholder.

5. Train a custom "Hey Zhora" wake word:
   - Use openWakeWord's free [training Colab notebook](https://github.com/dscripka/openWakeWord) (no account/company email required, just a Google account for Colab)
   - Export the resulting `.onnx` model file into `models/wakeword/`
   - Set `WAKE_WORD_MODEL_PATH` in `.env` to point to that file

6. Download the offline speech-to-text model (skip this only if you're using
   `STT_ENGINE=google` instead):
   - Download `vosk-model-small-en-us-0.15.zip` from
     [alphacephei.com/vosk/models](https://alphacephei.com/vosk/models)
   - Unzip it so you end up with `data/models/vosk-model-small-en-us-0.15/`
     (containing `am/`, `conf/`, `graph/`, etc. directly inside it) - or set
     `VOSK_MODEL_PATH` in `.env` if you put it somewhere else

7. Install Ollama:
   - Follow instructions at https://ollama.ai/ to install Ollama
   - Pull the model set in `.env` (default shown below):
     ```
     ollama pull taozhiyuai/llama-3-8b-lexi-uncensored:f16
     ```

8. Run the application - either the plain CLI:
   ```
   python main.py
   ```
   or the desktop app (tray icon + chat window):
   ```
   python run_desktop.py
   ```

9. Say the wake word followed by your command, or type into the chat window

## Switching Models

`OLLAMA_MODEL` in `.env` is the only thing that needs to change to switch models —
no code edits. Pull whatever you switch to first (`ollama pull <model>`):

- Small/fast test model: `llama3.2:3b`
- Full uncensored model (this project's intended default): `taozhiyuai/llama-3-8b-lexi-uncensored:f16`

Not every Ollama model has a chat template that supports tool calling. If tool use
silently doesn't trigger, check that your pulled model's Modelfile supports Ollama's
tools API (most mainstream instruct models like Llama 3.1+, Qwen2.5, and Mistral do;
some community uncensored fine-tunes may not).

## Switching Speech-to-Text Engines

`STT_ENGINE` in `.env` picks the backend, no code edits needed:

- `vosk` (default) - fully offline, runs on-device. Needs the model download from
  Setup step 6. Swap in a different/larger Vosk model (more accurate, bigger
  download) by pointing `VOSK_MODEL_PATH` at it instead.
- `google` - Google's free Web Speech API. More accurate than the small Vosk
  model, but needs an internet connection and sends audio off-device.

Adding another backend (a different offline engine, a different cloud API) means
adding one module under `modules/speech_to_text/backends/` exposing a
`recognize(audio_bytes, sample_rate)` function (see `base.py`), then one line in
`modules/speech_to_text/recognizer.py`'s `_BACKEND_MODULES` - nothing else in the
app touches backends directly.

## Tools, Plugins, PC Control, and MCP

Zhora can act, not just chat, through four layers:

- **Built-in tools** (`modules/tool_registry.py`): a fixed, vetted set (`DuckDuckGoTools`,
  `CalculatorTools` today) - toggle them from the desktop app's Tools panel, or add
  more of Agno's prebuilt toolkits to `AVAILABLE_TOOLS`.
- **Local plugins** (`plugins/<id>/manifest.json` + `plugin.py`, loaded by
  `modules/plugin_registry.py`): drop-in Python toolkits for anything not in the
  built-in set - folder-based capability packs loaded on demand, similar in spirit
  to how other AI assistant platforms let you extend what the model can do. It's a
  local, manifest-driven system, not a hosted marketplace - plugins are full-trust
  local code, same as installing any other software. You put the file there;
  nothing is fetched or installed automatically. Ships two reference plugins:
  - **PC Control** (`plugins/pc_control/`): screenshot, mouse/keyboard automation,
    opening applications, shell command execution (`run_command`), and full
    filesystem read/write. Deliberately capable, not artificially limited - taking
    real action on your machine is the point.
  - **Office Documents** (`plugins/office_documents/`): creates real Excel
    (`.xlsx`), Word (`.docx`), PowerPoint (`.pptx`), and PDF files.
- **MCP servers** (`modules/mcp_registry.py`): connect any Model Context Protocol
  server (stdio or HTTP) as another tool source - the same open standard several
  AI desktop apps use for extensibility. Add one from the desktop app's Tools panel
  with a label and a command string (e.g.
  `npx -y @modelcontextprotocol/server-filesystem C:/some/dir`).

**Safety gate:** every tool call goes through Agno's native human-in-the-loop
mechanism - a run pauses instead of executing a gated function, and
`modules/tool_confirmation.py` blocks until approved via any of three channels
(whichever answers first wins):
- Saying "yes" or "no" out loud
- Clicking Approve/Deny in the desktop app (when it's open)
- Typing `y`/`N` in the terminal

This fails closed: no answer within 20 seconds, or anything other than an explicit
approval, blocks the call - the tool genuinely does not run until approved. Every
plugin, PC Control action, and MCP-sourced tool is **always** gated this way, no
exceptions - they're arbitrary local/external code, the same trust model as
installing any other software. This is the actual safety boundary: capability is
not restricted, but nothing that touches the filesystem, other processes, or the
machine itself runs without you seeing exactly what's about to happen and saying yes.

The built-in `web_search` and `calculator` toolkits are read-only/harmless by
design and run without confirmation (see `always_confirm` in
`modules/tool_registry.py`) - gating them added a 20+ second stall for trivial
questions with no real safety benefit. Any future built-in toolkit that isn't
obviously harmless should be added with `always_confirm=True`.

## Modes

Each chat has a mode (switch it in the topbar), which changes how Zhora responds -
distinct response-style profiles given to the same model, rather than separate
applications:

- **Chat** - conversational, to the point. Default.
- **Co-Work** - longer, structured responses for building something substantial
  (code, a document, a plan) collaboratively.
- **Code** - focused on programming: correct, working code with brief explanations.

Independent of mode: any turn that came from voice (wake word or the push-to-talk
mic button) automatically gets a instruction to keep the reply to 1-2 short spoken
sentences, since it's read aloud via TTS - nobody wants an assistant that yaps at
them. Typed messages don't get this constraint.

Note: unlike a dedicated terminal-based coding agent (repo-aware multi-file editing,
test running, git operations), Zhora's "Code" mode is a lighter-weight
response-style toggle within the same chat, not a full agentic coding loop - it
doesn't read your repo autonomously.

The Canvas panel (sidebar) is unrelated to mode - it opens automatically whenever a
response includes a code block, in any mode (automatic based on content, not a
manual toggle).

## Desktop Client

`python run_desktop.py` launches a tray icon plus a chat window:

- **Tray icon** - Start/Stop/Restart the engine, Open Zhora (show the window),
  Quit. Closing the window minimizes to tray; only Quit stops Zhora entirely.
  The icon color reflects live status (idle/listening/thinking/speaking/error/etc).
- **Chat window** - multiple named conversations in the sidebar, each with its own
  persistent memory (backed by Agno's session database, so context survives
  restarts). Typed messages and voice commands both land in the same chat history.
- **Settings panel** - switch models (reads what's installed via `ollama list`),
  set the wake word model path, toggle auto-speak.
- **Tools panel** - enable/disable individual toolkits.

The engine itself (`modules/engine.py`) runs on a background thread regardless of
whether the desktop app or `main.py` is running it, so the same wake-word/STT/LLM/TTS
pipeline backs both entry points.

## Future Development Plans

- Enhanced command processing with context awareness
- Custom "Hey Zhora" wake word model (see Setup step 5)
- Local offline speech recognition

## Contributing

Contributions, ideas, and feedback are welcome! Feel free to open issues or submit pull requests.
