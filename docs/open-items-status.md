# Open Items Status (P1–P4)

Track incomplete workflow elements ranked by priority.

**Legend:** ✅ Done · 🟡 Partial · ⏸ Blocked / in progress · 📋 Documented only

**Last updated:** 2026-06-09 (post-reanalyze run; Phase 5 partial failure)

---

## Reanalyze result (2026-06-09)

`reanalyze-matching.ps1 -SkipPhase6` finished in **~2.85 hours** (exit 0). Phases 2, 3, and 4 completed; **Phase 5 aborted** mid-run.

| Metric | Count |
|--------|------:|
| Listings | 2,682 |
| Listing images | 11,650 |
| Card candidates | 166 |
| OCR results | 0 |
| Image detections | 0 |
| Verified candidates | 0 |
| Pricing-eligible | 78 |
| Scored listings | 2,682 |
| rank_value > 0 | 0 |

**Phase 5 failure:** `UniqueViolation` on `uq_listing_scryfall_source` inserting duplicate `faiss_proposal` candidate → session rollback; OCR/detections not persisted.

**Export:** PowerShell `-o` is ambiguous inside `Invoke-Cli` — scripts now use `--output` (fix committed locally).

**Next:** Fix `propose_embedding_candidates` upsert/dedup, re-run Phase 5 only (`phase5-verify-ocr --use-real-ocr --use-embedding-match`), then phase3 → phase4 → validation.

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
| 9 | Alembic migrations | 🟡 | Baseline `0001`; stamp after `init-db` — see runbook §4b |
| 10 | `mtg-card-recognition` standalone repo | ⏸ | Monorepo extract done; separate repo deferred |
| 11 | Global rate limit unification | ✅ | eBay, Scryfall, Cardmarket, image CDN share `GLOBAL_REQUESTS_PER_MINUTE_CAP` |
| 12 | OAuth refresh on long runs | ✅ | eBay Browse retries once with fresh token on 401 |
| 13 | Cache prune CLI | ✅ | `ebay-workflows prune-image-cache` |
| 14 | Condition-aware Cardmarket pricing | 🟡 | **Shipped in ranking:** `listing_condition.py` + `ev_guardrails.py` apply NM/LP/… multipliers; bulk CSV remains EX-only |
| 15 | FX / currency normalization | 🟡 | **Shipped for GBP→EUR:** `currency.py` + phase4/hybrid scoring via `FX_GBP_TO_EUR`; live rate API job not built |

---

## P3 — GUI & operator flows

| # | Item | Status | Notes |
|---|------|--------|-------|
| 16 | Opportunities tab useful data | ⏸ | 0 verified after reanalyze |
| 17 | Phase 6 lot detection | ⏸ | After Phase 5 succeeds on CPU |
| 18 | GUI dark theme / logs / thumbnails | ✅ | Shipped PR #5 |
| 19 | Headless resumable pipeline in GUI | 📋 | CLI `run-resumable-pipeline` only |
| 20 | Full reanalyze on 3.12 venv | 🟡 | Ran ~2.85h; Phase 5 failed — partial re-run needed |

---

## P4 — Docs & repo hygiene

| # | Item | Status | Notes |
|---|------|--------|-------|
| 21 | GitHub default branch → `main` | 📋 | Manual: GitHub → Settings → Default branch → `main` |
| 22 | `documentation-status.md` sync | ✅ | Points at `main` and this doc |
| 23 | Post-reanalyze operational metrics | ✅ | Snapshot recorded above; export blocked until `--output` fix deployed |
| 24 | Stale remote branches | 📋 | Review/delete `milestone-*`, old `feature/*` when convenient |

---

## After Phase 5 re-run — operator checklist

See **`post-workflow-checklist.md`** for the full post-run sequence (validation, GUI, config restructure, docs).

Quick validation:

```powershell
.\scripts\post-reanalyze-validation.ps1
.venv\Scripts\python.exe -m ebay_workflows.cli match-stats
```

---

## Not finishable now (deferred backlog)

These require substantial work, external assets, or must not run while reanalyze holds the pipeline lock:

| Area | Item | Why deferred |
|------|------|--------------|
| **CV / OCR** | PaddleOCR backend | Full implementation + accuracy validation vs Tesseract |
| **CV / OCR** | Labeled crop CI regression | Needs curated real eBay crop PNGs under `tests/fixtures/labeled_crops/examples/` |
| **Matching** | Milo / CollectorVision embedder | Evaluation and index rebuild project |
| **Repo** | Standalone `mtg-card-recognition` repo | Extract + CI port |
| **Schema** | Alembic incremental revisions | No pending schema change; use `init-db` + `ensure-db-indexes` until next model edit |
| **Pricing** | Live FX rate job | Static `FX_GBP_TO_EUR` sufficient for local MVP |
| **Pricing** | Cardmarket condition-specific bulk rows | Official export is EX-only; listing-side multipliers already applied at rank time |
| **GUI** | Resumable pipeline in GUI | New feature; CLI `run-resumable-pipeline` covers headless use |
| **Ops** | Phase 6 during reanalyze | `PIPELINE_ENFORCE_SINGLE_RUN` — wait for current run |
| **Ops** | GitHub default branch | One-time UI change on github.com |
| **Ops** | Delete stale remote branches | Needs owner review before `git push origin --delete` |

---

## Related docs

- `documentation-status.md` — doc index and tags
- `runbook-local.md` — setup, phases, reanalyze, post-reanalyze
- `future-pain-points.md` — detailed backlog
- `workflow-phases.md` — phase order 2→5→3→6→4
