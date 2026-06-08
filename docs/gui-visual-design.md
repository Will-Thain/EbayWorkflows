# GUI visual design — analysis and implementation plan

**Status:** **[Shipped]** (theme + widgets on branch)  
**Scope:** PySide6 operator desktop (`ebay_workflows.gui`)

---

## Current state (pre-refresh)

| Area | Finding |
|------|---------|
| **Styling** | Inline `setStyleSheet()` scattered across `dashboard_tab.py`, `qt_app.py`, panels — inconsistent borders, fonts, colors |
| **Style base** | Fusion only; no global QSS |
| **Hierarchy** | Page titles vary (18px bold, 13px bold); muted text uses ad-hoc `palette(mid)` |
| **Cards** | `StatCard` / `OngoingWorkflowCard` exist but state styling is inline (red `#c0392b`, highlight border) |
| **Workflows** | Flat `QPushButton` grid; active job highlighted with per-button stylesheet |
| **Tables** | Alternating rows in some tabs only; grid lines visible; no shared config |
| **Status** | LIVE / STALE / warming embedded in meta label text, not scannable chips |

**Root cause:** No design tokens or shared components — every screen reinvents spacing and color.

---

## Design goals

1. **Operator clarity** — status and progress readable at a glance during long runs  
2. **Consistency** — one typography scale, 8px spacing grid, one accent palette  
3. **Maintainability** — QSS + `objectName` / dynamic properties; minimal inline CSS  
4. **Low risk** — no new dependencies; Fusion + QSS only  

---

## Chosen approach: centralized light theme + shared widgets

### Why light (not dark)

- Matches default Windows/Fusion expectations for business tools  
- Listing images and OCR previews read better on light surfaces  
- Dark mode can be a follow-up via second QSS file + toggle  

### Token palette

| Token | Value | Use |
|-------|-------|-----|
| `bg` | `#f0f2f5` | Tab / window background |
| `surface` | `#ffffff` | Cards, inputs |
| `border` | `#dce1e9` | Card and table borders |
| `text` | `#1a1d26` | Primary text |
| `text-muted` | `#6b7280` | Captions, hints |
| `accent` | `#2563eb` | Primary actions, progress |
| `success` | `#059669` | LIVE, short jobs |
| `warning` | `#d97706` | Warming, long jobs |
| `danger` | `#dc2626` | STALE, stop |

### Typography scale

| Role | Object name | Size / weight |
|------|-------------|---------------|
| Page title | `pageTitle` | 20px, 600 |
| Section title | `sectionTitle` | 14px, 600 |
| Body | (default) | 13px |
| Caption | `caption` | 11px, muted |
| Stat value | `statValue` | 24px, 600 |

### Spacing

- Tab content margins: **16px**  
- Section gap: **12px**  
- Card internal padding: **14px**  
- Grid gap (workflow tiles): **10px**  

---

## Architecture

```
src/ebay_workflows/gui/
  theme.py              # apply_app_theme(), configure_data_table(), set_widget_state()
  styles/app.qss        # Global Fusion overrides
  widgets.py            # PageHeader, HintLabel, StatusChip, StatCard, WorkflowTile, CardFrame
```

**Dynamic state** (replaces inline stylesheets):

```python
set_widget_state(card, "cardState", "stale")  # triggers QSS [cardState="stale"]
set_widget_state(tile, "active", True)        # running workflow tile
```

---

## Component changes

### Home (Dashboard)

- `PageHeader` + stat row using themed `StatCard` (`statCard` + optional `statAccent`)  
- `OngoingWorkflowCard` → `CardFrame` with `StatusChip` in header (LIVE / WARMING / STALE / PAUSED)  
- Empty state uses `HintLabel`  
- Recent table → `configure_data_table()`  

### Workflows → Run now

- `PageHeader` with subtitle  
- **Workflow tiles** replace flat buttons: title, duration badge, Run button  
- Active tile uses `active=true` property (not inline CSS)  
- Transport row: Pause/Stop use `secondaryButton` / `dangerButton`  
- Log area: `logPanel` object name (monospace, inset)  

### Workflows → Stuck runs

- `HintLabel` for intro text  
- Themed data table  

### Opportunities / Database

- Detail title → `sectionTitle`  
- Tables → `configure_data_table()`  
- Primary actions → `primaryButton` where appropriate  

### Main window

- `QTabWidget#mainTabs` — padded tab bar, clear selected state  
- Status bar — muted caption styling via QSS  

---

## Out of scope (future)

- Dark theme QSS + toggle  
- Listing thumbnails in Opportunities table (data + delegate)  
- Sidebar navigation (tabs sufficient for 4 sections)  
- Toast notifications (keep `QMessageBox` for now)  

---

## Verification

- `ruff check .`  
- `py -m pytest tests/test_workflow_monitor.py tests/test_stale_workflows.py -q`  
- Manual: `.\scripts\run-gui.ps1` — Home cards, Workflows tiles, Stuck runs table  

---

## References

- `gui-application.md` — functional spec  
- `gui-build-prerequisites.md` — PySide6 setup  
