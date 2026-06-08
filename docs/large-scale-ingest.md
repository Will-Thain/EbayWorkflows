# Large-Scale eBay Ingest

This guide covers running **high-volume** eBay listing ingestion and the full scoring pipeline on a workstation (7950X / 64 GB RAM / RX 7900 XTX class hardware).

## Quick start

1. Copy `.env.example` → `.env` and set production eBay credentials.
2. Set `DISABLE_LIVE_API_WRITES=false` and `ENABLE_EBAY_API=true`.
3. Activate dev environment: `. .\scripts\activate-dev.ps1`
4. Run the all-in-one script:

```powershell
.\scripts\run-large-ingest.ps1 -Query "magic the gathering mtg" -MaxPages 20
```

Omit `-MaxPages` to use `EBAY_MAX_PAGES_PER_RUN` from `.env` (default **20** → up to **1,000 listings** per run at page size 50).

## Capacity limits

| Limit | Value | Notes |
|-------|-------|-------|
| Items per API page | `EBAY_PAGE_SIZE` (50) | eBay Browse default |
| Pages per run | `EBAY_MAX_PAGES_PER_RUN` (20) | Overridable via `--max-pages` |
| Max results per query | **~10,000** | eBay Browse offset ceiling; use narrower queries or multiple query runs |
| Theoretical max/run | `pages × page_size` | Capped automatically at offset 10,000 |

For corpora beyond ~10k listings per keyword, rotate queries (set names, card names, “bulk lot”, etc.) and rely on `PHASE1_SKIP_EXISTING_LISTINGS=true` to deduplicate across runs.

## Recommended `.env` for large ingest

```env
DISABLE_LIVE_API_WRITES=false
ENABLE_EBAY_API=true
EBAY_PAGE_SIZE=50
EBAY_MAX_PAGES_PER_RUN=20
EBAY_REQUESTS_PER_MINUTE=60
GLOBAL_REQUESTS_PER_MINUTE_CAP=90

PHASE1_SKIP_EXISTING_LISTINGS=true
PHASE1_COMMIT_BATCH_SIZE=50
PHASE1_IMAGE_DOWNLOAD_CHUNK_SIZE=100
PIPELINE_MAX_DOWNLOAD_WORKERS=16
PIPELINE_MAX_TITLE_MATCH_WORKERS=16
PIPELINE_MAX_IMAGE_WORKERS=12

DB_POOL_MAX=20
FAISS_BUILD_MAX_CARDS=10000
TORCH_DEVICE=directml
EMBEDDING_BATCH_SIZE=32
```

To **refresh prices/titles** on listings already in the database, set `PHASE1_SKIP_EXISTING_LISTINGS=false` or pass `-RefreshExisting` to `run-large-ingest.ps1`.

## One-time preparation

Run once (or when caches are stale):

```powershell
ebay-workflows init-db
ebay-workflows ensure-db-indexes
ebay-workflows sync-scryfall
ebay-workflows download-cardmarket-bulk -o ./data/cardmarket/prices.csv
ebay-workflows sync-cardmarket
ebay-workflows build-faiss-index    # 10k cards; ~15–45 min on DirectML
```

`validate-env` reports FAISS readiness, page caps, and worker counts.

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/run-large-ingest.ps1` | Full prep + Phase 1–6 + export; use for bulk ingest |
| `scripts/run-live-pipeline.ps1` | Lighter daily run (assumes Scryfall/Cardmarket already synced) |
| `scripts/reanalyze-matching.ps1` | Clear match artifacts + full Phase 2–6 re-run after logic changes |
| `scripts/rerun-image-matching.ps1` | Re-run Phase 5/6/4 on cached images (no eBay re-ingest) |
| `scripts/activate-dev.ps1` | Puts venv, Tesseract, psql on PATH |

### `run-large-ingest.ps1` flags

| Flag | Effect |
|------|--------|
| `-Query` | eBay search string (default: `magic the gathering mtg`) |
| `-MaxPages N` | Override `EBAY_MAX_PAGES_PER_RUN`; `0` = use `.env` |
| `-SkipPrep` | Skip Scryfall/FAISS/Cardmarket prep |
| `-SkipPhase1` | Skip eBay fetch (re-score existing listings) |
| `-RefreshExisting` | Set `PHASE1_SKIP_EXISTING_LISTINGS=false` for this run |
| `-RebuildFaiss` | Force FAISS rebuild even if index exists |

## Pipeline order (large ingest)

```
validate-env → init-db → ensure-db-indexes
→ sync-scryfall → [build-faiss-index] → sync-cardmarket
→ Phase 1 (ingest + parallel image download)
→ retry-failed-images
→ Phase 2 (title match) → Phase 5 (OCR + embedding + zone evidence)
→ Phase 3 (price join — after image verification)
→ Phase 6 (lot detection + crop pricing)
→ Phase 4 (hybrid rank — last, preserves v2_lot scores)
→ export-rankings → data-integrity-check
```

Phase 4 runs **after** Phase 6 so bulk-lot scores (`v2_lot`) are not overwritten by hybrid singles scoring.

## Operational checklist

- [ ] `ebay-workflows validate-env` — FAISS_INDEX_READY=yes, policy caps OK
- [ ] `ebay-workflows ebay-auth-check` — OAuth succeeds
- [ ] PostgreSQL has free disk (images + JSON payloads grow quickly)
- [ ] `.cache/images` on fast SSD; expect ~1–5 MB per listing with images
- [ ] Rate limits: start at 60 req/min eBay; lower if you see 429 responses
- [ ] After Phase 1: `ebay-workflows retry-failed-images` for transient CDN failures
- [ ] Monitor progress via CLI `ebay-workflows-progress` lines or GUI Workflows tab

## Incremental daily runs

For scheduled ingestion without re-downloading everything:

```powershell
.\scripts\run-live-pipeline.ps1 -MaxPages 5
```

Existing listings are skipped when `PHASE1_SKIP_EXISTING_LISTINGS=true`. Phase 2 skips unchanged titles when `PHASE2_SKIP_UNCHANGED_LISTINGS=true`.

## Troubleshooting

| Symptom | Action |
|---------|--------|
| 429 / throttling | Lower `EBAY_REQUESTS_PER_MINUTE`; reduce `PIPELINE_MAX_DOWNLOAD_WORKERS` |
| Partial Phase 1 after crash | Re-run Phase 1; batch commits preserve completed listings |
| Failed image downloads | `ebay-workflows retry-failed-images` |
| Rankings all 0.00 EV | Run Phase 5 before Phase 3; bulk lots need Phase 6 crop evidence for pricing |
| Bulk lots never priced | Ensure lot crops have set/collector or FAISS evidence; title-only blocked by design |
| FAISS match weak after subset index | Full build: `FAISS_BUILD_ALL_CARDS=true` + `-RebuildFaiss` or `./scripts/build-faiss-full.ps1` |
| FAISS match weak after full art-zone index | Expected with generic OpenCLIP on eBay photos — see `card-recognition-architecture.md`; evaluate Milo catalog before re-embedding |
| FAISS crop mismatch warning | `validate-env` reports index vs config crop mode — re-embed from cached `scryfall_art/` (no Scryfall re-download) |
| >10k results needed | Split into multiple queries; dedup handles overlap |

## Hardware notes (7950X / RX 7900 XTX)

- **Phase 1**: CPU + network bound; scale `PIPELINE_MAX_DOWNLOAD_WORKERS` (12–16).
- **Phase 2**: CPU bound; `PIPELINE_MAX_TITLE_MATCH_WORKERS=16`, token pre-filter enabled.
- **Phase 5 / FAISS build**: GPU via `TORCH_DEVICE=directml`, `EMBEDDING_BATCH_SIZE=32`.
- **Phase 6**: CPU (OpenCV + Tesseract); `PIPELINE_MAX_IMAGE_WORKERS=12`.

See `docs/config-contract.md` for all environment variables.

For known limits, mitigations, and roadmap items see **`docs/future-pain-points.md`**.
