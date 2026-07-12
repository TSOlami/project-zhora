import logging
import queue
import threading

import pyttsx3

from config import get_voice_id, get_voice_rate, get_voice_volume

logger = logging.getLogger(__name__)

# Safety net for a wedged job (SAPI runAndWait() that never returns) rather
# than the expected case - set well above the longest plausible response.
_JOB_TIMEOUT_SECONDS = 90

# SAPI's COM events (including "finished speaking", which runAndWait() blocks
# on) are only ever delivered to the OS thread that created the engine -
# creating it on one thread and driving say()/runAndWait() from another
# silently breaks event delivery, so runAndWait() never returns. _driver is
# therefore the one permanent thread that both creates the engine and runs
# every job on it, for the engine's whole life. _worker is a second, outer
# thread that only enforces the wedge timeout below without itself touching
# the engine - if a job doesn't finish in time, it abandons the driver
# thread and engine wholesale rather than trying to interrupt a stuck COM
# call, and the next speak_text() call spins up a fresh pair.
_jobs = queue.Queue()
_worker_started = threading.Event()
_worker_start_lock = threading.Lock()  # guards the check-then-spawn below
_engine = None  # only ever read/written from _driver's thread


def _worker():
    global _engine
    engine_ready = threading.Event()
    driver_jobs = queue.Queue()

    def _driver():
        global _engine
        _engine = pyttsx3.init()
        engine_ready.set()
        while True:
            job, finished = driver_jobs.get()
            try:
                job()
            finally:
                finished.set()

    threading.Thread(target=_driver, daemon=True).start()
    engine_ready.wait()
    _worker_started.set()
    while True:
        job = _jobs.get()
        finished = threading.Event()
        driver_jobs.put((job, finished))
        if not finished.wait(timeout=_JOB_TIMEOUT_SECONDS):
            logger.error(
                "TTS engine appears wedged (a job didn't finish within %ss) - "
                "rebuilding it so future speech isn't silently dead until restart",
                _JOB_TIMEOUT_SECONDS,
            )
            _worker_started.clear()
            return


def _ensure_worker():
    if _worker_started.is_set():
        return
    with _worker_start_lock:
        # Re-check inside the lock and wait for startup to finish before
        # releasing it - otherwise a second blocked caller could still see
        # _worker_started as False and spawn a redundant second worker.
        if not _worker_started.is_set():
            threading.Thread(target=_worker, daemon=True).start()
            _worker_started.wait()


def _run_on_worker(fn):
    """Runs fn() on the dedicated SAPI worker thread and blocks until it
    finishes, returning its result (or re-raising its exception).
    """
    _ensure_worker()
    result = {}
    done = threading.Event()

    def task():
        try:
            result["value"] = fn()
        except Exception as e:
            result["error"] = e
        finally:
            done.set()

    _jobs.put(task)
    done.wait()
    if "error" in result:
        raise result["error"]
    return result["value"]


def list_voices():
    """[{"id": ..., "name": ...}, ...] for every voice SAPI5 has installed."""
    return _run_on_worker(lambda: [{"id": v.id, "name": v.name} for v in _engine.getProperty("voices")])


def get_engine_defaults():
    """The engine's own current voice/rate/volume, read fresh since the
    actual default depends on what's installed on this Windows install.
    """

    def _read():
        return {
            "voice_id": _engine.getProperty("voice"),
            "rate": _engine.getProperty("rate"),
            "volume": _engine.getProperty("volume"),
        }

    return _run_on_worker(_read)


def _apply_voice_settings(engine, voice_id=None, rate=None, volume=None):
    voice_id = voice_id if voice_id is not None else get_voice_id()
    if voice_id:
        engine.setProperty("voice", voice_id)
    rate = rate if rate is not None else get_voice_rate()
    if rate:
        engine.setProperty("rate", rate)
    volume = volume if volume is not None else get_voice_volume()
    if volume is not None:
        engine.setProperty("volume", volume)


_active_token = None  # identifies the most recent speak_text() call


def speak_text(text, should_abort=None, voice_id=None, rate=None, volume=None):
    """Speaks text on the single shared pyttsx3 engine, on its dedicated
    worker thread.

    A newer call supersedes whatever is currently playing (interrupted via
    engine.stop()) rather than queuing behind it or racing it, so only the
    latest request is ever heard - e.g. rapid repeat clicks on a "read
    aloud" button, or a manual click landing while the auto-speak-after-
    response pass is still talking.

    voice_id/rate/volume override the persisted settings (config.get_voice_*)
    for this call only - used by the Settings panel's "Preview" button to
    audition a choice before saving it.
    """
    if not text:
        return

    global _active_token
    token = object()
    _active_token = token

    def superseded():
        return _active_token is not token or (should_abort is not None and should_abort())

    def _speak():
        if superseded():
            return

        _apply_voice_settings(_engine, voice_id, rate, volume)
        watcher_stop = threading.Event()

        def _watch():
            while not watcher_stop.is_set():
                if superseded():
                    _engine.stop()
                    return
                watcher_stop.wait(0.1)

        threading.Thread(target=_watch, daemon=True).start()
        _engine.say(text)
        _engine.runAndWait()
        watcher_stop.set()

    _run_on_worker(_speak)
