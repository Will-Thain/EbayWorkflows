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
    ebay_sandbox_client_id: str | None = Field(default=None, alias="EBAY_SANDBOX_CLIENT_ID")
    ebay_sandbox_client_secret: str | None = Field(default=None, alias="EBAY_SANDBOX_CLIENT_SECRET")
    ebay_use_sandbox: bool = Field(default=False, alias="EBAY_USE_SANDBOX")
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
    ocr_engine: str = Field(default="pytesseract", alias="OCR_ENGINE")
    tesseract_cmd: str | None = Field(default=None, alias="TESSERACT_CMD")
    faiss_index_path: str = Field(alias="FAISS_INDEX_PATH")
    faiss_top_k: int = Field(default=5, alias="FAISS_TOP_K")
    faiss_build_max_cards: int = Field(default=10000, alias="FAISS_BUILD_MAX_CARDS")
    faiss_index_use_art_zone: bool = Field(default=True, alias="FAISS_INDEX_USE_ART_ZONE")
    faiss_build_all_cards: bool = Field(default=False, alias="FAISS_BUILD_ALL_CARDS")
    openclip_model_name: str = Field(default="ViT-B-32", alias="OPENCLIP_MODEL_NAME")
    torch_device: str = Field(default="cpu", alias="TORCH_DEVICE")
    embedding_batch_size: int = Field(default=32, alias="EMBEDDING_BATCH_SIZE")
    image_min_region_score: float = Field(default=0.55, alias="IMAGE_MIN_REGION_SCORE")
    image_allow_full_frame_fallback: bool = Field(default=True, alias="IMAGE_ALLOW_FULL_FRAME_FALLBACK")
    pipeline_max_image_workers: int = Field(default=4, alias="PIPELINE_MAX_IMAGE_WORKERS")
    pipeline_max_download_workers: int = Field(default=8, alias="PIPELINE_MAX_DOWNLOAD_WORKERS")
    pipeline_max_title_match_workers: int = Field(default=12, alias="PIPELINE_MAX_TITLE_MATCH_WORKERS")
    title_match_prefilter_size: int = Field(default=512, alias="TITLE_MATCH_PREFILTER_SIZE")
    title_match_score_cutoff: float = Field(default=65.0, alias="TITLE_MATCH_SCORE_CUTOFF")
    phase2_skip_unchanged_listings: bool = Field(default=True, alias="PHASE2_SKIP_UNCHANGED_LISTINGS")
    phase1_skip_existing_listings: bool = Field(default=True, alias="PHASE1_SKIP_EXISTING_LISTINGS")
    phase1_commit_batch_size: int = Field(default=50, alias="PHASE1_COMMIT_BATCH_SIZE")
    phase1_image_download_chunk_size: int = Field(default=100, alias="PHASE1_IMAGE_DOWNLOAD_CHUNK_SIZE")
    phase1_refresh_after_hours: int | None = Field(default=None, alias="PHASE1_REFRESH_AFTER_HOURS")
    phase5_skip_analyzed_images: bool = Field(default=False, alias="PHASE5_SKIP_ANALYZED_IMAGES")
    phase6_skip_analyzed_images: bool = Field(default=False, alias="PHASE6_SKIP_ANALYZED_IMAGES")
    pipeline_lock_path: str = Field(default="./.cache/pipeline.lock", alias="PIPELINE_LOCK_PATH")
    pipeline_enforce_single_run: bool = Field(default=True, alias="PIPELINE_ENFORCE_SINGLE_RUN")
    image_download_requests_per_minute: int = Field(default=120, alias="IMAGE_DOWNLOAD_REQUESTS_PER_MINUTE")
    fx_gbp_to_eur: float | None = Field(default=1.17, alias="FX_GBP_TO_EUR")
    title_match_min_score_for_pricing: float = Field(default=0.90, alias="TITLE_MATCH_MIN_SCORE_FOR_PRICING")
    title_match_min_score_non_mtg: float = Field(default=0.98, alias="TITLE_MATCH_MIN_SCORE_NON_MTG")
    phase2_skip_bulk_lot_title_match: bool = Field(default=True, alias="PHASE2_SKIP_BULK_LOT_TITLE_MATCH")
    image_evidence_min_ocr_similarity: float = Field(default=0.60, alias="IMAGE_EVIDENCE_MIN_OCR_SIMILARITY")
    image_evidence_min_faiss_score: float = Field(default=0.55, alias="IMAGE_EVIDENCE_MIN_FAISS_SCORE")
    image_evidence_min_mana_confidence: float = Field(default=0.30, alias="IMAGE_EVIDENCE_MIN_MANA_CONFIDENCE")
    cardmarket_max_unit_price_eur: float = Field(default=250.0, alias="CARDMARKET_MAX_UNIT_PRICE_EUR")
    ev_max_listing_cost_multiple: float = Field(default=10.0, alias="EV_MAX_LISTING_COST_MULTIPLE")
    phase6_bulk_listings_only: bool = Field(default=True, alias="PHASE6_BULK_LISTINGS_ONLY")
    phase6_min_lot_detections: int = Field(default=2, alias="PHASE6_MIN_LOT_DETECTIONS")
    phase6_max_lot_ev_multiple: float = Field(default=50.0, alias="PHASE6_MAX_LOT_EV_MULTIPLE")
    phase6_use_faiss_crop_match: bool = Field(default=True, alias="PHASE6_USE_FAISS_CROP_MATCH")
    phase6_min_crop_match_confidence: float = Field(
        default=0.42, alias="PHASE6_MIN_CROP_MATCH_CONFIDENCE"
    )
    cardmarket_condition_multiplier_nm: float = Field(default=1.0, alias="CARDMARKET_CONDITION_MULTIPLIER_NM")
    cardmarket_condition_multiplier_lp: float = Field(default=0.85, alias="CARDMARKET_CONDITION_MULTIPLIER_LP")
    cardmarket_condition_multiplier_mp: float = Field(default=0.70, alias="CARDMARKET_CONDITION_MULTIPLIER_MP")
    cardmarket_condition_multiplier_hp: float = Field(default=0.55, alias="CARDMARKET_CONDITION_MULTIPLIER_HP")
    cardmarket_condition_multiplier_dmg: float = Field(default=0.40, alias="CARDMARKET_CONDITION_MULTIPLIER_DMG")
    cardmarket_condition_multiplier_unspecified: float = Field(
        default=0.95, alias="CARDMARKET_CONDITION_MULTIPLIER_UNSPECIFIED"
    )
    card_zone_ocr_enabled: bool = Field(default=True, alias="CARD_ZONE_OCR_ENABLED")
    card_zone_faiss_enabled: bool = Field(default=True, alias="CARD_ZONE_FAISS_ENABLED")
    card_zone_align_enabled: bool = Field(default=True, alias="CARD_ZONE_ALIGN_ENABLED")
    card_set_symbol_match_enabled: bool = Field(default=True, alias="CARD_SET_SYMBOL_MATCH_ENABLED")
    card_set_symbol_min_score: float = Field(default=0.45, alias="CARD_SET_SYMBOL_MIN_SCORE")
    card_mana_cost_enabled: bool = Field(default=True, alias="CARD_MANA_COST_ENABLED")
    align_min_confidence: float = Field(default=0.35, alias="ALIGN_MIN_CONFIDENCE")
    verify_name_hard_min: float = Field(default=0.75, alias="VERIFY_NAME_HARD_MIN")
    verify_name_strong_min: float = Field(default=0.88, alias="VERIFY_NAME_STRONG_MIN")
    verify_symbol_strong_min: float = Field(default=0.55, alias="VERIFY_SYMBOL_STRONG_MIN")
    faiss_propose_candidates: bool = Field(default=True, alias="FAISS_PROPOSE_CANDIDATES")

    global_requests_per_minute_cap: int = Field(alias="GLOBAL_REQUESTS_PER_MINUTE_CAP")
    enable_provider_policy_checks: bool = Field(default=True, alias="ENABLE_PROVIDER_POLICY_CHECKS")
    disable_live_api_writes: bool = Field(default=True, alias="DISABLE_LIVE_API_WRITES")

    @property
    def resolved_ebay_client_id(self) -> str | None:
        if self.ebay_use_sandbox:
            return self.ebay_sandbox_client_id
        return self.ebay_client_id

    @property
    def resolved_ebay_client_secret(self) -> str | None:
        if self.ebay_use_sandbox:
            return self.ebay_sandbox_client_secret
        return self.ebay_client_secret

    @staticmethod
    def _strip_optional(value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

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
            "FAISS_TOP_K": self.faiss_top_k,
            "FAISS_BUILD_MAX_CARDS": self.faiss_build_max_cards,
            "EMBEDDING_BATCH_SIZE": self.embedding_batch_size,
            "PIPELINE_MAX_IMAGE_WORKERS": self.pipeline_max_image_workers,
            "PIPELINE_MAX_DOWNLOAD_WORKERS": self.pipeline_max_download_workers,
            "PIPELINE_MAX_TITLE_MATCH_WORKERS": self.pipeline_max_title_match_workers,
            "PHASE1_COMMIT_BATCH_SIZE": self.phase1_commit_batch_size,
            "PHASE1_IMAGE_DOWNLOAD_CHUNK_SIZE": self.phase1_image_download_chunk_size,
        }
        for key, value in positive_fields.items():
            if value <= 0:
                raise ValueError(f"{key} must be a positive integer")

        if self.db_pool_min > self.db_pool_max:
            raise ValueError("DB_POOL_MIN cannot be greater than DB_POOL_MAX")

        if not 0 < self.title_match_score_cutoff <= 100:
            raise ValueError("TITLE_MATCH_SCORE_CUTOFF must be > 0 and <= 100")

        multiplier_fields = {
            "CARDMARKET_CONDITION_MULTIPLIER_NM": self.cardmarket_condition_multiplier_nm,
            "CARDMARKET_CONDITION_MULTIPLIER_LP": self.cardmarket_condition_multiplier_lp,
            "CARDMARKET_CONDITION_MULTIPLIER_MP": self.cardmarket_condition_multiplier_mp,
            "CARDMARKET_CONDITION_MULTIPLIER_HP": self.cardmarket_condition_multiplier_hp,
            "CARDMARKET_CONDITION_MULTIPLIER_DMG": self.cardmarket_condition_multiplier_dmg,
            "CARDMARKET_CONDITION_MULTIPLIER_UNSPECIFIED": self.cardmarket_condition_multiplier_unspecified,
        }
        for key, value in multiplier_fields.items():
            if value <= 0 or value > 1.5:
                raise ValueError(f"{key} must be > 0 and <= 1.5")

        if not 0 < self.card_set_symbol_min_score <= 1:
            raise ValueError("CARD_SET_SYMBOL_MIN_SCORE must be > 0 and <= 1")

        if not 0 < self.image_evidence_min_mana_confidence <= 1:
            raise ValueError("IMAGE_EVIDENCE_MIN_MANA_CONFIDENCE must be > 0 and <= 1")

        if not 0 < self.phase6_min_crop_match_confidence <= 1:
            raise ValueError("PHASE6_MIN_CROP_MATCH_CONFIDENCE must be > 0 and <= 1")

        try:
            from .services.openclip_runtime import normalize_torch_device

            normalize_torch_device(self.torch_device)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc

        self.ebay_client_id = self._strip_optional(self.ebay_client_id)
        self.ebay_client_secret = self._strip_optional(self.ebay_client_secret)
        self.ebay_sandbox_client_id = self._strip_optional(self.ebay_sandbox_client_id)
        self.ebay_sandbox_client_secret = self._strip_optional(self.ebay_sandbox_client_secret)

        if self.enable_ebay_api:
            if not self.resolved_ebay_client_id or not self.resolved_ebay_client_secret:
                if self.ebay_use_sandbox:
                    raise ValueError(
                        "EBAY_SANDBOX_CLIENT_ID and EBAY_SANDBOX_CLIENT_SECRET are required when "
                        "ENABLE_EBAY_API=true and EBAY_USE_SANDBOX=true"
                    )
                raise ValueError(
                    "EBAY_CLIENT_ID and EBAY_CLIENT_SECRET are required when "
                    "ENABLE_EBAY_API=true and EBAY_USE_SANDBOX=false"
                )
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

    @property
    def fx_rates_to_base(self) -> dict[str, float]:
        """Currency code -> multiply-by rate to reach BASE_CURRENCY."""
        target = self.base_currency.upper()
        rates: dict[str, float] = {}
        if target == "EUR" and self.fx_gbp_to_eur is not None:
            rates["GBP"] = self.fx_gbp_to_eur
        return rates

