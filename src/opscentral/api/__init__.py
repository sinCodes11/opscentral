"""API package for OpsCentral."""

from src.opscentral.api.dependencies import get_current_api_key, verify_api_key

__all__ = ["get_current_api_key", "verify_api_key"]
