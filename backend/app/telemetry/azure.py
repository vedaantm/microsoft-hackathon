from __future__ import annotations

from app.telemetry.contracts import (
    BudgetStatus,
    ErrorAggregate,
    Summary,
    TelemetryFilters,
    TelemetryProvider,
    UsageAggregate,
    UsagePoint,
    UsageRecord,
)


class AzureMonitorTelemetryProvider(TelemetryProvider):
    def _not_implemented(self) -> None:
        raise NotImplementedError(
            "Azure Monitor telemetry queries are planned for Phase 8 and are not implemented yet."
        )

    def get_summary(self, filters: TelemetryFilters | None = None) -> Summary:
        self._not_implemented()

    def get_usage_timeseries(self, filters: TelemetryFilters | None = None) -> list[UsagePoint]:
        self._not_implemented()

    def get_usage_by_department(
        self, filters: TelemetryFilters | None = None
    ) -> list[UsageAggregate]:
        self._not_implemented()

    def get_usage_by_team(self, filters: TelemetryFilters | None = None) -> list[UsageAggregate]:
        self._not_implemented()

    def get_usage_by_member(self, filters: TelemetryFilters | None = None) -> list[UsageAggregate]:
        self._not_implemented()

    def get_usage_by_model(self, filters: TelemetryFilters | None = None) -> list[UsageAggregate]:
        self._not_implemented()

    def get_recent_requests(
        self, filters: TelemetryFilters | None = None, limit: int = 20
    ) -> list[UsageRecord]:
        self._not_implemented()

    def get_budget_status(self, filters: TelemetryFilters | None = None) -> list[BudgetStatus]:
        self._not_implemented()

    def get_error_summary(self, filters: TelemetryFilters | None = None) -> list[ErrorAggregate]:
        self._not_implemented()
