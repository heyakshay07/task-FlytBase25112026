"""Perception layer: turns a frame description into structured Detections.

The assignment lets us simulate video frames with text descriptions, so the default
`TextPerceiver` plays the role of the "VLM output parser". The `Perceiver` protocol is
the seam where a real VLM caption (BLIP, Groq vision, ...) plugs in - see vlm.py.
"""
from __future__ import annotations

import re
from typing import Protocol

from .models import Detection, Frame

COLORS = {"blue", "red", "white", "black", "silver", "grey", "gray", "green", "yellow",
          "orange", "brown", "maroon"}

# make -> models;  model -> default category
MODELS = {
    "ford": {"f150": "truck", "ranger": "truck", "transit": "van"},
    "toyota": {"hilux": "truck", "camry": "car", "fortuner": "suv", "innova": "van"},
    "honda": {"civic": "car", "city": "car", "amaze": "car"},
    "tata": {"nexon": "suv", "harrier": "suv"},
    "mahindra": {"scorpio": "suv", "thar": "suv", "bolero": "truck"},
    "maruti": {"swift": "car", "brezza": "suv"},
    "hyundai": {"creta": "suv", "i20": "car"},
    "tesla": {"model3": "car", "modely": "suv"},
}
MODEL_TO_MAKE = {m: make for make, ms in MODELS.items() for m in ms}
MODEL_TO_CAT = {m: c for ms in MODELS.values() for m, c in ms.items()}

TYPE_TO_CAT = {
    "truck": "truck", "trucks": "truck", "pickup": "truck", "lorry": "truck",
    "car": "car", "cars": "car", "sedan": "car", "sedans": "car",
    "hatchback": "car", "hatchbacks": "car", "suv": "suv", "suvs": "suv",
    "van": "van", "vans": "van", "minivan": "van", "minivans": "van",
    "motorcycle": "bike", "motorcycles": "bike", "bike": "bike", "bikes": "bike",
    "scooter": "bike", "scooters": "bike", "motorbike": "bike", "motorbikes": "bike",
    "bus": "bus", "buses": "bus",
}
TYPE_CANONICAL = {
    "cars": "car", "sedans": "sedan", "hatchbacks": "hatchback", "suvs": "suv",
    "vans": "van", "minivans": "minivan", "motorcycles": "motorcycle", "bikes": "bike",
    "scooters": "scooter", "motorbikes": "motorbike", "buses": "bus", "trucks": "truck",
}
VEHICLE_WORDS = (COLORS | set(MODELS) | set(MODEL_TO_MAKE) | set(TYPE_TO_CAT)
                 | {"delivery", "model", "unknown", "unmarked"})

PERSON_WORDS = {"person", "people", "man", "men", "woman", "women", "intruder", "courier",
                "driver", "guard", "gardener", "worker", "visitor", "child", "pedestrian", "pedestrians",
                "trespasser", "individual", "someone", "figure"}
ROLE_WORDS = {"courier", "driver", "guard", "gardener", "worker", "visitor", "intruder",
              "trespasser"}
ANIMAL_WORDS = {"dog", "cat", "fox", "deer", "monkey", "cow", "bird", "animal", "stray"}
NUMBER_WORDS = {"two": 2, "three": 3, "four": 4, "five": 5, "several": 3, "group": 3}

# (regex, activity) in priority order - first match wins
ACTIVITY_PATTERNS = [
    (r"\b(tamper\w*|pry\w*|forcing|break\w* into|picking (?:the )?lock|jiggl\w*)", "tampering"),
    (r"\b(climb\w*|scal\w*|jump\w* (?:over|the))", "climbing"),
    (r"\b(run|runs|running|sprint\w*|fleeing)\b", "running"),
    (r"\b(loiter\w*|linger\w*|lurk\w*|hanging around|pacing)", "loitering"),
    (r"\bleaves? (?:a |the )?(?:package|parcel)", "working"),
    (r"\bexits? (?:the )?(?:vehicle|car|truck|van|suv)\b", "alighting"),
    (r"\b(enter|enters|entering|entered|arrive|arrives|arriving|pulls? in|drives? in)\b", "entering"),
    (r"\b(exit|exits|exiting|exited|leave|leaves|leaving|depart\w*|drives? (?:out|away))\b", "exiting"),
    (r"\b(idling|idles)\b", "idling"),
    (r"\b(parked|parks|stationary)\b", "parked"),
    (r"\b(walk\w*|crossing|approach\w*)\b", "walking"),
    (r"\b(stand\w*|waiting|waits)\b", "standing"),
    (r"\b(carry\w*|deliver\w*|trim\w*|water\w*|clean\w*|work\w*)\b", "working"),
]

SUSPICIOUS_OBJECTS = ["bolt cutter", "lock pick", "crowbar", "ladder", "knife", "weapon", "gun"]
PLATE_RE = re.compile(r"\b([A-Z]{2}\s?\d{1,2}\s?[A-Z]{1,3}\s?\d{4})\b")
NEGATION_RE = re.compile(r"\b(no one|nobody|no (?:person|people|vehicles?|activity|movement))\b\s*\w*")
CLOTHES = r"(?:hoodie|jacket|uniform|shirt|t-shirt|coat|cap|raincoat|vest|clothes|overalls)"
CLOTHES_RE = re.compile(rf"\bin (?:a |an )?((?:[a-z]+ ){{0,2}}{CLOTHES})")


class Perceiver(Protocol):
    def perceive(self, frame: Frame) -> list[Detection]: ...


def _clauses(text: str) -> list[str]:
    return [c.strip() for c in re.split(r"[.;,]| and ", text.lower()) if c.strip()]


def _vehicle_phrases(tokens: list[str]) -> list[list[str]]:
    """Contiguous runs of vehicle-ish tokens containing a make/model/type word."""
    runs, cur = [], []
    for i, tok in enumerate(tokens + [""]):
        if tok in VEHICLE_WORDS or (cur and tok.isdigit() and cur[-1] == "model"):
            cur.append(tok)
        else:
            if cur:
                anchored = any(
                    (t in MODEL_TO_MAKE and (t != "city" or "honda" in cur)) or t in TYPE_TO_CAT or
                    (t in MODELS and (t != "city" or "honda" in cur))
                    for t in cur
                )
                nxt = tokens[i] if i < len(tokens) else ""
                if anchored and nxt not in {"park", "port"}:
                    runs.append(cur)
                cur = []
    return runs


def _make_vehicle(run: list[str], activity: str, plate: str | None) -> Detection:
    run = ["f150" if t == "f-150" else t for t in run]
    run = [TYPE_CANONICAL.get(t, t) for t in run]
    if "model" in run:  # "tesla model 3" -> model3
        j = run.index("model")
        if j + 1 < len(run) and run[j + 1].isdigit():
            run[j:j + 2] = ["model" + run[j + 1]]
    color = next((t for t in run if t in COLORS), "")
    model = next((t for t in run if t in MODEL_TO_MAKE), "")
    make = next((t for t in run if t in MODELS), MODEL_TO_MAKE.get(model, ""))
    vtype = next((t for t in run if t in TYPE_TO_CAT), "")
    category = TYPE_TO_CAT.get(vtype) or MODEL_TO_CAT.get(model) or "car"
    parts = [color, make, model.replace("model", "model ") if model.startswith("model") else model]
    base = " ".join(p for p in parts if p) or " ".join(t for t in (color, vtype or category) if t)
    if not (make or model):
        base = " ".join(p for p in (color, "delivery" if "delivery" in run else "", vtype or category) if p)
    label = base + (f" {vtype}" if vtype and (make or model) and vtype not in base else "")
    key = f"plate:{plate.replace(' ', '').lower()}" if plate else base.strip()
    attrs = {"color": color, "make": make, "model": model, "vtype": vtype}
    if plate:
        attrs["plate"] = plate.replace(" ", "")
    return Detection("vehicle", category, label.strip(), key, activity, 1, attrs)


class TextPerceiver:
    """Rule/lexicon based parser for text frame descriptions."""

    def perceive(self, frame: Frame) -> list[Detection]:
        plate_m = PLATE_RE.search(frame.description)
        plate = plate_m.group(1) if plate_m else None
        found: dict[tuple[str, str], Detection] = {}
        for clause in _clauses(frame.description):
            clause = NEGATION_RE.sub(" ", clause)
            activity = next((act for pat, act in ACTIVITY_PATTERNS if re.search(pat, clause)), "present")
            tokens = re.findall(r"[a-z0-9\-]+", clause.replace("f-150", "f150"))
            for run in _vehicle_phrases(tokens):
                d = _make_vehicle(run, activity, plate)
                found.setdefault((d.kind, d.entity_key), d)
            for i, tok in enumerate(tokens):
                if tok in PERSON_WORDS:
                    d = self._person(tokens, i, clause, activity)
                    found.setdefault((d.kind, d.entity_key), d)
                elif tok in ANIMAL_WORDS:
                    found.setdefault(("animal", tok), Detection("animal", "animal", tok, f"animal:{tok}", activity, 1, {}))
            for obj in SUSPICIOUS_OBJECTS:
                if obj in clause:
                    found.setdefault(("object", obj), Detection("object", "object", obj, f"object:{obj}", "present", 1, {"suspicious": True}))
        return list(found.values())

    @staticmethod
    def _person(tokens: list[str], i: int, clause: str, activity: str) -> Detection:
        count = NUMBER_WORDS.get(tokens[i - 1], 1) if i else 1
        role = next((t for t in tokens if t in ROLE_WORDS), "")
        m = CLOTHES_RE.search(clause)
        descriptor = m.group(1) if m else ""
        ident = role or descriptor or "unidentified"
        label = (role or "person") + (f" in {descriptor}" if descriptor else "")
        return Detection("person", "person", label, f"person:{ident}", activity, count,
                         {"descriptor": descriptor, "role": role})
