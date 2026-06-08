# Data Model (PostgreSQL)

**Status:** Schema **[Shipped]**; Alembic migrations **[Future]** (use `ensure-db-indexes` interim). Verification fields in `evidence_json` match `data-dictionary.md`. Tags: `documentation-status.md`.

This schema is optimized for workflow traceability, deterministic reruns, and scalable listing enrichment.

## Core Tables

## `workflow_runs`

- `id` (uuid, pk)
- `workflow_name` (text)
- `requested_by` (text, nullable)
- `input_config_json` (jsonb)
- `status` (text: pending/running/succeeded/failed/cancelled)
- `started_at` (timestamptz)
- `finished_at` (timestamptz, nullable)
- `created_at` (timestamptz default now)

## `workflow_steps`

- `id` (uuid, pk)
- `run_id` (uuid, fk -> workflow_runs.id)
- `step_name` (text)
- `phase_number` (int)
- `status` (text)
- `attempt` (int default 1)
- `metrics_json` (jsonb, nullable)
- `error_json` (jsonb, nullable)
- `started_at` (timestamptz)
- `finished_at` (timestamptz, nullable)

Unique key:
- (`run_id`, `step_name`, `attempt`)

## `listings`

- `id` (uuid, pk)
- `source` (text, default 'ebay')
- `external_listing_id` (text, unique)
- `title` (text)
- `subtitle` (text, nullable)
- `listing_url` (text)
- `currency` (text)
- `price_amount` (numeric(12,2))
- `shipping_amount` (numeric(12,2), nullable)
- `condition_text` (text, nullable)
- `seller_name` (text, nullable)
- `raw_payload_json` (jsonb)
- `first_seen_at` (timestamptz)
- `last_seen_at` (timestamptz)
- `created_at` (timestamptz default now)
- `updated_at` (timestamptz default now)

Indexes:
- unique (`external_listing_id`)
- btree (`last_seen_at`)
- gin (`raw_payload_json`)

## `listing_images`

- `id` (uuid, pk)
- `listing_id` (uuid, fk -> listings.id)
- `source_url` (text)
- `local_path` (text, nullable)
- `content_hash` (text, nullable)
- `width_px` (int, nullable)
- `height_px` (int, nullable)
- `download_status` (text)
- `downloaded_at` (timestamptz, nullable)
- `error_json` (jsonb, nullable)

Unique key:
- (`listing_id`, `source_url`)

## Matching and Evidence Tables

## `listing_card_candidates`

- `id` (uuid, pk)
- `listing_id` (uuid, fk -> listings.id)
- `source_method` (text: `title_match` / `ocr_match` / `image_model` / `faiss_proposal` / lot crop methods)
- `scryfall_id` (uuid, nullable)
- `name_candidate` (text, nullable)
- `set_code_candidate` (text, nullable)
- `collector_number_candidate` (text, nullable)
- `match_score` (numeric(5,4))
- `confidence_score` (numeric(5,4))
- `rank_position` (int)
- `evidence_json` (jsonb) — see `data-dictionary.md` for verification and pricing fields

### `evidence_json` — verification (Phase 5) **[Shipped]**

Written by `mtg_card_recognition.evidence` attach logic. Key fields:

| Field | Type | Notes |
|-------|------|-------|
| `image_verified` | bool | Strict gate passed; at most one `true` per listing after Phase 5 |
| `image_verification_source` | text | `set_collector` or `set_symbol` when verified |
| `pricing_eligible` | bool | Phase 3 may attach Cardmarket price |
| `pricing_reject_reason` | text | e.g. `superseded_by_listing_winner` |
| `verification_listing_image_id` | uuid | Proving listing image |
| `verification_detection_id` | uuid | FK to `image_detections.id` |
| `verification_region_path` | text | Local proof crop path |
| `zone_evidence` | object | Zone OCR, symbol, mana, `zones_available` |

Historical OR-gate values (OCR/FAISS/mana as `image_verification_source`) are **[Historical]** — do not restore.
- `embedding_model` (text, nullable)
- `embedding_similarity` (numeric(7,6), nullable)
- `vector_index_version` (text, nullable)
- `created_at` (timestamptz default now)

Indexes:
- btree (`listing_id`, `rank_position`)
- btree (`scryfall_id`)

## `image_detections`

- `id` (uuid, pk)
- `listing_image_id` (uuid, fk -> listing_images.id)
- `detection_type` (text: card_region/text_region/lot_card)
- `bbox_x` (numeric(10,4))
- `bbox_y` (numeric(10,4))
- `bbox_w` (numeric(10,4))
- `bbox_h` (numeric(10,4))
- `detection_score` (numeric(5,4))
- `model_version` (text)
- `created_at` (timestamptz default now)

## `ocr_results`

- `id` (uuid, pk)
- `detection_id` (uuid, fk -> image_detections.id)
- `field_type` (text: title/set_code/collector_number/other)
- `raw_text` (text)
- `normalized_text` (text, nullable)
- `confidence_score` (numeric(5,4))
- `engine_name` (text)
- `engine_version` (text)
- `region_image_path` (text, nullable)
- `created_at` (timestamptz default now)

## Pricing and Scoring Tables

## `card_prices`

- `id` (uuid, pk)
- `source` (text, default 'cardmarket')
- `scryfall_id` (uuid)
- `currency` (text)
- `price_type` (text: trend/low/sell/avg)
- `condition` (text, nullable)
- `language` (text, nullable)
- `price_amount` (numeric(12,4))
- `price_timestamp` (timestamptz)
- `raw_payload_json` (jsonb)
- `created_at` (timestamptz default now)

Indexes:
- btree (`scryfall_id`, `price_timestamp`)

## `listing_scores`

- `id` (uuid, pk)
- `listing_id` (uuid, fk -> listings.id, unique)
- `ev_raw` (numeric(12,4))
- `ev_adjusted` (numeric(12,4))
- `confidence_score` (numeric(5,4))
- `risk_score` (numeric(5,4))
- `rank_value` (numeric(12,4))
- `scoring_version` (text)
- `explanation_json` (jsonb)
- `updated_at` (timestamptz default now)

## `listing_favorites` (GUI operator metadata)

- `listing_id` (uuid, pk, fk -> listings.id, on delete cascade)
- `note` (text, nullable)
- `favorited_at` (timestamptz default now)

Single-operator local use: one favourite row per listing. Used by the desktop app for starred listings and “favourites only” filters.

## `scheduled_jobs` (GUI / scheduler automation)

- `id` (uuid, pk)
- `name` (text) — operator label, e.g. “Nightly ingest”
- `job_id` (text) — key into workflow catalog (`phase1`, `phase4`, `pipeline`, …)
- `job_params_json` (jsonb) — CLI args snapshot (query, max_pages, flags)
- `schedule_type` (text: `interval` | `daily` | `once`)
- `interval_hours` (numeric, nullable) — for `interval`, e.g. 24
- `daily_at` (time, nullable) — local wall-clock time for `daily`
- `run_at` (timestamptz, nullable) — for `once`
- `timezone` (text, default operator TZ or `UTC`)
- `enabled` (boolean, default true)
- `catch_up_missed` (boolean, default false)
- `next_run_at` (timestamptz, nullable)
- `last_run_at` (timestamptz, nullable)
- `last_run_status` (text, nullable: succeeded | failed | skipped_overlap | skipped_disabled)
- `last_error` (text, nullable)
- `created_at` / `updated_at` (timestamptz)

Indexes:
- btree (`enabled`, `next_run_at`) for due-job queries

## Data Retention and Lifecycle

- keep raw integration payloads for reproducibility where allowed
- permit periodic compaction of image artifacts not referenced by active analyses
- store scoring and model versions for backtesting and comparisons

