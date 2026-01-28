"""Compliance API routes for security compliance tracking."""

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.opscentral.api.dependencies import verify_api_key
from src.opscentral.models.infrastructure import ComplianceCheck
from src.opscentral.models.database import get_db

router = APIRouter()


class ComplianceCheckResponse(BaseModel):
    """Compliance check result response."""

    id: int
    check_id: str
    check_name: str
    description: Optional[str] = None
    framework: str
    control_id: Optional[str] = None
    passed: bool
    resource_ocid: Optional[str] = None
    resource_type: str
    finding: Optional[str] = None
    remediation: Optional[str] = None
    severity: str
    checked_at: datetime

    class Config:
        """Pydantic config."""

        from_attributes = True


class ComplianceScoreResponse(BaseModel):
    """Overall compliance score response."""

    overall_score: float
    status: str  # compliant, at_risk, non_compliant
    total_checks: int
    passed_checks: int
    failed_checks: int
    by_framework: dict[str, dict]
    by_severity: dict[str, int]
    last_scan: Optional[datetime] = None


class ComplianceListResponse(BaseModel):
    """List of compliance check results."""

    items: List[ComplianceCheckResponse]
    total: int


class FrameworkSummary(BaseModel):
    """Summary for a specific compliance framework."""

    framework: str
    total: int
    passed: int
    failed: int
    score: float


@router.get("/score", response_model=ComplianceScoreResponse)
async def get_compliance_score(
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_api_key),
) -> ComplianceScoreResponse:
    """Get overall compliance score across all frameworks.

    Compliance score calculation:
    - Based on percentage of passed checks
    - Weighted by severity (critical failures have higher impact)
    """
    # Total checks
    total_checks = (
        await db.execute(select(func.count(ComplianceCheck.id)))
    ).scalar() or 0

    # Passed checks
    passed_checks = (
        await db.execute(
            select(func.count(ComplianceCheck.id)).where(ComplianceCheck.passed == True)
        )
    ).scalar() or 0

    failed_checks = total_checks - passed_checks

    # Score by framework
    framework_query = select(
        ComplianceCheck.framework,
        func.count(ComplianceCheck.id).label("total"),
        func.sum(func.cast(ComplianceCheck.passed, sqlalchemy_types_Integer)).label("passed"),
    ).group_by(ComplianceCheck.framework)

    # Import needed for cast
    from sqlalchemy import Integer as sqlalchemy_types_Integer

    framework_query = select(
        ComplianceCheck.framework,
        func.count(ComplianceCheck.id).label("total"),
    ).group_by(ComplianceCheck.framework)

    framework_result = await db.execute(framework_query)
    frameworks_raw = framework_result.all()

    by_framework = {}
    for row in frameworks_raw:
        framework = row[0]
        total = row[1]

        # Get passed count for this framework
        passed_for_framework = (
            await db.execute(
                select(func.count(ComplianceCheck.id)).where(
                    ComplianceCheck.framework == framework,
                    ComplianceCheck.passed == True,
                )
            )
        ).scalar() or 0

        score = (passed_for_framework / total * 100) if total > 0 else 100.0
        by_framework[framework] = {
            "total": total,
            "passed": passed_for_framework,
            "failed": total - passed_for_framework,
            "score": round(score, 1),
        }

    # Failed checks by severity
    severity_query = (
        select(ComplianceCheck.severity, func.count(ComplianceCheck.id))
        .where(ComplianceCheck.passed == False)
        .group_by(ComplianceCheck.severity)
    )
    severity_result = await db.execute(severity_query)
    by_severity = {row[0]: row[1] for row in severity_result.all()}

    # Ensure all severities present
    for sev in ["critical", "high", "medium", "low"]:
        if sev not in by_severity:
            by_severity[sev] = 0

    # Calculate overall score with severity weighting
    if total_checks == 0:
        overall_score = 100.0
    else:
        # Base score from pass rate
        base_score = (passed_checks / total_checks) * 100

        # Severity penalties for failures
        severity_penalty = (
            by_severity.get("critical", 0) * 5
            + by_severity.get("high", 0) * 3
            + by_severity.get("medium", 0) * 1
        )

        overall_score = max(0, min(100, base_score - severity_penalty))

    # Determine status
    if overall_score >= 90:
        status = "compliant"
    elif overall_score >= 70:
        status = "at_risk"
    else:
        status = "non_compliant"

    # Get last scan time
    last_scan_result = await db.execute(
        select(ComplianceCheck.checked_at).order_by(desc(ComplianceCheck.checked_at)).limit(1)
    )
    last_scan = last_scan_result.scalar_one_or_none()

    return ComplianceScoreResponse(
        overall_score=round(overall_score, 1),
        status=status,
        total_checks=total_checks,
        passed_checks=passed_checks,
        failed_checks=failed_checks,
        by_framework=by_framework,
        by_severity=by_severity,
        last_scan=last_scan,
    )


@router.get("/checks", response_model=ComplianceListResponse)
async def list_compliance_checks(
    framework: Optional[str] = Query(default=None),
    passed: Optional[bool] = Query(default=None),
    severity: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_api_key),
) -> ComplianceListResponse:
    """List compliance check results with filters.

    Args:
        framework: Filter by compliance framework (CIS, NIST, etc.)
        passed: Filter by pass/fail status
        severity: Filter by severity level
        limit: Maximum number of results
    """
    query = select(ComplianceCheck)

    if framework:
        query = query.where(ComplianceCheck.framework == framework)
    if passed is not None:
        query = query.where(ComplianceCheck.passed == passed)
    if severity:
        query = query.where(ComplianceCheck.severity == severity)

    query = query.order_by(desc(ComplianceCheck.checked_at)).limit(limit)

    result = await db.execute(query)
    checks = result.scalars().all()

    # Total count with filters
    count_query = select(func.count(ComplianceCheck.id))
    if framework:
        count_query = count_query.where(ComplianceCheck.framework == framework)
    if passed is not None:
        count_query = count_query.where(ComplianceCheck.passed == passed)
    if severity:
        count_query = count_query.where(ComplianceCheck.severity == severity)

    total = (await db.execute(count_query)).scalar() or 0

    return ComplianceListResponse(
        items=[ComplianceCheckResponse.model_validate(c) for c in checks],
        total=total,
    )


@router.get("/frameworks", response_model=List[FrameworkSummary])
async def list_frameworks(
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_api_key),
) -> List[FrameworkSummary]:
    """Get summary of compliance by framework."""
    # Get all unique frameworks
    frameworks_query = select(ComplianceCheck.framework).distinct()
    frameworks_result = await db.execute(frameworks_query)
    frameworks = [row[0] for row in frameworks_result.all()]

    summaries = []
    for framework in frameworks:
        total = (
            await db.execute(
                select(func.count(ComplianceCheck.id)).where(
                    ComplianceCheck.framework == framework
                )
            )
        ).scalar() or 0

        passed = (
            await db.execute(
                select(func.count(ComplianceCheck.id)).where(
                    ComplianceCheck.framework == framework,
                    ComplianceCheck.passed == True,
                )
            )
        ).scalar() or 0

        score = (passed / total * 100) if total > 0 else 100.0

        summaries.append(
            FrameworkSummary(
                framework=framework,
                total=total,
                passed=passed,
                failed=total - passed,
                score=round(score, 1),
            )
        )

    return summaries
