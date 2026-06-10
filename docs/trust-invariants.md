# Trust invariants

**Status:** **[Shipped]** — enforced in code and CI. Tags: `documentation-status.md`.

Non-negotiable rules for image verification and pricing eligibility. Changing these requires expert panel review (unanimous).

## Two-layer verification

| Layer | Owner | Role |
|-------|-------|------|
| **Tier 8 cascade gate** | `mtg-card-recognition` | Authoritative on in-memory proposals: `gate_status`, `gate_fail_reason` |
| **Row policy** | EbayWorkflows `candidates/` | Idempotent re-check on persisted `evidence_json`; sets `image_verified`, `pricing_eligible` |

Do **not** move row verification policy back into the library (ADR 0002, library v0.3.2).

## Hard verify rules **[Shipped]**

- Bottom zone must yield **set + collector** that match the candidate printing.
- **And** name OCR ≥ `VERIFY_NAME_HARD_MIN` **or** set symbol ≥ `VERIFY_SYMBOL_STRONG_MIN`.
- OCR alone, FAISS alone, and mana OCR alone **never** verify.
- `image_verification_source` when verified is only `set_collector` or `set_symbol`.

## Single winner per listing

- `candidates/candidate_selection.apply_per_listing_verification_gates` demotes extras.
- At most **one** `image_verified` printing per listing drives pricing/EV (`pricing_eligible`).

## Single writer discipline on `evidence_json`

Update order in Phase 5:

1. `candidate_sync` — merge cascade proposals + zone payload
2. `candidate_gate` — evaluate / demote verification
3. `candidate_selection` — pick pricing winner

Avoid parallel writers overwriting provenance fields.

## Provenance fields **[Shipped]**

Persist on verified rows:

- `verification_listing_image_id`
- `verification_detection_id`
- `verification_region_path`
- `image_verification_source`

See `data-dictionary.md` for full `evidence_json` schema.

## Optional FAISS propose

`FAISS_PROPOSE_CANDIDATES=true` may insert a `faiss_proposal` candidate — still subject to row gate; never auto-verifies.

## CI regression tests

| Invariant | Test module |
|-----------|-------------|
| Row gate sources | `test_evidence_gate.py` |
| Cascade → DB views | `test_cascade_persist.py` |
| Per-listing winner | `test_phase5_matching.py` |
| Import boundary | `test_import_boundaries.py` |
| Pricing guardrails | `test_ev_guardrails.py`, `test_hybrid_scoring.py` |

## Related

- `card-recognition-architecture.md` — Phase 5 wiring
- `ranking-and-confidence.md` — EV and guardrails
- `adr/0002-package-restructure.md` — package ownership
