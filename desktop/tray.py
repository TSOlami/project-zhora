import threading

import pystray
from PIL import Image, ImageDraw

from modules.engine import engine
from modules.shared_state import engine_state

_STATUS_COLORS = {
    "idle": (90, 200, 130),
    "listening_for_wake_word": (90, 160, 230),
    "listening_for_command": (60, 130, 230),
    "thinking": (230, 180, 60),
    "speaking": (150, 100, 230),
    "awaiting_confirmation": (230, 90, 90),
    "voice_unavailable": (160, 160, 160),
    "error": (220, 50, 50),
    "stopped": (120, 120, 120),
}


def _make_icon_image(color):
    size = 64
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((4, 4, size - 4, size - 4), fill=color)
    draw.text((20, 16), "Z", fill=(255, 255, 255))
    return image


class ZhoraTray:
    def __init__(self, on_open, on_quit):
        self._on_open = on_open
        self._on_quit = on_quit
        self.icon = pystray.Icon(
            "zhora",
            _make_icon_image(_STATUS_COLORS["stopped"]),
            "Zhora - stopped",
            menu=pystray.Menu(
                pystray.MenuItem("Open Zhora", self._open),
                pystray.MenuItem("Start", self._start),
                pystray.MenuItem("Stop", self._stop),
                pystray.MenuItem("Restart", self._restart),
                pystray.MenuItem("Quit", self._quit),
            ),
        )

    def _open(self, icon=None, item=None):
        self._on_open()

    def _start(self, icon=None, item=None):
        engine.start()

    def _stop(self, icon=None, item=None):
        engine.stop()

    def _restart(self, icon=None, item=None):
        engine.restart()

    def _quit(self, icon=None, item=None):
        engine.stop()
        self.icon.stop()
        self._on_quit()

    def _watch_status(self):
        while True:
            event = engine_state.status_queue.get()
            status = event["status"]
            color = _STATUS_COLORS.get(status, (128, 128, 128))
            self.icon.icon = _make_icon_image(color)
            self.icon.title = f"Zhora - {status.replace('_', ' ')}"

    def run(self):
        threading.Thread(target=self._watch_status, daemon=True).start()
        self.icon.run()
