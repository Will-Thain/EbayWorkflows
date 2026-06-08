# Card Recognition Architecture

This document defines how EbayWorkflows identifies MTG cards from eBay listing photos: our **propose-then-confirm** design, on-disk artifacts, zone geometry, lessons from external libraries, and the **pre-implementation review** that blocks naive consensus-gate coding.

Operational runbooks: `runbook-local.md`, `large-scale-ingest.md`.

## Implementation status

| Item | Status |
|------|--------|
| `mtg_card_recognition` package (extractable) | **Shipped** on `feature/card-recognition-package` |
| Strict consensus verification gate | **Shipped** — `mtg_card_recognition.evidence` + per-listing winner |
| Single-winner singles EV (Phase 4 / hybrid) | **Shipped** — `select_pricing_candidate` |
| OCR reprint bleed fix | **Shipped** — `candidates_for_region_evidence` |
| Evidence provenance (`verification_*` on attach) | **Shipped** — Phase 5 region persist |
| `zones_available` computation | **Shipped** — `zones/signals.compute_zones_available` |
| FAISS candidate proposal (`FAISS_PROPOSE_CANDIDATES`) | **Shipped** — Phase 5 inserts `faiss_proposal` when top-1 ∉ title matches |
| Milo / alternate embedder proposal | **Not built** |
| PaddleOCR on zones | **Planned** — not wired (`ocr_extract.py` still Tesseract) |
| Threshold calibration (0.80 / 0.65) | **Not validated** — do not copy into code without labeled eBay crops |

---

## Problem shape

eBay listing photos differ from phone-scanner apps (ManaBox, CollectorVision, scryglass):

| Factor | Scanner apps | EbayWorkflows |
|--------|--------------|---------------|
| Input | Single card, controlled angle, often sleeve-aware | Multi-card lots, glare, skew, listing thumbnails |
| Goal | End-to-end ID in &lt;100ms | Rank deals; explain why a price attached |
| Ambiguity | Accept top-1 match | Reprints, foils, wrong titles, bulk noise |
| Metadata | Lookup after ID | Postgres + `evidence_json` provenance required |

**Design choice:** treat vision as a **candidate proposer** and structured zone reads as **confirmation judges**. No external library reviewed implements multi-zone confirmation (name / bottom / symbol / mana) before pricing; that is our differentiator.

**Important correction:** In code today, OpenCLIP+FAISS **does not propose** new candidates — it only attaches scores to Scryfall IDs already returned by Phase 2 title match (`apply_embedding_evidence`). Milo/eval paths are future work.

---

## Pipeline overview (actual data flow)

```text
Phase 2   top_k=3 title candidates per listing (often same name, different sets)
          └─ listing_card_candidates (evidence_json, pricing_eligible)

Phase 5   Per listing image → per region:
          ├─ OpenCV gate + crops (card_regions.py)
          ├─ Align + zones (card_zones.py, zone_card_signals.py)
          ├─ FAISS search (embedding_index.py) — hits discarded unless ID ∈ Phase 2 list
          ├─ _update_candidate_confidence(ocr_title) — ALL name-matching reprints
          └─ _attach_zone_evidence — OR match @ 0.55 name threshold

Phase 5 end apply_image_evidence_gate on ENTIRE candidates table (global)

Phase 3   apply_price_to_evidence per candidate if pricing_eligible

Phase 6   Bulk: resolve_lot_crop_match (FAISS can override title; separate rules)

Phase 4   hybrid / v1 ranking — sums gross_value across verified top-3 candidates ⚠
```

Production phase order: **2 → 5 → 3 → 6 → 4** (`workflow-phases.md`).

### Module map

| Concern | Module | Role |
|---------|--------|------|
| Region detection | `card_regions.py`, `image_gate.py` | Card-like blobs in listing photos |
| Alignment | `card_align.py` | Perspective warp or soft resize (488×680) |
| Zone geometry | `card_zones.py` | Layout templates (modern / old / DFC) |
| Zone extraction | `zone_card_signals.py` | OCR, set symbol, mana on zone JPGs |
| Set symbol | `set_symbol_match.py` | Per-set template matrix (48×48 dot product) |
| Mana pips | `mana_cost.py` | HSV masks on mana-cost strip |
| Embeddings | `openclip_runtime.py`, `embedding_index.py` | OpenCLIP ViT-B/32 + FAISS IndexFlatIP |
| Evidence / gate | `image_evidence.py`, `ev_guardrails.py` | `image_verified`, pricing eligibility |
| Ranking | `hybrid_scoring.py`, `workflow_phase4.py` | EV — must use **one printing per listing** (not yet enforced) |

---

## Pre-implementation review (summary)

A detailed audit was completed before coding the consensus gate. P0 structural fixes are implemented in `mtg_card_recognition` (branch `feature/card-recognition-package`). Re-run Phase 5 reanalyze on existing caches to validate live metrics.

### Findings at a glance

| Severity | Issue |
|----------|--------|
| **P0** | One OCR string verifies **all** Phase 2 reprints (same name, different `scryfall_id`) |
| **P0** | Phase 4 **sums** Cardmarket prices across all verified top-K candidates → inflated EV for singles |
| **P0** | `_card_identifiers_match` returns true for **set-only** (no collector) — not a hard confirm |
| **P0** | Mana verification uses **any color overlap** — likely false positives (39 hits in last run ≠ quality proof) |
| **P0** | No `listing_image_id` / `detection_id` on verification evidence — stale/mixed proof |
| **P0** | `zones_available` undefined; fallback policy unspecified |
| **High** | Phase 5 dead branch: symbol/mana-only regions never attach `zone_evidence` |
| **High** | Attach policy (OR @ 0.55) looser than intended verify policy |
| **High** | Phase 5 singles vs Phase 6 lot FAISS override — inconsistent philosophy |
| **High** | `pricing_allowed_for_candidate` trusts `embedding` and `mana_colors` sources |
| **High** | OCR “confidence” is `len(text)/40`, not model confidence |
| **Med** | FAISS `read_index` per query — performance, not correctness |
| **Med** | scryglass rects ≈ our Scryfall-scan rects — **not** proof eBay zone coords are correct |

Full edge-case catalog and rule-by-rule critique: see **Evidence model** and **Structural bugs** below.

---

## Structural bugs (P0 — fix before consensus gate)

### 1. Reprint OCR bleed

`workflow_phase5._update_candidate_confidence` writes identical `ocr_verification` to every candidate whose **name** fuzzy-matches the same crop OCR. Phase 2 stores up to three printings of the same name.

**Required fix:** Verification must be **per printing** — require set+collector or set symbol match **for that** `scryfall_id`, never name alone across reprints.

### 2. Single winner for singles EV

`hybrid_scoring.compute_listing_score_hybrid` and `workflow_phase4._compute_listing_score` add `gross_value` for **every** verified candidate in top-3 with a price.

**Required fix:** Select **at most one** `scryfall_id` per listing for pricing and EV (highest confirmation score; tie-break by rank_position).

### 3. Set-only “collector” match

`image_evidence._card_identifiers_match` returns `True` when set codes match and collector is absent.

**Required fix:** `image_verification_source=set_collector` requires **parsed collector number** matching the candidate.

### 4. Mana as standalone verification

Intersection `detected & expected` with low HSV threshold and `color_identity` fallback is too weak for pricing.

**Required fix:** Mana is **supporting / tie-break only** — never `image_verified` alone; remove from `pricing_allowed_for_candidate` auto-allow list unless paired with collector proof.

### 5. Evidence provenance

Candidates do not record which image region proved the match.

**Required fix:** Store `verification_detection_id`, `verification_listing_image_id`, and `verification_region_path` in `evidence_json`.

### 6. Phase 5 attach dead branch

```text
if fields: ... attach zone_evidence
elif region_analysis.zone_evidence and fields:  # unreachable when fields empty
```

Symbol/mana-only extractions never attach. Fix before consensus uses symbol.

---

## Zone geometry

Zones are **not** stored per Scryfall card in Postgres. Three layout families in code supply normalized rects. After alignment, `prepare_card_for_zones()` writes:

| Zone suffix | Used for |
|-------------|----------|
| `*_name.jpg` | Title OCR |
| `*_art.jpg` | FAISS query when `CARD_ZONE_FAISS_ENABLED=true` |
| `*_bottom.jpg` | Set + collector parsing |
| `*_set_symbol.jpg` | Template match |
| `*_mana_cost.jpg` | WUBRG pip detection (supporting only) |

`detect_frame_layout()` uses heuristics (aspect, border brightness). **Planned:** map Scryfall `frame` / `layout` from `raw_payload_json` at sync.

### scryglass art rect

scryglass uses `x: 0.08–0.92`, `y: 0.11–0.53` on **Scryfall scans**. Our modern art zone is similar on clean scans. **Do not assume** the same rects are optimal for skewed eBay crops or full-frame fallback (`IMAGE_ALLOW_FULL_FRAME_FALLBACK=true`).

### `zones_available` (spec for implementation)

A listing region qualifies for strict zone confirmation only when **all** hold:

```text
zones_available :=
  CARD_ZONE_OCR_ENABLED
  AND CARD_ZONE_ALIGN_ENABLED (or align_confidence recorded)
  AND align_confidence >= T_ALIGN (e.g. 0.35 from card_align)
  AND bottom_path file exists
  AND (name_path exists OR bottom_parsed has set)
  AND NOT zone_evidence.fallback_full_card_ocr
```

When `zones_available` is false, use an **explicit degraded policy** (documented choice):

- **Recommended:** `image_verified=false`; no image-driven Cardmarket price; title-only path remains subject to `TITLE_MATCH_MIN_SCORE_FOR_PRICING`.
- **Not recommended:** Silent fallback to current OR gate (hides policy change).

---

## Evidence model

### Current behavior (OR gate — shipped)

`candidate_has_image_evidence()` returns verified if **any** signal passes:

| Source | Config default | Actual strength on eBay photos |
|--------|----------------|--------------------------------|
| OCR name | 0.60 | Strong when strip clean; **verifies all reprints** |
| FAISS | 0.55 | Weak (generic OpenCLIP); ~1 verification in full reanalyze |
| Set + collector | zone bottom | **Weaker than documented** — set-only passes |
| Set symbol | 0.45 | Moderate; hint narrowing can mis-steer |
| Mana colors | 0.30 | **Weak** — overlap logic; suspect false positives |

`region_zone_evidence_matches_card()` uses the same OR pattern at 0.55 name similarity before attaching `zone_evidence`.

**Last full reanalyze (~110k art-zone FAISS):** ~101 `image_verified` listings — sources roughly OCR 61, mana 39, FAISS 1.

**Do not interpret** mana 39 as validation of mana confirmation — likely OR-gate leakage given overlap logic and low thresholds.

### Draft consensus gate — **REJECTED** (do not implement)

The following was documented as a target but **failed review**:

```text
❌ if bottom set+collector → verified          (code allows set-only; parser noise)
❌ elif name ≥ 0.80 AND (symbol OR mana)      (reprints; mana OR too weak)
❌ elif name ≥ 0.65 AND symbol AND mana       (three noisy signals compound error)
❌ else block FAISS/OCR when zones exist      (undefined zones_available; no proposer)
```

### Target behavior — **approved spec** (implement after P0)

**Per listing:** at most **one** printing receives `image_verified=true` and Cardmarket pricing for singles EV.

**Per candidate C** (when `zones_available` for the proving region):

```text
HARD VERIFY (image_verified=true, source=set_collector):
  bottom_parsed.set AND bottom_parsed.collector present
  AND match C.set_code AND C.collector_number (normalized)
  AND (name_sim(OCR, C.name) >= 0.75 OR set_symbol matches C.set_code at score >= 0.55)

STRONG VERIFY (image_verified=true, source=set_symbol):
  set_symbol matches C.set_code at score >= 0.55
  AND name_sim >= 0.88
  AND bottom_parsed.set matches C.set_code (collector optional but preferred)

NOT ALLOWED alone for image_verified:
  - OCR name only (reprint ambiguity)
  - FAISS / embedding only
  - Mana colors only
  - Set code without collector (singles)

SUPPORTING (ranking / tie-break / hybrid weights only):
  - FAISS score when C already hard/strong verified
  - Mana overlap after printing locked
  - Phase 2 title_match_score

PROPOSAL (separate feature — not the gate):
  - If embed top-1 ∉ Phase 2 candidates → insert or promote candidate, then run verification
  - Milo HF NPZ eval on existing aligned crops without rebuilding scryfall_art/
```

**Phase 6 bulk crops:** Keep crop-level verification; align with same printing-specific rules; FAISS override only when followed by zone confirmation (future alignment with singles).

**Pricing guardrails:** Update `pricing_allowed_for_candidate` and `crop_match_allowed_for_pricing` to match — remove standalone `embedding` and `mana_colors` from auto-allow lists.

**Thresholds:** `0.75`, `0.88`, `0.55` symbol are **starting points** — calibrate on a labeled set of eBay zone crops before production.

### Edge cases (verification must handle)

| Case | Risk |
|------|------|
| Same name, 3 Phase 2 reprints | OCR verifies all today |
| Basic land / `{0}` | Mana expected empty — do not use mana |
| DFC / wrong layout | Zones cut wrong text — use Scryfall frame metadata |
| Full-frame fallback | Zones on entire thumbnail — exclude via `zones_available` |
| Wrong bottom OCR + symbol hints | Symbol search restricted to wrong set subset |
| Multiple images per listing | Last region overwrites `zone_evidence` |
| Phase 3 `pricing_eligible` default true | Stale candidates price before gate |

---

## On-disk artifacts

| Path | Approx. scale | Rebuild when |
|------|---------------|--------------|
| `scryfall_art/{uuid}.jpg` | ~110k, ~11 GB | Corrupt/missing only |
| `scryfall_art_zones/{uuid}_art.jpg` | ~110k+, ~23 GB | Crop mode / layout change |
| `faiss/index.bin` + `.meta.json` | ~110k vectors | Model, crop mode, dimension |
| `set_symbol_templates/{set}.png` | ~500 sets | `build-set-symbol-templates` |
| `crops/zones/` | per ingest | Phase 5 re-run |

**No per-card zone coordinate table** — geometry in code; labels from Scryfall JSON at confirm time.

---

## Rebuild matrix

| Goal | Re-download Scryfall? | Re-embed 110k? | Re-run Phase 5? |
|------|----------------------|----------------|-----------------|
| P0 bug fixes + consensus gate | No | No | Reanalyze recommended |
| PaddleOCR on zones | No | No | Yes |
| Milo A/B on aligned crops | No | No | Eval subset |
| Replace OpenCLIP with Milo index | No | Yes (from `scryfall_art/`) | Reanalyze |
| Toggle `FAISS_INDEX_USE_ART_ZONE` | No | Yes | Reanalyze |

---

## External libraries (reference only)

See prior deep review in git history. Short takeaways:

| Project | Use for us |
|---------|------------|
| **CollectorVision / Milo** | Future **proposer** catalog (~53 MB NPZ); AGPL; pre-cropped aligned paths |
| **scryglass** | Art+full fingerprint pattern; heavy index |
| **mtg-vision** | Synthetic YOLO training; skip duplicate HDF5 |
| **object-detection** | Learned zone boxes + OCR + DINO printing |
| **mtg_scanner** | Live scan / tracking only |

None implement our zone confirmation layer.

### Embedding role correction

| Today | Target |
|-------|--------|
| FAISS corroborates Phase 2 IDs only | + proposal path for top-K ∉ title candidates |
| OpenCLIP weak on eBay art zones | Optional Milo sidecar |

---

## Implementation roadmap (revised order)

| Step | Work | Rebuild 110k? |
|------|------|---------------|
| **1** | Single winner per listing for EV/pricing | No |
| **2** | Per-printing verification; remove set-only match | No |
| **3** | Remove mana/embedding as standalone verify; fix pricing guardrails | No |
| **4** | Fix Phase 5 dead branch + evidence provenance fields | No |
| **5** | Implement approved consensus spec + `zones_available` | No |
| **6** | Embedding proposal (FAISS top-1 or Milo NPZ) | No |
| **7** | PaddleOCR on name/bottom zones | No |
| **8** | Milo index replace (optional) | Re-embed only |
| **9** | Threshold calibration dataset | No |

---

## Configuration reference

`config-contract.md`. Critical toggles:

- `CARD_ZONE_*`, `FAISS_INDEX_USE_ART_ZONE`, `IMAGE_EVIDENCE_MIN_*`
- `IMAGE_ALLOW_FULL_FRAME_FALLBACK` — when true, often invalidates strict zones
- `TITLE_MATCH_MIN_SCORE_FOR_PRICING` — degraded path when image verify fails

`validate-env` — FAISS crop mode, vector count, set symbol templates.

---

## Related documents

- `workflow-phases.md` — phase I/O; current OR vs planned consensus
- `ranking-and-confidence.md` — single-winner EV requirement (to be enforced in code)
- `library-stack.md` — dependencies and external references
- `future-pain-points.md` — §6 OpenCLIP weakness, disk layout
