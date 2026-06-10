# Post-Workflow Checklist

**Status:** **[Shipped]** operator runbook. Use when `scripts/rerun-phase5.ps1` or `scripts/reanalyze-matching.ps1` finishes (success or failure).

**Related:** `open-items-status.md` (P1–P4 backlog), `runbook-local.md`, `config-contract.md`.

---

## 1. Confirm the run finished

Check the log:

```powershell
Get-Content ./data/exports/phase5-rerun.log -Tail 30
Get-Content ./data/exports/phase5-rerun-out.log -Tail 5
```

| Outcome | Next step |
|---------|-----------|
| `Phase 5 re-run pipeline completed.` | Continue with §2 |
| `Phase 5 failed with exit …` | §6 triage; do not start another full pipeline until resolved |
| Process still running | `Get-Content ./data/exports/phase5-rerun-out.log -Wait -Tail 10` |

---

## 2. Validate pipeline output

```powershell
. ./scripts/activate-dev.ps1
.venv\Scripts\python.exe -m ebay_workflows.cli monitor-pipeline
.venv\Scripts\python.exe -m ebay_workflows.cli match-stats
.\scripts\post-reanalyze-validation.ps1
```

Record results in `open-items-status.md` (pipeline snapshot table).

| Metric | Healthy sign |
|--------|----------------|
| OCR results | >> 0 |
| Image detections | >> 0 |
| Verified candidates | **> 0** (primary goal) |
| Pricing-eligible | > 0 |
| rank_value > 0 | ideally > 0 if deals exist |
| Integrity check | exit 0 |

---

## 3. GUI smoke test

```powershell
pip install -e ".[gui]"   # if PySide6 not installed
.venv\Scripts\python.exe -m ebay_workflows.gui.qt_app
```

- **Opportunities** — ranked rows with thumbnails (if verified > 0)
- **Workflows** — no stale `running` steps (`list-stale-workflows`)
- **View → Dark theme** / workflow logs panel

---

## 4. If verified candidates are still 0

After a **successful** Phase 5 (OCR rows exist), triage before changing code:

1. `validate-env` — Tesseract on PATH, `FAISS_INDEX_READY`
2. Sample `evidence_json.pricing_reject_reason` in DB for a few candidates
3. Review `VERIFY_*` in `.env` (see `config-contract.md`)
4. Consider labeled crops under `tests/fixtures/labeled_crops/examples/`

Optional: refresh Cardmarket bulk if `validate-env` reports stale:

```powershell
.venv\Scripts\python.exe -m ebay_workflows.cli download-cardmarket-bulk --output ./data/cardmarket/prices.csv
.venv\Scripts\python.exe -m ebay_workflows.cli sync-cardmarket
.venv\Scripts\python.exe -m ebay_workflows.cli phase3-join-prices
.venv\Scripts\python.exe -m ebay_workflows.cli phase4-rank --hybrid
```

---

## 5. Optional follow-ups (pipeline)

Only after §2–§4 are stable:

| Task | Command / action |
|------|------------------|
| Phase 6 lot detection (CPU) | `$env:TORCH_DEVICE="cpu"` then `phase6-detect-lots --use-real-detection` → `phase4-rank --hybrid` |
| Prune orphan image cache | `ebay-workflows prune-image-cache` (dry-run) then `--execute` |
| Clear stale workflow rows | `ebay-workflows clear-stale-workflows --yes` |
| GitHub default branch → `main` | Repo Settings → Default branch |

---

## 6. Config restructure (implement after workflow)

**Goal:** Smaller `.env` (secrets + machine + overrides only); versioned tuning in checked-in YAML; `config.py` remains the schema.

### 6.1 Design (target layout)

```
.env                          # secrets, DATABASE_URL, eBay keys, machine paths, rare overrides
config/
  verification.yaml           # VERIFY_*, IMAGE_EVIDENCE_*, ALIGN_MIN_CONFIDENCE
  pricing.yaml                # CARDMARKET_CONDITION_MULTIPLIER_*, FX_*, EV_MAX_*
  matching.yaml               # TITLE_MATCH_*, FAISS_PROPOSE_CANDIDATES, phase skip flags
src/ebay_workflows/config.py  # Pydantic Settings; load YAML then env overrides
```

**Precedence (highest wins):** environment variables → `.env` → YAML profiles → `config.py` defaults.

### 6.2 Implementation tasks

- [ ] Add `config/verification.yaml`, `config/pricing.yaml`, `config/matching.yaml` with current production values from `.env.example`
- [ ] Extend `Settings` to load YAML (no new dependency if using stdlib only, or add `pyyaml` with approval)
- [ ] Add `APP_CONFIG_PROFILE` or `CONFIG_DIR` env var (default `./config`)
- [ ] Slim `.env.example` to required secrets + paths + operational overrides; add comment block pointing here
- [ ] Migrate operator `.env` — remove lines that match YAML defaults
- [ ] Update `scripts/activate-dev.ps1` — `py -3.12`, `pip install -e ".[dev,gpu,gui]"`
- [ ] Deprecate or document `IMAGE_DOWNLOAD_REQUESTS_PER_MINUTE` vs `GLOBAL_REQUESTS_PER_MINUTE_CAP`
- [ ] `validate-env` — print which values came from YAML vs env vs default
- [ ] Tests: YAML load, env override wins, missing required secret still fails

### 6.3 Files to update (code references)

| Area | Files |
|------|--------|
| Settings | `src/ebay_workflows/config.py` |
| CLI display | `src/ebay_workflows/cli/commands/env.py` |
| Scripts | `activate-dev.ps1`, `run-live-pipeline.ps1`, `rerun-phase5.ps1`, `reanalyze-matching.ps1` |
| Recognition adapter | `src/ebay_workflows/adapters/recognition_settings.py` |
| Tests | `tests/test_config_*.py` (add YAML coverage) |

---

## 10. Post-restructure smoke (after ADR 0002 / doc changes)

Run before marking a doc or layout PR complete:

- [ ] `ruff check .`
- [ ] `pytest -q` (includes `test_import_boundaries`, `test_repositories`)
- [ ] Optional: `scripts/run_sample_iterations.py --count 5 --max-images 2`
- [ ] Grep docs for stale layout: `rg "services/|workflow_phase" docs/` — hits should be **[Historical]** or audit records only
- [ ] Update `documentation-status.md` if new docs added (`trust-invariants.md`, `contributing-docs.md`, …)

---

## 7. Documentation updates (after config restructure)

- [ ] **`config-contract.md`** — split into “Environment (secrets & deploy)” vs “Config profiles (YAML)”; table per file
- [ ] **`documentation-status.md`** — index entry for this checklist + new config layout
- [ ] **`runbook-local.md`** — setup steps: minimal `.env`, optional YAML tuning, `validate-env` output
- [ ] **`open-items-status.md`** — mark config/doc tasks done; refresh pipeline snapshot
- [ ] **`docs/README.md`** — document map entry for `post-workflow-checklist.md`
- [ ] **`.env.example`** — minimal template + pointer to `config/*.yaml`
- [ ] **`large-scale-ingest.md`** / **`gui-build-prerequisites.md`** — install line `.[dev,gpu,gui]`; Python 3.12 note
- [ ] **`future-pain-points.md`** — close or update “monolithic .env” item if added

---

## 8. Environment hygiene (can do anytime)

- [ ] Disable Windows **App execution aliases** for `python.exe` / `python3.exe`
- [ ] Uninstall Store **Python 3.11** stub
- [ ] Remove duplicate `Python311\Scripts` entries from User PATH
- [ ] Do **not** recreate `.venv` while a pipeline process is running

---

## 9. Commit / PR checklist

When implementing §6–§7:

1. `ruff check .` and `pytest -q`
2. `validate-env` on slim `.env` + YAML defaults
3. Single PR: “Config profiles + slim .env + docs” (avoid splitting mid-migration)
4. Update `open-items-status.md` P4 metrics after next successful full validation run

---

## Quick reference — current vs target `.env` size

| Keep in `.env` | Move to `config/*.yaml` |
|----------------|-------------------------|
| `DATABASE_URL`, `EBAY_*_SECRET`, `EBAY_USE_SANDBOX` | `VERIFY_*`, `IMAGE_EVIDENCE_*` |
| `ENABLE_EBAY_API`, `DISABLE_LIVE_API_WRITES`, `APP_ENV` | `CARDMARKET_CONDITION_MULTIPLIER_*` |
| `IMAGE_CACHE_DIR`, `FAISS_INDEX_PATH`, `TESSERACT_CMD` | `TITLE_MATCH_*` (non-secret tuning) |
| `TORCH_DEVICE`, `GLOBAL_REQUESTS_PER_MINUTE_CAP` | `FX_GBP_TO_EUR`, `EV_MAX_*` |
| `CARDMARKET_BULK_FILE_PATH` | Phase skip flags (unless scripting overrides) |

Secrets and machine-specific paths **never** go in committed YAML.
