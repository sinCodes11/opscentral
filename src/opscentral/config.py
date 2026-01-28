"""Configuration management for OpsCentral.

Loads settings from environment variables with validation.
"""

from functools import lru_cache
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application
    app_name: str = "OpsCentral"
    app_version: str = "1.0.0"
    debug: bool = False
    log_level: str = Field(default="INFO", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")

    # Database
    database_url: str = Field(
        default="postgresql://opscentral:password@localhost:5432/opscentral"
    )

    # Redis
    redis_url: str = Field(default="redis://localhost:6379/0")

    # API Security
    api_key: Optional[str] = Field(default=None)
    api_key_header: str = "X-API-Key"

    # OCI Configuration
    oci_config_file: Optional[str] = Field(default=None)
    oci_tenancy_ocid: Optional[str] = Field(default=None)
    oci_user_ocid: Optional[str] = Field(default=None)
    oci_compartment_ocid: Optional[str] = Field(default=None)
    oci_region: str = Field(default="us-ashburn-1")

    # Collection intervals (seconds)
    alert_collection_interval: int = Field(default=60, ge=10)
    metrics_collection_interval: int = Field(default=300, ge=60)

    # External integrations
    splunk_hec_url: Optional[str] = Field(default=None)
    splunk_hec_token: Optional[str] = Field(default=None)
    slack_webhook_url: Optional[str] = Field(default=None)

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        """Ensure database URL uses postgresql scheme."""
        if not v.startswith(("postgresql://", "postgresql+asyncpg://")):
            raise ValueError("Database URL must use postgresql:// scheme")
        return v

    @field_validator("redis_url")
    @classmethod
    def validate_redis_url(cls, v: str) -> str:
        """Ensure Redis URL uses redis scheme."""
        if not v.startswith("redis://"):
            raise ValueError("Redis URL must use redis:// scheme")
        return v

    @property
    def oci_configured(self) -> bool:
        """Check if OCI credentials are configured."""
        return all([
            self.oci_tenancy_ocid,
            self.oci_compartment_ocid,
        ])

    class Config:
        """Pydantic configuration."""

        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
