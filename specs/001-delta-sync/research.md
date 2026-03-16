# Research: Delta Sync — Incremental Updates

**Branch**: `001-delta-sync` | **Date**: 2026-03-15

## Decision Log

---

### Decision 1: ADO Incremental Work Item Fetch

**Decision**: Use `ado_wit_client.query_by_wiql()` with a WIQL query filtering on
`[System.ChangedDate]`.

**WIQL query**:

```sql
SELECT [System.Id]
FROM WorkItems
WHERE [System.TeamProject] = '{project_name}'
  AND [System.ChangedDate] >= '{checkpoint_minus_overlap}'
ORDER BY [System.ChangedDate] ASC
```

**Rationale**: `ChangedDate` is updated on any field modification, state transition, or
assignment change — covering all fields the sync cares about. `query_by_wiql()` is already
available via `app.ado_wit_client` (initialised in `App.connect()`). The returned IDs are
then passed to `get_work_items()` for full field retrieval, which is identical to the
current full-scan flow and requires no change to downstream processing.

**Alternatives considered**:

- `get_backlog_level_work_items()` (current): Fetches all items; no date filter available.
  Replaced by WIQL path for incremental mode.
- ADO service hooks / webhooks: Push-based, requires externally reachable endpoint.
  Incompatible with the polling architecture of this service.

---

### Decision 2: Asana Incremental Task Fetch

**Decision**: Use `asana.TasksApi.get_tasks_for_project()` with the `modified_since`
parameter (ISO 8601 string).

**Call pattern**:

```python
opts = {
    "modified_since": checkpoint_iso,
    "opt_fields": "gid,name,completed,modified_at,assignee,due_on,tags",
}
api_instance.get_tasks_for_project(project_gid, opts)
```

**Rationale**: `modified_since` is an officially documented parameter for
`GET /tasks?project=...` in the Asana API. It is stateless (just a timestamp), aligning
with the ADO approach and requiring no token management. If the call raises an `ApiException`
the caller falls back to a full task fetch for that cycle (FR-006).

**Alternatives considered**:

- Asana Events API (`GET /events?resource={project_gid}&sync={token}`): Provides definitive
  change detection including deletions but requires maintaining a sync token that expires in
  ~24 hours. Complexity of token management and forced re-sync on expiry outweighs benefits
  for this use case, especially since a daily full scan already covers deletions.
- In-memory `modified_at` filter: Fetch all tasks (compact), filter client-side by
  `modified_at`. Eliminates API-side uncertainty but does not reduce the number of API
  calls, defeating the purpose of incremental sync. Kept as a future fallback option if
  `modified_since` proves unreliable in practice.

---

### Decision 3: Schema Migration Strategy

**Decision**: Bump schema to version 3. Add two nullable `TEXT` columns to the `projects`
table via `ALTER TABLE` (backward-compatible; existing rows get `NULL` values, treated as
"never synced").

**New columns**:

| Column | Type | Meaning |
|--------|------|---------|
| `last_sync_at` | `TEXT` (UTC ISO 8601) | End time of last successful sync cycle (any mode). `NULL` = never synced → triggers first-run full scan. |
| `last_full_sync_at` | `TEXT` (UTC ISO 8601) | End time of last successful full scan. `NULL` or older than 24 h → triggers daily full scan. |

**Migration code location**: `database.py` → `_apply_migrations()` → new
`_migrate_to_version_3()` method, following the existing pattern.

**Rationale**: `ALTER TABLE … ADD COLUMN` is the lightest-weight SQLite migration and is
completely backward-compatible. Existing deployments upgrade transparently on first startup;
`NULL` values correctly signal "full scan required".

**Alternatives considered**:

- Store checkpoints in the `config` table (JSON blob): Avoids schema change but makes
  querying checkpoints awkward and ties checkpoint logic to a generic key-value store.
  Rejected in favour of explicit typed columns on `projects`.
- Separate `sync_checkpoints` table: More normalised but adds complexity for a simple
  one-to-one relationship. Rejected — YAGNI.

---

### Decision 4: Sync Mode Decision Logic

**Decision**: At the start of each project sync cycle, evaluate the following ordered rules:

1. `FORCE_FULL_SYNC=true` env var → full scan (ignore all timestamps).
2. `last_sync_at IS NULL` → first run → full scan.
3. `(now_utc - last_full_sync_at) >= 24 h` → daily full scan due → full scan.
4. Otherwise → incremental scan using `last_sync_at - SYNC_OVERLAP_MINUTES`.

After a successful cycle:

- Always persist `last_sync_at` using the timestamp captured at the **start** of the run
  (i.e., when the fetch queries were issued), not `now_utc` at cycle end. This ensures the
  next incremental window begins at the exact query boundary, so items modified during
  the previous processing window are not missed.
- Persist `last_full_sync_at` (same run-start value) only if the cycle ran as a full scan.

**Rationale**: Rules are evaluated in priority order; the daily full scan (rule 3) fires
automatically without requiring an explicit scheduler. Using `last_full_sync_at` as a
separate column means a mid-day forced full scan resets the 24-hour clock correctly.

**Alternatives considered**:

- Separate scheduler / cron job for daily full scan: More explicit but adds infrastructure
  complexity. The inline rule is sufficient and consistent with the existing polling model.
- Single timestamp with a "mode" flag: Conflates two distinct concerns. Rejected.

---

### Decision 5: Thread Safety for Checkpoint Updates

**Decision**: Checkpoint reads and writes go through `Database.get_connection()`, which is
already thread-safe (per-thread SQLite connection with WAL mode). No additional locking is
required. A new pair of methods — `get_sync_checkpoint(project_id)` and
`set_sync_checkpoint(project_id, last_sync_at, last_full_sync_at=None)` — are added to the
`Database` class to encapsulate the SQL and keep `sync.py` free of raw SQL.

**Rationale**: The existing `Database` wrapper already handles thread safety via WAL mode
and per-thread connections. Adding typed methods keeps the boundary-isolation principle
intact (sync logic does not write raw SQL).

---

### Decision 6: FORCE_FULL_SYNC Behaviour

**Decision**: `FORCE_FULL_SYNC=true` forces all projects to full scan for the next run.
After a successful forced full scan, `last_sync_at` and `last_full_sync_at` are both
updated normally. The env var itself is read once at startup; the operator must unset it
before the next run to resume incremental behaviour.

**Rationale**: Reading the env var at startup (via `App` constants, consistent with all
other env vars in this project) avoids mid-run confusion. The forced run resets the daily
clock correctly because `last_full_sync_at` is updated.

---

### Decision 7: PR Sync — No Change

**Decision**: Pull request sync continues to fetch all active PRs on every cycle. No
checkpoint or incremental logic is applied to `pull_request_sync.py`.

**Rationale**: The ADO Python SDK (`azure-devops 7.1.0b4`) has a known bug (Issue #491)
where `GitPullRequestSearchCriteria` is missing date filter fields. Even at the REST API
level, the only available date filters are creation date and close date — not
last-modified date. True delta PR sync is not technically feasible without a direct REST
workaround. Deferred to a future feature.
