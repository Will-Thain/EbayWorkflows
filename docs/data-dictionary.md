# Data Dictionary

## Purpose

Provide clear semantic definitions for key persisted fields and provenance requirements.

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

- `source_method`: origin of candidate (`title_match`, `ocr_match`, `image_model`)
- `match_score`: normalized matching score for candidate ordering
- `confidence_score`: confidence assigned to candidate
- `embedding_model`: embedding model identifier/version used for retrieval
- `embedding_similarity`: similarity from vector retrieval stage
- `vector_index_version`: FAISS index snapshot/version identifier
- `evidence_json`: structured trace of signals used to build candidate

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

