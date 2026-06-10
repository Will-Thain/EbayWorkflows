# EbayWorkflows Documentation

This repository hosts a local CLI application that evaluates MTG eBay listings by combining listing data, image analysis, and market pricing into ranked opportunities.

## Purpose

The docs in this folder define:

- product goals and non-goals
- end-to-end workflow and phase breakdown
- system architecture and module boundaries
- PostgreSQL schema and data lifecycle
- external API integration contracts
- confidence/EV scoring strategy
- development roadmap and quality gates

## Documentation status labels

All docs use **[Shipped]**, **[Historical]**, and **[Future]** tags where behavior may differ from older text. See `documentation-status.md` for the full index before trusting older paragraphs.

## Document Map

- `documentation-status.md` — shipped vs historical vs future labels; canonical doc index
- `contributing-docs.md` — **code change → doc to edit** (maintainers)
- `trust-invariants.md` — verification policy summary (non-negotiable rules)
- `post-workflow-checklist.md` — after pipeline run: validation, config, documentation updates
- `open-items-status.md` — P1–P4 backlog
- `product-requirements.md` — scope, users, objectives, constraints
- `workflow-phases.md` — phase-by-phase behavior and acceptance criteria
- `architecture.md` — component design, module boundaries, mermaid diagrams
- `card-recognition-architecture.md` — library vs consumer split (v0.3.2), Phase 5 wiring
- `adr/0002-package-restructure.md` — package layout (M1–M7 complete)
- `expert-panel/reviews/ebay-restructure-v1.md` — panel review of restructure plan
- `expert-panel/reviews/documentation-audit-v1.md` — documentation accuracy review
- `data-model.md` — PostgreSQL schema, Alembic, repositories
- `integration-specs.md` — eBay, Scryfall, Cardmarket contracts + CV boundary
- `library-stack.md` — propose/confirm stack; library vs consumer roles; version pin
- `ranking-and-confidence.md` — EV, risk, and confidence model definitions
- `development-roadmap.md` — milestones and delivery order
- `implementation-spec.md` — canonical module layout
- `config-contract.md` — environment variable schema and validation rules
- `error-model.md` — retry, failure, and CLI exit-code strategy
- `testing-strategy.md` — fixtures, integration tests, and quality gates
- `runbook-local.md` — local setup and operational troubleshooting
- `large-scale-ingest.md` — high-volume eBay ingest, capacity limits, and production scripts
- `future-cv-ocr.md` — PaddleOCR / Milo / labeled-crop roadmap **[Future]**
- `future-pain-points.md` — known limits, recommended fixes, and implementation status
- `gui-application.md` — local desktop app spec (PySide6 / Qt 6)
- `gui-build-prerequisites.md` — pre-build checklist and locked defaults
- `gui-operator-workflows.md` — example operator day-in-the-life flows
- `gui-windows-scheduler.md` — Windows Task Scheduler for headless `run-due-schedules`
- `data-dictionary.md` — field-level semantics and provenance definitions
- `adr/0001-tech-stack.md` — initial architecture decision record
- Panel v2 ADRs (sibling): [`../mtg-card-recognition/docs/adr/`](../mtg-card-recognition/docs/adr/)

## Working Principles

- Keep all business logic deterministic and reproducible.
- Prefer idempotent workflow steps so phases can be re-run safely.
- Record provenance for every derived field (source API, OCR, heuristic, model).
- Preserve raw source payloads where legally allowed for audit/debug.
- Keep security and secret-handling constraints explicit and centralized.

## Maintainer hygiene

After package or phase changes:

```powershell
rg "services/|workflow_phase|TEMP shim" docs/
.venv\Scripts\python.exe -m pytest -q tests/test_import_boundaries.py
```

See `contributing-docs.md` for the full doc map.
