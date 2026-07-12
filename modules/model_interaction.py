import logging
import os
import threading

from agno.agent import Agent, RunContentEvent, RunOutput, ToolCallCompletedEvent
from agno.db.sqlite import SqliteDb
from agno.memory import MemoryManager
from agno.models.ollama import Ollama
from agno.run.base import RunStatus

from config import DATA_DIR, OLLAMA_HOST, OLLAMA_MODEL
from modules.env_file import set_env_value
from modules.tool_confirmation import request_confirmation
from modules.tool_registry import build_enabled_tool_instances

logger = logging.getLogger(__name__)

_db = SqliteDb(db_file=os.path.join(DATA_DIR, "chats.db"))

_state = {"model": OLLAMA_MODEL, "agent": None}

# Zhora is a single-user local assistant (see project vision) - every memory
# belongs to this one fixed user, there's no multi-tenant id to track.
MEMORY_USER_ID = "default"

# Phrases that force a memory-extraction pass regardless of whether the
# model's own agentic judgment (the `update_user_memory` tool it decides to
# call on its own) would have fired - explicit requests must always be
# honored, not left to a small local model's discretion.
_REMEMBER_TRIGGERS = (
    "remember that",
    "remember this",
    "remember i",
    "remember my",
    "don't forget",
    "do not forget",
    "forget that",
    "forget i",
    "forget my",
)

BASE_INSTRUCTIONS = (
    "You are Zhora, the user's personal assistant. Be direct and natural. Only call a tool "
    "when the request genuinely requires real-time information, a calculation, or a "
    "real-world action you cannot already answer correctly - never for greetings, small "
    "talk, opinions, or things you already know. When you don't need a tool, just answer "
    "the user directly - never mention tools, function calls, JSON, or your own reasoning "
    "about whether to use one. The user never sees that reasoning and doesn't want to; "
    "respond as if the tools didn't exist unless you are actually using one."
)

MODE_INSTRUCTIONS = {
    "chat": "Keep responses conversational and to the point.",
    "co_work": (
        "You're collaborating on something substantial with the user - code, a document, a "
        "plan. Longer, structured responses are fine here. Present code or long-form content "
        "as a single clear fenced code block."
    ),
    "code": (
        "Focus on programming tasks. Prioritize correct, working code with brief "
        "explanations. Use fenced code blocks with the right language tag."
    ),
}

# Per-mode Ollama sampling options (passed straight through to /api/chat) -
# system-prompt wording alone is a request a small local model can ignore;
# temperature is an actual sampling parameter, so it's a real behavior
# difference between modes rather than a suggestion. Lower temperature for
# Code narrows sampling toward the single most-likely (usually correct)
# token instead of a more varied/creative one - what you want for working
# code, not for conversation.
MODE_OPTIONS = {
    "chat": {"temperature": 0.7},
    "co_work": {"temperature": 0.5},
    "code": {"temperature": 0.2},
}

CONCISE_INSTRUCTIONS = (
    "This reply will be read aloud by text-to-speech. Respond in 1-2 short, natural spoken "
    "sentences - no lists, no headers, no long explanations. Talk like a person in "
    "conversation, not a report."
)


def get_current_model():
    return _state["model"]


def set_current_model(model_id):
    """Switch models immediately and persist the choice to .env for next launch."""
    _state["model"] = model_id
    _state["agent"] = None
    set_env_value("OLLAMA_MODEL", model_id)


def refresh_tools():
    """Call after toggling a tool in the registry so the next request picks it up."""
    _state["agent"] = None


def _get_agent():
    if _state["agent"] is None:
        model = Ollama(id=_state["model"], host=OLLAMA_HOST)
        _state["agent"] = Agent(
            model=model,
            db=_db,
            add_history_to_context=True,
            tools=build_enabled_tool_instances(),
            markdown=False,
            user_id=MEMORY_USER_ID,
            # Reuses the same local Ollama model for memory extraction (the
            # default OpenAI fallback would otherwise require an API key this
            # project never has) - see agentic memory design notes below.
            memory_manager=MemoryManager(model=model, db=_db),
            enable_agentic_memory=True,
            add_memories_to_context=True,
        )
    return _state["agent"]


def _has_explicit_memory_trigger(text):
    lowered = text.lower()
    return any(trigger in lowered for trigger in _REMEMBER_TRIGGERS)


def force_remember_if_triggered(text):
    """If text explicitly asks to remember/forget something, force a memory
    extraction pass for it, in the background, regardless of whether the
    model's own in-line judgment (the `update_user_memory` tool it can choose
    to call while replying) would have caught it. Backgrounded the same way
    speak_text() is - the memory pass is its own model call, and there's no
    reason to make the user wait on it before seeing their reply.
    """
    if not _has_explicit_memory_trigger(text):
        return
    agent = _get_agent()
    threading.Thread(
        target=agent.memory_manager.update_memory_task,
        kwargs={"task": text, "user_id": MEMORY_USER_ID},
        daemon=True,
    ).start()


def list_memories():
    memories = _db.get_user_memories(user_id=MEMORY_USER_ID) or []
    memories.sort(key=lambda m: m.updated_at or 0, reverse=True)
    return [
        {"id": m.memory_id, "memory": m.memory, "topics": m.topics or [], "updated_at": m.updated_at}
        for m in memories
    ]


def delete_memory(memory_id):
    _db.delete_user_memory(memory_id=memory_id, user_id=MEMORY_USER_ID)


def clear_memories():
    _db.clear_memories()


def _build_instructions(mode, concise):
    parts = [BASE_INSTRUCTIONS, MODE_INSTRUCTIONS.get(mode, MODE_INSTRUCTIONS["chat"])]
    if concise:
        parts.append(CONCISE_INSTRUCTIONS)
    return "\n\n".join(parts)


def stream_response_from_model(command_text, chat_id=None, concise=False, mode="chat"):
    """Generator over the turn as it actually happens, instead of blocking
    until the whole reply is generated. Yields:
      ("started", run_id)                      - as soon as Agno assigns one
      ("tool_call", {"name": ..., "result": ...}) - as each tool call finishes
      ("chunk", text_delta)                    - real token-level deltas from Ollama
      ("done", response_text, tool_calls, run_id) - always the last item

    concise=True is for voice-triggered turns (wake word or push-to-talk) -
    short, spoken-style replies instead of long written answers. mode picks
    the behavior profile ("chat" / "co_work" / "code"), independent of concise.

    Confirmation-gated tools use Agno's native human-in-the-loop flow: a run
    pauses instead of running a gated tool, and this resumes it via
    continue_run() once request_confirmation() decides True/False - the same
    security boundary as before, just streamed instead of blocking.
    """
    try:
        agent = _get_agent()
        agent.instructions = _build_instructions(mode, concise)
        agent.model.options = MODE_OPTIONS.get(mode, MODE_OPTIONS["chat"])
        run_id = None
        final = None
        events = agent.run(command_text, session_id=chat_id, stream=True, stream_events=True, yield_run_output=True)
        while True:
            for item in events:
                if isinstance(item, RunOutput):
                    final = item
                    continue
                if run_id is None and item.run_id:
                    run_id = item.run_id
                    yield "started", run_id
                if isinstance(item, ToolCallCompletedEvent) and item.tool and item.tool.tool_name:
                    yield "tool_call", {"name": item.tool.tool_name, "result": item.tool.result}
                elif isinstance(item, RunContentEvent) and item.content:
                    yield "chunk", item.content

            if final is None or not final.is_paused:
                break
            for tool_execution in final.tools_requiring_confirmation:
                decision = request_confirmation(tool_execution.tool_name, tool_execution.tool_args)
                tool_execution.confirmed = decision == "approve"
            events = agent.continue_run(
                final, updated_tools=final.tools, stream=True, stream_events=True, yield_run_output=True
            )
            final = None

        tool_calls = [
            {"name": t.tool_name, "result": t.result} for t in (final.tools or []) if t.tool_name
        ] if final else []
        yield "done", (final.content if final else ""), tool_calls, (final.run_id if final else run_id)
    except Exception:
        logger.exception("An error occurred while getting response from the model")
        yield "done", "", [], None


def regenerate_last_response(chat_id):
    """Marks the most recent turn in chat_id as regenerated (Agno excludes
    RunStatus.regenerated runs from both history display and model context,
    the same way it already excludes paused/cancelled/error runs) and
    returns the original user text so the caller can resend it as a fresh
    turn. Returns None if there is nothing left to retry.
    """
    agent = _get_agent()
    session = agent.get_session(session_id=chat_id)
    if session is None or not session.runs:
        return None
    excluded = (RunStatus.cancelled, RunStatus.regenerated)
    for run in reversed(session.runs):
        if run.status in excluded:
            continue
        user_text = next(
            (m.get_content() for m in (run.messages or []) if m.role == "user"), None
        )
        run.status = RunStatus.regenerated
        agent.db.upsert_session(session)
        return user_text
    return None


def truncate_from_run(chat_id, run_id):
    """Marks run_id and every run after it as cancelled, so the active
    session continues as if the conversation had ended right before run_id.
    The original runs stay in the database (not deleted) but are excluded
    from history/context exactly like a regenerated run.
    """
    agent = _get_agent()
    session = agent.get_session(session_id=chat_id)
    if session is None:
        return
    truncating = False
    for run in session.runs:
        if run.run_id == run_id:
            truncating = True
        if truncating:
            run.status = RunStatus.cancelled
    agent.db.upsert_session(session)
