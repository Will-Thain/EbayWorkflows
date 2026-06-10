# ADR 0001: Initial Tech Stack

## Status

Accepted (updated **2026-06-10** for v0.3.2 consumer boundary — see ADR 0002)

## Context

The project requires a local-first workflow CLI with PostgreSQL persistence, image-assisted card matching, and strict integration safety controls.

## Decision

- local CLI + optional PySide6 GUI with **QProcess** phase isolation (no in-process CV in GUI)
- PostgreSQL for workflow and artifact persistence
- **`mtg-card-recognition`** sibling repo — image cascade only (zones, OCR, embeddings, Tier 8 gate, serialize)
- **EbayWorkflows** owns: ingest, ORM, candidate row policy (`candidates/`), scoring, phases
- OpenCV, OpenCLIP, FAISS, Tesseract **[Shipped]**; PaddleOCR **[Future]**
- RapidFuzz for Phase 2 title match **[Shipped]**
- Cardmarket bulk files (no live API) **[Shipped]**
- Strict verification: OCR/FAISS/mana never alone verify; provenance on attach **[Shipped]**

```mermaid
flowchart LR
  LIB[mtg-card-recognition] -->|ImageAnalysisResult| REC[recognition/]
  REC --> CAND[candidates/]
  CAND --> DB[(Postgres)]
```

## API safety

- shared rate-limit middleware; explicit provider budgets
- authorized endpoints only; fail fast on policy violations

## Consequences

- hybrid matching vs vision-only
- library SRP enables independent cascade evolution (v0.3.2 removed eBay shims from library)
- row policy colocated with ORM in consumer

## Revisit triggers

- provider policy changes
- FAISS scale (IVF/PQ, Milo catalog)
- OCR accuracy on eBay crops
- package migration completion (ADR 0002 M7)

## Related

- `adr/0002-package-restructure.md`
- `card-recognition-architecture.md`
- `documentation-status.md`
