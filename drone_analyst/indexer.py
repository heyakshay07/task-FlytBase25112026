"""Frame-by-frame index: SQLite (+FTS5 full-text, +semantic vectors).

Every frame is stored with timestamp, drone telemetry, caption and the structured
detections extracted from it, so it can be queried by time, object, location or free text.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import datetime
from typing import Any, Iterable

from .models import Alert, Detection, Frame, Severity
from .semantic import SemanticIndex

SCHEMA = """
CREATE TABLE IF NOT EXISTS frames(
  id INTEGER PRIMARY KEY, ts TEXT NOT NULL, location TEXT, x REAL, y REAL,
  altitude REAL, battery REAL, speed REAL, heading REAL, description TEXT);
CREATE INDEX IF NOT EXISTS idx_frames_ts ON frames(ts);
CREATE INDEX IF NOT EXISTS idx_frames_loc ON frames(location);
CREATE TABLE IF NOT EXISTS detections(
  id INTEGER PRIMARY KEY AUTOINCREMENT, frame_id INTEGER NOT NULL, kind TEXT, category TEXT,
  label TEXT, entity_key TEXT, activity TEXT, count INTEGER, attrs TEXT);
CREATE INDEX IF NOT EXISTS idx_det_frame ON detections(frame_id);
CREATE INDEX IF NOT EXISTS idx_det_entity ON detections(entity_key);
CREATE INDEX IF NOT EXISTS idx_det_cat ON detections(category);
CREATE TABLE IF NOT EXISTS visits(
  entity_key TEXT, visit_no INTEGER, label TEXT, category TEXT, day TEXT,
  start_ts TEXT, end_ts TEXT, PRIMARY KEY(entity_key, visit_no));
CREATE TABLE IF NOT EXISTS alerts(
  id INTEGER PRIMARY KEY AUTOINCREMENT, frame_id INTEGER, ts TEXT, rule TEXT,
  severity INTEGER, message TEXT, location TEXT, entity_key TEXT);
CREATE INDEX IF NOT EXISTS idx_alert_ts ON alerts(ts);
"""

# query words -> detection category / canonical term
CATEGORY_WORDS = {
    "truck": "truck", "trucks": "truck", "pickup": "truck", "lorry": "truck", "f150": "truck",
    "car": "car", "cars": "car", "sedan": "car", "van": "van", "vans": "van",
    "suv": "suv", "suvs": "suv", "bike": "bike", "motorcycle": "bike", "bus": "bus",
    "person": "person", "people": "person", "man": "person", "woman": "person",
    "intruder": "person", "courier": "person", "driver": "person", "gardener": "person",
    "animal": "animal", "animals": "animal", "dog": "animal", "fox": "animal", "cat": "animal",
    "vehicle": "vehicle", "vehicles": "vehicle",
}


class FrameIndex:
    def __init__(self, path: str = ":memory:", commit_every: int = 500, reset: bool = False):
        if reset and path != ":memory:" and os.path.exists(path):
            os.remove(path)
        if path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.path = path
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        try:
            self.db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS frames_fts USING fts5(description)")
            self.fts = True
        except sqlite3.OperationalError:  # SQLite built without FTS5 -> LIKE fallback
            self.fts = False
        self.semantic = SemanticIndex()
        self._pending = 0
        self._commit_every = commit_every
        for r in self.db.execute("SELECT id, description FROM frames"):  # warm vectors on reopen
            self.semantic.add(r["id"], r["description"])

    # ------------------------------------------------------------------ writes
    def add_frame(self, frame: Frame, detections: Iterable[Detection]) -> None:
        t = frame.telemetry
        self.db.execute(
            "INSERT OR REPLACE INTO frames VALUES(?,?,?,?,?,?,?,?,?,?)",
            (frame.frame_id, frame.timestamp.isoformat(timespec="seconds"), t.location, t.x, t.y,
             t.altitude_m, t.battery_pct, t.speed_mps, t.heading_deg, frame.description))
        if self.fts:
            self.db.execute("INSERT INTO frames_fts(rowid, description) VALUES(?,?)",
                            (frame.frame_id, frame.description))
        self.db.executemany(
            "INSERT INTO detections(frame_id,kind,category,label,entity_key,activity,count,attrs)"
            " VALUES(?,?,?,?,?,?,?,?)",
            [(frame.frame_id, d.kind, d.category, d.label, d.entity_key, d.activity, d.count,
              json.dumps(d.attrs)) for d in detections])
        self.semantic.add(frame.frame_id, frame.description)
        self._tick()

    def add_alert(self, a: Alert) -> None:
        self.db.execute(
            "INSERT INTO alerts(frame_id,ts,rule,severity,message,location,entity_key) VALUES(?,?,?,?,?,?,?)",
            (a.frame_id, a.timestamp.isoformat(timespec="seconds"), a.rule, int(a.severity),
             a.message, a.location, a.entity_key))
        self._tick()

    def upsert_visit(self, key: str, visit_no: int, label: str, category: str, day: str,
                     start: datetime, end: datetime | None) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO visits VALUES(?,?,?,?,?,?,?)",
            (key, visit_no, label, category, day, start.isoformat(timespec="seconds"),
             end.isoformat(timespec="seconds") if end else None))
        self._tick()

    def _tick(self) -> None:
        self._pending += 1
        if self._pending >= self._commit_every:
            self.flush()

    def flush(self) -> None:
        self.db.commit()
        self._pending = 0

    # ------------------------------------------------------------------ reads
    def frames(self, start: str | None = None, end: str | None = None,
               tod_start: str | None = None, tod_end: str | None = None,
               obj: str | None = None, location: str | None = None,
               limit: int = 50) -> list[dict[str, Any]]:
        """Query frames. start/end are ISO datetimes; tod_* are 'HH:MM' time-of-day filters
        (wrap-around such as 22:00-05:00 supported); obj is a free object term."""
        sql, args = ["SELECT DISTINCT f.* FROM frames f"], []
        where = []
        if obj:
            sql.append("LEFT JOIN detections d ON d.frame_id = f.id")
            clause, a = self._object_clause(obj)
            where.append(clause); args += a
        if start: where.append("f.ts >= ?"); args.append(start)
        if end: where.append("f.ts <= ?"); args.append(end)
        if tod_start and tod_end:
            t = "substr(f.ts, 12, 5)"
            if tod_start <= tod_end:
                where.append(f"{t} BETWEEN ? AND ?")
            else:
                where.append(f"({t} >= ? OR {t} <= ?)")
            args += [tod_start, tod_end]
        if location:
            where.append("lower(f.location) LIKE ?"); args.append(f"%{location.lower()}%")
        if where: sql.append("WHERE " + " AND ".join(where))
        sql.append("ORDER BY f.ts LIMIT ?"); args.append(limit)
        return [self._frame_row(r) for r in self.db.execute(" ".join(sql), args)]

    @staticmethod
    def _object_clause(term: str) -> tuple[str, list[str]]:
        term = term.lower().strip()
        cat = CATEGORY_WORDS.get(term)
        if cat == "vehicle":
            return "d.kind = 'vehicle'", []
        if cat:
            return "(d.category = ? OR d.label LIKE ?)", [cat, f"%{term}%"]
        return "(d.label LIKE ? OR d.entity_key LIKE ? OR f.description LIKE ?)", [f"%{term}%"] * 3

    def detections(self, frame_id: int) -> list[dict[str, Any]]:
        return [dict(r) for r in self.db.execute(
            "SELECT kind,category,label,entity_key,activity,count FROM detections WHERE frame_id=?",
            (frame_id,))]

    def text_search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        words = re.findall(r"[a-z0-9]+", query.lower())
        if not words:
            return []
        if self.fts:
            q = " OR ".join(f'"{w}"' for w in words)
            rows = self.db.execute(
                "SELECT f.* FROM frames_fts JOIN frames f ON f.id = frames_fts.rowid "
                "WHERE frames_fts MATCH ? ORDER BY rank LIMIT ?", (q, limit))
        else:
            like = " OR ".join("description LIKE ?" for _ in words)
            rows = self.db.execute(f"SELECT * FROM frames WHERE {like} LIMIT ?",
                                   [f"%{w}%" for w in words] + [limit])
        return [self._frame_row(r) for r in rows]

    def semantic_search(self, query: str, k: int = 5) -> list[dict[str, Any]]:
        out = []
        for fid, score in self.semantic.search(query, k):
            r = self.db.execute("SELECT * FROM frames WHERE id=?", (fid,)).fetchone()
            if r:
                row = self._frame_row(r); row["score"] = round(score, 3); out.append(row)
        return out

    def alerts(self, min_severity: Severity = Severity.INFO, tod_start: str | None = None,
               tod_end: str | None = None, limit: int = 200) -> list[Alert]:
        sql, args = "SELECT * FROM alerts WHERE severity >= ?", [int(min_severity)]
        if tod_start and tod_end:
            t = "substr(ts, 12, 5)"
            sql += f" AND {t} BETWEEN ? AND ?" if tod_start <= tod_end else f" AND ({t} >= ? OR {t} <= ?)"
            args += [tod_start, tod_end]
        sql += " ORDER BY ts, id LIMIT ?"; args.append(limit)
        return [Alert(r["frame_id"], datetime.fromisoformat(r["ts"]), r["rule"],
                      Severity(r["severity"]), r["message"], r["location"], r["entity_key"])
                for r in self.db.execute(sql, args)]

    def entities(self) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT d.entity_key, d.kind, d.category, MAX(d.label) AS label, COUNT(DISTINCT d.frame_id) AS frames,"
            " MIN(f.ts) AS first_seen, MAX(f.ts) AS last_seen"
            " FROM detections d JOIN frames f ON f.id = d.frame_id"
            " GROUP BY d.entity_key ORDER BY first_seen")
        return [dict(r) for r in rows]

    def visits(self, obj: str | None = None) -> list[dict[str, Any]]:
        sql, args = "SELECT * FROM visits", []
        if obj:
            term = obj.lower(); cat = CATEGORY_WORDS.get(term)
            if cat == "vehicle":
                pass
            elif cat:
                sql += " WHERE category = ? OR label LIKE ?"; args = [cat, f"%{term}%"]
            else:
                sql += " WHERE label LIKE ? OR entity_key LIKE ?"; args = [f"%{term}%"] * 2
        return [dict(r) for r in self.db.execute(sql + " ORDER BY start_ts", args)]

    def locations(self) -> list[str]:
        return [r[0] for r in self.db.execute("SELECT DISTINCT location FROM frames")]

    def stats(self) -> dict[str, Any]:
        q = lambda s: self.db.execute(s).fetchone()[0]
        return {"frames": q("SELECT COUNT(*) FROM frames"),
                "detections": q("SELECT COUNT(*) FROM detections"),
                "alerts": q("SELECT COUNT(*) FROM alerts"),
                "entities": q("SELECT COUNT(DISTINCT entity_key) FROM detections"),
                "first_ts": q("SELECT MIN(ts) FROM frames"), "last_ts": q("SELECT MAX(ts) FROM frames")}

    @staticmethod
    def _frame_row(r: sqlite3.Row) -> dict[str, Any]:
        return {"frame_id": r["id"], "ts": r["ts"], "hhmm": r["ts"][11:16], "location": r["location"],
                "altitude": r["altitude"], "battery": r["battery"], "description": r["description"]}

    def close(self) -> None:
        self.flush(); self.db.close()
