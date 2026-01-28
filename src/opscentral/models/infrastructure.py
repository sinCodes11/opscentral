"""Infrastructure models for compute instances and health tracking."""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.opscentral.models.database import Base


class InstanceState(str, Enum):
    """OCI compute instance lifecycle states."""

    PROVISIONING = "PROVISIONING"
    RUNNING = "RUNNING"
    STARTING = "STARTING"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    TERMINATED = "TERMINATED"


class ComputeInstance(Base):
    """OCI Compute instance tracking.

    Stores instance metadata and current metrics for monitoring.
    """

    __tablename__ = "compute_instances"

    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # OCI identifiers
    ocid: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    compartment_ocid: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Instance details
    shape: Mapped[str] = mapped_column(String(100), nullable=False)
    availability_domain: Mapped[str] = mapped_column(String(100), nullable=False)
    region: Mapped[str] = mapped_column(String(50), nullable=False)
    state: Mapped[str] = mapped_column(String(50), default=InstanceState.RUNNING.value)

    # Resource allocation
    ocpus: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    memory_gb: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Current metrics (updated by collector)
    cpu_utilization: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    memory_utilization: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    network_bytes_in: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    network_bytes_out: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Timestamps
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
    metrics_updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        Index("ix_compute_instances_compartment", "compartment_ocid"),
        Index("ix_compute_instances_state", "state"),
    )

    def __repr__(self) -> str:
        """String representation."""
        return f"<ComputeInstance(ocid='{self.ocid[:20]}...', name='{self.display_name}')>"


class InfrastructureHealth(Base):
    """Infrastructure health snapshot.

    Stores periodic health score calculations for trending.
    """

    __tablename__ = "infrastructure_health"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Health scores (0-100)
    overall_score: Mapped[float] = mapped_column(Float, nullable=False)
    compute_score: Mapped[float] = mapped_column(Float, nullable=False)
    network_score: Mapped[float] = mapped_column(Float, nullable=False)
    storage_score: Mapped[float] = mapped_column(Float, nullable=False)

    # Resource counts
    total_instances: Mapped[int] = mapped_column(Integer, default=0)
    running_instances: Mapped[int] = mapped_column(Integer, default=0)
    unhealthy_instances: Mapped[int] = mapped_column(Integer, default=0)

    # Alert summary at snapshot time
    critical_alerts: Mapped[int] = mapped_column(Integer, default=0)
    high_alerts: Mapped[int] = mapped_column(Integer, default=0)

    # Timestamp
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (Index("ix_infrastructure_health_recorded_at", "recorded_at"),)


class ComplianceCheck(Base):
    """Compliance check result tracking.

    Stores results of compliance checks against OCI resources.
    """

    __tablename__ = "compliance_checks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Check identification
    check_id: Mapped[str] = mapped_column(String(100), nullable=False)
    check_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Framework alignment
    framework: Mapped[str] = mapped_column(String(50), nullable=False)  # CIS, NIST, etc.
    control_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Result
    passed: Mapped[bool] = mapped_column(default=False)
    resource_ocid: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    finding: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    remediation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Severity if failed
    severity: Mapped[str] = mapped_column(String(20), default="medium")

    # Timestamps
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_compliance_checks_framework", "framework"),
        Index("ix_compliance_checks_passed", "passed"),
    )
