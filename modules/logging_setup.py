import logging
import logging.handlers
import os
import threading

from config import DATA_DIR
from modules.shared_state import engine_state

_configured = False


def setup_logging():
    """Rotating file logger + a threading.excepthook safety net.

    The desktop app is normally launched via pythonw.exe (see
    desktop/shortcut.py's autostart shortcut) which has no console attached,
    so print() output and default thread-exception tracebacks go nowhere.
    Everything gets routed to data/zhora.log instead, and any exception that
    escapes a background thread (e.g. the fire-and-forget TTS thread in
    engine.py) is both logged and published through engine_state so it
    surfaces in the UI as an error bubble instead of failing silently.
    """
    global _configured
    if _configured:
        return
    _configured = True

    log_path = os.path.join(DATA_DIR, "zhora.log")
    handler = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=2_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s [%(threadName)s] %(name)s: %(message)s")
    )

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)

    threading.excepthook = _thread_excepthook


def _thread_excepthook(args):
    logging.getLogger("zhora.thread").error(
        "Unhandled exception in background thread %r",
        args.thread.name,
        exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
    )
    try:
        engine_state.set_status("error", f"{args.thread.name}: {args.exc_value}")
    except Exception:
        pass
