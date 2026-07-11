import os

from agno.agent import Agent
from agno.db.sqlite import SqliteDb
from agno.models.ollama import Ollama

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
    "talk, opinions, or things you already know."
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


def _resolve_pending_confirmations(agent, response):
    """Agno's native human-in-the-loop flow: a run pauses instead of running a
    gated tool. Nothing here calls the tool directly - Agno only executes it
    once every pending ToolExecution.confirmed is True and we resume via
    continue_run(). This is the actual security boundary; request_confirmation
    only decides confirmed True/False.
    """
    while response.is_paused:
        for tool_execution in response.tools_requiring_confirmation:
            decision = request_confirmation(tool_execution.tool_name, tool_execution.tool_args)
            tool_execution.confirmed = decision == "approve"
        response = agent.continue_run(response, updated_tools=response.tools)
    return response


def get_response_from_model(command_text, chat_id=None, concise=False, mode="chat"):
    """Returns (response_text, tool_calls) where tool_calls is
    [{"name": ..., "result": ...}, ...] for whatever tools actually ran.

    concise=True is for voice-triggered turns (wake word or push-to-talk) -
    short, spoken-style replies instead of long written answers. mode picks
    the behavior profile ("chat" / "co_work" / "code"), independent of concise.
    """
    try:
        agent = _get_agent()
        agent.instructions = _build_instructions(mode, concise)
        response = agent.run(command_text, session_id=chat_id)
        response = _resolve_pending_confirmations(agent, response)
        tool_calls = [
            {"name": t.tool_name, "result": t.result} for t in (response.tools or []) if t.tool_name
        ]
        return response.content, tool_calls
    except Exception as e:
        print(f"An error occurred while getting response from the model: {e}")
        return "", []
