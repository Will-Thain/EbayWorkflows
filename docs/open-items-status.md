# Open Items Status (P1–P4)

Track incomplete workflow elements ranked by priority.

**Legend:** ✅ Done · 🟡 Partial · ⏸ Blocked / in progress · 📋 Documented only

**Last updated:** 2026-06-10 (ADR 0002 M1–M7; documentation audit P0–P1)

---

## P1 — Code & scripts (operational hygiene)

| # | Item | Status | Notes |
|---|------|--------|-------|
| 1 | `finish-ranking.ps1` + `finish_ranking.py` | ✅ | Phase4-only finish on CPU |
| 2 | `reanalyze-matching.ps1` CLI fix | ✅ | `python -m`; `clear-match-data -y`; `--output` for export |
| 3 | Typed HTTP errors — Cardmarket bulk | ✅ | `raise_for_http_response` + retry |
| 4 | `finish_ranking_debug.py` | ✅ | Operator-only; documented in `runbook-local.md` §17f |

---

## P2 — Designed / stubbed (engineering)

| # | Item | Status | Notes |
|---|------|--------|-------|
| 5 | Labeled crop regression | 🟡 | Manifest + schema tests; recognition test skips until real PNGs ≥512 B |
| 6 | PaddleOCR backend | ⏸ | Enum only; Tesseract is production OCR |
| 7 | Milo / alternate embedder | ⏸ | Docs only; OpenCLIP+FAISS is production path |
| 8 | FAISS tuning / Phase 6 GPU | 🟡 | Use `TORCH_DEVICE=cpu`; smoke-test Phase 6 after reanalyze |
| 9 | Alembic migrations | 🟡 | Baseline `0001`/`0002` shipped; incremental revisions when schema changes |
| 10 | `mtg-card-recognition` standalone repo | ✅ | Sibling repo v0.3.2+; EbayWorkflows is consumer (`scripts/install-dev.ps1`) |
| 11 | Global rate limit unification | ✅ | eBay, Scryfall, Cardmarket, image CDN share `GLOBAL_REQUESTS_PER_MINUTE_CAP` |
| 12 | OAuth refresh on long runs | ✅ | eBay Browse retries once with fresh token on 401 |
| 13 | Cache prune CLI | ✅ | `ebay-workflows prune-image-cache` |
| 14 | Condition-aware Cardmarket pricing | 🟡 | **Shipped in ranking:** `scoring/listing_condition.py` + `scoring/ev_guardrails.py`; bulk CSV remains EX-only |
| 15 | FX / currency normalization | 🟡 | **Shipped for GBP→EUR:** `scoring/currency.py` + phase4/hybrid via `FX_GBP_TO_EUR` |
| 16 | Repository coverage | 🟡 | All phases 1–6 use repos for listing/candidate/score reads; expand writes incrementally |
| 17 | Tier 7 metrics | ✅ | `operations/metrics.py`; Phase 5 `metrics_json` keys `tier7_*` |
| 18 | GUI resumable pipeline | ✅ | `workflows/catalog` job `pipeline` → `run-resumable-pipeline` |
| 19 | CV/OCR futures doc | 📋 | `future-cv-ocr.md`; PaddleOCR/Milo still **[Future]** |

---

## P3 — GUI & operator flows

| # | Item | Status | Notes |
|---|------|--------|-------|
| 20 | Opportunities tab useful data | ⏸ | Depends on verified candidates from Phase 5 runs |
| 21 | Phase 6 lot detection | 🟡 | Shipped; validate on CPU after Phase 5 sample |
| 22 | GUI dark theme / logs / thumbnails | ✅ | Shipped PR #5 |
| 23 | Headless resumable pipeline in GUI | ✅ | `pipeline` tile launches `run-resumable-pipeline` |
| 24 | Full corpus reanalyze on 3.12 venv | 🟡 | Use `scripts/validate-nonblockers.ps1` + sample iterations first |

---

## P4 — Docs & repo hygiene

| # | Item | Status | Notes |
|---|------|--------|-------|
| 25 | GitHub default branch → `main` | 📋 | Manual: GitHub → Settings → Default branch → `main` |
| 26 | `documentation-status.md` sync | ✅ | Post–M7 layout; audit P0–P1 applied |
| 27 | Expert doc audit P0–P1 | ✅ | `expert-panel/reviews/documentation-audit-v1.md` |
| 28 | Stale remote branches | 📋 | Review/delete `milestone-*`, old `feature/*` when convenient |

---

## After pipeline run — operator checklist

See **`post-workflow-checklist.md`** for the full post-run sequence (validation, GUI, config, docs).

Quick validation:

```powershell
.\scripts\post-reanalyze-validation.ps1
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m ebay_workflows.cli match-stats
```

Optional smoke after code/doc changes:

```powershell
.\.venv\Scripts\python.exe scripts\run_sample_iterations.py --count 5 --max-images 2
```

---

## [Historical] Reanalyze snapshot (2026-06-09)

`reanalyze-matching.ps1 -SkipPhase6` finished in **~2.85 hours** (exit 0). Phases 2, 3, and 4 completed; **Phase 5 aborted** mid-run.

| Metric | Count |
|--------|------:|
| Listings | 2,682 |
| Listing images | 11,650 |
| Card candidates | 166 |
| OCR results | 0 |
| Image detections | 0 |
| Verified candidates | 0 |

**Failure at time:** `UniqueViolation` on `uq_listing_scryfall_source` for duplicate `faiss_proposal` → session rollback. Subsequent code and sample iteration work addressed dedup paths; treat this as a **point-in-time snapshot**, not current blocker status.

---

## Not finishable now (deferred backlog)

| Area | Item | Why deferred |
|------|------|--------------|
| **CV / OCR** | PaddleOCR backend | Full implementation + accuracy validation vs Tesseract |
| **CV / OCR** | Labeled crop CI regression | Needs curated real eBay crop PNGs |
| **Matching** | Milo / CollectorVision embedder | Evaluation and index rebuild project |
| **Schema** | Alembic incremental revisions | Only when `models.py` changes |
| **Pricing** | Live FX rate job | Static `FX_GBP_TO_EUR` sufficient for local MVP |
| **Pricing** | Cardmarket condition-specific bulk rows | Official export is EX-only |
| **GUI** | Resumable pipeline in GUI | CLI covers headless use |
| **Ops** | GitHub default branch | One-time UI change |

---

## Related docs

- `documentation-status.md` — doc index and tags
- `contributing-docs.md` — code change → doc map
- `runbook-local.md` — setup, phases, reanalyze
- `future-pain-points.md` — detailed backlog
- `workflow-phases.md` — phase order 2→5→3→6→4
