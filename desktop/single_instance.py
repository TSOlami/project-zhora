import socket
import threading

import win32api
import win32event
import winerror

# The lock itself is a named Windows mutex, not the TCP port below - a
# kernel object is what "first process wins, race-free, auto-released even
# on a crash/force-kill" actually requires. This used to be a fixed local
# port bound as a makeshift mutex ("whoever binds it first wins", the same
# pattern Docker Desktop / Slack use on POSIX), but Windows' bind() doesn't
# give that guarantee the way POSIX does: SO_REUSEADDR lets a second
# process bind the same port while the first still holds it, and the fix
# for that - SO_EXCLUSIVEADDRUSE - swings the other way and can make even
# the *first* bind() fail with WinError 10048 if any socket (including one
# sitting in TIME_WAIT from a previous run) still references that port,
# which was falling through to an intentional fallback ("port unavailable,
# proceed as primary anyway") and producing the exact duplicate-instance
# bug this file exists to prevent. A named mutex has none of that: no port,
# no TIME_WAIT, atomic test-and-set, and the OS releases it the instant the
# owning process exits for any reason.
#
# The TCP port is kept only as a best-effort side channel for the
# non-critical part - asking an already-running instance to bring its
# window to front - where "occasionally doesn't work" is a minor UX miss,
# not a resource leak.
_MUTEX_NAME = "ZhoraSingleInstanceMutex"
_HOST = "127.0.0.1"
_PORT = 47821
_PING = b"ZHORA_PING"
_ACK = b"ZHORA_ACK"

_mutex_handle = None  # module-level so the handle (and the lock it holds) survives for the process's lifetime


def acquire_lock_or_notify_existing():
    """Claims the single-instance lock, or tells whoever already holds it to
    show their window. Must be called before any slow startup work (WebView2
    init alone takes seconds) - creating the mutex is a near-instant syscall,
    so doing this first is what makes the lock race-free between two
    near-simultaneous launches.

    Returns a socket if this process should proceed as the primary instance
    (pass it to serve_focus_requests once the window exists - it may or may
    not actually be bound, see below). Returns None if another instance
    already holds the lock and was asked to show itself - caller should exit
    immediately without building a window, starting the engine, etc.
    """
    global _mutex_handle
    _mutex_handle = win32event.CreateMutex(None, False, _MUTEX_NAME)
    already_running = win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS

    if already_running:
        try:
            with socket.create_connection((_HOST, _PORT), timeout=2) as client:
                client.sendall(_PING)
                client.recv(len(_ACK))
        except OSError:
            pass  # best-effort only - the mutex is the real lock, this is just the focus request
        return None

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((_HOST, _PORT))
        sock.listen(5)
    except OSError:
        # Some unrelated process has that port - the focus-request channel
        # just won't work this run. Doesn't affect the lock itself, which
        # the mutex above already secured.
        sock.close()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # unbound; serve_focus_requests no-ops on it
    return sock


def serve_focus_requests(sock, on_focus_requested):
    """Background thread: any connection on the lock port means a later
    launch happened - bring this instance's window to front instead.
    """
    try:
        sock.getsockname()
    except OSError:
        return  # never actually bound (see the fallback above) - nothing to serve

    def _serve():
        while True:
            try:
                conn, _ = sock.accept()
            except OSError:
                return
            with conn:
                try:
                    conn.recv(len(_PING))
                    conn.sendall(_ACK)
                except OSError:
                    pass
            on_focus_requested()

    threading.Thread(target=_serve, daemon=True).start()
