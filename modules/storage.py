import os
import sqlite3
import time
import uuid

from agno.db.base import SessionType
from agno.db.sqlite import SqliteDb

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


def get_messages(chat_id):
    """[{"role": ..., "content": ...}, ...] for display, oldest first."""
    session = _db.get_session(session_id=chat_id, session_type=SessionType.AGENT)
    if session is None:
        return []
    return [{"role": m.role, "content": m.get_content()} for m in session.get_chat_history()]
