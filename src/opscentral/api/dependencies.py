"""API dependencies for authentication and common operations."""

from typing import Optional

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader

from src.opscentral.config import get_settings

settings = get_settings()

# API key header security
api_key_header = APIKeyHeader(name=settings.api_key_header, auto_error=False)


async def get_current_api_key(
    api_key: Optional[str] = Security(api_key_header),
) -> Optional[str]:
    """Extract API key from request header.

    Returns None if no API key is configured (authentication disabled).
    """
    return api_key


async def verify_api_key(
    api_key: Optional[str] = Depends(get_current_api_key),
) -> bool:
    """Verify API key if authentication is enabled.

    Raises:
        HTTPException: If API key is required but missing or invalid
    """
    # If no API key is configured, authentication is disabled
    if not settings.api_key:
        return True

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    if api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key",
        )

    return True
