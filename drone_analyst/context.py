"""Context management.

Keeps just enough state to reason across the whole video without keeping every frame:

  * entity registry   - one small record per distinct object (first/last seen, entries per day,
                        on-site flag) -> grows with *distinct objects*, not with frames
  * presence timers   - dwell time of an entity in a zone (drives loitering detection)
  * rolling window    - the last N frame digests (short-term memory)
  * hourly digests    - older frames are compressed into per-hour counters (long-term memory)

`prompt_context()` renders all of that as a compact text block (bounded size) for an LLM.
"""
from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field
from datetime import datetime

from .models import Alert, Detection, Frame


@dataclass
class EntityRecord:
    key: str
    kind: str
    category: str
    label: str
    first_seen: datetime
    last_seen: datetime
    sightings: int = 0
    locations: Counter = field(default_factory=Counter)
    entries_by_day: dict[str, int] = field(default_factory=dict)
    total_entries: int = 0
    on_site: bool = False
    last_activity: str = ""
    visit_start: datetime | None = None


@dataclass
class HourDigest:
    frames: int = 0
    detections: Counter = field(default_factory=Counter)   # category -> n
    alerts: int = 0
    max_severity: int = 0


class ContextManager:
    def __init__(self, window: int = 8, keep_days: int = 7):
        self.entities: dict[str, EntityRecord] = {}
        self.recent: deque[str] = deque(maxlen=window)
        self.hourly: dict[str, HourDigest] = {}
        self.presence: dict[tuple[str, str], tuple[datetime, datetime]] = {}
        self.today_alerts: list[Alert] = []
        self.last_frame: Frame | None = None
        self.keep_days = keep_days
        self._visit_events: list[tuple[EntityRecord, int, datetime, datetime | None]] = []

    # ------------------------------------------------------------ update
    def update(self, frame: Frame, detections: list[Detection]) -> None:
        ts, loc = frame.timestamp, frame.telemetry.location
        day = ts.strftime("%Y-%m-%d")
        self._visit_events = []
        if self.last_frame and self.last_frame.timestamp.date() != ts.date():
            self.today_alerts = []
        self.last_frame = frame

        for d in detections:
            rec = self.entities.get(d.entity_key)
            if rec is None:
                rec = self.entities[d.entity_key] = EntityRecord(
                    d.entity_key, d.kind, d.category, d.label, ts, ts)
            rec.sightings += 1
            rec.last_seen = ts
            rec.locations[loc] += 1
            rec.last_activity = d.activity
            self._track_presence(d.entity_key, loc, ts)
            if d.kind == "vehicle":
                self._track_visit(rec, d, ts, day)

        digest = self.hourly.setdefault(ts.strftime("%Y-%m-%dT%H"), HourDigest())
        digest.frames += 1
        digest.detections.update(d.category for d in detections)
        self.recent.append(f"{frame.hhmm} @{loc}: {frame.description}")
        self._prune(ts)

    def record_alerts(self, alerts: list[Alert]) -> None:
        self.today_alerts += alerts
        for a in alerts:
            h = self.hourly.get(a.timestamp.strftime("%Y-%m-%dT%H"))
            if h:
                h.alerts += 1
                h.max_severity = max(h.max_severity, int(a.severity))

    def _track_presence(self, key: str, loc: str, ts: datetime, gap_min: float = 10.0) -> None:
        start, last = self.presence.get((key, loc), (ts, ts))
        if (ts - last).total_seconds() / 60 > gap_min:
            start = ts
        self.presence[(key, loc)] = (start, ts)

    def _track_visit(self, rec: EntityRecord, d: Detection, ts: datetime, day: str) -> None:
        if d.activity == "exiting":
            if rec.on_site:
                rec.on_site = False
                self._visit_events.append((rec, rec.total_entries, rec.visit_start or rec.first_seen, ts))
            return
        if not rec.on_site:                    # explicit "entering" or an inferred first sighting
            rec.on_site = True
            rec.total_entries += 1
            rec.entries_by_day[day] = rec.entries_by_day.get(day, 0) + 1
            rec.visit_start = ts
            self._visit_events.append((rec, rec.total_entries, ts, None))

    def _prune(self, now: datetime) -> None:
        if len(self.hourly) > self.keep_days * 24:
            for k in sorted(self.hourly)[: len(self.hourly) - self.keep_days * 24]:
                del self.hourly[k]
        if len(self.presence) > 5000:   # drop stale timers
            self.presence = {k: v for k, v in self.presence.items()
                             if (now - v[1]).total_seconds() < 3600}
        for rec in self.entities.values():
            if len(rec.entries_by_day) > self.keep_days:
                for k in sorted(rec.entries_by_day)[: -self.keep_days]:
                    del rec.entries_by_day[k]

    # ------------------------------------------------------------ queries
    def dwell_minutes(self, key: str, loc: str) -> float:
        if (key, loc) not in self.presence:
            return 0.0
        s, e = self.presence[(key, loc)]
        return (e - s).total_seconds() / 60

    def entries_today(self, key: str, day: str) -> int:
        rec = self.entities.get(key)
        return rec.entries_by_day.get(day, 0) if rec else 0

    def on_site(self) -> list[EntityRecord]:
        return [r for r in self.entities.values() if r.on_site]

    def prompt_context(self, max_chars: int = 3000) -> str:
        """Bounded-size text snapshot for an LLM prompt.

        Priority order: drone state > on-site entities > recent alerts > last frames > entity
        table. The entity table is the part that gets trimmed when the budget runs out, so the
        freshest information is never the thing that gets cut.
        """
        head = []
        if self.last_frame:
            t = self.last_frame.telemetry
            head.append(f"DRONE: {self.last_frame.timestamp:%Y-%m-%d %H:%M} at {t.location}, "
                        f"alt {t.altitude_m:.0f} m, battery {t.battery_pct:.0f}%")
        on = self.on_site()
        if on:
            head.append("ON SITE: " + ", ".join(f"{r.label} ({r.last_activity})" for r in on[:10]))
        if self.today_alerts:
            head.append("ALERTS TODAY: " + " | ".join(str(a) for a in self.today_alerts[-6:]))
        head.append("RECENT FRAMES:")
        head += [f"- {s[:160]}" for s in self.recent]
        head_txt = "\n".join(head)
        budget = max_chars - len(head_txt) - len("\nENTITIES (newest first):")
        ents = []
        for r in sorted(self.entities.values(), key=lambda r: r.last_seen, reverse=True):
            line = (f"- {r.label} [{r.kind}] first {r.first_seen:%m-%d %H:%M}, last {r.last_seen:%m-%d %H:%M}, "
                    f"seen {r.sightings}x, entries {r.total_entries}")
            if budget - len(line) - 1 < 0:
                break
            ents.append(line); budget -= len(line) + 1
        return head_txt + "\nENTITIES (newest first):\n" + "\n".join(ents)
