"""
Kanban Board — REST API + SSE stream für agent task management.

Endpoints:
  GET    /kanban                          → HTML dashboard
  GET    /kanban/tasks                    → JSON task-Liste
  POST   /kanban/tasks                    → Task erstellen
  GET    /kanban/tasks/{id}               → Einzelner Task
  PATCH  /kanban/tasks/{id}               → Task aktualisieren
  DELETE /kanban/tasks/{id}               → Task löschen
  GET    /kanban/tasks/{id}/comments      → Kommentar-Liste
  POST   /kanban/tasks/{id}/comments      → Kommentar erstellen
  POST   /kanban/tasks/{id}/trigger       → AI-Experte triggern (Q&A oder Task-Bearbeitung)
  POST   /kanban/agent/ceo                → CEO erstellt neuen Backlog-Eintrag
  GET    /kanban/stream                   → SSE-Stream (Real-time Updates)
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from fastapi.requests import Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from swiss_truth_mcp.db.neo4j_client import get_session
from swiss_truth_mcp.db import kanban_queries
from swiss_truth_mcp.api import kanban_agents

TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(tags=["kanban"])

# ─── SSE broadcaster ──────────────────────────────────────────────────────────
_sse_clients: list[asyncio.Queue] = []


async def _broadcast(event: dict[str, Any]) -> None:
    payload = json.dumps(event, ensure_ascii=False)
    for q in list(_sse_clients):
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            pass


# ─── Pydantic models ──────────────────────────────────────────────────────────

class TaskCreate(BaseModel):
    title: str
    description: str = ""
    status: str = "backlog"
    assigned_to: str = ""
    priority: int = 3
    created_by: str = "human"


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    assigned_to: Optional[str] = None
    priority: Optional[int] = None
    result_summary: Optional[str] = None
    agent_notes: Optional[str] = None
    feedback: Optional[str] = None
    session_id: Optional[str] = None


class CommentCreate(BaseModel):
    content: str
    author: str = "Martin"
    author_role: str = "human"
    comment_type: str = "note"   # question | answer | feedback | note
    addressed_to: str = ""       # Rolle des Empfängers (z.B. "cto")


class AgentTriggerRequest(BaseModel):
    role: str                    # ceo | cto | cfo | ...
    question: Optional[str] = None  # Wenn gesetzt: Q&A-Modus; sonst Task-Bearbeitung


class CeoRequest(BaseModel):
    context: str = ""            # Optionaler Kontext vom Eigentümer


# ─── HTML dashboard ───────────────────────────────────────────────────────────

@router.get("/kanban", response_class=HTMLResponse, include_in_schema=False)
async def kanban_board(request: Request):
    async with get_session() as session:
        tasks = await kanban_queries.list_tasks(session)
    return templates.TemplateResponse(
        request,
        "kanban.html",
        {"request": request, "tasks": tasks, "active": "kanban"},
    )


# ─── Task-Endpoints ───────────────────────────────────────────────────────────

@router.get("/kanban/tasks")
async def list_tasks(
    status: Optional[str] = None,
    assigned_to: Optional[str] = None,
):
    async with get_session() as session:
        return await kanban_queries.list_tasks(session, status=status, assigned_to=assigned_to)


@router.get("/kanban/tasks/{task_id}")
async def get_task(task_id: str):
    async with get_session() as session:
        task = await kanban_queries.get_task(session, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task nicht gefunden")
    return task


@router.post("/kanban/tasks", status_code=201)
async def create_task(body: TaskCreate):
    async with get_session() as session:
        task = await kanban_queries.create_task(session, body.model_dump())
    await _broadcast({"type": "task_created", "task": task})
    return task


@router.patch("/kanban/tasks/{task_id}")
async def update_task(task_id: str, body: TaskUpdate):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}

    # Status-Übergangs-Validierung
    if "status" in updates:
        async with get_session() as session:
            current = await kanban_queries.get_task(session, task_id)
        if current is None:
            raise HTTPException(status_code=404, detail="Task nicht gefunden")
        new_status = updates["status"]
        allowed = kanban_queries.VALID_TRANSITIONS.get(current["status"], [])
        if new_status not in allowed and new_status != current["status"]:
            raise HTTPException(
                status_code=422,
                detail=f"Übergang '{current['status']}' → '{new_status}' nicht erlaubt. "
                       f"Erlaubt: {allowed}",
            )

    async with get_session() as session:
        task = await kanban_queries.update_task(session, task_id, updates)
    if task is None:
        raise HTTPException(status_code=404, detail="Task nicht gefunden")
    await _broadcast({"type": "task_updated", "task": task})
    return task


@router.delete("/kanban/tasks/{task_id}", status_code=204)
async def delete_task(task_id: str):
    async with get_session() as session:
        deleted = await kanban_queries.delete_task(session, task_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Task nicht gefunden")
    await _broadcast({"type": "task_deleted", "task_id": task_id})


# ─── Kommentar-Endpoints ──────────────────────────────────────────────────────

@router.get("/kanban/tasks/{task_id}/comments")
async def list_comments(task_id: str):
    async with get_session() as session:
        task = await kanban_queries.get_task(session, task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Task nicht gefunden")
        return await kanban_queries.list_comments(session, task_id)


@router.post("/kanban/tasks/{task_id}/comments", status_code=201)
async def create_comment(task_id: str, body: CommentCreate):
    async with get_session() as session:
        comment = await kanban_queries.create_comment(session, task_id, body.model_dump())
    if comment is None:
        raise HTTPException(status_code=404, detail="Task nicht gefunden")
    await _broadcast({"type": "comment_created", "task_id": task_id, "comment": comment})
    return comment


# ─── AI-Agenten-Endpoints ─────────────────────────────────────────────────────

@router.post("/kanban/tasks/{task_id}/trigger")
async def trigger_agent(task_id: str, body: AgentTriggerRequest):
    """
    Triggert einen AI-Agenten für einen Task:
    - Mit `question`: Agent antwortet auf die Frage (Q&A-Modus)
    - Ohne `question`: Agent bearbeitet den Task vollständig und schiebt auf Review
    """
    valid_roles = list(kanban_agents.SYSTEM_PROMPTS.keys())
    if body.role not in valid_roles:
        raise HTTPException(
            status_code=422,
            detail=f"Ungültige Rolle '{body.role}'. Erlaubt: {valid_roles}",
        )

    try:
        if body.question:
            # Q&A-Modus: Frage beantworten
            result = await kanban_agents.agent_answer_question(
                task_id, body.role, body.question
            )
            await _broadcast({"type": "comment_created", "task_id": task_id, "comment": result})
            return {"mode": "qa", "comment": result}
        else:
            # Task-Bearbeitung: vollständig durcharbeiten → Review
            async with get_session() as session:
                task = await kanban_queries.get_task(session, task_id)
            if task is None:
                raise HTTPException(status_code=404, detail="Task nicht gefunden")
            if task["status"] != "in_progress":
                raise HTTPException(
                    status_code=422,
                    detail=f"Task muss 'in_progress' sein (aktuell: '{task['status']}'). "
                           "Bitte zuerst auf 'in_progress' verschieben.",
                )
            updated = await kanban_agents.agent_process_task(task_id, body.role)
            await _broadcast({"type": "task_updated", "task": updated})
            return {"mode": "process", "task": updated}

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent-Fehler: {str(e)}")


@router.post("/kanban/agent/ceo", status_code=201)
async def ceo_create_task(body: CeoRequest):
    """
    CEO-Agent analysiert aktuelle Tasks und erstellt den wichtigsten Backlog-Eintrag.
    """
    try:
        task = await kanban_agents.ceo_create_backlog_task(context=body.context)
        await _broadcast({"type": "task_created", "task": task})
        return task
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"CEO-Agent-Fehler: {str(e)}")


# ─── SSE stream ───────────────────────────────────────────────────────────────

@router.get("/kanban/stream", include_in_schema=False)
async def kanban_stream(request: Request):
    """Server-Sent Events: task_created / task_updated / task_deleted / comment_created."""
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    _sse_clients.append(queue)

    async def generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"data: {payload}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            if queue in _sse_clients:
                _sse_clients.remove(queue)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
