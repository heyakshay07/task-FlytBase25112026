"""Predefined rule configuration. Everything an operator would tune lives here."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time


@dataclass
class AnalystConfig:
    # Night window may wrap midnight (22:00 -> 05:00)
    night_start: time = time(22, 0)
    night_end: time = time(5, 0)

    loiter_dwell_min: float = 3.0         # same entity, same zone, this long => loitering
    presence_gap_min: float = 10.0        # unseen this long => dwell timer resets
    repeat_vehicle_threshold: int = 2     # entries/day that trigger a "repeat visitor" alert
    cooldown_min: float = 15.0            # suppress same entity+zone alerts unless severity escalates

    restricted_zones: frozenset[str] = frozenset({"Perimeter Fence"})
    known_vehicles: frozenset[str] = frozenset({"blue ford f150"})  # resident allow-list

    # Drone health / geofence (local metre frame)
    low_battery_pct: float = 20.0
    critical_battery_pct: float = 10.0
    max_altitude_m: float = 60.0
    min_altitude_m: float = 2.0
    geofence_x: tuple[float, float] = (-120.0, 120.0)
    geofence_y: tuple[float, float] = (-100.0, 100.0)

    suspicious_objects: frozenset[str] = frozenset(
        {"crowbar", "ladder", "bolt cutter", "lock pick", "knife", "weapon", "gun"}
    )

    def is_night(self, t: time) -> bool:
        if self.night_start <= self.night_end:
            return self.night_start <= t < self.night_end
        return t >= self.night_start or t < self.night_end
