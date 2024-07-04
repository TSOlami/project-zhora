from models.create_model_instance import create_porcupine_instance
import pyaudio
import struct


def listen_for_trigger_word():

    porcupine = None
    audio = None
    stream = None

    try:

        porcupine = create_porcupine_instance()
        audio = pyaudio.PyAudio()
        stream = audio.open(
            rate=porcupine.sample_rate,
            channels=1,
            format=pyaudio.paInt16,
            input=True,
            frames_per_buffer=porcupine.frame_length
        )
        stream.start_stream()

        print("Listening for trigger word...")

        while True:
            pcm = stream.read(porcupine.frame_length, exception_on_overflow=False)
            pcm = struct.unpack_from("h" * porcupine.frame_length, pcm)

            keyword_index = porcupine.process(pcm)
            if keyword_index >= 0:
                return True
    
    except Exception as e:
        print(f"An error occurred: {e}")
        return False

    finally:
        if porcupine is not None:
            porcupine.delete()
        if stream is not None:
            stream.stop_stream()
            stream.close()
        if audio is not None:
            audio.terminate()
