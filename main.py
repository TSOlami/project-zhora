from modules.trigger_word_detection import listen_for_trigger_word
from modules.google_recog import recognize_speech_from_microphone
# from modules.speech_recognition import listen_for_command
from modules.command_processing import process_command
# from modules.text_to_speech import speak_text
from modules.model_interaction import get_response_from_model

def main():
    print("Starting...")
    while True:
        if listen_for_trigger_word():
            print("Trigger word detected. Listening for command...")
            command = recognize_speech_from_microphone()
            if command:
                print(command)
                processed_command = process_command(command)
                response = get_response_from_model(processed_command)
                print(response)
                #speak_text(response)

if __name__ == "__main__":
    main()
