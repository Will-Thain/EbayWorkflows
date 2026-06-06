# Future Pain Points — Issues, Fixes, and Status

This document tracks known scalability and accuracy limits, the **recommended fix** for each, and what is **already implemented** in this repository.

Use with `ebay-workflows validate-env` for live operational warnings.

---

## 1. eBay ingest limits

### 1.1 ~10,000 results per query (offset ceiling)

**Symptoms:** No matter how high `EBAY_MAX_PAGES_PER_RUN` is, a single keyword stops returning new listings around 10,000 results.

**Best fix:** Rotate multiple search queries; deduplicate by `external_listing_id` across runs.

**Implemented:**
- `iter_listing_pages()` stops at offset 10,000 and when API `total` is reached.
- `--queries-file` on `ebay-workflows run` (one query per line).
- Example queries: `scripts/queries/mtg-default.txt`.
- Documented in `docs/large-scale-ingest.md`.

**Operator action:**
```powershell
ebay-workflows run --query "mtg lot" --no-dry-run --download-images `
  --queries-file scripts/queries/mtg-default.txt
```

---

### 1.2 Incremental runs skip price updates

**Symptoms:** Re-running ingest does not refresh prices on listings already in the DB.

**Best fix:** Time-based refresh of stale listings while keeping skip-by-default for dedup.

**Implemented:**
- `PHASE1_REFRESH_AFTER_HOURS` — when set (e.g. `24`), listings not seen within that window are upserted even if `PHASE1_SKIP_EXISTING_LISTINGS=true`.
- `-RefreshExisting` on `run-large-ingest.ps1` sets `PHASE1_SKIP_EXISTING_LISTINGS=false` for one run.

**Recommended `.env`:**
```env
PHASE1_SKIP_EXISTING_LISTINGS=true
PHASE1_REFRESH_AFTER_HOURS=24
```

---

### 1.3 Coarse pipeline resume skips Phase 1

**Symptoms:** `run-resumable-pipeline --resume` skips Phase 1 whenever *any* listings exist, even after a partial failed ingest.

**Best fix:** Resume Phase 1 only when the last successful Phase 1 run met a minimum `records_seen` threshold for the requested page count.

**Implemented:**
- `_phase_completion_snapshot()` checks last successful `phase1_ingest` step metrics vs `max_pages × page_size`.
- Use `--no-resume` to force Phase 1 regardless.

---

### 1.4 Memory use on large fetches

**Symptoms:** Fetching thousands of listings held entire result sets in RAM before DB writes.

**Best fix:** Stream API pages into the DB incrementally.

**Implemented:**
- `iter_listing_pages()` yields one page at a time.
- Phase 1 processes records as a streaming iterator with batch commits (`PHASE1_COMMIT_BATCH_SIZE`).

---

## 2. EV and ranking accuracy

### 2.1 GBP listings vs EUR Cardmarket (no FX)

**Symptoms:** EV compared listing cost in GBP directly against Cardmarket gross value in EUR — rankings skewed by ~15–20%.

**Best fix:** Convert listing cost to `BASE_CURRENCY` before EV math; configurable static rates (live FX API optional later).

**Implemented:**
- `services/currency.py` — `listing_total_cost_base()` used in hybrid scoring, Phase 4, and Phase 6.
- `FX_GBP_TO_EUR` in `.env` (default `1.17` when `BASE_CURRENCY=EUR`).

**Future:** ECB/OpenExchangeRates daily rate job; condition-aware Cardmarket price columns.

---

### 2.2 Title-match guardrails block singles pricing

**Symptoms:** Strong matches at ~0.85 get no Cardmarket price → `ev_adjusted=0`, `confidence=0`.

**Best fix:** Tune threshold per listing type; or use OCR/embedding confidence to lower effective threshold for priced singles.

**Implemented (partial):**
- Documented; default remains `TITLE_MATCH_MIN_SCORE_FOR_PRICING=0.88` for safety.
- Hybrid scoring blends OCR + embedding when Phase 5 has run.

**Operator tuning:** Lower to `0.85` in `.env` if false rejects are acceptable.

**Future:** Per-signal dynamic threshold in `ev_guardrails.py`.

---

### 2.3 Bulk lot OCR matches wrong card repeatedly

**Symptoms:** Many lots score against the same incorrect card (e.g. token match on bulk photos).

**Best fix:** Require minimum OCR confidence × match score product; cap lot item contribution; use embedding agreement per crop.

**Implemented (partial):**
- Phase 6 uses `title_match_allowed_for_pricing` and `sanitize_unit_price` per crop.
- `PHASE6_MIN_LOT_DETECTIONS` gates scoring.

**Future:** Per-crop FAISS verification; reject lot items below combined confidence floor.

---

### 2.4 Dual scoring models (v2_hybrid vs v2_lot)

**Symptoms:** Running Phase 4 after Phase 6 overwrote lot scores; unpriced listings sorted above negative lot EV when `rank_value=0`.

**Best fix:** Run hybrid rank **after** lot detection; Phase 4 skips `v2_lot` listings; unpriced listings rank by `ev_raw`.

**Implemented:**
- Pipeline order in `run-live-pipeline.ps1` and `run-large-ingest.ps1`: Phase 5 → 6 → 4.
- Phase 4 skips existing `v2_lot` scores.
- Hybrid scoring sets `rank_value = ev_raw` when no Cardmarket matches.

---

## 3. Compute time at scale

### 3.1 Phase 5 / Phase 6 runtime

**Symptoms:** OCR + OpenCV on every image dominates wall time for 500+ listings.

**Best fix:** Skip unchanged images; parallel workers; optional “bulk lots only” for Phase 6.

**Implemented:**
- `PHASE5_SKIP_ANALYZED_IMAGES=true` (default) — skips images with existing `card_region` detections.
- `PHASE6_SKIP_ANALYZED_IMAGES=true` (default) — skips images with existing `lot_card` detections.
- `PHASE6_BULK_LISTINGS_ONLY=true` — title filter before lot detection.
- `PIPELINE_MAX_IMAGE_WORKERS` (12 recommended on 7950X).

---

### 3.2 FAISS subset coverage

**Symptoms:** Embedding match only works for cards in the built index (~10k of 114k Scryfall cards).

**Best fix:** Build larger index; eventually IVF/PQ index or shard by set.

**Implemented (partial):**
- `FAISS_BUILD_MAX_CARDS=10000`; build progress via `ebay-workflows-progress`.
- `validate-env` warns when vector count < target.

**Future:** `IndexIVFFlat` migration; nightly incremental index append.

---

### 3.3 IndexFlatIP does not scale to full corpus

**Symptoms:** Exact search latency and RAM grow linearly beyond ~50k vectors.

**Best fix:** IVF + PQ compression; or separate index per format (modern vs reserved list).

**Status:** Documented only. Current `IndexFlatIP` is appropriate for ≤10k MVP index.

---

## 4. Data and infrastructure

### 4.1 No schema migrations

**Symptoms:** `init-db` uses `create_all`; existing DBs miss new columns/indexes.

**Best fix:** Alembic migrations (already a dependency) with versioned revision chain.

**Implemented (interim):**
- `ensure-db-indexes` — idempotent performance indexes.
- `init-db` calls `ensure-db-indexes` after `create_all`.

**Future:** `alembic init` + revision per schema change.

---

### 4.2 Disk growth (images + JSON)

**Symptoms:** `.cache/images` and `raw_payload_json` consume GB quickly.

**Best fix:** Retention policy — delete orphaned crops; compress/archive payloads older than N days; monitor disk in validate-env.

**Implemented (partial):**
- Documented in this file.

**Future:** `ebay-workflows prune-cache --older-than-days N` command.

---

### 4.3 Cardmarket bulk staleness

**Symptoms:** EV uses yesterday's (or older) trend prices.

**Best fix:** Scheduled `download-cardmarket-bulk` + `sync-cardmarket`; warn when file age > `CARDMARKET_BULK_REFRESH_HOURS`.

**Implemented:**
- `validate-env` operational health warns on stale/missing bulk file.

---

### 4.4 DirectML / torch stack fragility

**Symptoms:** GPU path breaks on driver or package upgrades; CI does not test `[gpu]` extra.

**Best fix:** Pin versions in optional `[gpu]` extra; CI smoke test on CPU; document fallback `TORCH_DEVICE=cpu`.

**Status:** Documented. `TORCH_DEVICE=cpu` always works; DirectML optional.

---

## 5. Operational gaps

### 5.1 Global rate cap not enforced on CDN downloads

**Symptoms:** Parallel image downloads can spike beyond intended aggregate budget.

**Best fix:** Shared token-bucket limiter across image CDN and FAISS art downloads.

**Implemented:**
- `IMAGE_DOWNLOAD_REQUESTS_PER_MINUTE` (default 120) via `GlobalRateLimiter` in `image_cache.py`.
- eBay API keeps its own `EBAY_REQUESTS_PER_MINUTE` limiter.

**Future:** Unify under `GLOBAL_REQUESTS_PER_MINUTE_CAP` accounting.

---

### 5.2 Failed image downloads silently reduce coverage

**Symptoms:** Listings without local images skip OCR/embedding.

**Best fix:** `retry-failed-images` after Phase 1; surface count in validate-env.

**Implemented:**
- `ebay-workflows retry-failed-images`
- Called automatically in `run-live-pipeline.ps1` and `run-large-ingest.ps1`
- `validate-env` warns when `failed_image_downloads > 0`

---

### 5.3 Concurrent pipeline runs

**Symptoms:** GUI Workflows + CLI + scheduler can overlap, corrupting cache or doubling API usage.

**Best fix:** Exclusive file lock for pipeline runs.

**Implemented:**
- `PIPELINE_ENFORCE_SINGLE_RUN=true` (default) with lock at `.cache/pipeline.lock`.
- Set `PIPELINE_ENFORCE_SINGLE_RUN=false` for deliberate parallel Phase 2+ only runs.

---

### 5.4 OAuth token on very long runs

**Symptoms:** Multi-hour ingests might outlive token TTL (rare at current page caps).

**Best fix:** Refresh token mid-pagination when `expires_in` elapsed.

**Status:** Documented only. Refresh token before each query in multi-query runs is a future improvement.

---

## 6. Search quality ceiling

### 6.1 Title-only matching for singles

**Symptoms:** eBay titles are ambiguous; fuzzy match alone is insufficient.

**Best fix:** Phase 5 OCR + FAISS as primary signals for singles; title match as prior.

**Implemented:** Hybrid weights: title 35%, OCR 25%, embedding 25%, price freshness 15%.

---

### 6.2 Non-MTG noise in broad queries

**Symptoms:** Comics, apparel, proxies appear in MTG searches.

**Best fix:** `is_non_mtg_listing()` stricter pricing gate; optional title blocklist; category filters in eBay query.

**Implemented:** `TITLE_MATCH_MIN_SCORE_NON_MTG=0.98` in guardrails.

**Future:** eBay category ID filter in Browse params.

---

### 6.3 Condition / language mismatch

**Symptoms:** Cardmarket NM trend price applied to eBay LP listing.

**Best fix:** Map eBay condition text to Cardmarket condition column; discount EV by condition delta.

**Status:** Documented only. Cardmarket bulk currently uses trend without condition join.

---

## Quick reference — new environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `FX_GBP_TO_EUR` | `1.17` | Convert eBay GBP costs to EUR base currency |
| `PHASE1_REFRESH_AFTER_HOURS` | disabled | Refresh stale listings without full re-ingest |
| `PHASE5_SKIP_ANALYZED_IMAGES` | `true` | Skip Phase 5 on already-analyzed images |
| `PHASE6_SKIP_ANALYZED_IMAGES` | `true` | Skip Phase 6 on images with lot detections |
| `IMAGE_DOWNLOAD_REQUESTS_PER_MINUTE` | `120` | CDN download rate limit |
| `PIPELINE_ENFORCE_SINGLE_RUN` | `true` | Exclusive pipeline lock |
| `PIPELINE_LOCK_PATH` | `./.cache/pipeline.lock` | Lock file location |

---

## Related docs

- `docs/large-scale-ingest.md` — production ingest runbook
- `docs/config-contract.md` — full env schema
- `docs/integration-specs.md` — eBay/Scryfall/Cardmarket contracts
