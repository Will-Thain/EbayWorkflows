# Expert panel (EbayWorkflows)

Architecture and package decisions for **EbayWorkflows** follow the same consultation model as **mtg-card-recognition**.

## Process reference

Normative process and decision rules: [`mtg-card-recognition/docs/expert-panel/process.md`](../../mtg-card-recognition/docs/expert-panel/process.md)

- **Unanimous** — trust invariants (verification policy, pricing eligibility)
- **Majority (3/5)** — package layout, migration order, docs structure
- **Expert lead** — agent whose specialty owns the change writes the first draft

## Reviews (this repo)

| Review | Date | Topic | Outcome |
|--------|------|-------|---------|
| [ebay-restructure-v1](reviews/ebay-restructure-v1.md) | 2026-06-10 | Package layout post v0.3.2 | **5/5 APPROVE WITH AMENDMENTS** |
| [documentation-audit-v1](reviews/documentation-audit-v1.md) | 2026-06-10 | Post–M7 documentation accuracy & improvement outlook | **5/5 APPROVE WITH AMENDMENTS** |
| [legacy-code-audit-v1](reviews/legacy-code-audit-v1.md) | 2026-06-10 | Legacy code findings verification (M7 shims, compat paths) | **5/5 CONFIRM WITH AMENDMENTS** |

## When to consult

- Changing package boundaries (`recognition/`, `candidates/`, `workflows/`)
- Moving verification policy between consumer and library
- GUI in-process CV (always **REJECT**)
- Phase execution order changes
- Major documentation refresh after milestone completion (see [documentation-audit-v1](reviews/documentation-audit-v1.md))
- Post-milestone legacy code / shim audits (see [legacy-code-audit-v1](reviews/legacy-code-audit-v1.md))

## Related ADRs

- `docs/adr/0002-package-restructure.md`
