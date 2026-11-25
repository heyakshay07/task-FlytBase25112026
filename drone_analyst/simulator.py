"""Simulated drone feed: scripted day at the property -> telemetry + frame captions (JSONL)."""
from __future__ import annotations

import json
import random
from datetime import datetime

from .models import Frame, Telemetry

# local metre frame, (0, 0) = dock
WAYPOINTS = {
    "Main Gate": (60.0, -10.0), "Garage": (-30.0, 20.0), "Backyard": (-50.0, 60.0),
    "Parking Lot": (30.0, 40.0), "Perimeter Fence": (90.0, 70.0), "Front Door": (0.0, 30.0),
}

# (HH:MM, location, caption, telemetry overrides)
SCENARIO: list[tuple[str, str, str, dict]] = [
    ("00:00", "Main Gate", "Empty driveway, gate closed. No activity.", {}),
    ("00:01", "Main Gate", "Person in dark hoodie loitering near main gate, looking at the lock.", {}),
    ("00:02", "Main Gate", "Person in dark hoodie standing at main gate, checking phone.", {}),
    ("00:03", "Main Gate", "Person in dark hoodie walking away from main gate toward the road.", {}),
    ("00:05", "Perimeter Fence", "Fox crossing the lawn near the fence. Nothing else visible.", {}),
    ("00:15", "Garage", "Garage door closed. No activity.", {}),
    ("06:30", "Main Gate", "Gate closed, empty driveway. No activity.", {}),
    ("07:45", "Main Gate", "Blue Ford F150 enters through main gate.", {}),
    ("07:46", "Garage", "Blue Ford F150 parked at garage, driver exits vehicle.", {}),
    ("08:30", "Main Gate", "Blue Ford F150 leaves through main gate.", {}),
    ("09:10", "Main Gate", "White delivery van arrives at main gate, courier carrying package.", {}),
    ("09:14", "Front Door", "Courier in white uniform leaves package at front door.", {}),
    ("09:18", "Main Gate", "White delivery van leaves through main gate.", {}),
    ("10:00", "Backyard", "Gardener in green uniform trimming hedge.", {}),
    ("11:58", "Main Gate", "Blue Ford F150 enters through main gate.", {}),
    ("12:00", "Garage", "Blue Ford F150 parked at garage.", {}),
    ("12:40", "Main Gate", "Blue Ford F150 exits through main gate.", {}),
    ("14:00", "Parking Lot", "Red Honda Civic plate MH12XY9999 parked in lot, no one visible.", {}),
    ("14:30", "Perimeter Fence", "Neighbouring property visible past the fence line.",
     {"x": 135.0, "y": 70.0, "battery_pct": 61.0}),
    ("14:31", "Perimeter Fence", "Wide shot of fence line and trees.", {"altitude_m": 72.0}),
    ("16:20", "Perimeter Fence", "Person in black jacket climbing over perimeter fence with a ladder.", {}),
    ("16:21", "Backyard", "Person in black jacket running toward backyard.", {}),
    ("16:22", "Backyard", "Person in black jacket tampering with back door.", {}),
    ("16:25", "Main Gate", "Quiet driveway. No activity.", {}),
    ("19:00", "Main Gate", "Blue Ford F150 enters through main gate.", {}),
    ("19:02", "Garage", "Blue Ford F150 parked at garage.", {}),
    ("22:30", "Main Gate", "Unknown black SUV idling near main gate, no one exits.",
     {"battery_pct": 18.0}),
    ("22:40", "Main Gate", "Black SUV still idling at main gate.", {"battery_pct": 17.0}),
    ("23:10", "Main Gate", "Black SUV drives away from main gate.", {"battery_pct": 15.0}),
    ("23:30", "Garage", "Garage door closed. Blue Ford F150 parked. No activity.", {}),
]


def build_frames(date: str = "2026-11-24", seed: int = 7, scenario=SCENARIO) -> list[Frame]:
    rng = random.Random(seed)
    frames = []
    for i, (hhmm, loc, caption, over) in enumerate(scenario, start=1):
        wx, wy = WAYPOINTS[loc]
        tel = dict(location=loc, x=round(wx + rng.uniform(-4, 4), 1), y=round(wy + rng.uniform(-4, 4), 1),
                   altitude_m=round(rng.uniform(18, 32), 1), battery_pct=round(rng.uniform(70, 96), 1),
                   speed_mps=round(rng.uniform(0, 4), 1), heading_deg=round(rng.uniform(0, 359), 0))
        tel.update(over)
        frames.append(Frame(i, datetime.fromisoformat(f"{date}T{hhmm}:00"), Telemetry(**tel), caption))
    return frames


def write_feed(path: str, **kw) -> int:
    frames = build_frames(**kw)
    with open(path, "w") as fh:
        for f in frames:
            fh.write(json.dumps(f.to_dict()) + "\n")
    return len(frames)


def read_feed(path: str) -> list[Frame]:
    with open(path) as fh:
        return [Frame.from_dict(json.loads(line)) for line in fh if line.strip()]
