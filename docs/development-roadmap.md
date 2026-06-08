# Development Roadmap

## Delivery Strategy

Implement in thin vertical slices so every milestone is runnable and testable from the CLI.

## Milestone 0: Foundation

- choose runtime/language for CLI app
- initialize project structure and config loading
- add migration system and PostgreSQL connection layer
- define workflow run/step primitives

Exit criteria:
- CLI command can create and complete a dummy workflow run in DB

## Milestone 1: Phase 1 End-to-End

- eBay search connector
- listing/image persistence
- local image download cache
- step status and retries

Exit criteria:
- real listings + image records stored from configurable query

## Milestone 2: Phase 2 + 3 Data Enrichment

- Scryfall bulk ingestion and local matcher
- Cardmarket bulk price-file ingestion and join
- candidate + pricing persistence
- title-based RapidFuzz disambiguation baseline

Exit criteria:
- each ingested listing has card candidate rows and joined price rows

## Milestone 3: Phase 4 Scoring

- EV calculator
- confidence baseline
- ranked output command (table + JSON export)

Exit criteria:
- ranked result set produced for a run

## Milestone 4: Phase 5 OCR Verification

- OpenCV preprocessing and card crop normalization
- OCR extraction pipeline (`PaddleOCR` primary, `Tesseract` fallback)
- OpenCLIP embedding generation + FAISS top-K candidate retrieval
- confidence recalibration from image evidence

Exit criteria:
- OCR and image retrieval evidence improve or downgrade confidence predictably

## Milestone 5: Phase 6 Bulk-Lot Detection

- multi-card detection flow (`YOLOv8` or equivalent detector)
- lot-level aggregation logic
- false-positive suppression

Exit criteria:
- bulk listings produce multi-card candidate sets with EV estimate

## Milestone 6: Desktop GUI (PySide6)

- Qt 6 main window with Opportunities, Workflows, and Database tabs
- favourites and ranked listing preview with cached images
- `QProcess` start/stop for CLI phases; schedule editor + `run-due-schedules`

Exit criteria:
- operator can review top listings and manage favourites without CLI
- operator can start/stop phase 2–4 and see logs in-app

See `gui-application.md` and `gui-build-prerequisites.md`.

## Testing Strategy

- unit tests for matching/scoring math
- integration tests for connectors with recorded fixtures
- DB migration tests for schema integrity
- workflow replay tests for idempotent reruns
- evaluation set tests for OCR-only vs embedding-only vs hybrid matching
- P0 matching fixes (single-winner EV, reprint-safe verify, set-only bug) then consensus gate per approved spec (`card-recognition-architecture.md`)

## Operational Checklist

- environment variable contract documented
- sample `.env.example` without real secrets
- structured logging enabled
- SQL indexes validated for query patterns
- backup/restore plan for PostgreSQL and image cache

