# Assignment Validation and Completion Status

This file records the latest local checks for the FlytBase AI Engineer assignment. It separates the simulated prototype, the supplemental real-video run, and submission tasks that require the candidate's external accounts or recordings.

## 1. Automated tests

Command used on Windows:

```powershell
python -m pytest -v
```

Result: **46 passed in 1.06 seconds**. The persistence test now creates its temporary database under the project workspace, avoiding the inaccessible `%TEMP%\pytest-of-akshay` directory. Pytest still emits a cache warning because Windows denied access to `.pytest_cache`; it does not affect the test results.

## 2. Real-video database check

Database: `output/city_traffic_complete.db`  
Feed: `data/city_traffic_real.jsonl`  
Frames: **26**, sampled approximately once per second across the 26-second clip.

| Query | Verified result |
|---|---|
| Objects | Car captions in 15 frames; motorcycle captions in 6 frames; person caption in 2 frames |
| Car events | 15 matching frames; first sampled sighting at 14:00:00 |
| Motorcycle events | 6 matching frames; last sampled sighting at 14:00:15 |
| Person events | 2 matching frames, 14:00:17 and 14:00:20 |
| 14:00–14:01 | 26 frames returned |
| Water tower | 2 manually reviewed frame descriptions, at 14:00:17 and 14:00:20 |
| Crowd / pedestrians | 2 manually reviewed descriptions of a crowd near roadside shops |
| Truck / van | No matching captions in this clip |
| Alerts | No alert rules matched this benign traffic clip |

**Interpretation:** frame counts are not counts of unique physical objects. BLIP generated the base captions and missed motorcycles, pedestrians, and water towers in the supplied clip. Those details were manually added to selected frame descriptions after visual review. This database is suitable for demonstrating indexing and follow-up queries; it is not evidence of complete automatic object detection or tracking. “Roadside shops” does not establish that the location is a market.

## 3. Scalability checks

The Windows-compatible benchmark was run with a fresh SQLite database at each size. Results are local to this machine; the small-run throughput is sensitive to timing overhead.

| Frames | Ingest time | Throughput | DB size | Peak working set | Truck query | Time-range query | FTS query | Semantic query |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 50 | 0.02 s | 2,019 frames/s | 0.1 MB | 20.4 MB | 0.3 ms | 0.4 ms | 0.2 ms | 0.7 ms |
| 100 | 0.03 s | 3,354 frames/s | 0.1 MB | 20.5 MB | 0.3 ms | 0.4 ms | 0.2 ms | 0.8 ms |
| 500 | 0.11 s | 4,728 frames/s | 0.3 MB | 22.5 MB | 0.4 ms | 0.5 ms | 0.2 ms | 2.0 ms |

Raw JSON outputs are in `output/scale_50.json`, `output/scale_100.json`, and `output/scale_500.json`; each run also created its matching SQLite database.

## 4. Assignment completion checklist

- [x] Feature specification with owner value and key requirements.
- [x] Architecture write-up and diagrams.
- [x] Python prototype for simulated telemetry and caption frames.
- [x] Structured parsing, context, logging, rule-based alerts, and SQLite/FTS indexing.
- [x] Follow-up Q&A and video summary features.
- [x] 46 automated test cases; latest local run passed.
- [x] 50-, 100-, and 500-frame scalability runs.
- [ ] Refresh the report PDF with the latest tests, benchmark, and real-video limitations.
- [ ] Replace repository and demo-video placeholders with real, accessible links.
- [ ] Personalize the AI-tool section to match the candidate's actual workflow.
- [ ] Record and add the required screen demonstrations with the candidate's voice-over.
- [ ] Verify private repository access and the required contributor invitation.

The workspace has no `.git` directory, so no remote repository or contributor invitation can be verified locally. The `videos/` folder contains the source traffic clip but no screen recordings. The PDF generator requires optional `reportlab` and `pillow` packages; rebuild instructions are in the README. The repository/video links, contributor invitation, and voice-over recordings require the candidate's accounts and participation.
