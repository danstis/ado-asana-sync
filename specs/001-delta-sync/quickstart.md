# Quickstart: Delta Sync — Incremental Updates

**Branch**: `001-delta-sync` | **Date**: 2026-03-15

This guide covers operator-facing changes introduced by the delta sync feature.
No changes to the container image build or deployment process are required.

---

## New Environment Variables

Two new optional environment variables are added. Both follow the existing all-env-var
configuration pattern.

### `SYNC_OVERLAP_MINUTES`

| Property | Value |
|----------|-------|
| Default | `5` |
| Type | Non-negative integer |
| Purpose | Safety overlap window subtracted from the last sync timestamp when computing the incremental fetch boundary. Guards against clock skew between ADO servers and the sync host. |
| Example | `SYNC_OVERLAP_MINUTES=10` |

When set to `0`, no overlap is applied. Increase this value if your ADO instance and sync
host have known clock drift greater than 5 minutes.

### `FORCE_FULL_SYNC`

| Property | Value |
|----------|-------|
| Default | `false` (unset) |
| Type | `true` or unset |
| Purpose | Forces a complete scan of all ADO work items and Asana tasks for every project on the next run, ignoring stored sync timestamps. |
| Example | `FORCE_FULL_SYNC=true` |

After the forced full scan completes successfully, the sync checkpoints are updated
normally. **Unset this variable before the following run** to resume incremental behaviour.

---

## Behaviour Summary

### Normal Operation (after first run)

1. Each project is evaluated at the start of its sync cycle.
2. If the last full scan was more than 24 hours ago, a full scan runs automatically.
3. Otherwise, only ADO work items with `ChangedDate >= (last_sync_at - SYNC_OVERLAP_MINUTES)`
   and Asana tasks with `modified_since = (last_sync_at - SYNC_OVERLAP_MINUTES)` are fetched.
4. Pull requests are always fetched in full (unchanged from previous behaviour).
5. On success, `last_sync_at` is updated. `last_full_sync_at` is updated only for full
   scan cycles.
6. On failure, no timestamps are updated; the next run re-processes from the previous
   successful checkpoint.

### First Run (new deployment)

No additional configuration required. The absence of a stored checkpoint is detected
automatically and a full scan runs to establish the baseline.

### Forced Reset

To reset sync state for all projects and force a complete re-scan:

```bash
FORCE_FULL_SYNC=true docker run ... ado-asana-sync
```

Or set the variable in your environment/secrets manager before the next scheduled run,
then remove it afterwards.

---

## Log Indicators

After this feature is deployed, each project sync cycle emits an INFO log line indicating
which mode ran and how many items were fetched:

```
INFO  [sync] Project "MyProject/MyTeam": mode=incremental, ado_items=12, asana_tasks=7
INFO  [sync] Project "MyProject/MyTeam": mode=full, ado_items=1843, asana_tasks=1821
INFO  [sync] Project "MyProject/MyTeam": mode=full (daily), ado_items=1843, asana_tasks=1821
INFO  [sync] Project "MyProject/MyTeam": mode=full (forced), ado_items=1843, asana_tasks=1821
```

A WARNING log is emitted if the incremental Asana fetch fails and a full scan fallback
is used:

```
WARNING [sync] Project "MyProject/MyTeam": incremental Asana fetch failed (ApiException: ...),
        falling back to full task scan for this cycle
```

---

## Upgrade Notes

- **Existing deployments**: The database schema migrates automatically from v2 to v3 on
  first startup. No manual steps required. All projects start with `NULL` checkpoints
  and will perform a full scan on the first run after upgrade.
- **Rollback**: If rolling back to a version without delta sync, the two new columns
  (`last_sync_at`, `last_full_sync_at`) in the `projects` table are ignored by the older
  code. No data loss or startup errors will occur.
