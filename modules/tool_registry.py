import json
import os

from agno.tools.calculator import CalculatorTools
from agno.tools.duckduckgo import DuckDuckGoTools

from config import DATA_DIR

TOOLS_CONFIG_PATH = os.path.join(DATA_DIR, "tools_config.json")

# Known, vetted toolkits only - this is a fixed registry the user picks from,
# not an install-anything marketplace (see plugin_registry.py / mcp_registry.py
# for the extensible sources). `always_confirm` is the confirmation gate itself:
# read-only/harmless toolkits (web search, arithmetic) run without asking,
# while anything that touches the filesystem, other processes, or the machine
# itself is marked always_confirm=True - a non-negotiable safety floor.
# Plugins and MCP servers (arbitrary local/external code) are always gated too,
# regardless of what they declare - see plugin_registry.py / mcp_registry.py.
AVAILABLE_TOOLS = {
    "web_search": {
        "label": "Web Search (DuckDuckGo)",
        "description": "Search the web for current information.",
        "factory": DuckDuckGoTools,
        "always_confirm": False,
    },
    "calculator": {
        "label": "Calculator",
        "description": "Perform arithmetic calculations.",
        "factory": CalculatorTools,
        "always_confirm": False,
    },
}

DEFAULT_ENABLED = {"web_search", "calculator"}

# MCP server tool ids are prefixed so set_tool_enabled can route unambiguously
# without a fragile try-each-registry-until-one-doesn't-raise chain.
MCP_ID_PREFIX = "mcp:"


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
    """Every known tool (built-in + plugins + MCP servers) with its current enabled state, for the settings UI."""
    from modules.mcp_registry import list_mcp_servers
    from modules.plugin_registry import list_plugins

    enabled_ids = _load_enabled_ids()
    tools = [
        {
            "id": tool_id,
            "label": meta["label"],
            "description": meta["description"],
            "enabled": tool_id in enabled_ids,
            "always_confirm": meta["always_confirm"],
            "kind": "built-in",
        }
        for tool_id, meta in AVAILABLE_TOOLS.items()
    ]
    tools.extend(list_plugins())
    tools.extend(
        {
            "id": f"{MCP_ID_PREFIX}{server['id']}",
            "label": server["label"],
            "description": server["command"],
            "enabled": server.get("enabled", False),
            "always_confirm": True,
            "kind": "mcp",
        }
        for server in list_mcp_servers()
    )
    return tools


def set_tool_enabled(tool_id, enabled):
    if tool_id in AVAILABLE_TOOLS:
        enabled_ids = _load_enabled_ids()
        if enabled:
            enabled_ids.add(tool_id)
        else:
            enabled_ids.discard(tool_id)
        _save_enabled_ids(enabled_ids)
        return

    if tool_id.startswith(MCP_ID_PREFIX):
        from modules.mcp_registry import set_mcp_server_enabled

        set_mcp_server_enabled(tool_id[len(MCP_ID_PREFIX) :], enabled)
        return

    from modules.plugin_registry import set_plugin_enabled

    set_plugin_enabled(tool_id, enabled)


def _instantiate_gated(factory, always_confirm):
    """Instantiate a toolkit, forcing confirmation on all its functions only if always_confirm is set."""
    if not always_confirm:
        return factory()
    probe = factory()
    function_names = list(probe.functions.keys())
    return factory(requires_confirmation_tools=function_names)


def build_enabled_tool_instances():
    """Instantiate the currently-enabled built-in tools + plugins + MCP servers, gated appropriately."""
    from modules.mcp_registry import build_enabled_mcp_toolkits
    from modules.plugin_registry import build_enabled_plugin_instances

    enabled_ids = _load_enabled_ids()
    instances = [
        _instantiate_gated(meta["factory"], meta["always_confirm"])
        for tool_id, meta in AVAILABLE_TOOLS.items()
        if tool_id in enabled_ids
    ]
    instances.extend(build_enabled_plugin_instances())
    instances.extend(build_enabled_mcp_toolkits())
    return instances
