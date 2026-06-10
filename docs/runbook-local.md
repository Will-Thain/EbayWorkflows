# Local Runbook

**Status:** Commands and phase order **[Shipped]**. Tags: `documentation-status.md`.

## Prerequisites

- PostgreSQL running locally
- Python runtime and virtual environment (or chosen runtime equivalent)
- eBay API credentials configured in environment variables
- downloaded Cardmarket bulk pricing file available locally

## Setup Steps

1. install Tesseract OCR (Windows): `winget install -e --id UB-Mannheim.TesseractOCR`
   - restart the terminal so `tesseract` is on PATH, or set `TESSERACT_CMD` in `.env`
1b. create and activate virtual environment (`python -m venv .venv`)
2. clone sibling recognition repo (once): `git clone https://github.com/Will-Thain/mtg-card-recognition.git ../mtg-card-recognition`
3. install dependencies: `.\scripts\install-dev.ps1` (editable `mtg-card-recognition` + `ebay-workflows[dev]`)
4. set required environment variables from `.env.example`
5. run DB migrations
6. run `ebay-workflows validate-env`
   - includes **Match Statistics** (verified listings, pricing-eligible count) when DB is up
   - if warnings mention shell overrides, run `./scripts/clear-ebay-env-overrides.ps1` (stale `EBAY_*` env vars beat `.env`)
6. verify eBay OAuth (production keys by default):
   `ebay-workflows ebay-auth-check`
   - use sandbox keys with `EBAY_USE_SANDBOX=true` in `.env`
   - production: **App ID** → `EBAY_CLIENT_ID`, **Client Secret** → `EBAY_CLIENT_SECRET`
   - sandbox: **App ID** → `EBAY_SANDBOX_CLIENT_ID`, **Client Secret** → `EBAY_SANDBOX_CLIENT_SECRET`
   - set `EBAY_USE_SANDBOX=true` to use sandbox credentials (not Cert ID)
7. run a dry-run workflow command to validate integration configuration
7. initialize schema with `ebay-workflows init-db`
7b. on an existing DB created before Alembic was added, stamp the baseline (does not run DDL):
   `alembic stamp head`
   - future schema changes should add revisions under `alembic/versions/` instead of relying on `create_all` alone
8. set `DISABLE_LIVE_API_WRITES=false` in `.env` for local persistence tests
9. run Phase 1 locally with mock data:
   `ebay-workflows run --query "mtg lot" --no-dry-run --mock-input-file "samples/mock_listings.json"`
10. sync Scryfall bulk cards into DB:
   `ebay-workflows sync-scryfall`
10b. build OpenCLIP+FAISS art index (subset; default 10k cards from `FAISS_BUILD_MAX_CARDS`):
   `ebay-workflows build-faiss-index`
   - progress lines emit during embedding batches
   - `validate-env` reports FAISS_INDEX_READY
10c. ensure performance indexes on existing DB:
   `ebay-workflows ensure-db-indexes`
11. run title-based matching:
   `ebay-workflows phase2-match-title --top-k 3`
12. download full Cardmarket MTG singles price guide (official daily export):
   `ebay-workflows download-cardmarket-bulk -o ./data/cardmarket/prices.csv`
   - raw JSON cached under `./data/cardmarket/`
   - set `CARDMARKET_BULK_FILE_PATH=./data/cardmarket/prices.csv`
13. sync Cardmarket pricing:
   `ebay-workflows sync-cardmarket`
14. run OCR/image verification **before** price join (sets `image_verified` / `pricing_eligible` via strict consensus gate):
   `ebay-workflows phase5-verify-ocr --mock-ocr-file "samples/mock_ocr_results.json"`
    or run real OCR from cached local images (OpenCV region detect + per-crop zone OCR + embedding):
   `ebay-workflows phase5-verify-ocr --use-real-ocr --use-embedding-match`
   - requires `listing_images.local_path` populated (Phase 1 with `--download-images`)
   - crops saved under `IMAGE_CACHE_DIR/crops`; zone strips under `crops/zones`
   - verification provenance stored in `evidence_json` (`verification_*` fields); see `data-dictionary.md`
   - tune gate defaults via `VERIFY_NAME_HARD_MIN`, `VERIFY_NAME_STRONG_MIN`, `VERIFY_SYMBOL_STRONG_MIN` in `.env`
   - optional: `FAISS_PROPOSE_CANDIDATES=true` (default) for FAISS top-1 proposal when absent from Phase 2
   - optional: `ebay-workflows build-set-symbol-templates` (one-time; auto-run by pipeline scripts)
15. run Phase 3 price join (after Phase 5 so newly verified candidates receive prices):
   `ebay-workflows phase3-join-prices`
16. run EV/confidence ranking (hybrid title+OCR+embedding+price by default):
   `ebay-workflows phase4-rank --hybrid`
16b. export ranked results (table + optional JSON):
   `ebay-workflows export-rankings --limit 25 -o ./data/exports/ranked.json`
   - JSON includes `image_verification_source`, `verification_detection_id`, `verification_listing_image_id` when verified
17. image-heavy phases use parallel workers (`PIPELINE_MAX_IMAGE_WORKERS`) and skip images without visible card regions (`IMAGE_MIN_REGION_SCORE`, `IMAGE_ALLOW_FULL_FRAME_FALLBACK=false`).
17b. Phase 1 skips listings already in DB when `PHASE1_SKIP_EXISTING_LISTINGS=true` (default).
17c. live production pipeline (after production OAuth works):
   `./scripts/run-live-pipeline.ps1`
   - omit `-MaxPages` to use `EBAY_MAX_PAGES_PER_RUN` from `.env` (default 20)
   - pass `-MaxPages 5` for a smaller daily incremental run
17d. **large-scale ingest** (full prep + up to 1,000 listings/run):
   `./scripts/run-large-ingest.ps1 -Query "magic the gathering mtg"`
   - see `docs/large-scale-ingest.md` for capacity limits, hardware tuning, and flags
   - requires Tesseract on PATH for meaningful OCR text; without it, OpenCV regions still run but OCR fields may be empty
17e. **reanalyze matching only** (clear OCR/detections, re-run 2→5→3→6→4 on cached images):
   `./scripts/reanalyze-matching.ps1`
   - pass `-SkipPhase6` if Phase 6 hangs on DirectML / GPU model load
   - **finish ranking only** (reuse Phase 5/3, skip Phase 6): `./scripts/finish-ranking.ps1`
   - post-run validation: `./scripts/post-reanalyze-validation.ps1`
   - backlog tracker: `docs/open-items-status.md`
17f. **debug phase4 hang** (operator only, not CI):
   `python scripts/finish_ranking_debug.py`
   - writes step trace to `data/exports/finish-debug.log`
   - use when `finish-ranking.ps1` or phase4 appears stuck on model/settings import
17g. **after reanalyze / phase5 re-run completes** — validation, config cleanup, docs:
   see `docs/post-workflow-checklist.md`
17b. run bulk-lot multi-card detection (mock):
   `ebay-workflows phase6-detect-lots --mock-lot-file "samples/mock_lot_detections.json"`
    or real OpenCV multi-card detection + OCR on cached images:
   `ebay-workflows phase6-detect-lots --use-real-lot-detection`
18. run post-MVP integrity checks:
   `ebay-workflows data-integrity-check`
18b. prune orphan listing image files from cache root (dry-run default):
   `ebay-workflows prune-image-cache`
   - execute deletions: `ebay-workflows prune-image-cache --execute`
19. run local quality gates before push:
   `ruff check .`
   `py -m compileall src`
   `py -m pytest -q`
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
- OCR/matching drift: compare against labeled regression dataset; re-run `./scripts/reanalyze-matching.ps1` after gate changes
- zero verified after Phase 5: check Tesseract on PATH, FAISS index coverage (`validate-env`), and `VERIFY_*` thresholds — see `future-pain-points.md` §6

