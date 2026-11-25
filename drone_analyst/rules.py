"""Predefined, configurable alert rules.

Each rule is a small class: evaluate(frame, detections, ctx, cfg) -> list[Alert].
The `RuleEngine` runs them, collapses duplicates per (entity, zone) keeping the most
severe, and applies a cooldown so a loitering person doesn't produce an alert every frame.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from .config import AnalystConfig
from .context import ContextManager
from .models import Alert, Detection, Frame, Severity, pretty_label


class Rule(ABC):
    name = "rule"

    @abstractmethod
    def evaluate(self, frame: Frame, dets: list[Detection], ctx: ContextManager,
                 cfg: AnalystConfig) -> list[Alert]: ...

    def _alert(self, frame: Frame, sev: Severity, msg: str, key: str = "") -> Alert:
        return Alert(frame.frame_id, frame.timestamp, self.name, sev, msg,
                     frame.telemetry.location, key)


class LoiteringRule(Rule):
    """Explicit 'loitering' caption OR same person in same zone longer than the dwell threshold."""
    name = "loitering"

    def evaluate(self, frame, dets, ctx, cfg):
        night = cfg.is_night(frame.timestamp.time())
        out = []
        for d in dets:
            if d.kind != "person":
                continue
            dwell = ctx.dwell_minutes(d.entity_key, frame.telemetry.location)
            if d.activity == "loitering" or (d.activity in {"standing", "present"} and dwell >= cfg.loiter_dwell_min):
                sev = Severity.HIGH if night else Severity.MEDIUM
                out.append(self._alert(frame, sev, f"Person loitering at {frame.telemetry.location}", d.entity_key))
        return out


class NightPresenceRule(Rule):
    name = "night_presence"

    def evaluate(self, frame, dets, ctx, cfg):
        if not cfg.is_night(frame.timestamp.time()):
            return []
        return [self._alert(frame, Severity.MEDIUM,
                            f"Person detected at {frame.telemetry.location} during night hours", d.entity_key)
                for d in dets if d.kind == "person"]


class UnknownVehicleNightRule(Rule):
    name = "unknown_vehicle_night"

    def evaluate(self, frame, dets, ctx, cfg):
        if not cfg.is_night(frame.timestamp.time()):
            return []
        return [self._alert(frame, Severity.HIGH,
                            f"Unrecognised {pretty_label(d.kind, d.label)} at {frame.telemetry.location} after hours", d.entity_key)
                for d in dets if d.kind == "vehicle" and d.activity != "exiting"
                and d.entity_key not in cfg.known_vehicles and not d.entity_key.startswith("plate:")]


class SuspiciousActivityRule(Rule):
    name = "suspicious_activity"

    def evaluate(self, frame, dets, ctx, cfg):
        out, loc = [], frame.telemetry.location
        night = cfg.is_night(frame.timestamp.time())
        for d in dets:
            if d.kind == "person" and d.activity == "climbing":
                out.append(self._alert(frame, Severity.CRITICAL, f"Person climbing at {loc} (possible intrusion)", d.entity_key))
            elif d.kind == "person" and d.activity == "tampering":
                out.append(self._alert(frame, Severity.CRITICAL, f"Person tampering with property at {loc}", d.entity_key))
            elif d.kind == "person" and d.activity == "running":
                out.append(self._alert(frame, Severity.HIGH if night else Severity.MEDIUM,
                                       f"Person running at {loc}", d.entity_key))
            elif d.kind == "object" and d.attrs.get("suspicious"):
                out.append(self._alert(frame, Severity.HIGH, f"Suspicious object ({d.label}) at {loc}", d.entity_key))
        return out


class RestrictedZoneRule(Rule):
    name = "restricted_zone"

    def evaluate(self, frame, dets, ctx, cfg):
        if frame.telemetry.location not in cfg.restricted_zones:
            return []
        return [self._alert(frame, Severity.HIGH,
                            f"{d.kind.capitalize()} in restricted zone {frame.telemetry.location}", d.entity_key)
                for d in dets if d.kind in {"person", "vehicle"}]


class RepeatVehicleRule(Rule):
    """The brief's 'a blue Ford F150 entered twice today' insight."""
    name = "repeat_vehicle"

    def evaluate(self, frame, dets, ctx, cfg):
        day = frame.timestamp.strftime("%Y-%m-%d")
        out = []
        for d in dets:
            if d.kind == "vehicle" and d.activity == "entering":
                n = ctx.entries_today(d.entity_key, day)
                if n >= cfg.repeat_vehicle_threshold:
                    out.append(self._alert(frame, Severity.LOW,
                                           f"{pretty_label(d.kind, d.label)} has entered {n} times today", d.entity_key))
        return out


class TelemetryHealthRule(Rule):
    """Drone-side safety: battery, altitude envelope, geofence."""
    name = "telemetry"

    def evaluate(self, frame, dets, ctx, cfg):
        t, out = frame.telemetry, []
        if t.battery_pct < cfg.critical_battery_pct:
            out.append(self._alert(frame, Severity.CRITICAL, f"Drone battery critical ({t.battery_pct:.0f}%) - return to dock", "drone:battery"))
        elif t.battery_pct < cfg.low_battery_pct:
            out.append(self._alert(frame, Severity.MEDIUM, f"Drone battery low ({t.battery_pct:.0f}%)", "drone:battery"))
        if t.altitude_m > cfg.max_altitude_m:
            out.append(self._alert(frame, Severity.MEDIUM, f"Drone altitude {t.altitude_m:.0f} m above safe ceiling", "drone:altitude"))
        elif 0 < t.altitude_m < cfg.min_altitude_m:
            out.append(self._alert(frame, Severity.MEDIUM, f"Drone altitude {t.altitude_m:.1f} m below minimum", "drone:altitude"))
        if not (cfg.geofence_x[0] <= t.x <= cfg.geofence_x[1] and cfg.geofence_y[0] <= t.y <= cfg.geofence_y[1]):
            out.append(self._alert(frame, Severity.HIGH, f"Drone outside geofence at ({t.x:.0f}, {t.y:.0f})", "drone:geofence"))
        return out


DEFAULT_RULES = [LoiteringRule, NightPresenceRule, UnknownVehicleNightRule, SuspiciousActivityRule,
                 RestrictedZoneRule, RepeatVehicleRule, TelemetryHealthRule]


class RuleEngine:
    def __init__(self, cfg: AnalystConfig | None = None, rules: list[Rule] | None = None):
        self.cfg = cfg or AnalystConfig()
        self.rules = rules or [r() for r in DEFAULT_RULES]
        self._last: dict[tuple[str, str], tuple[datetime, Severity]] = {}

    @staticmethod
    def _key(a: Alert) -> tuple[str, str]:
        # drone-health alerts are about the drone, not a zone, so they ignore location
        return (a.entity_key, "" if a.entity_key.startswith("drone") else a.location)

    def evaluate(self, frame: Frame, dets: list[Detection], ctx: ContextManager) -> list[Alert]:
        raw = [a for r in self.rules for a in r.evaluate(frame, dets, ctx, self.cfg)]
        best: dict[tuple[str, str], Alert] = {}          # collapse per (entity, zone)
        for a in raw:
            k = self._key(a)
            if k not in best or a.severity > best[k].severity:
                best[k] = a
        out = []
        for k, a in best.items():                         # cooldown unless severity escalates
            prev = self._last.get(k)
            if prev:
                age = (a.timestamp - prev[0]).total_seconds() / 60
                if 0 <= age < self.cfg.cooldown_min and a.severity <= prev[1]:
                    continue
            self._last[k] = (a.timestamp, a.severity)
            out.append(a)
        return sorted(out, key=lambda a: -a.severity)
