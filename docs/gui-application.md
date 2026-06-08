# Desktop GUI Application (Specification)

**Status:** GUI-0 through GUI-7 **[Shipped]** (PySide6). Verification provenance display **[Shipped]**. Tags: `documentation-status.md`.

## Purpose

A **local desktop application** (native window, no browser) that lets one operator:

1. **Start and stop** workflow phases (CLI jobs running as child processes).
2. **Monitor progress** of those background jobs in near real time.
3. **View and query** PostgreSQL data safely.
4. **Preview** the most promising ranked matches with listing images and match context.
5. **Schedule** workflows to run on an interval (e.g. every 24h), daily at a time, or once on a specific date/time.
6. **Favourite** listings for later review and filtering.

The GUI orchestrates and visualizes work; **business logic stays in** `ebay_workflows` (CLI + existing services). Long-running CV phases (5–6) run out-of-process so the UI stays responsive.

## Platform choice: PySide6 (Qt 6)

The desktop app is built with **[PySide6](https://doc.qt.io/qtforpython/)** — the official Qt 6 Python bindings. This gives a native desktop window, modern widgets, and room to grow (tables, docks, system tray) without a browser or Electron.

| Concern | PySide6 approach |
|---------|------------------|
| Layout | `QMainWindow` + `QTabWidget` (**Home**, Opportunities, Workflows, Database) |
| Rankings table | `QTableView` + `QAbstractTableModel` (sortable columns, row selection) |
| Split detail / image | `QSplitter` (list left, detail + `QLabel` / `QScrollArea` right) |
| Workflow log | `QPlainTextEdit` (read-only), fed by signals from worker thread |
| Child CLI jobs | **`QProcess`** (preferred) or `subprocess.Popen` on a `QThread` |
| Stop job | `QProcess.terminate()` → `kill()` after timeout |
| DB polling | `QTimer` every 2–5 s → query `workflow_steps` → update status bar |
| Images | `QPixmap` / `QImage.fromFile` (Qt built-in; **Pillow not required**) |
| Favourite star | `QToolButton` or toggle in toolbar |
| Dialogs | `QDialog` for schedule create/edit and job parameters |

### Look and feel (defaults)

- **Base style:** `QApplication.setStyle("Fusion")` — consistent cross-version look on Windows.
- **Theme (optional v1.1):** [qdarktheme](https://github.com/5yutan5/QDarkStyleSheet) or Qt 6 **light/dark** palette via `QPalette` — avoid hard-coded colors in widgets.
- **Typography:** use system default (`QApplication.font()`); optional app-wide **Segoe UI** on Windows.
- **High DPI:** enable `Qt.ApplicationAttribute.AA_EnableHighDpiScaling` (Qt 6 handles scaling automatically in most builds).
- **Icons:** [Qt Material Icons](https://fonts.google.com/icons) via `QIcon.fromTheme` or bundled SVGs for star, play, stop, refresh.

Do **not** use Tkinter, CustomTkinter, or a local web view for the target application.

### Implementation

Entry module: **`gui/qt_app.py`**. Shared logic (`favorites.py`, `presenters.py`, `models_qt.py`, `workflow_catalog.py`) stays framework-agnostic. No Tkinter code in the repository.

## Operator goals → application features

| Goal | Tab / area | Primary data source |
|------|------------|---------------------|
| Pipeline overview & ongoing runs | **Home** (dashboard) | Counts from `listings`, `listing_scores`, `listing_favorites`, `listing_images`; all `workflow_steps` with `status = 'running'` |
| Start / stop workflows | **Workflows** | Child `ebay-workflows` processes; optional `workflow_runs` / `workflow_steps` rows written by CLI |
| Monitor progress | **Home** + **Workflows** | Poll `workflow_steps` where `status = 'running'`; Workflows tab also tails subprocess stdout |
| View / query database | **Database** | SQLAlchemy read-only sessions; curated queries + optional read-only SQL |
| Preview best matches | **Opportunities** | `fetch_ranked_listings`; `listing_images.local_path`; `listing_card_candidates` + `evidence_json` |
| Schedule future runs | **Schedules** (sub-panel of Workflows) | `scheduled_jobs` table; in-app scheduler + headless CLI tick |
| Favourite listings | **Opportunities** | `listing_favorites` table; star toggle + “Favourites only” filter |

## Window layout

```text
┌─ EbayWorkflows ─────────────────────────────────────────────────────────┐
│ [Workflows] [Opportunities] [Database]                                    │
│   Workflows tab contains: [Run now] | [Schedules]                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│  (active tab content)                                                     │
│                                                                           │
├─────────────────────────────────────────────────────────────────────────┤
│ Status: DB ok | Listings 966 | Images 1590 ok | Job: phase5 running 42%  │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Tab 1: Workflows (start, stop, monitor)

### Workflow catalog

Predefined jobs map 1:1 to existing CLI commands (no duplicate phase logic):

| Job ID | Label | CLI (illustrative) | Typical duration |
|--------|-------|-------------------|------------------|
| `phase1` | Ingest eBay listings | `run --no-dry-run --max-pages N --download-images` | Minutes–hours |
| `phase2` | Title match | `phase2-match-title --top-k 3` | Minutes (large catalog) |
| `phase3` | Join Cardmarket prices | `phase3-join-prices` | Seconds–minutes |
| `sync_cm` | Sync Cardmarket bulk | `sync-cardmarket` | Minutes |
| `phase4` | Rank (hybrid) | `phase4-rank --hybrid` | Minutes |
| `phase5` | OCR + embeddings | `phase5-verify-ocr --use-real-ocr --use-embedding-match` | Hours |
| `phase6` | Bulk lot detection | `phase6-detect-lots --use-real-detection` | Hours |
| `integrity` | Data integrity check | `data-integrity-check` | Seconds |
| `pipeline` | Resumable 1–6 | `run-resumable-pipeline ...` | Hours |

Each job opens a **parameter dialog** before start (query, `max_pages`, flags). Values are passed as CLI args only—never shell-string concatenation from raw user SQL.

### Start

1. Operator picks job + parameters → **Start**.
2. GUI builds argv: `["ebay-workflows", ...]` with `cwd` = project root (or install root).
3. **`JobRunner`** spawns `Popen` with `stdout=PIPE`, `stderr=STDOUT`, text mode, `bufsize=1`.
4. `QProcess.readyReadStandardOutput` (or a `QThread` reader) appends lines to a **log view** (`QPlainTextEdit`) via Qt signals (never block the GUI thread on I/O).
5. Disable **Start** for conflicting jobs (only one heavy job at a time by default).
6. Set `EBAY_*` / `.env` via existing `Settings` (child inherits environment).

### Stop

1. **Stop** sends `terminate()` to the child process.
2. If not exited within N seconds (e.g. 10), `kill()`.
3. Log line: `--- stopped by operator ---`.
4. DB row for in-flight `workflow_steps` may remain `running` if the CLI did not finish; show a **stale run** warning and link to the Database tab (operator can inspect `error_json` / last metrics).

**Limitation:** Phase 5/6 cannot checkpoint mid-image; stop is best-effort process kill. Document in UI tooltip.

### Monitor progress

Combine **three signals** (no new server required):

| Signal | Mechanism | UI element |
|--------|-----------|------------|
| **Subprocess log** | Queue-drained stdout/stderr | Scrolling log; lines matching `ebay-workflows-progress N/M unit` update **%** and **N / M** label |
| **DB step status** | Poll every 2–5 s: `SELECT * FROM workflow_steps WHERE status = 'running' ORDER BY started_at DESC` | Phase badge: `Phase 3 running…` |
| **Step metrics** | On `status = 'succeeded'`, show `metrics_json` (e.g. `listings_inserted`, `images_downloaded`) | Summary chips below log |

Optional progress bar when metrics include countable work:

- Phase 1: `records_seen` vs expected (`max_pages × page_size`).
- Phase 5/6: if CLI prints `progress X/Y` lines, parse with regex; else indeterminate spinner.

**Active jobs list:** table of `JobRunner` entries (job id, pid, started_at, state: running | succeeded | failed | stopped).

### Schedules sub-panel (Workflows tab)

Lets operators define **when** a catalog job runs without manual clicks.

#### Schedule types

| Type | Operator input | Example |
|------|----------------|---------|
| **Interval** | Every N hours (min 1) | Ingest every 24h |
| **Daily** | Local time + timezone | Rank at 06:00 Europe/London |
| **Once** | Date + time (datetime picker) | Full pipeline on 2026-06-10 02:00 |

Optional later: cron expression (advanced users only).

#### Persistence: `scheduled_jobs` table

Stored in PostgreSQL (see `data-model.md`). Fields include: job id, `job_params_json`, schedule type, interval/daily/once fields, `enabled`, `next_run_at`, `last_run_at`, `last_run_status`, `last_error`.

GUI **Create / Edit / Enable / Disable / Delete** schedules. List view shows next run time and last outcome.

#### Two execution modes (both supported)

| Mode | When it runs | Use case |
|------|----------------|----------|
| **In-app scheduler** | While `ebay-workflows-gui` is open | Laptop always on during trading hours |
| **Headless tick** | Windows Task Scheduler calls CLI every 1–5 min | Runs when GUI is closed |

Headless entrypoint (to implement with scheduler feature):

```powershell
ebay-workflows run-due-schedules
```

- Loads due rows (`enabled` and `next_run_at <= now()`).
- Skips if a job is already running (mutex via `JobRunner` lock file or `workflow_steps.status = 'running'`).
- Spawns the same argv as **Run now**; updates `last_run_at`, `next_run_at`, `last_run_status`.
- Task Scheduler example: daily trigger + `run-due-schedules` every 5 minutes.

In-app: **`APScheduler`** (or stdlib-only timer for interval-only MVP) in a background thread; on fire, call the same code path as `run-due-schedules` for one job id.

#### Scheduling rules

- **No overlap:** if the same schedule’s job is still running, skip and log `skipped_overlap` (retry next interval).
- **Rate limits:** do not stack ingest + phase5 every hour; UI warns on aggressive intervals.
- **Timezone:** store UTC in DB; display in operator local timezone (`zoneinfo`).
- **Missed runs:** if PC was off, optional “run on next startup” checkbox (catch-up once) vs “skip missed” (default for ingest).

### Implementation module

```text
src/ebay_workflows/gui/
  job_runner.py         # JobRunner, JobState, start/stop, log queue
  workflow_catalog.py   # job definitions → argv builders
  scheduler_service.py  # next_run_at calculation, due job dispatch
src/ebay_workflows/
  scheduler.py          # run_due_schedules() shared by GUI and CLI
  models.py             # ScheduledJob, ListingFavorite
```

---

## Tab 2: Opportunities (preview promising matches)

### Ranked list (default view)

- Load **`fetch_ranked_listings(session, limit=N)`** (same as CLI export).
- **Table** columns: Rank, EV adj, Confidence, Risk, Title (truncated), Top card, Match %, Price, Favourite indicator.
  - Export JSON (CLI `export-rankings`) also includes `image_verification_source`, `verification_detection_id`, `verification_listing_image_id` when verified.
- Sidebar filters:
  - Min `rank_value` / EV adj
  - Min confidence
  - Scoring version (`v2_hybrid`, `v2_lot`, …)
  - Text search on title (client-side filter on loaded rows)

### Detail + images (selection)

When a row is selected:

| Panel | Content |
|-------|---------|
| **Summary** | Full title, listing cost, `ev_raw`, `ev_adjusted`, `confidence_score`, `scoring_version`, explanation snippet from `listing_scores.explanation_json` |
| **Match** | Top 3 `listing_card_candidates`: card name, `match_score`, `source_method`, Cardmarket price from `evidence_json.cardmarket_price`, reject reasons from guardrails |
| **Verification** | When `image_verified`: **Verified by** (`set_collector` / `set_symbol`), **Proof detection** (truncated `verification_detection_id`), **Proof crop** (`verification_region_path`); pricing exclusion reason when not eligible |
| **Detection highlight** | Card region overlay prefers `verification_detection_id` when set; else fuzzy OCR title match |
| **Actions** | Open eBay (`QDesktopServices.openUrl`), copy listing ID, open cache folder in Explorer |
| **Images** | Thumbnail strip (`QListWidget` icons) + main preview (`QLabel` + scaled `QPixmap`); paths validated under `IMAGE_CACHE_DIR` |

Optional: overlay OCR snippet from `evidence_json.ocr_verification` and FAISS corroboration when present (read JSON only—do not load torch in GUI). FAISS alone does not imply verified — check **Verified by** line.

### “Most promising” default

Default sort = **`rank_value DESC`** (already used by `fetch_ranked_listings`). Operator can sort by clicking column headers on `QTableView`.

### Favourites

Operators can mark listings to revisit after prices or scores change.

#### UI

- **Star / Favourite** toggle on the detail panel (filled = favourited).
- Toolbar filter: **All** | **Favourites only**.
- Optional **note** field (short text) stored per favourite—shown in detail panel and Database curated view.

#### Persistence: `listing_favorites` table

- One row per `listing_id` (single-operator local app; no user accounts).
- Columns: `listing_id`, `note`, `favorited_at`.
- Deleting a listing cascades or blocks per FK policy (prefer **ON DELETE CASCADE**).

#### Queries

- `fetch_ranked_listings` gains optional `favorites_only: bool` or a join filter in `gui/presenters.py`.
- Curated Database view: **All favourites** with title, rank_value, favourited_at, note.

Favourites are **operator metadata**—safe for the GUI to write via a small `FavoritesRepository` (not ad-hoc SQL from the query tab).

---

## Tab 3: Database (view and query)

### Design principles

- **Read-only by default** — GUI sessions do not call `session.commit()` for ad-hoc SQL.
- **No secrets in queries** — never display `DATABASE_URL` password in UI.
- **Parameterized curated queries** — avoid raw string SQL from untrusted input in v1.

### Curated views (dropdown)

| Query name | Returns |
|------------|---------|
| Table row counts | listings, images, candidates, scores, scryfall_cards, card_prices |
| Recent workflow runs | last 20 `workflow_runs` with status and duration |
| Recent workflow steps | last 50 `workflow_steps` with phase, status, metrics |
| Failed images | `listing_images` where `download_status = failed` (limit 100) |
| Listings without scores | listings left join scores where score is null |
| Top rank_value | listings join scores order by rank_value desc limit 50 |
| Favourites | listings join `listing_favorites` join scores |

Each runs a fixed SQLAlchemy `select()` in `gui/db_browser.py` → results in a **QTableView** (export CSV button).

### Ad-hoc query (v1.1, optional)

- Read-only textarea for **SELECT** only; reject statements containing `INSERT`, `UPDATE`, `DELETE`, `DROP`, `;` chaining (basic guard).
- Execute with `session.execute(text(sql)).fetchmany(500)` and row cap warning.
- Prefer teaching operators to use curated views first.

### Row drill-down

Double-click a row → open **Opportunities** tab filtered to that `listing_id` if applicable.

---

## Shared services (backend for GUI)

```text
src/ebay_workflows/gui/
  __init__.py
  qt_app.py            # QApplication, QMainWindow, tabs, status bar, QTimers
  models_qt.py         # QAbstractTableModel for rankings / DB query results
  job_runner.py        # QProcess wrapper, start/stop, log signals
  workflow_catalog.py  # CLI argv templates
  db_browser.py        # curated queries + guards
  presenters.py        # RankedListingRow → table cells; image path validation
  favorites.py         # add/remove/list favourites
  widgets.py           # OpportunitiesPanel, LogPanel, ImagePreview (optional)
  scheduler_service.py # in-app due-job dispatch
```

Reuse existing:

- `config.Settings`
- `db.build_session_factory`
- `services.ranked_export.fetch_ranked_listings`
- `models.*`

Do **not** import `workflow_phase5`, `open_clip`, or `torch` from GUI modules.

---

## Architecture

```text
┌─────────────────────────────────────────────────────────┐
│  ebay-workflows-gui  (Qt event loop / GUI thread)         │
│  ├─ Workflows: JobRunner + Schedules ──spawn──► CLI     │
│  ├─ Opportunities: ranked_export + favourites + images  │
│  └─ Database: read-only SQLAlchemy (+ favourites write) │
└────────────────────────┬────────────────────────────────┘
                         │
         ┌───────────────┴───────────────┐
         ▼                               ▼
  PostgreSQL                      ./.cache/images
  workflow_runs / steps           listing image files
  scheduled_jobs / listing_favorites
```

---

## Dependencies and entry point

```toml
[project.optional-dependencies]
gui = [
  "pyside6>=6.6",
  "apscheduler>=3.10",  # in-app scheduling (GUI-6); headless tick uses scheduler.py
]

[project.scripts]
ebay-workflows-gui = "ebay_workflows.gui.qt_app:main"
ebay-workflows-run-due-schedules = "ebay_workflows.scheduler:run_due_schedules_main"
```

Optional theme extra (operator choice): `qdarktheme` or ship custom `QPalette` in-repo.

```powershell
pip install -e ".[gui]"
ebay-workflows-gui
```

Bind nothing on the network.

---

## Security and operations

- Child processes inherit `.env`; GUI never shows API keys.
- Image paths: `resolve()` and must be under `IMAGE_CACHE_DIR`.
- One heavy job at a time to respect `EBAY_REQUESTS_PER_MINUTE` and `GLOBAL_REQUESTS_PER_MINUTE_CAP`.
- Stop = process termination; warn that DB step rows may be left `running`.

---

## Delivery phases

| Phase | Deliverable |
|-------|-------------|
| **GUI-0** | PySide6 shell + Opportunities tab (rankings + detail + images + refresh) |
| **GUI-1** | Database tab (curated queries + counts) |
| **GUI-2** | Workflows tab (start/stop + log tail) for phases 2–4 and export |
| **GUI-3** | DB polling for `workflow_steps`; metrics summary on complete |
| **GUI-4** | Phase 1 / 5 / 6 in catalog with strong “long running” warnings |
| **GUI-5** | Favourites (star, filter, notes) + `listing_favorites` model |
| **GUI-6** | Schedules UI + `scheduled_jobs` + `run-due-schedules` CLI (implemented) |
| **GUI-7** | `gui-windows-scheduler.md`, `register-run-due-schedules-task.ps1`, `build-gui-exe.ps1` (implemented) |

Build **GUI-0 → GUI-1 → GUI-2 → GUI-5 → GUI-6** so preview and manual runs land before automation.

---

## Acceptance criteria

1. Native desktop window with four tabs: Home, Opportunities, Workflows, Database.
2. Operator can **start** at least phase 2, 3, and 4 from the UI and see live log output.
3. Operator can **stop** a running child process; UI reflects stopped state.
4. While a CLI phase runs, UI shows **running** step from DB and/or log activity within 5 s poll interval.
5. Opportunities tab lists top ranked listings and shows **image preview** for selected row when cached.
6. Database tab runs curated queries without write access.
7. Ranking and match data use **`fetch_ranked_listings`** and existing models—no duplicated scoring logic.
8. Operator can **favourite** a listing, filter Opportunities to favourites only, and see favourites in Database tab.
9. Operator can create a schedule (24h interval, daily time, or one-shot datetime), enable/disable it, and see `next_run_at` / last run status.
10. `ebay-workflows run-due-schedules` runs due jobs headless; in-app scheduler fires the same path when GUI is open.

---

## Testing

- Unit: `presenters`, `workflow_catalog.build_argv`, `db_browser` SQL guards, image path validation.
- Manual: start phase 4 on dev DB; stop mid-run; verify Opportunities refresh after complete.
- CI: `compileall` on `src/ebay_workflows/gui`; optional `pytest-qt` for model tests; no full GUI E2E in CI initially.
- Qt rule: **never** call SQLAlchemy or blocking I/O on the GUI thread — use `QThread` + signals or short `QTimer` polls.

---

## Related documents

- `workflow-phases.md` — what each job does; labels for Workflows tab.
- `runbook-local.md` — CLI flags mirrored in parameter dialogs.
- `data-model.md` / `data-dictionary.md` — Database tab column help.
- `ranking-and-confidence.md` — Opportunities tab tooltips; strict verify gate
- `card-recognition-architecture.md` — verification spec mirrored in match detail panel
- `documentation-status.md` — Shipped / Historical / Future labels
- `product-requirements.md` — hosted multi-user web UI remains out of scope; this is local desktop only.
