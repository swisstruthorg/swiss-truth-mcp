"""
Kanban Board — REST API + SSE stream for agent task management.

Endpoints:
  GET  /kanban           → HTML dashboard (kanban.html)
  GET  /kanban/tasks     → JSON list of tasks
  POST /kanban/tasks     → Create task
  PATCH /kanban/tasks/{id} → Update task
  DELETE /kanban/tasks/{id} → Delete task
  GET  /kanban/stream    → SSE stream for real-time updates
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.requests import Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from swiss_truth_mcp.db.neo4j_client import get_session
from swiss_truth_mcp.db import kanban_queries

TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(tags=["kanban"])

# ─── SSE broadcaster ─────────────────────────────────────────────────────────
# One asyncio.Queue per connected SSE client.
_sse_clients: list[asyncio.Queue] = []


async def _broadcast(event: dict[str, Any]) -> None:
    payload = json.dumps(event)
    for q in list(_sse_clients):
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            pass


# ─── Pydantic models ─────────────────────────────────────────────────────────

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
    session_id: Optional[str] = None


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


# ─── REST endpoints ───────────────────────────────────────────────────────────

@router.get("/kanban/tasks")
async def list_tasks(
    status: Optional[str] = None,
    assigned_to: Optional[str] = None,
):
    async with get_session() as session:
        return await kanban_queries.list_tasks(session, status=status, assigned_to=assigned_to)


@router.post("/kanban/tasks", status_code=201)
async def create_task(body: TaskCreate):
    async with get_session() as session:
        task = await kanban_queries.create_task(session, body.model_dump())
    await _broadcast({"type": "task_created", "task": task})
    return task


@router.patch("/kanban/tasks/{task_id}")
async def update_task(task_id: str, body: TaskUpdate):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    async with get_session() as session:
        task = await kanban_queries.update_task(session, task_id, updates)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    await _broadcast({"type": "task_updated", "task": task})
    return task


@router.delete("/kanban/tasks/{task_id}", status_code=204)
async def delete_task(task_id: str):
    async with get_session() as session:
        deleted = await kanban_queries.delete_task(session, task_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Task not found")
    await _broadcast({"type": "task_deleted", "task_id": task_id})


# ─── SSE stream ───────────────────────────────────────────────────────────────

@router.get("/kanban/stream", include_in_schema=False)
async def kanban_stream(request: Request):
    """Server-Sent Events: emits task_created / task_updated / task_deleted."""
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    _sse_clients.append(queue)

    async def generator():
        try:
            # Keep-alive ping every 15s
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"data: {payload}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            _sse_clients.remove(queue)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
