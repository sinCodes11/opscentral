"""Tests for alert API endpoints."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.opscentral.models.alert import Alert, AlertSeverity, AlertStatus


@pytest.mark.asyncio
async def test_list_alerts_empty(client: AsyncClient):
    """Test listing alerts when none exist."""
    response = await client.get("/api/v1/alerts")

    assert response.status_code == 200

    data = response.json()
    assert data["total"] == 0
    assert data["items"] == []


@pytest.mark.asyncio
async def test_create_alert(client: AsyncClient):
    """Test creating a new alert."""
    alert_data = {
        "title": "Test Alert",
        "description": "This is a test alert",
        "severity": "high",
        "source": "test",
        "category": "test_category",
    }

    response = await client.post("/api/v1/alerts", json=alert_data)

    assert response.status_code == 201

    data = response.json()
    assert data["title"] == "Test Alert"
    assert data["severity"] == "high"
    assert data["status"] == "new"


@pytest.mark.asyncio
async def test_get_alert(client: AsyncClient, db_session: AsyncSession):
    """Test getting a specific alert."""
    # Create an alert directly in DB
    alert = Alert(
        title="Direct Alert",
        description="Created directly",
        severity=AlertSeverity.MEDIUM.value,
        source="test",
    )
    db_session.add(alert)
    await db_session.commit()
    await db_session.refresh(alert)

    response = await client.get(f"/api/v1/alerts/{alert.id}")

    assert response.status_code == 200

    data = response.json()
    assert data["title"] == "Direct Alert"


@pytest.mark.asyncio
async def test_acknowledge_alert(client: AsyncClient, db_session: AsyncSession):
    """Test acknowledging an alert."""
    # Create an alert
    alert = Alert(
        title="Alert to Acknowledge",
        severity=AlertSeverity.HIGH.value,
        source="test",
    )
    db_session.add(alert)
    await db_session.commit()
    await db_session.refresh(alert)

    response = await client.post(
        f"/api/v1/alerts/{alert.id}/acknowledge",
        json={"user": "test_user"},
    )

    assert response.status_code == 200

    data = response.json()
    assert data["status"] == AlertStatus.ACKNOWLEDGED.value
    assert data["acknowledged_by"] == "test_user"


@pytest.mark.asyncio
async def test_alert_summary(client: AsyncClient, db_session: AsyncSession):
    """Test getting alert summary."""
    # Create alerts with different severities
    for severity in [AlertSeverity.CRITICAL, AlertSeverity.HIGH, AlertSeverity.MEDIUM]:
        alert = Alert(
            title=f"{severity.value} Alert",
            severity=severity.value,
            source="test",
        )
        db_session.add(alert)

    await db_session.commit()

    response = await client.get("/api/v1/alerts/summary")

    assert response.status_code == 200

    data = response.json()
    assert data["total"] == 3
    assert "by_severity" in data
    assert "by_status" in data
