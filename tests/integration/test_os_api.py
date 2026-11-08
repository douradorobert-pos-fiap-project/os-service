from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from src.infrastructure.database.models import (
    OutboxMessageModel,
    SagaModel,
    ServiceOrderHistoryModel,
    ServiceOrderModel,
)


def create_customer_and_vehicle(client: TestClient) -> tuple[str, str]:
    customer = client.post(
        "/api/v1/customers",
        json={"name": "Ana Silva", "document": "52998224725"},
    )
    assert customer.status_code == 201
    customer_id = customer.json()["id"]

    vehicle = client.post(
        "/api/v1/vehicles",
        json={
            "customer_id": customer_id,
            "license_plate": "ABC1D23",
            "make": "Fiat",
            "model": "Argo",
            "year": 2024,
        },
    )
    assert vehicle.status_code == 201
    return customer_id, vehicle.json()["id"]


def test_open_order_persists_order_saga_history_and_outbox_atomically(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    customer_id, vehicle_id = create_customer_and_vehicle(client)
    correlation_id = uuid4()

    response = client.post(
        "/api/v1/service-orders",
        headers={"X-Correlation-ID": str(correlation_id)},
        json={"customer_id": customer_id, "vehicle_id": vehicle_id},
    )

    assert response.status_code == 201
    assert response.headers["X-Correlation-ID"] == str(correlation_id)
    assert response.json()["status"] == "DIAGNOSIS_PENDING"
    UUID(response.json()["id"])
    UUID(response.json()["saga_id"])

    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(ServiceOrderModel)) == 1
        assert session.scalar(select(func.count()).select_from(SagaModel)) == 1
        assert (
            session.scalar(select(func.count()).select_from(ServiceOrderHistoryModel))
            == 1
        )
        assert session.scalar(select(func.count()).select_from(OutboxMessageModel)) == 1
        message = session.scalar(select(OutboxMessageModel))
        assert message is not None
        assert message.message_type == "DiagnosisRequested"


def test_order_can_be_queried_with_its_history(client: TestClient) -> None:
    customer_id, vehicle_id = create_customer_and_vehicle(client)
    opened = client.post(
        "/api/v1/service-orders",
        json={"customer_id": customer_id, "vehicle_id": vehicle_id},
    )
    order_id = opened.json()["id"]

    detail = client.get(f"/api/v1/service-orders/{order_id}")
    history = client.get(f"/api/v1/service-orders/{order_id}/history")

    assert detail.status_code == 200
    assert detail.json()["id"] == order_id
    assert detail.json()["status"] == "DIAGNOSIS_PENDING"
    assert history.status_code == 200
    assert [entry["status"] for entry in history.json()] == ["DIAGNOSIS_PENDING"]


def test_open_order_rejects_vehicle_owned_by_another_customer(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _, vehicle_id = create_customer_and_vehicle(client)
    another_customer = client.post(
        "/api/v1/customers",
        json={"name": "Bruno Souza", "document": "11144477735"},
    ).json()["id"]

    response = client.post(
        "/api/v1/service-orders",
        json={"customer_id": another_customer, "vehicle_id": vehicle_id},
    )

    assert response.status_code == 409
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(ServiceOrderModel)) == 0
        assert session.scalar(select(func.count()).select_from(OutboxMessageModel)) == 0


def test_invalid_correlation_id_is_rejected_without_persistence(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    customer_id, vehicle_id = create_customer_and_vehicle(client)

    response = client.post(
        "/api/v1/service-orders",
        headers={"X-Correlation-ID": "not-a-uuid"},
        json={"customer_id": customer_id, "vehicle_id": vehicle_id},
    )

    assert response.status_code == 400
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(ServiceOrderModel)) == 0


def test_openapi_exposes_customer_vehicle_and_order_operations(
    client: TestClient,
) -> None:
    paths = client.get("/openapi.json").json()["paths"]

    assert "/api/v1/customers" in paths
    assert "/api/v1/vehicles" in paths
    assert "/api/v1/service-orders" in paths
    assert "/api/v1/service-orders/{order_id}" in paths
    assert "/api/v1/service-orders/{order_id}/history" in paths
