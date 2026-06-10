# Development Roadmap

**Status:** Milestones 0–7 **[Shipped]**. Tags: `documentation-status.md`.

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

## Milestone 4: Phase 5 OCR Verification **[Shipped]**

- OpenCV preprocessing, card alignment, zone strips
- Tesseract zone OCR **[Shipped]**; PaddleOCR **[Future]**
- OpenCLIP embedding + FAISS retrieval; optional `FAISS_PROPOSE_CANDIDATES`
- **`mtg_card_recognition` strict consensus gate** — OCR/FAISS/mana never alone verify
- provenance attach (`verification_*` fields); per-listing single verified winner

Exit criteria:
- verified listings require set+collector + name/symbol consensus; pricing guardrails enforce sources

## Milestone 5: Phase 6 Bulk-Lot Detection **[Shipped]**

- OpenCV multi-card detection (contour-based; YOLO **[Future]**)
- lot-level aggregation; `crop_match_allowed_for_pricing` under strict gate
- false-positive suppression via detection score and min lot count

Exit criteria:
- bulk listings produce multi-card candidate sets with lot EV when crop evidence verifies

## Milestone 6: Desktop GUI (PySide6) **[Shipped]**

- Qt 6 main window: Home, Opportunities, Workflows, Database
- favourites and ranked listing preview with cached images
- verification provenance in match detail; proof detection highlight on image overlay
- `QProcess` start/stop for CLI phases; schedule editor + `run-due-schedules`

Exit criteria:
- operator can review top listings, audit verification proof, and manage favourites without CLI
- operator can start/stop phases and see logs in-app

See `gui-application.md` and `gui-build-prerequisites.md`.

## Milestone 7: Recognition package extraction **[Shipped]** (standalone repo ready)

- **`mtg-card-recognition`** — sibling repo [`../mtg-card-recognition`](https://github.com/Will-Thain/mtg-card-recognition) (v0.2.0+), FAISS core extracted
- eBay shims + `RecognitionSettings` adapter remain in EbayWorkflows
- Dev install: `scripts/install-dev.ps1` (editable sibling clone, not a pyproject path dep)
- Remote: https://github.com/Will-Thain/mtg-card-recognition

Exit criteria:
- tests pass against package imports; push to remote per mtg-card-recognition README **[Ready]**

## Testing Strategy

- unit tests for matching/scoring math
- integration tests for connectors with recorded fixtures
- DB migration tests for schema integrity
- workflow replay tests for idempotent reruns
- evaluation set tests for OCR-only vs embedding-only vs hybrid matching
- matching evaluation on post-consensus reanalyze (verified counts, EV sanity) **[Future]** validation pass — gate **[Shipped]** per `card-recognition-architecture.md`
- PaddleOCR zones, Milo embedder, threshold calibration dataset **[Future]**

## Operational Checklist

- environment variable contract documented
- sample `.env.example` without real secrets
- structured logging enabled
- SQL indexes validated for query patterns
- backup/restore plan for PostgreSQL and image cache

