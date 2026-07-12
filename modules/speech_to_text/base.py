"""The contract every speech_to_text backend implements.

A backend is just a module under speech_to_text/backends/ exposing one
module-level function:

    def recognize(audio_bytes: bytes, sample_rate: int) -> str | None:
        # raw 16-bit PCM mono audio in, transcribed text out (None if
        # nothing was understood)

Adding a new backend (a different offline engine, a different cloud API)
means adding one such module, then one line to _BACKEND_MODULES in
recognizer.py - nothing else in the app touches backends directly.

A backend can optionally also support live partial results (used for the
"text appears as you speak" caption in the desktop UI) by setting
SUPPORTS_STREAMING = True and adding:

    def create_stream(sample_rate) -> stream:
        # stream.feed(chunk_bytes) -> str | None   (interim best guess so far)
        # stream.finish() -> str | None            (final transcript)

See backends/vosk_backend.py for a real implementation. A backend without
SUPPORTS_STREAMING just gets recognize() called once on the full recording,
same as today - no live caption, but nothing else changes.
"""
