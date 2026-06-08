# Card Recognition Architecture

This document defines how EbayWorkflows identifies MTG cards from eBay listing photos: our **propose-then-confirm** design, on-disk artifacts, zone geometry, lessons from external libraries, and the **strict consensus verification gate** shipped in `mtg_card_recognition` (branch `feature/card-recognition-package`).

Operational runbooks: `runbook-local.md`, `large-scale-ingest.md`.

## Implementation status

| Item | Status |
|------|--------|
| `mtg_card_recognition` package (extractable) | **[Shipped]** on `feature/card-recognition-package` |
| Strict consensus verification gate | **[Shipped]** — `mtg_card_recognition.evidence` + per-listing winner |
| Single-winner singles EV (Phase 4 / hybrid) | **[Shipped]** — `select_pricing_candidate` |
| OCR reprint bleed fix | **[Shipped]** — `candidates_for_region_evidence` |
| Evidence provenance (`verification_*` on attach) | **[Shipped]** — Phase 5 region persist |
| `zones_available` computation | **[Shipped]** — `zones/signals.compute_zones_available` |
| FAISS candidate proposal (`FAISS_PROPOSE_CANDIDATES`) | **[Shipped]** — Phase 5 inserts `faiss_proposal` when top-1 ∉ title matches |
| Scryfall `layout` / `frame` layout hints | **[Shipped]** — `layout_from_scryfall_payload`; wider art-zone wiring **[Future]** |
| FAISS index process cache | **[Shipped]** — `embedding_index.clear_faiss_index_cache` |
| Milo / alternate embedder | **[Future]** |
| PaddleOCR on zones | **[Future]** — Tesseract interim **[Shipped]** |
| Threshold calibration (`VERIFY_*` defaults) | **[Future]** — starting points **[Shipped]** in code; eBay crop eval not done |
| Phase 6 FAISS override vs singles gate alignment | **[Future]** |

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

**Proposal:** When `FAISS_PROPOSE_CANDIDATES=true` (default), Phase 5 may insert a `faiss_proposal` candidate if FAISS top-1 is absent from Phase 2 title matches; strict verification still applies. Milo/alternate embedders remain future work.

---

## Pipeline overview (shipped data flow)

```text
Phase 2   top_k=3 title candidates per listing (often same name, different sets)
          └─ listing_card_candidates (evidence_json, pricing_eligible)

Phase 5   Per listing image → per region:
          ├─ OpenCV gate + crops
          ├─ Align + zones (mtg_card_recognition.zones)
          ├─ FAISS search — corroborates Phase 2 IDs; optional faiss_proposal insert
          ├─ candidates_for_region_evidence — no name-only bleed across reprints
          └─ zone attach + verification_* provenance on detection

Phase 5 end apply_per_listing_verification_gates — at most one verified printing per listing

Phase 3   apply_price_to_evidence per candidate if pricing_eligible

Phase 6   Bulk: resolve_lot_crop_match (set_collector + strict crop evidence)

Phase 4   hybrid ranking — select_pricing_candidate (single printing for singles EV)
```

Production phase order: **2 → 5 → 3 → 6 → 4** (`workflow-phases.md`).

### Module map

| Concern | Package / shim | Role |
|---------|----------------|------|
| Recognition core | `src/mtg_card_recognition/` | Extractable library (`RecognitionSettings`, zones, evidence) |
| eBay adapter | `ebay_workflows.adapters.recognition_settings` | Maps `Settings` → `RecognitionSettings` |
| Region detection | `card_regions.py`, `image_gate.py` | Card-like blobs in listing photos (eBay) |
| Zones / OCR / align | `card_zones.py`, `zone_card_signals.py`, … shims | Delegate to `mtg_card_recognition` |
| Set symbol build | `set_symbol_match.py` | Template download + matrix (eBay DB); match in package |
| Embeddings | `embedding_index.py`, `openclip_runtime.py` | FAISS + OpenCLIP (eBay); vectors in `.cache/faiss/` |
| Evidence / gate | `image_evidence.py` shim → `mtg_card_recognition.evidence` | Strict verify, per-listing winner |
| Pricing guardrails | `ev_guardrails.py` | Title/bulk rules; only `set_collector` / `set_symbol` bypass when verified |
| Ranking | `hybrid_scoring.py`, `workflow_phase4.py` | `select_pricing_candidate` — one printing per listing |

---

## Historical audit **[Historical]**

A detailed audit was completed before coding the consensus gate. The issues below described **production behavior before** `feature/card-recognition-package`; all P0 items are **fixed** in `mtg_card_recognition`. Re-run Phase 5 reanalyze on existing caches to measure impact (expect fewer `image_verified` than the old ~101 OR-gate run).

### Findings at a glance (fixed)

| Severity | Issue (was) | Fix (shipped) |
|----------|-------------|---------------|
| **P0** | OCR verified all Phase 2 reprints | `candidates_for_region_evidence` |
| **P0** | Phase 4 summed prices across verified top-K | `select_pricing_candidate` |
| **P0** | Set-only match counted as collector verify | Strict set **and** collector in `evidence.gate` |
| **P0** | Mana standalone verification | Mana supporting only; removed from pricing auto-allow |
| **P0** | No detection provenance on evidence | `verification_*` fields on attach |
| **P0** | `zones_available` undefined | `compute_zones_available` in `zones/signals.py` |
| **High** | Phase 5 dead branch (symbol-only regions) | Fixed `elif zone_evidence` branch |
| **High** | OR attach @ 0.55 looser than verify | Attach still permissive; verify gate is strict |
| **High** | `pricing_allowed` trusted embedding/mana | Only `set_collector` / `set_symbol` when verified |
| **Med** | FAISS `read_index` per query | Process-level index cache in `embedding_index.py` |

Remaining open items: Phase 6 FAISS override philosophy alignment, OCR confidence heuristic, scryglass rect validation on eBay crops.

---

## Historical P0 bugs **[Historical]**

### 1. Reprint OCR bleed

`workflow_phase5._update_candidate_confidence` writes identical `ocr_verification` to every candidate whose **name** fuzzy-matches the same crop OCR. Phase 2 stores up to three printings of the same name.

**Was:** Verification applied by name across reprints. **Now:** `candidates_for_region_evidence` routes by set+collector or single unambiguous name match.

### 2. Single winner for singles EV

`hybrid_scoring.compute_listing_score_hybrid` and `workflow_phase4._compute_listing_score` add `gross_value` for **every** verified candidate in top-3 with a price.

**Was:** Summed all verified top-K prices. **Now:** `select_pricing_candidate` + `apply_per_listing_verification_gates`.

### 3. Set-only “collector” match

`image_evidence._card_identifiers_match` returns `True` when set codes match and collector is absent.

**Was:** Set-only match passed. **Now:** `_card_identifiers_match_strict` requires both set and collector.

### 4. Mana as standalone verification

Intersection `detected & expected` with low HSV threshold and `color_identity` fallback is too weak for pricing.

**Was:** Mana overlap could verify alone. **Now:** Mana never sets `image_verified`; removed from pricing auto-allow.

### 5. Evidence provenance

Candidates do not record which image region proved the match.

**Was:** No provenance. **Now:** Stored on candidate `evidence_json` and nested `zone_evidence` (see `data-dictionary.md`).

### 6. Phase 5 attach dead branch

```text
if fields: ... attach zone_evidence
elif region_analysis.zone_evidence and fields:  # unreachable when fields empty
```

**Was:** Unreachable branch left symbol-only regions without detections. **Now:** Fixed; shell detection persisted for zone-only regions.

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

`detect_frame_layout()` uses heuristics (aspect, border brightness). `layout_from_scryfall_payload()` and optional `layout_hint` on `prepare_card_for_zones()` support Scryfall `frame` / `layout` when metadata is available (e.g. art-zone build).

### scryglass art rect

scryglass uses `x: 0.08–0.92`, `y: 0.11–0.53` on **Scryfall scans**. Our modern art zone is similar on clean scans. **Do not assume** the same rects are optimal for skewed eBay crops or full-frame fallback (`IMAGE_ALLOW_FULL_FRAME_FALLBACK=true`).

### `zones_available` (shipped — `zones/signals.compute_zones_available`)

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
- **Not recommended:** Silent fallback to the old OR gate (hides policy change).

---

## Evidence model

### Shipped verification behavior (`mtg_card_recognition.evidence`)

**Per listing:** at most **one** printing receives `image_verified=true` and Cardmarket pricing for singles EV (`apply_per_listing_verification_gates`).

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

PROPOSAL (shipped when FAISS_PROPOSE_CANDIDATES=true):
  - If embed top-1 ∉ Phase 2 candidates → insert faiss_proposal candidate, then run verification
  - Milo HF NPZ eval — future work
```

**Phase 6 bulk crops:** Crop-level `set_collector` and strict image evidence via `crop_match_allowed_for_pricing`. FAISS may suggest matches but does not alone verify.

**Pricing guardrails:** `pricing_allowed_for_candidate` allows image bypass only for `set_collector` and `set_symbol` when `image_verified`.

**Thresholds:** `VERIFY_NAME_HARD_MIN` (0.75), `VERIFY_NAME_STRONG_MIN` (0.88), `VERIFY_SYMBOL_STRONG_MIN` (0.55) — calibrate on labeled eBay crops after reanalyze.

### Historical OR gate **[Historical]**

Before `mtg_card_recognition`, `candidate_has_image_evidence()` verified if **any** signal passed (OCR, FAISS, set-only, mana). Last OR-gate reanalyze (~110k FAISS): ~101 `image_verified` — roughly OCR 61, mana 39, FAISS 1. Mana hits were OR leakage, not quality proof.

### Draft consensus gate — **REJECTED** **[Historical]**

```text
❌ if bottom set+collector → verified          (allowed set-only in old code)
❌ elif name ≥ 0.80 AND (symbol OR mana)      (reprints; mana OR too weak)
❌ elif name ≥ 0.65 AND symbol AND mana       (three noisy signals compound error)
❌ else block FAISS/OCR when zones exist      (undefined zones_available at time of draft)
```

### Edge cases (still apply)

| Case | Risk |
|------|------|
| Same name, 3 Phase 2 reprints | Mitigated by per-printing attach + single winner |
| Basic land / `{0}` | Mana expected empty — do not use mana |
| DFC / wrong layout | Zones cut wrong text — use Scryfall frame metadata |
| Full-frame fallback | Zones on entire thumbnail — exclude via `zones_available` |
| Wrong bottom OCR + symbol hints | Symbol search restricted to wrong set subset |
| Multiple images per listing | Last region may overwrite `zone_evidence`; provenance fields identify proof source |
| Phase 3 `pricing_eligible` default true | Phase 5 gate clears ineligible before Phase 3 in correct pipeline order |

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
| Consensus gate shipped (code on branch) | No | No | Reanalyze recommended |
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

### Embedding roles

| Role | Status |
|------|--------|
| FAISS corroborates Phase 2 candidate IDs | **[Shipped]** |
| FAISS top-1 proposal when absent from Phase 2 (`FAISS_PROPOSE_CANDIDATES`) | **[Shipped]** — still requires strict verify to price |
| OpenCLIP on eBay art zones (weak vs printing-aware) | **[Shipped]** limitation |
| Milo / alternate embedder sidecar | **[Future]** |

---

## Implementation roadmap

| Step | Work | Status | Rebuild 110k? |
|------|------|--------|---------------|
| **1** | Single winner per listing for EV/pricing | **[Shipped]** | No |
| **2** | Per-printing verification; remove set-only match | **[Shipped]** | No |
| **3** | Remove mana/embedding standalone verify; pricing guardrails | **[Shipped]** | No |
| **4** | Phase 5 dead branch + evidence provenance | **[Shipped]** | No |
| **5** | Consensus spec + `zones_available` | **[Shipped]** | No |
| **6** | FAISS top-1 proposal (`FAISS_PROPOSE_CANDIDATES`) | **[Shipped]** | No |
| **7** | PaddleOCR on name/bottom zones | **[Future]** | No |
| **8** | Milo index replace (optional) | **[Future]** | Re-embed only |
| **9** | Threshold calibration dataset | **[Future]** | No |

---

## Configuration reference

`config-contract.md`. Critical toggles:

- `CARD_ZONE_*`, `FAISS_INDEX_USE_ART_ZONE`, `VERIFY_*`, `FAISS_PROPOSE_CANDIDATES`
- `IMAGE_ALLOW_FULL_FRAME_FALLBACK` — when true, often invalidates strict zones
- `TITLE_MATCH_MIN_SCORE_FOR_PRICING` — degraded path when image verify fails

`validate-env` — FAISS crop mode, vector count, set symbol templates.

---

## Related documents

- `workflow-phases.md` — phase I/O and strict verification gate
- `ranking-and-confidence.md` — single-winner EV and evidence table
- `data-dictionary.md` — `evidence_json` verification and provenance fields
- `library-stack.md` — dependencies and external references
- `future-pain-points.md` — §6 OpenCLIP weakness, disk layout
