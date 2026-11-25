"""SecurityAnalystAgent: ingestion pipeline + question answering + summarisation.

Pipeline per frame:  perceive -> context.update -> index -> rules -> alerts -> log lines.
Q&A is answered from the index (single source of truth) so it works on a saved DB too.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

from .config import AnalystConfig
from .context import ContextManager
from .indexer import CATEGORY_WORDS, FrameIndex
from .models import Alert, Detection, Frame, Severity, pretty_label
from .perception import Perceiver, TextPerceiver
from .rules import RuleEngine

PERIODS = {"night": ("22:00", "05:00"), "midnight": ("00:00", "01:00"),
           "morning": ("05:00", "11:59"), "afternoon": ("12:00", "17:59"), "evening": ("18:00", "21:59")}
SEVERITY_WORDS = {"critical": Severity.CRITICAL, "high": Severity.HIGH, "medium": Severity.MEDIUM,
                  "serious": Severity.HIGH, "urgent": Severity.HIGH}
VERB_FOR = {"entering": "spotted entering", "exiting": "spotted leaving", "parked": "parked",
            "idling": "idling", "loitering": "loitering", "walking": "walking",
            "standing": "standing", "running": "running", "climbing": "climbing",
            "tampering": "tampering", "working": "active", "alighting": "getting out of vehicle",
            "present": "spotted"}


@dataclass
class FrameResult:
    frame: Frame
    detections: list[Detection]
    alerts: list[Alert]
    logs: list[str] = field(default_factory=list)


@dataclass
class Answer:
    text: str
    frames: list[dict] = field(default_factory=list)


class SecurityAnalystAgent:
    def __init__(self, index: FrameIndex | None = None, cfg: AnalystConfig | None = None,
                 perceiver: Perceiver | None = None):
        self.index = index or FrameIndex()
        self.cfg = cfg or AnalystConfig()
        self.perceiver = perceiver or TextPerceiver()
        self.ctx = ContextManager()
        self.engine = RuleEngine(self.cfg)

    # ------------------------------------------------------------ ingestion
    def ingest(self, frame: Frame) -> FrameResult:
        dets = self.perceiver.perceive(frame)
        self.ctx.update(frame, dets)
        self.index.add_frame(frame, dets)
        for rec, no, start, end in self.ctx._visit_events:
            self.index.upsert_visit(rec.key, no, rec.label, rec.category,
                                    start.strftime("%Y-%m-%d"), start, end)
        alerts = self.engine.evaluate(frame, dets, self.ctx)
        for a in alerts:
            self.index.add_alert(a)
        self.ctx.record_alerts(alerts)
        logs = [self._log_line(frame, d) for d in dets if d.kind != "object" or d.attrs.get("suspicious")]
        return FrameResult(frame, dets, alerts, logs)

    @staticmethod
    def _log_line(frame: Frame, d: Detection) -> str:
        loc = frame.telemetry.location.lower()
        verb = VERB_FOR.get(d.activity, "spotted")
        subject = pretty_label(d.kind, d.label)
        if d.count > 1:
            subject = f"{d.count} x {d.label}"
        if d.kind == "vehicle" and d.activity in {"parked", "present"}:
            return f"{subject} spotted at {loc}, {frame.hhmm}."
        return f"{subject} {verb} at {loc}, {frame.hhmm}."

    def ingest_many(self, frames, on_result: Callable[[FrameResult], None] | None = None) -> int:
        n = 0
        for f in frames:
            res = self.ingest(f)
            n += 1
            if on_result:
                on_result(res)
        self.index.flush()
        return n

    # ------------------------------------------------------------ summarisation
    def summary(self) -> str:
        s = self.index.stats()
        if not s["frames"]:
            return "No frames processed yet."
        alerts = self.index.alerts()
        by_sev = {sv: [a for a in alerts if a.severity == sv] for sv in Severity}
        ents = self.index.entities()
        vehicles = [e for e in ents if e["kind"] == "vehicle"]
        persons = [e for e in ents if e["kind"] == "person"]
        top = max(alerts, key=lambda a: (a.severity, -a.timestamp.timestamp()), default=None)
        one = (f"Across {s['frames']} frames the index tracked {len(vehicles)} vehicle profile(s) and "
               f"{len(persons)} person profile(s) and raised {len(alerts)} alert(s)")
        one += (f"; most serious: {top.message.lower()} at {top.hhmm} ({top.severity.name})."
                if top else ".")
        lines = [one, ""]
        counts: dict[tuple[str, str], int] = {}
        for v in self.index.visits():
            counts[(v["label"], v["day"])] = counts.get((v["label"], v["day"]), 0) + 1
        for (label, day), n in counts.items():
            if n > 1:
                lines.append(f"- {pretty_label('vehicle', label)} entered {n} times on {day}.")
        for sv in (Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM):
            if by_sev[sv]:
                lines.append(f"- {sv.name}: " + "; ".join(f"{a.message} ({a.hhmm})" for a in by_sev[sv]))
        return "\n".join(lines)

    # ------------------------------------------------------------ Q&A
    def ask(self, q: str) -> Answer:
        ql = q.lower().strip()
        obj = self._object_term(ql)
        tod = self._time_range(ql)
        loc = self._location(ql)

        if re.search(r"\b(summar|overview|recap|what happened (?:today|overall|in the video))", ql):
            return Answer(self.summary())
        if re.search(r"what (?:objects|things|entities)|list (?:all )?(?:objects|entities)|what was in the video", ql):
            return self._answer_objects()
        if re.search(r"\balerts?\b|\bthreats?\b|anything suspicious|\bsuspicious\b", ql):
            return self._answer_alerts(ql, tod)
        if obj and re.search(r"how many times|how often|how many visits|\btwice\b|\bentered\b|\bentries\b", ql):
            return self._answer_visits(obj)
        if obj and re.search(r"\bhow many\b|\bnumber of\b|\bcount(?: of)?\b", ql):
            category = CATEGORY_WORDS.get(obj)
            if category in {"vehicle", "car", "truck", "van", "suv", "bike", "bus"}:
                frames = self.index.frames(obj=obj, limit=100000)
                if not frames:
                    return Answer(f"No '{obj}' detections were found in the indexed frames.")
                return Answer(
                    f"The index found {len(frames)} sampled frame(s) matching '{obj}'. "
                    "This caption index does not track individual vehicles, so it cannot "
                    "give a reliable count of distinct vehicles."
                )
        if obj and re.search(r"\bwhen\b|last time|first time|what time", ql):
            return self._answer_when(obj, ql, loc, tod)
        if obj or tod or loc:
            frames = self.index.frames(tod_start=tod[0] if tod else None, tod_end=tod[1] if tod else None,
                                       obj=obj, location=loc, limit=1000)
            return self._answer_frames(frames, obj, tod, loc)
        terms = [w for w in re.findall(r"[a-z0-9]+", ql)
                 if w not in {"a", "an", "the", "is", "are", "on", "in", "at", "of", "to", "near", "with"}]
        if terms:
            matched = []
            for frame in self.index.frames(limit=100000):
                description = frame["description"].lower()
                score = sum(bool(re.search(rf"\b{re.escape(term)}\b", description)) for term in terms)
                if score:
                    matched.append((score, frame))
            if matched:
                matched.sort(key=lambda item: (-item[0], item[1]["ts"]))
                frames = [frame for _, frame in matched[:5]]
                return Answer("Matching frames:\n" + "\n".join(self._fmt(f) for f in frames), frames)
        hits = self.index.semantic_search(q, 5)
        if not hits:
            return Answer("I could not find anything relevant in the indexed frames.")
        return Answer("Closest matching frames:\n" + "\n".join(self._fmt(h) for h in hits), hits)

    # --- helpers
    def _object_term(self, ql: str) -> str | None:
        words = re.findall(r"[a-z0-9\-]+", ql)
        for w in words:
            if w in CATEGORY_WORDS:
                return w.replace("-", "")
        for e in self.index.entities():           # entity label mentioned ("blue ford f150")
            if e["label"] in ql:
                return e["label"]
        return None

    def _time_range(self, ql: str) -> tuple[str, str] | None:
        m = re.search(r"between (\d{1,2}):?(\d{2})? ?(?:and|to|-) ?(\d{1,2}):?(\d{2})?", ql)
        if m:
            return f"{int(m[1]):02d}:{int(m[2] or 0):02d}", f"{int(m[3]):02d}:{int(m[4] or 0):02d}"
        m = re.search(r"\bat (\d{1,2}):(\d{2})\b", ql)
        if m:
            t = f"{int(m[1]):02d}:{m[2]}"
            return t, t
        for word, rng in PERIODS.items():
            if re.search(rf"\b{word}\b", ql):
                return rng
        return None

    def _location(self, ql: str) -> str | None:
        for loc in self.index.locations():
            if loc.lower() in ql or loc.lower().split()[-1] in ql.split():
                return loc
        return None

    @staticmethod
    def _fmt(f: dict) -> str:
        when = f.get("ts", "")[11:19] or f["hhmm"]
        return f"  {when} @{f['location']}: {f['description']}"

    def _answer_frames(self, frames, obj, tod, loc) -> Answer:
        what = " ".join(x for x in [f"'{obj}'" if obj else "", f"at {loc}" if loc else "",
                                    f"from {tod[0]} to {tod[1]}" if tod else ""] if x)
        if not frames:
            return Answer(f"No frames found matching {what}.")
        return Answer(f"{len(frames)} frame(s) matching {what}:\n" + "\n".join(self._fmt(f) for f in frames), frames)

    def _answer_objects(self) -> Answer:
        ents = self.index.entities()
        if not ents:
            return Answer("No objects have been detected.")
        groups: dict[str, list[str]] = {}
        for e in ents:
            groups.setdefault(e["kind"], []).append(
                f"{e['label']} ({e['frames']} frame{'s' if e['frames'] != 1 else ''}, "
                f"{e['first_seen'][11:19]}-{e['last_seen'][11:19]})")
        text = "\n".join(f"{k.capitalize()}s: " + "; ".join(v) for k, v in groups.items())
        return Answer(text)

    def _answer_alerts(self, ql: str, tod) -> Answer:
        minsev = next((v for w, v in SEVERITY_WORDS.items() if w in ql), Severity.INFO)
        alerts = self.index.alerts(minsev, tod[0] if tod else None, tod[1] if tod else None)
        if not alerts:
            return Answer("No alerts match that filter.")
        return Answer(f"{len(alerts)} alert(s):\n" + "\n".join(f"  {a}" for a in alerts))

    def _answer_visits(self, obj: str) -> Answer:
        visits = self.index.visits(obj)
        if not visits:
            return Answer(f"No '{obj}' visits recorded.")
        by: dict[str, list[dict]] = {}
        for v in visits:
            by.setdefault(v["label"], []).append(v)
        out = []
        for label, vs in by.items():
            times = ", ".join(f"{v['start_ts'][11:16]}" + (f"-{v['end_ts'][11:16]}" if v["end_ts"] else "") for v in vs)
            out.append(f"{pretty_label('vehicle', label)} entered {len(vs)} time(s): {times}.")
        return Answer("\n".join(out))

    def _answer_when(self, obj: str, ql: str, loc: str | None = None, tod=None) -> Answer:
        frames = self.index.frames(obj=obj, location=loc, limit=100000,
                                   tod_start=tod[0] if tod else None, tod_end=tod[1] if tod else None)
        if not frames:
            return Answer(f"No frames contain '{obj}'" + (f" at {loc}." if loc else "."))
        pick = frames[0] if "first" in ql else frames[-1]
        which = "First" if "first" in ql else "Last"
        return Answer(f"{which} '{obj}' sighting:\n{self._fmt(pick)}", [pick])
