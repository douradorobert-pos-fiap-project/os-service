import json
from uuid import uuid4

from src.infrastructure.observability.logging import bind_context, log_event, sanitize
from src.infrastructure.observability.telemetry import record_event


def test_structured_log_propagates_context_and_redacts_sensitive_data(capsys):
    correlation_id, saga_id, order_id = uuid4(), uuid4(), uuid4()
    with bind_context(
        correlation_id=correlation_id, saga_id=saga_id, order_id=order_id
    ):
        log_event("message.consumed", token="secret", cpf="12345678901", status="ok")

    payload = json.loads(capsys.readouterr().out)
    assert payload["correlation_id"] == str(correlation_id)
    assert payload["saga_id"] == str(saga_id)
    assert payload["order_id"] == str(order_id)
    assert payload["token"] == "[REDACTED]"
    assert payload["cpf"] == "[REDACTED]"
    assert payload["status"] == "ok"


def test_telemetry_sanitizes_attributes_before_calling_agent():
    calls = []
    record_event(
        "SagaTransition",
        {"correlation_id": str(uuid4()), "qr_payload": "complete-qr", "error": "none"},
        recorder=lambda name, attributes: calls.append((name, attributes)),
    )

    assert calls[0][0] == "SagaTransition"
    assert calls[0][1]["qr_payload"] == "[REDACTED]"
    assert calls[0][1]["error"] == "none"
    assert sanitize({"password": "x", "nested": {"authorization": "y"}}) == {
        "password": "[REDACTED]",
        "nested": {"authorization": "[REDACTED]"},
    }


def test_telemetry_failure_does_not_break_business_flow():
    record_event(
        "MessagePublished",
        {"event_id": str(uuid4())},
        recorder=lambda *_: (_ for _ in ()).throw(RuntimeError("agent unavailable")),
    )
