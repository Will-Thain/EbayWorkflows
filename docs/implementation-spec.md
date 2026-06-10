# Implementation Specification

**Status:** Phases 1–6, GUI, and ADR 0002 package layout **[Shipped]**. Tags: `documentation-status.md`.

## Objective

Concrete module layout and build order for the local CLI + PostgreSQL workflow engine, with **mtg-card-recognition v0.3.2** as the image cascade library and EbayWorkflows owning workflow integration.

## Delivered scope

- local CLI workflow runner (`ebay-workflows`)
- PostgreSQL persistence with workflow run/step traceability
- Phases 1–6 + resumable pipeline (`pipeline_resume.py`)
- Desktop GUI (PySide6) — subprocess phases only
- Sibling library **`mtg-card-recognition`** (import `mtg_card_recognition` only from `recognition/` + `adapters/`)

Production phase order: **Phase 2 → 5 → 3 → 6 → 4**.

## Module layout (canonical)

```text
src/ebay_workflows/
  workflows/                   # phase1..6 executors, catalog, resume entrypoints
  recognition/                 # ONLY mtg_card_recognition imports
    phase5_analysis.py         # analyze_listing_image wrapper
    cascade_persist.py, catalog_index.py, embedding_index.py, …
  candidates/                  # row policy (gate, attach, sync, selection)
  scoring/                     # hybrid_scoring, ev_guardrails, currency
  operations/                  # lock, health, export, progress, sample scope
  persistence/                 # session, models re-export, repositories
  integrations/                # ebay, scryfall, cardmarket HTTP
  adapters/                    # Settings ↔ RecognitionSettings
  cli/
  gui/
  models.py                    # canonical SQLAlchemy ORM definitions
  db.py                        # compat shim → persistence.session (Alembic CLI paths)
  persistence/models.py        # re-exports models.py for Alembic env.py
  config.py, pipeline_resume.py
```

**Import rule:** only `recognition/` and `adapters/` may `import mtg_card_recognition`. CI: `tests/test_import_boundaries.py`.

## Contributor doc map

See `contributing-docs.md` for “code change → doc to edit”. Quick reference:

| Code area | Primary docs |
|-----------|--------------|
| `workflows/phase*` | `workflow-phases.md`, `architecture.md` |
| `recognition/` | `card-recognition-architecture.md`, sibling `integration/ebay-workflows.md` |
| `candidates/` | `data-dictionary.md`, `trust-invariants.md`, `ranking-and-confidence.md` |
| `scoring/` | `ranking-and-confidence.md`, `product-requirements.md` |
| `persistence/` | `data-model.md`, `data-dictionary.md` |
| `operations/` | `runbook-local.md`, `testing-strategy.md` |
| `gui/` | `gui-application.md` (no in-process CV) |
| Package layout | `adr/0002-package-restructure.md`, `architecture.md` |

## Build order (historical)

1. Bootstrap, config, DB, phases 1–4 **[Shipped]**
2. Phase 5/6 + FAISS + extract library **[Shipped]**
3. Library v0.3.2 — consumer owns row policy **[Shipped]**
4. ADR 0002 M1–M7 — layered packages, repositories, no `services/` shims **[Shipped]**

## API safety **[Shipped]**

- shared rate-limit guard; retry with backoff
- Cardmarket bulk only with provenance metadata
- `validate-env`, `ebay-auth-check`

## Definition of done

- CLI runs phases 1–6 with resumable checkpoints
- ranked output with verification provenance
- GUI previews matches without in-process CV
- import boundary: only `recognition/` + `adapters/` touch `mtg_card_recognition`

## Related docs

- `architecture.md` — component diagram
- `card-recognition-architecture.md` — Phase 5 sequence
- `adr/0002-package-restructure.md` — restructure record
- `workflow-phases.md` — acceptance criteria
- `trust-invariants.md` — verification policy summary

## [Historical] Pre–ADR 0002 layout

Before 2026-06-10, phase executors lived at repo root (`workflow_phase*.py`) and row policy lived under `services/candidate_*`. **`services/` package removed in M7** — do not restore.

```text
# [Historical] — do not use
workflow_phase{1..6}.py
services/candidate_*, image_analysis, hybrid_scoring, …
```

Migration record: `expert-panel/reviews/ebay-restructure-v1.md`, milestones in `adr/0002-package-restructure.md`.
