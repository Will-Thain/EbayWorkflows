# mtg-card-recognition

Standalone packaging scaffold for the `mtg_card_recognition` Python package.

## Current layout (monorepo)

Source of truth during development:

```
src/mtg_card_recognition/
```

eBay Workflows integrates through:

```
src/ebay_workflows/adapters/recognition_settings.py
```

## Extract to own repository

1. Copy `src/mtg_card_recognition/` to the new repo as `src/mtg_card_recognition/`.
2. Copy this `pyproject.toml` and adjust `tool.setuptools.packages.find`.
3. Copy recognition tests from `tests/test_card_*`, `tests/test_image_evidence.py`, etc.
4. Remove `ebay_workflows.adapters` dependency; callers pass `RecognitionSettings` directly.

## Public API

- `RecognitionSettings` — framework-agnostic configuration
- `extract_card_zone_signals` — `mtg_card_recognition.zones.signals`
- `apply_per_listing_verification_gates` — strict per-listing verification
- `select_pricing_candidate` — single printing for singles EV

See `docs/card-recognition-architecture.md` in the parent monorepo.
