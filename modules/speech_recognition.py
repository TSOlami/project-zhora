import pyaudio
import struct
from models.create_model_instance import create_leopard_instance


def listen_for_command():
    leopard = None
    audio = None
    stream = None

    try:
        leopard = create_leopard_instance()
        audio = pyaudio.PyAudio()
        stream = audio.open(
            rate=leopard.sample_rate,
            channels=1,
            format=pyaudio.paInt16,
            input=True,
            frames_per_buffer=leopard.frame_length
        )
        stream.start_stream()

        print("Listening for command...")
        frames = []
        while True:
            pcm = stream.read(leopard.frame_length, exception_on_overflow=False)
            pcm = struct.unpack_from("h" * leopard.frame_length, pcm)
            frames.extend(pcm)

            if len(frames) >= leopard.sample_rate * 5:  # 5 seconds buffer
                result = leopard.process(frames)
                text = result.transcript
                print(f"Recognized: {text}")
                return text
    except Exception as e:
        print(f"An error occurred: {e}")
        return None
    finally:
        if leopard is not None:
            leopard.delete()
        if stream is not None:
            stream.stop_stream()
            stream.close()
        if audio is not None:
            audio.terminate()
        if leopard is not None:
            leopard.delete()
        if stream is not None:
            stream.stop_stream()
            stream.close()
        if audio is not None:
            audio.terminate()