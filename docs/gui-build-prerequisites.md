# GUI Build Prerequisites

Checklist and **locked defaults** before implementing the desktop app. See `gui-application.md` for full UI spec.

## Ready-to-build checklist

- [x] Desktop platform: **PySide6** (Qt 6; no browser)
- [x] Schema sketched: `listing_favorites`, `scheduled_jobs` in `data-model.md`
- [x] Operator workflows documented in `gui-operator-workflows.md`
- [ ] Run `ebay-workflows init-db` after pulling models (creates new tables via `create_all`)
- [ ] Confirm `[gui]` optional dependency approved (`pyside6`; `apscheduler` deferred to GUI-6)
- [ ] Qt runtime smoke: `python -c "from PySide6.QtWidgets import QApplication"` succeeds after install
- [ ] Hugging Face / Tesseract available if scheduling Phase 5 headless later

## Locked product decisions

| Topic | Decision |
|-------|----------|
| Primary workflow | Nightly **ingest** (scheduled) → morning **rank** → **Opportunities** review → **favourites** for follow-up |
| Schedule granularity | **One CLI job per schedule** (not full pipeline in v1); operator chains via multiple schedules |
| “Promising” default | Sort `rank_value DESC`, limit 50, hybrid scores only |
| Favourites | Star + optional note; **CASCADE** delete when listing removed; show last known scores |
| Long jobs on schedule | **Allow:** `phase1`, `phase2`, `phase3`, `phase4`, `sync_cm`. **Discourage:** `phase5`, `phase6` (UI warning) |
| GUI closed schedules | **Yes** — Windows Task Scheduler runs `ebay-workflows run-due-schedules` every 5 min |
| Timezone | Store UTC; display **system local** (`datetime.now().astimezone()`) |
| Catch-up missed runs | Default **false** (skip missed); per-schedule opt-in |
| Global job mutex | **One heavy child process at a time** (any phase) |
| Stale `workflow_steps` | After stop/kill, show warning; operator may re-run phase |
| DB browser v1 | **Curated queries only**; no ad-hoc SQL |
| Table size | Load top **200** ranked rows max per refresh (`QTableView`) |
| Missing images | Placeholder label “No cached image”; optional “Open folder” if any path exists |

## Technical contract

### Child process spawn

- Executable: `ebay-workflows` on `PATH` (editable install: `pip install -e .`).
- Working directory: repository root (directory containing `.env`).
- Environment: inherit OS env; load `.env` via existing `Settings` in child (same as CLI).
- Recommend running `scripts/clear-ebay-env-overrides.ps1` before starting GUI if eBay creds misbehave.

### Workflow catalog

Single module `ebay_workflows.gui.workflow_catalog` defines `job_id → argv builder`. GUI and `run-due-schedules` must use it only—no duplicated argv strings.

### Schema migration

- **Current:** `ebay-workflows init-db` → `Base.metadata.create_all` (no Alembic).
- **New tables** do not alter existing rows; safe on DBs with 966+ listings.
- **Future:** introduce Alembic before multi-machine deploys.

### Dependencies (`[gui]` extra)

```toml
gui = ["pyside6>=6.6"]
```

- **PySide6** — widgets, `QProcess`, images via `QPixmap`.
- **Pillow not required** for the Qt app (optional only if sharing image utils with CLI).
- `apscheduler>=3.10` added in GUI-6 with scheduler UI.
- Optional: `qdarktheme` for dark mode (operator install or second extra `gui[dark]`).

### Qt implementation rules

- GUI thread: event loop only (`QApplication.exec()`).
- Long work: `QProcess` for CLI, `QThread` + signals for DB refresh batches if needed.
- Use **Fusion** style by default; system-native on Windows is acceptable via default Qt platform plugin.
- GUI entrypoint is `ebay_workflows.gui.qt_app:main` only.

### Performance expectations (from live DB)

| Phase | ~966 listings | UI treatment |
|-------|----------------|--------------|
| phase2 | ~40+ min | Indeterminate progress; log tail |
| phase4 | minutes | Log + `workflow_steps` poll |
| phase5 | hours | Not default schedule; warn in UI |
| Opportunities refresh | <2 s | Top 50–200 query only |

### Rate limits

- Respect `EBAY_REQUESTS_PER_MINUTE` and `GLOBAL_REQUESTS_PER_MINUTE_CAP` via existing CLI limiters.
- Do not start a second child while `JobRunner.is_busy()`.

## Windows Task Scheduler (headless schedules)

After GUI-6 implements `run-due-schedules`:

1. Action: `C:\Path\to\python.exe` or `ebay-workflows run-due-schedules`
2. Start in: `C:\Users\...\EbayWorkflows`
3. Trigger: every **5 minutes**
4. Condition: run whether user logged on or not (if desired)
5. Ensure PostgreSQL service is running

## Build order (implementation)

| Step | Deliverable |
|------|-------------|
| **Now** | Prerequisites + operator docs; models; GUI-0 PySide6 Opportunities + favourites |
| GUI-1 | Database tab (curated queries) |
| GUI-2 | Workflows run now + JobRunner |
| GUI-5 | Favourites polish (notes in DB tab) |
| GUI-6 | Schedules + `run-due-schedules` + APScheduler in GUI |
| GUI-7 | PyInstaller + Task Scheduler export helper (include PySide6 DLLs / `pyside6-deploy` if used) |

## Acceptance smoke test (GUI-0)

1. `pip install -e ".[gui]"` and `ebay-workflows init-db`
2. `ebay-workflows-gui` opens native window
3. Ranked rows appear (requires phase 4 run)
4. Select row → detail + image or placeholder
5. Star toggles favourite; filter “Favourites only” works
6. Restart app → favourite persists

## Related documents

- `gui-application.md` — feature spec
- `gui-operator-workflows.md` — day-in-the-life flows
- `runbook-local.md` — CLI phases
- `config-contract.md` — env vars (show read-only in status bar later)
