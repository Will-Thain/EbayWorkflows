# Testing Strategy

## Goals

- verify deterministic workflow behavior across reruns
- detect regressions in matching/scoring logic
- prevent API misuse, permission overreach, and rate-limit violations
- run automated lint and test checks on every PR to `main`

## Test Layers

- unit tests for parsing, scoring formulas, and confidence composition
- integration tests for each connector with recorded fixtures
- repository/migration tests for DB schema integrity
- workflow orchestration tests for checkpoint/resume behavior
- baseline pytest coverage for Phase 6 rerun idempotency and integrity-check outcomes

## CI Automation

- GitHub Actions workflow at `.github/workflows/ci.yml`
- gates: `ruff check .`, `python -m compileall src`, `pytest -q`
- triggers on pushes to `main` and `milestone-*`, and PRs into `main`

## API Safety Tests

- assert shared rate-limit guard is used by all integration clients
- assert retries honor capped attempts and provider retry headers
- assert disallowed endpoints/scopes are blocked before request execution
- assert request budget counters and logging fields are populated

## Bulk Data Validation Tests

- assert Cardmarket bulk files are present, readable, and schema-valid
- assert stale or malformed files fail fast with actionable errors
- assert file checksum/source metadata is persisted for traceability

## Matching and CV Tests

- OCR extraction correctness on fixture crops
- OpenCLIP + FAISS retrieval sanity for known cards
- hybrid scorer comparison versus OCR-only and embedding-only baselines

## Regression Dataset

- maintain a small labeled dataset (single-card + bulk-lot examples)
- store expected top candidates, confidence bands, and rank ordering
- run dataset checks in CI for pull requests affecting matching/scoring/image code

