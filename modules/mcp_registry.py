import asyncio
import json
import logging
import os
import threading

from agno.tools.mcp import MCPTools

from config import DATA_DIR

logger = logging.getLogger(__name__)

MCP_CONFIG_PATH = os.path.join(DATA_DIR, "mcp_servers.json")

_loop = None
_loop_thread = None
_connected_toolkits = {}  # server_id -> connected MCPTools instance, kept alive across calls


def _ensure_loop():
    """A single background thread running its own asyncio loop for the whole
    process lifetime - MCP's stdio connections need to stay open across many
    sync calls, not be torn down after each one (which asyncio.run() would do).
    """
    global _loop, _loop_thread
    if _loop is None:
        _loop = asyncio.new_event_loop()
        _loop_thread = threading.Thread(target=_loop.run_forever, daemon=True)
        _loop_thread.start()
    return _loop


def _run_coro(coro, timeout=30):
    loop = _ensure_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=timeout)


def _load_servers():
    if not os.path.exists(MCP_CONFIG_PATH):
        return []
    try:
        with open(MCP_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f).get("servers", [])
    except (json.JSONDecodeError, OSError):
        return []


def _save_servers(servers):
    with open(MCP_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump({"servers": servers}, f, indent=2)


def list_mcp_servers():
    return _load_servers()


def add_mcp_server(server_id, label, command, env=None):
    """command is a single shell-style string, e.g. 'npx -y @modelcontextprotocol/server-filesystem C:/some/dir'."""
    servers = [s for s in _load_servers() if s["id"] != server_id]
    servers.append({"id": server_id, "label": label, "command": command, "env": env or {}, "enabled": False})
    _save_servers(servers)


def remove_mcp_server(server_id):
    _save_servers([s for s in _load_servers() if s["id"] != server_id])
    toolkit = _connected_toolkits.pop(server_id, None)
    if toolkit is not None:
        try:
            _run_coro(toolkit.close())
        except Exception:
            pass


def set_mcp_server_enabled(server_id, enabled):
    servers = _load_servers()
    for s in servers:
        if s["id"] == server_id:
            s["enabled"] = enabled
    _save_servers(servers)


def build_enabled_mcp_toolkits():
    """Connect to every enabled MCP server and return ready Toolkit instances,
    each forced to always require confirmation - an MCP server is arbitrary
    external code you've configured, same trust model as a local plugin.
    """
    instances = []
    for server in _load_servers():
        if not server.get("enabled"):
            continue
        server_id = server["id"]
        toolkit = _connected_toolkits.get(server_id)
        if toolkit is None:
            # timeout_seconds=10 (agno's default) is too tight for `npx`-spawned
            # servers: npx does a registry/version check over the network before
            # the server process even starts, and MCPTools' own initialize()
            # swallows a timeout there internally (logs, doesn't raise), leaving
            # a "connected" toolkit with zero discovered tools and no visible
            # error. Give it real headroom, and verify below regardless.
            toolkit = MCPTools(command=server["command"], env=server.get("env") or None, timeout_seconds=60)
            try:
                # match _run_coro's own wait-timeout to the toolkit's internal
                # timeout_seconds above - otherwise this outer wait cuts the
                # connection off before the more generous internal one applies.
                _run_coro(toolkit.connect(), timeout=60)
            except Exception:
                logger.exception("Failed to connect MCP server '%s'", server_id)
                continue
            if not toolkit.initialized or not toolkit.functions:
                logger.warning(
                    "MCP server '%s' did not initialize correctly "
                    "(no error raised, but no tools were discovered) - skipping.",
                    server_id,
                )
                try:
                    _run_coro(toolkit.close())
                except Exception:
                    pass
                continue
            _connected_toolkits[server_id] = toolkit

        toolkit.requires_confirmation_tools = list(toolkit.functions.keys())
        for fn in toolkit.functions.values():
            fn.requires_confirmation = True
        instances.append(toolkit)
    return instances
