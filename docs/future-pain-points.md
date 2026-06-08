# Future Pain Points — Issues, Fixes, and Status

This document tracks known scalability and accuracy limits, the **recommended fix** for each, and what is **already implemented** in this repository.

**Status tags:** **[Shipped]** = current code; **[Historical]** = pre-consensus OR-gate era; **[Future]** = planned or not final. See `documentation-status.md`.

Use with `ebay-workflows validate-env` for live operational warnings.

---

## 1. eBay ingest limits **[Shipped]**

### 1.1 ~10,000 results per query (offset ceiling) **[Shipped]**

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

### 1.2 Incremental runs skip price updates **[Shipped]**

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

### 1.3 Coarse pipeline resume skips Phase 1 **[Shipped]**

**Symptoms:** `run-resumable-pipeline --resume` skips Phase 1 whenever *any* listings exist, even after a partial failed ingest.

**Best fix:** Resume Phase 1 only when the last successful Phase 1 run met a minimum `records_seen` threshold for the requested page count.

**Implemented:**
- `_phase_completion_snapshot()` checks last successful `phase1_ingest` step metrics vs `max_pages × page_size`.
- Use `--no-resume` to force Phase 1 regardless.

---

### 1.4 Memory use on large fetches **[Shipped]**

**Symptoms:** Fetching thousands of listings held entire result sets in RAM before DB writes.

**Best fix:** Stream API pages into the DB incrementally.

**Implemented:**
- `iter_listing_pages()` yields one page at a time.
- Phase 1 processes records as a streaming iterator with batch commits (`PHASE1_COMMIT_BATCH_SIZE`).

---

## 2. EV and ranking accuracy

### 2.1 GBP listings vs EUR Cardmarket (no FX) **[Shipped]**

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

**Implemented [Shipped]:**
- `pricing_allowed_for_candidate()` allows Cardmarket join when `image_verified` with **`set_collector` or `set_symbol` only** (strict gate).
- Title-only path still uses `TITLE_MATCH_MIN_SCORE_FOR_PRICING` when not image-verified.
- Phase 3 runs **after** Phase 5 in all production scripts so newly verified singles receive prices.

**Historical [Historical]:** Pre-consensus gate allowed OCR/embedding/mana as `image_verification_source` for pricing bypass — removed.

**Operator tuning [Future]:** Per-listing-type thresholds; OCR/embedding confidence to lower effective title threshold.

---

### 2.3 Bulk lot listings never received Cardmarket unit prices

**Symptoms:** Phase 6 detected cards in bulk photos but `lot_total_value` stayed 0; ~98% of inventory unaffected by ranking.

**Root cause:** `title_match_allowed_for_pricing()` blocked all bulk listing titles, including per-crop matches with strong image evidence.

**Implemented [Shipped]:**
- `crop_match_allowed_for_pricing()` — bulk lots price individual crops when crop-level evidence passes **strict rules** (primarily `set_collector` or verified set symbol).
- `candidate_has_image_evidence()` / `mtg_card_recognition.evidence` — FAISS and mana **do not alone verify**.
- Phase 5 attach uses `candidates_for_region_evidence` + provenance fields.

**Historical [Historical]:** “FAISS or set symbol alone verifies bulk crop” under OR gate.

---

### 2.4 Bulk lot OCR matches wrong card repeatedly **[Shipped]** (partial)

**Symptoms:** Many lots score against the same incorrect card (e.g. token match on bulk photos).

**Best fix:** Require minimum OCR confidence × match score product; cap lot item contribution; use embedding agreement per crop.

**Implemented (partial):**
- Phase 6 uses `crop_match_allowed_for_pricing`, `resolve_lot_crop_match` (FAISS + set/collector), and `sanitize_unit_price` per crop.
- `PHASE6_MIN_LOT_DETECTIONS` gates scoring.

**Future:** Reject lot items below combined confidence floor when FAISS disagrees with fuzzy title.

---

### 2.5 Dual scoring models (v2_hybrid vs v2_lot) **[Shipped]**

**Symptoms:** Running Phase 4 after Phase 6 overwrote lot scores; unpriced listings sorted above negative lot EV when `rank_value=0`.

**Best fix:** Run hybrid rank **after** lot detection; Phase 4 skips `v2_lot` listings; unpriced listings rank by `ev_raw`.

**Implemented:**
- Pipeline order in production scripts: **Phase 2 → 5 → 3 → 6 → 4** (price join after image verification).
- `run-resumable-pipeline` uses the same execution order.
- Phase 4 skips existing `v2_lot` scores.
- Hybrid scoring sets `rank_value = ev_raw` when no Cardmarket matches.

---

## 3. Compute time at scale

### 3.1 Phase 5 / Phase 6 runtime **[Shipped]**

**Symptoms:** OCR + OpenCV on every image dominates wall time for 500+ listings.

**Best fix:** Skip unchanged images; parallel workers; optional “bulk lots only” for Phase 6.

**Implemented:**
- `PHASE5_SKIP_ANALYZED_IMAGES` (default `false`) — set `true` to skip images with existing `card_region` detections.
- `PHASE6_SKIP_ANALYZED_IMAGES` (default `false`) — set `true` to skip images with existing `lot_card` detections.
- `PHASE6_BULK_LISTINGS_ONLY=true` — title filter before lot detection.
- `PIPELINE_MAX_IMAGE_WORKERS` (12 recommended on 7950X).

---

### 3.2 FAISS subset vs full corpus **[Shipped]**

**Symptoms:** Default `FAISS_BUILD_MAX_CARDS=10000` indexes only a subset; embedding verify fails for cards outside the index.

**Best fix:** Full batched build (`build-faiss-full.ps1`, `FAISS_BUILD_ALL_CARDS=true`) or use external prebuilt catalog (Milo NPZ ~53 MB).

**Implemented:**
- `build-faiss-index-batches` / `build-faiss-full.ps1` — full ~110k art-zone index supported.
- `validate-env` warns when `faiss_vector_count` < `faiss_indexable_total` or crop mode mismatch.
- Art-zone crops cached under `IMAGE_CACHE_DIR/scryfall_art_zones/` — reuse on re-embed without re-download.

**Operator:** After full build, do not rebuild unless `FAISS_INDEX_USE_ART_ZONE`, `OPENCLIP_MODEL_NAME`, or embedder changes. See `card-recognition-architecture.md` § Rebuild matrix.

---

### 3.3 IndexFlatIP at ~110k vectors **[Shipped]**

**Symptoms:** Exact search RAM ~0.2 GB at 110k × 512-d; latency acceptable on CPU for batch Phase 5.

**Best fix:** IVF + PQ if corpus grows past ~500k or query latency becomes bottleneck.

**Status:** Full `IndexFlatIP` at ~110k is operational. Milo 128-d catalog is an alternative proposer without local re-embed (evaluation only).

---

## 4. Data and infrastructure

### 4.1 No schema migrations **[Shipped]** (interim indexes)

**Symptoms:** `init-db` uses `create_all`; existing DBs miss new columns/indexes.

**Best fix:** Alembic migrations (already a dependency) with versioned revision chain.

**Implemented (interim):**
- `ensure-db-indexes` — idempotent performance indexes.
- `init-db` calls `ensure-db-indexes` after `create_all`.

**Future:** `alembic init` + revision per schema change.

---

### 4.2 Disk growth (images + JSON)

**Symptoms:** `.cache/images` and `raw_payload_json` consume tens of GB at full scale.

**Typical layout after full FAISS + ingest** (see `card-recognition-architecture.md`):

| Path under `IMAGE_CACHE_DIR` | Approx. size |
|------------------------------|--------------|
| `scryfall_art/` | ~11 GB |
| `scryfall_art_zones/` | ~23 GB |
| `crops/` + zones | varies per ingest |
| `set_symbol_templates/` | ~150 MB |

**Best fix:** Retention policy — do not delete `scryfall_art/` or art zones unless re-download is acceptable; prune orphaned listing crops only.

**Future:** `ebay-workflows prune-cache --older-than-days N` command; disk budget in `validate-env`.

---

### 4.3 Cardmarket bulk staleness **[Shipped]**

**Symptoms:** EV uses yesterday's (or older) trend prices.

**Best fix:** Scheduled `download-cardmarket-bulk` + `sync-cardmarket`; warn when file age > `CARDMARKET_BULK_REFRESH_HOURS`.

**Implemented:**
- `validate-env` operational health warns on stale/missing bulk file.

---

### 4.4 DirectML / torch stack fragility **[Shipped]** (documented)

**Symptoms:** GPU path breaks on driver or package upgrades; CI does not test `[gpu]` extra.

**Best fix:** Pin versions in optional `[gpu]` extra; CI smoke test on CPU; document fallback `TORCH_DEVICE=cpu`.

**Status:** Documented. `TORCH_DEVICE=cpu` always works; DirectML optional.

---

## 5. Operational gaps

### 5.1 Global rate cap not enforced on CDN downloads **[Shipped]** (partial)

**Symptoms:** Parallel image downloads can spike beyond intended aggregate budget.

**Best fix:** Shared token-bucket limiter across image CDN and FAISS art downloads.

**Implemented:**
- `IMAGE_DOWNLOAD_REQUESTS_PER_MINUTE` (default 120) via `GlobalRateLimiter` in `image_cache.py`.
- eBay API keeps its own `EBAY_REQUESTS_PER_MINUTE` limiter.

**Future:** Unify under `GLOBAL_REQUESTS_PER_MINUTE_CAP` accounting.

---

### 5.2 Failed image downloads silently reduce coverage **[Shipped]**

**Symptoms:** Listings without local images skip OCR/embedding.

**Best fix:** `retry-failed-images` after Phase 1; surface count in validate-env.

**Implemented:**
- `ebay-workflows retry-failed-images`
- Called automatically in `run-live-pipeline.ps1` and `run-large-ingest.ps1`
- `validate-env` warns when `failed_image_downloads > 0`

---

### 5.3 Concurrent pipeline runs **[Shipped]**

**Symptoms:** GUI Workflows + CLI + scheduler can overlap, corrupting cache or doubling API usage.

**Best fix:** Exclusive file lock for pipeline runs.

**Implemented:**
- `PIPELINE_ENFORCE_SINGLE_RUN=true` (default) with lock at `.cache/pipeline.lock`.
- Set `PIPELINE_ENFORCE_SINGLE_RUN=false` for deliberate parallel Phase 2+ only runs.

---

### 5.4 OAuth token on very long runs **[Future]**

**Symptoms:** Multi-hour ingests might outlive token TTL (rare at current page caps).

**Best fix:** Refresh token mid-pagination when `expires_in` elapsed.

**Status:** Documented only. Refresh token before each query in multi-query runs is a future improvement.

---

## 6. Search quality ceiling

### 6.1 Generic OpenCLIP weak on eBay art-zone queries

**Symptoms:** After full art-zone FAISS rebuild (~110k vectors), FAISS rarely drives **verification** (expected under strict gate). Generic ViT-B/32 is not MTG-printing-aware.

**Best fix [Future]:**
1. Evaluate Milo/CollectorVision HF catalog on existing aligned crops — no Scryfall re-download.
2. PaddleOCR on name/bottom zones using existing `crops/zones/*` files.
3. Calibrate `VERIFY_*` thresholds on labeled eBay crops.

**Implemented [Shipped]:**
- Zone pipeline, art-zone index, set symbol templates, mana as **supporting** signal only.
- Strict consensus gate — FAISS/mana/OCR do not alone set `image_verified`.
- `FAISS_PROPOSE_CANDIDATES` inserts proposal candidates; verify gate still required for pricing.

**Historical [Historical]:** Last OR-gate reanalyze ~101 `image_verified` (OCR ~61, mana ~39, FAISS ~1) — mana/OCR counts reflected leakage, not quality.

**Documented:** `card-recognition-architecture.md` — external library analysis and rebuild matrix.

---

### 6.2 Title-only matching for singles

**Symptoms:** eBay titles are ambiguous; fuzzy match alone is insufficient.

**Best fix [Shipped]:** Phase 5 zone OCR + embeddings as signals; title match as prior; strict consensus gate for pricing.

**Implemented [Shipped]:** Hybrid weights: title 35%, OCR 25%, embedding 25%, price freshness 15%; `select_pricing_candidate` for singles EV.

**Future [Future]:** Re-weight hybrid components after post-consensus reanalyze metrics.

---

### 6.3 Non-MTG noise in broad queries **[Shipped]** (partial)

**Symptoms:** Comics, apparel, proxies appear in MTG searches.

**Best fix:** `is_non_mtg_listing()` stricter pricing gate; optional title blocklist; category filters in eBay query.

**Implemented:** `TITLE_MATCH_MIN_SCORE_NON_MTG=0.98` in guardrails.

**Future:** eBay category ID filter in Browse params.

---

### 6.4 Condition / language mismatch **[Future]**

**Symptoms:** Cardmarket NM trend price applied to eBay LP listing.

**Best fix:** Map eBay condition text to Cardmarket condition column; discount EV by condition delta.

**Status:** Documented only. Cardmarket bulk currently uses trend without condition join.

---

## Quick reference — new environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `FAISS_INDEX_USE_ART_ZONE` | `true` | Index art-zone crops (matches query domain); rebuild index after toggle |
| `FAISS_BUILD_ALL_CARDS` | `false` | Full Scryfall index via `build-faiss-full.ps1` in large ingest |
| `IMAGE_EVIDENCE_MIN_FAISS_SCORE` | `0.55` | FAISS proposal/corroboration threshold **[Shipped]** — not standalone verify |
| `IMAGE_EVIDENCE_MIN_MANA_CONFIDENCE` | `0.30` | Mana zone signal threshold **[Shipped]** — supporting only |
| `VERIFY_NAME_HARD_MIN` | `0.75` | Hard verify name OCR **[Shipped]** defaults; calibration **[Future]** |
| `VERIFY_NAME_STRONG_MIN` | `0.88` | Strong symbol path name OCR **[Shipped]** |
| `VERIFY_SYMBOL_STRONG_MIN` | `0.55` | Set symbol verify threshold **[Shipped]** |
| `FAISS_PROPOSE_CANDIDATES` | `true` | Insert `faiss_proposal` when top-1 ∉ Phase 2 **[Shipped]** |
| `IMAGE_ALLOW_FULL_FRAME_FALLBACK` | `true` | OCR/embed when contour detection finds no crop |
| `PHASE5_SKIP_ANALYZED_IMAGES` | `false` | Set `true` for faster incremental image re-runs (skip existing detections) |
| `PHASE6_SKIP_ANALYZED_IMAGES` | `false` | Set `true` to skip images with existing lot detections |
| `FX_GBP_TO_EUR` | `1.17` | Convert eBay GBP costs to EUR base currency |
| `PHASE1_REFRESH_AFTER_HOURS` | disabled | Refresh stale listings without full re-ingest |
| `IMAGE_DOWNLOAD_REQUESTS_PER_MINUTE` | `120` | CDN download rate limit |
| `PIPELINE_ENFORCE_SINGLE_RUN` | `true` | Exclusive pipeline lock |
| `PIPELINE_LOCK_PATH` | `./.cache/pipeline.lock` | Lock file location |

---

## Related docs

- `docs/card-recognition-architecture.md` — zones, artifacts, external libraries, rebuild matrix
- `docs/large-scale-ingest.md` — production ingest runbook
- `docs/config-contract.md` — full env schema
- `docs/integration-specs.md` — eBay/Scryfall/Cardmarket contracts
