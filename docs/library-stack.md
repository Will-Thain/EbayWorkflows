# Recommended Library Stack

## Decision Summary

Production matching is a **hybrid propose-then-confirm** pipeline (see `card-recognition-architecture.md`):

- **Propose [Shipped]:** Phase 2 title match; optional FAISS top-1 insert (`FAISS_PROPOSE_CANDIDATES`, `source_method=faiss_proposal`)
- **Propose [Future]:** Milo HF catalog as alternate embedder/proposer
- **Confirm [Shipped]:** `mtg_card_recognition.evidence` — zone OCR + set/collector + symbol per **printing**; one verified winner per listing

Core dependencies:

- `OpenCV` for preprocessing, card region detection, alignment, and zone crops
- `OpenCLIP` for image embeddings and coarse candidate retrieval (catalog: ~110k art-zone vectors)
- `FAISS` for fast nearest-neighbor search (`IndexFlatIP`)
- `Tesseract` (baseline) / `PaddleOCR` (planned primary) for zone text extraction
- `RapidFuzz` for deterministic name reconciliation and disambiguation

## Why Hybrid Beats Vision-Only

MTG cards are near-duplicate visuals across printings. Vision-only matching confuses:

- different sets with similar art
- foil/lighting/angle distortions on eBay photos
- language/version variants

Zone fields (title, set code, collector number, symbol, mana) disambiguate what embeddings cannot prove alone. External scanners (CollectorVision, scryglass, mtg-vision) focus on **proposal**; none implement our multi-zone **confirmation gate**.

## Implementation Pattern (current)

1. detect card regions and normalize crops with OpenCV (`image_gate.py`)
2. align card, detect frame layout, extract zone strips (`mtg_card_recognition.zones` via eBay shims)
3. OCR name/bottom/type-line; match set symbol; detect mana pips (supporting only)
4. embed art-zone crop with OpenCLIP; query FAISS for top-K; optional `faiss_proposal` candidate
5. attach `zone_evidence` with provenance; `candidates_for_region_evidence` prevents reprint OCR bleed
6. `apply_per_listing_verification_gates` sets at most one `image_verified` printing per listing
7. hybrid rank uses `select_pricing_candidate` for singles EV

## Recommended Defaults

- **Image preprocessing:** `opencv-python`
- **OCR:** `pytesseract` **[Shipped]** via `mtg_card_recognition.ocr`; `paddleocr` primary **[Future]**
- **Embeddings:** `open-clip-torch` with `ViT-B-32` + `force_quick_gelu=True`
- **Vector index:** `faiss-cpu` (full corpus ~110k with `build-faiss-full.ps1`)
- **Fuzzy text matching:** `rapidfuzz`
- **Bulk lot detection (Phase 6):** OpenCV multi-card; optional `ultralytics` YOLO later

## External reference implementations

Not dependencies today — design references only:

| Project | Takeaway for us |
|---------|-----------------|
| [CollectorVision / Milo](https://github.com/HanClinto/CollectorVision) | MTG-specific 128-d embed + ~53 MB HF catalog; use as proposer on aligned crops; AGPL |
| [scryglass](https://github.com/KJBurnett/scryglass) | Art + full dual fingerprint; DINO patches; validates our art-zone rects |
| [mtg-vision](https://github.com/nmichlo/mtg-vision) | Synthetic detection training; Qdrant + ConvNeXt pattern |
| [object-detection (techishthoughts)](https://github.com/techishthoughts-org/object-detection) | YOLO zone classes + OCR + DINO art for printing |
| [mtg_scanner](https://github.com/wmjg-alt/mtg_scanner) | YOLO + OCR + Scryfall; tracking for live scan |

Evaluation path without rebuilding Scryfall caches: download Milo NPZ, query existing `crops/zones/aligned/` — see `card-recognition-architecture.md` § Rebuild matrix.

## Operational Guidance

- version embedder model and `index_crop_mode` in FAISS meta JSON
- run `validate-env` after index or zone config changes
- keep a labeled validation set for OCR-only vs embedding-only vs hybrid regression
- prefer deterministic zone confirmation over opaque score drift

## Desktop GUI (operator application)

- **UI framework:** `PySide6` (Qt 6) — native window, `QTableView`, `QProcess`, `QTimer`
- **Default style:** Qt **Fusion**; optional dark palette via `qdarktheme` or custom `QPalette`
- **Not used for GUI:** Tkinter, Streamlit, Electron (see `gui-application.md`)
- **Scheduling (in-app):** `apscheduler` (GUI-6); headless: `ebay-workflows run-due-schedules` + Windows Task Scheduler
- **Packaging:** PyInstaller with PySide6 Qt libraries bundled
