"""Infrastructure API routes for compute and health monitoring."""

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.opscentral.api.dependencies import verify_api_key
from src.opscentral.models.alert import Alert, AlertSeverity, AlertStatus
from src.opscentral.models.infrastructure import ComputeInstance, InfrastructureHealth
from src.opscentral.models.database import get_db

router = APIRouter()


class ComputeInstanceResponse(BaseModel):
    """Compute instance response schema."""

    id: int
    ocid: str
    display_name: str
    shape: str
    availability_domain: str
    region: str
    state: str
    ocpus: Optional[float] = None
    memory_gb: Optional[float] = None
    cpu_utilization: Optional[float] = None
    memory_utilization: Optional[float] = None
    network_bytes_in: Optional[int] = None
    network_bytes_out: Optional[int] = None
    metrics_updated_at: Optional[datetime] = None

    class Config:
        """Pydantic config."""

        from_attributes = True


class ComputeListResponse(BaseModel):
    """List of compute instances."""

    items: List[ComputeInstanceResponse]
    total: int


class HealthScoreResponse(BaseModel):
    """Infrastructure health score response."""

    overall_score: float
    status: str  # healthy, degraded, critical
    compute_score: float
    network_score: float
    storage_score: float
    total_instances: int
    running_instances: int
    unhealthy_instances: int
    critical_alerts: int
    high_alerts: int
    last_updated: datetime


class ResourceSummaryResponse(BaseModel):
    """Summary of all infrastructure resources."""

    compute_instances: int
    running_instances: int
    vcns: int
    subnets: int
    buckets: int
    total_alerts: int
    open_alerts: int


@router.get("/compute", response_model=ComputeListResponse)
async def list_compute_instances(
    state: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_api_key),
) -> ComputeListResponse:
    """List OCI compute instances with current metrics.

    Args:
        state: Filter by instance state (RUNNING, STOPPED, etc.)
        limit: Maximum number of instances to return
    """
    query = select(ComputeInstance)

    if state:
        query = query.where(ComputeInstance.state == state.upper())

    query = query.order_by(desc(ComputeInstance.updated_at)).limit(limit)

    result = await db.execute(query)
    instances = result.scalars().all()

    # Get total count
    count_query = select(func.count(ComputeInstance.id))
    if state:
        count_query = count_query.where(ComputeInstance.state == state.upper())
    total = (await db.execute(count_query)).scalar() or 0

    return ComputeListResponse(
        items=[ComputeInstanceResponse.model_validate(i) for i in instances],
        total=total,
    )


@router.get("/health", response_model=HealthScoreResponse)
async def get_infrastructure_health(
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_api_key),
) -> HealthScoreResponse:
    """Calculate current infrastructure health score.

    Health score factors:
    - Compute: Instance availability, CPU/memory utilization
    - Network: VCN health, security list compliance
    - Storage: Bucket accessibility, policy compliance
    - Alerts: Weight by severity (critical=-20, high=-10, medium=-5)
    """
    # Get latest health snapshot or calculate
    result = await db.execute(
        select(InfrastructureHealth).order_by(desc(InfrastructureHealth.recorded_at)).limit(1)
    )
    health = result.scalar_one_or_none()

    if health:
        # Use cached health score if recent (within 5 minutes)
        from datetime import timedelta

        if datetime.now(timezone.utc) - health.recorded_at < timedelta(minutes=5):
            status_label = _calculate_status(health.overall_score)
            return HealthScoreResponse(
                overall_score=health.overall_score,
                status=status_label,
                compute_score=health.compute_score,
                network_score=health.network_score,
                storage_score=health.storage_score,
                total_instances=health.total_instances,
                running_instances=health.running_instances,
                unhealthy_instances=health.unhealthy_instances,
                critical_alerts=health.critical_alerts,
                high_alerts=health.high_alerts,
                last_updated=health.recorded_at,
            )

    # Calculate fresh health score
    health_data = await _calculate_health_score(db)
    return health_data


@router.get("/summary", response_model=ResourceSummaryResponse)
async def get_resource_summary(
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_api_key),
) -> ResourceSummaryResponse:
    """Get summary counts of all infrastructure resources."""
    # Compute instances
    total_instances = (
        await db.execute(select(func.count(ComputeInstance.id)))
    ).scalar() or 0

    running_instances = (
        await db.execute(
            select(func.count(ComputeInstance.id)).where(
                ComputeInstance.state == "RUNNING"
            )
        )
    ).scalar() or 0

    # Total and open alerts
    total_alerts = (await db.execute(select(func.count(Alert.id)))).scalar() or 0

    open_alerts = (
        await db.execute(
            select(func.count(Alert.id)).where(
                Alert.status.in_([AlertStatus.NEW.value, AlertStatus.ACKNOWLEDGED.value])
            )
        )
    ).scalar() or 0

    return ResourceSummaryResponse(
        compute_instances=total_instances,
        running_instances=running_instances,
        vcns=0,  # Populated by OCI collector
        subnets=0,  # Populated by OCI collector
        buckets=0,  # Populated by OCI collector
        total_alerts=total_alerts,
        open_alerts=open_alerts,
    )


def _calculate_status(score: float) -> str:
    """Determine health status from score."""
    if score >= 80:
        return "healthy"
    elif score >= 50:
        return "degraded"
    return "critical"


async def _calculate_health_score(db: AsyncSession) -> HealthScoreResponse:
    """Calculate infrastructure health score from current state."""
    # Instance counts
    total_instances = (
        await db.execute(select(func.count(ComputeInstance.id)))
    ).scalar() or 0

    running_instances = (
        await db.execute(
            select(func.count(ComputeInstance.id)).where(
                ComputeInstance.state == "RUNNING"
            )
        )
    ).scalar() or 0

    # Count unhealthy (high CPU/memory)
    unhealthy_query = select(func.count(ComputeInstance.id)).where(
        (ComputeInstance.cpu_utilization > 90) | (ComputeInstance.memory_utilization > 90)
    )
    unhealthy_instances = (await db.execute(unhealthy_query)).scalar() or 0

    # Alert counts
    critical_alerts = (
        await db.execute(
            select(func.count(Alert.id)).where(
                Alert.severity == AlertSeverity.CRITICAL.value,
                Alert.status.in_([AlertStatus.NEW.value, AlertStatus.ACKNOWLEDGED.value]),
            )
        )
    ).scalar() or 0

    high_alerts = (
        await db.execute(
            select(func.count(Alert.id)).where(
                Alert.severity == AlertSeverity.HIGH.value,
                Alert.status.in_([AlertStatus.NEW.value, AlertStatus.ACKNOWLEDGED.value]),
            )
        )
    ).scalar() or 0

    # Calculate scores
    compute_score = 100.0
    if total_instances > 0:
        availability = (running_instances / total_instances) * 100
        health_penalty = (unhealthy_instances / total_instances) * 30
        compute_score = max(0, min(100, availability - health_penalty))

    # Network and storage start at 100 (no data yet)
    network_score = 100.0
    storage_score = 100.0

    # Alert penalties
    alert_penalty = (critical_alerts * 20) + (high_alerts * 10)

    # Overall score (weighted average minus alert penalty)
    overall_score = (compute_score * 0.5 + network_score * 0.3 + storage_score * 0.2)
    overall_score = max(0, min(100, overall_score - alert_penalty))

    status = _calculate_status(overall_score)

    return HealthScoreResponse(
        overall_score=round(overall_score, 1),
        status=status,
        compute_score=round(compute_score, 1),
        network_score=round(network_score, 1),
        storage_score=round(storage_score, 1),
        total_instances=total_instances,
        running_instances=running_instances,
        unhealthy_instances=unhealthy_instances,
        critical_alerts=critical_alerts,
        high_alerts=high_alerts,
        last_updated=datetime.now(timezone.utc),
    )
