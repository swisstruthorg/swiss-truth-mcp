"""
Kanban board queries — KanbanTask + TaskComment CRUD operations.
Pattern identical to db/queries.py: async, AsyncSession, plain dicts.

Status-Übergänge:
  backlog → approved → in_progress → review → done
                              ↑           |
                              └───────────┘ (feedback-Loop)
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from neo4j import AsyncSession


VALID_TRANSITIONS: dict[str, list[str]] = {
    "backlog":     ["approved"],
    "approved":    ["in_progress", "backlog"],
    "in_progress": ["review"],
    "review":      ["done", "in_progress"],
    "done":        [],
}

ALL_STATUSES = list(VALID_TRANSITIONS.keys())

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


# ─── KanbanTask ───────────────────────────────────────────────────────────────

async def create_task(session: AsyncSession, task: dict[str, Any]) -> dict[str, Any]:
    """Insert a new KanbanTask node, return the created task dict."""
    task_id = str(uuid4())
    now = _now()
    params = {
        "id": task_id,
        "title": task["title"],
        "description": task.get("description", ""),
        "status": task.get("status", "backlog"),
        "assigned_to": task.get("assigned_to", ""),
        "priority": task.get("priority", 3),
        "created_by": task.get("created_by", "human"),
        "result_summary": task.get("result_summary", ""),
        "agent_notes": task.get("agent_notes", ""),
        "feedback": task.get("feedback", ""),
        "session_id": task.get("session_id", ""),
        "created_at": now,
        "updated_at": now,
    }
    await session.run(
        """
        CREATE (k:KanbanTask {
            id: $id,
            title: $title,
            description: $description,
            status: $status,
            assigned_to: $assigned_to,
            priority: $priority,
            created_by: $created_by,
            result_summary: $result_summary,
            agent_notes: $agent_notes,
            feedback: $feedback,
            session_id: $session_id,
            created_at: $created_at,
            updated_at: $updated_at
        })
        """,
        params,
    )
    return {**params}


async def list_tasks(
    session: AsyncSession,
    status: Optional[str] = None,
    assigned_to: Optional[str] = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Return KanbanTask nodes, optionally filtered by status or agent."""
    filters = []
    params: dict[str, Any] = {"limit": limit}
    if status:
        filters.append("k.status = $status")
        params["status"] = status
    if assigned_to:
        filters.append("k.assigned_to = $assigned_to")
        params["assigned_to"] = assigned_to

    where = ("WHERE " + " AND ".join(filters)) if filters else ""
    cypher = f"""
    MATCH (k:KanbanTask)
    {where}
    RETURN k {{
        .id, .title, .description, .status, .assigned_to,
        .priority, .created_by, .result_summary, .agent_notes,
        .feedback, .session_id, .created_at, .updated_at
    }} AS task
    ORDER BY k.priority DESC, k.created_at DESC
    LIMIT $limit
    """
    result = await session.run(cypher, params)
    rows = await result.data()
    return [row["task"] for row in rows]


async def get_task(session: AsyncSession, task_id: str) -> Optional[dict[str, Any]]:
    """Retrieve a single KanbanTask by id."""
    result = await session.run(
        """
        MATCH (k:KanbanTask {id: $id})
        RETURN k {
            .id, .title, .description, .status, .assigned_to,
            .priority, .created_by, .result_summary, .agent_notes,
            .feedback, .session_id, .created_at, .updated_at
        } AS task
        """,
        {"id": task_id},
    )
    rows = await result.data()
    return rows[0]["task"] if rows else None


async def update_task(
    session: AsyncSession, task_id: str, updates: dict[str, Any]
) -> Optional[dict[str, Any]]:
    """Update specific fields on a KanbanTask. Returns updated task or None."""
    allowed = {
        "title", "description", "status", "assigned_to", "priority",
        "result_summary", "agent_notes", "feedback", "session_id", "created_by",
    }
    safe = {k: v for k, v in updates.items() if k in allowed}
    if not safe:
        return await get_task(session, task_id)

    set_clauses = ", ".join(f"k.{k} = ${k}" for k in safe)
    params = {"id": task_id, "updated_at": _now(), **safe}
    result = await session.run(
        f"""
        MATCH (k:KanbanTask {{id: $id}})
        SET {set_clauses}, k.updated_at = $updated_at
        RETURN k {{
            .id, .title, .description, .status, .assigned_to,
            .priority, .created_by, .result_summary, .agent_notes,
            .feedback, .session_id, .created_at, .updated_at
        }} AS task
        """,
        params,
    )
    rows = await result.data()
    return rows[0]["task"] if rows else None


async def delete_task(session: AsyncSession, task_id: str) -> bool:
    """Delete a KanbanTask and all its comments. Returns True if deleted."""
    result = await session.run(
        """
        MATCH (k:KanbanTask {id: $id})
        OPTIONAL MATCH (k)-[:HAS_COMMENT]->(c:TaskComment)
        DETACH DELETE k, c
        RETURN count(k) AS deleted
        """,
        {"id": task_id},
    )
    rows = await result.data()
    return bool(rows and rows[0]["deleted"])


# ─── TaskComment ──────────────────────────────────────────────────────────────

async def create_comment(
    session: AsyncSession, task_id: str, comment: dict[str, Any]
) -> Optional[dict[str, Any]]:
    """
    Attach a TaskComment node to a KanbanTask.
    comment_type: question | answer | feedback | note
    Returns the created comment or None if task not found.
    """
    comment_id = str(uuid4())
    now = _now()
    params = {
        "task_id": task_id,
        "id": comment_id,
        "author": comment.get("author", "human"),
        "author_role": comment.get("author_role", "human"),
        "content": comment["content"],
        "comment_type": comment.get("comment_type", "note"),
        "addressed_to": comment.get("addressed_to", ""),
        "created_at": now,
    }
    result = await session.run(
        """
        MATCH (k:KanbanTask {id: $task_id})
        CREATE (c:TaskComment {
            id: $id,
            author: $author,
            author_role: $author_role,
            content: $content,
            comment_type: $comment_type,
            addressed_to: $addressed_to,
            created_at: $created_at
        })
        CREATE (k)-[:HAS_COMMENT]->(c)
        RETURN c {
            .id, .author, .author_role, .content,
            .comment_type, .addressed_to, .created_at
        } AS comment
        """,
        params,
    )
    rows = await result.data()
    if not rows:
        return None
    return rows[0]["comment"]


async def list_comments(
    session: AsyncSession, task_id: str
) -> list[dict[str, Any]]:
    """Return all TaskComment nodes for a given task, ordered by created_at ASC."""
    result = await session.run(
        """
        MATCH (k:KanbanTask {id: $task_id})-[:HAS_COMMENT]->(c:TaskComment)
        RETURN c {
            .id, .author, .author_role, .content,
            .comment_type, .addressed_to, .created_at
        } AS comment
        ORDER BY c.created_at ASC
        """,
        {"task_id": task_id},
    )
    rows = await result.data()
    return [row["comment"] for row in rows]
