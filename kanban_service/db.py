"""
SQLite-Datenbankschicht für den Standalone-Kanban-Service.
Ersetzt Neo4j vollständig — kein externer DB-Service nötig.
"""
from __future__ import annotations

import os
import aiosqlite
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

DB_PATH = os.environ.get("DB_PATH", "/data/kanban.db")

VALID_TRANSITIONS: dict[str, list[str]] = {
    "backlog":     ["approved"],
    "approved":    ["in_progress", "backlog"],
    "in_progress": ["review"],
    "review":      ["done", "in_progress"],
    "done":        [],
}

ROLE_LABELS = {
    "ceo":        "CEO",
    "cto":        "CTO",
    "cfo":        "CFO",
    "scientist":  "Scientist",
    "researcher": "Researcher",
    "blockchain": "Blockchain Expert",
    "growth":     "Growth Hacker",
    "legal":      "Legal Lawyer",
    "bizdev":     "Business Developer",
    "sales":      "Sales Manager",
    "human":      "Martin",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def init_db() -> None:
    """Schema anlegen (idempotent)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id           TEXT PRIMARY KEY,
                title        TEXT NOT NULL,
                description  TEXT DEFAULT '',
                status       TEXT DEFAULT 'backlog',
                assigned_to  TEXT DEFAULT '',
                priority     INTEGER DEFAULT 3,
                created_by   TEXT DEFAULT 'human',
                result_summary TEXT DEFAULT '',
                agent_notes  TEXT DEFAULT '',
                feedback     TEXT DEFAULT '',
                session_id   TEXT DEFAULT '',
                created_at   TEXT NOT NULL,
                updated_at   TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS comments (
                id           TEXT PRIMARY KEY,
                task_id      TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                author       TEXT DEFAULT 'human',
                author_role  TEXT DEFAULT 'human',
                content      TEXT NOT NULL,
                comment_type TEXT DEFAULT 'note',
                addressed_to TEXT DEFAULT '',
                created_at   TEXT NOT NULL
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_comments_task ON comments(task_id)")
        await db.commit()


def _row_to_task(row: aiosqlite.Row) -> dict[str, Any]:
    keys = [
        "id", "title", "description", "status", "assigned_to", "priority",
        "created_by", "result_summary", "agent_notes", "feedback",
        "session_id", "created_at", "updated_at",
    ]
    return dict(zip(keys, row))


def _row_to_comment(row: aiosqlite.Row) -> dict[str, Any]:
    keys = ["id", "task_id", "author", "author_role", "content",
            "comment_type", "addressed_to", "created_at"]
    return dict(zip(keys, row))


# ─── Tasks ────────────────────────────────────────────────────────────────────

async def create_task(task: dict[str, Any]) -> dict[str, Any]:
    task_id = str(uuid4())
    now = _now()
    row = (
        task_id,
        task["title"],
        task.get("description", ""),
        task.get("status", "backlog"),
        task.get("assigned_to", ""),
        task.get("priority", 3),
        task.get("created_by", "human"),
        task.get("result_summary", ""),
        task.get("agent_notes", ""),
        task.get("feedback", ""),
        task.get("session_id", ""),
        now, now,
    )
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", row
        )
        await db.commit()
    return {
        "id": task_id, "title": task["title"],
        "description": task.get("description", ""),
        "status": task.get("status", "backlog"),
        "assigned_to": task.get("assigned_to", ""),
        "priority": task.get("priority", 3),
        "created_by": task.get("created_by", "human"),
        "result_summary": task.get("result_summary", ""),
        "agent_notes": task.get("agent_notes", ""),
        "feedback": task.get("feedback", ""),
        "session_id": task.get("session_id", ""),
        "created_at": now, "updated_at": now,
    }


async def list_tasks(
    status: Optional[str] = None,
    assigned_to: Optional[str] = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    where_parts = []
    params: list[Any] = []
    if status:
        where_parts.append("status = ?")
        params.append(status)
    if assigned_to:
        where_parts.append("assigned_to = ?")
        params.append(assigned_to)
    where = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""
    params.append(limit)
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            f"SELECT * FROM tasks {where} ORDER BY priority DESC, created_at DESC LIMIT ?",
            params,
        )
        rows = await cursor.fetchall()
    return [_row_to_task(r) for r in rows]


async def get_task(task_id: str) -> Optional[dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        row = await cursor.fetchone()
    return _row_to_task(row) if row else None


async def update_task(task_id: str, updates: dict[str, Any]) -> Optional[dict[str, Any]]:
    allowed = {
        "title", "description", "status", "assigned_to", "priority",
        "result_summary", "agent_notes", "feedback", "session_id", "created_by",
    }
    safe = {k: v for k, v in updates.items() if k in allowed}
    if not safe:
        return await get_task(task_id)
    set_sql = ", ".join(f"{k} = ?" for k in safe)
    params = list(safe.values()) + [_now(), task_id]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"UPDATE tasks SET {set_sql}, updated_at = ? WHERE id = ?", params
        )
        await db.commit()
    return await get_task(task_id)


async def delete_task(task_id: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        await db.commit()
        return cursor.rowcount > 0


# ─── Comments ─────────────────────────────────────────────────────────────────

async def create_comment(task_id: str, comment: dict[str, Any]) -> Optional[dict[str, Any]]:
    task = await get_task(task_id)
    if task is None:
        return None
    comment_id = str(uuid4())
    now = _now()
    row = (
        comment_id, task_id,
        comment.get("author", "human"),
        comment.get("author_role", "human"),
        comment["content"],
        comment.get("comment_type", "note"),
        comment.get("addressed_to", ""),
        now,
    )
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO comments VALUES (?,?,?,?,?,?,?,?)", row)
        await db.commit()
    return {
        "id": comment_id, "task_id": task_id,
        "author": comment.get("author", "human"),
        "author_role": comment.get("author_role", "human"),
        "content": comment["content"],
        "comment_type": comment.get("comment_type", "note"),
        "addressed_to": comment.get("addressed_to", ""),
        "created_at": now,
    }


async def list_comments(task_id: str) -> list[dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT * FROM comments WHERE task_id = ? ORDER BY created_at ASC",
            (task_id,),
        )
        rows = await cursor.fetchall()
    return [_row_to_comment(r) for r in rows]
