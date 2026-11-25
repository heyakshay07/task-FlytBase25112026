from drone_analyst.models import Severity
from tests.conftest import make_frame


def test_sample_log_lines(full_run):
    _, results = full_run
    logs = [l for r in results for l in r.logs]
    assert "Blue Ford F150 spotted at garage, 12:00." in logs


def test_sample_alert(full_run):
    a, _ = full_run
    assert "[HIGH] Person loitering at Main Gate, 00:01." in [str(x) for x in a.index.alerts()]


def test_every_frame_indexed_with_telemetry(full_run):
    a, _ = full_run
    assert a.index.stats()["frames"] == 30
    f = a.index.frames(tod_start="00:01", tod_end="00:01")[0]
    assert f["location"] == "Main Gate" and f["altitude"] > 0


def test_query_by_object_truck(full_run):
    a, _ = full_run
    frames = a.index.frames(obj="truck")
    assert len(frames) == 9 and all("F150" in f["description"] for f in frames[:8])


def test_query_by_time_range_and_wraparound_night(full_run):
    a, _ = full_run
    assert [f["hhmm"] for f in a.index.frames(tod_start="00:00", tod_end="00:05")] == ["00:00", "00:01", "00:02", "00:03", "00:05"]
    night = {f["hhmm"] for f in a.index.frames(tod_start="22:00", tod_end="05:00", limit=100)}
    assert {"00:01", "22:30", "23:10"} <= night and "12:00" not in night


def test_query_by_location_and_combined_filters(full_run):
    a, _ = full_run
    assert len(a.index.frames(location="garage")) == 5
    assert [f["hhmm"] for f in a.index.frames(obj="truck", location="garage", tod_start="07:00", tod_end="08:00")] == ["07:46"]


def test_full_text_and_semantic_search(full_run):
    a, _ = full_run
    assert a.index.text_search("hedge")[0]["hhmm"] == "10:00"
    top = [h["hhmm"] for h in a.index.semantic_search("someone trying to break in", 3)]
    assert "16:22" in top or "16:20" in top


def test_visit_tracking_three_entries(full_run):
    a, _ = full_run
    v = a.index.visits("truck")
    assert len(v) == 3 and v[0]["end_ts"].endswith("08:30:00") and v[2]["end_ts"] is None


def test_qa_how_many_times(full_run):
    a, _ = full_run
    assert "entered 3 time" in a.ask("How many times did the blue truck enter?").text


def test_qa_objects_in_video(full_run):
    a, _ = full_run
    t = a.ask("What objects were in the video?").text
    for word in ("blue ford f150", "white delivery van", "black suv", "fox", "ladder"):
        assert word in t


def test_qa_alert_filters(full_run):
    a, _ = full_run
    t = a.ask("show critical alerts").text
    assert "climbing" in t and "tampering" in t and "loitering" not in t
    assert "loitering" in a.ask("any suspicious activity at night?").text


def test_qa_time_range_and_last_seen(full_run):
    a, _ = full_run
    assert "Fox crossing" in a.ask("what happened between 00:00 and 01:00").text
    assert "00:03" in a.ask("when was the last time a person was at the gate between 00:00 and 01:00").text
    assert "23:30" in a.ask("when was the last time the truck was at the garage").text
    assert "07:45" in a.ask("when was the first time the truck was seen").text


def test_qa_summary_is_one_sentence_plus_details(full_run):
    a, _ = full_run
    s = a.summary()
    assert s.split("\n")[0].startswith("Across 30 frames") and "entered 3 times" in s and "CRITICAL" in s


def test_context_stays_bounded_and_tracks_on_site(full_run):
    a, _ = full_run
    assert len(a.ctx.prompt_context()) <= 3000
    assert len(a.ctx.recent) == 8
    assert "blue ford f150" in {r.key for r in a.ctx.on_site()}   # last seen parked, never exited after 19:00


def test_empty_agent_summary(agent):
    assert agent.summary() == "No frames processed yet."


def test_persistence_roundtrip(project_tmp_path):
    from drone_analyst.agent import SecurityAnalystAgent
    from drone_analyst.indexer import FrameIndex
    from drone_analyst.simulator import build_frames
    p = str(project_tmp_path / "d.db")
    a = SecurityAnalystAgent(FrameIndex(p)); a.ingest_many(build_frames()); a.index.close()
    b = SecurityAnalystAgent(FrameIndex(p))
    try:
        assert "entered 3 time" in b.ask("how many times did the blue truck enter").text
        assert b.index.semantic_search("ladder", 1)[0]["hhmm"] == "16:20"   # vectors rebuilt on reopen
    finally:
        b.index.close()
