import os

from agno.agent import Agent
from agno.db.sqlite import SqliteDb
from agno.models.ollama import Ollama

from config import DATA_DIR, OLLAMA_HOST, OLLAMA_MODEL
from modules.env_file import set_env_value
from modules.tool_confirmation import confirm_tool_call
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
            tool_hooks=[confirm_tool_call],
            markdown=False,
        )
    return _state["agent"]


def get_response_from_model(command_text, chat_id=None):
    try:
        agent = _get_agent()
        response = agent.run(command_text, session_id=chat_id)
        return response.content
    except Exception as e:
        print(f"An error occurred while getting response from the model: {e}")
        return ""
