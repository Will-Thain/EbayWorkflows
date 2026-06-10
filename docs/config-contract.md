# Configuration Contract

## Purpose

Define all required environment variables, defaults, and validation rules.

Recognition/matching variables are **[Shipped]** unless noted **[Future]** in `documentation-status.md` (e.g. threshold calibration).

## Environment variable prefixes

| Prefix | Scope | Examples |
|--------|-------|----------|
| `VERIFY_*` | Trust / image verification thresholds | `VERIFY_NAME_HARD_MIN`, `VERIFY_SYMBOL_STRONG_MIN` |
| `PHASE1_*` … `PHASE6_*` | Phase-specific pipeline behaviour | `PHASE5_SKIP_ANALYZED_IMAGES`, `PHASE6_BULK_LISTINGS_ONLY` |
| `FAISS_*`, `OPENCLIP_*`, `TORCH_*` | Embedding index and GPU | `FAISS_INDEX_PATH`, `TORCH_DEVICE` |
| `IMAGE_*`, `CARD_ZONE_*`, `LOT_CROP_*` | CV / OCR (shared with library via adapter) | `IMAGE_CACHE_DIR`, `OCR_ENGINE` |
| `EBAY_*` | eBay Browse OAuth and ingest | `EBAY_CLIENT_ID`, `EBAY_PAGE_SIZE` |
| `SCRYFALL_*`, `CARDMARKET_*` | Reference data providers | `SCRYFALL_BULK_URI` |
| `TITLE_MATCH_*` | Phase 2 title fuzzy match | `TITLE_MATCH_SCORE_CUTOFF` |
| `PIPELINE_*` | Workers, lock, resume | `PIPELINE_MAX_IMAGE_WORKERS`, `PIPELINE_LOCK_PATH` |
| `GLOBAL_*` | Cross-provider rate limits | `GLOBAL_REQUESTS_PER_MINUTE_CAP` (eBay, Scryfall, Cardmarket, **image CDN**) |
| `FX_*`, `EV_*`, `CARDMARKET_MAX_*` | Pricing / guardrails | `FX_GBP_TO_EUR`, `EV_MAX_LISTING_COST_MULTIPLE` |

Phase-scoped flags use `PHASEn_`; trust knobs use `VERIFY_*` even when they affect Phase 5.

**Removed:** `IMAGE_DOWNLOAD_REQUESTS_PER_MINUTE` — unused; image downloads share `GLOBAL_REQUESTS_PER_MINUTE_CAP`.

## Core Runtime

- `APP_ENV` (`local` default)
- `LOG_LEVEL` (`info` default)
- `WORKFLOW_DEFAULT_NAME` (`ebay_mtg_scan` default)
- `BASE_CURRENCY` (`EUR` default)

## Database

- `DATABASE_URL` (required)
- `DB_POOL_MIN` (default `1`)
- `DB_POOL_MAX` (default `10`)
- `DB_STATEMENT_TIMEOUT_MS` (default `30000`)

## eBay

- `ENABLE_EBAY_API` (default `true`; set `false` to temporarily disable eBay live calls)
- `EBAY_CLIENT_ID` (production App ID; required when `ENABLE_EBAY_API=true` and `EBAY_USE_SANDBOX=false`)
- `EBAY_CLIENT_SECRET` (production Client Secret; required with production client ID above)
- `EBAY_SANDBOX_CLIENT_ID` (sandbox App ID; required when `ENABLE_EBAY_API=true` and `EBAY_USE_SANDBOX=true`)
- `EBAY_SANDBOX_CLIENT_SECRET` (sandbox Client Secret; required with sandbox client ID above)
- `EBAY_USE_SANDBOX` (default `false`; selects which credential pair is used for OAuth and Browse)
- `EBAY_MARKETPLACE_ID` (default `EBAY_GB`)
- `EBAY_PAGE_SIZE` (default `50`)
- `EBAY_MAX_PAGES_PER_RUN` (default `20`; used when CLI `--max-pages` is omitted)
- `EBAY_REQUESTS_PER_MINUTE` (required when `ENABLE_EBAY_API=true`, provider-safe cap)
- `PHASE1_SKIP_EXISTING_LISTINGS` (default `true`; skip listings already stored by `external_listing_id`)
- `PHASE1_COMMIT_BATCH_SIZE` (default `50`; commit listing writes every N upserts during Phase 1)
- `PHASE1_IMAGE_DOWNLOAD_CHUNK_SIZE` (default `100`; download and commit images in chunks)

## Scryfall

- `SCRYFALL_BULK_URI` (required)
- `SCRYFALL_BULK_CACHE_PATH` (default `./data/scryfall/default-cards.json`)
- `SCRYFALL_SYNC_INTERVAL_HOURS` (default `24`)
- `SCRYFALL_REQUESTS_PER_MINUTE` (default `30`)

## Cardmarket

- `CARDMARKET_BULK_FILE_PATH` (required; local path to normalized bulk CSV — generate with `download-cardmarket-bulk`)
- `CARDMARKET_BULK_REFRESH_HOURS` (default `24`)

## Image/OCR/Matching

Recognition library settings (`CARD_ZONE_*`, `VERIFY_*`, FAISS, OpenCLIP, lot-crop thresholds, etc.) are documented in **[mtg-card-recognition `docs/config.md`](../mtg-card-recognition/docs/config.md)** with canonical env names. EbayWorkflows maps them via `adapters/recognition_settings.py` from the same `.env` keys listed in `.env.example`.

EbayWorkflows-specific (pipeline workers, pricing guardrails, phase skips):

- `PIPELINE_MAX_IMAGE_WORKERS` (default `4`; parallel workers for Phase 5/6 image analysis)
- `PIPELINE_MAX_DOWNLOAD_WORKERS` (default `8`; parallel workers for Phase 1 image downloads)
- `PIPELINE_MAX_TITLE_MATCH_WORKERS` (default `12`; parallel workers for Phase 2 title matching)
- `PHASE5_SKIP_ANALYZED_IMAGES` (default `false`; set `true` to skip images that already have `card_region` detections)
- `PHASE6_SKIP_ANALYZED_IMAGES` (default `false`; set `true` to skip images that already have `lot_card` detections)
- `TITLE_MATCH_MIN_SCORE_FOR_PRICING` (default `0.90`; minimum fuzzy match score to attach Cardmarket prices)
- `TITLE_MATCH_MIN_SCORE_NON_MTG` (default `0.98`; stricter threshold when listing title looks non-MTG)
- `CARDMARKET_MAX_UNIT_PRICE_EUR` (default `250`; reject or cap outlier unit prices unless match is very strong)
- `EV_MAX_LISTING_COST_MULTIPLE` (default `10`; cap rank EV relative to listing cost)
- `PHASE6_BULK_LISTINGS_ONLY` (default `true`; run real lot detection only on bulk-style titles)
- `PHASE6_MIN_LOT_DETECTIONS` (default `2`; minimum distinct lot card detections before scoring)
- `PHASE6_MAX_LOT_EV_MULTIPLE` (default `50`; cap lot EV relative to listing cost)
- `PHASE2_SKIP_BULK_LOT_TITLE_MATCH` (default `true`; skip Phase 2 title match for bulk-style listing titles)
- `PHASE6_USE_FAISS_CROP_MATCH` (default `true`; FAISS in Phase 6 lot crop resolution)

Recognition env vars also present in `.env.example` (shared with mtg-card-recognition): `IMAGE_CACHE_DIR`, `OCR_ENGINE` (default `pytesseract`), `FAISS_*`, `OPENCLIP_*`, `TORCH_DEVICE`, `CARD_ZONE_*`, `VERIFY_*`, `IMAGE_EVIDENCE_MIN_*`, `TITLE_MATCH_PREFILTER_SIZE`, `TITLE_MATCH_SCORE_CUTOFF`, and lot-crop floor via `LOT_CROP_MIN_COMBINED_CONFIDENCE` or legacy alias `PHASE6_MIN_CROP_MATCH_CONFIDENCE`.

## Compliance and Safety

- `GLOBAL_REQUESTS_PER_MINUTE_CAP` (required)
- `ENABLE_PROVIDER_POLICY_CHECKS` (default `true`)
- `DISABLE_LIVE_API_WRITES` (default `true`)

## Validation Rules

- fail fast on missing required values
- reject non-positive rate-limit values
- enforce `GLOBAL_REQUESTS_PER_MINUTE_CAP <= sum(active provider budgets)` where eBay budget is counted only when `ENABLE_EBAY_API=true`
- reject startup when credentials are present but policy checks are disabled in non-local environments

