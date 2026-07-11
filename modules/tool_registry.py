import json
import os

from agno.tools.calculator import CalculatorTools
from agno.tools.duckduckgo import DuckDuckGoTools

from config import DATA_DIR

TOOLS_CONFIG_PATH = os.path.join(DATA_DIR, "tools_config.json")

# Known, vetted toolkits only - this is a fixed registry the user picks from,
# not an install-anything marketplace. See README's safety note on why that
# matters for a project that runs an unrestricted model with no other gate.
AVAILABLE_TOOLS = {
    "web_search": {
        "label": "Web Search (DuckDuckGo)",
        "description": "Search the web for current information.",
        "factory": DuckDuckGoTools,
    },
    "calculator": {
        "label": "Calculator",
        "description": "Perform arithmetic calculations.",
        "factory": CalculatorTools,
    },
}

DEFAULT_ENABLED = {"web_search", "calculator"}


def _load_enabled_ids():
    if not os.path.exists(TOOLS_CONFIG_PATH):
        return set(DEFAULT_ENABLED)
    try:
        with open(TOOLS_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {tool_id for tool_id in data.get("enabled", []) if tool_id in AVAILABLE_TOOLS}
    except (json.JSONDecodeError, OSError):
        return set(DEFAULT_ENABLED)


def _save_enabled_ids(enabled_ids):
    with open(TOOLS_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump({"enabled": sorted(enabled_ids)}, f, indent=2)


def list_tools():
    """Every known tool with its current enabled state, for the settings UI."""
    enabled_ids = _load_enabled_ids()
    return [
        {
            "id": tool_id,
            "label": meta["label"],
            "description": meta["description"],
            "enabled": tool_id in enabled_ids,
        }
        for tool_id, meta in AVAILABLE_TOOLS.items()
    ]


def set_tool_enabled(tool_id, enabled):
    if tool_id not in AVAILABLE_TOOLS:
        raise ValueError(f"Unknown tool: {tool_id}")
    enabled_ids = _load_enabled_ids()
    if enabled:
        enabled_ids.add(tool_id)
    else:
        enabled_ids.discard(tool_id)
    _save_enabled_ids(enabled_ids)


def build_enabled_tool_instances():
    """Instantiate the currently-enabled tools, for wiring into an Agent."""
    enabled_ids = _load_enabled_ids()
    return [meta["factory"]() for tool_id, meta in AVAILABLE_TOOLS.items() if tool_id in enabled_ids]
