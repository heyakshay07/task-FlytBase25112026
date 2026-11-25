"""Builds report/Drone_Security_Analyst_Report.pdf from the real outputs in docs/."""
import json
import os
import re

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, Preformatted, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = lambda *p: os.path.join(ROOT, *p)
res = json.load(open(D("docs", "scalability_results.json")))

ss = getSampleStyleSheet()
body = ParagraphStyle("b", parent=ss["BodyText"], fontSize=9.6, leading=13.2, spaceAfter=5, alignment=TA_LEFT)
h1 = ParagraphStyle("h1", parent=ss["Heading1"], fontSize=15, spaceBefore=10, spaceAfter=6, textColor=colors.HexColor("#1F3B63"))
h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=11.5, spaceBefore=8, spaceAfter=4, textColor=colors.HexColor("#2F5D8C"))
mono = ParagraphStyle("m", fontName="Courier", fontSize=7.6, leading=9.6, backColor=colors.HexColor("#F4F6F8"),
                      borderPadding=4, spaceAfter=6)
small = ParagraphStyle("s", parent=body, fontSize=8.4, leading=11, textColor=colors.HexColor("#555555"))
bul = ParagraphStyle("bul", parent=body, leftIndent=12, bulletIndent=2, spaceAfter=2)


def P(t, s=body): return Paragraph(t, s)
def B(items): return [Paragraph(i, bul, bulletText="-") for i in items]
def code(t):
    import textwrap
    lines = []
    for l in t.split("\n"):
        lines += textwrap.wrap(l, 118, subsequent_indent="    ") or [""]
    return Preformatted("\n".join(lines), mono)


def table(rows, widths, head=True):
    t = Table([[Paragraph(str(c), ParagraphStyle("c", parent=body, fontSize=8.4, leading=10.5, spaceAfter=0)) for c in r] for r in rows],
              colWidths=widths, repeatRows=1 if head else 0)
    st = [("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#B8C2CC")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
          ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]
    if head:
        st.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E4ECF5")))
    t.setStyle(TableStyle(st))
    return t


def img(path, width):
    from PIL import Image as PI
    w, h = PI.open(path).size
    return Image(path, width=width, height=width * h / w)


def footer(c, d):
    c.saveState(); c.setFont("Helvetica", 7.5); c.setFillColor(colors.grey)
    c.drawString(18 * mm, 10 * mm, "Drone Security Analyst Agent - approach report")
    c.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {d.page}"); c.restoreState()


run = open(D("docs", "sample_run_output.txt")).read().splitlines()
excerpt = [l.strip() for l in run if l.strip().startswith(("ALERT", "LOG"))]
key_logs = [l for l in excerpt if any(k in l for k in ("12:00", "00:01", "11:58", "16:2", "22:30", "14:3", "09:10"))]
qa = open(D("docs", "sample_qa_output.txt")).read().strip().split("\n\n")

s = []
s += [P("Drone Security Analyst Agent", ParagraphStyle("t", parent=ss["Title"], fontSize=22, textColor=colors.HexColor("#1F3B63"))),
      P("Approach report - FlytBase AI Engineer assignment", ParagraphStyle("st", parent=body, fontSize=11, textColor=colors.HexColor("#555555"))),
      P("Akshay Patil &nbsp;|&nbsp; Repository: <i>[private GitHub link]</i> &nbsp;|&nbsp; Videos: <i>[Drive links, view access]</i>", small), Spacer(1, 6)]

s += [P("1. Summary", h1),
      P("I built a working prototype of a Drone Security Analyst Agent: it ingests simulated telemetry and frame descriptions, "
        "logs objects and events with context, raises severity-ranked real-time alerts from configurable rules, indexes every frame "
        "in SQLite (timestamp, telemetry, structured detections, full-text and semantic vectors) and answers follow-up questions and "
        "summaries (both bonus items). The core uses only the Python standard library; a LangGraph/Groq agent and a real-video BLIP bridge are optional layers."),
      P("The design goal was <b>correct, explainable behaviour that can be tested</b>: every alert traces to a named rule and threshold, and every "
        "answer traces to rows in the index. The 46-test suite passes, and the pipeline sustained about %s frames/s over %s frames." % (f"{res['frames_per_second']:,}", f"{res['frames']:,}"))]

s += [P("2. Feature spec (value and requirements)", h1),
      P("<b>Value to property owners:</b> automated, always-on monitoring - instant alerts on suspicious behaviour plus a searchable history, "
        "so an owner reviews a few events instead of hours of footage."),
      table([["#", "Requirement", "Acceptance"],
             ["R1", "Ingest telemetry + frames, log objects/events with context", "Logs like 'Blue Ford F150 spotted at garage, 12:00.'; every frame stored with telemetry"],
             ["R2", "Real-time rule-based alerts without alert fatigue", "'Person loitering at Main Gate, 00:01' HIGH at night; no repeat alerts unless severity escalates"],
             ["R3", "Frame-by-frame index and conversational follow-up", "Query by time (incl. overnight), object, location, text; counts, object lists, summary"]],
            [10 * mm, 70 * mm, 94 * mm])]

s += [P("3. Assumptions", h1)] + B([
    "<b>Video is simulated by text captions</b> (explicitly allowed). A caption stands in for VLM output; the <font name='Courier'>Perceiver</font> interface isolates that assumption, and <font name='Courier'>vlm.py</font> captions real video with BLIP.",
    "Telemetry is simulated in a local metre frame (0,0 = dock) with waypoint positions per zone; one scripted day (30 frames) with injected normal and abnormal events.",
    "Night = 22:00-05:00; loitering = same person in same zone for 3 min or an explicit 'loitering' caption; cooldown = 15 min; resident allow-list = the blue Ford F150. All are in <font name='Courier'>config.py</font> and would be owner-tunable.",
    "Entities are identified from descriptions (colour+make+model, plate, role/clothing). Two people in identical clothing would merge - acceptable for a prototype, and a re-ID problem in production.",
    "A vehicle 'visit' starts at an entering caption (or first sighting) and ends at an exiting caption."])

s += [P("4. Architecture and design", h1),
      img(D("docs", "architecture.png"), 150 * mm),
      P("Per frame: <b>perceive</b> (caption to detections with stable entity keys) -> <b>update context</b> (registry, dwell timers, visit state, digests) -> "
        "<b>index</b> (SQLite + FTS5 + vectors) -> <b>rules</b> (7 rules) -> <b>collapse and cooldown</b> -> alert. Q&amp;A and summaries read only the index, so they work on a saved database.", body),
      img(D("docs", "pipeline.png"), 78 * mm)]

s += [P("4.1 Alert rules", h2),
      table([["Rule", "Trigger", "Severity"],
             ["loitering", "caption says loitering, or same person+zone dwell >= 3 min", "HIGH night / MEDIUM day"],
             ["night_presence", "any person 22:00-05:00", "MEDIUM"],
             ["unknown_vehicle_night", "non-resident vehicle at night (not when leaving)", "HIGH"],
             ["suspicious_activity", "climbing, tampering / running / suspicious object", "CRITICAL / HIGH-MEDIUM / HIGH"],
             ["restricted_zone", "person or vehicle in Perimeter Fence", "HIGH"],
             ["repeat_vehicle", "Nth entry of the same vehicle today, N >= 2", "LOW"],
             ["telemetry", "battery < 20% (<10% critical), altitude > 60 m or < 2 m, outside geofence", "MEDIUM / CRITICAL, HIGH"]],
            [38 * mm, 98 * mm, 38 * mm]),
      P("<b>Alert hygiene</b> matters as much as detection: candidates are collapsed per (entity, zone) to the most severe one, then a cooldown suppresses repeats "
        "unless severity increases. Without it one loiterer would alert on every frame.", body)]

s += [P("5. Tool and configuration choices (and why)", h1),
      table([["Choice", "Why", "Alternative considered"],
             ["Text captions as simulated VLM", "Deterministic, testable, matches the brief; real VLM is behind one interface", "Run BLIP/CLIP on real video: slower, non-deterministic tests, needs footage and model downloads"],
             ["BLIP (in vlm.py) rather than CLIP", "Generative captions give free-text scene descriptions the parser can read; CLIP only scores image-text similarity (good for search, not for narrating events)", "CLIP embeddings for frame retrieval - the natural upgrade for the semantic index"],
             ["Rule engine for alerts, not an LLM", "Auditable, deterministic, zero latency/cost per frame; operators can see exactly why an alert fired", "LLM per frame: flexible but costly, slow and hard to test; kept for Q&amp;A reasoning only"],
             ["SQLite + FTS5 as the index", "Zero-ops, ACID, indexed time/location/entity queries, single file reused by Q&amp;A", "Chroma/Qdrant/Postgres+pgvector - right at larger scale, overkill here"],
             ["Hashed bag-of-words + synonym vectors", "Dependency-free stand-in showing the vector-index interface", "sentence-transformers / CLIP + ANN index"],
             ["Deterministic Q&amp;A router + optional LangGraph ReAct agent", "Common questions are fast, grounded and offline; the LLM handles open-ended ones using the same index as tools", "LLM-only: simpler code, but ungrounded and key-dependent"],
             ["Stable entity keys + visit tracking", "Enable 'entered twice today' and dwell-time loitering; counting sightings would be wrong", "Frame-level alerts only"]],
            [42 * mm, 72 * mm, 60 * mm])]

s += [P("6. Results", h1), P("Real output from <font name='Courier'>python -m drone_analyst run</font> on the simulated day (excerpt):", body),
      code("\n".join(key_logs[:16])),
      P("Follow-up questions answered from the index:", body)]
for block in qa[:4]:
    s.append(code(block))
s += [P("Summary (bonus): <i>" + re.search(r"=== SUMMARY ===\n(Across[^\n]+)", "\n".join(run)).group(1) + "</i>", body)] if re.search(r"=== SUMMARY ===\n(Across[^\n]+)", "\n".join(run)) else []
s += [P("Video references: <b>Video 1</b> processing, logs and alerts; <b>Video 2</b> index and follow-up Q&amp;A; <b>Video 3</b> context, scalability, tests, AI tooling. <i>[insert links]</i>", body)]

s += [P("7. Testing", h1),
      P("46 automated tests (13 perception, 15 rules/alerts, 16 index/Q&amp;A, 2 LLM-tool) run in about 1 s without network or API keys. "
        "Highlights: the midnight loiterer produces exactly the expected HIGH alert and the same behaviour by day is MEDIUM; dwell-based loitering triggers at 3 min and resets after a gap; "
        "a resident truck is never 'unknown' but an unknown SUV is, except when leaving; repeat-visit alert fires on the second entry and resets next day; "
        "climbing beats restricted-zone via collapse; cooldown suppresses repeats but allows escalation; overnight wrap-around time queries; DB persistence round-trip."),
      P("Emergency scenarios in the simulated day: intrusion sequence 16:20-16:22 (CRITICAL), after-hours unknown SUV, drone geofence breach + altitude excursion + low battery."),
      P("<b>Bugs found by running it:</b> non-deterministic semantic hashing (built-in hash() varies per process), 'F-150' tokenisation, 'leaves package' / 'exits vehicle' misread as exits, "
        "Q&amp;A ignoring filters on 'when' questions, alert spam from an idling vehicle, and LLM-context truncation that cut the newest information.")]

q = res["queries_ms"]
s += [P("8. Scalability", h1),
      P("<font name='Courier'>scripts/scalability_test.py</font> replays synthetic frames (varied vehicles, people, incidents) over many simulated days through the full pipeline, writing to SQLite."),
      table([["Metric", "Result (%s frames)" % f"{res['frames']:,}"],
             ["Ingest throughput", f"{res['frames_per_second']:,} frames/s ({res['ingest_seconds']} s total)"],
             ["Database size / peak memory", f"{res['db_mb']} MB / {res['peak_rss_mb']} MB (memory dominated by in-memory semantic index)"],
             ["LLM context size at 20/40/60/80/100%", ", ".join(str(x) for x in res["context_chars_at_20/40/60/80/100pct"]) + " chars - flat by design"],
             ["Object query 'truck'", f"{q['object query: truck (all events)']['avg_ms']} ms ({q['object query: truck (all events)']['rows']:,} rows)"],
             ["Time-of-day query 22:00-05:00", f"{q['time-of-day query: 22:00-05:00']['avg_ms']} ms ({q['time-of-day query: 22:00-05:00']['rows']:,} rows)"],
             ["Full-text search", f"{q[chr(102)+'ull-text search: '+chr(39)+'hedge'+chr(39)]['avg_ms']} ms"],
             ["Q&amp;A 'how many times did the truck enter'", f"{q['Q&A: how many times did the truck enter']['avg_ms']} ms"],
             ["Semantic search (brute force)", f"{q[chr(115)+'emantic search: '+chr(39)+'break in'+chr(39)]['avg_ms']} ms - linear in frames; first thing to replace with an ANN index"]],
            [70 * mm, 104 * mm]),
      P("Caveat: these are text-caption frames. With a real VLM at hundreds of ms per frame, the model - not this pipeline - is the bottleneck; the context design (state per distinct object, hourly digests, capped prompt) is what keeps reasoning cost flat as the video grows.", small)]

s += [P("9. How AI tools were used", h1),
      P("<b>Claude</b> (chat with code-execution sandbox) generated the first draft of the architecture, the rule set and perception lexicon (the AI-generated components), the SQLite schema, "
        "the Q&amp;A router, the LangGraph tool layer, tests, Graphviz diagrams and docs. I used the sandbox to run the tests and the 50k-frame benchmark and iterate on failures "
        "(section 7). Human judgement was needed for the thresholds, for deciding what counts as a visit, and for catching a wrong test expectation (the code was right). "
        "<i>[Personalise: what you changed, what you learned, which parts you extended, and if you are new to LangChain/VLMs say so.]</i>")]

s += [P("10. What I would do with more time", h1)] + B([
    "Run a real VLM (BLIP-2 / a hosted vision model) prompted for <b>JSON detections</b> so perception no longer depends on a lexicon; add plate OCR and appearance re-ID for identity.",
    "Replace the toy vector index with CLIP or sentence-transformer embeddings in Chroma/Qdrant; add hybrid (BM25 + vector) ranking.",
    "Alert sinks (webhook/SMS/Slack), acknowledgement workflow, evidence clip extraction around each alert, and operator feedback to tune thresholds.",
    "Per-property learned baselines (normal visitors/times) to cut false positives; multi-day and multi-drone summaries; a small web dashboard.",
    "Evaluate precision/recall on labelled real footage and measure end-to-end latency with the VLM in the loop.",
    "Limitations to acknowledge: lexicon-bound perception, description-based identity, brute-force semantic search, single process, no real footage tested."])

doc = SimpleDocTemplate(D("report", "Drone_Security_Analyst_Report.pdf"), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                        topMargin=16 * mm, bottomMargin=18 * mm, title="Drone Security Analyst Agent - Approach Report", author="Akshay Patil")
doc.build(s, onFirstPage=footer, onLaterPages=footer)
print("ok")
