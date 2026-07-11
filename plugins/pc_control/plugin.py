import os
import subprocess
import time

import pyautogui
from agno.tools.toolkit import Toolkit


class PCControlTools(Toolkit):
    """Mouse/keyboard automation, app launching, shell command execution, and
    filesystem access. Every function here always requires explicit
    confirmation (enforced in plugin_registry.py, not just here) - that
    approval is the safety boundary, not a restriction on what Zhora can do
    once you've approved it.
    """

    def __init__(self, **kwargs):
        tools = [
            self.take_screenshot,
            self.open_application,
            self.move_mouse,
            self.click,
            self.type_text,
            self.press_key,
            self.run_command,
            self.read_file,
            self.write_file,
            self.list_directory,
        ]
        super().__init__(
            name="pc_control",
            tools=tools,
            requires_confirmation_tools=[t.__name__ for t in tools],
            **kwargs,
        )

    def take_screenshot(self) -> str:
        """Take a screenshot of the whole screen and save it. Returns the saved file path."""
        path = os.path.join(os.getcwd(), f"screenshot_{int(time.time())}.png")
        pyautogui.screenshot(path)
        return path

    def open_application(self, path_or_name: str) -> str:
        """Open an application or file by path or by name (e.g. 'notepad', 'calc')."""
        try:
            os.startfile(path_or_name)
            return f"Opened {path_or_name}"
        except OSError as e:
            return f"Failed to open {path_or_name}: {e}"

    def move_mouse(self, x: int, y: int) -> str:
        """Move the mouse cursor to the given screen coordinates."""
        pyautogui.moveTo(x, y, duration=0.2)
        return f"Moved mouse to ({x}, {y})"

    def click(self, x: int = None, y: int = None, button: str = "left") -> str:
        """Click the mouse at the given coordinates (or the current position if x/y are omitted)."""
        pyautogui.click(x=x, y=y, button=button)
        return f"Clicked {button} at ({x}, {y})"

    def type_text(self, text: str) -> str:
        """Type the given text as keyboard input at the current cursor/focus location."""
        pyautogui.write(text, interval=0.02)
        return f"Typed: {text}"

    def press_key(self, key: str) -> str:
        """Press a single keyboard key (e.g. 'enter', 'esc', 'tab')."""
        pyautogui.press(key)
        return f"Pressed key: {key}"

    def run_command(self, command: str, timeout: int = 30) -> str:
        """Run a shell command and return its output. Runs via the system shell,
        so pipes/redirection work. Always confirmed before execution."""
        try:
            result = subprocess.run(
                command, shell=True, capture_output=True, text=True, timeout=timeout
            )
            output = result.stdout
            if result.stderr:
                output += f"\n[stderr]\n{result.stderr}"
            return output.strip() or f"(command exited {result.returncode}, no output)"
        except subprocess.TimeoutExpired:
            return f"Command timed out after {timeout}s"
        except Exception as e:
            return f"Failed to run command: {e}"

    def read_file(self, path: str) -> str:
        """Read a text file from anywhere on disk."""
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
        except OSError as e:
            return f"Failed to read {path}: {e}"

    def write_file(self, path: str, content: str) -> str:
        """Write a text file anywhere on disk, creating parent folders if needed."""
        try:
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return f"Wrote {len(content)} chars to {path}"
        except OSError as e:
            return f"Failed to write {path}: {e}"

    def list_directory(self, path: str = ".") -> str:
        """List the contents of a directory."""
        try:
            return ", ".join(os.listdir(path)) or "(empty)"
        except OSError as e:
            return f"Failed to list {path}: {e}"


def get_toolkit():
    return PCControlTools()
