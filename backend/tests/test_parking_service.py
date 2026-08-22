"""Parking capacity/registration business-rule tests against an in-memory
fake repository (no real Firestore required) - see tests/fakes.py.
"""
from __future__ import annotations

import threading

import pytest

from app.exceptions import (
    ParkingFullError,
    VehicleAlreadyActiveError,
    VehicleAlreadyExitedError,
    VehicleNotFoundError,
)
from app.schemas.parking import AddVehicleRequest
from app.services.parking_service import ParkingService
from tests.fakes import FakeParkingRepository


def make_service(capacity: int = 100) -> ParkingService:
    return ParkingService(FakeParkingRepository(total_capacity=capacity))


def add(service: ParkingService, vehicle_number: str, wheel_category: int = 4, vehicle_type: str = "SUV"):
    return service.add_vehicle(
        AddVehicleRequest(vehicleNumber=vehicle_number, wheelCategory=wheel_category, vehicleType=vehicle_type)
    )


def test_entry_decrements_available_100_to_99():
    service = make_service(capacity=100)
    add(service, "TS09AB1234")
    capacity = service.get_capacity()
    assert capacity.total_capacity == 100
    assert capacity.available_slots == 99
    assert capacity.occupied_slots == 1


def test_second_entry_decrements_99_to_98():
    service = make_service(capacity=100)
    add(service, "TS09AB1234")
    add(service, "AP16CD5678")
    capacity = service.get_capacity()
    assert capacity.available_slots == 98
    assert capacity.occupied_slots == 2


def test_duplicate_active_vehicle_keeps_capacity_unchanged():
    service = make_service(capacity=100)
    add(service, "TS09AB1234")
    add(service, "AP16CD5678")

    with pytest.raises(VehicleAlreadyActiveError):
        add(service, "TS09AB1234")

    capacity = service.get_capacity()
    assert capacity.available_slots == 98
    assert capacity.occupied_slots == 2


def test_exit_changes_98_to_99():
    service = make_service(capacity=100)
    add(service, "TS09AB1234")
    add(service, "AP16CD5678")

    session = service.exit_vehicle("TS09AB1234")
    assert session.status == "EXITED"

    capacity = service.get_capacity()
    assert capacity.available_slots == 99
    assert capacity.occupied_slots == 1


def test_double_exit_keeps_99_and_raises():
    service = make_service(capacity=100)
    add(service, "TS09AB1234")
    add(service, "AP16CD5678")
    service.exit_vehicle("TS09AB1234")

    with pytest.raises(VehicleAlreadyExitedError):
        service.exit_vehicle("TS09AB1234")

    capacity = service.get_capacity()
    assert capacity.available_slots == 99
    assert capacity.occupied_slots == 1


def test_exit_unknown_vehicle_raises_not_found():
    service = make_service(capacity=100)
    with pytest.raises(VehicleNotFoundError):
        service.exit_vehicle("XX00ZZ0000")


def test_full_parking_rejects_entry_and_never_goes_negative():
    service = make_service(capacity=1)
    add(service, "TS09AB1234")

    with pytest.raises(ParkingFullError):
        add(service, "AP16CD5678")

    capacity = service.get_capacity()
    assert capacity.available_slots == 0
    assert capacity.occupied_slots == 1


def test_reentry_after_exit_is_allowed():
    service = make_service(capacity=100)
    add(service, "TS09AB1234")
    service.exit_vehicle("TS09AB1234")
    session = add(service, "TS09AB1234")

    assert session.status == "ACTIVE"
    capacity = service.get_capacity()
    assert capacity.available_slots == 99
    assert capacity.occupied_slots == 1


def test_concurrent_entries_never_overbook():
    capacity_limit = 20
    service = make_service(capacity=capacity_limit)
    num_threads = 100
    successes = []
    failures = []
    lock = threading.Lock()

    def worker(i: int):
        try:
            add(service, f"TS{i:04d}AB0000".replace(" ", "")[:10])
            with lock:
                successes.append(i)
        except ParkingFullError:
            with lock:
                failures.append(i)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(successes) == capacity_limit
    assert len(failures) == num_threads - capacity_limit

    capacity = service.get_capacity()
    assert capacity.available_slots == 0
    assert capacity.occupied_slots == capacity_limit
    assert capacity.occupied_slots >= 0
