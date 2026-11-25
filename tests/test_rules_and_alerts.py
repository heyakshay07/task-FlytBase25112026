from tests.conftest import make_frame


def alerts_for(agent, *frames):
    out = []
    for f in frames:
        out += agent.ingest(f).alerts
    return out


def test_person_loitering_at_midnight_triggers_high_alert(agent):
    (a,) = alerts_for(agent, make_frame(1, "00:01", "Person in dark hoodie loitering near main gate."))
    assert (a.severity.name, a.rule, str(a)) == ("HIGH", "loitering", "[HIGH] Person loitering at Main Gate, 00:01.")


def test_same_loitering_by_day_is_only_medium(agent):
    (a,) = alerts_for(agent, make_frame(1, "14:00", "Person loitering near main gate."))
    assert a.severity.name == "MEDIUM"


def test_dwell_based_loitering_without_keyword(agent):
    frames = [make_frame(i, f"14:0{i}", "Person in grey cap standing at main gate.") for i in range(0, 5)]
    out = alerts_for(agent, *frames)
    assert len(out) == 1 and out[0].rule == "loitering" and out[0].hhmm == "14:03"   # 3 min dwell


def test_dwell_resets_after_gap(agent):
    out = alerts_for(agent,
                     make_frame(1, "14:00", "Person in grey cap standing at main gate."),
                     make_frame(2, "15:00", "Person in grey cap standing at main gate."),
                     make_frame(3, "15:01", "Person in grey cap standing at main gate."))
    assert out == []


def test_unknown_vehicle_at_night_high_but_resident_not_flagged(agent):
    a = alerts_for(agent, make_frame(1, "23:00", "Black SUV idling near main gate."))
    assert [x.rule for x in a] == ["unknown_vehicle_night"] and a[0].severity.name == "HIGH"


def test_resident_truck_at_night_is_not_unknown(agent):
    out = alerts_for(agent, make_frame(1, "23:00", "Blue Ford F150 enters through main gate."))
    assert not any(a.rule == "unknown_vehicle_night" for a in out)


def test_vehicle_leaving_at_night_not_flagged(agent):
    assert alerts_for(agent, make_frame(1, "23:10", "Black SUV drives away from main gate.")) == []


def test_repeat_vehicle_alert_on_second_entry_same_day(agent):
    out = alerts_for(agent,
                     make_frame(1, "07:45", "Blue Ford F150 enters through main gate."),
                     make_frame(2, "08:30", "Blue Ford F150 leaves through main gate."),
                     make_frame(3, "12:00", "Blue Ford F150 enters through main gate."))
    assert [a.message for a in out] == ["Blue Ford F150 has entered 2 times today"]


def test_repeat_counter_resets_next_day(agent):
    out = alerts_for(agent,
                     make_frame(1, "07:45", "Blue Ford F150 enters.", day="2026-11-24"),
                     make_frame(2, "08:30", "Blue Ford F150 leaves.", day="2026-11-24"),
                     make_frame(3, "07:45", "Blue Ford F150 enters.", day="2026-11-25"))
    assert out == []


def test_climbing_is_critical_and_beats_restricted_zone(agent):
    out = alerts_for(agent, make_frame(1, "16:20", "Person climbing over perimeter fence.", loc="Perimeter Fence"))
    assert [(a.rule, a.severity.name) for a in out] == [("suspicious_activity", "CRITICAL")]  # collapsed


def test_person_in_restricted_zone_daytime(agent):
    out = alerts_for(agent, make_frame(1, "11:00", "Person walking along the fence.", loc="Perimeter Fence"))
    assert out[0].rule == "restricted_zone"


def test_animal_triggers_nothing(agent):
    assert alerts_for(agent, make_frame(1, "00:05", "Fox crossing the lawn.", loc="Perimeter Fence")) == []


def test_cooldown_suppresses_repeats_but_allows_escalation(agent):
    out = alerts_for(agent,
                     make_frame(1, "00:01", "Person in dark hoodie standing at main gate."),   # night presence MEDIUM
                     make_frame(2, "00:02", "Person in dark hoodie standing at main gate."),   # suppressed
                     make_frame(3, "00:03", "Person in dark hoodie loitering at main gate."))  # escalates to HIGH
    assert [a.severity.name for a in out] == ["MEDIUM", "HIGH"]


def test_telemetry_alerts(agent):
    out = alerts_for(agent, make_frame(1, "12:00", "Quiet.", battery_pct=8, altitude_m=75, x=300))
    assert {a.entity_key for a in out} == {"drone:battery", "drone:altitude", "drone:geofence"}
    assert max(a.severity for a in out).name == "CRITICAL"


def test_healthy_telemetry_is_silent(agent):
    assert alerts_for(agent, make_frame(1, "12:00", "Quiet.")) == []
