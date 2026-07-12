"""The contract every speech_to_text backend implements.

A backend is a module under speech_to_text/backends/ exposing:

    def recognize(audio_bytes: bytes, sample_rate: int) -> str | None: ...

New backend = one such module + one line in recognizer.py's
_BACKEND_MODULES.

Optionally, for live partial results (the "as you speak" caption), set
SUPPORTS_STREAMING = True and add:

    def create_stream(sample_rate) -> stream:
        # stream.feed(chunk_bytes) -> str | None   (interim guess)
        # stream.finish() -> str | None            (final transcript)

See backends/vosk_backend.py for a real implementation.
"""
