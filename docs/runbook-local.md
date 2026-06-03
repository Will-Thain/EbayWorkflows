# Local Runbook

## Prerequisites

- PostgreSQL running locally
- Python runtime and virtual environment (or chosen runtime equivalent)
- eBay API credentials configured in environment variables
- downloaded Cardmarket bulk pricing file available locally

## Setup Steps

1. create and activate virtual environment
2. install dependencies (`pip install -e .` or `pip install -r requirements.txt`)
3. set required environment variables from `.env.example`
4. run DB migrations
5. run `ebay-workflows validate-env`
6. verify eBay OAuth (production keys by default):
   `ebay-workflows ebay-auth-check`
   - use sandbox keys with `EBAY_USE_SANDBOX=true` in `.env`
   - map **App ID (Client ID)** → `EBAY_CLIENT_ID` and **Client Secret** → `EBAY_CLIENT_SECRET` (not Cert ID)
7. run a dry-run workflow command to validate integration configuration
7. initialize schema with `ebay-workflows init-db`
8. set `DISABLE_LIVE_API_WRITES=false` in `.env` for local persistence tests
9. run Phase 1 locally with mock data:
   `ebay-workflows run --query "mtg lot" --no-dry-run --mock-input-file "samples/mock_listings.json"`
10. sync Scryfall bulk cards into DB:
   `ebay-workflows sync-scryfall`
11. run title-based matching:
   `ebay-workflows phase2-match-title --top-k 3`
12. set `CARDMARKET_BULK_FILE_PATH=./samples/cardmarket_prices.csv` for local test data
13. sync Cardmarket pricing:
   `ebay-workflows sync-cardmarket`
14. run Phase 3 price join:
   `ebay-workflows phase3-join-prices`
15. run EV/confidence ranking:
   `ebay-workflows phase4-rank`
16. run OCR verification (mock evidence):
   `ebay-workflows phase5-verify-ocr --mock-ocr-file "samples/mock_ocr_results.json"`
    or run real OCR from cached local images (OpenCV region detect + per-crop OCR):
   `ebay-workflows phase5-verify-ocr --use-real-ocr`
   - requires `listing_images.local_path` populated (Phase 1 with `--download-images`)
   - crops saved under `IMAGE_CACHE_DIR/crops`
17. run bulk-lot multi-card detection:
   `ebay-workflows phase6-detect-lots --mock-lot-file "samples/mock_lot_detections.json"`
18. run post-MVP integrity checks:
   `ebay-workflows data-integrity-check`
19. run local quality gates before push:
   `ruff check .`
   `python -m compileall src`
   `pytest -q`
20. run resumable full pipeline (skips completed phases by default):
   `ebay-workflows run-resumable-pipeline --query "mtg lot" --mock-input-file "samples/mock_listings.json" --mock-ocr-file "samples/mock_ocr_results.json" --mock-lot-file "samples/mock_lot_detections.json"`

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

