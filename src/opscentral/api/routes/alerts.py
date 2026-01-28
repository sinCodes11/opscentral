"""Alert API routes for security alert management."""

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.opscentral.api.dependencies import verify_api_key
from src.opscentral.models.alert import Alert, AlertSeverity, AlertStatus
from src.opscentral.models.database import get_db

router = APIRouter()


# Pydantic schemas for request/response
class AlertResponse(BaseModel):
    """Alert response schema."""

    id: int
    title: str
    description: Optional[str] = None
    severity: str
    status: str
    source: str
    source_id: Optional[str] = None
    category: Optional[str] = None
    rule_name: Optional[str] = None
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    resource_name: Optional[str] = None
    detected_at: datetime
    acknowledged_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None

    class Config:
        """Pydantic config."""

        from_attributes = True


class AlertListResponse(BaseModel):
    """Paginated alert list response."""

    items: List[AlertResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class AlertSummaryResponse(BaseModel):
    """Alert summary counts by severity."""

    total: int
    by_severity: dict[str, int]
    by_status: dict[str, int]
    recent_24h: int


class AcknowledgeRequest(BaseModel):
    """Request to acknowledge an alert."""

    user: str = Field(..., min_length=1, max_length=255)


class AlertCreateRequest(BaseModel):
    """Request to create a new alert."""

    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    severity: str = Field(default=AlertSeverity.MEDIUM.value)
    source: str = Field(..., min_length=1, max_length=50)
    source_id: Optional[str] = None
    category: Optional[str] = None
    rule_name: Optional[str] = None
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    resource_name: Optional[str] = None


@router.get("", response_model=AlertListResponse)
async def list_alerts(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    severity: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    source: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_api_key),
) -> AlertListResponse:
    """List alerts with pagination and filters.

    Args:
        page: Page number (1-indexed)
        page_size: Number of items per page
        severity: Filter by severity level
        status: Filter by alert status
        source: Filter by alert source
    """
    # Build query
    query = select(Alert)

    # Apply filters
    if severity:
        query = query.where(Alert.severity == severity)
    if status:
        query = query.where(Alert.status == status)
    if source:
        query = query.where(Alert.source == source)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # Apply pagination and ordering
    query = (
        query.order_by(desc(Alert.detected_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    # Execute query
    result = await db.execute(query)
    alerts = result.scalars().all()

    # Calculate total pages
    total_pages = (total + page_size - 1) // page_size

    return AlertListResponse(
        items=[AlertResponse.model_validate(a) for a in alerts],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/summary", response_model=AlertSummaryResponse)
async def get_alert_summary(
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_api_key),
) -> AlertSummaryResponse:
    """Get alert summary with counts by severity and status."""
    # Total count
    total = (await db.execute(select(func.count(Alert.id)))).scalar() or 0

    # Count by severity
    severity_query = select(Alert.severity, func.count(Alert.id)).group_by(
        Alert.severity
    )
    severity_result = await db.execute(severity_query)
    by_severity = {row[0]: row[1] for row in severity_result.all()}

    # Ensure all severities are present
    for sev in AlertSeverity:
        if sev.value not in by_severity:
            by_severity[sev.value] = 0

    # Count by status
    status_query = select(Alert.status, func.count(Alert.id)).group_by(Alert.status)
    status_result = await db.execute(status_query)
    by_status = {row[0]: row[1] for row in status_result.all()}

    # Ensure all statuses are present
    for st in AlertStatus:
        if st.value not in by_status:
            by_status[st.value] = 0

    # Recent 24h count
    from datetime import timedelta

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    recent_query = select(func.count(Alert.id)).where(Alert.detected_at >= cutoff)
    recent_24h = (await db.execute(recent_query)).scalar() or 0

    return AlertSummaryResponse(
        total=total,
        by_severity=by_severity,
        by_status=by_status,
        recent_24h=recent_24h,
    )


@router.get("/{alert_id}", response_model=AlertResponse)
async def get_alert(
    alert_id: int,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_api_key),
) -> AlertResponse:
    """Get a specific alert by ID."""
    result = await db.execute(select(Alert).where(Alert.id == alert_id))
    alert = result.scalar_one_or_none()

    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert {alert_id} not found",
        )

    return AlertResponse.model_validate(alert)


@router.post("/{alert_id}/acknowledge", response_model=AlertResponse)
async def acknowledge_alert(
    alert_id: int,
    request: AcknowledgeRequest,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_api_key),
) -> AlertResponse:
    """Acknowledge an alert."""
    result = await db.execute(select(Alert).where(Alert.id == alert_id))
    alert = result.scalar_one_or_none()

    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert {alert_id} not found",
        )

    alert.acknowledge(request.user)
    await db.commit()
    await db.refresh(alert)

    return AlertResponse.model_validate(alert)


@router.post("/{alert_id}/resolve", response_model=AlertResponse)
async def resolve_alert(
    alert_id: int,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_api_key),
) -> AlertResponse:
    """Mark an alert as resolved."""
    result = await db.execute(select(Alert).where(Alert.id == alert_id))
    alert = result.scalar_one_or_none()

    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert {alert_id} not found",
        )

    alert.resolve()
    await db.commit()
    await db.refresh(alert)

    return AlertResponse.model_validate(alert)


@router.post("", response_model=AlertResponse, status_code=status.HTTP_201_CREATED)
async def create_alert(
    request: AlertCreateRequest,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_api_key),
) -> AlertResponse:
    """Create a new alert (used by collectors and integrations)."""
    alert = Alert(
        title=request.title,
        description=request.description,
        severity=request.severity,
        source=request.source,
        source_id=request.source_id,
        category=request.category,
        rule_name=request.rule_name,
        resource_type=request.resource_type,
        resource_id=request.resource_id,
        resource_name=request.resource_name,
    )

    db.add(alert)
    await db.commit()
    await db.refresh(alert)

    return AlertResponse.model_validate(alert)
