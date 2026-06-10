# Contributing to documentation

**Status:** **[Shipped]** maintainer guide. Tags: `documentation-status.md`.

Use this map when changing code so docs stay aligned with `main`.

## Status tags

Before editing, read `documentation-status.md`. Tag each claim:

- **[Shipped]** — matches code on `main`
- **[Historical]** — audit only; do not restore behavior
- **[Future]** — planned or partial

After a milestone (package move, new phase behavior), update the **status index** and grep `docs/` for stale paths.

## Code change → doc to edit

| If you change… | Update these docs |
|----------------|-------------------|
| `workflows/phase*` behavior or order | `workflow-phases.md`, `architecture.md` sequence diagram |
| Phase acceptance criteria | `workflow-phases.md`, `product-requirements.md` |
| `recognition/*` or library integration | `card-recognition-architecture.md`, sibling `mtg-card-recognition/docs/integration/ebay-workflows.md` |
| `candidates/*` gate / selection | `trust-invariants.md`, `data-dictionary.md`, `ranking-and-confidence.md` |
| `scoring/*` EV or guardrails | `ranking-and-confidence.md`, `future-pain-points.md` (if closing items) |
| `operations/*` export, health, sample | `runbook-local.md`, `testing-strategy.md` |
| `persistence/*` repos or schema | `data-model.md`, `data-dictionary.md` |
| `models.py` columns / constraints | `data-model.md`, new Alembic revision under `alembic/versions/` |
| `config.py` / env vars | `config-contract.md`, `.env.example` |
| `gui/*` (no library imports) | `gui-application.md`, `gui-operator-workflows.md` |
| Package layout or imports | `architecture.md`, `implementation-spec.md`, `adr/0002-package-restructure.md` |
| CI tests for verification | `testing-strategy.md`, `trust-invariants.md` |
| Operator runbooks / scripts | `runbook-local.md`, `post-workflow-checklist.md`, `open-items-status.md` |

## Grep hygiene (after package moves)

From repo root, scan for stale layout language:

```powershell
rg "services/|workflow_phase|TEMP shim|today ``" docs/
```

Expected hits: **[Historical]** sections, ADR migration records, expert panel reviews — not “current behavior” paragraphs.

## Review triggers

Consult `expert-panel/process.md` when:

- Moving verification policy between consumer and library
- Changing GUI to in-process CV (**reject**)
- Major doc refresh after milestones — see `expert-panel/reviews/documentation-audit-v1.md`

## Related

- `documentation-status.md` — full doc index
- `post-workflow-checklist.md` §7 — doc updates after pipeline runs
- `implementation-spec.md` — canonical module tree
