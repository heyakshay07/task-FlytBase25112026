"""Plain data models shared by every stage of the pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum
from typing import Any


class Severity(IntEnum):
    INFO = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4

    @classmethod
    def parse(cls, name: str) -> "Severity":
        return cls[name.strip().upper()]


@dataclass(frozen=True)
class Telemetry:
    """One telemetry sample. x/y are metres in a local property frame (0,0 = dock)."""
    location: str
    x: float
    y: float
    altitude_m: float
    battery_pct: float
    speed_mps: float = 0.0
    heading_deg: float = 0.0


@dataclass(frozen=True)
class Frame:
    frame_id: int
    timestamp: datetime
    telemetry: Telemetry
    description: str  # simulated VLM caption of the video frame

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Frame":
        return cls(
            frame_id=int(d["frame_id"]),
            timestamp=datetime.fromisoformat(d["timestamp"]),
            telemetry=Telemetry(**d["telemetry"]),
            description=d["description"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame_id": self.frame_id,
            "timestamp": self.timestamp.isoformat(timespec="seconds"),
            "telemetry": self.telemetry.__dict__.copy(),
            "description": self.description,
        }

    @property
    def hhmm(self) -> str:
        return self.timestamp.strftime("%H:%M")


@dataclass
class Detection:
    """An object/activity extracted from one frame."""
    kind: str            # vehicle | person | animal | object
    category: str        # truck, car, suv, van, bike, bus, person, animal, object
    label: str           # human readable, e.g. "blue ford f150"
    entity_key: str      # stable identity used for cross-frame tracking
    activity: str        # entering, exiting, parked, loitering, walking, ...
    count: int = 1
    attrs: dict[str, Any] = field(default_factory=dict)


@dataclass
class Alert:
    frame_id: int
    timestamp: datetime
    rule: str
    severity: Severity
    message: str
    location: str
    entity_key: str = ""

    @property
    def hhmm(self) -> str:
        return self.timestamp.strftime("%H:%M")

    def __str__(self) -> str:
        return f"[{self.severity.name}] {self.message}, {self.hhmm}."


def pretty_label(kind: str, label: str) -> str:
    """'blue ford f150' -> 'Blue Ford F150', 'black suv' -> 'Black SUV'; others just capitalised."""
    if kind == "vehicle":
        return " ".join(w.upper() if (w == "suv" or any(ch.isdigit() for ch in w)) else w.capitalize()
                        for w in label.split())
    return label[:1].upper() + label[1:]
