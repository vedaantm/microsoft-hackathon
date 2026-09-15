from __future__ import annotations

import os

from app.telemetry.azure import AzureMonitorTelemetryProvider
from app.telemetry.contracts import TelemetryProvider
from app.telemetry.seed import SeedTelemetryProvider


def create_telemetry_provider(source: str | None = None) -> TelemetryProvider:
    selected_source = source or os.getenv("TELEMETRY_SOURCE", "seed")
    if selected_source == "seed":
        return SeedTelemetryProvider()
    if selected_source == "application_insights":
        return AzureMonitorTelemetryProvider()
    raise ValueError(
        f"Unsupported TELEMETRY_SOURCE={selected_source!r}; "
        "expected 'seed' or 'application_insights'"
    )
