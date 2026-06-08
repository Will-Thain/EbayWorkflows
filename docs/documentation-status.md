# Documentation Status Labels

Use these tags when reading or editing docs so **shipped code**, **historical behavior**, and **planned work** are not confused.

## Tags

| Tag | Meaning |
|-----|---------|
| **[Shipped]** | Implemented on branch `main`. Describes current production behavior. |
| **[Historical]** | Describes behavior **before** the consensus gate / `mtg_card_recognition` extraction. Kept for audit and before/after comparison — **do not restore**. |
| **[Future]** | Planned, partial, or tunable — **not final** production behavior. May exist as config flags or stubs without full validation. |

When a line mixes shipped and planned parts, tag each clause: e.g. “FAISS corroboration **[Shipped]**; Milo embedder **[Future]**”.

## Full document index

| Document | Status | Notes |
|----------|--------|-------|
| `card-recognition-architecture.md` | **[Shipped]** + **[Historical]** | Canonical verification spec; OR-gate audit sections labeled |
| `workflow-phases.md` | **[Shipped]** | Phase order 2→5→3→6→4; Phase 5 gate |
| `config-contract.md` | **[Shipped]** | Env vars including `VERIFY_*`, `FAISS_PROPOSE_CANDIDATES` |
| `data-dictionary.md` | **[Shipped]** | `evidence_json` verification + provenance fields |
| `data-model.md` | **[Shipped]** | Schema; Alembic **[Future]** |
| `ranking-and-confidence.md` | **[Shipped]** | Guardrails; formula tuning **[Future]** |
| `library-stack.md` | **[Shipped]** | Tesseract shipped; PaddleOCR/Milo **[Future]** |
| `integration-specs.md` | **[Shipped]** | API contracts + CV policy summary |
| `implementation-spec.md` | **[Shipped]** | Actual module layout and build order |
| `runbook-local.md` | **[Shipped]** | Setup, phases, reanalyze scripts |
| `testing-strategy.md` | **[Shipped]** | CI + verification gate tests; labeled dataset **[Future]** |
| `large-scale-ingest.md` | **[Shipped]** | Runbook; troubleshooting tagged inline |
| `future-pain-points.md` | Mixed | Per-section **[Shipped]** / **[Future]** / **[Historical]** |
| `architecture.md` | **[Shipped]** | High-level; detail in card-recognition doc |
| `development-roadmap.md` | Mixed | Milestones tagged shipped vs future |
| `product-requirements.md` | **[Shipped]** | Scope + strict verify requirements |
| `error-model.md` | **[Shipped]** | Error categories and exit codes |
| `gui-application.md` | **[Shipped]** | PySide6 spec; provenance UI; Start/Pause/Stop transport |
| `gui-visual-design.md` | **[Shipped]** | Theme tokens, QSS architecture, widget plan |
| `gui-operator-workflows.md` | **[Shipped]** | Operator flows + verify review |
| `gui-build-prerequisites.md` | **[Shipped]** | Checklist (GUI-0–7 complete) |
| `gui-windows-scheduler.md` | **[Shipped]** | Headless `run-due-schedules` |
| `adr/0001-tech-stack.md` | **[Shipped]** | Stack + `mtg_card_recognition` |
| `README.md` (this folder) | **[Shipped]** | Doc map + tag legend pointer |
| `packages/mtg-card-recognition/README.md` | Mixed | Shipped API; future standalone repo |
| `open-items-status.md` | **[Shipped]** | P1–P4 tracker, reanalyze checklist, deferred backlog |

## Intentionally not “final” (by design)

These remain accurate but tagged **[Future]** where noted in source docs:

- PaddleOCR backend
- Milo / CollectorVision external catalog evaluation
- `VERIFY_*` threshold calibration on labeled eBay crops
- Alembic migrations (interim: `ensure-db-indexes`)
- Condition-aware Cardmarket pricing
- Labeled regression dataset in CI
- Post-reanalyze operational metrics — see `open-items-status.md` (updated after each full reanalyze)

Last full doc sync: 2026-06-08 (branch `main`).

## Code map (for doc authors)

| Concern | Location |
|---------|----------|
| Recognition library | `src/mtg_card_recognition/` |
| eBay adapter | `src/ebay_workflows/adapters/recognition_settings.py` |
| Service shims | `src/ebay_workflows/services/{image_evidence,card_zones,…}.py` |
| Strict gate | `mtg_card_recognition.evidence` |
| GUI provenance | `gui/listing_detail.py`, `gui/match_widgets.py` |
| Export provenance | `services/ranked_export.py` |
| Open items tracker | `docs/open-items-status.md` |
