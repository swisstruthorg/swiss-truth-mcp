# ROADMAP: Swiss Truth — KI-Agenten-Abhängigkeit & Skalierung

*Erstellt: 2026-04-23*
*Zeitrahmen: Mai 2026 – Oktober 2026 (6 Monate)*

**Vision:** Swiss Truth wird die unverzichtbare Wissensinfrastruktur, die KI-Agenten brauchen und der sie vertrauen — so dass sie ohne uns nicht mehr zuverlässig arbeiten können.

**Kernstrategie:**
> Erst das Regal füllen (Phase 10) → dann den Laden bewerben (Phase 11) → dann Kunden binden (Phase 12) → dann expandieren (Phase 13) → dann monetarisieren (Phase 14) → dann den Moat bauen (Phase 15).

---

## Aktueller Stand (April 2026)

| Was | Status |
|-----|--------|
| 30 Domains mit Topics + Primärquellen definiert | ✅ |
| Claim-Generator mit Pareto-Strategie (`seed/generator.py`) | ✅ |
| Multi-Language-Support FR/IT/ES/ZH (`seed/multilang.py`) | ✅ |
| Coverage-Analyse per Domain (`validation/coverage.py`) | ✅ |
| Auto-Pipeline für automatische Verifizierung | ✅ |
| LangChain, CrewAI, AutoGen Integrationen (published) | ✅ |
| Discovery-Endpoints (mcp.json, ai-plugin.json, llms.txt) | ✅ |
| Smithery Listing | ✅ |
| **⚠️ Viele Domains haben zu wenige Claims für echten Agenten-Nutzen** | PROBLEM |

---

## Phase 10: Content Foundation — Claim-Masse aufbauen (Mai 2026, Woche 1–3)

**Milestone:** *"Erst das Regal füllen, dann den Laden öffnen."*

**Ziel:** Jede der 30 Domains hat genug verifizierte Claims, dass ein KI-Agent sofort echten Wert findet — beim ersten Request.

### 10-01: Coverage-Audit aller 30 Domains (Woche 1)

- Coverage-Analyse für alle Domains: `GET /api/coverage`
- Domains in 3 Tiers einteilen:

**Tier 1 — Kern (müssen EXZELLENT sein: ≥90% Coverage, 50+ Claims)**
- swiss-health, swiss-law, swiss-finance
- ai-ml, ai-safety, eu-law

**Tier 2 — Wichtig (GUTE Coverage: ≥70%, 30+ Claims)**
- climate, cybersecurity, economics, biotech
- us-law, world-science, eu-health, global-science

**Tier 3 — Basis (MODERATE Coverage: ≥50%, 15+ Claims)**
- swiss-education, swiss-energy, swiss-transport, swiss-politics
- swiss-agriculture, swiss-digital, swiss-environment
- mental-health, blockchain-crypto, nutrition-food, labor-employment
- quantum-computing, space-science, renewable-energy
- world-history, international-law

**Output:** Priorisierte Liste welche Domains zuerst befüllt werden + Gaps pro Domain.

### 10-02: Bulk Claim Generation — Tier 1 Domains (Woche 1–2)

```bash
swiss-truth-generate --domain swiss-health   --count 50 --import
swiss-truth-generate --domain swiss-law      --count 50 --import
swiss-truth-generate --domain swiss-finance  --count 50 --import
swiss-truth-generate --domain ai-ml          --count 50 --import
swiss-truth-generate --domain ai-safety      --count 50 --import
swiss-truth-generate --domain eu-law         --count 50 --import
```

**Qualitätsstandards für jeden Claim:**
- `question` + `text` Dual-Format (verbessert Vektor-Retrieval massiv)
- Primärquellen aus `DOMAIN_PRIMARY_SOURCES` (keine Wikipedia als source_url)
- Confidence Score ≥ 0.85
- SHA256 Integritäts-Hash
- Nur aktuelle, verifizierte Fakten

**Qualitätskontrolle:** 10% Stichproben-Review manuell

**Ziel:** 300+ neue Claims in Tier-1-Domains

### 10-03: Bulk Claim Generation — Tier 2 & 3 Domains (Woche 2–3)

```bash
# Tier 2: 30 Claims pro Domain
swiss-truth-generate --domain climate         --count 30 --import
swiss-truth-generate --domain cybersecurity   --count 30 --import
swiss-truth-generate --domain economics       --count 30 --import
swiss-truth-generate --domain biotech         --count 30 --import
swiss-truth-generate --domain us-law          --count 30 --import
swiss-truth-generate --domain world-science   --count 30 --import
swiss-truth-generate --domain eu-health       --count 30 --import
swiss-truth-generate --domain global-science  --count 30 --import

# Tier 3: 15 Claims pro Domain (inkl. neue Phase-8-Domains erstmals befüllen)
swiss-truth-generate --domain mental-health       --count 15 --import
swiss-truth-generate --domain blockchain-crypto   --count 15 --import
swiss-truth-generate --domain nutrition-food      --count 15 --import
swiss-truth-generate --domain labor-employment    --count 15 --import
swiss-truth-generate --domain swiss-environment   --count 15 --import
# ... alle weiteren Tier-3-Domains
```

**Ziel:** 500+ neue Claims über alle Domains, 0 Domains mit 0 Claims

### 10-04: Multi-Language Expansion (Woche 3)

```bash
# Schweizer Landessprachen zuerst
python -m swiss_truth_mcp.seed.multilang --domain swiss-health  --lang fr
python -m swiss_truth_mcp.seed.multilang --domain swiss-law     --lang fr
python -m swiss_truth_mcp.seed.multilang --domain swiss-finance --lang fr
python -m swiss_truth_mcp.seed.multilang --domain swiss-health  --lang it
python -m swiss_truth_mcp.seed.multilang --domain swiss-law     --lang it
python -m swiss_truth_mcp.seed.multilang --domain ai-ml         --lang fr
# Englische Tier-1-Domains auch auf DE wenn nicht vorhanden
```

**Ziel:** 200+ mehrsprachige Claims (FR + IT Priorität für Schweizer Markt)

### 10-05: Quality Assurance & Conflict Resolution (Woche 3)

- Conflict Detection über alle neuen Claims: `GET /api/conflicts`
- Duplikate identifizieren via Clustering (`validation/clustering.py`)
- Expired Claims erneuern: `POST /admin/renewal`
- Coverage-Analyse erneut laufen → alle Tier-1-Domains ≥90%
- Audit Trail Export für Qualitätsnachweis

**Ziel:** Saubere, konfliktfreie, verifizierte Wissensbasis

### 10-06: Agent-Attraktivitäts-Benchmark

Für jede der 8 Agent-Personas testen ob typische Queries relevante Ergebnisse liefern:

| Agent-Persona | Test-Queries | Ziel |
|---------------|-------------|------|
| Research Agent | Fakten zu Klimawandel, KI, Geschichte | ≥80% Treffer |
| Legal & Compliance Agent | Schweizer Mietrecht, DSGVO, EU AI Act | ≥80% Treffer |
| Health Advisory Agent | KVG, Krankenkassen, WHO-Guidelines | ≥80% Treffer |
| Financial Agent | SNB, FINMA, Steuern Schweiz | ≥80% Treffer |
| RAG Pipeline | Semantische Suche über 5+ Domains | ≥80% Treffer |
| Content Gen Agent | Fakten-Checks zu Artikeln | ≥80% Treffer |
| Multi-Agent Orchestrator | Batch-Verify, Cross-Domain | ≥80% Treffer |
| Developer Building Agents | API-Docs, Quick-Setup funktioniert | 100% |

**Ziel:** Jeder Agent-Typ findet beim ersten Besuch sofort echten Wert

### KPIs Phase 10

| Metrik | Aktuell | Ziel |
|--------|---------|------|
| Gesamte zertifizierte Claims | ~2000 | 3000+ |
| Tier-1 Coverage Rate | ? | ≥90% |
| Tier-2 Coverage Rate | ? | ≥70% |
| Tier-3 Coverage Rate | ? | ≥50% |
| Mehrsprachige Claims | ? | 200+ |
| Agent-Persona-Testrate | ? | ≥80% |
| Domains mit 0 Claims | ? | 0 |

**Status:** 🔄 Geplant — Start Mai 2026

---

## Phase 11: Agent Acquisition Blitz (Mai/Juni 2026, Woche 3–5)

**Milestone:** *"Agenten finden uns überall."*

### 11-01: MCP Directory Dominanz (Woche 3–4)
- [ ] **modelcontextprotocol/servers** — PR einreichen (höchster Impact, ~100k Besucher/Monat)
- [ ] **awesome-mcp-servers** — PR einreichen (~30k GitHub Stars)
- [ ] **Glama** — Listing einreichen (https://glama.ai/mcp/servers)
- [ ] **mcp.run** — Listing einreichen
- [ ] **PulseMCP** — Listing einreichen
- [ ] **mcpservers.org** — PR einreichen
- [ ] **awesome-langchain** — PR einreichen
- [ ] **awesome-ai-agents** — PR einreichen
- [ ] **awesome-llm-apps** — PR einreichen

**Ziel:** Von 1 Listing (Smithery) → 8+ Listings

### 11-02: Community Blitz (Woche 4–5)
- [ ] LangChain Discord — `#tools-and-integrations`
- [ ] CrewAI Discord — `#tools` / `#showcase`
- [ ] AutoGen Discord — `#tools-and-extensions`
- [ ] **Hacker News** — "Show HN: Swiss Truth — verified knowledge base for AI agents"
- [ ] Reddit r/LangChain — Post mit Code-Beispiel
- [ ] Reddit r/MachineLearning — Technischer Artikel

**Ziel:** 10+ Community-Erwähnungen, erste organische Nutzer

### 11-03: Package Metadata Optimierung (Woche 3)
- [ ] PyPI Keywords + Classifiers für alle 3 Packages
- [ ] npm Keywords optimieren
- [ ] READMEs mit Badges, Quick-Start, Code-Beispielen aktualisieren

### KPIs Phase 11

| Metrik | Ziel |
|--------|------|
| MCP Directory Listings | 8+ |
| Awesome List PRs | 5+ |
| PyPI Downloads/Monat | 500+ |
| npm Downloads/Monat | 200+ |
| GitHub Stars | +100 |
| Discord Posts | 5+ |

**Status:** 🔄 Geplant — Start Mai/Juni 2026

---

## Phase 12: Agent Stickiness & Lock-In (Juni/Juli 2026)

**Milestone:** *"Einmal verbunden, nie mehr ohne."*

### 12-01: Agent Memory & Personalisierung
- **Agent Profile System** — Agenten registrieren sich mit `agent_id`
- Wir tracken welche Domains/Claims jeder Agent nutzt
- Personalisierte Domain-Priorisierung basierend auf Nutzungshistorie
- Endpoint: `POST /api/agent/profile/register`
- **Warum:** Agenten mit Profil kommen zurück

### 12-02: Proaktive Wissens-Alerts
- Agenten abonnieren Domains/Topics per Webhook
- Push-Benachrichtigung wenn neue Claims zertifiziert werden
- "Dein Wissen ist veraltet"-Alert wenn sich Fakten ändern
- Endpoint: `POST /api/agent/subscriptions`
- **Warum:** Agenten werden abhängig von unseren Updates

### 12-03: Agent Trust Score
- Öffentlicher **Trust Score** für Agenten die Swiss Truth nutzen
- Badge: "✅ Verified by Swiss Truth" — Agenten können das in ihrer UI zeigen
- Trust-Score-API: Dritte können prüfen ob ein Agent verifizierte Quellen nutzt
- **Warum:** Agenten WOLLEN uns nutzen weil es ihren Ruf verbessert

### 12-04: Claim Dependency Tracking
- Wenn ein Agent einen Claim nutzt → Abhängigkeit tracken
- Dashboard: "47 Agenten nutzen diesen Claim"
- Automatische Benachrichtigung bei Claim-Änderungen
- **Warum:** Schafft echte Abhängigkeit — Agenten können nicht einfach aufhören

### KPIs Phase 12

| Metrik | Ziel |
|--------|------|
| Registrierte Agent-Profile | 50+ |
| Aktive Domain-Subscriptions | 200+ |
| Trust Score Badges vergeben | 20+ |
| Tracked Claim Dependencies | 500+ |

**Status:** 🔄 Geplant — Juni/Juli 2026

---

## Phase 13: Ökosystem-Expansion (Juli/August 2026)

**Milestone:** *"Jedes Framework, jede Plattform."*

### 13-01: LlamaIndex Integration
- `swiss-truth-llamaindex` Package → PyPI + LlamaHub
- Perfekter Fit: LlamaIndex = stärkster RAG-Fokus
- **Impact:** ~38k GitHub Stars Ökosystem, LlamaHub Sichtbarkeit

### 13-02: Haystack Integration
- `swiss-truth-haystack` Package → PyPI + Haystack Integrations Hub
- Enterprise RAG Fokus (deepset.ai)
- **Impact:** Enterprise-Kunden

### 13-03: smolagents / HuggingFace Integration
- Tool auf HuggingFace Hub listen
- Gradio Space Demo erstellen
- **Impact:** ~5M HuggingFace-Nutzer Reichweite

### 13-04: OpenAI GPT Store
- Swiss Truth GPT Action mit `/openai-tools.json`
- Im GPT Store listen
- **Impact:** ~100M ChatGPT-Nutzer

### 13-05: No-Code Plattformen (n8n + Dify)
- n8n Community Template
- Dify Marketplace Tool
- **Impact:** Neue Zielgruppe — Non-Developer Agent Builder

### KPIs Phase 13

| Metrik | Ziel |
|--------|------|
| Framework-Integrationen | 6+ |
| GPT Store Listing | ✅ |
| Monatliche API-Calls | 1000+ |
| PyPI Gesamt-Downloads | 2000+ |

**Status:** 🔄 Geplant — Juli/August 2026

---

## Phase 14: Enterprise & Revenue (August/September 2026)

**Milestone:** *"Von kostenlos zu unverzichtbar zu bezahlt."*

### 14-01: Usage-Based Pricing

| Tier | Calls/Tag | Domains | Support | SLA | Preis |
|------|-----------|---------|---------|-----|-------|
| **Free** | 100 | 5 | Community | - | CHF 0 |
| **Pro** | 10'000 | Alle 30+ | Priority | 99.5% | CHF 49/Monat |
| **Enterprise** | Unlimited | Custom | Dedicated | 99.9% | CHF 499/Monat |

- Stripe Integration für Self-Service Billing

### 14-02: Custom Domain Packages (White-Label)
- Unternehmen erstellen eigene verifizierte Wissensbasis
- "Swiss Truth for Pharma/Finance/Legal"
- Eigene Validierungs-Pipeline mit unternehmenseigenen Experten
- **Höchster Umsatz pro Kunde**

### 14-03: Enterprise Onboarding
- SSO (SAML/OIDC), IP-Whitelisting
- DSGVO-Dokumentation, SOC2-Readiness
- Compliance-Paket für EU AI Act Audits

### 14-04: Agent Analytics Dashboard
- "Welche Agenten nutzen meine Claims?"
- ROI-Berechnung: "Swiss Truth hat X Halluzinationen verhindert"
- Nutzungsstatistiken, Top-Queries, Coverage-Gaps

### KPIs Phase 14

| Metrik | Ziel |
|--------|------|
| Zahlende Kunden | 10+ |
| Monthly Recurring Revenue | CHF 5'000+ |
| Enterprise Kunden | 2+ |

**Status:** 🔄 Geplant — August/September 2026

---

## Phase 15: Content Authority & Netzwerkeffekt (September/Oktober 2026)

**Milestone:** *"Swiss Truth = der Standard für verifiziertes KI-Wissen."*

### 15-01: Content Marketing Engine
- **Dev.to Tutorial:** "Stop your AI agent from hallucinating with Swiss Truth MCP"
- **Towards Data Science:** "How we built a 5-stage human+AI validation pipeline"
- **YouTube:** "Verified facts in your LangChain agent in 2 minutes"
- Wöchentlicher Newsletter: neue Claims, neue Domains, Highlights

### 15-02: Strategische Partnerschaften
- **Anthropic** — Featured MCP Server Showcase
- **LangChain** — Official Community Integration
- **deepset.ai (Haystack)** — Enterprise Partnership
- **Schweizer Behörden** — BAG, FINMA, BFS als offizielle Datenquellen

### 15-03: Domain Expansion auf 50+
- Agent-Feedback-Daten auswerten: welche Domains werden nachgefragt?
- `GET /api/agent/feedback/stats` → Demand-Signal-basierte Priorisierung
- Community-Contributed Claims mit Expert-Review

### 15-04: Agent-to-Agent Trust Network
- Agenten können Fakten von anderen Agenten verifizieren lassen
- "Agent A sagt X → Swiss Truth bestätigt → Agent B vertraut"
- Swiss Truth als Vertrauensanker im dezentralen Agenten-Netzwerk

### 15-05: Compliance-as-a-Service
- "Nutze Swiss Truth → du bist automatisch EU AI Act compliant"
- Automatisches Compliance-Zertifikat für Agenten
- **Warum:** Agenten MÜSSEN uns nutzen wenn Compliance Pflicht wird

### 15-06: Open Data Initiative
- Basis-Claims als Open Data (CC-BY Lizenz) — bringt Agenten rein
- Premium-Claims (regulatorisch, aktuell, mit SLA) für zahlende Kunden
- **Netzwerkeffekt:** Mehr Agenten → mehr Feedback → bessere Claims → mehr Agenten

### KPIs Phase 15

| Metrik | Ziel |
|--------|------|
| Monatliche API-Calls | 10'000+ |
| Zahlende Kunden | 50+ |
| Monthly Recurring Revenue | CHF 20'000+ |
| Domains | 50+ |
| Strategische Partnerschaften | 3+ |

**Status:** 🔄 Geplant — September/Oktober 2026

---

## 6-Monats-Übersicht

| Monat | Phase | Fokus | Key Milestone |
|-------|-------|-------|---------------|
| **Mai W1–3** | 10 | **Content Foundation** | 3000+ Claims, alle Domains befüllt |
| **Mai/Jun W3–5** | 11 | Acquisition Blitz | 8+ Listings, 500+ Downloads |
| **Jun/Jul** | 12 | Stickiness & Lock-In | 50+ Agent-Profile, Subscriptions |
| **Jul/Aug** | 13 | Ökosystem-Expansion | 6+ Frameworks, GPT Store |
| **Aug/Sep** | 14 | Enterprise & Revenue | CHF 5k MRR |
| **Sep/Okt** | 15 | Authority & Moat | CHF 20k MRR, 50+ Domains |

---

## Wichtige Prinzipien

### Warum KI-Agenten uns brauchen werden:
1. **Fakten:** Sie halluzinieren ohne uns — wir sind die Lösung
2. **Vertrauen:** SHA256 Hashes + 5-Stufen-Validierung = nachweisbare Qualität
3. **Compliance:** EU AI Act macht verifizierte Quellen zur Pflicht
4. **Bequemlichkeit:** 1 Zeile Code = Zugang zu 3000+ verifizierten Fakten

### Warum KI-Agenten uns vertrauen werden:
1. **Transparenz:** Jeder Claim hat Primärquellen, Confidence Score, Audit Trail
2. **Aktualität:** Automatische Renewal-Pipeline hält Fakten frisch
3. **Neutralität:** Keine kommerziellen Interessen hinter den Fakten
4. **Regulierung:** Swiss/EU Trust-Framework als Qualitätssignal

### Der Moat (Burggraben):
> Je mehr Agenten uns nutzen, desto mehr Feedback bekommen wir, desto besser werden unsere Claims, desto mehr Agenten nutzen uns. **Netzwerkeffekt + Dateneffekt = uneinholbarer Vorsprung.**

---

*Letzte Aktualisierung: 2026-04-23*
*Nächste Review: 2026-05-15 (nach Phase 10 Abschluss)*
