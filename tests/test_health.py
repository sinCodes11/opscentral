"""Tests for health endpoint."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_endpoint(client: AsyncClient):
    """Test that health endpoint returns expected structure."""
    response = await client.get("/api/v1/health")

    assert response.status_code == 200

    data = response.json()
    assert "status" in data
    assert "timestamp" in data
    assert "version" in data
    assert "components" in data


@pytest.mark.asyncio
async def test_root_endpoint(client: AsyncClient):
    """Test that root endpoint returns API info."""
    response = await client.get("/")

    assert response.status_code == 200

    data = response.json()
    assert data["name"] == "OpsCentral"
    assert "version" in data
