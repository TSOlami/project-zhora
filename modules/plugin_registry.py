import importlib.util
import json
import logging
import os

from agno.tools.toolkit import Toolkit

from config import DATA_DIR, PROJECT_ROOT

logger = logging.getLogger(__name__)

PLUGINS_DIR = os.path.join(PROJECT_ROOT, "plugins")
PLUGINS_CONFIG_PATH = os.path.join(DATA_DIR, "plugins_config.json")


def _load_enabled_ids():
    if not os.path.exists(PLUGINS_CONFIG_PATH):
        return set()
    try:
        with open(PLUGINS_CONFIG_PATH, "r", encoding="utf-8") as f:
            return set(json.load(f).get("enabled", []))
    except (json.JSONDecodeError, OSError):
        return set()


def _save_enabled_ids(enabled_ids):
    with open(PLUGINS_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump({"enabled": sorted(enabled_ids)}, f, indent=2)


def _discover_manifests():
    """[(plugin_id, manifest_dict, plugin_dir), ...] for every plugins/<id>/manifest.json found."""
    if not os.path.isdir(PLUGINS_DIR):
        return []
    found = []
    for entry in sorted(os.listdir(PLUGINS_DIR)):
        plugin_dir = os.path.join(PLUGINS_DIR, entry)
        manifest_path = os.path.join(plugin_dir, "manifest.json")
        if not os.path.isfile(manifest_path):
            continue
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        found.append((entry, manifest, plugin_dir))
    return found


def list_plugins():
    """Every discovered plugin with its enabled state, for the settings UI."""
    enabled_ids = _load_enabled_ids()
    return [
        {
            "id": plugin_id,
            "label": manifest.get("label", plugin_id),
            "description": manifest.get("description", ""),
            "enabled": plugin_id in enabled_ids,
            "always_confirm": True,  # plugins are never exempt from confirmation
            "kind": "plugin",
        }
        for plugin_id, manifest, _ in _discover_manifests()
    ]


def set_plugin_enabled(plugin_id, enabled):
    known_ids = {pid for pid, _, _ in _discover_manifests()}
    if plugin_id not in known_ids:
        raise ValueError(f"Unknown plugin: {plugin_id}")
    enabled_ids = _load_enabled_ids()
    if enabled:
        enabled_ids.add(plugin_id)
    else:
        enabled_ids.discard(plugin_id)
    _save_enabled_ids(enabled_ids)


def _load_plugin_module(plugin_id, plugin_dir, entrypoint):
    module_path = os.path.join(plugin_dir, entrypoint)
    spec = importlib.util.spec_from_file_location(f"zhora_plugin_{plugin_id}", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_enabled_plugin_instances():
    """Instantiate every enabled plugin's toolkit, always confirmation-gated.

    Plugins are full-trust local Python code, not sandboxed - the only
    boundary is that you have to put the file in plugins/ yourself, same as
    installing any other software. Every function a plugin exposes always
    requires explicit approval, regardless of REQUIRE_TOOL_CONFIRMATION.
    """
    enabled_ids = _load_enabled_ids()
    instances = []
    for plugin_id, manifest, plugin_dir in _discover_manifests():
        if plugin_id not in enabled_ids:
            continue
        entrypoint = manifest.get("entrypoint", "plugin.py")
        function_name = manifest.get("function", "get_toolkit")
        try:
            module = _load_plugin_module(plugin_id, plugin_dir, entrypoint)
            result = getattr(module, function_name)()
        except Exception:
            logger.exception("Failed to load plugin '%s'", plugin_id)
            continue

        if isinstance(result, Toolkit):
            result.requires_confirmation_tools = list(result.functions.keys())
            for fn in result.functions.values():
                fn.requires_confirmation = True
            instances.append(result)
        else:
            callables = list(result)
            names = [fn.__name__ for fn in callables]
            instances.append(Toolkit(name=plugin_id, tools=callables, requires_confirmation_tools=names))
    return instances
