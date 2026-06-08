# Documentation Status Labels

Use these tags when reading or editing docs so **shipped code**, **historical behavior**, and **planned work** are not confused.

## Tags

| Tag | Meaning |
|-----|---------|
| **[Shipped]** | Implemented on branch `feature/card-recognition-package` (or `main` after merge). Describes current production behavior. |
| **[Historical]** | Describes behavior **before** the consensus gate / `mtg_card_recognition` extraction. Kept for audit and before/after comparison — **do not restore**. |
| **[Future]** | Planned, partial, or tunable — **not final** production behavior. May exist as config flags or stubs without full validation. |

When a line mixes shipped and planned parts, tag each clause: e.g. “FAISS corroboration **[Shipped]**; Milo embedder **[Future]**”.

## Canonical docs (match code today)

| Document | Status |
|----------|--------|
| `card-recognition-architecture.md` | **[Shipped]** spec + **[Historical]** audit sections (labeled in-doc) |
| `workflow-phases.md` | **[Shipped]** phase order and Phase 5 gate |
| `config-contract.md` | **[Shipped]** env vars |
| `data-dictionary.md` | **[Shipped]** `evidence_json` verification fields |
| `ranking-and-confidence.md` | **[Shipped]** guardrails; some formulas **[Future]** tuning |
| `library-stack.md` | **[Shipped]** stack; PaddleOCR/Milo **[Future]** |

## Docs with mixed / operational status

| Document | Notes |
|----------|--------|
| `future-pain-points.md` | Per-section tags; ingest/infra mostly **[Shipped]**; §6 search quality mixes **[Shipped]** + **[Future]** |
| `large-scale-ingest.md` | Runbook **[Shipped]**; troubleshooting rows tagged inline |
| `architecture.md` | High-level **[Shipped]**; detail deferred to `card-recognition-architecture.md` |
| `development-roadmap.md` | Milestones tagged **[Shipped]** / **[Future]** |
| `integration-specs.md` | API contracts **[Shipped]**; CV detail in architecture doc |

## Code map (for doc authors)

| Concern | Location |
|---------|----------|
| Recognition library | `src/mtg_card_recognition/` |
| eBay adapter | `src/ebay_workflows/adapters/recognition_settings.py` |
| Service shims | `src/ebay_workflows/services/{image_evidence,card_zones,…}.py` |
| Strict gate | `mtg_card_recognition.evidence` |

Last full doc sync for consensus gate: 2026-06-08 (branch `feature/card-recognition-package`).
