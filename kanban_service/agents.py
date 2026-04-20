"""
AI-Agenten für den Standalone-Kanban-Service.
Identisch mit der integrierten Version, aber ohne Neo4j-Abhängigkeit.
Modell: claude-sonnet-4-6
"""
from __future__ import annotations

import json
import os
from typing import Any

import anthropic

import db

MODEL = "claude-sonnet-4-6"

_client: anthropic.AsyncAnthropic | None = None


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


_BASE = """
Du arbeitest für ein Startup mit dem Ziel, ein Unicorn zu werden (Bewertung > 1 Milliarde USD).
Das Unternehmen entwickelt Swiss Truth MCP — eine verifizierte Wissens-API für KI-Agenten,
die auf Neo4j + FastAPI basiert und weltweit KI-Systeme mit geprüften Fakten versorgt.
Alle deine Antworten sind auf Deutsch, präzise und umsetzungsorientiert.
"""

SYSTEM_PROMPTS: dict[str, str] = {
    "ceo": _BASE + """
Du bist der CEO. Deine Aufgabe ist es, die wichtigsten strategischen Prioritäten zu erkennen
und als Backlog-Einträge zu formulieren. Du denkst in Quartals-OKRs, Wachstumspfaden und
Fundraising-Meilensteinen. Jeder Task den du erstellst, hat einen klaren Business-Impact
und eine Begründung warum er JETZT die dringendste Aufgabe ist.
""",
    "cto": _BASE + """
Du bist der CTO. Du verantwortest Architektur, Performance, Skalierbarkeit und Developer
Experience. Bei Aufgaben analysierst du zuerst den technischen Kontext, dann lieferst du
eine konkrete, umsetzbare Lösung mit Code-Beispielen wenn sinnvoll.
""",
    "cfo": _BASE + """
Du bist der CFO. Du verantwortest Finanzen, Budgets, Runway, Fundraising und Unit Economics.
Bei Aufgaben analysierst du finanziellen Impact und gibst klare Empfehlungen zu Costs,
Revenue-Streams und Investor-Narrativen. Zahlen müssen begründet und realistisch sein.
""",
    "scientist": _BASE + """
Du bist der Chief Scientist. Du verantwortest Forschung, Datenanalyse und wissenschaftliche
Fundierung. Bei Aufgaben lieferst du evidenzbasierte Analysen und schlägst Experimente vor.
Du zitierst Quellen und quantifizierst Unsicherheiten.
""",
    "researcher": _BASE + """
Du bist der Lead Researcher. Du verantwortest Marktforschung, Wettbewerbsanalyse und
Trends. Bei Aufgaben lieferst du strukturierte Analysen mit Marktgrössen (TAM/SAM/SOM)
und strategischen Schlussfolgerungen.
""",
    "blockchain": _BASE + """
Du bist der Blockchain Expert. Du verantwortest Web3-Strategie, Smart Contracts und
Tokenomics. Du bist pragmatisch: Blockchain nur wenn es wirklich Sinn ergibt.
""",
    "growth": _BASE + """
Du bist der Growth Hacker. Du verantwortest User-Acquisition, Retention und Wachstums-
metriken. Bei Aufgaben lieferst du konkrete Growth-Experimente und Funnel-Optimierungen
mit erwarteten Impact-Zahlen.
""",
    "legal": _BASE + """
Du bist der Legal Counsel. Du verantwortest Compliance, Vertragsrecht und Regulierung
(DSGVO, EU AI Act, FinTech). Du arbeitest lösungsorientiert, nicht nur Risiko-aufzeigend.
""",
    "bizdev": _BASE + """
Du bist der Business Developer. Du verantwortest Partnerships, B2B-Deals und strategische
Allianzen. Du denkst in Netzwerkeffekten und Ecosystem-Aufbau.
""",
    "sales": _BASE + """
Du bist der Sales Manager. Du verantwortest Sales-Pipeline, CRM und Revenue-Ziele.
Bei Aufgaben lieferst du konkrete Sales-Strategien, ICP-Definitionen und Pipeline-Prognosen.
""",
}


async def ceo_create_backlog_task(context: str = "") -> dict[str, Any]:
    """CEO analysiert aktuelle Tasks und erstellt den dringendsten Backlog-Eintrag."""
    existing = await db.list_tasks(limit=50)
    existing_summary = "\n".join(
        f"- [{t['status'].upper()}] {t['title']} (Assignee: {t['assigned_to'] or 'offen'})"
        for t in existing
    ) or "Noch keine Tasks vorhanden."

    prompt = f"""
Aktuelle Kanban-Tasks:
{existing_summary}

{f'Zusätzlicher Kontext: {context}' if context else ''}

Erstelle JETZT den wichtigsten fehlenden Backlog-Eintrag.
Antworte NUR in diesem JSON-Format (kein Markdown):

{{
  "title": "Kurzer, prägnanter Titel (max 80 Zeichen)",
  "description": "Ausführliche Beschreibung: Was? Warum jetzt? Welcher Business-Impact? Definition of Done?",
  "assigned_to": "Rolle (cto|cfo|scientist|researcher|blockchain|growth|legal|bizdev|sales)",
  "priority": 1,
  "rationale": "Begründung warum DIESE Aufgabe JETZT die wichtigste ist"
}}
"""
    client = _get_client()
    message = await client.messages.create(
        model=MODEL, max_tokens=1024,
        system=SYSTEM_PROMPTS["ceo"],
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text.strip()
    data = json.loads(raw[raw.find("{"):raw.rfind("}") + 1])

    return await db.create_task({
        "title": data["title"],
        "description": data["description"] + f"\n\n**CEO-Begründung:** {data.get('rationale', '')}",
        "assigned_to": data.get("assigned_to", ""),
        "priority": int(data.get("priority", 3)),
        "status": "backlog",
        "created_by": "ceo",
    })


async def agent_process_task(task_id: str, role: str) -> dict[str, Any]:
    """Experte bearbeitet Task vollständig und schiebt ihn auf Review."""
    task = await db.get_task(task_id)
    if task is None:
        raise ValueError(f"Task {task_id} nicht gefunden")
    comments = await db.list_comments(task_id)

    thread = "\n".join(
        f"[{c['author_role'].upper()} — {c['comment_type']}]: {c['content']}"
        for c in comments
    ) or "Noch keine Kommentare."

    feedback_section = (
        f"\n\n**Feedback vom Eigentümer:**\n{task['feedback']}"
        if task.get("feedback") else ""
    )

    prompt = f"""
Task: {task['title']}
Beschreibung: {task['description']}
Priorität: {task['priority']}/5
{feedback_section}

Bisheriger Thread:
{thread}

Bearbeite diese Aufgabe vollständig. Antworte NUR in diesem JSON-Format:

{{
  "result_summary": "Was hast du gemacht — konkret, überprüfbar, alle Entscheidungen und Ergebnisse",
  "agent_notes": "Interne Notizen: Annahmen, offene Punkte, Empfehlungen",
  "review_comment": "Erklärung für den Eigentümer: Was wurde gemacht? Wie kann er es prüfen?"
}}
"""
    client = _get_client()
    message = await client.messages.create(
        model=MODEL, max_tokens=2048,
        system=SYSTEM_PROMPTS.get(role, SYSTEM_PROMPTS["cto"]),
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text.strip()
    data = json.loads(raw[raw.find("{"):raw.rfind("}") + 1])

    updated = await db.update_task(task_id, {
        "status": "review",
        "result_summary": data["result_summary"],
        "agent_notes": data.get("agent_notes", ""),
        "feedback": "",
    })
    await db.create_comment(task_id, {
        "author": db.ROLE_LABELS.get(role, role),
        "author_role": role,
        "content": data["review_comment"],
        "comment_type": "note",
    })
    return updated


async def agent_answer_question(task_id: str, role: str, question: str) -> dict[str, Any]:
    """Experte antwortet auf eine Frage im Task-Ticket."""
    task = await db.get_task(task_id)
    if task is None:
        raise ValueError(f"Task {task_id} nicht gefunden")
    comments = await db.list_comments(task_id)

    thread = "\n".join(
        f"[{c['author_role'].upper()}]: {c['content']}"
        for c in comments
    ) or "Noch keine Kommentare."

    prompt = f"""
Task: {task['title']}
Beschreibung: {task['description']}

Thread:
{thread}

Frage: {question}

Beantworte als {db.ROLE_LABELS.get(role, role)} vollständig und präzise.
Antworte nur mit der Antwort (kein JSON-Wrapper).
"""
    client = _get_client()
    message = await client.messages.create(
        model=MODEL, max_tokens=1024,
        system=SYSTEM_PROMPTS.get(role, SYSTEM_PROMPTS["cto"]),
        messages=[{"role": "user", "content": prompt}],
    )
    answer = message.content[0].text.strip()

    return await db.create_comment(task_id, {
        "author": db.ROLE_LABELS.get(role, role),
        "author_role": role,
        "content": answer,
        "comment_type": "answer",
        "addressed_to": "human",
    })
