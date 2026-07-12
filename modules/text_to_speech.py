import logging
import queue
import threading

import pyttsx3

from config import get_voice_id, get_voice_rate, get_voice_volume

logger = logging.getLogger(__name__)

# Generous upper bound on a single job (mainly speak_text()'s _speak()) - a
# well-behaved call finishes quickly after being superseded/interrupted, or
# naturally once the utterance ends. This exists purely as a safety net for
# the rare case where SAPI's engine.stop() races with the utterance's own
# natural completion and runAndWait() never returns (observed in practice:
# clicking a second message's speak button while an earlier one is still
# playing can occasionally wedge it) - set well above the longest plausible
# uninterrupted response read aloud, so real speech is never cut short.
_JOB_TIMEOUT_SECONDS = 90

# pyttsx3's SAPI5 engine is a COM object whose events (including the
# "finished speaking" one that runAndWait() blocks on) are only ever
# delivered back to the specific OS thread that created the engine (COM
# apartment affinity) - creating it on one thread and then driving it
# (say()/runAndWait()) from another, even a second later, silently breaks
# event delivery: runAndWait() never returns, because the completion event
# has nowhere to land. (Confirmed directly: driving a cross-thread-created
# engine gets the *first* event and then nothing - not even a delayed one.)
# The previous design created the engine lazily on whichever ad-hoc per-call
# thread got there first, then reused it from later ad-hoc threads, hitting
# exactly this. A later design fixed the "which thread creates it" half by
# using one permanent thread for that - but then still ran each job on a
# *fresh, throwaway* inner thread, which broke the exact same affinity one
# level down: clicking a second "speak" button while an earlier one was
# still playing would supersede and stop the first (audibly), but the
# second would then never actually play, because the first job's
# runAndWait() - now driven from a throwaway thread instead of the engine's
# creating thread - never returned to free up the worker for the next job.
#
# The fix: the engine must be created *and* driven for its entire life by
# the same single, permanent thread. That thread (_driver) does nothing but
# create the engine once and then run jobs handed to it one at a time,
# forever. A second, outer thread (_worker) exists purely to enforce the
# wedge timeout below without itself ever touching the engine: if a job
# doesn't finish in time, _worker gives up waiting and abandons both the
# driver thread and the engine (rather than trying to interrupt a COM call
# stuck on another thread), and the next speak_text() call spins up a fresh
# pair from scratch.
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

    # Daemon, permanent for this engine generation: created once here and
    # never replaced except by abandoning it wholesale below.
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
            return  # abandons the stuck driver thread/engine; _ensure_worker() spins up a fresh pair next call


def _ensure_worker():
    if _worker_started.is_set():
        return
    with _worker_start_lock:
        # Re-check inside the lock, and wait for the worker to actually
        # finish starting *before* releasing it - otherwise a second thread
        # blocked on this lock would still see _worker_started as False the
        # moment it gets in, since setting that flag happens asynchronously
        # inside the spawned thread, and would spawn a redundant second
        # worker (which loses the CoInitialize race and crashes).
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
    """The engine's own current voice/rate/volume - read fresh rather than
    guessed, since the actual default depends on what's installed on this
    Windows install. Used to seed the Settings UI's sliders before any
    override has been chosen.
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
