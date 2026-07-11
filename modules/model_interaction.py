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


def get_response_from_model(command_text, chat_id=None):
    """Returns (response_text, tool_calls) where tool_calls is
    [{"name": ..., "result": ...}, ...] for whatever tools actually ran,
    so callers can show "used tool X" activity in a chat transcript.
    """
    try:
        agent = _get_agent()
        response = agent.run(command_text, session_id=chat_id)
        response = _resolve_pending_confirmations(agent, response)
        tool_calls = [
            {"name": t.tool_name, "result": t.result} for t in (response.tools or []) if t.tool_name
        ]
        return response.content, tool_calls
    except Exception as e:
        print(f"An error occurred while getting response from the model: {e}")
        return "", []
