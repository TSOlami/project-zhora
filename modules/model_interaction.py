import os

from agno.agent import Agent, RunContentEvent, RunOutput, ToolCallCompletedEvent
from agno.db.sqlite import SqliteDb
from agno.models.ollama import Ollama
from agno.run.base import RunStatus

from config import DATA_DIR, OLLAMA_HOST, OLLAMA_MODEL
from modules.env_file import set_env_value
from modules.tool_confirmation import request_confirmation
from modules.tool_registry import build_enabled_tool_instances

_db = SqliteDb(db_file=os.path.join(DATA_DIR, "chats.db"))

_state = {"model": OLLAMA_MODEL, "agent": None}

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
        _state["agent"] = Agent(
            model=Ollama(id=_state["model"], host=OLLAMA_HOST),
            db=_db,
            add_history_to_context=True,
            tools=build_enabled_tool_instances(),
            markdown=False,
        )
    return _state["agent"]


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
    except Exception as e:
        print(f"An error occurred while getting response from the model: {e}")
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


def fork_conversation(chat_id):
    """Deep-copies the full chat into a new, independent Agno session and
    returns its session_id. Used to snapshot the pre-edit conversation
    before truncate_from_run() rewrites the active one.
    """
    agent = _get_agent()
    return agent.fork_session(source_session_id=chat_id)


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
