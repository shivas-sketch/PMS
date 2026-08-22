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


def test_add_vehicle_returns_201_and_session(client_with_capacity):
    with client_with_capacity() as client:
        response = client.post(
            "/api/parking/vehicles",
            json={"vehicleNumber": "TS09AB1234", "wheelCategory": 4, "vehicleType": "SUV"},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["vehicleNumber"] == "TS09AB1234"
        assert body["status"] == "ACTIVE"
        assert body["sessionId"] == "PS-000001"
        assert body["exitTime"] is None


def test_duplicate_active_vehicle_returns_409(client_with_capacity):
    with client_with_capacity() as client:
        payload = {"vehicleNumber": "TS09AB1234", "wheelCategory": 4, "vehicleType": "SUV"}
        client.post("/api/parking/vehicles", json=payload)
        response = client.post("/api/parking/vehicles", json=payload)
        assert response.status_code == 409
        assert response.json()["error"] == "VEHICLE_ALREADY_ACTIVE"


def test_full_parking_returns_409(client_with_capacity):
    with client_with_capacity(capacity=1) as client:
        client.post(
            "/api/parking/vehicles",
            json={"vehicleNumber": "TS09AB1234", "wheelCategory": 4, "vehicleType": "SUV"},
        )
        response = client.post(
            "/api/parking/vehicles",
            json={"vehicleNumber": "AP16CD5678", "wheelCategory": 4, "vehicleType": "Sedan"},
        )
        assert response.status_code == 409
        assert response.json()["error"] == "PARKING_FULL"


def test_get_capacity(client_with_capacity):
    with client_with_capacity(capacity=100) as client:
        client.post(
            "/api/parking/vehicles",
            json={"vehicleNumber": "TS09AB1234", "wheelCategory": 4, "vehicleType": "SUV"},
        )
        response = client.get("/api/parking/capacity")
        assert response.status_code == 200
        body = response.json()
        assert body == {"totalCapacity": 100, "availableSlots": 99, "occupiedSlots": 1}


def test_list_active_vehicles(client_with_capacity):
    with client_with_capacity() as client:
        client.post(
            "/api/parking/vehicles",
            json={"vehicleNumber": "TS09AB1234", "wheelCategory": 4, "vehicleType": "SUV"},
        )
        client.post(
            "/api/parking/vehicles",
            json={"vehicleNumber": "TS10XY9087", "wheelCategory": 2, "vehicleType": "Bike"},
        )
        response = client.get("/api/parking/vehicles")
        assert response.status_code == 200
        body = response.json()
        assert body["count"] == 2
        plates = {v["vehicleNumber"] for v in body["vehicles"]}
        assert plates == {"TS09AB1234", "TS10XY9087"}


def test_get_vehicle_by_number_not_found_returns_404(client_with_capacity):
    with client_with_capacity() as client:
        response = client.get("/api/parking/vehicles/ZZ99ZZ9999")
        assert response.status_code == 404
        assert response.json()["error"] == "VEHICLE_NOT_FOUND"


def test_exit_flow_and_double_exit(client_with_capacity):
    with client_with_capacity() as client:
        client.post(
            "/api/parking/vehicles",
            json={"vehicleNumber": "TS09AB1234", "wheelCategory": 4, "vehicleType": "SUV"},
        )

        exit_response = client.post("/api/parking/vehicles/TS09AB1234/exit")
        assert exit_response.status_code == 200
        assert exit_response.json()["status"] == "EXITED"

        capacity = client.get("/api/parking/capacity").json()
        assert capacity["availableSlots"] == 100
        assert capacity["occupiedSlots"] == 0

        double_exit = client.post("/api/parking/vehicles/TS09AB1234/exit")
        assert double_exit.status_code == 409
        assert double_exit.json()["error"] == "VEHICLE_ALREADY_EXITED"

        capacity_after = client.get("/api/parking/capacity").json()
        assert capacity_after["availableSlots"] == 100


def test_search_vehicle_by_number_returns_current_status(client_with_capacity):
    with client_with_capacity() as client:
        client.post(
            "/api/parking/vehicles",
            json={"vehicleNumber": "ts09ab1234", "wheelCategory": 4, "vehicleType": "SUV"},
        )
        response = client.get("/api/parking/vehicles/ts09ab1234")
        assert response.status_code == 200
        body = response.json()
        assert body["vehicleNumber"] == "TS09AB1234"
        assert body["status"] == "ACTIVE"


# --- slot reassignment tests -----------------------------------------------

def _setup_area_with_slots(client, area_name="A1", num_slots=5):
    area_resp = client.post(
        "/api/parking/areas",
        json={"name": area_name, "areaType": "GROUND", "description": "Test area"},
    )
    area_id = area_resp.json()["areaId"]
    for i in range(1, num_slots + 1):
        client.post(f"/api/parking/areas/{area_id}/slots", json={"slotNumber": str(i)})
    return area_id


def test_reassign_slot_from_no_slot(client_with_capacity):
    with client_with_capacity() as client:
        area_id = _setup_area_with_slots(client)
        client.post(
            "/api/parking/vehicles",
            json={"vehicleNumber": "KA01AB1234", "wheelCategory": 4, "vehicleType": "Car"},
        )
        slots = client.get(f"/api/parking/areas/{area_id}/slots").json()["slots"]
        target = next(s for s in slots if s["slotNumber"] == "3")

        resp = client.patch(
            "/api/parking/vehicles/KA01AB1234/slot",
            json={"slotId": target["slotId"]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["slotId"] == target["slotId"]
        assert body["slotNumber"] == "3"
        assert body["areaId"] == area_id

        area = client.get("/api/parking/areas").json()["areas"][0]
        assert area["availableSlots"] == 4
        assert area["occupiedSlots"] == 1


def test_reassign_slot_to_different_slot_same_area(client_with_capacity):
    with client_with_capacity() as client:
        area_id = _setup_area_with_slots(client)
        slots = client.get(f"/api/parking/areas/{area_id}/slots").json()["slots"]
        slot1 = next(s for s in slots if s["slotNumber"] == "1")
        slot3 = next(s for s in slots if s["slotNumber"] == "3")

        client.post(
            "/api/parking/vehicles",
            json={
                "vehicleNumber": "KA01AB1234",
                "wheelCategory": 4,
                "vehicleType": "Car",
                "areaId": area_id,
                "slotId": slot1["slotId"],
            },
        )
        area_before = client.get("/api/parking/areas").json()["areas"][0]
        assert area_before["occupiedSlots"] == 1

        resp = client.patch(
            "/api/parking/vehicles/KA01AB1234/slot",
            json={"slotId": slot3["slotId"]},
        )
        assert resp.status_code == 200
        assert resp.json()["slotNumber"] == "3"

        slots_after = client.get(f"/api/parking/areas/{area_id}/slots").json()["slots"]
        s1 = next(s for s in slots_after if s["slotNumber"] == "1")
        s3 = next(s for s in slots_after if s["slotNumber"] == "3")
        assert s1["status"] == "AVAILABLE"
        assert s3["status"] == "OCCUPIED"
        assert s3["vehicleNumber"] == "KA01AB1234"

        area_after = client.get("/api/parking/areas").json()["areas"][0]
        assert area_after["availableSlots"] == 4
        assert area_after["occupiedSlots"] == 1


def test_reassign_slot_to_occupied_returns_409(client_with_capacity):
    with client_with_capacity() as client:
        area_id = _setup_area_with_slots(client, num_slots=4)
        slots = client.get(f"/api/parking/areas/{area_id}/slots").json()["slots"]
        slot1 = next(s for s in slots if s["slotNumber"] == "1")
        slot2 = next(s for s in slots if s["slotNumber"] == "2")

        client.post(
            "/api/parking/vehicles",
            json={
                "vehicleNumber": "KA01AA1111",
                "wheelCategory": 4,
                "vehicleType": "Car",
                "areaId": area_id,
                "slotId": slot1["slotId"],
            },
        )
        client.post(
            "/api/parking/vehicles",
            json={
                "vehicleNumber": "KA01BB2222",
                "wheelCategory": 4,
                "vehicleType": "SUV",
                "areaId": area_id,
                "slotId": slot2["slotId"],
            },
        )
        resp = client.patch(
            "/api/parking/vehicles/KA01AA1111/slot",
            json={"slotId": slot2["slotId"]},
        )
        assert resp.status_code == 409
        assert resp.json()["error"] == "SLOT_ALREADY_OCCUPIED"


def test_reassign_slot_vehicle_not_found_returns_404(client_with_capacity):
    with client_with_capacity() as client:
        area_id = _setup_area_with_slots(client, num_slots=2)
        slots = client.get(f"/api/parking/areas/{area_id}/slots").json()["slots"]
        resp = client.patch(
            "/api/parking/vehicles/FAKE0000/slot",
            json={"slotId": slots[0]["slotId"]},
        )
        assert resp.status_code == 404


def test_reassign_slot_exited_vehicle_returns_409(client_with_capacity):
    with client_with_capacity() as client:
        area_id = _setup_area_with_slots(client, num_slots=2)
        slots = client.get(f"/api/parking/areas/{area_id}/slots").json()["slots"]
        client.post(
            "/api/parking/vehicles",
            json={
                "vehicleNumber": "KA01AB1234",
                "wheelCategory": 4,
                "vehicleType": "Car",
                "areaId": area_id,
                "slotId": slots[0]["slotId"],
            },
        )
        client.post("/api/parking/vehicles/KA01AB1234/exit")
        resp = client.patch(
            "/api/parking/vehicles/KA01AB1234/slot",
            json={"slotId": slots[1]["slotId"]},
        )
        assert resp.status_code == 409
