import logging
import threading

import pystray
from PIL import Image, ImageDraw

from desktop.shortcut import create_desktop_shortcut
from modules.engine import engine
from modules.shared_state import engine_state

logger = logging.getLogger(__name__)

# Mirrors the voice orb in the chat window (see #voice-orb rules in
# style.css) - fully monochrome except the one danger red for error/needs-
# your-attention. "Actively working" is a brighter neutral, not a hue -
# lightness carries the distinction the way it does in the CSS. Not one
# color per state; color only answers "should I look at this."
_NEUTRAL = (107, 109, 116)
_ACTIVE = (232, 232, 234)
_DANGER = (208, 65, 63)
_STATUS_COLORS = {
    "idle": _NEUTRAL,
    "listening_for_wake_word": _NEUTRAL,
    "voice_unavailable": _NEUTRAL,
    "stopped": _NEUTRAL,
    "listening_for_command": _ACTIVE,
    "thinking": _ACTIVE,
    "responding": _ACTIVE,
    "streaming_chunk": _ACTIVE,
    "speaking": _ACTIVE,
    "awaiting_confirmation": _DANGER,
    "error": _DANGER,
}


def _make_icon_image(color):
    size = 64
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((4, 4, size - 4, size - 4), fill=color)
    # Text color has to follow the background's lightness now that _ACTIVE is
    # a bright near-white instead of blue - white-on-white would be
    # unreadable. Perceptual luminance, not a flat midpoint split.
    r, g, b = color[:3]
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    text_color = (20, 21, 23) if luminance > 140 else (255, 255, 255)
    draw.text((20, 16), "Z", fill=text_color)
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
                pystray.MenuItem("Add to Desktop", self._add_to_desktop),
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

    def _add_to_desktop(self, icon=None, item=None):
        try:
            create_desktop_shortcut()
        except Exception:
            logger.exception("Failed to create desktop shortcut")

    def _quit(self, icon=None, item=None):
        # engine.stop() can block for its full join(timeout=5) if the engine
        # thread is stuck in an uninterruptible call (an in-flight LLM
        # response, or - previously - voice recognition; see engine.py). Its
        # own thread is what's driving this tray icon and, on the win32
        # backend, the icon's message loop - blocking here freezes the tray
        # (and can make the whole app look hung) for the entire wait. The
        # engine thread is a daemon, so it's safe to just signal it and move
        # on with teardown instead of waiting for it to actually finish.
        threading.Thread(target=engine.stop, daemon=True).start()
        self.icon.stop()
        self._on_quit()

    def quit(self):
        """Public alias so other entry points (the in-app close dialog's
        "Quit completely" choice) can trigger the exact same teardown
        sequence as the tray's own Quit menu item, instead of duplicating it.
        """
        self._quit()

    def _watch_status(self):
        subscription = engine_state.subscribe()
        while True:
            event = subscription.get()
            status = event["status"]
            if status == "amplitude":
                continue  # high-frequency telemetry, not a real status change
            color = _STATUS_COLORS.get(status, (128, 128, 128))
            self.icon.icon = _make_icon_image(color)
            self.icon.title = f"Zhora - {status.replace('_', ' ')}"

            if status == "awaiting_confirmation" and not engine_state.window_visible:
                # The confirmation modal only exists inside the (currently
                # hidden) chat window, so without this the user has no way
                # to know a tool call is waiting on them - it just silently
                # times out and denies after 20s. A toast is the standard
                # pattern for "app running in the background needs your
                # attention" (this is exactly what e.g. VPN clients and
                # backup tools do for the same kind of background approval).
                detail = event.get("detail") or {}
                function_name = detail.get("function_name", "a tool call")
                self.icon.notify(
                    f'Zhora wants to run "{function_name}". Open Zhora to approve or deny - '
                    f"it's denied automatically if no one answers in time.",
                    "Zhora needs your approval",
                )

    def run(self):
        threading.Thread(target=self._watch_status, daemon=True).start()
        self.icon.run()
