"""Alert model for security alert tracking."""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.opscentral.models.database import Base


class AlertSeverity(str, Enum):
    """Alert severity levels aligned with SIEM standards."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class AlertStatus(str, Enum):
    """Alert lifecycle status."""

    NEW = "new"
    ACKNOWLEDGED = "acknowledged"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    FALSE_POSITIVE = "false_positive"


class Alert(Base):
    """Security alert model.

    Stores normalized alerts from multiple sources (SIEM, OCI, internal systems).
    """

    __tablename__ = "alerts"

    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Core alert fields
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    severity: Mapped[str] = mapped_column(
        String(20),
        default=AlertSeverity.MEDIUM.value,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default=AlertStatus.NEW.value,
        nullable=False,
    )

    # Source tracking
    source: Mapped[str] = mapped_column(String(50), nullable=False)  # splunk, oci, internal
    source_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Categorization
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    rule_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Affected resources
    resource_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    resource_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    resource_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Timestamps
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # User tracking
    acknowledged_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Indexes for common queries
    __table_args__ = (
        Index("ix_alerts_severity_status", "severity", "status"),
        Index("ix_alerts_source", "source"),
        Index("ix_alerts_detected_at", "detected_at"),
    )

    def __repr__(self) -> str:
        """String representation."""
        return f"<Alert(id={self.id}, title='{self.title[:30]}...', severity={self.severity})>"

    def acknowledge(self, user: str) -> None:
        """Mark alert as acknowledged."""
        self.status = AlertStatus.ACKNOWLEDGED.value
        self.acknowledged_at = datetime.now(timezone.utc)
        self.acknowledged_by = user

    def resolve(self) -> None:
        """Mark alert as resolved."""
        self.status = AlertStatus.RESOLVED.value
        self.resolved_at = datetime.now(timezone.utc)
