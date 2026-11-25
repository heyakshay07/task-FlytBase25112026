# Feature Spec - Drone Security Analyst Agent

## Problem
A docked drone patrols a fixed property every day. Raw video is too long for an owner to review, and
an incident is only useful if someone hears about it *while it happens*.

## Value to property owners
Automated, always-on monitoring: the agent watches every frame, **alerts immediately** on suspicious
behaviour and keeps a **searchable memory** ("a blue Ford F150 entered three times today") so the owner
reviews a handful of events instead of hours of footage.

## Users
* **Owner / resident** - wants a few high-signal alerts and a daily summary.
* **Security operator** - wants severity-ranked alerts, evidence frames and the ability to ask follow-ups.

## Key requirements
| # | Requirement | Acceptance criteria |
|---|---|---|
| R1 | Ingest telemetry + frames and log objects/events with context | Each frame yields log lines such as `Blue Ford F150 spotted at garage, 12:00.`; every frame is stored with telemetry |
| R2 | Real-time, rule-based alerts without alert fatigue | `Person loitering at Main Gate, 00:01` raised as HIGH at night (MEDIUM by day); repeated frames do not re-alert unless severity escalates; drone battery/altitude/geofence breaches flagged |
| R3 | Frame-by-frame index and conversational follow-up | Query by time window (incl. overnight wrap), object, location, free text; answer "how many times", "what objects", "any alerts"; produce a one-sentence summary |

## Out of scope (prototype)
Real pixel-level detection (simulated by captions; `vlm.py` shows the real path), multi-drone fleets,
authentication, notification delivery channels, video clip storage.

## Success metrics (for a production version)
Alert precision/recall on labelled incidents; median time from event to alert; alerts per patrol-hour
(fatigue); query latency at 10^6 frames.
