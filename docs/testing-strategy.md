# Testing Strategy

**Status:** CI gates and verification-gate regression tests **[Shipped]**. Full labeled eBay crop dataset **[Future]**. Tags: `documentation-status.md`.

## Goals

- verify deterministic workflow behavior across reruns
- detect regressions in matching/scoring logic and **strict verification gate**
- prevent API misuse, permission overreach, and rate-limit violations
- run automated lint and test checks on every PR to `main`

## Test Layers

- **unit tests** — parsing, scoring formulas, confidence composition, currency conversion
- **recognition library tests** — cascade tiers, zone layouts, identifiers (serialization only in `evidence.serialize`)
- **workflow integration tests** — `ebay_workflows.candidates`, `cascade_persist`, Phase 5 matching
- **integration tests** — each connector with recorded fixtures
- **repository/migration tests** — DB schema integrity, `ensure-db-indexes`
- **workflow orchestration tests** — checkpoint/resume, pipeline lock, Phase 6 idempotency
- **GUI unit tests** — presenters, workflow catalog argv, db_browser guards, `workflow_control_flags`, models_qt (no full E2E in CI)

## CI Automation **[Shipped]**

- GitHub Actions workflow at `.github/workflows/ci.yml`
- gates: `ruff check .`, `python -m compileall src`, `pytest -q`
- triggers on pushes to `main` and `milestone-*`, and PRs into `main`

On Windows dev machines use `py -m pytest -q` if `python` is not on PATH.

## Verification Gate Tests **[Shipped]**

Critical regressions to catch in CI when touching Phase 5, guardrails, or `mtg_card_recognition`:

| Area | Test modules |
|------|----------------|
| Cascade persist views | `test_cascade_persist.py` |
| Tier 7 funnel metrics | `test_tier7_metrics.py`, Phase 5 `metrics_json` |
| Import boundary (recognition + adapters only) | `test_import_boundaries.py` **[Shipped]** |
| Library Tier 8 + consumer row policy | `test_evidence_gate.py`, `candidates/image_evidence` facade |
| Per-listing single winner | `test_phase5_matching.py` |
| FAISS proposal (non-verifying insert) | `test_faiss_propose.py` |
| Pricing guardrails (`set_collector` / `set_symbol` only) | `test_ev_guardrails.py`, `test_hybrid_scoring.py` |
| Export provenance columns | `test_ranked_export.py` |
| GUI match detail fields | `test_listing_detail.py` |

Assert that `image_verification_source` is only `set_collector` or `set_symbol` when `image_verified=true`.

## API Safety Tests

- assert shared rate-limit guard is used by integration clients
- assert retries honor capped attempts and provider retry headers
- assert disallowed endpoints/scopes are blocked before request execution
- assert request budget counters and logging fields are populated

## Bulk Data Validation Tests

- assert Cardmarket bulk files are present, readable, and schema-valid
- assert stale or malformed files fail fast with actionable errors
- assert file checksum/source metadata is persisted for traceability

## Matching and CV Tests

- Recognition unit tests: **mtg-card-recognition** (`pytest` in sibling clone)
- Consumer integration:
  - `tests/test_evidence_gate.py` — row policy (`candidates/`)
  - `tests/test_cascade_persist.py` — `cascade_regions_from_analysis`
  - `tests/test_phase5_matching.py`, `test_faiss_propose.py`
  - `tests/test_import_boundaries.py` — only `recognition/` + `adapters/` import library **[Shipped]**
- OpenCLIP + FAISS: `test_embedding_index.py`, `test_faiss_batch.py`
- Hybrid scorer: `test_hybrid_scoring.py`

## Iterative smoke tiers **[Shipped]**

Scale validation in small steps before full-corpus reruns:

| Tier | Command | Scope | Typical runtime |
|------|---------|-------|-----------------|
| 0 | `.\scripts\run-smoke-pipeline.ps1 -Tier 0` | pytest + single-listing Phase 5 (`validate_phase5_listing.py`) | seconds–minutes |
| 1 | `.\scripts\run-smoke-pipeline.ps1 -Tier 1` | 1 eBay page, 10 listings, 30 images | minutes |
| 2 | `-Tier 2` | 3 pages, 50 listings, 200 images | tens of minutes |
| 3 | `-Tier 3` | full corpus (no sample caps) | hours |

Use `-ClearMatchData` on tier 1+ when re-testing matching logic on an existing DB. Use `-SkipIngest` to reuse current listings. CLI flags `--max-listings` / `--max-images` and env `WORKFLOW_MAX_*` apply the same caps to phases 2, 5, and 6.

Per-tier checklist: imports OK, Phase 2 candidates, Phase 5 regions + cascade, FAISS propose, gate fields (`bottom_parsed`, `image_verified`), Phase 3 prices joined, Phase 4 `rank_value > 0` on known-good singles, integrity check green.

Reference listing for bulk-lot cascade: prefix `6ea4f4d3` (multi-card, strict gate expected). Labeled crops: `mtg-card-recognition/tests/fixtures/labeled_crops/`.

## Regression Dataset **[Future]**

- maintain a small labeled dataset (single-card + bulk-lot eBay crops)
- store expected verify/pass/fail, top candidates, and rank ordering
- run dataset checks in CI for pull requests affecting matching/scoring/image code
- calibrate `VERIFY_*` thresholds against labeled crops (see `future-pain-points.md` §6.1)
