import threading

import webview

from desktop.app import build_window
from desktop.single_instance import notify_existing_instance, start_focus_listener
from desktop.tray import ZhoraTray
from modules.engine import engine


def main():
    if notify_existing_instance():
        print("Zhora is already running - showing its window instead of starting a new instance.")
        return

    window = build_window()

    def on_closing():
        # Closing the window minimizes to tray instead of quitting -
        # only the tray's Quit action stops Zhora entirely.
        window.hide()
        return False

    window.events.closing += on_closing

    tray = ZhoraTray(on_open=window.show, on_quit=lambda: window.destroy())
    threading.Thread(target=tray.run, daemon=True).start()
    start_focus_listener(on_focus_requested=window.show)

    engine.start()
    webview.start()


if __name__ == "__main__":
    main()
