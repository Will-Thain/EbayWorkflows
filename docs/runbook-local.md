# Local Runbook

## Prerequisites

- PostgreSQL running locally
- Python runtime and virtual environment (or chosen runtime equivalent)
- eBay API credentials configured in environment variables
- downloaded Cardmarket bulk pricing file available locally

## Setup Steps

1. install Tesseract OCR (Windows): `winget install -e --id UB-Mannheim.TesseractOCR`
   - restart the terminal so `tesseract` is on PATH, or set `TESSERACT_CMD` in `.env`
1b. create and activate virtual environment
2. install dependencies (`pip install -e .` or `pip install -r requirements.txt`)
3. set required environment variables from `.env.example`
4. run DB migrations
5. run `ebay-workflows validate-env`
   - if warnings mention shell overrides, run `./scripts/clear-ebay-env-overrides.ps1` (stale `EBAY_*` env vars beat `.env`)
6. verify eBay OAuth (production keys by default):
   `ebay-workflows ebay-auth-check`
   - use sandbox keys with `EBAY_USE_SANDBOX=true` in `.env`
   - production: **App ID** → `EBAY_CLIENT_ID`, **Client Secret** → `EBAY_CLIENT_SECRET`
   - sandbox: **App ID** → `EBAY_SANDBOX_CLIENT_ID`, **Client Secret** → `EBAY_SANDBOX_CLIENT_SECRET`
   - set `EBAY_USE_SANDBOX=true` to use sandbox credentials (not Cert ID)
7. run a dry-run workflow command to validate integration configuration
7. initialize schema with `ebay-workflows init-db`
8. set `DISABLE_LIVE_API_WRITES=false` in `.env` for local persistence tests
9. run Phase 1 locally with mock data:
   `ebay-workflows run --query "mtg lot" --no-dry-run --mock-input-file "samples/mock_listings.json"`
10. sync Scryfall bulk cards into DB:
   `ebay-workflows sync-scryfall`
10b. build OpenCLIP+FAISS art index (subset, rate-limited downloads):
   `ebay-workflows build-faiss-index --max-cards 500`
11. run title-based matching:
   `ebay-workflows phase2-match-title --top-k 3`
12. download full Cardmarket MTG singles price guide (official daily export):
   `ebay-workflows download-cardmarket-bulk -o ./data/cardmarket/prices.csv`
   - raw JSON cached under `./data/cardmarket/`
   - set `CARDMARKET_BULK_FILE_PATH=./data/cardmarket/prices.csv`
13. sync Cardmarket pricing:
   `ebay-workflows sync-cardmarket`
14. run Phase 3 price join:
   `ebay-workflows phase3-join-prices`
15. run EV/confidence ranking (hybrid title+OCR+embedding+price by default):
   `ebay-workflows phase4-rank --hybrid`
15b. export ranked results (table + optional JSON):
   `ebay-workflows export-rankings --limit 25 -o ./data/exports/ranked.json`
16. run OCR verification (mock evidence):
   `ebay-workflows phase5-verify-ocr --mock-ocr-file "samples/mock_ocr_results.json"`
    or run real OCR from cached local images (OpenCV region detect + per-crop OCR):
   `ebay-workflows phase5-verify-ocr --use-real-ocr --use-embedding-match`
   - requires `listing_images.local_path` populated (Phase 1 with `--download-images`)
   - crops saved under `IMAGE_CACHE_DIR/crops`
17. image-heavy phases use parallel workers (`PIPELINE_MAX_IMAGE_WORKERS`) and skip images without visible card regions (`IMAGE_MIN_REGION_SCORE`, `IMAGE_ALLOW_FULL_FRAME_FALLBACK=false`).
17b. Phase 1 skips listings already in DB when `PHASE1_SKIP_EXISTING_LISTINGS=true` (default).
17c. live production pipeline (after production OAuth works):
   `./scripts/run-live-pipeline.ps1 -MaxPages 1`
   - requires Tesseract on PATH for meaningful OCR text; without it, OpenCV regions still run but OCR fields may be empty
17b. run bulk-lot multi-card detection (mock):
   `ebay-workflows phase6-detect-lots --mock-lot-file "samples/mock_lot_detections.json"`
    or real OpenCV multi-card detection + OCR on cached images:
   `ebay-workflows phase6-detect-lots --use-real-detection`
18. run post-MVP integrity checks:
   `ebay-workflows data-integrity-check`
19. run local quality gates before push:
   `ruff check .`
   `python -m compileall src`
   `pytest -q`
20. run resumable full pipeline (skips completed phases by default):
   `ebay-workflows run-resumable-pipeline --query "mtg lot" --mock-input-file "samples/mock_listings.json" --mock-ocr-file "samples/mock_ocr_results.json" --mock-lot-file "samples/mock_lot_detections.json"`
21. desktop GUI — **PySide6** (Opportunities + favourites; requires phase 4 scores):
   `pip install -e ".[gui]"`  (installs `pyside6` and console scripts)
   `ebay-workflows init-db`  (creates `listing_favorites` / `scheduled_jobs` if missing)
   `ebay-workflows-gui`
   - same app without the script: `python -m ebay_workflows.gui.qt_app`
   - entrypoint: `ebay_workflows.gui.qt_app` (Qt 6 / PySide6)
   - if `pip install -e ".[gui]"` fails with **WinError 32** on `ebay-workflows.exe`, stop other runs first:
     `Get-Process ebay-workflows -ErrorAction SilentlyContinue | Stop-Process -Force`
     then re-run `pip install -e ".[gui]"`, or use `python -m ebay_workflows.gui.qt_app` (scripts are optional)
22. headless schedules (GUI closed): see `gui-windows-scheduler.md` or `.\scripts\register-run-due-schedules-task.ps1`
23. optional standalone GUI `.exe`: `.\scripts\build-gui-exe.ps1` (requires `pip install pyinstaller`)

## First Execution

- use a narrow query and low page cap for initial validation
- verify that run/step records are persisted
- inspect listing/image ingestion counts before enabling larger runs

## API and Permission Safety Checklist

- confirm configured requests-per-minute values are below provider limits
- confirm only approved scopes are present for live API credentials (for example eBay)
- confirm `DISABLE_LIVE_API_WRITES=true` for ingestion-only workflow
- confirm policy checks are enabled before running live API calls

## Troubleshooting

- auth failure: validate credentials and scope grants
- repeated throttling: lower per-provider request budget and page size
- data mismatch: inspect raw payload snapshots and schema validation errors
- OCR/matching drift: compare against labeled regression dataset

