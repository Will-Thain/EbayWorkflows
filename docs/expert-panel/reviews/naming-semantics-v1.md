# Expert panel — Semantics & naming conventions v1

**Date:** 2026-06-10  
**Topic:** Project-wide vocabulary, identifier schemes, and naming consistency (post-M7)  
**Outcome:** **5/5 APPROVE WITH AMENDMENTS** — core semantics are **coherent**; **document a glossary** and fix **P1 alias drift** (CLI flags, evidence fields, favourite spelling)  
**Process:** [`process.md`](../process.md) · Unanimous for persisted-field names; majority for CLI/GUI labels

## Scope

Panel review of naming across:

- Packages/modules (`workflows/`, `candidates/`, `recognition/`, …)
- CLI commands vs GUI `job_id` vs `workflow_steps.step_name`
- ORM tables/columns and `evidence_json` keys
- Operator-facing strings (GUI, catalog labels)
- Config/env var prefixes
- Library ↔ consumer boundary terms (`printing_id`, `Proposal`, cascade fields)

**Question:** Are semantics predictable for contributors and operators? Where should naming converge without a breaking rename?

---

## Canonical vocabulary (adopted)

| Term | Meaning | Where used |
|------|---------|------------|
| **Listing** | One eBay offer row (`listings` table) | Phases, GUI, docs |
| **Candidate** | One possible printing match for a listing (`listing_card_candidates`) | Backend, DB, `candidates/` package |
| **Match** | Operator-facing label for a candidate in GUI previews | `MatchDetail`, `MatchRowWidget` — **presentation alias only** |
| **Phase** | Numbered pipeline stage (1–6); **execution order ≠ phase number** | Docs, `workflows/phase*.py` |
| **Workflow run / step** | Traceability rows (`workflow_runs`, `workflow_steps`) | Persistence, GUI monitor |
| **Verification** | Strict image gate outcome (`image_verified`, cascade `gate_status`) | Trust docs, Phase 5 |
| **Pricing eligibility** | Whether Phase 3 may attach Cardmarket price (`pricing_eligible`) | Phase 3, guardrails |

---

## Expert 1 — Domain language & documentation

**Specialty:** Operator docs, data dictionary, trust invariants

### Assessment

**Strengths**

- `data-dictionary.md` defines persisted fields clearly; `trust-invariants.md` separates cascade vs row policy.
- Phase **execution order** (2→5→3→6→4) is documented consistently in `workflow-phases.md`, `catalog.py` pipeline label, and `implementation-spec.md`.
- “Bulk lot” vs “single card” semantics are distinct in `listing_filters.py` and Phase 6 docs.

**Gaps**

| Issue | Severity | Example |
|-------|----------|---------|
| **Candidate vs match** undocumented | P1 | DB/`ListingCardCandidate` vs GUI `MatchDetail` — same entity, two words |
| **`source_method` vs `match_method`** | P1 | Column `source_method="title_match"`; Phase 2 stores `evidence_json["method"]` / `match_method` from title matcher — overlapping semantics |
| **Dual verification field names** | P1 | Cascade serialize: `verification_source`; consumer persist: `image_verification_source`; gate reads both paths (`candidate_gate.py:84`) |
| **Favourite spelling split** | P2 | UK UI: “Favourites”, “Favourited”; US code: `favorites.py`, `is_favorited`, `ListingFavorite`, `favorited_at` |
| **Phase 5 CLI name vs module** | P2 | CLI `phase5-verify-ocr`; module `recognition/phase5_analysis.py`; step `phase5_ocr_verification` — three labels, one phase |

### Vote

**APPROVE WITH AMENDMENTS** — Add a **one-page glossary** cross-linking GUI terms to DB terms.

### Actions (E1)

| ID | Action |
|----|--------|
| E1-1 | Add `docs/glossary.md`: Listing, Candidate, Match (GUI), verification vs pricing, bulk lot |
| E1-2 | Extend `data-dictionary.md` § Candidate: `source_method` vs `evidence_json.method` / `match_method` |
| E1-3 | Document `verification_source` (cascade) → `image_verification_source` (canonical persist) mapping |

---

## Expert 2 — CLI, catalog & job identifiers

**Specialty:** `ebay-workflows` command surface, `workflows/catalog.py`, scheduler

### Assessment

**Strengths**

- Kebab-case CLI commands (`phase2-match-title`, `run-resumable-pipeline`) are consistent and grep-friendly.
- `WORKFLOW_JOBS` maps stable **`job_id`** (`phase1`…`phase6`, `pipeline`, `sync_cm`) to argv builders — GUI and scheduler share one catalog.
- `workflow_steps.py` `STEP_TO_JOB` bridges DB `step_name` (`phase2_title_match`) → catalog `job_id` (`phase2`).

**Gaps**

| Issue | Severity | Evidence |
|-------|----------|----------|
| **Phase 1 has no `phase1-*` command** | P2 | Catalog `job_id=phase1` → CLI subcommand `run` (`catalog.py:16-17`) — only phase without numbered command |
| **`sync_cm` abbreviated job_id** | P2 | `job_id="sync_cm"` vs CLI `sync-cardmarket` — inconsistent abbreviation pattern |
| **Flag name drift Phase 6** | P1 | Pipeline/resume: `use_real_lot_detection`; Phase 6 executor: `use_real_detection`; CLI phase6: `use_real_detection`; pipeline CLI: `use_real_lot_detection` |
| **Phase 5 naming: verify vs analysis** | P2 | `phase5-verify-ocr` suggests OCR-only; catalog label “OCR + embeddings”; code path is full cascade |
| **`clear-match-data` vs table `listing_card_candidates`** | P2 | “Match” in CLI, “candidate” in schema — operator confusion |

**Naming layers (reference)**

| Layer | Pattern | Example |
|-------|---------|---------|
| `job_id` | short snake or `phaseN` | `phase5`, `sync_cm` |
| CLI command | `phaseN-verb-noun` or verb | `phase5-verify-ocr`, `run` |
| `step_name` | `phaseN_snake_description` | `phase5_ocr_verification` |
| Module | `workflows/phaseN.py` | `workflows/phase5.py` |

### Vote

**APPROVE WITH AMENDMENTS** — **Do not rename CLI commands** (breaking); align **flags and docs** first.

### Actions (E2)

| ID | Action |
|----|--------|
| E2-1 | Standardize Phase 6 flag: prefer `use_real_lot_detection` everywhere or alias in Typer with deprecation note |
| E2-2 | Document three-layer map (job_id / CLI / step_name) in `gui-application.md` or `glossary.md` |
| E2-3 | Optional future: add hidden alias `phase1-ingest` → `run` (non-breaking) |
| E2-4 | Rename catalog label Phase 5 → “Image cascade (OCR + embeddings)” for accuracy |

---

## Expert 3 — Persistence & `evidence_json` semantics

**Specialty:** ORM, JSON contracts, Alembic

### Assessment

**Strengths**

- Table names plural snake_case: `listings`, `listing_card_candidates`, `listing_scores` — consistent.
- Trust fields in `evidence_json` align with `trust-invariants.md`: `image_verified`, `pricing_eligible`, provenance trio.
- `detection_type` enum strings documented: `card_region`, `lot_card` (`data-dictionary.md`).
- `scryfall_id` FK naming matches Scryfall domain; library `printing_id` mapped at sync boundary (`candidate_sync.py:36`).

**Gaps**

| Issue | Severity | Evidence |
|-------|----------|----------|
| **`verification_source` vs `image_verification_source`** | P1 | Library/cascade rows may carry `verification_source`; consumer canonical output is `image_verification_source` — dual keys in same JSON during transition |
| **`source_method` values informal** | P2 | Known: `title_match`, `faiss_proposal`; events also log `faiss_search`, `set_collector` as `source_method` in match log — not all are column values |
| **`gate_status` not in data-dictionary table** | P1 | Written by cascade sync; gate depends on it — should be in dictionary |
| **Stats key naming** | P2 | `match_stats`: `verification_source_counts` aggregates `image_verification_source` — shortened key name |
| **Model class at root** | P2 | `ebay_workflows.models` vs package `persistence/` — naming implies persistence owns models (see legacy audit) |

### Vote

**APPROVE WITH AMENDMENTS** — **Unanimous:** do not rename JSON keys without migration; **document canonical set**.

### Actions (E3)

| ID | Action |
|----|--------|
| E3-1 | Add `evidence_json` rows for `gate_status`, `gate_fail_reason`, `verification_source` (cascade), `cascade_region_id` |
| E3-2 | Add `source_method` enum table in data-dictionary (allowed column values vs log-only strings) |
| E3-3 | Gate merge rule doc: when `gate_status` present, `image_verification_source` is authoritative for pricing |

---

## Expert 4 — Package & module naming

**Specialty:** ADR 0002 layout, import paths, file naming patterns

### Assessment

**Strengths**

- Layer names are **plural domains**: `workflows`, `candidates`, `operations`, `integrations` — clear roles.
- `candidate_*` modules under singular package `candidates/` — consistent prefix for row-policy SRP.
- `recognition/phase5_analysis.py` ties phase number to analysis entrypoint; other recognition modules are **capability-named** (`embedding_index`, `cascade_persist`).
- `cascade_bridge.py` clearly marks library boundary re-exports.

**Gaps**

| Issue | Severity | Evidence |
|-------|----------|----------|
| **Lot detection triple naming** | P1 | `bulk_lot_detection.py`, `listing_lot_detection.py` (re-export wrapper), `run_phase6_bulk_lot_detection`, CLI `phase6-detect-lots` |
| **Crop match pair** | P2 | `region_crop_match.py` (low-level cascade), `lot_crop_match.py` (Settings wrapper) — “region” vs “lot” unclear |
| **`image_evidence.py` facade** | P2 | Re-exports gate/selection — name sounds like persistence, lives in `candidates/` |
| **`sync_cm` vs `operations/`** | P2 | Cardmarket sync is operational but CLI lives under ingest + catalog job |
| **Metrics module** | ✅ | `operations/metrics.py` — Tier 7 keys `tier7_*` match library tier vocabulary |

**Adopted module naming rules**

| Package | File pattern | Example |
|---------|--------------|---------|
| `workflows/` | `phaseN.py` | `phase5.py` |
| `candidates/` | `candidate_<verb>.py` | `candidate_sync.py` |
| `recognition/` | `<capability>.py` or `phaseN_*` for phase entry | `cascade_persist.py`, `phase5_analysis.py` |
| `operations/` | `<noun>.py` or `<noun>_<aspect>.py` | `ranked_export.py` |
| `scoring/` | domain noun | `hybrid_scoring.py` |

### Vote

**APPROVE WITH AMENDMENTS** — Consolidate **lot** naming in docs; defer file renames unless touching Phase 6.

### Actions (E4)

| ID | Action |
|----|--------|
| E4-1 | Document in `architecture.md`: `bulk_lot_detection` = CV detect; `listing_lot_detection` = Phase 6 adapter; `lot_crop_match` = per-card ID |
| E4-2 | Consider renaming `image_evidence.py` → `candidate_policy.py` only if imports churn acceptable (P3) |
| E4-3 | Fix `listing_lot_detection.py` self-import `..recognition.catalog_index` → `.catalog_index` (path smell) |

---

## Expert 5 — Config, env vars & cross-repo alignment

**Specialty:** `config.py`, library `RecognitionSettings`, identifier alignment

### Assessment

**Strengths**

- Env aliases SCREAMING_SNAKE; Python fields snake_case — Pydantic standard.
- Trust knobs prefixed **`VERIFY_*`** — discoverable and documented in `config-contract.md`.
- Phase-scoped flags prefixed **`PHASE1_*` … `PHASE6_*`** — clear ownership.
- CV/FAISS prefixed **`FAISS_*`**, **`IMAGE_*`**, **`OPENCLIP_*`** — grouped by subsystem.
- `coerce_recognition_settings` / `RecognitionSettings` — explicit adapter boundary.

**Gaps**

| Issue | Severity | Evidence |
|-------|----------|----------|
| **`IMAGE_DOWNLOAD_REQUESTS_PER_MINUTE` orphan** | P1 | Field exists; downloads use `GLOBAL_REQUESTS_PER_MINUTE_CAP` |
| **Mixed phase vs behavior prefixes** | P2 | `phase5_skip_analyzed_images` vs `verify_name_hard_min` — both Phase 5 related, different prefixes (acceptable if documented) |
| **`printing_id` vs `scryfall_id`** | P1 (semantic) | Library proposals use `printing_id`; ORM `scryfall_id` — same UUID, different names at boundary (document, don’t unify ORM) |
| **`paddleocr` in deps, Tesseract in production** | P2 | `OCR_ENGINE` default `pytesseract`; package name suggests alternate backend |
| **Tier 7 metrics vs phase numbers** | ✅ | Metrics use library tier index, not workflow phase — correct |

### Vote

**APPROVE WITH AMENDMENTS** — Env taxonomy is **good**; remove or wire dead fields.

### Actions (E5)

| ID | Action |
|----|--------|
| E5-1 | Remove or deprecate `IMAGE_DOWNLOAD_REQUESTS_PER_MINUTE`; document in `config-contract.md` |
| E5-2 | Add `config-contract.md` § Prefix guide: `VERIFY_`, `PHASEn_`, `FAISS_`, `EBAY_`, … |
| E5-3 | Add boundary note: library `printing_id` ≡ consumer `scryfall_id` for MTG printings |

---

## Phase C — Final votes

| Agent | Specialty | Vote |
|-------|-----------|------|
| 1 | Domain language & docs | APPROVE WITH AMENDMENTS |
| 2 | CLI & catalog identifiers | APPROVE WITH AMENDMENTS |
| 3 | Persistence & evidence_json | APPROVE WITH AMENDMENTS |
| 4 | Package & module naming | APPROVE WITH AMENDMENTS |
| 5 | Config & cross-repo terms | APPROVE WITH AMENDMENTS |

**Result: 5/5 APPROVE WITH AMENDMENTS**

---

## Consolidated naming backlog

### P0 — Glossary (zero breaking changes)

| ID | Action |
|----|--------|
| P0-1 | Create `docs/glossary.md` with canonical vocabulary table |
| P0-2 | Link from `docs/README.md` and `contributing-docs.md` |

### P1 — Document & align semantics (non-breaking)

| ID | Action | Status |
|----|--------|--------|
| P1-1 | Extend `data-dictionary.md`: `gate_status`, `source_method` enum, verification field map | ✅ |
| P1-2 | Unify Phase 6 flag naming (`use_real_lot_detection` + deprecated CLI alias) | ✅ |
| P1-3 | Document lot-module naming in `architecture.md` | ✅ |
| P1-4 | Remove `IMAGE_DOWNLOAD_REQUESTS_PER_MINUTE` | ✅ |
| P1-5 | `config-contract.md` env prefix guide | ✅ |

### P2 — UX copy & minor consistency

| ID | Action | Status |
|----|--------|--------|
| P2-1 | GUI: UK “Favourite” in UI; US module names documented in `favorites.py` | ✅ |
| P2-2 | Catalog Phase 5 label → “Image cascade (OCR + embeddings)” | ✅ |
| P2-3 | CLI help: `clear-match-data` mentions candidate rows | ✅ |
| P2-4 | Fix `listing_lot_detection.py` relative import | ✅ |

### P3 — Optional renames (breaking / churn)

| ID | Action | Risk |
|----|--------|------|
| P3-1 | CLI alias `phase1-ingest` → `run` | Low |
| P3-2 | Rename `image_evidence.py` → `candidate_policy.py` | Medium import churn |
| P3-3 | Rename `sync_cm` → `sync_cardmarket` in catalog | Breaks saved GUI schedules |
| P3-4 | ORM rename `scryfall_id` → `printing_id` | **Rejected** — DB migration |

---

## Rejected proposals

| ID | Proposal | Reason |
|----|----------|--------|
| R-N1 | Rename all GUI “match” to “candidate” | Operator-friendly “match” is intentional presentation layer |
| R-N2 | Rename CLI `phase5-verify-ocr` | Breaking for scripts, Task Scheduler, GUI catalog |
| R-N3 | Unify UK/US favourite spelling in code | DB column `favorited_at` not worth migration |
| R-N4 | Single word for all step identifiers | Three-layer scheme (job_id / CLI / step_name) is stable |

---

## Semantics health summary

| Dimension | Grade | Note |
|-----------|-------|------|
| Phase numbering vs execution order | ✅ A | Well documented |
| Package layout names | ✅ A | ADR 0002 consistent |
| Trust field vocabulary | 🟡 B+ | Dual keys during cascade transition — document |
| CLI / catalog / step alignment | 🟡 B | Phase 1 exception; flag drift Phase 6 |
| GUI vs backend terms | 🟡 B | Candidate/Match split needs glossary |
| Config env taxonomy | ✅ A- | One dead field |
| Library boundary terms | 🟡 B+ | printing_id vs scryfall_id — document only |

---

## Related

- `docs/data-dictionary.md` — field definitions
- `docs/trust-invariants.md` — verification semantics
- `docs/expert-panel/reviews/codebase-improvement-v1.md` — structural improvements
- `docs/adr/0002-package-restructure.md` — package naming rationale
