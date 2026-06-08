# Ranking and Confidence Model

## Purpose

Provide a transparent and versioned method to rank listings by expected value (EV) while accounting for uncertainty from matching and image interpretation.

## Baseline EV

Suggested baseline formula:

- `listing_cost = listing_price + shipping + fees_estimate`
- `gross_value = sum(candidate_card_market_values)`
- `ev_raw = gross_value - listing_cost`

## Confidence Dimensions

Each listing gets sub-scores in `[0.0, 1.0]`:

- `title_match_confidence`
- `ocr_confidence`
- `embedding_match_confidence`
- `set_collector_confidence`
- `price_freshness_confidence`
- `image_quality_confidence`
- `lot_completeness_confidence` (Phase 6 heavy impact)

## Composite Confidence

Initial weighted approach:

- `confidence_score = w1*title + w2*ocr + w3*embedding + w4*set_collector + w5*price_freshness + w6*image_quality + w7*lot_completeness`

Weights are stored by scoring version to support backtesting.

## Risk Adjustment

Define:

- `risk_score = 1.0 - confidence_score`
- `ev_adjusted = ev_raw * confidence_score`

## Image Verification and Pricing Guardrails

Singles (Phase 5) and bulk lot crops (Phase 6) require **image evidence** before Cardmarket prices attach:

| Evidence source | Phase 5 singles | Phase 6 lot crops | Confirmation strength |
|-----------------|-----------------|-------------------|------------------------|
| OCR name match | yes | via crop title OCR | supporting only; never standalone verify |
| FAISS embedding | yes | yes | proposer (`FAISS_PROPOSE_CANDIDATES`); corroboration only for verify |
| Set + collector (zone OCR) | yes | yes | **hard confirm** when collector parses |
| Set symbol template | yes | yes | strong for reprint disambiguation |
| Mana colors (zone) | yes | yes | supporting / tie-breaker only |

**Shipped:** one printing per listing for pricing/EV (`select_pricing_candidate`); strict consensus gate in `mtg_card_recognition.evidence`; provenance fields on region attach.

Bulk **listing titles** never drive pricing alone (`bulk_lot_title_requires_image_evidence`). Phase 6 uses `crop_match_allowed_for_pricing` so individual detected cards can still receive unit prices when crop evidence confirms the match.

Phase 3 (price join) must run **after** Phase 5 so `pricing_eligible` reflects image verification. Pipeline scripts use order: **2 → 5 → 3 → 6 → 4**.

Alternative conservative variant:

- `ev_adjusted = ev_raw - risk_penalty_multiplier * risk_score`

## Ranking Value

Default:

- `rank_value = ev_adjusted`

Optional tie-breaks:

1. higher `confidence_score`
2. more recent listing timestamp
3. lower image ambiguity count

## Explainability Output

Each score record should include an explanation payload:

- selected card candidates and contributions
- OpenCLIP similarity values and FAISS top-K details
- `zone_evidence` payload (name/bottom OCR, set symbol score, mana colors)
- `image_verification_source` (`ocr`, `embedding`, `set_collector`, `set_symbol`, `mana_colors`)
- confidence component breakdown
- penalties applied
- scoring/model versions

This enables auditability and easier tuning over time.

