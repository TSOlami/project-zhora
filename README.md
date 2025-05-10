# Zhora - Voice-Activated AI Assistant

Zhora is a personal AI assistant that listens for a specific wake word, understands your spoken commands, and responds using a powerful AI language model.

## What Zhora Can Do

- Listen for the wake word "Hey Zora" to activate
- Convert your spoken commands to text using Google's speech recognition 
- Process your commands
- Generate intelligent responses using a local AI model
- Display responses (with potential for spoken responses)

## Technologies Used

- **Python**: Main programming language
- **Porcupine**: Wake word detection by Picovoice
- **PyAudio**: Audio input processing
- **SpeechRecognition**: Converting speech to text using Google's service
- **Ollama**: Running local AI models
- **Llama 3**: AI language model (specifically taozhiyuai/llama-3-8b-lexi-uncensored:f16)
- **pyttsx3**: Text-to-speech conversion (currently not active)

## Project Structure

- **main.py**: Main application that ties everything together
- **modules/**: Contains the core functionality
  - **trigger_word_detection.py**: Listens for the wake word
  - **google_recog.py**: Handles speech recognition
  - **command_processing.py**: Processes recognized commands
  - **model_interaction.py**: Interacts with the AI model
  - **text_to_speech.py**: Converts text to speech (currently not implemented)
- **models/**: Contains model-related code
  - **create_model_instance.py**: Creates instances of Porcupine and Leopard

## Required External Services/Software

- Picovoice account (for Porcupine wake word detection)
- Internet connection (for Google Speech Recognition)
- Ollama installed locally (for running the Llama 3 model)

## How It Works

1. The system continuously listens for the wake word "Hey Zora"
2. When detected, it starts recording your command
3. Your spoken command is converted to text using Google's speech recognition
4. The text is processed and sent to the Llama 3 model running on Ollama
5. The AI model generates a response which is displayed (and potentially spoken)

## Setup

1. Clone the repo
2. Create a virtual environment:
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Create a `.env` file with your credentials (if needed)
4. Create `config.py` with your Picovoice access key:
   ```python
   PICOVOICE_ACCESS_KEY = "your-picovoice-key-here"
   ```
5. Install required packages:
   ```
   pip install -r requirements.txt
   ```
   
   Note: You may need to install additional packages not listed in requirements.txt:
   ```
   pip install pyaudio speech_recognition pvleopard
   ```

6. Setup the Porcupine model:
   - Create a Picovoice account at https://console.picovoice.ai/
   - Create a wake word model for "Hey Zora" in your Picovoice dashboard
   - Download your custom wake word model
   - Unzip and copy the model (.ppn file) into the models/porcupine directory
   - Update the file path in models/create_model_instance.py with the correct path to your downloaded model

7. Install Ollama:
   - Follow instructions at https://ollama.ai/ to install Ollama
   - Pull the Llama 3 model:
     ```
     ollama pull taozhiyuai/llama-3-8b-lexi-uncensored:f16
     ```

8. Run the application:
   ```
   python main.py
   ```

9. Say "Hey Zora" followed by your command

## Future Development Plans

- Enhanced command processing with context awareness
- Integration with more services and APIs
- Improved voice response capabilities
- Local offline speech recognition
- Persistent memory of conversations
- Custom capabilities and skill development

## Related Projects

This project is part of a larger ecosystem that includes:
- **AIOS**: A comprehensive AI operating system framework
- **Phidata**: A framework for building AI assistants with knowledge management

## Contributing

Contributions, ideas, and feedback are welcome! Feel free to open issues or submit pull requests.
