import logging
import threading

from modules.shared_state import engine_state

logger = logging.getLogger(__name__)

CONFIRMATION_TIMEOUT_SECONDS = 20


def _listen_for_voice_confirmation(req):
    from modules.google_recog import recognize_speech_from_microphone

    text = recognize_speech_from_microphone()
    if req.event.is_set() or not text:
        return
    text = text.lower()
    if "yes" in text:
        req.resolve("approve")
    elif "no" in text:
        req.resolve("deny")


def _listen_for_terminal_confirmation(req):
    try:
        answer = input("Allow this tool call? [y/N]: ").strip().lower()
    except (EOFError, OSError):
        answer = ""
    if not req.event.is_set():
        req.resolve("approve" if answer == "y" else "deny")


def request_confirmation(function_name, arguments):
    """Block until a pending tool call is approved or denied.

    Approval can come from a spoken "yes"/"no", a typed y/N in the terminal, or
    (when the desktop UI is open) a button click resolving the same pending
    request via engine_state.resolve_confirmation(). Whichever answers first
    wins. Fails closed: no answer within the timeout, or anything other than
    an explicit approval, denies. This project intentionally runs an
    uncensored model with no other safety net between a voice command and a
    tool executing - callers (model_interaction.py) must not invoke the tool
    unless this returns "approve".
    """
    req = engine_state.begin_confirmation(function_name, arguments)
    logger.info("Confirmation required: tool '%s' with arguments: %s", function_name, arguments)

    print(f"\n[Confirmation required] Run tool '{function_name}' with arguments: {arguments}")
    print("Say 'yes'/'no', click Approve/Deny in the app, or type y/N here.")

    threading.Thread(target=_listen_for_voice_confirmation, args=(req,), daemon=True).start()
    threading.Thread(target=_listen_for_terminal_confirmation, args=(req,), daemon=True).start()

    result = req.wait(timeout=CONFIRMATION_TIMEOUT_SECONDS)
    engine_state.end_confirmation()

    if result != "approve":
        logger.info("Blocked tool call: %s (result=%s)", function_name, result)
        print(f"Blocked tool call: {function_name}")
        return "deny"
    logger.info("Approved tool call: %s", function_name)
    return "approve"
