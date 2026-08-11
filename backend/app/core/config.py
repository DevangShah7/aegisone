"""Application settings.

Single source of truth for runtime configuration. All values are loaded
from environment variables (or the .env file in development). Settings
are typed via pydantic-settings so misconfiguration fails fast at startup.
"""

from __future__ import annotations

import ipaddress
import logging
from functools import lru_cache
from typing import Final

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Branding constants — used by OpenAPI metadata, /about endpoint, response headers.
APP_NAME: Final[str] = "AegisOne"
APP_TAGLINE: Final[str] = "Secure Remote Device Management"
DEVELOPER_NAME: Final[str] = "Devang Shah"


class Settings(BaseSettings):
    """Typed application configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Runtime
    environment: str = Field(default="dev", description="One of: dev, staging, prod")
    log_level: str = Field(default="INFO")
    app_version: str = Field(default="0.1.0")

    # Branding (overridable via env for self-hosted builds)
    developer_name: str = Field(default=DEVELOPER_NAME)
    app_name: str = Field(default=APP_NAME)
    app_tagline: str = Field(default=APP_TAGLINE)

    # Database — psycopg (v3) async driver. URL scheme is
    # `postgresql+psycopg` for async use with SQLAlchemy 2.x.
    database_url: str = Field(
        default="postgresql+psycopg://aegisone:aegisone_dev_only@localhost:5432/aegisone"
    )
    database_pool_size: int = Field(default=10, ge=1, le=100)

    # Redis
    redis_url: str = Field(default="redis://localhost:6379/0")

    # Auth
    # NOTE: the default sentinel is exactly 32 bytes (the HMAC-SHA256 minimum
    # per RFC 7518 §3.2). It must be replaced via JWT_SECRET_KEY /
    # JWT_REFRESH_SECRET_KEY in any non-dev environment; the lifespan
    # bootstrap in app/main.py refuses to boot in `production` if either
    # is left at this default.
    _JWT_DEV_SENTINEL: Final[str] = "AEGISONE_DEV_ONLY_REPLACE_ME_!!!"  # 32 bytes
    jwt_secret_key: str = Field(default=_JWT_DEV_SENTINEL)
    jwt_refresh_secret_key: str = Field(default=_JWT_DEV_SENTINEL)
    jwt_algorithm: str = Field(default="HS256")
    access_token_expire_minutes: int = Field(default=15, ge=1, le=1440)
    refresh_token_expire_days: int = Field(default=30, ge=1, le=365)

    # CORS / proxy
    cors_origins: str = Field(default="http://localhost:3000")
    trusted_proxies: str = Field(default="127.0.0.1/32,::1/128")

    # MinIO
    minio_endpoint: str = Field(default="localhost:9000")
    minio_access_key: str = Field(default="aegisone")
    minio_secret_key: str = Field(default="aegisone_dev_only")
    minio_bucket: str = Field(default="aegisone")

    # Rate limits (sliding window)
    rate_limit_login_per_min: int = Field(default=5, ge=1)
    rate_limit_login_per_email_per_min: int = Field(default=10, ge=1)
    rate_limit_register_per_hour: int = Field(default=3, ge=1)

    # Server
    app_port: int = Field(default=8000, ge=1, le=65535)

    @field_validator("environment")
    @classmethod
    def _validate_environment(cls, v: str) -> str:
        v = v.lower().strip()
        if v not in {"dev", "staging", "prod", "production", "development"}:
            raise ValueError("environment must be one of: dev, staging, prod")
        # Normalize.
        return {"production": "prod", "development": "dev"}.get(v, v)

    @field_validator("cors_origins")
    @classmethod
    def _validate_cors(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("cors_origins must not be empty")
        return v

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def trusted_proxy_networks(self) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
        nets: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
        for raw in self.trusted_proxies.split(","):
            raw = raw.strip()
            if not raw:
                continue
            nets.append(ipaddress.ip_network(raw, strict=False))
        return nets

    @property
    def is_production(self) -> bool:
        return self.environment == "prod"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings accessor.

    Tests should clear the cache via ``get_settings.cache_clear()`` after
    mutating environment variables.
    """
    return Settings()


settings = get_settings()


def _configure_logger_once() -> None:
    """No-op placeholder kept for backwards-compatibility with older imports."""


_logging_configured = False


def _ensure_logging_configured() -> None:
    global _logging_configured
    if _logging_configured:
        return
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    _logging_configured = True


_ensure_logging_configured()  # noqa: E402  (side-effect import; intentional)
