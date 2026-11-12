import json
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

_context: ContextVar[dict[str, str] | None] = ContextVar(
    "observability_context", default=None
)
_sensitive = {
    "authorization",
    "cpf",
    "document",
    "password",
    "qr_payload",
    "secret",
    "token",
}


def sanitize(value: Any, key: str = "") -> Any:
    if key.lower() in _sensitive:
        return "[REDACTED]"
    if isinstance(value, dict):
        return {
            str(item_key): sanitize(item, str(item_key))
            for item_key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [sanitize(item) for item in value]
    return str(value) if hasattr(value, "hex") and not isinstance(value, str) else value


@contextmanager
def bind_context(**values: Any):
    current = _context.get() or {}
    token = _context.set(
        {
            **current,
            **{key: str(value) for key, value in values.items() if value is not None},
        }
    )
    try:
        yield
    finally:
        _context.reset(token)


def log_event(event: str, **attributes: Any) -> None:
    payload = {
        "timestamp": datetime.now(UTC).isoformat(),
        "event": event,
        **(_context.get() or {}),
        **attributes,
    }
    print(
        json.dumps(sanitize(payload), separators=(",", ":"), sort_keys=True), flush=True
    )
