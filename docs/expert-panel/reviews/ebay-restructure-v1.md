# Expert panel — EbayWorkflows package restructure v1

**Date:** 2026-06-10  
**Topic:** Package layout after mtg-card-recognition v0.3.2 SRP split  
**Outcome:** **5/5 APPROVE WITH AMENDMENTS** — proceed per `adr/0002-package-restructure.md` milestones M1–M7  
**Process:** [`mtg-card-recognition/docs/expert-panel/process.md`](../../mtg-card-recognition/docs/expert-panel/process.md)

## Proposal under vote

Restructure EbayWorkflows into: `recognition/` (sole library boundary), `candidates/` (row policy), `workflows/` (thin phases), `persistence/` (repos), `scoring/`, `operations/`, with GUI subprocess-only and incremental migration shims.

## Phase C — Final votes

| Agent | Specialty | Vote |
|-------|-----------|------|
| 1 | Application architecture | APPROVE WITH AMENDMENTS |
| 2 | Workflow orchestration | APPROVE |
| 3 | Data / persistence | APPROVE WITH AMENDMENTS |
| 4 | Systems / migration | APPROVE WITH AMENDMENTS |
| 5 | Trust / verification | APPROVE |

## Adopted P0 actions

| ID | Action |
|----|--------|
| H-1 | `recognition/` only import path to `mtg_card_recognition` + CI lint |
| H-2 | Extract `candidates/` from `services/candidate_*` |
| H-3 | Thin `workflows/` — no direct library types in phase files |
| H-4 | Incremental migration M1–M7 with re-export shims |
| H-5 | GUI stays QProcess-only |
| H-6 | Docs: confirm layer = library Tier 8 + consumer `candidates/` |
| H-7 | Shared `workflows/catalog.py` for CLI + GUI |
| H-8 | Collapse Phase 5 dual attach before `candidates/` rename |
| H-9 | Contract tests in CI: `test_evidence_gate`, `test_cascade_persist`, import boundaries |

## Rejected / deferred

| ID | Item |
|----|------|
| R-1 | Big-bang `models.py` split — defer until Alembic + repos (M6) |
| R-2 | Delete `services/` in one PR — use shims until M7 |
| R-3 | Move `catalog_index` to `persistence/` — stays in `recognition/` (ORM→library bridge) |

## Full deliberation

See chat record 2026-06-10 — architecture review with five domain experts (application architecture, workflow orchestration, data layer, systems migration, trust/verification).
