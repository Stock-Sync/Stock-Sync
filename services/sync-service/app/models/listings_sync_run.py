from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import JSON, Column, String
from sqlmodel import Field, SQLModel


class SyncRunStatus(StrEnum):
    """Lifecycle states of a listings sync run."""

    RUNNING = "running"
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    FAILED = "failed"
    # Reconciliation was aborted because the missing set exceeded the safety
    # threshold. No local listings/mappings were touched.
    FLAGGED_SAFETY_THRESHOLD = "flagged_safety_threshold"


class ListingsSyncRun(SQLModel, table=True):
    """Audit trail of manual "Sincronizar Anúncios" pulls."""

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: str = Field(index=True, max_length=100)
    status: SyncRunStatus = Field(
        default=SyncRunStatus.RUNNING,
        sa_column=Column(String(50), nullable=False, index=True),
    )
    items_found: int = Field(default=0)
    items_upserted: int = Field(default=0)
    mappings_created: int = Field(default=0)
    # Candidate missing ids for audit. Populated on completed reconciliation
    # runs and, more importantly, on flagged runs where no deletion happened.
    items_removed: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False, default=list),
    )
    error_summary: str | None = Field(default=None, max_length=2000)
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = Field(default=None)
