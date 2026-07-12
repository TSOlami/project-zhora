import socket
import threading

# Arbitrary fixed local port used as both the single-instance lock (whoever
# binds it first wins) and the channel a later launch uses to ask the
# already-running instance to show its window - the same pattern Docker
# Desktop / Slack use, instead of letting every launch spawn a full new
# process (each with its own engine, wake-word listener, and Ollama
# connection - see project memory on the 4-duplicate-process incident).
_HOST = "127.0.0.1"
_PORT = 47821
_PING = b"ZHORA_PING"
_ACK = b"ZHORA_ACK"


def notify_existing_instance():
    """True if a running Zhora instance answered and was asked to show its
    window - caller should exit instead of starting a second instance.
    """
    try:
        with socket.create_connection((_HOST, _PORT), timeout=1) as client:
            client.sendall(_PING)
            return client.recv(len(_ACK)) == _ACK
    except OSError:
        return False


def start_focus_listener(on_focus_requested):
    """Claims the lock port and shows the window whenever a later launch
    connects. If the port can't be bound (e.g. taken by unrelated software),
    this silently does nothing - single-instance is a convenience, not worth
    blocking startup over.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((_HOST, _PORT))
        sock.listen(5)
    except OSError:
        return

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
