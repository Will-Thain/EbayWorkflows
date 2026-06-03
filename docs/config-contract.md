# Configuration Contract

## Purpose

Define all required environment variables, defaults, and validation rules before coding starts.

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
- `EBAY_MAX_PAGES_PER_RUN` (default `20`)
- `EBAY_REQUESTS_PER_MINUTE` (required when `ENABLE_EBAY_API=true`, provider-safe cap)

## Scryfall

- `SCRYFALL_BULK_URI` (required)
- `SCRYFALL_SYNC_INTERVAL_HOURS` (default `24`)
- `SCRYFALL_REQUESTS_PER_MINUTE` (default `30`)

## Cardmarket

- `CARDMARKET_BULK_FILE_PATH` (required; local path to normalized bulk CSV — generate with `download-cardmarket-bulk`)
- `CARDMARKET_BULK_REFRESH_HOURS` (default `24`)

## Image/OCR/Matching

- `IMAGE_CACHE_DIR` (required)
- `IMAGE_DOWNLOAD_TIMEOUT_MS` (default `20000`)
- `OCR_ENGINE` (default `paddleocr`)
- `FAISS_INDEX_PATH` (required when vector search enabled)
- `OPENCLIP_MODEL_NAME` (default `ViT-B-32`)

## Compliance and Safety

- `GLOBAL_REQUESTS_PER_MINUTE_CAP` (required)
- `ENABLE_PROVIDER_POLICY_CHECKS` (default `true`)
- `DISABLE_LIVE_API_WRITES` (default `true`)

## Validation Rules

- fail fast on missing required values
- reject non-positive rate-limit values
- enforce `GLOBAL_REQUESTS_PER_MINUTE_CAP <= sum(active provider budgets)` where eBay budget is counted only when `ENABLE_EBAY_API=true`
- reject startup when credentials are present but policy checks are disabled in non-local environments

