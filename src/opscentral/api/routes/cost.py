"""Cost API routes for OCI cost tracking and analysis."""

from datetime import datetime, date, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from src.opscentral.api.dependencies import verify_api_key

router = APIRouter()


class CostDataPoint(BaseModel):
    """Cost data point for a specific date."""

    date: date
    amount: float
    currency: str = "USD"


class ServiceCost(BaseModel):
    """Cost breakdown by OCI service."""

    service: str
    amount: float
    percentage: float


class CostSummaryResponse(BaseModel):
    """Cost summary for current billing period."""

    current_month_total: float
    previous_month_total: float
    month_over_month_change: float
    projected_month_end: float
    currency: str
    by_service: List[ServiceCost]
    daily_trend: List[CostDataPoint]
    last_updated: datetime


class CostBudgetResponse(BaseModel):
    """Budget tracking response."""

    budget_amount: float
    current_spend: float
    percentage_used: float
    days_remaining: int
    projected_overage: float
    status: str  # under_budget, at_risk, over_budget


@router.get("/summary", response_model=CostSummaryResponse)
async def get_cost_summary(
    _: bool = Depends(verify_api_key),
) -> CostSummaryResponse:
    """Get cost summary for current billing period.

    Note: Returns mock data when OCI Cost Management API is not configured.
    Real implementation would use OCI Cost Management API.
    """
    # Mock data for demo - replace with OCI Cost Management API integration
    today = datetime.now(timezone.utc)

    # Generate mock daily trend
    from datetime import timedelta

    daily_trend = []
    for i in range(30):
        day = today - timedelta(days=29 - i)
        # Simulate varying daily costs
        import random

        amount = 12.50 + random.uniform(-3, 5) + (i * 0.1)
        daily_trend.append(
            CostDataPoint(
                date=day.date(),
                amount=round(amount, 2),
            )
        )

    current_total = sum(d.amount for d in daily_trend)
    previous_total = current_total * 0.92  # Simulate 8% growth

    # Service breakdown
    services = [
        ServiceCost(service="Compute", amount=round(current_total * 0.45, 2), percentage=45.0),
        ServiceCost(service="Object Storage", amount=round(current_total * 0.20, 2), percentage=20.0),
        ServiceCost(service="Networking", amount=round(current_total * 0.15, 2), percentage=15.0),
        ServiceCost(service="Database", amount=round(current_total * 0.12, 2), percentage=12.0),
        ServiceCost(service="Other", amount=round(current_total * 0.08, 2), percentage=8.0),
    ]

    # Project month-end based on daily average
    days_elapsed = today.day
    daily_avg = current_total / days_elapsed if days_elapsed > 0 else 0
    from calendar import monthrange

    days_in_month = monthrange(today.year, today.month)[1]
    projected_total = daily_avg * days_in_month

    return CostSummaryResponse(
        current_month_total=round(current_total, 2),
        previous_month_total=round(previous_total, 2),
        month_over_month_change=round(
            ((current_total - previous_total) / previous_total * 100) if previous_total > 0 else 0, 1
        ),
        projected_month_end=round(projected_total, 2),
        currency="USD",
        by_service=services,
        daily_trend=daily_trend,
        last_updated=today,
    )


@router.get("/budget", response_model=CostBudgetResponse)
async def get_budget_status(
    budget: float = Query(default=500.0, description="Monthly budget amount"),
    _: bool = Depends(verify_api_key),
) -> CostBudgetResponse:
    """Get budget tracking status.

    Args:
        budget: Monthly budget amount in USD
    """
    today = datetime.now(timezone.utc)

    # Get current spend (mock)
    from calendar import monthrange

    days_in_month = monthrange(today.year, today.month)[1]
    days_elapsed = today.day
    days_remaining = days_in_month - days_elapsed

    # Simulate current spend
    daily_rate = budget / days_in_month
    current_spend = daily_rate * days_elapsed * 0.95  # Slightly under budget

    percentage_used = (current_spend / budget * 100) if budget > 0 else 0
    projected_total = (current_spend / days_elapsed * days_in_month) if days_elapsed > 0 else 0
    projected_overage = max(0, projected_total - budget)

    # Determine status
    if percentage_used < (days_elapsed / days_in_month * 100):
        status = "under_budget"
    elif projected_overage > 0:
        status = "over_budget"
    else:
        status = "at_risk"

    return CostBudgetResponse(
        budget_amount=budget,
        current_spend=round(current_spend, 2),
        percentage_used=round(percentage_used, 1),
        days_remaining=days_remaining,
        projected_overage=round(projected_overage, 2),
        status=status,
    )


@router.get("/trend")
async def get_cost_trend(
    days: int = Query(default=30, ge=7, le=90),
    _: bool = Depends(verify_api_key),
) -> List[CostDataPoint]:
    """Get daily cost trend for the specified number of days.

    Args:
        days: Number of days of history to return (7-90)
    """
    today = datetime.now(timezone.utc)
    from datetime import timedelta
    import random

    trend = []
    base_cost = 15.0

    for i in range(days):
        day = today - timedelta(days=days - 1 - i)
        # Add some variance and weekly pattern (lower on weekends)
        weekday_factor = 0.85 if day.weekday() >= 5 else 1.0
        amount = base_cost * weekday_factor + random.uniform(-2, 3)
        trend.append(
            CostDataPoint(
                date=day.date(),
                amount=round(max(0, amount), 2),
            )
        )

    return trend
