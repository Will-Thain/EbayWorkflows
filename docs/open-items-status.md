# Open Items Status (P1–P4)

Track incomplete workflow elements ranked by priority. Updated after incremental closure pass on **2026-06-08** (`main` @ post finish-ranking commit).

**Legend:** ✅ Done · 🟡 Partial · ⏸ Blocked · 📋 Documented only

---

## P1 — Code & scripts (operational hygiene)

| # | Item | Status | Notes |
|---|------|--------|-------|
| 1 | `finish-ranking.ps1` + `finish_ranking.py` | ✅ | Committed `7676e62`; phase4-only finish on CPU |
| 2 | `reanalyze-matching.ps1` Invoke-Cli fix | ✅ | `ValueFromRemainingArguments` + `clear-match-data -y` |
| 3 | Typed HTTP errors — Cardmarket bulk | ✅ | `cardmarket_bulk.py` uses `raise_for_http_response` + retry |
| 4 | `finish_ranking_debug.py` | 🟡 | Kept for operator step-through; not wired into CI |

---

## P2 — Designed / stubbed (engineering)

| # | Item | Status | Notes |
|---|------|--------|-------|
| 5 | Labeled crop regression | 🟡 | Manifest + schema tests shipped; recognition regression skips until real PNGs added |
| 6 | PaddleOCR backend | ⏸ | Enum accepts `paddleocr`; Tesseract only. Needs backend impl + accuracy validation |
| 7 | Milo / alternate embedder | ⏸ | Architecture docs only; OpenCLIP+FAISS is production path |
| 8 | FAISS tuning / rebuild automation | 🟡 | `build-faiss-index` works; Phase 6 DirectML hang on Windows — use `TORCH_DEVICE=cpu` or `-SkipPhase6` |
| 9 | Alembic migrations | 🟡 | Baseline stamp `0001`; schema changes use `init-db` + `ensure-db-indexes` interim |
| 10 | `mtg-card-recognition` standalone repo | ⏸ | Monorepo extract complete; separate repo + CI port deferred |
| 11 | Global rate limit unification | 🟡 | Shared limiter wired for Scryfall + Cardmarket + image CDN; eBay keeps per-provider limiter + global wait |
| 12 | OAuth refresh on long runs | ✅ | eBay Browse API retries once with fresh token on 401 |
| 13 | Cache prune CLI | ✅ | `ebay-workflows prune-image-cache` removes unreferenced root cache files |
| 14 | Condition-aware Cardmarket pricing | ⏸ | Multipliers in config; bulk CSV is EX-only — needs condition mapping from listing text |
| 15 | FX / currency normalization job | ⏸ | Rankings use listing currency as-is |

---

## P3 — GUI & operator flows

| # | Item | Status | Notes |
|---|------|--------|-------|
| 16 | Opportunities tab useful data | ⏸ | Blocked on Phase 5 verify (0 verified after last finish-ranking) |
| 17 | Phase 6 lot detection | ⏸ | Hung on DirectML model load; 0 lot detections in DB |
| 18 | GUI dark theme / logs / thumbnails | ✅ | Shipped PR #5 |
| 19 | Headless resumable pipeline in GUI | 📋 | CLI `run-resumable-pipeline` only; documented in `gui-operator-workflows.md` |
| 20 | Full reanalyze on new 3.12 venv | ⏸ | Operator action: `./scripts/reanalyze-matching.ps1 -SkipPhase6` |

---

## P4 — Docs & repo hygiene

| # | Item | Status | Notes |
|---|------|--------|-------|
| 21 | GitHub default branch → `main` | ⏸ | Requires `gh` CLI or GitHub UI: Settings → Default branch → `main` |
| 22 | `documentation-status.md` sync | ✅ | Branch reference updated to `main`; links this doc |
| 23 | Post-reanalyze operational metrics | 🟡 | Last finish-ranking run recorded below; re-run after full Phase 5 |
| 24 | Stale remote branches | 📋 | `milestone-*` / old `feature/*` remotes unmaintained — safe to delete after review |

---

## Latest pipeline snapshot (finish-ranking, 2026-06-08)

After venv rebuild (Python 3.12) and `scripts/finish-ranking.ps1` (phase4-only, Phase 6 skipped):

| Metric | Count |
|--------|------:|
| Listings | 2,682 |
| OCR results | 110,784 |
| Scored listings | 2,682 |
| Verified candidates | 0 |
| Pricing-eligible | 0 |
| rank_value > 0 | 0 |
| Lot card detections | 0 |

**Interpretation:** Phase 4 structure is populated; strict verification and positive EV require a **fresh Phase 5 re-run** on the new venv.

---

## Recommended next actions

1. `./scripts/reanalyze-matching.ps1 -SkipPhase6` — full OCR + verify on 3.12 venv
2. If still 0 verified — review Tesseract, FAISS coverage, `VERIFY_*` thresholds
3. Phase 6 only after `TORCH_DEVICE=cpu` confirmed stable
4. Add real labeled crops under `tests/fixtures/labeled_crops/examples/` for CI regression

---

## Related docs

- `documentation-status.md` — doc index and tags
- `runbook-local.md` — operator commands including finish-ranking and reanalyze
- `future-pain-points.md` — detailed backlog
- `workflow-phases.md` — phase order 2→5→3→6→4
