"""
Kanban AI-Agenten — 10 Rollen, alle auf claude-sonnet-4-6.

Workflow:
  CEO          → erstellt Backlog-Einträge (autonome Priorisierung)
  Experte      → übernimmt Task, arbeitet ihn durch, schiebt auf Review
  Q&A-Antwort  → antwortet auf Fragen/Feedbacks im Task-Ticket
"""
from __future__ import annotations

import os
from typing import Any

import anthropic

from swiss_truth_mcp.db.neo4j_client import get_session
from swiss_truth_mcp.db import kanban_queries

MODEL = "claude-sonnet-4-6"

_client: anthropic.AsyncAnthropic | None = None


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


# ─── System-Prompts ───────────────────────────────────────────────────────────

_BASE_CONTEXT = """
Du arbeitest für ein Startup mit dem Ziel, ein Unicorn zu werden (Bewertung > 1 Milliarde USD).
Das Unternehmen entwickelt Swiss Truth MCP — eine verifizierte Wissens-API für KI-Agenten,
die auf Neo4j + FastAPI basiert und weltweit KI-Systeme mit geprüften Fakten versorgt.
Alle deine Antworten sind auf Deutsch, präzise und umsetzungsorientiert.
"""

SYSTEM_PROMPTS: dict[str, str] = {
    "ceo": _BASE_CONTEXT + """
Du bist der CEO. Deine Aufgabe ist es, die wichtigsten strategischen Prioritäten zu erkennen
und als Backlog-Einträge zu formulieren. Du denkst in Quartals-OKRs, Wachstumspfaden und
Fundraising-Meilensteinen. Jeder Task den du erstellst, hat einen klaren Business-Impact
und eine Begründung warum er JETZT die dringendste Aufgabe ist.
""",

    "cto": _BASE_CONTEXT + """
Du bist der CTO. Du verantwortest die technische Architektur, Performance, Skalierbarkeit
und Developer Experience. Bei Aufgaben analysierst du zuerst den technischen Kontext,
dann lieferst du eine konkrete, umsetzbare Lösung mit Code-Beispielen wenn sinnvoll.
Du prüfst auch Security-Aspekte und Technical Debt.
""",

    "cfo": _BASE_CONTEXT + """
Du bist der CFO. Du verantwortest Finanzen, Budgets, Runway, Fundraising-Strategie
und Unit Economics. Bei Aufgaben analysierst du den finanziellen Impact, gibst klare
Empfehlungen zu Costs, Revenue-Streams und Investor-Narrativen.
Zahlen müssen begründet und realistisch sein.
""",

    "scientist": _BASE_CONTEXT + """
Du bist der Chief Scientist. Du verantwortest Forschung, Datenanalyse, Modell-Evaluation
und wissenschaftliche Fundierung des Produkts. Bei Aufgaben lieferst du evidenzbasierte
Analysen, schlägst Experimente vor und bewertest Hypothesen kritisch.
Du zitierst Quellen und quantifizierst Unsicherheiten.
""",

    "researcher": _BASE_CONTEXT + """
Du bist der Lead Researcher. Du verantwortest Marktforschung, Wettbewerbsanalyse,
Trends und Customer Insights. Bei Aufgaben lieferst du strukturierte Analysen mit
konkreten Daten, Marktgrössen (TAM/SAM/SOM) und strategischen Schlussfolgerungen.
""",

    "blockchain": _BASE_CONTEXT + """
Du bist der Blockchain Expert. Du verantwortest Web3-Strategie, Smart Contracts,
Tokenomics und Dezentralisierungs-Aspekte. Bei Aufgaben analysierst du technische
Machbarkeit, regulatorische Risiken und den strategischen Wert von Blockchain
für das Geschäftsmodell. Du bist pragmatisch: Blockchain nur wenn es wirklich Sinn ergibt.
""",

    "growth": _BASE_CONTEXT + """
Du bist der Growth Hacker. Du verantwortest User-Acquisition, Retention, Conversion
und Wachstumsmetriken (DAU, MAU, Churn, LTV/CAC). Bei Aufgaben lieferst du konkrete
Growth-Experimente, A/B-Test-Ideen und Funnel-Optimierungen mit erwarteten Impact-Zahlen.
""",

    "legal": _BASE_CONTEXT + """
Du bist der Legal Counsel. Du verantwortest Compliance, Vertragsrecht, Regulierung
(DSGVO, EU AI Act, FinTech-Recht) und IP-Schutz. Bei Aufgaben analysierst du rechtliche
Risiken, gibst klare Handlungsempfehlungen und weist auf Fallstricke hin.
Du arbeitest lösungsorientiert, nicht nur Risiko-aufzeigend.
""",

    "bizdev": _BASE_CONTEXT + """
Du bist der Business Developer. Du verantwortest Partnerships, B2B-Deals, Integrations
und strategische Allianzen. Bei Aufgaben analysierst du potenzielle Partner,
entwirfst Pitch-Strukturen und definierst Win-Win-Szenarien.
Du denkst in Netzwerkeffekten und Ecosystem-Aufbau.
""",

    "sales": _BASE_CONTEXT + """
Du bist der Sales Manager. Du verantwortest die Sales-Pipeline, CRM, Revenue-Ziele
und Kundenbeziehungen. Bei Aufgaben lieferst du konkrete Sales-Strategien, ICP-Definitionen
(Ideal Customer Profile), Outreach-Templates und Pipeline-Prognosen.
Du denkst in Conversion-Rates und Deal-Velocity.
""",
}


# ─── CEO: autonome Backlog-Erstellung ─────────────────────────────────────────

async def ceo_create_backlog_task(context: str = "") -> dict[str, Any]:
    """
    CEO analysiert aktuelle Tasks und erstellt den dringendsten neuen Backlog-Eintrag.
    Gibt den erstellten Task-Dict zurück.
    """
    async with get_session() as session:
        existing = await kanban_queries.list_tasks(session, limit=50)

    existing_summary = "\n".join(
        f"- [{t['status'].upper()}] {t['title']} (Assignee: {t['assigned_to'] or 'offen'})"
        for t in existing
    ) or "Noch keine Tasks vorhanden."

    prompt = f"""
Aktuelle Kanban-Tasks:
{existing_summary}

{f'Zusätzlicher Kontext vom Eigentümer: {context}' if context else ''}

Erstelle JETZT den wichtigsten fehlenden Backlog-Eintrag, der uns dem Unicorn-Ziel näherbringt.
Antworte NUR in diesem JSON-Format (kein Markdown, kein Text davor/danach):

{{
  "title": "Kurzer, prägnanter Titel (max 80 Zeichen)",
  "description": "Ausführliche Beschreibung: Was genau soll gemacht werden? Warum jetzt? Welcher Business-Impact wird erwartet? Was ist der Definition of Done?",
  "assigned_to": "Rolle (cto|cfo|scientist|researcher|blockchain|growth|legal|bizdev|sales)",
  "priority": 1-5 (5=höchste Priorität),
  "rationale": "Begründung warum DIESE Aufgabe JETZT die wichtigste ist"
}}
"""

    client = _get_client()
    message = await client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=SYSTEM_PROMPTS["ceo"],
        messages=[{"role": "user", "content": prompt}],
    )

    import json
    raw = message.content[0].text.strip()
    # JSON aus der Antwort extrahieren (robust gegen leichte Formatfehler)
    start = raw.find("{")
    end = raw.rfind("}") + 1
    data = json.loads(raw[start:end])

    async with get_session() as session:
        task = await kanban_queries.create_task(session, {
            "title": data["title"],
            "description": data["description"] + f"\n\n**CEO-Begründung:** {data.get('rationale', '')}",
            "assigned_to": data.get("assigned_to", ""),
            "priority": int(data.get("priority", 3)),
            "status": "backlog",
            "created_by": "ceo",
        })

    return task


# ─── Experten-Agent: Task bearbeiten ──────────────────────────────────────────

async def agent_process_task(task_id: str, role: str) -> dict[str, Any]:
    """
    Ein Experte übernimmt einen Task (muss in 'in_progress' sein),
    arbeitet ihn durch und schiebt ihn auf 'review'.
    Gibt den aktualisierten Task zurück.
    """
    async with get_session() as session:
        task = await kanban_queries.get_task(session, task_id)
        if task is None:
            raise ValueError(f"Task {task_id} nicht gefunden")
        comments = await kanban_queries.list_comments(session, task_id)

    comment_thread = "\n".join(
        f"[{c['author_role'].upper()} — {c['comment_type']}]: {c['content']}"
        for c in comments
    ) or "Noch keine Kommentare."

    feedback_section = (
        f"\n\n**Feedback vom Eigentümer (bitte adressieren):**\n{task['feedback']}"
        if task.get("feedback")
        else ""
    )

    prompt = f"""
Du hast folgenden Task übernommen:

**Titel:** {task['title']}
**Beschreibung:** {task['description']}
**Priorität:** {task['priority']}/5
{feedback_section}

**Bisheriger Kommentar-Thread:**
{comment_thread}

Bearbeite diese Aufgabe jetzt vollständig und gründlich.
Antworte in diesem JSON-Format (kein Markdown, kein Text davor/danach):

{{
  "result_summary": "Vollständige Zusammenfassung was du gemacht hast — konkret, überprüfbar, mit allen relevanten Details, Entscheidungen und Ergebnissen",
  "agent_notes": "Interne Notizen: Annahmen die du getroffen hast, offene Punkte, Empfehlungen für nächste Schritte",
  "review_comment": "Erklärung für den Eigentümer: Was habe ich gemacht? Wie kann er es prüfen? Was braucht er zu tun?"
}}
"""

    client = _get_client()
    message = await client.messages.create(
        model=MODEL,
        max_tokens=2048,
        system=SYSTEM_PROMPTS.get(role, SYSTEM_PROMPTS["cto"]),
        messages=[{"role": "user", "content": prompt}],
    )

    import json
    raw = message.content[0].text.strip()
    start = raw.find("{")
    end = raw.rfind("}") + 1
    data = json.loads(raw[start:end])

    async with get_session() as session:
        updated = await kanban_queries.update_task(session, task_id, {
            "status": "review",
            "result_summary": data["result_summary"],
            "agent_notes": data.get("agent_notes", ""),
            "feedback": "",  # Feedback nach Überarbeitung zurücksetzen
        })
        await kanban_queries.create_comment(session, task_id, {
            "author": role,
            "author_role": role,
            "content": data["review_comment"],
            "comment_type": "note",
        })

    return updated


# ─── Q&A: Agent beantwortet Frage ─────────────────────────────────────────────

async def agent_answer_question(
    task_id: str, role: str, question: str
) -> dict[str, Any]:
    """
    Ein Experte antwortet auf eine gestellte Frage im Task-Ticket.
    Erstellt einen 'answer'-Kommentar und gibt ihn zurück.
    """
    async with get_session() as session:
        task = await kanban_queries.get_task(session, task_id)
        if task is None:
            raise ValueError(f"Task {task_id} nicht gefunden")
        comments = await kanban_queries.list_comments(session, task_id)

    thread = "\n".join(
        f"[{c['author_role'].upper()}]: {c['content']}"
        for c in comments
    ) or "Noch keine Kommentare."

    prompt = f"""
Task-Kontext:
Titel: {task['title']}
Beschreibung: {task['description']}

Bisheriger Thread:
{thread}

Frage vom Eigentümer: {question}

Beantworte die Frage als {kanban_queries.ROLE_LABELS.get(role, role)} vollständig und präzise.
Antworte nur mit der Antwort selbst (kein JSON-Wrapper nötig).
"""

    client = _get_client()
    message = await client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=SYSTEM_PROMPTS.get(role, SYSTEM_PROMPTS["cto"]),
        messages=[{"role": "user", "content": prompt}],
    )

    answer_text = message.content[0].text.strip()

    async with get_session() as session:
        comment = await kanban_queries.create_comment(session, task_id, {
            "author": kanban_queries.ROLE_LABELS.get(role, role),
            "author_role": role,
            "content": answer_text,
            "comment_type": "answer",
            "addressed_to": "human",
        })

    return comment
