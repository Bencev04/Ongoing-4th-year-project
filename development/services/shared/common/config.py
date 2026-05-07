"""
Configuration management for all microservices.

Provides centralized configuration using Pydantic settings
with environment variable support for different deployment environments.
"""

import logging
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# SECRET_KEY values that are known-insecure defaults; reject them outside dev.
_INSECURE_SECRET_KEYS = frozenset(
    {
        "your-secret-key-change-in-production",
        "your-super-secret-key-change-this-in-production",
        "changeme",
        "secret",
    }
)


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    Attributes:
        app_name:                    Name of the application.
        debug:                       Debug mode flag.
        database_url:                PostgreSQL connection string.
        test_database_url:           PostgreSQL connection string for testing.
        secret_key:                  Secret key for JWT and session management.
        algorithm:                   JWT signing algorithm.
        access_token_expire_minutes: Access-token lifetime in minutes.
        refresh_token_expire_days:   Refresh-token lifetime in days.
        user_service_url:            User DB-access service base URL.
        customer_service_url:        Customer DB-access service base URL.
        job_service_url:             Job DB-access service base URL.
        auth_service_url:            Auth service base URL.
        user_bl_service_url:         User BL service base URL.
        job_bl_service_url:          Job BL service base URL.
        customer_bl_service_url:     Customer BL service base URL.
        admin_bl_service_url:        Admin BL service base URL.
        redis_url:                   Redis connection URL.
        cache_ttl_short:             TTL for frequently changing data (seconds).
        cache_ttl_medium:            TTL for moderately stable data (seconds).
        cache_ttl_long:              TTL for rarely changing data (seconds).
    """

    # Application
    app_name: str = "Workflow Platform"
    debug: bool = False

    # Database
    database_url: str = (
        "postgresql://postgres:postgres@localhost:5432/workflow_platform"
    )
    test_database_url: str = (
        "postgresql://postgres:postgres@localhost:5432/workflow_platform_test"
    )

    # Security
    secret_key: str = "your-secret-key-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # Service URLs (for inter-service communication)
    # DB Access Layer
    user_service_url: str = "http://user-db-access-service:8001"
    customer_service_url: str = "http://customer-db-access-service:8002"
    job_service_url: str = "http://job-db-access-service:8003"

    # Business Logic Layer
    auth_service_url: str = "http://auth-service:8005"
    user_bl_service_url: str = "http://user-bl-service:8004"
    job_bl_service_url: str = "http://job-bl-service:8006"
    customer_bl_service_url: str = "http://customer-bl-service:8007"
    admin_bl_service_url: str = "http://admin-bl-service:8008"

    # Notification Service
    notification_service_url: str = "http://notification-service:8011"

    # SMTP (email notifications)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = "noreply@workflow.local"
    smtp_from_name: str = "Workflow Platform"
    smtp_use_tls: bool = False

    # Notification encryption
    notification_encryption_key: str = ""

    # Maps Access Layer
    maps_service_url: str = "http://maps-access-service:8009"

    # Google Maps
    google_maps_browser_key: str = ""
    google_maps_server_key: str = ""
    google_maps_map_id: str = ""

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # CORS — comma-separated origins; "*" allows all (use only in dev)
    cors_origins: str = "*"

    # Cache TTL defaults (seconds)
    cache_ttl_short: int = 30  # Frequently changing data
    cache_ttl_medium: int = 120  # Moderately stable data
    cache_ttl_long: int = 300  # Rarely changing data

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance.

    Returns:
        Settings: Application settings singleton
    """
    settings = Settings()
    _warn_insecure_secret_key(settings.secret_key)
    return settings


def _warn_insecure_secret_key(key: str) -> None:
    """Log a critical warning if a known-insecure SECRET_KEY is in use."""
    if key.lower().strip() in _INSECURE_SECRET_KEYS:
        logger.critical(
            "SECURITY: SECRET_KEY is set to a known insecure default! "
            "Set a strong, unique SECRET_KEY environment variable before "
            "deploying to staging or production."
        )


# Global settings instance
settings = get_settings()
