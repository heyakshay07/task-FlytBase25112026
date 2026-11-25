import pytest

from drone_analyst.perception import TextPerceiver
from tests.conftest import make_frame

P = TextPerceiver()


def dets(text):
    return P.perceive(make_frame(1, "12:00", text))


def test_blue_ford_f150_logged_as_truck():
    (d,) = dets("Blue Ford F150 enters through main gate.")
    assert (d.kind, d.category, d.entity_key, d.activity) == ("vehicle", "truck", "blue ford f150", "entering")


def test_same_truck_different_wording_same_entity():
    a = dets("Blue Ford F150 parked at garage.")[0]
    b = dets("A blue F-150 pickup truck leaves.")[0]
    assert a.entity_key == b.entity_key == "blue ford f150"


def test_person_with_clothing_descriptor_and_loitering():
    (d,) = dets("Person in dark hoodie loitering near main gate, looking at the lock.")
    assert d.kind == "person" and d.activity == "loitering" and d.entity_key == "person:dark hoodie"


def test_no_activity_frames_produce_no_detections():
    assert dets("Empty driveway, gate closed. No activity.") == []


def test_negation_suppresses_person():
    ds = dets("Unknown black SUV idling near main gate, no one exits.")
    assert [d.kind for d in ds] == ["vehicle"] and ds[0].activity == "idling"


def test_plate_becomes_identity():
    (d,) = dets("Red Honda Civic plate MH12XY9999 parked in lot.")
    assert d.entity_key == "plate:mh12xy9999" and d.attrs["plate"] == "MH12XY9999"


def test_count_and_suspicious_object():
    ds = dets("Two people climbing over perimeter fence with a ladder.")
    person = next(d for d in ds if d.kind == "person")
    assert person.count == 2 and person.activity == "climbing"
    assert any(d.kind == "object" and d.attrs["suspicious"] for d in ds)


def test_courier_leaving_package_is_not_exiting():
    ds = dets("Courier in white uniform leaves package at front door.")
    assert ds[0].activity == "working"


def test_driver_exits_vehicle_is_not_vehicle_exit():
    ds = dets("Blue Ford F150 parked at garage, driver exits vehicle.")
    assert {d.kind: d.activity for d in ds} == {"vehicle": "parked", "person": "alighting"}


@pytest.mark.parametrize("text,cat", [("white delivery van arrives", "van"), ("black SUV idling", "suv"),
                                       ("red motorcycle parked", "bike"), ("Tesla Model 3 enters", "car")])
def test_vehicle_categories(text, cat):
    assert dets(text)[0].category == cat
