from uuid import UUID, uuid4

from src.domain.service_order import ServiceOrder


def open_order(
    customer_id: UUID, vehicle_id: UUID, correlation_id: UUID
) -> ServiceOrder:
    """Create an order without skipping any distributed lifecycle state."""
    return ServiceOrder(
        id=uuid4(),
        customer_id=customer_id,
        vehicle_id=vehicle_id,
        saga_id=uuid4(),
        correlation_id=correlation_id,
    )
