import os

import win32com.client

from config import PROJECT_ROOT


def create_desktop_shortcut():
    """Create a Windows desktop shortcut that launches the Zhora desktop app."""
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    shortcut_path = os.path.join(desktop, "Zhora.lnk")

    venv_scripts = os.path.join(PROJECT_ROOT, "venv", "Scripts")
    pythonw = os.path.join(venv_scripts, "pythonw.exe")
    target = pythonw if os.path.exists(pythonw) else os.path.join(venv_scripts, "python.exe")
    run_script = os.path.join(PROJECT_ROOT, "run_desktop.py")

    shell = win32com.client.Dispatch("WScript.Shell")
    shortcut = shell.CreateShortCut(shortcut_path)
    shortcut.TargetPath = target
    shortcut.Arguments = f'"{run_script}"'
    shortcut.WorkingDirectory = PROJECT_ROOT
    shortcut.Description = "Zhora - personal voice assistant"
    shortcut.save()
    return shortcut_path
