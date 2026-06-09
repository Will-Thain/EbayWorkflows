# EbayWorkflows Documentation

This repository will host a local CLI application that evaluates MTG eBay listings by combining listing data, image analysis, and market pricing into ranked opportunities.

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

All docs in this folder use **[Shipped]**, **[Historical]**, and **[Future]** tags where behavior may differ from older text. See `documentation-status.md` for the full index before trusting older paragraphs.

## Document Map

- `documentation-status.md` - shipped vs historical vs future labels; canonical doc index
- `post-workflow-checklist.md` - after pipeline run: validation, config restructure, documentation updates
- `open-items-status.md` - P1–P4 backlog and pipeline snapshots
- `product-requirements.md` - scope, users, objectives, constraints
- `workflow-phases.md` - phase-by-phase behavior and acceptance criteria
- `architecture.md` - component design for CLI, services, and workers
- `data-model.md` - PostgreSQL schema design and indexing strategy
- `integration-specs.md` - eBay, Scryfall, and Cardmarket integration details
- `library-stack.md` - recommended CV/OCR/embedding/vector-search libraries
- `card-recognition-architecture.md` - pointer to **mtg-card-recognition** `docs/architecture.md`
- `ranking-and-confidence.md` - EV, risk, and confidence model definitions
- `development-roadmap.md` - milestones, testing strategy, and delivery order
- `implementation-spec.md` - concrete MVP build order and module plan
- `config-contract.md` - environment variable schema and validation rules
- `error-model.md` - retry, failure, and CLI exit-code strategy
- `testing-strategy.md` - fixtures, integration tests, and quality gates
- `runbook-local.md` - local setup and operational troubleshooting
- `large-scale-ingest.md` - high-volume eBay ingest, capacity limits, and production scripts
- `future-pain-points.md` - known limits, recommended fixes, and implementation status
- `gui-application.md` - local desktop app spec (PySide6 / Qt 6; workflows, monitor, DB browse, match preview)
- `gui-build-prerequisites.md` - pre-build checklist and locked defaults
- `gui-operator-workflows.md` - example operator day-in-the-life flows
- `gui-windows-scheduler.md` - Windows Task Scheduler for headless `run-due-schedules`
- `data-dictionary.md` - field-level semantics and provenance definitions
- `docs/adr/0001-tech-stack.md` - initial architecture decision record
- Panel v2 ADRs: [`../mtg-card-recognition/docs/adr/`](../mtg-card-recognition/docs/adr/) (`0003-proposal-cascade-flow`, `0003-eval-brief`, `0003-expert-review-v3`)

## Working Principles

- Keep all business logic deterministic and reproducible.
- Prefer idempotent workflow steps so phases can be re-run safely.
- Record provenance for every derived field (source API, OCR, heuristic, model).
- Preserve raw source payloads where legally allowed for audit/debug.
- Keep security and secret-handling constraints explicit and centralized.

