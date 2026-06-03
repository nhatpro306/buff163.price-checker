"""Result models + run summary for cloud-friendly scraper runs.

Borrowed concept (no vendored code) from Crawlee's run statistics: a single
structured summary at the end of a run that maps cleanly to a process exit
code and a one-line log. See docs/scraper-cloud-readiness.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

_TS_FORMAT = "%Y-%m-%d %H:%M:%S"

# Per-item outcomes.
ITEM_SUCCESS = "success"
ITEM_FAILED = "failed"
ITEM_SKIPPED = "skipped"

# Whole-run outcomes.
RUN_SUCCESS = "success"
RUN_PARTIAL = "partial_success"
RUN_FAILED = "failed"


def _now() -> str:
    return datetime.now(UTC).strftime(_TS_FORMAT)


@dataclass
class ScrapeItemResult:
    goods_id: str
    status: str = ITEM_SUCCESS
    item_name: str | None = None
    price: float | None = None
    listing_count: int | None = None
    scraped_at: str | None = None
    error_type: str | None = None
    error_message: str | None = None


@dataclass
class ScrapeRunSummary:
    started_at: str
    finished_at: str | None = None
    status: str = RUN_SUCCESS
    attempted: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0
    storage_backend: str | None = None
    errors: list[str] = field(default_factory=list)

    @classmethod
    def start(cls) -> ScrapeRunSummary:
        return cls(started_at=_now())

    def record(self, result: ScrapeItemResult) -> None:
        self.attempted += 1
        if result.status == ITEM_SUCCESS:
            self.succeeded += 1
        elif result.status == ITEM_SKIPPED:
            self.skipped += 1
        else:
            self.failed += 1
        if result.status != ITEM_SUCCESS and result.error_message:
            self.errors.append(
                f"{result.goods_id}: {result.error_type or 'error'}: {result.error_message}"
            )

    def finalize(self) -> ScrapeRunSummary:
        self.finished_at = _now()
        if self.attempted == 0 or self.succeeded == self.attempted:
            self.status = RUN_SUCCESS
        elif self.succeeded == 0:
            self.status = RUN_FAILED
        else:
            self.status = RUN_PARTIAL
        return self

    @property
    def duration_seconds(self) -> float:
        if not self.finished_at:
            return 0.0
        try:
            started = datetime.strptime(self.started_at, _TS_FORMAT)
            finished = datetime.strptime(self.finished_at, _TS_FORMAT)
        except ValueError:
            return 0.0
        return max(0.0, (finished - started).total_seconds())

    def to_dict(self) -> dict[str, Any]:
        """Structured summary for JSON logs / Lambda responses (no secrets)."""
        return {
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_seconds": round(self.duration_seconds, 1),
            "attempted": self.attempted,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "skipped": self.skipped,
            "invalid": self.skipped,
            "storage_backend": self.storage_backend,
            "error_count": len(self.errors),
        }

    def log_line(self) -> str:
        backend = f" backend={self.storage_backend}" if self.storage_backend else ""
        return (
            f"Scraper run finished: status={self.status} "
            f"attempted={self.attempted} succeeded={self.succeeded} "
            f"failed={self.failed} skipped={self.skipped}{backend} "
            f"duration_seconds={self.duration_seconds:.1f}"
        )

    def exit_code(self) -> int:
        """0 unless every attempted item failed (then 1). Empty run is success."""
        if self.attempted > 0 and self.succeeded == 0:
            return 1
        return 0


__all__ = [
    "ITEM_SUCCESS",
    "ITEM_FAILED",
    "ITEM_SKIPPED",
    "RUN_SUCCESS",
    "RUN_PARTIAL",
    "RUN_FAILED",
    "ScrapeItemResult",
    "ScrapeRunSummary",
]
