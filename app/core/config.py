"""Application configuration via environment variables."""
from typing import Literal
from uuid import UUID

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # App
    APP_ENV: Literal["local", "staging", "prod"] = "local"
    APP_NAME: str = "chatbot"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    APP_DEBUG: bool = False
    APP_SECRET_KEY: str = Field(..., min_length=32)
    APP_BASE_URL: str = "http://localhost:8000"
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:8000"]

    # Database
    DATABASE_URL: str
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # LLM providers
    ANTHROPIC_API_KEY: str = ""
    GOOGLE_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    TAVILY_API_KEY: str = ""

    # LLM defaults
    LLM_DEFAULT_TIER: Literal["cheap", "main", "hard"] = "main"
    LLM_CHEAP_MODEL: str = "gemini-2.5-flash"
    LLM_MAIN_MODEL: str = "claude-haiku-4-5-20251001"
    LLM_HARD_MODEL: str = "claude-opus-4-7"
    LLM_MAX_TOKENS: int = 4096
    LLM_MAX_ITERATIONS: int = 5

    # Embedding
    EMBEDDING_MODEL: str = "text-embedding-004"
    EMBEDDING_DIM: int = 768

    # SSO
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    MICROSOFT_CLIENT_ID: str = ""
    MICROSOFT_CLIENT_SECRET: str = ""
    MICROSOFT_TENANT_ID: str = "common"

    # JWT
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_EXPIRE_DAYS: int = 7

    # Quota
    QUOTA_EXTERNAL_MESSAGES: int = 50
    QUOTA_INTERNAL_MESSAGES: int = 500
    QUOTA_EXTERNAL_TOKENS: int = 50_000
    QUOTA_INTERNAL_TOKENS: int = 500_000
    QUOTA_EXTERNAL_COST_USD: float = 0.50
    QUOTA_INTERNAL_COST_USD: float = 5.00

    # Cache
    CACHE_L1_TTL_SECONDS: int = 3600

    # Observability
    OTEL_EXPORTER_OTLP_ENDPOINT: str = ""
    OTEL_SERVICE_NAME: str = "chatbot"
    LANGFUSE_PUBLIC_KEY: str = ""
    LANGFUSE_SECRET_KEY: str = ""
    LANGFUSE_HOST: str = "https://cloud.langfuse.com"

    # Storage
    AZURE_STORAGE_CONNECTION_STRING: str = ""
    AZURE_BLOB_CONTAINER: str = "chatbot-docs"

    # Tenant
    DEFAULT_TENANT_ID: UUID = UUID("00000000-0000-0000-0000-000000000001")

    # Channels (Phase 7)
    SLACK_BOT_TOKEN: str = ""
    SLACK_SIGNING_SECRET: str = ""
    TELEGRAM_BOT_TOKEN: str = ""

    # Email (Phase 8)
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""
    SMTP_USE_TLS: bool = False  # use STARTTLS by default on port 587
    COST_REPORT_RECIPIENTS: str = ""  # comma-separated emails


settings = Settings()  # type: ignore[call-arg]
