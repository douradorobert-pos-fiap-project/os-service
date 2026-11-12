from collections.abc import Callable
from typing import Any

from src.infrastructure.observability.logging import sanitize


def record_event(
    name: str, attributes: dict[str, Any], recorder: Callable | None = None
) -> None:
    if recorder is None:
        try:
            from newrelic import agent

            recorder = agent.record_custom_event
        except ImportError:
            return
    try:
        recorder(name, sanitize(attributes))
    except Exception:  # noqa: BLE001 - telemetry must never break business flow
        return
