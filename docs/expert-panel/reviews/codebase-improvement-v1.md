# Expert panel — Codebase improvement v1

**Date:** 2026-06-10  
**Topic:** Post–M7 (`d038a3f`) codebase health — architecture, trust tests, persistence, CI, config  
**Outcome:** **5/5 APPROVE WITH AMENDMENTS** — layout is sound; **trust-path unit tests** and **CI hygiene** are the highest-value next work  
**Process:** [`process.md`](../process.md) · Unanimous for trust-path tests; majority for refactors and config split

## Scope

Panel review after ADR 0002 M7 commit and legacy-code audit P0–P3. Cross-checked:

- `src/ebay_workflows/` (all packages)
- `tests/` — **127 passed** at review time
- `.github/workflows/ci.yml`, `pyproject.toml`, `config.py`
- `docs/open-items-status.md`, `post-workflow-checklist.md`

**Question:** What still needs improvement? What is correctly deferred?

**Baseline:** Commit `d038a3f` on local `main` (**ahead of origin by 1** — push pending).

---

## Executive summary

| Area | Maturity | Top gap |
|------|----------|---------|
| Package layout (M7) | ✅ Shipped | Push commit; optional anti-`services/` CI grep |
| Library import boundary | ✅ Enforced | `test_import_boundaries.py` + CI step |
| Trust policy (code) | ✅ Shipped | **`candidate_sync` / `candidate_selection` / `candidate_attach` untested** |
| Phase executors | 🟡 Relocated monoliths | Phase 5 (566 LOC), Phase 6 (481 LOC) |
| Persistence repos | 🟡 Read-only | Writes still inline in phases |
| Config | 🟡 Monolithic | YAML split deferred; dead env field |
| CI | 🟡 Partial | **`ruff check .` fails locally** (6 `src/` + 4 `scripts/` issues) |
| GUI boundary | ✅ Subprocess-only | No `mtg_card_recognition` in `gui/` |

---

## Expert 1 — Application architecture

**Specialty:** Package boundaries, layering, module size

### Assessment

**Strengths**

- M7 layout is clean: no `services/` or `workflow_phase*` on disk; canonical imports under `workflows/`, `candidates/`, etc.
- `test_import_boundaries.py` enforces the mtg library rule; CI runs it explicitly.
- Thin re-export shims (`db.py`, `gui/workflow_catalog.py`, `recognition/regions.py`) are acceptable.

**Gaps**

| Issue | Severity | Evidence |
|-------|----------|----------|
| Phase executors not “thin” per ADR M4 intent | P1 | `phase5.py` 566 lines, `phase6.py` 481 lines — orchestration + persistence + CV glue in one file |
| CLI reaches into `recognition/` | P2 | `cli/commands/index.py` imports `embedding_index`, `set_symbol_match`; `env.py` imports `index_exists` |
| `operations/health_checks.py` imports recognition | P2 | CV health in operations layer — coupling for `validate-env` |
| Duplicate phase boilerplate | P2 | `_now()` copied in all six `workflows/phase*.py` files |
| Unused imports in phases | P2 | Ruff F401: `phase4.py` (`uuid`, `select`), `phase5.py` (`Listing`, `ListingScoreRepository`) |

### Vote

**APPROVE WITH AMENDMENTS** — Architecture is **correct at package level**; next wins are ** slimming phase5/6** and shared run/step helpers.

### Actions (E1)

| ID | Action |
|----|--------|
| E1-1 | Extract shared workflow run/step bootstrap (`workflow_run.py` or `operations/workflow_run.py`) |
| E1-2 | Fix ruff F401 in `phase4.py`, `phase5.py` (CI blocker) |
| E1-3 | Document CLI → `recognition/` as intentional operator surface in `architecture.md` |

---

## Expert 2 — Workflow orchestration

**Specialty:** Phase graph, Phase 5/6 complexity, resume pipeline

### Assessment

**Strengths**

- Production order **2 → 5 → 3 → 6 → 4** documented and implemented in `pipeline_resume.py`.
- `workflows/catalog.py` shared by CLI and GUI (ADR H-7).
- Tier 7 metrics in Phase 5 (`operations/metrics.py`, `test_tier7_metrics.py`).

**Gaps**

| Issue | Severity | Evidence |
|-------|----------|----------|
| Phase integration tests sparse | P1 | Only `test_phase6_and_integrity.py` runs a phase executor end-to-end; phases 1–4 have **no** integration tests |
| Phase 5 test surface narrow | P1 | `test_phase5_matching.py` — 2 tests on `_apply_region_evidence_to_candidates` only; cascade attach path untested |
| Mock OCR bypasses cascade | P2 | `--mock-ocr-file` in `phase5.py` / CLI — dev path; production uses `--use-real-ocr` |
| Broad `except Exception` | P2 | All phases → `fail_workflow_step`; no typed partial-failure taxonomy |
| Lambda assignments | P2 | Ruff E731 in `phase6.py:434`, `recognition/lot_crop_match.py:32` |

### Vote

**APPROVE WITH AMENDMENTS** — Orchestration works; **test the cascade attach path** before the next matching change.

### Actions (E2)

| ID | Action |
|----|--------|
| E2-1 | Add `test_phase5_cascade_sync.py` — fixture cascade payload → `apply_cascade_proposals_to_candidates` |
| E2-2 | Smoke test Phase 4 ranking with in-memory DB (minimal listing + candidate rows) |
| E2-3 | Split Phase 5: `_persist_analysis` + parallel OCR into `recognition/phase5_persist.py` when next touching Phase 5 |

---

## Expert 3 — Data / persistence

**Specialty:** ORM, repositories, Alembic

### Assessment

**Strengths**

- ORM narrative fixed: `models.py` canonical; `persistence/models.py` Alembic surface.
- Repositories used for reads in all phases (`test_repositories.py`).
- Alembic baseline `0001`/`0002` shipped; `env.py` imports `persistence.models.Base`.

**Gaps**

| Issue | Severity | Evidence |
|-------|----------|----------|
| Repositories read-only | P1 | `CandidateRepository` / `ListingRepository` / `ListingScoreRepository` — query methods only; phases use `session.add` / `delete` directly (e.g. `phase1.py:225`, `phase5.py:235`) |
| No transaction boundaries doc | P2 | Multi-step phase writes commit inline; rollback story implicit |
| GUI read-side SQLAlchemy | ✅ OK | `gui/db_browser.py`, `workflow_monitor.py` — read queries only, not workflow execution |

### Vote

**APPROVE WITH AMENDMENTS** — Incremental repo write migration per open-items #16; **no big-bang** (ADR R-1 still applies).

### Actions (E3)

| ID | Action |
|----|--------|
| E3-1 | Add `ListingRepository.upsert_from_ebay` (or similar) for Phase 1 writes — first write migration |
| E3-2 | Add `CandidateRepository.replace_title_matches(listing_id, rows)` for Phase 2 delete+insert pattern |
| E3-3 | Document commit/rollback expectations in `data-model.md` § workflow runs |

---

## Expert 4 — Systems, CI, config

**Specialty:** CI gates, config contract, operator tooling

### Assessment

**Strengths**

- CI: checkout, Python 3.11, Tesseract, ruff, compileall, import-boundary pytest, full pytest.
- `validate-nonblockers.ps1` — operator smoke subset (not in CI).
- Global rate limit unified (`GLOBAL_REQUESTS_PER_MINUTE_CAP`).

**Gaps**

| Issue | Severity | Evidence |
|-------|----------|----------|
| **Ruff fails on `main`** | P1 | `ruff check .` → 10 errors (6 in `src/`+`tests`, 4 in `scripts/`) — **CI would fail on push** |
| Config YAML split not started | P2 | `post-workflow-checklist.md` §6.2 all unchecked; no `config/*.yaml` |
| Dead config field | P2 | `IMAGE_DOWNLOAD_REQUESTS_PER_MINUTE` in `config.py:77` — **never read**; Phase 1 uses `global_requests_per_minute_cap` |
| `validate-nonblockers.ps1` not in CI | P2 | Faster subset than full pytest; catches doc/layout drift |
| Python 3.12 not in matrix | P3 | Open-items #24 recommends 3.12 venv for full corpus; CI only 3.11 |
| `paddleocr` in core deps | P3 | `pyproject.toml:15` — production OCR is Tesseract; Paddle **[Future]** |
| No coverage / mypy | P3 | Acceptable for now; revisit when trust tests land |

### Vote

**APPROVE WITH AMENDMENTS** — **Fix ruff before push**; config split is next milestone, not blocker.

### Actions (E4)

| ID | Action |
|----|--------|
| E4-1 | Fix all ruff errors in `src/` and `tests/`; fix or exclude `scripts/` consistently |
| E4-2 | Push `d038a3f` to origin; confirm CI green |
| E4-3 | Remove or wire `IMAGE_DOWNLOAD_REQUESTS_PER_MINUTE`; update `.env.example` |
| E4-4 | Add CI step: `pytest -q tests/test_import_boundaries.py tests/test_evidence_gate.py tests/test_repositories.py tests/test_tier7_metrics.py` as fast trust gate |
| E4-5 | Schedule config YAML milestone per `post-workflow-checklist.md` §6 |

---

## Expert 5 — Trust / verification

**Specialty:** Candidate row policy, cascade attach, pricing eligibility

### Assessment

**Strengths**

- `candidate_gate.py` tested (`test_evidence_gate.py` — 6 tests including pre-cascade fallback).
- `test_cascade_persist.py` covers signal mapping.
- `trust-invariants.md` documents single-winner policy.
- Cascade blocked rows cannot be upgraded by legacy heuristics (tested).

**Gaps**

| Issue | Severity | Evidence |
|-------|----------|----------|
| **`candidate_sync` untested** | **P0 trust** | Zero test references; merges `proposal_to_evidence`, provenance, zone payload — **Phase 5 production path** |
| **`candidate_selection` untested** | **P0 trust** | `apply_per_listing_verification_gates`, `select_pricing_candidate` — **≤1 verified winner** invariant |
| **`candidate_attach` untested** | P1 | `merge_verification_provenance`, region attach helpers |
| Pre-cascade fallback sunset | P2 | Keep until reanalyze; grep DB for missing `gate_status` before removal (legacy audit E5-2) |
| Labeled-crop regression | P2 | `test_labeled_crops_manifest.py` only; real PNGs deferred to mtg-card-recognition repo |

### Vote

**APPROVE WITH AMENDMENTS** — **Unanimous:** add sync + selection tests **before** the next verification or pricing change.

### Actions (E5)

| ID | Action |
|----|--------|
| E5-1 | **`tests/test_candidate_sync.py`** — proposal merge, provenance fields, gate_status on evidence |
| E5-2 | **`tests/test_candidate_selection.py`** — two verified candidates → one winner; demotion of losers |
| E5-3 | **`tests/test_candidate_attach.py`** — provenance merge idempotency |
| E5-4 | Extend `validate-nonblockers.ps1` to require E5-1/E5-2 passing |

---

## Phase C — Final votes

| Agent | Specialty | Vote |
|-------|-----------|------|
| 1 | Application architecture | APPROVE WITH AMENDMENTS |
| 2 | Workflow orchestration | APPROVE WITH AMENDMENTS |
| 3 | Data / persistence | APPROVE WITH AMENDMENTS |
| 4 | Systems / CI / config | APPROVE WITH AMENDMENTS |
| 5 | Trust / verification | APPROVE WITH AMENDMENTS |

**Result: 5/5 APPROVE WITH AMENDMENTS**

---

## Consolidated improvement backlog

### P0 — Trust & release hygiene

| ID | Action | Owner |
|----|--------|-------|
| P0-1 | Add `test_candidate_sync.py` + `test_candidate_selection.py` | Trust | ✅ |
| P0-2 | Fix ruff errors in `src/` + `tests/`; push `main` and confirm CI | Systems | ✅ |
| P0-3 | Push M7 commit to origin if not already | Systems | ✅ |

### P1 — Quality & coverage

| ID | Action | Owner |
|----|--------|-------|
| P1-1 | Phase 5 cascade attach integration test | Workflow | ✅ |
| P1-2 | `test_candidate_attach.py` | Trust | ✅ |
| P1-3 | Begin repository write migration (Phase 1 listings) | Data | ✅ |
| P1-4 | Fix unused imports / E731 lambdas flagged by ruff | Architecture | ✅ |

### P2 — Structure & operator UX

| ID | Action | Owner |
|----|--------|-------|
| P2-1 | Extract shared phase run/step bootstrap | Workflow | ✅ |
| P2-2 | Config YAML split OR remove dead `IMAGE_DOWNLOAD_REQUESTS_PER_MINUTE` | Systems | ✅ |
| P2-3 | Tests for `health_checks`, `rate_limit`, `pipeline_lock` | Operations | ✅ |
| P2-4 | Phase 4 minimal integration test | Workflow | ✅ |
| P2-5 | Opportunities tab — blocked until verified Phase 5 data (open-items #20) | GUI |

### P3 — Future / nice-to-have

| ID | Action | Owner |
|----|--------|-------|
| P3-1 | Python 3.12 CI matrix job | Systems | ✅ |
| P3-2 | Tier 7-style metrics for phases 1–4, 6 | Operations | ✅ |
| P3-3 | Move `paddleocr` to optional extra | Systems | ✅ |
| P3-4 | Split Phase 5/6 into smaller modules | Workflow | ✅ |
| P3-5 | Labeled-crop PNG regression in sibling repo | Recognition |

---

## Correctly deferred (do not treat as defects)

| Item | Reason |
|------|--------|
| GUI in-process CV | ADR + unanimous **REJECT** — `QProcess` only; verified no mtg imports in `gui/` |
| Full `models.py` split into `persistence/` | ADR R-1 — Alembic + repos first |
| Pre-cascade `gate_status` fallback removal | Needs post-reanalyze data criterion |
| PaddleOCR / Milo production backends | Documented **[Future]** in `future-cv-ocr.md` |
| YAML config profiles | Designed in checklist §6; not started by choice |
| Full corpus reanalyze | Operator task (hours); open-items #24 |

---

## Rejected proposals

| ID | Proposal | Reason |
|----|----------|--------|
| R-I1 | Big-bang rewrite of phase5/6 before trust tests | Risk without sync/selection coverage |
| R-I2 | Enforce full ADR dependency DAG in CI beyond mtg boundary | Diminishing returns; CLI index commands need recognition |
| R-I3 | Delete mock OCR path now | Still useful for dev; not production default |
| R-I4 | Mandatory mypy/coverage gates immediately | Add after ruff green + trust tests |

---

## Maturity model (post-M7)

| Level | Criteria | Status |
|-------|----------|--------|
| L1 Layered packages | ADR 0002 M7 on branch | ✅ local `main` |
| L2 Enforced library boundary | `test_import_boundaries` + CI | ✅ |
| L3 Trust path unit-tested | gate + cascade_persist + sync/selection/attach | ✅ |
| L4 CI always green | ruff + pytest on push | ✅ |
| L5 Thin phase executors | <300 LOC, shared bootstrap | 🟡 phase5/6 split started |
| L6 Config profiles | YAML + slim `.env` | ❌ deferred |
| L7 Full phase integration tests | All phases smoke-tested | 🟡 phase4 + phase6 |

---

## Related

- `docs/expert-panel/reviews/legacy-code-audit-v1.md` — shim removal (P0–P3 ✅)
- `docs/expert-panel/reviews/ebay-restructure-v1.md` — original layout vote
- `docs/open-items-status.md` — tracked partial items
- `docs/trust-invariants.md` — policy reference for E5 tests
