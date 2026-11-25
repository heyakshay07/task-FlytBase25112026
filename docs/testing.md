# Testing

Run: `python -m pytest -q` (46 tests, ~1 s, no network or API key). Raw output: `pytest_output.txt`.

| File | Tests | What it proves |
|---|---|---|
| `test_perception.py` | 13 | truck logged as `truck` / `blue ford f150`; "F-150 pickup truck" maps to the same entity; clothing descriptor + loitering; "No activity" -> nothing; negation; plate identity; count + suspicious object; courier "leaves package" is not an exit; driver "exits vehicle" is not a vehicle exit; vehicle categories (van, SUV, bike, car) |
| `test_rules_and_alerts.py` | 15 | midnight loiterer -> `[HIGH] Person loitering at Main Gate, 00:01.`; same by day -> MEDIUM; dwell-based loitering at exactly 3 min; dwell resets after a 1-hour gap; unknown vs resident vehicle at night; leaving vehicle not flagged; repeat-entry alert; counter resets next day; CRITICAL beats restricted-zone (collapse); restricted zone by day; animals silent; cooldown vs escalation; battery/altitude/geofence; healthy telemetry silent |
| `test_indexing_and_qa.py` | 16 | sample log + alert strings; all 30 frames indexed with telemetry; object / time / wrap-around-night / location / combined queries; FTS + semantic search; visit tracking (3 entries, last still on site); Q&A (counts, objects, alert filters, time range, first/last seen); summary; bounded context; empty-agent behaviour; DB persistence round-trip |
| `test_llm_tools.py` | 2 | LangChain tools return grounded results; missing `GROQ_API_KEY` raises |

## Scenarios (dynamic input / emergency response)
Simulated day (`data/sample_feed.jsonl`): midnight loiterer; resident truck 3x; delivery van; gardener;
unknown parked car with plate; drone beyond geofence then above altitude ceiling; **intrusion
sequence 16:20-16:22** (fence climb with ladder -> run -> tamper with back door); after-hours
unknown SUV with low drone battery.

## Bugs the tests/runs caught during development
* Built-in `hash()` made the semantic index non-deterministic across runs -> switched to `crc32`.
* `F-150` was tokenised so the vehicle phrase broke -> normalised before tokenising.
* "Courier leaves package" and "driver exits vehicle" were read as exits -> new activity patterns.
* "When was the last time ..." ignored location/time filters -> passed through.
* Alert spam (same SUV every frame) -> cooldown with escalation, and no alert for a leaving vehicle.
* LLM context truncation cut the *newest* data -> section budgets (entities trimmed first).

## Not covered
Real VLM output, live Groq calls, concurrent writers, multi-day soak test.
