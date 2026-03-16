# Implementation Plan: Delta Sync — Incremental Updates

**Branch**: `001-delta-sync` | **Date**: 2026-03-15 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/001-delta-sync/spec.md`

## Summary

Implement a per-project sync checkpoint that records the UTC **start** timestamp of the
last successful sync cycle (i.e., when the fetch queries were issued). On subsequent
cycles the system fetches only ADO work items with
`ChangedDate >= checkpoint - overlap` via WIQL, and only Asana tasks with
`modified_since = checkpoint - overlap`. Using the query start time (rather than cycle
end time) ensures items modified during processing are included in the next incremental
window. A daily unconditional full scan catches deleted items. Pull request sync is
unchanged. The operator can force a full scan via `FORCE_FULL_SYNC=true`. Timestamps
are captured at query time and persisted only on successful cycle completion.

## Technical Context

**Language/Version**: Python 3.13
**Primary Dependencies**: azure-devops 7.1.0b4, asana (latest), sqlite3 (stdlib)
**Storage**: SQLite via custom `Database` wrapper (`ado_asana_sync/database/database.py`);
schema bumped to version 3 — two new nullable columns added to `projects` table via
backward-compatible `ALTER TABLE` migration
**Testing**: pytest with real SQLite databases in `tempfile.TemporaryDirectory()`; mock only
`azure.devops` and `asana` API clients at boundary
**Target Platform**: Linux container (Docker)
**Project Type**: Background sync daemon
**Performance Goals**: Subsequent cycles processing <5 % of changed items complete in
≤10 % of full-scan wall-clock time (SC-001); API call count scales proportionally to
fraction of changed items (SC-002)
**Constraints**: Zero breaking changes to existing sync correctness guarantees; no forced
re-migration for existing deployments; PR sync path entirely unchanged; ruff/mypy clean
**Scale/Scope**: 5 000+ work items per project; multiple projects processed concurrently
via `ThreadPoolExecutor` (up to `THREAD_COUNT` workers)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Python-First Development | ✅ Pass | Python 3.13; ruff + mypy enforced; uv for deps |
| II. Boundary-Isolated Architecture | ✅ Pass | Checkpoint R/W isolated in `database.py`; WIQL call in `sync.py`; Asana `modified_since` in `asana.py` helper; data models carry no API-client concerns |
| III. Integration-First Testing | ✅ Pass | Real `App` + real SQLite in tests; ADO/Asana clients mocked at boundary |
| IV. Bidirectional Sync Correctness | ✅ Pass | Timestamp written only on success; API-error fallback; daily full scan for deletions; PR path unchanged |
| V. Conventional Commits & CI | ✅ Pass | Conventional commits enforced; all CI gates must pass before merge |

All gates pass. No violations to justify.

## Project Structure

### Documentation (this feature)

```text
specs/001-delta-sync/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output (new env vars + operator guide)
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
ado_asana_sync/
├── database/
│   └── database.py          # Schema v3 migration; get_sync_checkpoint(),
│                            #   set_sync_checkpoint() methods on Database
├── sync/
│   ├── app.py               # SYNC_OVERLAP_MINUTES + FORCE_FULL_SYNC constants
│   └── sync.py              # sync_mode decision; delta ADO fetch; delta Asana fetch;
│                            #   checkpoint write on success
tests/
├── test_delta_sync_integration.py   # Integration tests (real DB, mocked APIs)
└── test_delta_sync_unit.py          # Unit tests (pure logic functions)
```

**Structure Decision**: Single-project layout extending existing source files. No new
top-level modules needed; all changes are additive within `database/` and `sync/`.

## Complexity Tracking

> No constitution violations — section not required.
