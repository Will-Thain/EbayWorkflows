# Testing Strategy

**Status:** CI gates and verification-gate regression tests **[Shipped]**. Full labeled eBay crop dataset **[Future]**. Tags: `documentation-status.md`.

## Goals

- verify deterministic workflow behavior across reruns
- detect regressions in matching/scoring logic and **strict verification gate**
- prevent API misuse, permission overreach, and rate-limit violations
- run automated lint and test checks on every PR to `main`

## Test Layers

- **unit tests** — parsing, scoring formulas, confidence composition, currency conversion
- **recognition library tests** — `mtg_card_recognition.evidence` gate, region attach, zone layouts, identifiers
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
| Strict gate (OCR/FAISS/mana alone fail) | `test_image_evidence.py`, `test_phase5_matching.py` |
| Per-listing single winner | `test_phase5_matching.py`, `test_region_attach.py` |
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

- OCR extraction correctness on fixture crops (`test_card_zones*.py`)
- OpenCLIP + FAISS retrieval sanity (`test_embedding_index.py`, `test_faiss_batch.py`)
- hybrid scorer vs OCR-only and embedding-only baselines (`test_hybrid_scoring.py`)
- Scryfall layout → zone selection (`test_layout_scryfall.py`)

## Regression Dataset **[Future]**

- maintain a small labeled dataset (single-card + bulk-lot eBay crops)
- store expected verify/pass/fail, top candidates, and rank ordering
- run dataset checks in CI for pull requests affecting matching/scoring/image code
- calibrate `VERIFY_*` thresholds against labeled crops (see `future-pain-points.md` §6.1)
