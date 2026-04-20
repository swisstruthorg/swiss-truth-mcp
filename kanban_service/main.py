"""
Swiss Truth Kanban — Standalone FastAPI Service
Läuft unabhängig auf Hostinger KVM 4, ohne Neo4j.
Datenbank: SQLite via aiosqlite
"""
from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.requests import Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

import db
import agents

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# ─── SSE broadcaster ──────────────────────────────────────────────────────────
_sse_clients: list[asyncio.Queue] = []


async def _broadcast(event: dict[str, Any]) -> None:
    payload = json.dumps(event, ensure_ascii=False)
    for q in list(_sse_clients):
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            pass


# ─── Startup ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(os.path.dirname(db.DB_PATH), exist_ok=True)
    await db.init_db()
    yield


app = FastAPI(
    title="Swiss Truth Kanban",
    description="Internes Kanban-Board mit AI-Agenten",
    version="1.0.0",
    lifespan=lifespan,
)


# ─── Pydantic Models ──────────────────────────────────────────────────────────

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
    comment_type: str = "note"
    addressed_to: str = ""


class AgentTrigger(BaseModel):
    role: str
    question: Optional[str] = None


class CeoRequest(BaseModel):
    context: str = ""


# ─── HTML Board ───────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
@app.get("/kanban", response_class=HTMLResponse, include_in_schema=False)
async def kanban_board(request: Request):
    tasks = await db.list_tasks()
    return templates.TemplateResponse(
        request, "kanban.html",
        {"request": request, "tasks": tasks, "active": "kanban"},
    )


# ─── Health ───────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "service": "kanban", "version": "1.0.0"}


# ─── Task Endpoints ───────────────────────────────────────────────────────────

@app.get("/kanban/tasks")
async def list_tasks(status: Optional[str] = None, assigned_to: Optional[str] = None):
    return await db.list_tasks(status=status, assigned_to=assigned_to)


@app.get("/kanban/tasks/{task_id}")
async def get_task(task_id: str):
    task = await db.get_task(task_id)
    if task is None:
        raise HTTPException(404, "Task nicht gefunden")
    return task


@app.post("/kanban/tasks", status_code=201)
async def create_task(body: TaskCreate):
    task = await db.create_task(body.model_dump())
    await _broadcast({"type": "task_created", "task": task})
    return task


@app.patch("/kanban/tasks/{task_id}")
async def update_task(task_id: str, body: TaskUpdate):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}

    if "status" in updates:
        current = await db.get_task(task_id)
        if current is None:
            raise HTTPException(404, "Task nicht gefunden")
        allowed = db.VALID_TRANSITIONS.get(current["status"], [])
        if updates["status"] not in allowed and updates["status"] != current["status"]:
            raise HTTPException(
                422,
                f"Übergang '{current['status']}' → '{updates['status']}' nicht erlaubt. "
                f"Erlaubt: {allowed}",
            )

    task = await db.update_task(task_id, updates)
    if task is None:
        raise HTTPException(404, "Task nicht gefunden")
    await _broadcast({"type": "task_updated", "task": task})
    return task


@app.delete("/kanban/tasks/{task_id}", status_code=204)
async def delete_task(task_id: str):
    deleted = await db.delete_task(task_id)
    if not deleted:
        raise HTTPException(404, "Task nicht gefunden")
    await _broadcast({"type": "task_deleted", "task_id": task_id})


# ─── Comment Endpoints ────────────────────────────────────────────────────────

@app.get("/kanban/tasks/{task_id}/comments")
async def list_comments(task_id: str):
    task = await db.get_task(task_id)
    if task is None:
        raise HTTPException(404, "Task nicht gefunden")
    return await db.list_comments(task_id)


@app.post("/kanban/tasks/{task_id}/comments", status_code=201)
async def create_comment(task_id: str, body: CommentCreate):
    comment = await db.create_comment(task_id, body.model_dump())
    if comment is None:
        raise HTTPException(404, "Task nicht gefunden")
    await _broadcast({"type": "comment_created", "task_id": task_id, "comment": comment})
    return comment


# ─── Agent Endpoints ──────────────────────────────────────────────────────────

@app.post("/kanban/tasks/{task_id}/trigger")
async def trigger_agent(task_id: str, body: AgentTrigger):
    if body.role not in agents.SYSTEM_PROMPTS:
        raise HTTPException(422, f"Ungültige Rolle '{body.role}'")
    try:
        if body.question:
            result = await agents.agent_answer_question(task_id, body.role, body.question)
            await _broadcast({"type": "comment_created", "task_id": task_id, "comment": result})
            return {"mode": "qa", "comment": result}
        else:
            task = await db.get_task(task_id)
            if task is None:
                raise HTTPException(404, "Task nicht gefunden")
            if task["status"] != "in_progress":
                raise HTTPException(
                    422,
                    f"Task muss 'in_progress' sein (aktuell: '{task['status']}')",
                )
            updated = await agents.agent_process_task(task_id, body.role)
            await _broadcast({"type": "task_updated", "task": updated})
            return {"mode": "process", "task": updated}
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, f"Agent-Fehler: {e}")


@app.post("/kanban/agent/ceo", status_code=201)
async def ceo_create_task(body: CeoRequest):
    try:
        task = await agents.ceo_create_backlog_task(context=body.context)
        await _broadcast({"type": "task_created", "task": task})
        return task
    except Exception as e:
        raise HTTPException(500, f"CEO-Agent-Fehler: {e}")


# ─── SSE Stream ───────────────────────────────────────────────────────────────

@app.get("/kanban/stream", include_in_schema=False)
async def kanban_stream(request: Request):
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
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=False)
