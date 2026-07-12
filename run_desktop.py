import sys
import threading

import webview

import config
from desktop.app import build_window
from desktop.single_instance import acquire_lock_or_notify_existing, serve_focus_requests
from desktop.tray import ZhoraTray
from modules.engine import engine
from modules.shared_state import engine_state


def main():
    # Claimed first, before any of the slow startup work below (WebView2
    # init alone takes seconds) - otherwise two near-simultaneous launches
    # can both pass this check before either one binds the lock.
    lock_sock = acquire_lock_or_notify_existing()
    if lock_sock is None:
        print("Zhora is already running - showing its window instead of starting a new instance.")
        return

    # Passed by the Startup-folder autostart shortcut (see desktop/shortcut.py
    # set_start_on_boot) - signing in shouldn't pop a chat window open, it
    # should just start listening in the tray like it does when minimized.
    start_hidden = "--background" in sys.argv
    window, api = build_window(hidden=start_hidden)
    engine_state.set_window_visible(not start_hidden)

    def show_window():
        engine_state.set_window_visible(True)
        window.show()

    def on_closing():
        # What the window's X button does is itself a setting (Settings ->
        # "When closing the window"), read fresh here since it can change at
        # runtime: always minimize to tray, always quit, or ask (default).
        behavior = config.get_close_behavior()
        if behavior == "quit":
            # Deliberately not tray.quit() here - that also calls
            # window.destroy(), and destroying a window from inside its own
            # closing-event handler is asking for trouble. Returning True
            # lets pywebview's native close finish the job instead; we just
            # need to stop the engine/tray icon first.
            engine.stop()
            tray.icon.stop()
            return True

        if behavior == "tray":
            engine_state.set_window_visible(False)
            window.hide()
            return False
        # "ask": hand off to the in-page dialog (app.js showCloseConfirm) -
        # its buttons call Api.resolve_close_choice, which does the actual
        # hide-or-quit and persists the choice if "remember" was checked.
        # Cancel this native close for now; the modal decides what happens.
        window.evaluate_js("window.showCloseConfirm()")
        return False

    window.events.closing += on_closing

    tray = ZhoraTray(on_open=show_window, on_quit=lambda: window.destroy())
    api.set_quit_callback(tray.quit)
    threading.Thread(target=tray.run, daemon=True).start()
    serve_focus_requests(lock_sock, on_focus_requested=show_window)

    engine.start()
    webview.start()


if __name__ == "__main__":
    main()
