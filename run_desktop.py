import threading

import webview

from desktop.app import build_window
from desktop.tray import ZhoraTray
from modules.engine import engine


def main():
    window = build_window()

    def on_closing():
        # Closing the window minimizes to tray instead of quitting -
        # only the tray's Quit action stops Zhora entirely.
        window.hide()
        return False

    window.events.closing += on_closing

    tray = ZhoraTray(on_open=window.show, on_quit=lambda: window.destroy())
    threading.Thread(target=tray.run, daemon=True).start()

    engine.start()
    webview.start()


if __name__ == "__main__":
    main()
