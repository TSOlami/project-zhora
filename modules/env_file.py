import os

from config import PROJECT_ROOT

ENV_PATH = os.path.join(PROJECT_ROOT, ".env")


def _read_lines():
    if not os.path.exists(ENV_PATH):
        return []
    with open(ENV_PATH, "r", encoding="utf-8") as f:
        return f.read().splitlines()


def set_env_value(key, value):
    """Update or insert KEY=value in .env, preserving other lines, and apply it to this process."""
    lines = _read_lines()
    prefix = f"{key}="
    for i, line in enumerate(lines):
        if line.startswith(prefix):
            lines[i] = f"{key}={value}"
            break
    else:
        lines.append(f"{key}={value}")

    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    os.environ[key] = value
