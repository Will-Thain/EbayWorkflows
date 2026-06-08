# Implementation Specification

**Status:** Phases 1–6 and GUI **[Shipped]** on branch `feature/card-recognition-package`. Tags: `documentation-status.md`.

## Objective

Concrete module layout and build order for the local CLI + PostgreSQL workflow engine, including image-assisted matching and strict verification gates.

## Delivered Scope

- local CLI workflow runner (`ebay-workflows`)
- PostgreSQL-backed persistence with workflow run/step traceability
- Phase 1: eBay ingest + image cache
- Phase 2: Scryfall title matching (top-K candidates)
- Phase 3: Cardmarket bulk price join
- Phase 4: hybrid EV/confidence ranking + export
- Phase 5: zone OCR, embeddings, strict verification gate, provenance attach
- Phase 6: bulk-lot multi-card detection and lot scoring
- Desktop GUI (PySide6): Opportunities, Workflows, Database, Home, Schedules
- Extractable recognition library: `mtg_card_recognition`

## Module Layout (actual)

```text
src/
  mtg_card_recognition/          # Card recognition library (zones, OCR, embeddings, evidence gate)
    config.py                    # RecognitionSettings
    evidence/                    # gate, selection, attach
    zones/                       # align, layouts, symbol, mana, regions
    ocr/, embeddings/, catalog/, title/, pipeline/
  ebay_workflows/
    cli.py                       # Command handlers
    config.py                    # Settings (env parsing)
    workflow_phase{1..6}.py      # Phase executors
    pipeline_resume.py           # Resumable pipeline
    adapters/recognition_settings.py  # Settings → RecognitionSettings
    integrations/                # ebay, scryfall, cardmarket, cardmarket_bulk
    services/                    # Shims + eBay-specific (ranked_export, ev_guardrails, …)
    gui/                         # PySide6 desktop app
    scheduler.py                 # Headless due-job dispatch
    models.py, db.py
packages/mtg-card-recognition/ # Standalone package metadata (future repo split)
tests/                         # Unit + integration tests (112+ passing)
```

Legacy doc references to `src/cli/`, `src/matching/`, etc. are **[Historical]** — all logic lives under `ebay_workflows` and `mtg_card_recognition`.

## Build Order (as implemented)

1. Bootstrap project, config, DB models, workflow runner skeleton
2. eBay connector + image cache + Phase 1
3. Scryfall sync + Phase 2 title match
4. Cardmarket bulk download/sync + Phase 3
5. OpenCLIP + FAISS index build; Phase 5 zone pipeline + verification gate
6. Phase 4 hybrid scoring + guardrails + ranked export
7. Phase 6 bulk lot detection + lot scoring
8. Extract `mtg_card_recognition`; wire shims and P0 verification fixes
9. GUI (Opportunities → Database → Workflows → Schedules)
10. Operational scripts (`run-live-pipeline.ps1`, `reanalyze-matching.ps1`, large ingest)

Production phase order in scripts: **Phase 2 → 5 → 3 → 6 → 4** (price join after image verification).

## API Safety Requirements (Mandatory) **[Shipped]**

- all provider requests pass through shared rate-limit guard
- retries respect provider policy with exponential backoff + jitter
- no endpoint queried without explicit permission in provider terms
- Cardmarket uses permitted downloadable bulk files with checksum/source metadata
- `validate-env` and `ebay-auth-check` for startup health

## Definition of Done

- CLI runs phases 1–6 against configured query with resumable checkpoints
- run status and errors persisted; partial reruns safe
- ranked output with explainable EV/confidence and verification provenance
- API calls within configured limits; pipeline single-run lock optional
- GUI previews matches with verification source and proof detection highlight

## Related docs

- `card-recognition-architecture.md` — verification spec and package boundaries
- `workflow-phases.md` — per-phase acceptance criteria
- `gui-application.md` — desktop app spec (implemented)
