# ADR 0001: Initial Tech Stack

## Status

Accepted (updated 2026-06-08 for `mtg_card_recognition` extraction and strict verification gate)

## Context

The project requires a local-first workflow CLI with PostgreSQL persistence, image-assisted card matching, and strict integration safety controls.

## Decision

- use a local CLI architecture with phase-based workflow execution
- use PostgreSQL for workflow and artifact persistence
- extract card recognition into **`mtg_card_recognition`** (zones, OCR, embeddings, evidence gate); eBay app uses adapter + shims
- use OpenCV for preprocessing and region operations **[Shipped]**
- use OpenCLIP + FAISS for image candidate retrieval **[Shipped]**
- use **Tesseract** (`pytesseract`) for zone OCR **[Shipped]**; PaddleOCR as optional future backend **[Future]**
- use RapidFuzz for deterministic text-level disambiguation **[Shipped]**
- use Cardmarket downloadable bulk pricing files instead of Cardmarket API access **[Shipped]**
- strict verification gate: OCR/FAISS/mana never alone verify; provenance on attach **[Shipped]**

## API Safety and Permission Constraints

- all provider calls go through shared rate-limit middleware
- each provider has explicit max request budget configured in environment
- only officially supported/authorized API endpoints are permitted
- endpoint/scope policy checks run at startup and before live calls
- permission violations fail fast and are treated as non-retryable

## Consequences

- hybrid matching improves robustness vs vision-only matching
- extractable recognition library enables future standalone repo without duplicating gate logic
- strict verify gate reduces false pricing bypass vs historical OR-gate
- implementation complexity is higher but yields explainable confidence

## Revisit Triggers

- provider policy changes
- significant dataset scale increase requiring indexing changes (IVF/PQ, Milo catalog)
- material drift in OCR or embedding retrieval quality — calibrate `VERIFY_*` on labeled crops
- PaddleOCR adoption if Tesseract accuracy insufficient on eBay crops

## Related

- `card-recognition-architecture.md` — shipped verification spec
- `documentation-status.md` — Shipped / Historical / Future tags
