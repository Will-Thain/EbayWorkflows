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

- `IMAGE_CACHE_DIR` (required)
- `IMAGE_DOWNLOAD_TIMEOUT_MS` (default `20000`)
- `OCR_ENGINE` (default `paddleocr`)
- `FAISS_INDEX_PATH` (required when vector search enabled)
- `FAISS_TOP_K` (default `5`)
- `FAISS_BUILD_MAX_CARDS` (default `10000`; subset of Scryfall art indexed by `build-faiss-index`)
- `OPENCLIP_MODEL_NAME` (default `ViT-B-32`)
- `TORCH_DEVICE` (default `cpu`; `cuda` for NVIDIA, `directml` for AMD on Windows with `torch-directml`)
- `EMBEDDING_BATCH_SIZE` (default `32`; batch size for OpenCLIP image embedding)
- `IMAGE_MIN_REGION_SCORE` (default `0.55`; minimum OpenCV region score before OCR/embedding)
- `IMAGE_ALLOW_FULL_FRAME_FALLBACK` (default `false`; when false, skip images with no card-like crop)
- `PIPELINE_MAX_IMAGE_WORKERS` (default `4`; parallel workers for Phase 5/6 image analysis)
- `PIPELINE_MAX_DOWNLOAD_WORKERS` (default `8`; parallel workers for Phase 1 image downloads)
- `PIPELINE_MAX_TITLE_MATCH_WORKERS` (default `12`; parallel workers for Phase 2 title matching)
- `TITLE_MATCH_PREFILTER_SIZE` (default `512`; max Scryfall names scored per listing after token pre-filter)
- `PHASE2_SKIP_UNCHANGED_LISTINGS` (default `true`; skip title match when stored evidence title equals current listing title)
- `TESSERACT_CMD` (optional; path to `tesseract.exe` on Windows)
- `TITLE_MATCH_MIN_SCORE_FOR_PRICING` (default `0.88`; minimum fuzzy match score to attach Cardmarket prices)
- `TITLE_MATCH_MIN_SCORE_NON_MTG` (default `0.98`; stricter threshold when listing title looks non-MTG)
- `CARDMARKET_MAX_UNIT_PRICE_EUR` (default `250`; reject or cap outlier unit prices unless match is very strong)
- `EV_MAX_LISTING_COST_MULTIPLE` (default `10`; cap rank EV relative to listing cost)
- `PHASE6_BULK_LISTINGS_ONLY` (default `true`; run real lot detection only on bulk-style titles)
- `PHASE6_MIN_LOT_DETECTIONS` (default `2`; minimum distinct lot card detections before scoring)
- `PHASE6_MAX_LOT_EV_MULTIPLE` (default `50`; cap lot EV relative to listing cost)

## Compliance and Safety

- `GLOBAL_REQUESTS_PER_MINUTE_CAP` (required)
- `ENABLE_PROVIDER_POLICY_CHECKS` (default `true`)
- `DISABLE_LIVE_API_WRITES` (default `true`)

## Validation Rules

- fail fast on missing required values
- reject non-positive rate-limit values
- enforce `GLOBAL_REQUESTS_PER_MINUTE_CAP <= sum(active provider budgets)` where eBay budget is counted only when `ENABLE_EBAY_API=true`
- reject startup when credentials are present but policy checks are disabled in non-local environments

