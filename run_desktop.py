import sys
import threading

import webview

import config
from desktop.app import build_window
from desktop.single_instance import acquire_lock_or_notify_existing, serve_focus_requests
from desktop.tray import ZhoraTray
from modules.engine import engine
from modules.logging_setup import setup_logging
from modules.shared_state import engine_state


def main():
    # First thing, full stop: the autostart shortcut launches this via
    # pythonw.exe (no console), so print()/tracebacks have nowhere to go
    # unless this is in place before anything else can fail.
    setup_logging()

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

    # window.destroy() (called below by the tray's Quit menu item and by the
    # in-app dialog's "Quit completely" button, via tray.quit()) fires this
    # same closing event a second time before the window actually closes -
    # pywebview's FormClosing handler re-invokes on_closing() regardless of
    # what triggered Close(). Without this guard, that re-entrant call would
    # re-read CLOSE_BEHAVIOR (still "ask" if the user didn't check "remember",
    # or "tray") and cancel the close - re-showing the dialog, or hiding a
    # window whose engine/tray were already torn down a moment earlier,
    # leaving an unrecoverable hidden zombie process.
    quitting = threading.Event()

    def on_closing():
        if quitting.is_set():
            return True

        # What the window's X button does is itself a setting (Settings ->
        # "When closing the window"), read fresh here since it can change at
        # runtime: always minimize to tray, always quit, or ask (default).
        behavior = config.get_close_behavior()
        if behavior == "quit":
            # Deliberately not tray.quit() here - that also calls
            # window.destroy(), and destroying a window from inside its own
            # closing-event handler is asking for trouble. Returning True
            # lets pywebview's native close finish the job instead; we just
            # need to stop the engine/tray icon first. Signaled in the
            # background rather than awaited here - engine.stop() can block
            # for its full join(timeout=5) if the engine thread is stuck in
            # an uninterruptible call (an in-flight LLM response), and this
            # runs on the window's own closing-event thread, so waiting on
            # it here would freeze the window for that whole stretch. The
            # engine thread is a daemon, so it's safe to just signal it.
            quitting.set()
            threading.Thread(target=engine.stop, daemon=True).start()
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
        #
        # evaluate_js() must NOT be called directly here: it blocks on a
        # semaphore that's only released by a WebView2 callback scheduled via
        # TaskScheduler.FromCurrentSynchronizationContext() - which needs
        # this same UI thread's message loop to be pumping to ever fire.
        # Since on_closing() runs synchronously inside FormClosing (on the UI
        # thread), calling evaluate_js() here blocks that thread waiting on a
        # callback only that same blocked thread could deliver - a permanent
        # deadlock, reproduced live: the window goes fully unresponsive
        # (confirmed via SendMessageTimeout/SMTO_ABORTIFHUNG) the instant the
        # native X is clicked with CLOSE_BEHAVIOR=ask. Backgrounding the call
        # lets FormClosing return first, so the UI thread is free to pump the
        # continuation by the time evaluate_js's Invoke reaches it.
        threading.Thread(target=window.evaluate_js, args=("window.showCloseConfirm()",), daemon=True).start()
        return False

    window.events.closing += on_closing

    def destroy_window():
        quitting.set()
        window.destroy()

    tray = ZhoraTray(on_open=show_window, on_quit=destroy_window)
    api.set_quit_callback(tray.quit)
    threading.Thread(target=tray.run, daemon=True).start()
    serve_focus_requests(lock_sock, on_focus_requested=show_window)

    engine.start()
    # debug=True enables the WebView2 devtools (right-click -> Inspect, or F12),
    # including its own page reload - lets frontend (HTML/CSS/JS) edits show up
    # without restarting this whole process. Python-side changes still need a
    # full restart regardless, since modules are only loaded once. pywebview
    # defaults to popping the devtools window open automatically whenever
    # debug=True - turn that off so debug=True only makes devtools reachable
    # (F12 / right-click Inspect), not visible on every launch.
    webview.settings["OPEN_DEVTOOLS_IN_DEBUG"] = False
    webview.start(debug=True)


if __name__ == "__main__":
    main()
