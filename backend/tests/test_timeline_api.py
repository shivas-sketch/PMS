from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_parking_service, get_timeline_service
from app.main import app
from app.services.parking_service import ParkingService
from app.services.timeline_service import TimelineService
from tests.fakes import FakeParkingRepository, FakeTimelineRepository


@pytest.fixture
def client_with_capacity():
    def _make(capacity: int = 100):
        repository = FakeParkingRepository(total_capacity=capacity)
        service = ParkingService(repository)
        timeline_service = TimelineService(repository, FakeTimelineRepository(repository))
        app.dependency_overrides[get_parking_service] = lambda: service
        app.dependency_overrides[get_timeline_service] = lambda: timeline_service
        return TestClient(app)

    yield _make
    app.dependency_overrides.pop(get_parking_service, None)
    app.dependency_overrides.pop(get_timeline_service, None)


def _add_vehicle(client, vehicle_number="KA01AB1234", **extra):
    payload = {"vehicleNumber": vehicle_number, "wheelCategory": 4, "vehicleType": "Car"}
    payload.update(extra)
    resp = client.post("/api/parking/vehicles", json=payload)
    assert resp.status_code == 201
    return resp.json()


def _setup_area_with_slots(client, area_name="A1", num_slots=3):
    area_resp = client.post("/api/parking/areas", json={"name": area_name, "areaType": "GROUND"})
    area_id = area_resp.json()["areaId"]
    for i in range(1, num_slots + 1):
        client.post(f"/api/parking/areas/{area_id}/slots", json={"slotNumber": str(i)})
    return area_id


# --- timeline creation & retrieval --------------------------------------

def test_add_vehicle_creates_assigned_for_parking_event(client_with_capacity):
    with client_with_capacity() as client:
        session = _add_vehicle(client)
        assert session["currentStage"] == "ASSIGNED_FOR_PARKING"

        timeline = client.get(f"/api/parking/sessions/{session['sessionId']}/timeline").json()
        assert timeline["count"] == 1
        assert timeline["events"][0]["stage"] == "ASSIGNED_FOR_PARKING"
        assert timeline["events"][0]["displayName"] == "Assigned for parking"


def test_add_vehicle_with_slot_also_creates_parked_event(client_with_capacity):
    with client_with_capacity() as client:
        area_id = _setup_area_with_slots(client)
        slots = client.get(f"/api/parking/areas/{area_id}/slots").json()["slots"]
        session = _add_vehicle(client, areaId=area_id, slotId=slots[0]["slotId"])
        assert session["currentStage"] == "PARKED"

        timeline = client.get(f"/api/parking/sessions/{session['sessionId']}/timeline").json()
        stages = [e["stage"] for e in timeline["events"]]
        assert stages == ["ASSIGNED_FOR_PARKING", "PARKED"]


def test_timeline_sorted_chronologically(client_with_capacity):
    with client_with_capacity() as client:
        area_id = _setup_area_with_slots(client)
        slots = client.get(f"/api/parking/areas/{area_id}/slots").json()["slots"]
        session = _add_vehicle(client)
        session_id = session["sessionId"]
        client.post(f"/api/parking/sessions/{session_id}/accept-parking-request")
        client.patch(
            f"/api/parking/vehicles/{session['vehicleNumber']}/slot",
            json={"slotId": slots[0]["slotId"]},
        )
        client.post(f"/api/parking/sessions/{session_id}/mark-parked")

        timeline = client.get(f"/api/parking/sessions/{session_id}/timeline").json()
        timestamps = [e["timestamp"] for e in timeline["events"]]
        assert timestamps == sorted(timestamps)
        assert [e["stage"] for e in timeline["events"]] == [
            "ASSIGNED_FOR_PARKING",
            "PARKING_REQUEST_ACCEPTED",
            "PARKED",
        ]


def test_duplicate_stages_are_all_recorded(client_with_capacity):
    with client_with_capacity() as client:
        session = _add_vehicle(client)
        session_id = session["sessionId"]
        client.post(f"/api/parking/sessions/{session_id}/accept-parking-request")
        client.post(f"/api/parking/sessions/{session_id}/accept-parking-request")

        timeline = client.get(f"/api/parking/sessions/{session_id}/timeline").json()
        stages = [e["stage"] for e in timeline["events"]]
        assert stages.count("PARKING_REQUEST_ACCEPTED") == 2
        assert timeline["count"] == 3


def test_generic_timeline_post_endpoint(client_with_capacity):
    with client_with_capacity() as client:
        session = _add_vehicle(client)
        session_id = session["sessionId"]
        resp = client.post(
            f"/api/parking/sessions/{session_id}/timeline",
            json={"stage": "PARKING_REQUEST_ACCEPTED", "notes": "manual note"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["stage"] == "PARKING_REQUEST_ACCEPTED"
        assert body["notes"] == "manual note"
        assert body["sessionId"] == session_id
        assert body["vehicleNumber"] == session["vehicleNumber"]


def test_timeline_for_invalid_session_returns_404(client_with_capacity):
    with client_with_capacity() as client:
        resp = client.get("/api/parking/sessions/PS-999999/timeline")
        assert resp.status_code == 404
        assert resp.json()["error"] == "PARKING_SESSION_NOT_FOUND"


def test_timeline_post_invalid_stage_returns_422(client_with_capacity):
    with client_with_capacity() as client:
        session = _add_vehicle(client)
        resp = client.post(
            f"/api/parking/sessions/{session['sessionId']}/timeline",
            json={"stage": "NOT_A_REAL_STAGE"},
        )
        assert resp.status_code == 422


def test_timeline_post_for_invalid_session_returns_404(client_with_capacity):
    with client_with_capacity() as client:
        resp = client.post(
            "/api/parking/sessions/PS-999999/timeline",
            json={"stage": "PARKED"},
        )
        assert resp.status_code == 404


# --- full valet workflow -------------------------------------------------

def test_full_delivery_workflow_exits_vehicle_and_frees_capacity(client_with_capacity):
    with client_with_capacity() as client:
        area_id = _setup_area_with_slots(client)
        slots = client.get(f"/api/parking/areas/{area_id}/slots").json()["slots"]
        session = _add_vehicle(client, areaId=area_id, slotId=slots[0]["slotId"])
        session_id = session["sessionId"]

        capacity_before = client.get("/api/parking/capacity").json()
        assert capacity_before["occupiedSlots"] == 1

        client.post(f"/api/parking/sessions/{session_id}/request-delivery")
        client.post(f"/api/parking/sessions/{session_id}/assign-for-delivery", json={"valetName": "Ravi"})
        client.post(f"/api/parking/sessions/{session_id}/accept-delivery")

        picked_up_resp = client.post(f"/api/parking/sessions/{session_id}/picked-up")
        assert picked_up_resp.status_code == 200

        # Slot should be freed immediately on pickup, but global occupancy
        # must NOT drop yet (vehicle is still on-site with the valet).
        slot_after_pickup = client.get(f"/api/parking/areas/{area_id}/slots").json()["slots"][0]
        assert slot_after_pickup["status"] == "AVAILABLE"
        capacity_after_pickup = client.get("/api/parking/capacity").json()
        assert capacity_after_pickup["occupiedSlots"] == 1

        client.post(f"/api/parking/sessions/{session_id}/arrived")
        client.post(f"/api/parking/sessions/{session_id}/manual-override")
        delivered_resp = client.post(f"/api/parking/sessions/{session_id}/delivered")
        assert delivered_resp.status_code == 200
        assert delivered_resp.json()["stage"] == "DELIVERED"

        # Vehicle session must now be EXITED and capacity released exactly once.
        vehicle = client.get(f"/api/parking/vehicles/{session['vehicleNumber']}").json()
        assert vehicle["status"] == "EXITED"
        assert vehicle["currentStage"] == "DELIVERED"

        capacity_after_delivery = client.get("/api/parking/capacity").json()
        assert capacity_after_delivery["occupiedSlots"] == 0
        assert capacity_after_delivery["availableSlots"] == capacity_after_delivery["totalCapacity"]

        timeline = client.get(f"/api/parking/sessions/{session_id}/timeline").json()
        stages = [e["stage"] for e in timeline["events"]]
        assert stages == [
            "ASSIGNED_FOR_PARKING",
            "PARKED",
            "REQUESTED_FOR_DELIVERY",
            "ASSIGNED_FOR_DELIVERY",
            "DELIVERY_REQUEST_ACCEPTED",
            "PICKED_UP",
            "ARRIVED",
            "REQUESTED_FOR_MANUAL_OVERRIDE",
            "DELIVERED",
        ]


def test_delivered_without_prior_pickup_still_releases_slot_once(client_with_capacity):
    with client_with_capacity() as client:
        area_id = _setup_area_with_slots(client)
        slots = client.get(f"/api/parking/areas/{area_id}/slots").json()["slots"]
        session = _add_vehicle(client, areaId=area_id, slotId=slots[0]["slotId"])
        session_id = session["sessionId"]

        # Skip pickup entirely - go straight to delivered.
        client.post(f"/api/parking/sessions/{session_id}/delivered")

        capacity = client.get("/api/parking/capacity").json()
        assert capacity["occupiedSlots"] == 0
        assert capacity["availableSlots"] == capacity["totalCapacity"]

        area = client.get("/api/parking/areas").json()["areas"][0]
        assert area["occupiedSlots"] == 0
        assert area["availableSlots"] == area["totalSlots"]


def test_delivered_on_already_exited_session_returns_409(client_with_capacity):
    with client_with_capacity() as client:
        session = _add_vehicle(client)
        session_id = session["sessionId"]
        client.post(f"/api/parking/vehicles/{session['vehicleNumber']}/exit")

        resp = client.post(f"/api/parking/sessions/{session_id}/delivered")
        assert resp.status_code == 409
        assert resp.json()["error"] == "VEHICLE_ALREADY_EXITED"


def test_picked_up_on_vehicle_with_no_slot_does_not_error(client_with_capacity):
    with client_with_capacity() as client:
        session = _add_vehicle(client)
        session_id = session["sessionId"]
        resp = client.post(f"/api/parking/sessions/{session_id}/picked-up")
        assert resp.status_code == 200
        assert resp.json()["stage"] == "PICKED_UP"


def test_mark_parked_without_slot_returns_422(client_with_capacity):
    with client_with_capacity() as client:
        session = _add_vehicle(client)
        session_id = session["sessionId"]
        resp = client.post(f"/api/parking/sessions/{session_id}/mark-parked")
        assert resp.status_code == 422
        assert resp.json()["error"] == "PARKING_SLOT_REQUIRED"


def test_generic_parked_post_without_slot_returns_422(client_with_capacity):
    with client_with_capacity() as client:
        session = _add_vehicle(client)
        session_id = session["sessionId"]
        resp = client.post(
            f"/api/parking/sessions/{session_id}/timeline",
            json={"stage": "PARKED"},
        )
        assert resp.status_code == 422
        assert resp.json()["error"] == "PARKING_SLOT_REQUIRED"


def test_manual_override_does_not_delete_prior_events(client_with_capacity):
    with client_with_capacity() as client:
        session = _add_vehicle(client)
        session_id = session["sessionId"]
        client.post(f"/api/parking/sessions/{session_id}/accept-parking-request")
        client.post(f"/api/parking/sessions/{session_id}/manual-override")

        timeline = client.get(f"/api/parking/sessions/{session_id}/timeline").json()
        stages = [e["stage"] for e in timeline["events"]]
        assert stages == ["ASSIGNED_FOR_PARKING", "PARKING_REQUEST_ACCEPTED", "REQUESTED_FOR_MANUAL_OVERRIDE"]
