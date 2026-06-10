# CV / OCR roadmap (non-blockers)

**Status:** **[Future]** — production path remains Tesseract + OpenCLIP + FAISS. Tags: `documentation-status.md`.

## PaddleOCR backend

- **Today:** `Settings.ocr_engine` supports `pytesseract` in production; PaddleOCR is enum-ready in library config only.
- **To ship:** accuracy benchmark on labeled crops, env wiring in `adapters/recognition_settings.py`, Phase 5 regression via `test_phase5_matching.py` + sample iterations.
- **Owner docs:** `card-recognition-architecture.md`, sibling `mtg-card-recognition` OCR modules.

## Milo / alternate embedder

- **Today:** OpenCLIP `ViT-B-32` + FAISS index (`recognition/embedding_index.py`).
- **To ship:** offline eval on zone crops, index rebuild script, pin model in FAISS meta JSON.
- **Reference only:** CollectorVision / scryglass — see `library-stack.md`.

## Labeled crop CI regression

- **Canonical fixtures:** `../mtg-card-recognition/tests/fixtures/labeled_crops/`
- **Consumer pointer:** `tests/fixtures/labeled_crops/README.md`
- **Curate:** `scripts/curate_labeled_crops.py` → sibling clone
- **CI today:** `tests/test_labeled_crops_manifest.py` (manifest + script presence); full PNG regression runs in **mtg-card-recognition** when crops ≥512 B.

## When to revisit

After Phase 5 sample iterations show stable verification rates on fresh singles, prioritize PaddleOCR A/B before Milo embedder swap.

## Related

- `open-items-status.md` P2 items 5–7
- `testing-strategy.md` — smoke tiers
- `trust-invariants.md` — verification rules unchanged by OCR backend
