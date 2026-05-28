# Workflow Phases

This document defines the first six workflow phases and expected behavior.

## End-to-End Flow

eBay Browse API
-> Search MTG listings
-> Store listing metadata + image URLs
-> Download/cache images
-> Detect card regions
-> OCR title/collector number/set code
-> Match to Scryfall data
-> Join to Cardmarket pricing
-> Calculate EV + confidence
-> Rank listings

## Phase 1: eBay Search + Image Download + Local DB

### Inputs

- search queries (keywords/category/filter set)
- run window and pagination options

### Outputs

- persisted listing records
- persisted image records + local cache references
- run-level audit and step status

### Acceptance Criteria

- listings are deduplicated on stable listing ID
- images are stored/cached with content hash when available
- failures are retried and recorded without crashing full run

## Phase 2: Title-Based Scryfall Matching

### Inputs

- listing title
- optional subtitle/description fields (if available)
- Scryfall card/bulk reference dataset

### Outputs

- candidate card matches with normalized name score
- best-match card ID and confidence baseline

### Acceptance Criteria

- matching is deterministic for identical input datasets
- ambiguous cases retain top-N candidates for later reconciliation

## Phase 3: Cardmarket Price Join

### Inputs

- matched card identifiers
- Cardmarket pricing dataset/API response

### Outputs

- normalized price fields (currency, timestamp, condition if available)
- price-source provenance metadata

### Acceptance Criteria

- each joined price record indicates source currency and conversion method
- stale/missing prices flagged instead of silently defaulting

## Phase 4: Simple EV Ranking

### Inputs

- listing total cost (price + shipping + optional fees)
- joined market prices
- match confidence indicators

### Outputs

- per-listing EV estimate
- ranking table by EV and confidence-adjusted EV

### Acceptance Criteria

- ranking supports deterministic tie-break rules
- formulas are documented and versioned

## Phase 5: OCR/Image Recognition Verification

### Inputs

- cached listing images
- detected card regions/crops

### Outputs

- OCR text candidates (title, set code, collector number)
- OpenCLIP + FAISS image candidates for each card crop
- image-derived evidence that can override title-only assumptions

### Acceptance Criteria

- OCR evidence is linked to image and region coordinates
- embedding candidates are persisted with model/index version metadata
- confidence model is updated using OCR corroboration/contradiction

## Phase 6: Bulk-Lot Multi-Card Detection

### Inputs

- lot listing images containing multiple cards

### Outputs

- set of detected card entities per listing image
- aggregated lot EV estimate across detected cards

### Acceptance Criteria

- multi-card detections are represented individually and aggregately
- detector model version and per-region confidence are persisted
- false-positive controls are applied before EV amplification

## Cross-Phase Rules

- every phase writes step-level status (`pending`, `running`, `succeeded`, `failed`)
- every derived field stores provenance and algorithm/model version
- reruns can start at phase boundaries without corrupting prior outputs

