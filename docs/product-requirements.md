# Product Requirements

**Status:** Core scope **[Shipped]**; labeled regression dataset and condition-aware pricing **[Future]**. Tags: `documentation-status.md`.

## Problem Statement

MTG buyers and resellers need a repeatable way to evaluate eBay listings (single-card and bulk lots) against market prices. Manual review is slow and inconsistent, especially when listing titles are noisy and images are low quality.

## Product Goal

Build a local CLI + PostgreSQL workflow engine that:

1. ingests eBay listings and listing images,
2. identifies cards from listing content and images,
3. maps cards to trusted catalog/pricing datasets (Scryfall + Cardmarket),
4. computes expected value (EV) with confidence,
5. outputs ranked opportunities for operator review.

## Intended Users

- Individual card arbitrage traders
- Small MTG storefront operators
- Data-savvy hobbyists running local workflows

## Success Criteria

- Can run workflows end-to-end on a local machine with restart safety.
- Produces ranked output with transparent EV and confidence calculations.
- Supports both single-card listings and bulk-lot listings.
- Can reprocess historical listings as OCR or matching improves.
- Image verification uses a **strict consensus gate** (set+collector + name/symbol); at most one verified printing per listing drives pricing/EV.
- Verification **provenance** (image, detection, crop path) is persisted and visible in GUI/export.

## Scope

### In Scope (Initial Program)

- CLI-driven workflow orchestration
- local desktop GUI (PySide6) for review, favourites, and workflow control (see `gui-application.md`)
- Local PostgreSQL persistence
- eBay listing metadata + image URL ingestion
- local image caching and processing pipeline
- hybrid title/OCR/embedding-driven Scryfall matching via `mtg_card_recognition` library
- Cardmarket bulk-price-file joins
- EV and confidence scoring
- ranking output for operator decision making

### Out of Scope (Initial Program)

- hosted multi-user web UI (see `gui-application.md` for a proposed **local desktop** read-only app)
- automatic buy actions
- payment/account automation
- non-MTG domains

## Constraints

- Must run on local workstation.
- Must avoid embedding credentials or secrets in code/repo.
- Must support resumable workflow execution and partial reruns.
- Must maintain data lineage for debugging and trust.

## Non-Functional Requirements

- **Reliability:** workflow retries, idempotency, and resumability
- **Performance:** batch-oriented processing with checkpointing
- **Observability:** structured logs + per-step status records
- **Security:** environment-based secret handling, least-privilege DB access
- **Extensibility:** pluggable step implementations for future models/APIs

