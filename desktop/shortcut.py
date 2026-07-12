import os

import win32com.client

from config import PROJECT_ROOT

# Standard per-user autostart location - anything here launches automatically
# at sign-in, no admin rights or registry editing needed. This is the same
# mechanism Windows' own Task Manager > Startup apps tab reads from (as does
# the HKCU Run registry key some apps use instead; a Startup-folder shortcut
# was chosen here because it's also just a normal file the user can find,
# inspect, or delete themselves without opening regedit).
STARTUP_DIR = os.path.join(
    os.path.expanduser("~"), "AppData", "Roaming", "Microsoft", "Windows", "Start Menu", "Programs", "Startup"
)
_STARTUP_SHORTCUT_PATH = os.path.join(STARTUP_DIR, "Zhora.lnk")


def _launch_target():
    venv_scripts = os.path.join(PROJECT_ROOT, "venv", "Scripts")
    pythonw = os.path.join(venv_scripts, "pythonw.exe")
    target = pythonw if os.path.exists(pythonw) else os.path.join(venv_scripts, "python.exe")
    return target, os.path.join(PROJECT_ROOT, "run_desktop.py")


def _write_shortcut(shortcut_path, arguments, description):
    target, run_script = _launch_target()
    shell = win32com.client.Dispatch("WScript.Shell")
    shortcut = shell.CreateShortCut(shortcut_path)
    shortcut.TargetPath = target
    shortcut.Arguments = arguments.format(run_script=run_script)
    shortcut.WorkingDirectory = PROJECT_ROOT
    shortcut.Description = description
    shortcut.save()
    return shortcut_path


def create_desktop_shortcut():
    """Create a Windows desktop shortcut that launches the Zhora desktop app."""
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    shortcut_path = os.path.join(desktop, "Zhora.lnk")
    return _write_shortcut(shortcut_path, '"{run_script}"', "Zhora - personal voice assistant")


def is_start_on_boot_enabled():
    return os.path.exists(_STARTUP_SHORTCUT_PATH)


def set_start_on_boot(enabled):
    """Adds or removes the Startup-folder shortcut that launches Zhora at sign-in.

    Launches with --background so it starts minimized to the tray rather than
    popping a window open the moment the user logs in - the whole point of
    "start on boot" for a background assistant is that it's just already
    listening when you sit down, not that it demands attention immediately.
    """
    if enabled:
        _write_shortcut(
            _STARTUP_SHORTCUT_PATH, '"{run_script}" --background', "Zhora - personal voice assistant (autostart)"
        )
    elif os.path.exists(_STARTUP_SHORTCUT_PATH):
        os.remove(_STARTUP_SHORTCUT_PATH)
