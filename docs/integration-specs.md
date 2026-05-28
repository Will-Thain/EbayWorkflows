# Integration Specifications

## eBay Integration (Phase 1)

## Goal

Retrieve MTG listings and image URLs using eBay APIs with predictable pagination and deduplication.

## Required Inputs

- API credentials (environment variables)
- search query config (keywords, category, condition filters, price bounds)
- pagination and rate-limit settings

## Expected Fields

- listing identifier
- title and URL
- current price and shipping
- condition/seller information if exposed
- primary and additional image URLs
- raw payload capture

## Behavior Requirements

- enforce rate-limit aware request pacing
- retry transient HTTP failures
- record request/response metadata for traceability
- deduplicate by stable external listing ID

## Scryfall Integration (Phase 2)

## Goal

Map listing candidates to canonical MTG card entities.

## Data Strategy

- use Scryfall bulk data snapshot for deterministic local matching
- optionally use card API endpoints for targeted refreshes

## Matching Inputs

- normalized title text
- optional OCR title, set code, collector number

## Matching Outputs

- best candidate `scryfall_id`
- ranked alternatives
- similarity and confidence components

## Cardmarket Integration (Phase 3)

## Goal

Attach market pricing suitable for EV calculations.

## Behavior Requirements

- ingest pricing from downloaded Cardmarket bulk data files (no direct API dependency)
- normalize currencies to configured base currency
- attach price timestamps and source metadata
- preserve condition/language qualifiers where available
- handle missing/stale data explicitly

## Cross-Integration Concerns

- centralized HTTP client with retries, timeout, and backoff
- strict schema validation for external payload parsing
- no secrets in source control or logs
- track connector versioning for reproducibility

## Rate-Limit and Permission Policy

- use token-bucket or leaky-bucket limiting per provider plus a global cap
- honor provider headers (for example `Retry-After`) before retrying
- do not exceed published quotas even if local limit configuration is higher
- allow requests only to documented and authorized endpoints
- map credentials to least-privilege scopes required for eBay and any other live APIs
- block execution when policy checks fail or endpoint access is not explicitly allowed

## Cardmarket Bulk Data Policy

- obtain files only from permitted Cardmarket export/download channels
- record file source, download timestamp, and checksum for provenance
- do not assume API credential availability for Cardmarket pricing
- validate schema and reject malformed bulk files before price joins

## CV/OCR/Matching Components (Phases 5-6)

## Recommended Libraries

- `opencv-python` for preprocessing and card crop normalization
- `open-clip-torch` for image embedding generation
- `faiss-cpu`/`faiss-gpu` for nearest-neighbor candidate retrieval
- `paddleocr` (primary) with `pytesseract` fallback
- `rapidfuzz` for deterministic title/set reconciliation

## Functional Requirements

- persist embedding model version and FAISS index version per match
- store OCR engine/version and field-level confidence
- keep top-K candidate list before final disambiguation
- support hybrid final scoring (embedding similarity + OCR + text matching)

