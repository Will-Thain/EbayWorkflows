# Recommended Library Stack

## Decision Summary

Using `OpenCLIP + FAISS + OpenCV` is a good and practical choice for this workflow.  
The recommended production approach is a hybrid pipeline:

- `OpenCV` for preprocessing, card region detection support, and crop normalization
- `OpenCLIP` for image embeddings and coarse candidate retrieval
- `FAISS` for fast nearest-neighbor search against Scryfall embeddings
- `PaddleOCR` (preferred) or `Tesseract` (baseline) for title/set code/collector number extraction
- `RapidFuzz` for deterministic text reconciliation and disambiguation

## Why Hybrid Is Better Than Vision-Only

MTG cards are near-duplicate visuals across printings and variants. Vision-only matching can confuse:

- different sets with similar art
- foil/lighting/angle distortions
- language/version variants

OCR fields (title, set code, collector number) provide high-value disambiguation that embeddings alone cannot guarantee.

## Recommended Defaults

- **Image preprocessing:** `opencv-python`
- **OCR:** `paddleocr` (fallback: `pytesseract`)
- **Embeddings:** `open-clip-torch` with `ViT-B/32` as initial baseline
- **Vector index:** `faiss-cpu` first, `faiss-gpu` when GPU path is stable
- **Fuzzy text matching:** `rapidfuzz`
- **Bulk lot card detection (Phase 6):** `ultralytics` (`YOLOv8`) or `RT-DETR` model

## Implementation Pattern

1. detect card regions and normalize crops with OpenCV
2. run OCR over card-relevant text regions
3. embed crops with OpenCLIP
4. query FAISS for top-K Scryfall candidates
5. compute a hybrid score combining embedding similarity + OCR agreement + title fuzz score
6. persist candidates and evidence for explainable ranking

## Operational Guidance

- version all models and matching/scoring formulas in DB
- keep a labeled validation set for regression checks
- evaluate OCR-only, embedding-only, and hybrid performance per release
- prefer deterministic post-processing over opaque heuristic drift

## Desktop GUI (operator application)

- **UI framework:** `PySide6` (Qt 6) — native window, `QTableView`, `QProcess`, `QTimer`
- **Default style:** Qt **Fusion**; optional dark palette via `qdarktheme` or custom `QPalette`
- **Not used for GUI:** Tkinter, Streamlit, Electron (see `gui-application.md`)
- **Scheduling (in-app):** `apscheduler` (GUI-6); headless: `ebay-workflows run-due-schedules` + Windows Task Scheduler
- **Packaging:** PyInstaller with PySide6 Qt libraries bundled

