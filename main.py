from modules.speech_recognition import recognize_speech_from_microphone
# from modules.trigger_word_detection import detect_trigger_word
# from modules.command_processing import process_command
# from modules.text_to_speech import speak_text
# from modules.model_interaction import get_response_from_model

def main():
    print("Listening for trigger word...")
    while True:
        text = recognize_speech_from_microphone()
        # if detect_trigger_word(text):
        #     print("Trigger word detected. Listening for command...")
        #     command = recognize_speech_from_microphone()
        #     if command:
        #         processed_command = process_command(command)
        #         response = get_response_from_model(processed_command)
        #         speak_text(response)

if __name__ == "__main__":
    main()
