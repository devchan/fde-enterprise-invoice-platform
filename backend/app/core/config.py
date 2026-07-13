from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_JWT_SECRET = "change-me-in-local-only"
MIN_PRODUCTION_JWT_SECRET_LENGTH = 32
# Environments where insecure defaults are tolerated (local dev, automated tests, CI).
NON_PRODUCTION_ENVIRONMENTS = {"local", "development", "dev", "test", "testing", "ci"}


class Settings(BaseSettings):
    app_name: str = "FDE Enterprise Invoice Platform"
    app_env: str = "local"
    app_debug: bool = True
    database_url: str = "postgresql+psycopg://invoice_user:invoice_pass@localhost:5432/invoice_platform"
    redis_url: str = "redis://localhost:6379/0"
    processing_queue_name: str = "invoice_processing_jobs"
    worker_poll_timeout_seconds: int = 5
    worker_sleep_seconds: int = 1
    processing_job_max_attempts: int = 3
    openai_api_key: str = ""
    openai_extraction_model: str = "gpt-4.1"
    openai_input_cost_per_million_tokens: str = "0"
    openai_output_cost_per_million_tokens: str = "0"
    # Gemini is an alternative extraction provider (free tier). Its key being set
    # is what makes the "gemini" option selectable; empty means unavailable.
    gemini_api_key: str = ""
    gemini_extraction_model: str = "gemini-flash-latest"
    gemini_input_cost_per_million_tokens: str = "0"
    gemini_output_cost_per_million_tokens: str = "0"
    object_storage_bucket: str = "invoice-platform-local"
    object_storage_backend: str = "local"
    object_storage_local_path: str = ".local-storage"
    object_storage_endpoint_url: str = ""
    object_storage_region: str = "us-east-1"
    object_storage_access_key_id: str = ""
    object_storage_secret_access_key: str = ""
    invoice_file_download_url_ttl_seconds: int = 300
    invoice_upload_max_bytes: int = 10 * 1024 * 1024
    upload_rate_limit_enabled: bool = True
    upload_rate_limit_requests: int = 20
    upload_rate_limit_window_seconds: int = 60
    cors_allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    jwt_secret: str = DEFAULT_JWT_SECRET
    jwt_access_token_ttl_seconds: int = 3600
    jwt_refresh_token_ttl_seconds: int = 1209600  # 14 days
    cookie_secure: bool = True
    cookie_samesite: str = "lax"
    login_rate_limit_enabled: bool = True
    login_rate_limit_requests: int = 10
    login_rate_limit_window_seconds: int = 300
    otel_enabled: bool = False
    otel_service_name: str = "invoice-platform-backend"
    otel_exporter_otlp_endpoint: str = ""
    otel_console_export: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def is_production_like(self) -> bool:
        return self.app_env.strip().lower() not in NON_PRODUCTION_ENVIRONMENTS

    @model_validator(mode="after")
    def _enforce_production_secrets(self) -> "Settings":
        """Fail fast at startup if a production-like deployment boots with an
        insecure JWT secret, rather than silently signing forgeable tokens."""
        if not self.is_production_like:
            return self
        if self.jwt_secret == DEFAULT_JWT_SECRET or not self.jwt_secret.strip():
            raise ValueError(
                f"JWT_SECRET must be overridden with a strong value when APP_ENV is "
                f"'{self.app_env}' (the built-in default must not be used outside local/test)."
            )
        if len(self.jwt_secret) < MIN_PRODUCTION_JWT_SECRET_LENGTH:
            raise ValueError(
                f"JWT_SECRET must be at least {MIN_PRODUCTION_JWT_SECRET_LENGTH} characters "
                f"when APP_ENV is '{self.app_env}'."
            )
        return self


settings = Settings()
