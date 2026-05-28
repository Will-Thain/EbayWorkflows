from __future__ import annotations

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = Field(default="local", alias="APP_ENV")
    log_level: str = Field(default="info", alias="LOG_LEVEL")
    workflow_default_name: str = Field(default="ebay_mtg_scan", alias="WORKFLOW_DEFAULT_NAME")
    base_currency: str = Field(default="EUR", alias="BASE_CURRENCY")

    database_url: str = Field(alias="DATABASE_URL")
    db_pool_min: int = Field(default=1, alias="DB_POOL_MIN")
    db_pool_max: int = Field(default=10, alias="DB_POOL_MAX")
    db_statement_timeout_ms: int = Field(default=30000, alias="DB_STATEMENT_TIMEOUT_MS")

    enable_ebay_api: bool = Field(default=True, alias="ENABLE_EBAY_API")
    ebay_client_id: str | None = Field(default=None, alias="EBAY_CLIENT_ID")
    ebay_client_secret: str | None = Field(default=None, alias="EBAY_CLIENT_SECRET")
    ebay_marketplace_id: str = Field(default="EBAY_GB", alias="EBAY_MARKETPLACE_ID")
    ebay_page_size: int = Field(default=50, alias="EBAY_PAGE_SIZE")
    ebay_max_pages_per_run: int = Field(default=20, alias="EBAY_MAX_PAGES_PER_RUN")
    ebay_requests_per_minute: int | None = Field(default=None, alias="EBAY_REQUESTS_PER_MINUTE")

    scryfall_bulk_uri: str = Field(alias="SCRYFALL_BULK_URI")
    scryfall_bulk_cache_path: str = Field(default="./data/scryfall/default-cards.json", alias="SCRYFALL_BULK_CACHE_PATH")
    scryfall_sync_interval_hours: int = Field(default=24, alias="SCRYFALL_SYNC_INTERVAL_HOURS")
    scryfall_requests_per_minute: int = Field(default=30, alias="SCRYFALL_REQUESTS_PER_MINUTE")

    cardmarket_bulk_file_path: str = Field(alias="CARDMARKET_BULK_FILE_PATH")
    cardmarket_bulk_refresh_hours: int = Field(default=24, alias="CARDMARKET_BULK_REFRESH_HOURS")

    image_cache_dir: str = Field(alias="IMAGE_CACHE_DIR")
    image_download_timeout_ms: int = Field(default=20000, alias="IMAGE_DOWNLOAD_TIMEOUT_MS")
    ocr_engine: str = Field(default="paddleocr", alias="OCR_ENGINE")
    faiss_index_path: str = Field(alias="FAISS_INDEX_PATH")
    openclip_model_name: str = Field(default="ViT-B-32", alias="OPENCLIP_MODEL_NAME")

    global_requests_per_minute_cap: int = Field(alias="GLOBAL_REQUESTS_PER_MINUTE_CAP")
    enable_provider_policy_checks: bool = Field(default=True, alias="ENABLE_PROVIDER_POLICY_CHECKS")
    disable_live_api_writes: bool = Field(default=True, alias="DISABLE_LIVE_API_WRITES")

    @model_validator(mode="after")
    def validate_policy_and_limits(self) -> "Settings":
        positive_fields = {
            "DB_POOL_MIN": self.db_pool_min,
            "DB_POOL_MAX": self.db_pool_max,
            "DB_STATEMENT_TIMEOUT_MS": self.db_statement_timeout_ms,
            "EBAY_PAGE_SIZE": self.ebay_page_size,
            "EBAY_MAX_PAGES_PER_RUN": self.ebay_max_pages_per_run,
            "SCRYFALL_SYNC_INTERVAL_HOURS": self.scryfall_sync_interval_hours,
            "SCRYFALL_REQUESTS_PER_MINUTE": self.scryfall_requests_per_minute,
            "CARDMARKET_BULK_REFRESH_HOURS": self.cardmarket_bulk_refresh_hours,
            "IMAGE_DOWNLOAD_TIMEOUT_MS": self.image_download_timeout_ms,
            "GLOBAL_REQUESTS_PER_MINUTE_CAP": self.global_requests_per_minute_cap,
        }
        for key, value in positive_fields.items():
            if value <= 0:
                raise ValueError(f"{key} must be a positive integer")

        if self.db_pool_min > self.db_pool_max:
            raise ValueError("DB_POOL_MIN cannot be greater than DB_POOL_MAX")

        if self.enable_ebay_api:
            if not self.ebay_client_id or not self.ebay_client_secret:
                raise ValueError("EBAY_CLIENT_ID and EBAY_CLIENT_SECRET are required when ENABLE_EBAY_API=true")
            if self.ebay_requests_per_minute is None or self.ebay_requests_per_minute <= 0:
                raise ValueError("EBAY_REQUESTS_PER_MINUTE must be a positive integer when ENABLE_EBAY_API=true")

        # Keep global cap conservative compared to per-provider aggregate.
        ebay_budget = self.ebay_requests_per_minute if self.enable_ebay_api and self.ebay_requests_per_minute else 0
        provider_sum = ebay_budget + self.scryfall_requests_per_minute
        if (
            not self.disable_live_api_writes
            and self.global_requests_per_minute_cap > provider_sum
        ):
            raise ValueError(
                "GLOBAL_REQUESTS_PER_MINUTE_CAP must be <= sum of active provider request-per-minute budgets "
                "when live API writes are enabled"
            )

        if self.app_env.lower() != "local" and not self.enable_provider_policy_checks:
            raise ValueError(
                "ENABLE_PROVIDER_POLICY_CHECKS must remain true outside local environment"
            )

        return self

