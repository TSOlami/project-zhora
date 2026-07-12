import os
import sqlite3
import time
import uuid

from agno.db.base import SessionType
from agno.db.sqlite import SqliteDb
from agno.run.base import RunStatus

from config import DATA_DIR

DB_PATH = os.path.join(DATA_DIR, "chats.db")

# Same physical file model_interaction.py's Agent uses for message/context
# storage (Agno's own session tables). This module adds one small table of
# its own for chat titles/ordering - not a duplicate of message content,
# which stays exclusively in Agno's session store.
_db = SqliteDb(db_file=DB_PATH)


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS zhora_chats (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            created_at REAL NOT NULL
        )
        """
    )
    try:
        conn.execute("ALTER TABLE zhora_chats ADD COLUMN mode TEXT DEFAULT 'chat'")
    except sqlite3.OperationalError:
        pass  # column already exists from a previous run
    return conn


def create_chat(title="New chat", mode="chat"):
    chat_id = str(uuid.uuid4())
    with _connect() as conn:
        conn.execute(
            "INSERT INTO zhora_chats (id, title, created_at, mode) VALUES (?, ?, ?, ?)",
            (chat_id, title, time.time(), mode),
        )
    return chat_id


def list_chats():
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, title, created_at, mode FROM zhora_chats ORDER BY created_at DESC"
        ).fetchall()
    return [{"id": row[0], "title": row[1], "created_at": row[2], "mode": row[3] or "chat"} for row in rows]


def get_chat(chat_id):
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, title, created_at, mode FROM zhora_chats WHERE id = ?", (chat_id,)
        ).fetchone()
    if row is None:
        return None
    return {"id": row[0], "title": row[1], "created_at": row[2], "mode": row[3] or "chat"}


def register_forked_chat(session_id, title, mode="chat"):
    """Adds a sidebar entry for a session_id that Agno's fork_session() already
    created in its own store - used so an edited-and-resent message's pre-edit
    branch shows up as an openable chat instead of being silently orphaned.
    """
    with _connect() as conn:
        conn.execute(
            "INSERT INTO zhora_chats (id, title, created_at, mode) VALUES (?, ?, ?, ?)",
            (session_id, title, time.time(), mode),
        )


def get_chat_mode(chat_id):
    with _connect() as conn:
        row = conn.execute("SELECT mode FROM zhora_chats WHERE id = ?", (chat_id,)).fetchone()
    return (row[0] if row and row[0] else "chat")


def set_chat_mode(chat_id, mode):
    with _connect() as conn:
        conn.execute("UPDATE zhora_chats SET mode = ? WHERE id = ?", (mode, chat_id))


def rename_chat(chat_id, title):
    with _connect() as conn:
        conn.execute("UPDATE zhora_chats SET title = ? WHERE id = ?", (title, chat_id))


def delete_chat(chat_id):
    with _connect() as conn:
        conn.execute("DELETE FROM zhora_chats WHERE id = ?", (chat_id,))
    try:
        _db.delete_session(session_id=chat_id)
    except Exception:
        pass  # no messages were ever sent in this chat, so no session exists yet


_EXCLUDED_RUN_STATUSES = (RunStatus.paused, RunStatus.cancelled, RunStatus.error, RunStatus.regenerated)


def get_messages(chat_id):
    """[{"role": ..., "content": ..., "run_id": ...}, ...] for display, oldest
    first. run_id lets the UI target a specific turn for edit/retry.

    Built from session.runs directly (rather than session.get_chat_history())
    so each message can carry its run_id, and so tool-call-announcement
    messages (assistant messages with no text content, just a tool call) are
    skipped instead of rendering as an empty bubble.
    """
    session = _db.get_session(session_id=chat_id, session_type=SessionType.AGENT)
    if session is None:
        return []
    out = []
    for run in session.runs:
        if run.parent_run_id is not None or run.status in _EXCLUDED_RUN_STATUSES:
            continue
        for m in run.messages or []:
            if m.role not in ("user", "assistant") or getattr(m, "from_history", False):
                continue
            content = m.get_content()
            if content:
                out.append({"role": m.role, "content": content, "run_id": run.run_id})
    return out
