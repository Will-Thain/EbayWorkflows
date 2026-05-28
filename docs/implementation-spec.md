# Implementation Specification (MVP)

## Objective

Translate the roadmap into a concrete implementation order that yields a runnable CLI quickly while enforcing API safety, rate-limit controls, and permission boundaries.

## MVP Scope

- local CLI workflow runner
- PostgreSQL-backed persistence
- Phase 1 ingestion (eBay search + listing/image persistence + image cache download)
- Phase 2 title/OCR-assisted candidate matching baseline
- Phase 3 pricing join baseline
- Phase 4 initial EV and confidence ranking output

## Module Layout (Proposed)

- `src/cli/` command handlers and output formatters
- `src/config/` env parsing, validation, and defaults
- `src/workflows/` run coordinator and phase executor contracts
- `src/integrations/` provider clients (`ebay`, `scryfall`, `cardmarket`)
- `src/image/` preprocessing, download, OCR orchestration
- `src/matching/` RapidFuzz and embedding candidate logic
- `src/scoring/` EV/confidence/ranking calculators
- `src/db/` migrations and repositories
- `src/common/` logging, errors, utility helpers

## Build Order

1. bootstrap project and config system
2. add DB migrations for run/step/listing/image tables
3. implement workflow runner skeleton with step checkpoints
4. implement eBay connector with safe pagination and retries
5. implement image downloader/cache with dedupe and retry
6. add Scryfall dataset sync and title matcher
7. add Cardmarket bulk-file pricing join adapter
8. implement scoring and ranking output command

## API Safety Requirements (Mandatory)

- all provider requests must pass through a shared rate-limit guard
- retries must respect provider policy and include exponential backoff + jitter
- no endpoint should be queried without explicit permission in provider terms
- no scraping of restricted endpoints; use official APIs and allowed datasets only
- per-provider request logs must capture endpoint, status, remaining budget fields when available
- for Cardmarket, use permitted downloadable bulk files and validate file provenance/checksum

## Permission and Compliance Guardrails

- keep provider credentials in environment variables only
- assign least-privilege API scopes; do not request unused scopes
- block startup if required live-API credentials/scopes are missing or invalid
- store terms/policy references in connector docs and code comments where needed
- expose a `--dry-run` mode for integration validation without full ingest volume

## Definition of Done (MVP)

- single CLI command runs phases 1-4 against configured query
- run status and errors are persisted and resumable
- output includes ranked listings with explainable EV/confidence components
- API calls remain within configured limits and compliance controls

