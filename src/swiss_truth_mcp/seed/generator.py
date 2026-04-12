"""
swiss-truth-generate — Pareto-optimierter KI-Agenten-Claim-Generator

Strategie (80/20-Prinzip):
  Phase 1  Pareto-Analyse: Welche 20% der Fragen decken 80% aller Agenten-Anfragen?
           → Zapft offizielle Quellen an (admin.ch, Wikipedia-API, etc.)
           → Claude identifiziert Hochfrequenz-Fragen mit Halluzinations-Risiko
  Phase 2  Antwort-Generierung: Für jede Frage einen präzisen, verifizierten Claim
           → Dual-Format: question + text (verbessert Vektor-Retrieval massiv)

Quell-Typen (erweiterbar):
  faq_urls    — Statische HTML-Seiten (admin.ch, bag.admin.ch, snb.ch, ...)
  wiki_topics — Wikipedia-API (JSON, kein JS-Rendering nötig, mehrsprachig)
  wiki_lang   — Wikipedia-Sprache (Standard: "de")

Neue Domain hinzufügen:
  1. Eintrag in DOMAINS mit name, description, topics
  2. faq_urls und/oder wiki_topics setzen
  3. swiss-truth-generate --domain meine-domain --count 25

Verwendung:
  swiss-truth-generate --domain swiss-health --count 25
  swiss-truth-generate --domain swiss-law --count 50 --import
  swiss-truth-generate --list-domains
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

import anthropic
import httpx

from swiss_truth_mcp.config import settings

SEED_DIR = Path(__file__).parent

# ─── Domain-Definitionen ─────────────────────────────────────────────────────

# ─── Primärquellen pro Domain ────────────────────────────────────────────────
# Wird in den Claim-Prompts injiziert: Claude muss aus DIESEN Quellen zitieren.
# Wikipedia ist explizit NICHT erlaubt als source_url — nur als interner Kontext.

DOMAIN_PRIMARY_SOURCES = {
    "swiss-health": [
        "bag.admin.ch (Bundesamt für Gesundheit)",
        "swissmedic.ch (Heilmittelbehörde)",
        "bfs.admin.ch (Bundesamt für Statistik)",
        "santesuisse.ch (Branchenverband Krankenversicherer)",
        "ksgr.ch / spitalverband.ch (Spitäler)",
        "fedlex.admin.ch (Gesetzestexte KVG/KVV)",
    ],
    "swiss-law": [
        "fedlex.admin.ch (Bundesrecht: OR, ZGB, StGB, BV)",
        "bj.admin.ch (Bundesamt für Justiz)",
        "bger.ch (Bundesgericht — Entscheide)",
        "bsv.admin.ch (Bundesamt für Sozialversicherungen)",
        "mietrecht.ch (Mieterinnen- und Mieterverbände)",
    ],
    "swiss-finance": [
        "snb.ch (Schweizerische Nationalbank — Berichte, Statistiken)",
        "finma.ch (FINMA — Regulierung und Rundschreiben)",
        "estv.admin.ch (Eidg. Steuerverwaltung)",
        "six-group.com (SIX Swiss Exchange)",
        "bsv.admin.ch (AHV/IV/EO/ALV Statistiken)",
        "bfs.admin.ch (Bundesamt für Statistik)",
    ],
    "swiss-education": [
        "sbfi.admin.ch (Staatssekretariat für Bildung, Forschung und Innovation)",
        "edk.ch (Schweizerische Konferenz der kantonalen Erziehungsdirektoren)",
        "ethz.ch / epfl.ch (ETH-Bereich)",
        "bfs.admin.ch (Bildungsstatistiken)",
        "pisa.oecd.org (PISA-Studien)",
    ],
    "swiss-energy": [
        "bfe.admin.ch (Bundesamt für Energie — Statistiken, Berichte)",
        "swissgrid.ch (Nationaler Übertragungsnetzbetreiber)",
        "bfs.admin.ch (Energiestatistik)",
        "ensi.ch (Eidg. Nuklearsicherheitsinspektorat)",
        "uvek.admin.ch (Departement Umwelt, Verkehr, Energie)",
    ],
    "swiss-transport": [
        "bav.admin.ch (Bundesamt für Verkehr)",
        "astra.admin.ch (Bundesamt für Strassen)",
        "sbb.ch/media (SBB Medienmitteilungen und Fakten)",
        "bazl.admin.ch (Bundesamt für Zivilluftfahrt)",
        "bfs.admin.ch (Verkehrsstatistiken)",
    ],
    "swiss-politics": [
        "admin.ch (Bundesrat und Bundesverwaltung)",
        "parlament.ch (Bundesversammlung — Abstimmungen, Protokolle)",
        "bk.admin.ch (Bundeskanzlei — Volksrechte, Abstimmungen)",
        "bfs.admin.ch (Wahlstatistiken)",
        "fedlex.admin.ch (Bundesverfassung BV)",
    ],
    "swiss-agriculture": [
        "blw.admin.ch (Bundesamt für Landwirtschaft — Agrarbericht)",
        "bio-suisse.ch (Bio Suisse Richtlinien)",
        "bfs.admin.ch (Landwirtschaftsstatistiken)",
        "agroscope.admin.ch (Forschung Agroscope)",
        "bio-inspecta.ch / fibl.org (Forschungsinstitut Biologischer Landbau)",
    ],
    "climate": [
        "ipcc.ch / ipcc.ch/report (IPCC-Berichte — AR5, AR6)",
        "bafu.admin.ch (Bundesamt für Umwelt)",
        "meteoswiss.admin.ch (MeteoSchweiz Klimadaten)",
        "noaa.gov (US-Ozean- und Atmosphärenbehörde)",
        "nasa.gov/climate (NASA Klimadaten)",
        "nature.com / science.org (Peer-reviewed Journals)",
        "unfccc.int (UN-Klimarahmenkonvention)",
    ],
    "ai-ml": [
        "arxiv.org (Preprint-Server: cs.LG, cs.CL, cs.CV)",
        "neurips.cc (NeurIPS Conference Proceedings)",
        "icml.cc (ICML Conference Proceedings)",
        "openreview.net (ICLR Papers)",
        "anthropic.com/research (Anthropic Research)",
        "openai.com/research (OpenAI Research)",
        "deepmind.google/research (DeepMind Research)",
        "huggingface.co/papers (Paper-Aggregator)",
        "nature.com/natmachintell (Nature Machine Intelligence)",
    ],
    "world-science": [
        "arxiv.org (Preprint-Server: physics, quant-ph, math, bio)",
        "pubmed.ncbi.nlm.nih.gov (PubMed — Biomedizin)",
        "nature.com / science.org (Top-Journals)",
        "royalsociety.org (Royal Society Publications)",
        "nobelprize.org (Nobel-Preisträger und Erklärungen)",
        "mpg.de (Max-Planck-Gesellschaft)",
        "cern.ch (CERN — Teilchenphysik)",
        "ncbi.nlm.nih.gov (NCBI — Genomik, Biologie)",
    ],
    "world-history": [
        "bpb.de (Bundeszentrale für politische Bildung)",
        "dhm.de (Deutsches Historisches Museum)",
        "un.org/history (Vereinte Nationen Archiv)",
        "britannica.com (Encyclopaedia Britannica — anerkannte Referenz)",
        "jstor.org (Wissenschaftliche Historikerjournale)",
        "europeana.eu (Europäisches Kulturerbe-Portal)",
        "loc.gov (Library of Congress)",
        "histsoc.org / historicalreview.org (Historische Gesellschaften)",
    ],
    # ── Europäische / Globale Domains ────────────────────────────────────────
    "eu-law": [
        "eur-lex.europa.eu (EU Official Journal & Legislation)",
        "ec.europa.eu (European Commission — Regulations & Directives)",
        "gdpr-info.eu / cnil.fr (GDPR resources)",
        "digital-strategy.ec.europa.eu (EU AI Act, Digital Markets Act)",
        "europarl.europa.eu (European Parliament)",
        "curia.europa.eu (Court of Justice of the EU — Rulings)",
        "edpb.europa.eu (European Data Protection Board)",
    ],
    "eu-health": [
        "ema.europa.eu (European Medicines Agency)",
        "ecdc.europa.eu (European Centre for Disease Prevention and Control)",
        "who.int (World Health Organization)",
        "ec.europa.eu/health (European Commission — Health Policy)",
        "efsa.europa.eu (European Food Safety Authority)",
        "eurosurveillance.org (Peer-reviewed EU epidemiology journal)",
    ],
    "global-science": [
        "pubmed.ncbi.nlm.nih.gov (PubMed — biomedical literature)",
        "arxiv.org (Preprint server — physics, math, bio, CS)",
        "nature.com / science.org (Top peer-reviewed journals)",
        "thelancet.com / nejm.org (Medical journals)",
        "nih.gov (National Institutes of Health)",
        "who.int (WHO — global health data)",
        "cell.com (Cell Press journals)",
        "royalsociety.org (Royal Society Publications)",
    ],
}

DOMAINS = {
    # ── Schweizer Domains (admin.ch / Bundesbehörden) ─────────────────────────
    "swiss-health": {
        "name": "Schweizer Gesundheitswesen",
        "description": "Medizinische Leitlinien, KVG, Krankenkassen und Gesundheitsstatistiken der Schweiz",
        "topics": [
            "KVG (Krankenversicherungsgesetz)", "Krankenkassenprämien und Kantonsunterschiede",
            "Spitalfinanzierung und DRG", "Swissmedic und Medikamentenzulassung",
            "Lebenserwartung Schweiz", "Hausarztmangel und Versorgung",
            "Elektronisches Patientendossier (EPD)", "Pflegefinanzierung",
            "Diabetes und chronische Krankheiten Schweiz", "Suchtproblematik und Prävention",
        ],
        "faq_urls": [
            "https://www.bag.admin.ch/bag/de/home/versicherungen/krankenversicherung/krankenversicherung-versicherte-mit-wohnsitz-in-der-schweiz.html",
            "https://www.bag.admin.ch/bag/de/home/versicherungen/krankenversicherung/krankenversicherung-leistungen-tarife/Leistungen.html",
        ],
        "wiki_topics": ["Krankenversicherung in der Schweiz"],
    },
    "swiss-law": {
        "name": "Schweizer Recht",
        "description": "Gesetze, Rechtsgrundsätze und Institutionen des Schweizer Rechtssystems",
        "topics": [
            "Bundesverfassung (BV) Grundrechte", "Obligationenrecht (OR) Vertragsrecht",
            "Strafgesetzbuch (StGB) Grundsätze", "Zivilgesetzbuch (ZGB) Familienrecht",
            "Mietrecht und Wohnungsrecht", "Datenschutzgesetz (DSG/nDSG)",
            "Bundesgericht als oberste Instanz", "Direkte Demokratie und Volksrechte",
            "Erbrecht Schweiz", "Arbeitsrecht und Kündigungsschutz",
        ],
        "faq_urls": [
            "https://www.bj.admin.ch/bj/de/home/wirtschaft/mietrecht.html",
            "https://www.bj.admin.ch/bj/de/home/wirtschaft/vertragsrecht.html",
        ],
        "wiki_topics": ["Obligationenrecht (Schweiz)", "Mietrecht (Schweiz)"],
    },
    "swiss-finance": {
        "name": "Schweizer Finanzmarkt",
        "description": "Finanzplatz Schweiz, SNB, Banken, Börse und Regulierung",
        "topics": [
            "Schweizerische Nationalbank (SNB) Mandat", "FINMA Bankenregulierung",
            "SIX Swiss Exchange", "Too-big-to-fail und Bankenregulierung",
            "Schweizer Franken als Fluchtwährung", "3-Säulen-Pensionssystem",
            "Goldreserven der SNB", "Negativzinsen und Geldpolitik",
            "Hedge Funds und Asset Management", "Bankgeheimnis Entwicklung",
        ],
        "faq_urls": [
            "https://www.snb.ch/de/the-snb/mandates-goals",
            "https://www.estv.admin.ch/estv/de/home/mehrwertsteuer/grundlagen/steuersaetze.html",
        ],
        "wiki_topics": ["Schweizerische Nationalbank", "Drei-Säulen-System (Schweiz)"],
    },
    "swiss-education": {
        "name": "Schweizer Bildungssystem",
        "description": "Bildungsstruktur, Hochschulen, Berufsbildung und Bildungsstatistiken der Schweiz",
        "topics": [
            "Maturität und Gymnasien", "Duales Berufsbildungssystem (Lehre)",
            "ETH Zürich und EPFL", "Hochschullandschaft (Universitäten, FH, PH)",
            "Schulpflicht und Volksschule", "PISA-Ergebnisse der Schweiz",
            "Bildungsausgaben", "Bologna-Reform", "Sprachregionen und Bildung",
            "Weiterbildung und Erwachsenenbildung",
        ],
        "faq_urls": [
            "https://www.sbfi.admin.ch/sbfi/de/home/bildung/berufsbildung.html",
            "https://www.sbfi.admin.ch/sbfi/de/home/bildung/maturitaet.html",
        ],
        "wiki_topics": ["Bildungssystem der Schweiz", "Berufliche Grundbildung (Schweiz)"],
    },
    "swiss-energy": {
        "name": "Schweizer Energie",
        "description": "Energieproduktion, -verbrauch, Kernkraft, Wasserkraft und Energiestrategie der Schweiz",
        "topics": [
            "Kernkraftwerke (Gösgen, Leibstadt, Beznau)", "Wasserkraft (57% Stromproduktion)",
            "Energiestrategie 2050", "Solarenergie Ausbau",
            "Stromimporte/-exporte", "CO₂-Abgabe und Lenkungsabgaben",
            "Fernwärme und Gebäudeheizung", "Elektromobilität",
            "Energieverbrauch pro Kopf", "Netzinfrastruktur Swissgrid",
        ],
        "faq_urls": [
            "https://www.bfe.admin.ch/bfe/de/home/politik/energiestrategie-2050.html",
            "https://www.bfe.admin.ch/bfe/de/home/versorgung/statistik-und-geodaten/energiestatistiken.html",
        ],
        "wiki_topics": ["Energiestrategie 2050 (Schweiz)", "Kernkraftwerk in der Schweiz"],
    },
    "swiss-transport": {
        "name": "Schweizer Verkehr",
        "description": "Bahn, Strasse, Luftfahrt und öffentlicher Verkehr in der Schweiz",
        "topics": [
            "SBB und öffentlicher Verkehr", "NEAT / Gotthard-Basistunnel",
            "Autobahnvignette und Nationalstrassen", "Flughafen Zürich",
            "Velowegnetz und Langsamverkehr", "Strassengebühren und LSVA",
            "Pendlerverkehr und Stau", "GA und Halbtax",
            "Schienennetz und Pünktlichkeit", "Mobility-Sharing",
        ],
        "faq_urls": [
            "https://www.bav.admin.ch/bav/de/home/das-bav/aufgaben-des-bav.html",
            "https://www.astra.admin.ch/astra/de/home/themen/nationalstrassen.html",
        ],
        "wiki_topics": ["Schweizerische Bundesbahnen", "Gotthard-Basistunnel"],
    },
    "swiss-politics": {
        "name": "Schweizer Politik",
        "description": "Politisches System, Bundesrat, Parlament und direkte Demokratie der Schweiz",
        "topics": [
            "Bundesrat (7 Mitglieder, Kollegialitätsprinzip)", "Nationalrat und Ständerat",
            "Volksinitiative und Referendum", "Konkordanzdemokratie",
            "Parteiensystem (SP, SVP, FDP, Mitte, Grüne)", "Bundesversammlung",
            "Kantonsregierungen", "Volksabstimmungen und Abstimmungsquoten",
            "Proporzwahlrecht", "Bundesgericht und Justiz",
        ],
        "faq_urls": [
            "https://www.admin.ch/gov/de/start/bundesrat.html",
            "https://www.parlament.ch/de/%C3%BCber-das-parlament/parlamentsportr%C3%A4t",
        ],
        "wiki_topics": ["Politisches System der Schweiz", "Volksinitiative (Schweiz)"],
    },
    "swiss-agriculture": {
        "name": "Schweizer Landwirtschaft",
        "description": "Landwirtschaft, Lebensmittelproduktion und Agrarpolitik der Schweiz",
        "topics": [
            "Direktzahlungen und Agrarpolitik", "Bio-Landwirtschaft Schweiz",
            "Selbstversorgungsgrad", "Milchwirtschaft und Käseproduktion",
            "Berglandwirtschaft", "IP-SUISSE und Qualitätslabels",
            "Weinbau", "Pflanzenschutzmittel-Regulierung",
            "Bodenrecht und Pachtland", "Tierwohl-Standards",
        ],
        "faq_urls": [
            "https://www.blw.admin.ch/blw/de/home/politik/agrarpolitik.html",
            "https://www.blw.admin.ch/blw/de/home/nachhaltige-produktion/biologische-landwirtschaft.html",
        ],
        "wiki_topics": ["Landwirtschaft in der Schweiz"],
    },
    # ── Internationale / Wissenschaftliche Domains (Wikipedia-API) ────────────
    "climate": {
        "name": "Klimawissenschaft",
        "description": "Wissenschaftlicher Konsens zu Klimawandel, CO₂ und Umwelt",
        "topics": [
            "CO₂-Konzentration und Treibhauseffekt", "Globale Temperaturentwicklung",
            "Meeresspiegel und Eisschmelze", "IPCC-Berichte und Klimamodelle",
            "Kipppunkte im Klimasystem", "Erneuerbare Energien weltweit",
            "Paris-Abkommen und Klimaziele", "Extremwetterereignisse",
            "Permafrost und Methanemissionen", "CO₂-Senken (Wälder, Ozeane)",
        ],
        "faq_urls": [
            "https://www.bafu.admin.ch/bafu/de/home/themen/klima/fachinformationen/klimaentwicklung.html",
        ],
        "wiki_topics": ["Klimawandel", "Pariser Abkommen", "Treibhauseffekt"],
    },
    "ai-ml": {
        "name": "AI/ML",
        "description": "Definitionen, Konzepte und Fakten zu Künstlicher Intelligenz und Machine Learning",
        "topics": [
            "Large Language Models (GPT, Claude, Gemini)", "Transformer-Architektur",
            "Reinforcement Learning from Human Feedback (RLHF)", "Neural Networks Grundlagen",
            "Computer Vision und Bildverarbeitung", "Natural Language Processing",
            "Overfitting und Regularisierung", "Gradient Descent und Optimierung",
            "AI-Ethik und Bias", "Embeddings und Vektorräume",
        ],
        "faq_urls": [],
        "wiki_topics": [
            "Großes Sprachmodell", "Maschinelles Lernen",
            "Transformer (Maschinelles Lernen)", "Neuronales Netz",
        ],
        "wiki_lang": "de",
    },
    "world-science": {
        "name": "Naturwissenschaften",
        "description": "Grundlagen der Physik, Chemie, Biologie und Mathematik",
        "topics": [
            "Relativitätstheorie (Einstein)", "Quantenmechanik Grundlagen",
            "Periodensystem und Elemente", "DNA und Genetik",
            "Evolution und natürliche Selektion", "Thermodynamik",
            "Elektromagnetismus", "Newtonsche Mechanik",
            "Zelluläre Biologie", "Mathematische Grundsätze",
        ],
        "faq_urls": [],
        "wiki_topics": [
            "Relativitätstheorie", "Quantenmechanik",
            "Desoxyribonukleinsäure", "Evolution",
        ],
        "wiki_lang": "de",
    },
    "world-history": {
        "name": "Weltgeschichte",
        "description": "Wichtige historische Ereignisse und Entwicklungen der Weltgeschichte",
        "topics": [
            "Französische Revolution", "Industrielle Revolution",
            "Erster und Zweiter Weltkrieg", "Kalter Krieg",
            "Römisches Reich", "Entdeckungszeitalter",
            "Aufklärung", "Dekolonisierung",
            "UNO-Gründung", "Digitale Revolution",
        ],
        "faq_urls": [],
        "wiki_topics": [
            "Französische Revolution", "Erster Weltkrieg",
            "Zweiter Weltkrieg", "Kalter Krieg",
        ],
        "wiki_lang": "de",
    },
    # ── Europäische / Globale Domains ────────────────────────────────────────
    "eu-law": {
        "name": "EU Law & Regulation",
        "description": "European Union legislation, GDPR, AI Act, Digital Markets Act, and EU court rulings",
        "topics": [
            "GDPR (General Data Protection Regulation) — key rights and obligations",
            "EU AI Act — risk categories and compliance requirements",
            "Digital Markets Act (DMA) — gatekeeper obligations",
            "Digital Services Act (DSA) — platform liability",
            "EU competition law and antitrust enforcement",
            "Court of Justice of the EU (CJEU) — landmark rulings",
            "EU Charter of Fundamental Rights",
            "European Arrest Warrant",
            "EU product liability and consumer protection",
            "Schengen Area — rules and member states",
        ],
        "faq_urls": [
            "https://digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai",
            "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32016R0679",
        ],
        "wiki_topics": ["General Data Protection Regulation", "AI Act"],
        "wiki_lang": "en",
    },
    "eu-health": {
        "name": "EU & Global Health",
        "description": "European Medicines Agency, WHO guidelines, EU health policy, and global epidemiology",
        "topics": [
            "European Medicines Agency (EMA) — drug approval process",
            "WHO essential medicines list",
            "EU vaccination schedules and recommendations",
            "ECDC disease surveillance — key findings",
            "Antimicrobial resistance (AMR) — WHO data",
            "EU health data space regulation",
            "One Health approach (WHO/EU)",
            "Global disease burden — WHO statistics",
            "Pandemic preparedness — EU Health Union",
            "EFSA food safety standards",
        ],
        "faq_urls": [
            "https://www.ema.europa.eu/en/about-us/what-we-do/authorisation-medicines",
            "https://www.who.int/news-room/fact-sheets",
        ],
        "wiki_topics": ["European Medicines Agency", "World Health Organization"],
        "wiki_lang": "en",
    },
    "global-science": {
        "name": "Global Science",
        "description": "Peer-reviewed scientific findings across medicine, biology, physics, and interdisciplinary research",
        "topics": [
            "mRNA vaccine technology — mechanism and efficacy",
            "CRISPR-Cas9 — gene editing applications",
            "Cancer immunotherapy — checkpoint inhibitors",
            "Antibiotic resistance mechanisms",
            "Alzheimer's disease — current understanding",
            "Quantum computing — current state and limitations",
            "Microbiome and human health",
            "Stem cell therapy — approved and experimental",
            "Drug development pipeline — phases and approval rates",
            "Global burden of disease — GBD study findings",
        ],
        "faq_urls": [
            "https://www.nih.gov/research-training/research-resources",
            "https://www.who.int/data/gho",
        ],
        "wiki_topics": [
            "CRISPR", "mRNA vaccine", "Quantum computing",
        ],
        "wiki_lang": "en",
    },
}

# ─── Prompts ─────────────────────────────────────────────────────────────────

SYSTEM_PROMPT_PARETO = """Du bist ein Experte für KI-Agenten-Anfragen und Wissensmanagement.
Deine Aufgabe: Identifiziere die häufigsten und wichtigsten Fragen, die KI-Agenten
zu einem bestimmten Thema stellen — mit Fokus auf das Pareto-Prinzip (80/20-Regel).

Priorisiere Fragen nach:
1. Häufigkeit (wird diese Frage oft gestellt?)
2. Halluzinations-Risiko (machen Agenten hier oft Fehler?)
3. Schweizer Spezifik (wird häufig deutsches/EU-Recht verwechselt?)
4. Aktualität (gibt es neuere Fakten die Agenten nicht kennen?)

Antworte IMMER nur mit validem JSON. Kein erklärender Text."""

SYSTEM_PROMPT_CLAIMS = """Du bist ein präziser Fakten-Kurator für Swiss Truth, eine neutrale,
maschinenlesbare Wissensplattform für KI-Agenten.

Deine Aufgabe: Generiere faktisch korrekte, verifizierbare Claim-Antworten auf
häufige KI-Agenten-Fragen. Das Dual-Format (Frage + Antwort) ist entscheidend für
optimales semantisches Retrieval.

PFLICHTREGELN:
- "question": exakt die gestellte Frage — unverändert übernehmen
- "text": direkte, faktisch korrekte Antwort (1-3 Sätze, enthält konkrete Zahlen/Regelungen)
- Keine Meinungen, keine Prognosen — ausschliesslich belegbare Fakten
- confidence_score: 0.95–0.99 sehr gut belegt, 0.90–0.94 solide belegt

QUELLEN — STRENGE REGELN:
- source_urls: NUR Primärquellen — offizielle Behörden, Peer-reviewed Journals, Forschungsinstitute
- Wikipedia ist VERBOTEN als source_url — es ist eine Sekundärquelle
- Wenn Wikipedia als Kontext genutzt wurde: folge den dort genannten Primärquellen und zitiere diese
- Prüfe ob die URL plausibel ist (korrekte Domain, keine erfundenen Pfade)
- Mindestens 1 URL, max. 2 URLs pro Claim

Antworte IMMER nur mit validem JSON-Array. Kein erklärender Text."""


# ─── Web-Fetcher (Swiss FAQ Sources) ─────────────────────────────────────────

def _extract_text(html: str) -> str:
    """Extrahiert lesbaren Text aus HTML (ohne externe Bibliotheken)."""
    # Scripts, Styles, Nav entfernen
    html = re.sub(
        r'<(script|style|nav|header|footer|aside)[^>]*>.*?</\1>',
        '', html, flags=re.DOTALL | re.IGNORECASE,
    )
    # Tags entfernen
    text = re.sub(r'<[^>]+>', ' ', html)
    # HTML-Entities dekodieren
    entities = {
        '&amp;': '&', '&lt;': '<', '&gt;': '>', '&nbsp;': ' ',
        '&auml;': 'ä', '&ouml;': 'ö', '&uuml;': 'ü',
        '&Auml;': 'Ä', '&Ouml;': 'Ö', '&Uuml;': 'Ü',
        '&#8211;': '–', '&#8212;': '—', '&#8230;': '…',
        '&szlig;': 'ß', '&eacute;': 'é', '&agrave;': 'à',
    }
    for entity, char in entities.items():
        text = text.replace(entity, char)
    # Whitespace normalisieren
    text = re.sub(r'\s+', ' ', text).strip()
    return text


async def fetch_html_pages(urls: list[str], max_chars_per_url: int = 2500) -> str:
    """
    Ruft statische HTML-Seiten ab (admin.ch, bag.admin.ch, snb.ch, etc.).
    Funktioniert mit server-gerendertem HTML — nicht für JS-SPAs geeignet.
    """
    if not urls:
        return ""

    snippets: list[str] = []
    headers = {
        "User-Agent": "SwissTruthBot/1.0 (swiss-truth knowledge validator; contact@swisstruth.org)",
        "Accept-Language": "de-CH,de;q=0.9",
    }

    async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
        for url in urls[:3]:
            try:
                r = await client.get(url, headers=headers)
                if r.status_code == 200:
                    text = _extract_text(r.text)[:max_chars_per_url]
                    if len(text) > 200:
                        snippets.append(f"[Quelle: {url}]\n{text}")
                        print(f"    ✓ HTML: {url} ({len(text)} Zeichen)")
                    else:
                        print(f"    ⚠ Zu wenig Inhalt: {url}")
                else:
                    print(f"    ✗ HTTP {r.status_code}: {url}")
            except Exception as e:
                print(f"    ✗ Fehler bei {url}: {type(e).__name__}")

    return "\n\n".join(snippets)


async def fetch_wikipedia_extracts(
    topics: list[str],
    lang: str = "de",
    max_chars_per_topic: int = 1500,
) -> str:
    """
    Ruft Wikipedia-Artikel-Einleitungen via MediaWiki-API ab.
    Gibt plain text zurück — kein JS-Rendering, keine Scraping-Probleme.
    Funktioniert für beliebige Wikipedia-Sprachen und Themen.

    Neue Domain hinzufügen: einfach wiki_topics in der Domain-Config setzen.
    """
    if not topics:
        return ""

    snippets: list[str] = []
    api_url = f"https://{lang}.wikipedia.org/w/api.php"

    async with httpx.AsyncClient(timeout=10.0) as client:
        for topic in topics[:5]:
            try:
                r = await client.get(api_url, params={
                    "action":         "query",
                    "titles":         topic,
                    "prop":           "extracts",
                    "exintro":        "1",
                    "explaintext":    "1",
                    "exsectionformat":"plain",
                    "format":         "json",
                    "redirects":      "1",
                })
                if r.status_code == 200:
                    data = r.json()
                    pages = data.get("query", {}).get("pages", {})
                    for page in pages.values():
                        if page.get("pageid", -1) == -1:
                            print(f"    ⚠ Wikipedia: Kein Artikel für '{topic}'")
                            continue
                        extract = page.get("extract", "")[:max_chars_per_topic]
                        if extract:
                            title = page.get("title", topic)
                            snippets.append(f"[Wikipedia ({lang}): {title}]\n{extract}")
                            print(f"    ✓ Wikipedia: {title} ({len(extract)} Zeichen)")
            except Exception as e:
                print(f"    ✗ Wikipedia-Fehler für '{topic}': {type(e).__name__}")

    return "\n\n".join(snippets)


async def fetch_source_content(domain: dict) -> str:
    """
    Kombiniert alle Quell-Typen einer Domain:
      - faq_urls    → statische HTML-Seiten (admin.ch, bag.admin.ch, ...)
      - wiki_topics → Wikipedia-API (für internationale / wissenschaftliche Domains)

    Erweiterbar: neue Quell-Typen können hier ergänzt werden.
    """
    html_content  = await fetch_html_pages(domain.get("faq_urls", []))
    wiki_content  = await fetch_wikipedia_extracts(
        domain.get("wiki_topics", []),
        lang=domain.get("wiki_lang", "de"),
    )
    parts = [p for p in [html_content, wiki_content] if p]
    return "\n\n".join(parts)


# Legacy-Alias für Rückwärtskompatibilität
async def fetch_faq_content(urls: list[str], max_chars_per_url: int = 2500) -> str:
    return await fetch_html_pages(urls, max_chars_per_url)


# ─── Phase 1: Pareto-Fragen generieren ───────────────────────────────────────

async def generate_pareto_questions(
    domain_id: str,
    count: int,
    faq_context: str,
    model: str = "claude-sonnet-4-5",
) -> list[dict]:
    """
    Phase 1: Identifiziert die wichtigsten Agenten-Fragen nach dem 80/20-Prinzip.
    Gibt eine priorisierte Liste von Fragen zurück.
    """
    domain = DOMAINS[domain_id]
    topics_str = "\n".join(f"  - {t}" for t in domain["topics"])

    context_section = ""
    if faq_context:
        context_section = f"""
Kontext aus offiziellen Schweizer Quellen (nutze diese Fakten als Orientierung):
---
{faq_context[:4000]}
---
"""

    prompt = f"""Analysiere, welche Fragen KI-Agenten am häufigsten über "{domain['name']}" stellen.

Domain-Beschreibung: {domain['description']}

Relevante Themen:
{topics_str}
{context_section}
Wende das Pareto-Prinzip an: Identifiziere die {count} wichtigsten Fragen,
die zusammen ~80% aller Agenten-Anfragen zu diesem Thema abdecken.

Priorisiere nach:
1. Zahlen, Beträge, Schwellenwerte, Fristen (KI halluziniert hier am meisten)
2. Schweizer Besonderheiten die von deutschem/EU-Recht abweichen
3. Häufige Missverständnisse und Irrtümer
4. Änderungen nach 2022 (fehlt in Trainings-Daten vieler Agenten)
5. Verfahren und Zuständigkeiten (Wer ist verantwortlich für was?)

Sortiere die Fragen nach Wichtigkeit (wichtigste zuerst).

Antworte NUR als JSON-Array:
[
  {{
    "question": "Präzise Frage auf Deutsch",
    "category": "zahlen|recht|verfahren|institution|aktuell|irrtum",
    "hallucination_risk": "high|medium"
  }}
]"""

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=SYSTEM_PROMPT_PARETO,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    try:
        questions = json.loads(raw)
        return questions[:count]
    except json.JSONDecodeError as e:
        print(f"    ⚠ JSON-Fehler in Phase 1: {e} — versuche Reparatur")
        try:
            questions = json.loads(raw + "]")
            return questions[:count]
        except Exception:
            print("    ✗ Phase 1 fehlgeschlagen — nutze Themen als Fallback")
            return []


# ─── Phase 2: Claims aus Fragen generieren ───────────────────────────────────

async def generate_claims_from_questions(
    domain_id: str,
    questions: list[dict],
    faq_context: str,
    model: str = "claude-sonnet-4-5",
) -> list[dict]:
    """
    Phase 2: Für jede Pareto-Frage wird ein präziser, verifizierbarer Claim generiert.
    Dual-Format: question + text → optimiert Vektor-Retrieval massiv.
    """
    if not questions:
        return []

    domain = DOMAINS[domain_id]
    batch_size = 20  # Kleinere Batches für höhere Antwortqualität
    all_claims: list[dict] = []
    batches = (len(questions) + batch_size - 1) // batch_size

    context_section = ""
    if faq_context:
        context_section = f"""
Recherche-Kontext (nur zur Orientierung — NICHT als source_url zitieren, kein Wikipedia):
---
{faq_context[:3000]}
---
"""

    primary_sources = DOMAIN_PRIMARY_SOURCES.get(domain_id, [])
    sources_str = "\n".join(f"  - {s}" for s in primary_sources)

    for batch_num in range(batches):
        start = batch_num * batch_size
        batch_questions = questions[start:start + batch_size]

        questions_str = json.dumps(
            [q["question"] for q in batch_questions],
            ensure_ascii=False, indent=2,
        )

        prompt = f"""Für jede der folgenden häufigen KI-Agenten-Fragen zur Domain "{domain['name']}"
generiere einen präzisen, verifizierten Claim als direkte Antwort.
{context_section}
Akzeptierte Primärquellen für source_urls (KEINE anderen, KEIN Wikipedia):
{sources_str}

Fragen (Batch {batch_num + 1}/{batches}):
{questions_str}

Pflichtformat:
- "question": exakt die Frage aus der Liste (unverändert!)
- "text": direkte faktische Antwort mit konkreten Zahlen/Regelungen (1-3 Sätze)
- "domain_id": "{domain_id}"
- "language": "de"
- "confidence_score": 0.95-0.99 für sehr gut belegte Fakten, 0.90-0.94 für solide
- "source_urls": 1-2 reale URLs ausschliesslich aus den akzeptierten Primärquellen (KEIN Wikipedia)
- "validators": [{{"name": "Swiss Truth Team", "institution": "Swiss Truth Foundation"}}]

Antworte NUR mit dem JSON-Array, kein Text davor oder danach."""

        print(f"    Batch {batch_num + 1}/{batches} ({len(batch_questions)} Fragen)...", end=" ", flush=True)

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model=model,
            max_tokens=8192,
            system=SYSTEM_PROMPT_CLAIMS,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = response.content[0].text.strip()
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        try:
            batch_claims = json.loads(raw)
            all_claims.extend(batch_claims)
            print(f"✓ ({len(batch_claims)} Claims)")
        except json.JSONDecodeError as e:
            print(f"⚠ JSON-Fehler: {e}")
            try:
                batch_claims = json.loads(raw + "]")
                all_claims.extend(batch_claims)
                print(f"   Repariert: {len(batch_claims)} Claims")
            except Exception:
                print(f"   Batch übersprungen.")

    return all_claims


# ─── Fallback: Topic-basierte Generierung (Legacy) ───────────────────────────

async def _generate_claims_legacy(
    domain_id: str,
    count: int,
    model: str,
) -> list[dict]:
    """Fallback falls Phase 1 fehlschlägt — generiert ohne Pareto-Vorfilter."""
    domain = DOMAINS[domain_id]
    topics_str = "\n".join(f"  - {t}" for t in domain["topics"])

    prompt = f"""Generiere exakt {count} Claims für die Domain "{domain['name']}".
Beschreibung: {domain['description']}

Themen:
{topics_str}

Format — jeder Claim hat DIESE Felder:
{{
  "question": "Die häufigste KI-Agenten-Frage zu diesem Fact",
  "text": "Faktisch korrekte Antwort (1-3 Sätze, mit konkreten Zahlen/Regelungen)",
  "domain_id": "{domain_id}",
  "language": "de",
  "confidence_score": 0.97,
  "source_urls": ["https://..."],
  "validators": [{{"name": "Swiss Truth Team", "institution": "Swiss Truth Foundation"}}]
}}

Antworte NUR mit dem JSON-Array."""

    batch_size = 25
    all_claims: list[dict] = []
    batches = (count + batch_size - 1) // batch_size
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    for batch_num in range(batches):
        remaining = count - len(all_claims)
        current_batch = min(batch_size, remaining)
        batch_prompt = prompt.replace(f"exakt {count} Claims", f"exakt {current_batch} Claims")

        print(f"    Fallback-Batch {batch_num + 1}/{batches} ({current_batch})...", end=" ", flush=True)
        response = client.messages.create(
            model=model,
            max_tokens=8192,
            system=SYSTEM_PROMPT_CLAIMS,
            messages=[{"role": "user", "content": batch_prompt}],
        )

        raw = response.content[0].text.strip()
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        try:
            batch_claims = json.loads(raw)
            all_claims.extend(batch_claims)
            print(f"✓ ({len(batch_claims)})")
        except json.JSONDecodeError:
            try:
                batch_claims = json.loads(raw + "]")
                all_claims.extend(batch_claims)
            except Exception:
                print("✗ übersprungen")

    return all_claims[:count]


# ─── Haupt-Generator ─────────────────────────────────────────────────────────

async def generate_claims(
    domain_id: str,
    count: int = 25,
    model: str = "claude-sonnet-4-5",
) -> list[dict]:
    """
    Pareto-optimierte Claim-Generierung:
      1. Offizielle Schweizer Quellen abrufen (ch.ch etc.)
      2. Phase 1: KI identifiziert Top-Fragen (80/20-Prinzip)
      3. Phase 2: Für jede Frage einen verifizierten Dual-Format-Claim generieren

    Rückgabe: list[dict] mit question + text + source_urls + confidence_score
    """
    if domain_id not in DOMAINS:
        raise ValueError(f"Unbekannte Domain: '{domain_id}'. Verfügbar: {', '.join(DOMAINS.keys())}")

    domain = DOMAINS[domain_id]
    print(f"\n🤖  Pareto-Generierung für '{domain['name']}' ({count} Claims)")
    print(f"    Modell: {model}")
    print("    " + "─" * 50)

    # ── Schritt 1: Quellen abrufen (HTML + Wikipedia) ────────────────────────
    n_html = len(domain.get("faq_urls", []))
    n_wiki = len(domain.get("wiki_topics", []))
    print(f"    📡 Fetche Quellen: {n_html} HTML-Seiten, {n_wiki} Wikipedia-Artikel...")
    faq_context = await fetch_source_content(domain)
    if faq_context:
        print(f"    ✓ Kontext: {len(faq_context)} Zeichen")
    else:
        print("    ⚠ Kein Kontext geladen — nutze Claude-Wissen")

    # ── Schritt 2: Phase 1 — Pareto-Fragen ──────────────────────────────────
    print(f"\n    Phase 1: Pareto-Analyse ({count} Top-Fragen)...")
    questions = await generate_pareto_questions(domain_id, count, faq_context, model)

    if questions:
        high_risk = sum(1 for q in questions if q.get("hallucination_risk") == "high")
        print(f"    ✓ {len(questions)} Fragen generiert ({high_risk} mit hohem Halluzinations-Risiko)")
        categories = {}
        for q in questions:
            cat = q.get("category", "?")
            categories[cat] = categories.get(cat, 0) + 1
        cats_str = ", ".join(f"{k}: {v}" for k, v in sorted(categories.items()))
        print(f"    Kategorien: {cats_str}")
    else:
        print("    ⚠ Phase 1 fehlgeschlagen — nutze Legacy-Generator als Fallback")
        return await _generate_claims_legacy(domain_id, count, model)

    # ── Schritt 3: Phase 2 — Claims generieren ───────────────────────────────
    print(f"\n    Phase 2: Claim-Generierung ({len(questions)} Antworten)...")
    claims = await generate_claims_from_questions(domain_id, questions, faq_context, model)

    if not claims:
        print("    ✗ Phase 2 fehlgeschlagen — Fallback")
        return await _generate_claims_legacy(domain_id, count, model)

    print(f"\n    ✅ {len(claims)} Dual-Format-Claims generiert")
    return claims[:count]


# ─── CLI-Hauptroutine ─────────────────────────────────────────────────────────

async def _run() -> None:
    args = sys.argv[1:]

    if "--list-domains" in args:
        print("\n🌍  Verfügbare Domains für swiss-truth-generate:\n")
        for domain_id, domain in DOMAINS.items():
            existing = SEED_DIR / f"{domain_id.replace('-', '_')}_claims.json"
            status = "✅ vorhanden" if existing.exists() else "⬜ neu"
            urls = len(domain.get("faq_urls", []))
            print(f"  {status}  {domain_id:<22} → {domain['name']} ({urls} FAQ-Quellen)")
        print()
        return

    domain_id = None
    count = 25
    do_import = "--import" in args
    model = "claude-sonnet-4-5"

    if "--domain" in args:
        idx = args.index("--domain")
        if idx + 1 < len(args):
            domain_id = args[idx + 1]

    if "--count" in args:
        idx = args.index("--count")
        if idx + 1 < len(args):
            count = int(args[idx + 1])

    if "--model" in args:
        idx = args.index("--model")
        if idx + 1 < len(args):
            model = args[idx + 1]

    if not domain_id:
        print("❌  --domain DOMAIN ist erforderlich.", file=sys.stderr)
        sys.exit(1)

    if not settings.anthropic_api_key:
        print("❌  ANTHROPIC_API_KEY nicht gesetzt.", file=sys.stderr)
        sys.exit(1)

    print("🌱  Swiss Truth — Pareto Claim-Generator (80/20)")
    print("=" * 55)

    claims = await generate_claims(domain_id=domain_id, count=count, model=model)

    if not claims:
        print("❌  Keine Claims generiert.", file=sys.stderr)
        sys.exit(1)

    filename = f"{domain_id.replace('-', '_')}_claims.json"
    output_path = SEED_DIR / filename

    existing_claims: list[dict] = []
    if output_path.exists():
        existing_claims = json.loads(output_path.read_text(encoding="utf-8"))
        existing_texts = {c["text"] for c in existing_claims}
        new_claims = [c for c in claims if c["text"] not in existing_texts]
        merged = existing_claims + new_claims
        print(f"\n📎  Merge: {len(existing_claims)} bestehend + {len(new_claims)} neu = {len(merged)} total")
    else:
        merged = claims
        new_claims = claims

    output_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n💾  Gespeichert: {output_path.name} ({len(merged)} Claims total)")

    certified = sum(1 for c in new_claims if c.get("confidence_score", 0) >= 0.95)
    review = len(new_claims) - certified
    has_question = sum(1 for c in new_claims if c.get("question"))
    print(f"   ✅  Direkt zertifizierbar: {certified}")
    print(f"   🟡  In Review:             {review}")
    print(f"   ❓  Mit Frage (Dual-Format): {has_question}/{len(new_claims)}")

    if do_import:
        print(f"\n→  Starte Import ({filename})...")
        from swiss_truth_mcp.seed.loader import _run as loader_run
        await loader_run(only_file=str(output_path))
    else:
        print(f"\n→  Import: swiss-truth-seed --domain {domain_id}")


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
