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

## Document Map

- `product-requirements.md` - scope, users, objectives, constraints
- `workflow-phases.md` - phase-by-phase behavior and acceptance criteria
- `architecture.md` - component design for CLI, services, and workers
- `data-model.md` - PostgreSQL schema design and indexing strategy
- `integration-specs.md` - eBay, Scryfall, and Cardmarket integration details
- `library-stack.md` - recommended CV/OCR/embedding/vector-search libraries
- `ranking-and-confidence.md` - EV, risk, and confidence model definitions
- `development-roadmap.md` - milestones, testing strategy, and delivery order
- `implementation-spec.md` - concrete MVP build order and module plan
- `config-contract.md` - environment variable schema and validation rules
- `error-model.md` - retry, failure, and CLI exit-code strategy
- `testing-strategy.md` - fixtures, integration tests, and quality gates
- `runbook-local.md` - local setup and operational troubleshooting
- `gui-application.md` - local desktop app spec (PySide6 / Qt 6; workflows, monitor, DB browse, match preview)
- `gui-build-prerequisites.md` - pre-build checklist and locked defaults
- `gui-operator-workflows.md` - example operator day-in-the-life flows
- `gui-windows-scheduler.md` - Windows Task Scheduler for headless `run-due-schedules`
- `data-dictionary.md` - field-level semantics and provenance definitions
- `docs/adr/0001-tech-stack.md` - initial architecture decision record

## Working Principles

- Keep all business logic deterministic and reproducible.
- Prefer idempotent workflow steps so phases can be re-run safely.
- Record provenance for every derived field (source API, OCR, heuristic, model).
- Preserve raw source payloads where legally allowed for audit/debug.
- Keep security and secret-handling constraints explicit and centralized.

