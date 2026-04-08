"""SQLite persistence layer for Arcade OS conversations and personas."""
import aiosqlite
import uuid
import time
import asyncio
from pathlib import Path

DB_PATH = Path.home() / ".nano_claude" / "arcade_os.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS personas (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL UNIQUE,
    role          TEXT NOT NULL,
    avatar        TEXT DEFAULT '🤖',
    description   TEXT DEFAULT '',
    system_prompt TEXT NOT NULL,
    model         TEXT,
    voice_id      TEXT,
    color         TEXT DEFAULT '#00c896',
    is_active     INTEGER DEFAULT 1,
    created_at    TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at    TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS conversations (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL DEFAULT 'New Chat',
    persona_id  INTEGER,
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL,
    FOREIGN KEY (persona_id) REFERENCES personas(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id              TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    role            TEXT NOT NULL,       -- user | assistant | tool | system
    content         TEXT NOT NULL DEFAULT '',
    created_at      REAL NOT NULL,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id, created_at);
"""

# ── Singleton connection with lock ─────────────────────────────────────────
_db: aiosqlite.Connection | None = None
_db_lock = asyncio.Lock()
_seeded = False  # Track whether we've already seeded this session


async def get_db() -> aiosqlite.Connection:
    """Get or create the singleton database connection."""
    global _db, _seeded
    if _db is not None:
        try:
            # Test if connection is alive
            await _db.execute("SELECT 1")
            return _db
        except Exception:
            _db = None

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    _db = await aiosqlite.connect(str(DB_PATH))
    _db.row_factory = aiosqlite.Row
    await _db.execute("PRAGMA journal_mode=WAL")
    await _db.execute("PRAGMA foreign_keys=ON")
    await _db.executescript(SCHEMA)
    print(f"[DB] Connected to {DB_PATH}")

    # Seed default personas on first connection of this process
    if not _seeded:
        try:
            from personas.seeds import seed_default_personas
            await seed_default_personas(_db)
            _seeded = True
        except Exception as e:
            print(f"[DB] Warning: persona seeding failed — {e}")
            _seeded = True  # Don't retry endlessly

    return _db


async def close_db():
    """Close the singleton connection."""
    global _db
    if _db is not None:
        await _db.close()
        _db = None


# ── Conversations ────────────────────────────────────────────────────────────

async def create_conversation(title: str = "New Chat", persona_id: int | None = None) -> dict:
    async with _db_lock:
        db = await get_db()
        conv_id = uuid.uuid4().hex[:16]
        now = time.time()
        await db.execute(
            "INSERT INTO conversations (id, title, persona_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (conv_id, title, persona_id, now, now),
        )
        await db.commit()
        return {"id": conv_id, "title": title, "persona_id": persona_id, "created_at": now, "updated_at": now}


async def list_conversations(limit: int = 50) -> list[dict]:
    async with _db_lock:
        db = await get_db()
        cursor = await db.execute(
            "SELECT id, title, persona_id, created_at, updated_at FROM conversations ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_conversation(conv_id: str) -> dict | None:
    async with _db_lock:
        db = await get_db()
        cursor = await db.execute(
            "SELECT id, title, persona_id, created_at, updated_at FROM conversations WHERE id = ?",
            (conv_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def delete_conversation(conv_id: str) -> bool:
    async with _db_lock:
        db = await get_db()
        await db.execute("DELETE FROM messages WHERE conversation_id = ?", (conv_id,))
        cursor = await db.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
        await db.commit()
        return cursor.rowcount > 0


async def update_conversation_title(conv_id: str, title: str):
    async with _db_lock:
        db = await get_db()
        await db.execute(
            "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
            (title, time.time(), conv_id),
        )
        await db.commit()


async def update_conversation_persona(conv_id: str, persona_id: int | None):
    """Bind or unbind a persona to a conversation."""
    async with _db_lock:
        db = await get_db()
        await db.execute(
            "UPDATE conversations SET persona_id = ?, updated_at = ? WHERE id = ?",
            (persona_id, time.time(), conv_id),
        )
        await db.commit()


async def touch_conversation(conv_id: str):
    async with _db_lock:
        db = await get_db()
        await db.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (time.time(), conv_id),
        )
        await db.commit()


# ── Messages ───────────────────────────────────────────────────────────────

async def add_message(conv_id: str, role: str, content: str) -> dict:
    async with _db_lock:
        db = await get_db()
        msg_id = uuid.uuid4().hex[:16]
        now = time.time()
        await db.execute(
            "INSERT INTO messages (id, conversation_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
            (msg_id, conv_id, role, content, now),
        )
        await db.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (now, conv_id),
        )
        await db.commit()
        return {"id": msg_id, "role": role, "content": content, "created_at": now}


async def get_messages(conv_id: str) -> list[dict]:
    async with _db_lock:
        db = await get_db()
        cursor = await db.execute(
            "SELECT id, role, content, created_at FROM messages WHERE conversation_id = ? ORDER BY created_at",
            (conv_id,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


# ── Personas ───────────────────────────────────────────────────────────────

async def create_persona(
    name: str,
    role: str,
    system_prompt: str,
    avatar: str = "🤖",
    description: str = "",
    model: str | None = None,
    voice_id: str | None = None,
    color: str = "#00c896",
) -> dict:
    """Create a new persona. Returns the full persona dict with auto-generated id."""
    async with _db_lock:
        db = await get_db()
        cursor = await db.execute(
            """INSERT INTO personas (name, role, avatar, description, system_prompt, model, voice_id, color)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (name, role, avatar, description, system_prompt, model, voice_id, color),
        )
        await db.commit()
        persona_id = cursor.lastrowid
        return await _fetch_persona(db, persona_id)


async def list_personas(active_only: bool = True) -> list[dict]:
    """List all personas, optionally filtering to active-only."""
    async with _db_lock:
        db = await get_db()
        if active_only:
            cursor = await db.execute(
                "SELECT * FROM personas WHERE is_active = 1 ORDER BY id"
            )
        else:
            cursor = await db.execute("SELECT * FROM personas ORDER BY id")
        rows = await cursor.fetchall()
        return [_persona_row_to_dict(r) for r in rows]


async def get_persona(persona_id: int) -> dict | None:
    """Get a single persona by ID."""
    async with _db_lock:
        db = await get_db()
        return await _fetch_persona(db, persona_id)


async def update_persona(persona_id: int, **fields) -> bool:
    """Update a persona's fields. Only non-None kwargs are applied.

    Returns True if the persona was found and updated.
    """
    if not fields:
        return False

    # Filter out None values — only update explicitly provided fields
    updates = {k: v for k, v in fields.items() if v is not None}
    if not updates:
        return False

    # Always update the timestamp
    updates["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [persona_id]

    async with _db_lock:
        db = await get_db()
        cursor = await db.execute(
            f"UPDATE personas SET {set_clause} WHERE id = ?",
            values,
        )
        await db.commit()
        return cursor.rowcount > 0


async def delete_persona(persona_id: int) -> bool:
    """Delete a persona by ID. Returns True if a row was deleted.

    Conversations referencing this persona will have persona_id set to NULL
    (via ON DELETE SET NULL foreign key constraint).
    """
    async with _db_lock:
        db = await get_db()
        cursor = await db.execute("DELETE FROM personas WHERE id = ?", (persona_id,))
        await db.commit()
        return cursor.rowcount > 0


# ── Internal helpers ───────────────────────────────────────────────────────

async def _fetch_persona(db, persona_id: int) -> dict | None:
    """Fetch a single persona row (caller must hold _db_lock)."""
    cursor = await db.execute("SELECT * FROM personas WHERE id = ?", (persona_id,))
    row = await cursor.fetchone()
    return _persona_row_to_dict(row) if row else None


def _persona_row_to_dict(row) -> dict:
    """Convert a persona Row to a clean dict with bool for is_active."""
    d = dict(row)
    d["is_active"] = bool(d.get("is_active", 1))
    return d
