# Expert panel — Legacy code audit v1

**Date:** 2026-06-10  
**Topic:** Verification of post–ADR 0002 legacy-code findings (M7 shims, compat paths, dead branches)  
**Outcome:** **5/5 CONFIRM FINDINGS WITH AMENDMENTS** — no parallel legacy codebase; **commit M7 deletions** before calling migration complete on `main`  
**Process:** [`process.md`](../process.md) · Majority for cleanup priority; unanimous for trust-path classification

## Scope

Independent panel review of an automated legacy-code audit (2026-06-10). Cross-checked:

- `src/ebay_workflows/` package tree and import graph
- Git index vs working tree for `services/` and `workflow_phase*.py`
- `tests/` (126 passed at review time)
- `scripts/` migration tooling
- ADR 0002 M7 intent vs current tree

**Question:** Are the audit’s legacy-code findings accurate? What should be fixed next?

---

## Findings under verification

| ID | Audit claim | Severity |
|----|-------------|----------|
| F1 | `services/` + `workflow_phase*.py` deleted on disk; **37 files uncommitted** | P0 |
| F2 | No live `src/` or `tests/` imports of `services` or `workflow_phase` | — (clean) |
| F3 | Thin compat shims remain: `db.py`, `persistence/models.py`, `gui/workflow_catalog.py`, `recognition/regions.py` | Intentional |
| F4 | Root `models.py` is canonical ORM; `persistence/models.py` re-exports (docs inverted) | P2 |
| F5 | Repositories are read/query-only; phases still write via `session.add` | P2 (deferred) |
| F6 | `candidate_gate` fallback when `gate_status` absent (pre-cascade DB rows) | Intentional |
| F7 | Phase 5 `--mock-ocr-file` path bypasses cascade attach | Intentional dev path |
| F8 | Phase 5 `if analysis.cascade is None` inside `cascade_regions_from_analysis` loop is **unreachable** | P1 |
| F9 | `progress_report._PROGRESS_LEGACY` regex for old stdout format | Intentional |
| F10 | `faiss_proposal` rows are optional feature, not layout legacy | Rejected as legacy |
| F11 | One-off migration scripts (`fix_migration_imports.py`, `migrate_imports_m7.py`, `split_cli.py`) | P3 |
| F12 | `finish_ranking_debug.py` log says `workflow_phase4` but imports `workflows.phase4` | P3 |
| F13 | No second parallel implementation / legacy codebase | Confirmed |

---

## Expert 1 — Application architecture

**Specialty:** Package boundaries, import graph, shim policy

### Verification

| Finding | Verdict | Evidence |
|---------|---------|----------|
| F1 | **CONFIRM** | `git status` shows `D` for 31 `services/*` + 6 `workflow_phase*.py`; directory absent on disk |
| F2 | **CONFIRM** | `rg 'services\.|workflow_phase|ebay_workflows\.services' src/` → zero hits |
| F3 | **CONFIRM intentional** | Shims are one-liner re-exports; no duplicate business logic |
| F13 | **CONFIRM** | Single implementation under layered packages; import-boundary CI enforces library rule |

**Amendment:** F3 — `persistence/models.py` docstring claims “canonical import path” while re-exporting root `models.py` (see Expert 3). Architecture docs should not describe both as canonical.

### Vote

**CONFIRM WITH AMENDMENTS** — M7 code removal is real locally; **origin/main still ships shims until commit**.

### Actions (E1)

| ID | Action |
|----|--------|
| E1-1 | Commit M7 deletions + new packages as one logical changeset |
| E1-2 | Add CI grep gate (optional): fail if `src/ebay_workflows/services/` reappears |
| E1-3 | Fix `persistence/models.py` module docstring to “Alembic import surface; definitions in `ebay_workflows.models`” |

---

## Expert 2 — Workflow orchestration

**Specialty:** Phase executors, Phase 5 attach paths, CLI/GUI catalog

### Verification

| Finding | Verdict | Evidence |
|---------|---------|----------|
| F7 | **CONFIRM intentional** | `cli/commands/phases.py` exposes `--mock-ocr-file`; `_process_mock_row` uses region attach without cascade — dev/CI shortcut |
| F8 | **CONFIRM dead code** | `cascade_regions_from_analysis` returns `[]` when `analysis.cascade is None` (`cascade_persist.py:62–63`); loop body at `phase5.py:365` never runs on real OCR path |
| F3 `gui/workflow_catalog` | **CONFIRM** | Re-export of `workflows/catalog.py`; scheduler + GUI share one catalog — matches ADR H-7 |

**Amendment:** F7 — not “legacy layout”; document in `testing-strategy.md` as non-production attach path only.

### Vote

**CONFIRM WITH AMENDMENTS** — Remove F8 dead branch; keep mock OCR until labeled-crop CI replaces it.

### Actions (E2)

| ID | Action |
|----|--------|
| E2-1 | Delete unreachable `if analysis.cascade is None` block in `phase5._persist_analysis` |
| E2-2 | Tag mock OCR path in `phase5.py` module docstring or CLI help as **[Dev only]** |
| E2-3 | After F8 removal, run full `pytest -q` + one Phase 5 smoke |

---

## Expert 3 — Data / persistence

**Specialty:** ORM location, Alembic, repositories

### Verification

| Finding | Verdict | Evidence |
|---------|---------|----------|
| F4 | **CONFIRM** | `models.py` ~250 lines of SQLAlchemy models; `persistence/models.py` is `from ebay_workflows.models import *` |
| F5 | **CONFIRM partial** | `CandidateRepository` / `ListingRepository` / `ListingScoreRepository` — query methods only; phases 1–6 use `session.add` / `delete` for writes |
| F3 `db.py` | **CONFIRM intentional** | Used by `cli_context.py`, `scheduler.py`; points at `persistence.session` |

**Amendment:** F4 aligns with ADR **R-1** (defer `models.py` split until Alembic + repos). Not a migration bug — **documentation inversion** only.

### Vote

**CONFIRM** — Repository write migration remains deferred per ADR; no rollback to `services/`.

### Actions (E3)

| ID | Action |
|----|--------|
| E3-1 | Update `data-model.md` / `implementation-spec.md`: ORM definitions live in `ebay_workflows.models`; `persistence.models` is Alembic metadata import |
| E3-2 | Defer repository write helpers until next persistence milestone (non-blocker) |

---

## Expert 4 — Systems / migration

**Specialty:** Git state, migration scripts, operator tooling

### Verification

| Finding | Verdict | Evidence |
|---------|---------|----------|
| F1 | **CONFIRM critical gap** | Working tree = post-M7; `main...origin/main` with large unstaged migration — **docs claim M7 shipped but remote may not** |
| F11 | **CONFIRM** | `fix_migration_imports.py`, `migrate_imports_m7.py`, `split_cli.py` are untracked one-offs; not imported at runtime |
| F12 | **CONFIRM cosmetic** | `finish_ranking_debug.py:28` log string stale; import at `:29` is correct |
| F9 | **CONFIRM intentional** | Legacy progress regex preserves GUI parsing for older log files |

**Amendment:** F1 severity is **process**, not runtime — local installs use new paths; risk is **stale clone / partial pull** until commit.

### Vote

**CONFIRM WITH AMENDMENTS** — Treat uncommitted M7 as **P0 release hygiene**, not code defect.

### Actions (E4)

| ID | Action |
|----|--------|
| E4-1 | Commit full ADR 0002 tree (deletions + new packages + tests) |
| E4-2 | After commit, move migration scripts to `scripts/archive/` or delete |
| E4-3 | Fix `finish_ranking_debug.py` log line when touching scripts |

---

## Expert 5 — Trust / verification

**Specialty:** Verification policy, evidence rows, cascade gate

### Verification

| Finding | Verdict | Evidence |
|---------|---------|----------|
| F6 | **CONFIRM intentional** | `candidate_gate.evaluate_image_verification`: when `gate_status is not None`, cascade wins; else zone heuristics (lines 79–107) for rows without cascade fields |
| F6 tests | **PARTIAL COVERAGE** | `test_cascade_blocked_not_upgraded_by_legacy_heuristics` covers blocked rows; **no test** for no-`gate_status` fallback alone |
| F10 | **REJECT as legacy** | `faiss_proposal` is gated optional insert; still subject to row policy — current design |
| F8 trust impact | **NONE** | Dead branch does not weaken gate; cascade attach path is production |

**Amendment:** F6 fallback must remain until operator **post-consensus reanalyze** backfills `gate_status` on all priced rows. Removal requires **data migration criterion**, not code-only delete.

### Vote

**CONFIRM** — Trust invariants intact; legacy = **data-shape compat**, not OR-gate revival.

### Actions (E5)

| ID | Action |
|----|--------|
| E5-1 | Add test: evidence without `gate_status` + strict set/collector still evaluates (documents F6) |
| E5-2 | Document F6 sunset: remove fallback after reanalyze + grep DB for missing `gate_status` on Phase 5 rows |
| E5-3 | Do **not** remove F6 until E5-2 criterion met (unanimous) |

---

## Phase C — Final votes

| Agent | Specialty | Vote |
|-------|-----------|------|
| 1 | Application architecture | CONFIRM WITH AMENDMENTS |
| 2 | Workflow orchestration | CONFIRM WITH AMENDMENTS |
| 3 | Data / persistence | CONFIRM |
| 4 | Systems / migration | CONFIRM WITH AMENDMENTS |
| 5 | Trust / verification | CONFIRM |

**Result: 5/5 CONFIRM FINDINGS WITH AMENDMENTS**

---

## Consolidated verdict on audit claims

| Claim | Panel consensus |
|-------|-----------------|
| No parallel legacy codebase | **Unanimous CONFIRM** |
| M7 shims removed locally, uncommitted | **Unanimous CONFIRM (P0 commit)** |
| Intentional compat shims (4 files) | **Unanimous CONFIRM — keep** |
| ORM at root, persistence re-export | **CONFIRM — doc fix only (P2)** |
| Read-only repositories | **CONFIRM — deferred per ADR (P2)** |
| Pre-cascade gate fallback | **CONFIRM — keep until reanalyze (trust)** |
| Phase 5 dead `cascade is None` branch | **CONFIRM — safe to delete (P1)** |
| Mock OCR path | **CONFIRM — dev path, not layout legacy** |
| Migration scripts / debug log | **CONFIRM — P3 cleanup after commit** |
| `faiss_proposal` = legacy | **REJECTED — current optional feature** |

---

## Adopted priority backlog

### P0 — Migration truth on `main`

| ID | Action | Owner | Status |
|----|--------|-------|--------|
| P0-1 | Commit M7 deletion of `services/` + `workflow_phase*.py` with new package tree | Systems | ✅ |
| P0-2 | Verify CI runs `test_import_boundaries` on committed tree | Architecture | ✅ |

### P1 — Safe code cleanup

| ID | Action | Owner | Status |
|----|--------|-------|--------|
| P1-1 | Remove dead Phase 5 branch (`phase5.py` ~365) | Workflow | ✅ |
| P1-2 | Add `test_evidence_gate` case for missing `gate_status` (document F6) | Trust | ✅ |

### P2 — Clarity (non-blocker)

| ID | Action | Owner | Status |
|----|--------|-------|--------|
| P2-1 | Fix ORM location narrative in `data-model.md` / `implementation-spec.md` | Data | ✅ |
| P2-2 | Fix `persistence/models.py` docstring | Architecture | ✅ |

### P3 — Hygiene after P0

| ID | Action | Owner | Status |
|----|--------|-------|--------|
| P3-1 | Archive or delete migration scripts | Systems | ✅ → `scripts/archive/` |
| P3-2 | Fix `finish_ranking_debug.py` log string | Systems | ✅ |

### Rejected / deferred (unanimous)

| ID | Item | Reason |
|----|------|--------|
| R-L1 | Remove `candidate_gate` no-`gate_status` fallback now | Pre-reanalyze DB rows may lack cascade fields |
| R-L2 | Remove mock OCR before labeled-crop CI | Still useful for dev; not production default |
| R-L3 | Remove `_PROGRESS_LEGACY` regex | Low cost; helps old logs |
| R-L4 | Classify `faiss_proposal` as legacy | Active optional feature behind gate |

---

## Rejected audit overstating

| Audit phrasing | Panel correction |
|----------------|------------------|
| “Second legacy codebase” | **No** — only shims + compat branches |
| “M7 complete on main” | **Only true after commit** — local vs remote gap |
| “models.py is shim” | **Inverted** — root is source; persistence is import surface |

---

## Related

- `docs/adr/0002-package-restructure.md` — M7 milestone
- `docs/expert-panel/reviews/ebay-restructure-v1.md` — original layout vote
- `docs/expert-panel/reviews/documentation-audit-v1.md` — doc parity (parallel effort)
- `tests/test_import_boundaries.py` — enforceable architecture truth
