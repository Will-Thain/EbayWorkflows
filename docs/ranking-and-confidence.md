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
- confidence component breakdown
- penalties applied
- scoring/model versions

This enables auditability and easier tuning over time.

