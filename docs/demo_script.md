# Demo videos - shot list and voiceover script

The brief requires **screen recordings with your own voiceover** (videos without voiceover are
penalised). Record 3 short videos (~2-3 min each). Terminal font large, dark theme. Commands are exact.

## Video 1 - Processing, logs and real-time alerts (R1, R2)
**Show:** `cat data/sample_feed.jsonl | head -3`, then `python -m drone_analyst run --delay 0.4`

> "This is a Drone Security Analyst agent for a docked drone that patrols a property. Each line of this
> feed is one frame: timestamp, telemetry - location, altitude, battery - and a caption of what the
> camera sees. I simulate captions with text, as the brief allows, and I've also included a bridge for
> real video with BLIP.
> Now I run the pipeline live. Each frame is parsed into objects with a stable identity, logged with
> context - here: 'Blue Ford F150 spotted at garage, 12:00'. At 00:01 a person in a dark hoodie is
> loitering at the main gate: HIGH alert because it's night. The same behaviour at midday would be
> MEDIUM. Notice the next frames don't re-alert - cooldown, unless severity escalates.
> At 11:58 the blue truck enters a second time, so the repeat-visitor insight fires. At 14:30 the drone
> itself leaves the geofence, then exceeds its altitude ceiling. At 16:20 the intrusion sequence -
> climbing the fence with a ladder, running, tampering with the back door - gives CRITICAL alerts.
> At 22:30 an unknown SUV idles after hours, with low drone battery."

## Video 2 - Frame-by-frame index and follow-up Q&A (R3, bonus)
**Show:** `python -m drone_analyst chat` then ask, in order:
`show all truck events` / `how many times did the blue truck enter?` / `what objects were in the video?` /
`what happened between 00:00 and 01:00` / `any critical alerts?` / `anything suspicious at night?` /
`someone trying to break in` ; then `python -m drone_analyst summary`.
Then show SQL: `sqlite3 output/drone.db "select ts,location,description from frames limit 5"` and
`sqlite3 output/drone.db "select label,visit_no,start_ts,end_ts from visits"`.

> "Every frame is indexed in SQLite with its timestamp, telemetry and the structured detections, plus a
> full-text index and a small vector index. So I can query by object - 'all truck events' - by time
> window, including overnight windows that wrap midnight, by location, or by free text. The visits
> table tracks enter and exit, which is how 'entered three times' is computed. Last, the summary - one
> sentence plus the incidents ranked by severity."

## Video 3 - Context management, scalability, tests, AI tooling (reasoning, QA)
**Show:** `python -c "from drone_analyst.agent import *; from drone_analyst.simulator import *; a=SecurityAnalystAgent(); a.ingest_many(build_frames()); print(a.ctx.prompt_context())"`,
`python scripts/scalability_test.py --frames 50000`, `python -m pytest -v`, optionally the Groq agent
(`ask_llm`, see README), then `docs/ai_tools_log.md`.

> "Context management: the agent doesn't keep all frames in memory. It keeps one record per distinct
> object, dwell timers, a rolling window and hourly digests, and renders a capped snapshot for an LLM.
> That's why context size stays flat from 10 thousand to 50 thousand frames in this test, at about
> 4,800 frames a second, with queries in tens of milliseconds. Semantic search is brute force, 178 ms
> at 50 thousand, so that is what I'd replace first. 46 tests pass. [Explain which parts AI generated,
> what you changed, and one bug it caught.]"

## Tips
Say your name and the role at the start; keep each video under ~3 minutes; share via Google Drive with
**view access** and put links in the report and email.

## PowerShell walkthrough for the supplied city-traffic clip

The clip is an optional real-video demonstration. The assignment's core test scenario remains the
simulated feed above. The BLIP captions missed some visible details; selected motorcycle, pedestrian,
crowd, and water-tower notes in `data/city_traffic_real.jsonl` were added after reviewing frames.
Say this clearly in the voice-over. Frame counts are not counts of unique objects.

### Demo 1 - video processing and indexed observations

```powershell
Get-Content data\city_traffic_real.jsonl -TotalCount 3
python -m drone_analyst run --feed data/city_traffic_real.jsonl --db output/city_traffic_complete.db --quiet
python -m drone_analyst query --db output/city_traffic_complete.db --object car --limit 100
```

Voice-over: “The clip is sampled about once per second. BLIP writes a caption for each sampled
frame, then the pipeline stores the frame and parsed observations in SQLite. The model missed some
small details, so I reviewed selected frames and marked those notes as manual. The results show
frames containing an object; they are not a count of unique cars or motorcycles.”

### Demo 2 - follow-up questions

```powershell
python -m drone_analyst chat --db output/city_traffic_complete.db
```

Ask about cars, motorcycles, pedestrians, water towers, and the 14:00-14:01 interval. Then enter a
blank line to exit chat before running any other PowerShell command. Explain that truck/van queries
with no matches mean the index has no matching captions for this clip.

### Demo 3 - tests and scalability

```powershell
$runTmp = Join-Path $PWD ('.pytest_demo_' + [guid]::NewGuid().ToString('N'))
python -m pytest -v --basetemp $runTmp
python scripts\scalability_test.py --frames 50 --db output\demo_scale_50.db
python scripts\scalability_test.py --frames 100 --db output\demo_scale_100.db
python scripts\scalability_test.py --frames 500 --db output\demo_scale_500.db
```

Use your own voice-over, keep the video links private/viewable as required, and replace the pending
links in the report only after the recordings and repository are ready.
