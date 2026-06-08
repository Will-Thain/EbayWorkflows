# Data Dictionary

## Purpose

Provide clear semantic definitions for key persisted fields and provenance requirements. Verification fields reflect **[Shipped]** consensus gate behavior; legacy OR-gate values are **[Historical]** — see `documentation-status.md`.

## Listings

- `external_listing_id`: provider-stable listing identifier used for deduplication
- `price_amount`: listing item price excluding shipping
- `shipping_amount`: shipping cost estimate from provider payload
- `raw_payload_json`: raw listing response for audit/debug (with secret redaction)

## Listing Images

- `source_url`: provider-reported image URL
- `local_path`: local cache path to downloaded image
- `content_hash`: hash used for dedupe and cache integrity
- `download_status`: lifecycle state (`pending`, `succeeded`, `failed`)

## Candidate Matching

- `source_method`: origin of candidate (`title_match`, `faiss_proposal`, …)
- `match_score`: normalized matching score for candidate ordering
- `confidence_score`: confidence assigned to candidate
- `rank_position`: Phase 2 ordering (1 = best title match)
- `evidence_json`: structured trace of signals used to build candidate (see below)

### `evidence_json` — image verification (Phase 5)

Set by `mtg_card_recognition.evidence` and Phase 5 attach logic:

| Field | Type | Meaning |
|-------|------|---------|
| `image_verified` | bool | Strict gate passed for this printing (at most one `true` per listing after Phase 5) |
| `image_verification_source` | string \| null | `set_collector` or `set_symbol` when verified; null when gated |
| `pricing_eligible` | bool | Whether Phase 3 may attach Cardmarket price |
| `pricing_reject_reason` | string \| null | e.g. `no_image_reference`, `superseded_by_listing_winner` |
| `verification_listing_image_id` | string (uuid) | Listing image that supplied the proving region |
| `verification_detection_id` | string (uuid) | `image_detections.id` for the card_region row |
| `verification_region_path` | string | Local path to the crop used as proof |
| `zone_evidence` | object | Zone OCR, symbol, mana, `zones_available`, nested `listing_image_id` / `detection_id` |
| `ocr_verification` | object | `ocr_title`, `similarity`, optional provenance sub-fields |
| `faiss_matches` | array | Top-K FAISS hits (corroboration; does not alone verify) |
| `faiss_score` | float | Score for this candidate's ID in region matches |
| `cardmarket_price` | object | Attached in Phase 3 when allowed |
| `cardmarket_price_rejected` | object | Reason price was dropped or superseded |

Legacy / supporting fields may include `embedding_agreement`, `method`, `parsed_identifiers` (Phase 6 crops).

## OCR and Detection

- `detection_type`: detection class (`card_region`, `text_region`, `lot_card`)
- `detection_score`: detector confidence for region
- `raw_text`: unmodified OCR output
- `normalized_text`: cleaned OCR text used for matching
- `engine_name`/`engine_version`: OCR engine provenance
- `region_image_path`: optional path to stored crop used by OCR

## Scoring

- `ev_raw`: unadjusted expected value
- `confidence_score`: final blended confidence value
- `risk_score`: inverse confidence or configured risk metric
- `ev_adjusted`: risk-adjusted expected value used for ranking
- `rank_value`: final ranking score
- `scoring_version`: scoring formula/config version
- `explanation_json`: structured explanation payload for auditability

## Listing Favourites (GUI)

- `listing_id`: favourited listing (one row per listing)
- `note`: optional operator comment (short text)
- `favorited_at`: when the star was set

## Scheduled Jobs (GUI / automation)

- `name`: operator label for the schedule
- `job_id`: workflow catalog key (`phase1`, `phase4`, …)
- `job_params_json`: CLI parameters snapshot (query, max_pages, flags)
- `schedule_type`: `interval`, `daily`, or `once`
- `interval_hours`: hours between runs (interval type)
- `daily_at`: wall-clock time for daily runs
- `run_at`: absolute timestamp for one-shot runs
- `timezone`: IANA timezone name for daily/once display
- `enabled`: whether the schedule is active
- `catch_up_missed`: run once after downtime if true; otherwise skip missed windows
- `next_run_at` / `last_run_at`: scheduler bookkeeping (UTC)
- `last_run_status`: `succeeded`, `failed`, `skipped_overlap`, `skipped_disabled`
- `last_error`: short error message from last headless run

## Cardmarket Bulk Source Metadata (Recommended)

- `source_file_path`: local path to imported Cardmarket bulk file
- `source_file_checksum`: checksum for reproducibility and tamper checks
- `source_file_downloaded_at`: timestamp when file was downloaded
- `source_file_version`: provider file version/date label when available

