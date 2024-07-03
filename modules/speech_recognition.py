import vosk
import json
import os
from pyaudio import PyAudio, paInt16

def recognize_speech_from_microphone():
    model_path = r"C:\Users\teejay\www\my projects\project-zhora\models\vosk-model-small-en-us-0.15"
    if not os.path.exists(model_path):
        print(f"Model not found at {model_path}")
        return ""
    
    model = vosk.Model(model_path)
    recognizer = vosk.KaldiRecognizer(model, 16000)
    
    mic = PyAudio()
    stream = mic.open(format=paInt16, channels=1, rate=16000, input=True, frames_per_buffer=8192)
    stream.start_stream()

    print("Listening...")
    while True:
        data = stream.read(4096, exception_on_overflow=False)
        if recognizer.AcceptWaveform(data):
            result = json.loads(recognizer.Result())
            print(f"Result: {result}")
            text = result.get('text', '')
            print(f"Recognized: {text}")
            return text
        elif recognizer.PartialResult():
            partial_result = json.loads(recognizer.PartialResult())
            print(f"Partial: {partial_result.get('partial', '')}")
