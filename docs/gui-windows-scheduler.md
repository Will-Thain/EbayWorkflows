# Windows Task Scheduler (headless schedules)

**Status:** Headless scheduler **[Shipped]**. Tags: `documentation-status.md`.

Use this when the PySide6 GUI is **closed** but you still want `scheduled_jobs` rows to run on time.

## Prerequisites

1. PostgreSQL running locally (same `DATABASE_URL` as `.env`).
2. Dev install: `.\scripts\install-dev.ps1` from the repo root (includes sibling `mtg-card-recognition`).
3. Schema includes `scheduled_jobs`: `ebay-workflows init-db`
4. At least one **enabled** schedule with `next_run_at` in the past or future (create in **Workflows → Schedules**).

## Quick register (PowerShell)

From the repository root (adjust paths if needed):

```powershell
.\scripts\register-run-due-schedules-task.ps1
```

This creates a task **EbayWorkflows-RunDueSchedules** that runs every **5 minutes** as the current user.

## Manual Task Scheduler settings

| Field | Value |
|-------|--------|
| Program | `python` (or full path to your venv `python.exe`) |
| Arguments | `-m ebay_workflows.scheduler` |
| Start in | `C:\Users\...\EbayWorkflows` (repo root with `.env`) |
| Trigger | Daily, repeat every **5 minutes** for 1 day (or use custom trigger) |
| Conditions | Uncheck “Start only on AC power” if on a laptop |

Alternative if `ebay-workflows` is on PATH:

| Field | Value |
|-------|--------|
| Program | `ebay-workflows` |
| Arguments | `run-due-schedules` |

## Behaviour

- Loads due rows: `enabled = true` and `next_run_at <= now()` (UTC).
- Skips dispatch if any `workflow_steps.status = 'running'` (global mutex).
- Spawns **one** due job per tick as a detached CLI process.
- Updates `last_run_at`, `last_run_status`, and `next_run_at` on the schedule row.

## Verify

```powershell
ebay-workflows run-due-schedules
```

Stderr prints `Dispatched schedule '...' (phase1)` when a job fires; exit code `0` when nothing was due.

## Remove the task

```powershell
Unregister-ScheduledTask -TaskName EbayWorkflows-RunDueSchedules -Confirm:$false
```

## Desktop executable (optional)

See `scripts/build-gui-exe.ps1` for a PyInstaller-based `.exe` (operator-only; not required for scheduling).
