# Data Model: Delta Sync — Incremental Updates

**Branch**: `001-delta-sync` | **Date**: 2026-03-15

## Schema Version

Database schema advances from **version 2** → **version 3**.
Migration is applied automatically on startup via `_apply_migrations()` in `database.py`.

---

## Modified Entity: Project (projects table)

### Current Schema (v2)

```sql
CREATE TABLE projects (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ado_project_name    TEXT NOT NULL,
    ado_team_name       TEXT NOT NULL,
    asana_project_name  TEXT NOT NULL,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(ado_project_name, ado_team_name)
)
```

### New Schema (v3)

```sql
CREATE TABLE projects (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ado_project_name    TEXT NOT NULL,
    ado_team_name       TEXT NOT NULL,
    asana_project_name  TEXT NOT NULL,
    last_sync_at        TEXT,          -- UTC ISO 8601; NULL = never synced
    last_full_sync_at   TEXT,          -- UTC ISO 8601; NULL = never full-synced
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(ado_project_name, ado_team_name)
)
```

### Migration (v2 → v3)

```sql
ALTER TABLE projects ADD COLUMN last_sync_at TEXT;
ALTER TABLE projects ADD COLUMN last_full_sync_at TEXT;
```

Existing rows receive `NULL` for both columns, which is the correct sentinel value
meaning "never synced — perform a full scan".

---

## New Fields

### `last_sync_at` (TEXT, nullable)

| Property | Value |
|----------|-------|
| Format | UTC ISO 8601 string, e.g. `"2026-03-15T14:32:00+00:00"` |
| Semantics | **Start** timestamp of the last successful sync cycle for this project — captured when the fetch queries were issued, not when the cycle finished. Using the query start time ensures the next incremental window begins at the exact boundary where the previous queries ran, so any items modified during processing are not missed. `NULL` means the project has never completed a sync. |
| Written by | `Database.set_sync_checkpoint()` — called at the end of a successful `sync_project()`, passing in the timestamp that was captured at the **beginning** of that run. |
| Read by | `Database.get_sync_checkpoint()` — read at the start of each `sync_project()` call to determine the incremental fetch window. |
| Null behaviour | Triggers a first-run full scan (FR-004). |

### `last_full_sync_at` (TEXT, nullable)

| Property | Value |
|----------|-------|
| Format | UTC ISO 8601 string |
| Semantics | **Start** timestamp of the last successful full scan for this project (same capture convention as `last_sync_at`). `NULL` or older than 24 hours triggers the daily full scan (FR-011). |
| Written by | `Database.set_sync_checkpoint()` — only updated when `full_scan=True` is passed, using the run-start timestamp. |
| Read by | `Database.get_sync_checkpoint()` — compared against `now_utc - 24h` to decide daily full scan. |
| Null behaviour | Treated as "full scan overdue"; triggers full scan on first cycle. |

---

## New Database Methods

### `Database.get_sync_checkpoint(ado_project_name: str, ado_team_name: str) -> dict`

Returns a dict with keys:

```python
{
    "last_sync_at": str | None,       # ISO 8601 UTC or None
    "last_full_sync_at": str | None,  # ISO 8601 UTC or None
}
```

### `Database.set_sync_checkpoint(ado_project_name: str, ado_team_name: str, run_started_at: str, full_scan: bool = False) -> None`

- `run_started_at` is the ISO 8601 UTC timestamp captured at the **start** of the sync
  run (when the fetch queries were issued), not the time this method is called.
- Always writes `last_sync_at` to `run_started_at`.
- If `full_scan=True`, also writes `last_full_sync_at` to `run_started_at`.
- Called only after a cycle completes successfully — never on failure.
- Wrapped in the existing `get_connection()` context manager for thread safety.

---

## Sync Mode Decision (derived from data model)

```python
def determine_sync_mode(checkpoint: dict, force_full: bool, overlap_minutes: int) -> tuple[str, datetime | None]:
    """
    Returns (mode, fetch_since) where mode is "full" or "incremental"
    and fetch_since is the lower bound for the incremental window (or None for full).

    NOTE: checkpoint["last_sync_at"] stores the run-START timestamp of the previous
    cycle (when queries were issued). The overlap is subtracted from that value to
    compute the safe lower bound for the next incremental fetch.
    """
    if force_full:
        return "full", None
    if checkpoint["last_sync_at"] is None:
        return "full", None  # First run
    last_full = checkpoint["last_full_sync_at"]
    if last_full is None or (now_utc() - parse_iso(last_full)) >= timedelta(hours=24):
        return "full", None  # Daily full scan due
    # Subtract overlap from the previous run's query-start time
    since = parse_iso(checkpoint["last_sync_at"]) - timedelta(minutes=overlap_minutes)
    return "incremental", since


# At the start of sync_project(), before any API calls:
run_started_at = now_utc()  # Captured HERE — before WIQL/Asana queries fire

# ... perform sync ...

# On success only — pass run_started_at (not now_utc()) to set_sync_checkpoint:
db.set_sync_checkpoint(ado_project_name, ado_team_name, run_started_at.isoformat(), full_scan=is_full)
```

---

## Entity Relationships (unchanged)

```text
Project (projects table)
  │
  ├── 1:N ── WorkItemMatch (matches table)      [existing]
  ├── 1:N ── PRMatch (pr_matches table)         [existing]
  └── 1:1 ── SyncCheckpoint (last_sync_at,      [NEW — columns on projects row]
                              last_full_sync_at)
```

---

## Invariants

1. Both columns store the **run-start** timestamp (query time), never the cycle-end time.
2. `last_sync_at` is NEVER written if the sync cycle raised an unhandled exception.
3. `last_full_sync_at` is NEVER written for an incremental cycle.
4. Both columns are always valid ISO 8601 UTC strings or `NULL`; no other values are valid.
5. `last_full_sync_at <= last_sync_at` always holds for any row where both are non-null.
