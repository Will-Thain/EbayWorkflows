# GUI Operator Workflows

## Home dashboard

Open the **Home** tab first for a snapshot of the pipeline (listing counts, ranked rows, favourites, cached images) and a dedicated **Ongoing workflows** panel. Every running `workflow_step` appears as a card with progress and a **GUI** vs **External** badge. Use **Manage workflows →** to jump to the Workflows tab for logs and start/stop.

Example **day-in-the-life** flows for the local desktop app. Assumes PostgreSQL, `.env`, and `pip install -e ".[gui]"` (PySide6) are configured.

## Flow A: Daily arbitrage review (GUI open)

**Goal:** See the best new singles after data is already ingested and ranked.

1. Open **`ebay-workflows-gui`** (Opportunities tab).
2. Confirm sort is **Rank value (desc)** and limit **50**.
3. Scan the table; select rows with high **EV adj** and acceptable **confidence**.
4. For each shortlist:
   - Review **top card** and match % in the detail pane.
   - Check **cached image** (or note missing cache).
   - Click **Open on eBay** to verify set/condition.
5. Press **★ Favourite** on listings to revisit.
6. Set filter **Favourites only** to build a watchlist.
7. Optionally add a **note** (e.g. “verify foil”, “counterfeit risk”).

**CLI assumed already run:** phase 4 hybrid at least once. Ingest may have run overnight via schedule (Flow C).

---

## Flow B: Manual refresh after CLI work

**Goal:** Update the GUI after running phases in Terminal.

1. In Terminal:
   ```powershell
   ./scripts/clear-ebay-env-overrides.ps1
   ebay-workflows phase2-match-title
   ebay-workflows phase5-verify-ocr --use-real-ocr --use-embedding-match
   ebay-workflows phase3-join-prices
   ebay-workflows phase6-detect-lots --use-real-detection
   ebay-workflows phase4-rank --hybrid
   ```
   Or use `./scripts/rerun-image-matching.ps1` when only re-scoring cached images.
2. In GUI: click **Refresh** on Opportunities.
3. Compare new top ranks vs yesterday’s favourites (notes still attached).

---

## Flow C: Automated nightly ingest (GUI closed)

**Goal:** New eBay listings every 24h without keeping the app open.

**Prerequisites:** `scheduled_jobs` table (`ebay-workflows init-db`) and **Workflows → Schedules** or `ebay-workflows run-due-schedules`.

1. In GUI **Schedules** (or one-time SQL seed): create schedule
   - Job: **phase1** (ingest)
   - Params: query `magic the gathering`, `max_pages` 20, download images on
   - Type: **interval** every **24** hours
   - Catch-up missed: **off**
2. Windows Task Scheduler: run `ebay-workflows run-due-schedules` every 5 minutes.
3. Morning: optional second schedule or manual CLI:
   - phase2 → phase5 → phase3 → phase6 → phase4 (or `./scripts/run-live-pipeline.ps1`)
4. Open GUI Opportunities to review.

**Rate limits:** 20 pages × 50 listings respects ~20 eBay Browse calls per run (within 60/min).

---

## Flow D: Staggered schedule (rank after ingest)

| Local time | Scheduled job | Purpose |
|------------|---------------|---------|
| 02:00 | `phase1` | Ingest + image download |
| 03:30 | `phase2` → `phase5` → `phase3` → `phase6` → `phase4` | Match, verify, price, lot score, rank |

**Mutex:** only one job runs at a time; stagger times so ingest finishes before phase2.

---

## Flow E: Stop a runaway job

1. **Workflows** tab → see active job log (GUI-started jobs) or **External:** status with progress bar (terminal/CLI-started jobs).
2. Click **Stop** → terminates only jobs started from the GUI; external runs must be stopped in the terminal (Ctrl+C).
3. If DB step stuck `running`, note warning in UI; inspect **Database → Recent workflow steps**.
4. Re-run phase after fixing env (e.g. HF network for phase 5).

**Monitoring CLI jobs:** The Workflows tab polls `workflow_steps` every ~2s. Phases publish `progress_current` / `progress_total` on the running step so progress appears even without live log output.

---

## Flow F: One-shot full refresh before a buying session

**Goal:** Specific date/time run (e.g. Saturday 08:00).

1. Schedule type **Once**: `2026-06-14 08:00` local.
2. Job: `phase1` with higher `max_pages` if needed.
3. Manually run phase2–4 when ingest completes (or separate daily schedules).
4. GUI **Favourites only** during the session.

---

## What not to schedule (v1 guidance)

| Job | Risk |
|-----|------|
| `phase5` / `phase6` | Hours-long; HF/Tesseract dependencies; poor overlap with ingest |
| Full `run-resumable-pipeline` | Hard to reason about partial failure in headless mode |

Use Terminal with monitoring for OCR/lot passes until GUI progress UX is mature.

---

## Related documents

- `gui-build-prerequisites.md` — defaults and checklist
- `gui-application.md` — tabs and architecture
- `runbook-local.md` — CLI command reference
