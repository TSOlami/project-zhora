# Zhora - Voice-Activated AI Assistant

Zhora is a personal, local-first AI assistant that listens for a wake word, understands your spoken commands, and responds using a local AI language model via Ollama — no cloud LLM, no account walls.

## What Zhora Can Do

- Listen for the wake word "Hey Zhora" (custom-trained openWakeWord model) to activate
- Convert your spoken commands to text using Google's speech recognition
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
- **SpeechRecognition**: Converting speech to text using Google's service
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
  - **google_recog.py**: Handles speech recognition
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

- Internet connection (for Google Speech Recognition)
- Ollama installed locally (for running the Llama 3 model)

No account or API key is required for wake word detection.

## How It Works

1. The system continuously listens for the wake word
2. When detected, it starts recording your command
3. Your spoken command is converted to text using Google's speech recognition
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

6. Install Ollama:
   - Follow instructions at https://ollama.ai/ to install Ollama
   - Pull the model set in `.env` (default shown below):
     ```
     ollama pull taozhiyuai/llama-3-8b-lexi-uncensored:f16
     ```

7. Run the application - either the plain CLI:
   ```
   python main.py
   ```
   or the desktop app (tray icon + chat window):
   ```
   python run_desktop.py
   ```

8. Say the wake word followed by your command, or type into the chat window

## Switching Models

`OLLAMA_MODEL` in `.env` is the only thing that needs to change to switch models —
no code edits. Pull whatever you switch to first (`ollama pull <model>`):

- Small/fast test model: `llama3.2:3b`
- Full uncensored model (this project's intended default): `taozhiyuai/llama-3-8b-lexi-uncensored:f16`

Not every Ollama model has a chat template that supports tool calling. If tool use
silently doesn't trigger, check that your pulled model's Modelfile supports Ollama's
tools API (most mainstream instruct models like Llama 3.1+, Qwen2.5, and Mistral do;
some community uncensored fine-tunes may not).

## Tools, Plugins, and PC Control

Zhora can act, not just chat, through three layers:

- **Built-in tools** (`modules/tool_registry.py`): a fixed, vetted set (`DuckDuckGoTools`,
  `CalculatorTools` today) - toggle them from the desktop app's Tools panel, or add
  more of Agno's prebuilt toolkits to `AVAILABLE_TOOLS`.
- **Local plugins** (`plugins/<id>/manifest.json` + `plugin.py`, loaded by
  `modules/plugin_registry.py`): drop-in Python toolkits for anything not in the
  built-in set. This is a local, manifest-driven system, not a hosted marketplace -
  plugins are full-trust local code, same as installing any other software. You put
  the file there; nothing is fetched or installed automatically.
- **PC Control** (`plugins/pc_control/`): ships as the reference plugin. Screenshot,
  mouse/keyboard automation, opening applications, shell command execution
  (`run_command`), and full filesystem read/write. It is deliberately capable, not
  artificially limited - taking real action on your machine is the point.

**Safety gate:** every tool call goes through Agno's native human-in-the-loop
mechanism - a run pauses instead of executing a gated function, and
`modules/tool_confirmation.py` blocks until approved via any of three channels
(whichever answers first wins):
- Saying "yes" or "no" out loud
- Clicking Approve/Deny in the desktop app (when it's open)
- Typing `y`/`N` in the terminal

This fails closed: no answer within 20 seconds, or anything other than an explicit
approval, blocks the call - the tool genuinely does not run until approved. Every
plugin and every PC Control action is **always** gated this way regardless of the
`REQUIRE_TOOL_CONFIRMATION` setting; that setting only affects the built-in tools.
This is the actual safety boundary: capability is not restricted, but nothing runs
without you seeing exactly what's about to happen and saying yes.

Set `REQUIRE_TOOL_CONFIRMATION=false` in `.env` (or the desktop app's Settings panel)
to skip confirmation for the *built-in* tools only, once you trust them.

## Desktop Client

`python run_desktop.py` launches a tray icon plus a chat window:

- **Tray icon** - Start/Stop/Restart the engine, Open Zhora (show the window),
  Quit. Closing the window minimizes to tray; only Quit stops Zhora entirely.
  The icon color reflects live status (idle/listening/thinking/speaking/error/etc).
- **Chat window** - multiple named conversations in the sidebar, each with its own
  persistent memory (backed by Agno's session database, so context survives
  restarts). Typed messages and voice commands both land in the same chat history.
- **Settings panel** - switch models (reads what's installed via `ollama list`),
  set the wake word model path, toggle tool confirmation.
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
