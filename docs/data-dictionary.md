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

- `source_method`: **column** — how the candidate row was created (see enum below)
- `match_score`: normalized matching score for candidate ordering
- `confidence_score`: confidence assigned to candidate
- `rank_position`: Phase 2 ordering (1 = best title match)
- `evidence_json`: structured trace of signals used to build candidate (see below)

### `source_method` (column enum) **[Shipped]**

Values persisted on `listing_card_candidates.source_method`:

| Value | Set by | Meaning |
|-------|--------|---------|
| `title_match` | Phase 2 | Fuzzy title / set+collector match from listing text |
| `faiss_proposal` | Phase 5 (optional) | Inserted when `FAISS_PROPOSE_CANDIDATES=true` and top-1 ∉ Phase 2 rows |

**Log-only / nested strings** (not column values): `faiss_search`, `set_collector`, `zone_set_collector` — appear in `match_event_log` or `evidence_json.method` / `match_method`, not necessarily in `source_method`.

Phase 2 also stores title-match detail inside `evidence_json`:

- `method` or `match_method` — e.g. `fuzzy_title`, `set_collector` (title matcher output)
- Do **not** confuse with `image_verification_source` (image gate outcome)

### `evidence_json` — cascade fields (Phase 5) **[Shipped]**

Written by `candidate_sync` from library serialize + zone payload:

| Field | Type | Meaning |
|-------|------|---------|
| `gate_status` | string \| null | Cascade Tier 8 outcome: `verified`, `blocked_at_gate`, … |
| `gate_fail_reason` | string \| null | Why cascade blocked (when not verified) |
| `verification_source` | string \| null | Library proposal field; see mapping below |
| `cascade_region_id` | string | Region id from cascade attach |
| `pricing_eligible` | bool | Library + row policy: may Phase 3 price this printing |

When `gate_status` is present, row policy treats cascade as authoritative (`candidate_gate`).

### Verification field mapping (library → consumer) **[Shipped]**

| Library / cascade (serialize) | Canonical persisted (pricing/EV) | Notes |
|------------------------------|----------------------------------|-------|
| `gate_status` | `gate_status` | Copied into evidence |
| `verification_source` | `image_verification_source` | Consumer renames on apply; gate reads both during transition |
| (derived) | `image_verified` | Set by `candidate_gate` / selection |
| `pricing_eligible` | `pricing_eligible` | Must be true with verified set_collector for Phase 3 |

**Boundary:** library `printing_id` on proposals ≡ ORM `scryfall_id` (same UUID).

### `evidence_json` — image verification (Phase 5)

Set by **EbayWorkflows `candidates/`** row policy (`candidate_gate`, `candidate_sync`, `candidate_attach`) after library cascade Tier 8; serialized fields from `mtg_card_recognition.serialize`:

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

