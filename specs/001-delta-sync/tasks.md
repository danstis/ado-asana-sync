---
description: "Task list for Delta Sync — Incremental Updates"
---

# Tasks: Delta Sync — Incremental Updates

**Input**: Design documents from `/specs/001-delta-sync/`
**Prerequisites**: plan.md ✅ | spec.md ✅ | research.md ✅ | data-model.md ✅ | quickstart.md ✅

**Tests**: Included — integration-first testing is non-negotiable per project constitution
(Principle III). Tests use real SQLite databases in temp dirs; only ADO/Asana API clients
are mocked.

**Organization**: Tasks are grouped by user story to enable independent implementation and
testing of each story.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Include exact file paths in all task descriptions

## Path Conventions

Single-project layout extending existing source files at repository root:

```text
ado_asana_sync/database/database.py   — schema migration + checkpoint DB methods
ado_asana_sync/sync/app.py            — new env var constants
ado_asana_sync/sync/asana.py          — incremental Asana fetch helper
ado_asana_sync/sync/sync.py           — sync mode decision + refactored sync_project()
tests/test_delta_sync_integration.py  — integration tests (real DB, mocked APIs)
tests/test_delta_sync_unit.py         — unit tests (pure logic)
.env.example                          — new env var documentation
README.md                             — operator-facing documentation update
```

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Add new environment variable constants needed by all subsequent phases.

- [x] T001 Add `SYNC_OVERLAP_MINUTES` (default `5`, read from env var, type `int`) and `FORCE_FULL_SYNC` (default `False`, read from env var as `bool`) constants to `ado_asana_sync/sync/app.py` — follow the existing `SLEEP_TIME`/`ASANA_PAGE_SIZE` pattern

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Database schema migration and core helper functions that every user story
depends on. No user story implementation can begin until this phase is complete.

**⚠️ CRITICAL**: Complete T002–T007 before starting any user story phase.

- [x] T002 Bump `CURRENT_SCHEMA_VERSION` to `3` and add `_migrate_to_version_3(self, conn)` method to `Database` in `ado_asana_sync/database/database.py` — execute `ALTER TABLE projects ADD COLUMN last_sync_at TEXT` and `ALTER TABLE projects ADD COLUMN last_full_sync_at TEXT`; follow existing `_migrate_to_version_2` pattern

- [x] T003 Hook `_migrate_to_version_3()` into `_apply_migrations()` in `ado_asana_sync/database/database.py` — add `if current_version < 3: self._migrate_to_version_3(conn); self._record_migration(conn, 3, "Add sync checkpoint columns to projects table")` block

- [x] T004 Add `get_sync_checkpoint(self, ado_project_name: str, ado_team_name: str) -> dict` method to `Database` in `ado_asana_sync/database/database.py` — SELECT `last_sync_at`, `last_full_sync_at` FROM projects WHERE `ado_project_name = ? AND ado_team_name = ?`; return `{"last_sync_at": str | None, "last_full_sync_at": str | None}`

- [x] T005 Add `set_sync_checkpoint(self, ado_project_name: str, ado_team_name: str, run_started_at: str, full_scan: bool = False) -> None` method to `Database` in `ado_asana_sync/database/database.py` — UPDATE projects SET `last_sync_at = ?` (and `last_full_sync_at = ?` when `full_scan=True`) WHERE `ado_project_name = ? AND ado_team_name = ?`; `run_started_at` is the run-start timestamp captured before API calls, not the current time

- [x] T005b **[F1 fix — CRITICAL]** Refactor `sync_projects_from_json()` in `ado_asana_sync/database/database.py` to use `INSERT INTO projects (...) ON CONFLICT(ado_project_name, ado_team_name) DO UPDATE SET asana_project_name=excluded.asana_project_name, updated_at=CURRENT_TIMESTAMP` instead of `DELETE FROM projects` + `INSERT`. This preserves `last_sync_at` and `last_full_sync_at` across application restarts. Projects removed from `projects.json` MUST still be deleted by comparing the incoming list against existing rows and issuing targeted `DELETE` statements for entries no longer present. **Without this fix, checkpoint data is wiped on every restart, making delta sync non-functional.**

- [x] T006 Add `determine_sync_mode(checkpoint: dict, force_full: bool, overlap_minutes: int) -> tuple[str, datetime | None]` function to `ado_asana_sync/sync/sync.py` — implement the 4-rule decision tree: (1) `force_full=True` → `("full", None)`; (2) `checkpoint["last_sync_at"] is None` → `("full", None)`; (3) `now_utc - last_full_sync_at >= 24h` → `("full", None)`; (4) else → `("incremental", parse(last_sync_at) - timedelta(minutes=overlap_minutes))`

- [x] T007 [P] Write integration tests for schema v3 migration, `get_sync_checkpoint`, and `set_sync_checkpoint` in `tests/test_delta_sync_integration.py` — use `TestDataBuilder.create_real_app(temp_dir)`; verify: migration adds columns to existing db, NULL columns on fresh project, set then get round-trips correctly, `full_scan=False` does not update `last_full_sync_at`

- [x] T008 [P] Write unit tests for `determine_sync_mode()` in `tests/test_delta_sync_unit.py` — cover all 4 branches: force_full override, null checkpoint, daily-full-due (last_full_sync_at > 24h ago), and incremental (verify `fetch_since = last_sync_at - overlap`)

**Checkpoint**: Foundation ready — all user story phases can now proceed.

---

## Phase 3: User Story 1 — Incremental Sync on Repeat Runs (Priority: P1) 🎯 MVP

**Goal**: Subsequent sync cycles fetch only ADO work items and Asana tasks modified since
the previous run's query start time, reducing API calls proportionally to the change rate.

**Independent Test**: Run two consecutive sync cycles against a mocked data set where only
5 of 2 000 items change. Verify the second cycle's mocked ADO/Asana fetch calls receive
the incremental boundary timestamp and the cycle completes without re-processing all items.

### Implementation for User Story 1

- [x] T009 [P] [US1] Add `get_asana_tasks_modified_since(app: App, project_gid: str, modified_since_iso: str) -> list` to `ado_asana_sync/sync/asana.py` — call `asana.TasksApi(app.asana_client).get_tasks_for_project(project_gid, {"modified_since": modified_since_iso, "opt_fields": "gid,name,completed,modified_at,assignee,due_on,tags"})` and return the paged results as a list

- [x] T010 [P] [US1] Add `get_ado_work_items_modified_since(app: App, project_name: str, since_dt: datetime) -> list[int]` to `ado_asana_sync/sync/sync.py` — issue WIQL query `SELECT [System.Id] FROM WorkItems WHERE [System.TeamProject] = '{project_name}' AND [System.ChangedDate] >= '{since_dt.isoformat()}'` via `app.ado_wit_client.query_by_wiql()`; return list of work item IDs

- [x] T011 [US1] Refactor `sync_project()` in `ado_asana_sync/sync/sync.py` to: (1) capture `run_started_at = datetime.now(timezone.utc)` at the very top before any API calls; (2) read `checkpoint = app.db.get_sync_checkpoint(project_name, team_name)`; (3) call `determine_sync_mode(checkpoint, FORCE_FULL_SYNC, SYNC_OVERLAP_MINUTES)`; (4) dispatch to `get_ado_work_items_modified_since` or full fetch per mode; (5) emit `_LOGGER.info("Project %s/%s: mode=%s, ado_items=%d, asana_tasks=%d", ...)`; (6) call `app.db.set_sync_checkpoint(project_name, team_name, run_started_at.isoformat(), full_scan=is_full)` only after successful completion

- [x] T012 [US1] Write integration test `test_incremental_sync_processes_only_changed_items` in `tests/test_delta_sync_integration.py` — use real App+DB in temp dir; mock ADO/Asana clients; first cycle records checkpoint; second cycle verifies incremental fetch boundary is passed to mock ADO WIQL call and Asana `modified_since`; verify `last_sync_at` is the run-start time (not end time)

**Checkpoint**: US1 fully functional — incremental cycles reduce API calls proportionally.

---

## Phase 4: User Story 2 — First-Run Full Sync (Priority: P2)

**Goal**: A project with no stored checkpoint automatically performs a full scan and
records a checkpoint so subsequent runs can use the incremental path.

**Independent Test**: Clear `last_sync_at` for a project, trigger a sync cycle, verify
a full scan ran and both `last_sync_at` and `last_full_sync_at` are recorded as the
run-start time.

### Implementation for User Story 2

- [x] T013 [US2] Write integration test `test_first_run_triggers_full_scan_and_records_checkpoint` in `tests/test_delta_sync_integration.py` — project with NULL `last_sync_at`; mock full ADO + Asana fetch (not WIQL); verify after successful cycle: `last_sync_at` is non-null, `last_full_sync_at` is non-null, both equal the captured run-start time; verify next cycle enters incremental mode

- [x] T014 [US2] Write integration test `test_force_full_sync_overrides_existing_checkpoint` in `tests/test_delta_sync_integration.py` — project with existing checkpoint; set `FORCE_FULL_SYNC=True`; verify full ADO + Asana fetch is called (not WIQL incremental); verify checkpoint refreshed with new run-start time after success

**Checkpoint**: US1 + US2 independently functional — bootstrapping and incremental paths verified.

---

## Phase 5: User Story 3 — Graceful Fallback to Full Sync (Priority: P3)

**Goal**: When the incremental Asana fetch raises an API error, the system falls back to
a full task scan for that cycle, logs a warning, and retries incremental on the next run.

**Independent Test**: Inject an `ApiException` from `get_asana_tasks_modified_since()`.
Verify the cycle completes using the full Asana fetch, a WARNING is logged, and the next
cycle again attempts the incremental path.

### Implementation for User Story 3

- [x] T015 [US3] Wrap the `get_asana_tasks_modified_since()` call in `sync_project()` in `ado_asana_sync/sync/sync.py` with `try/except ApiException` — on exception: emit `_LOGGER.warning("Project %s: incremental Asana fetch failed (%s), falling back to full task scan", project_name, e)`; fall back to the existing full Asana task fetch for this cycle only; the incremental ADO fetch result is still used

- [x] T015b **[F6 fix]** Write integration test `test_pr_sync_path_unchanged_after_refactor` in `tests/test_delta_sync_integration.py` — after the `sync_project()` refactor (T011), verify that PR processing still invokes the full active-PR fetch on every cycle regardless of whether the work-item sync ran in incremental or full mode; mock ADO git client and assert it is called with `status="active"` on both cycle types

- [x] T016 [US3] Write integration test `test_asana_api_error_triggers_fallback_and_warning` in `tests/test_delta_sync_integration.py` — project with existing checkpoint; mock `get_asana_tasks_modified_since` to raise `ApiException`; verify: full Asana fetch called as fallback, WARNING log emitted, cycle completes successfully, `last_sync_at` updated; verify next cycle attempts incremental Asana path again

**Checkpoint**: All 3 user stories independently functional.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, quality gates, and operator-facing configuration updates.

- [x] T017 [P] Add `SYNC_OVERLAP_MINUTES` and `FORCE_FULL_SYNC` entries to `.env.example` with descriptive comments matching the quickstart.md descriptions

- [x] T018 Update `README.md` to document `SYNC_OVERLAP_MINUTES` and `FORCE_FULL_SYNC` environment variables in the "How to use" configuration section — follow existing env var entry format

- [x] T019 Run `uv run check` (`ruff` lint + format + `mypy`) across all modified files and fix any violations — zero ruff errors and zero mypy errors required

- [x] T020 Run `uv run test` and verify all new tests pass and overall coverage remains ≥ 60 %

- [x] T021 [P] Run `uv run mdformat *.md` on any modified markdown files and commit formatting fixes

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on T001 (Phase 1) — BLOCKS all user stories
- **US1 (Phase 3)**: Depends on Phase 2 complete (T002–T008)
- **US2 (Phase 4)**: Depends on Phase 3 complete (T009–T012); tests verify first-run path added in T011
- **US3 (Phase 5)**: Depends on Phase 3 complete (T011 specifically)
- **Polish (Phase 6)**: Depends on all user story phases complete

### User Story Dependencies

- **US1 (P1)**: Can start after Foundational — no dependency on US2 or US3
- **US2 (P2)**: Shares `sync_project()` with US1 — start after US1 complete
- **US3 (P3)**: Wraps US1's Asana fetch call — start after US1 complete; parallel with US2

### Within Each User Story

- T009 and T010 (US1): parallel — different files (`asana.py`, `sync.py`)
- T011 (US1): sequential — depends on T009 and T010
- T012 (US1): sequential — depends on T011
- T007 and T008 (Foundational): parallel — different test files
- T013 and T014 (US2): sequential — same test file, ordered addition
- T015 and T016 (US3): sequential — implementation then test

---

## Parallel Opportunities

```bash
# Foundational phase — after T002–T006 complete:
T007: Integration tests for DB methods      (tests/test_delta_sync_integration.py)
T008: Unit tests for determine_sync_mode()  (tests/test_delta_sync_unit.py)

# US1 implementation — can start in parallel once Phase 2 done:
T009: Asana incremental fetch helper        (ado_asana_sync/sync/asana.py)
T010: ADO WIQL incremental fetch            (ado_asana_sync/sync/sync.py)

# Polish — after all stories complete:
T017: Update .env.example                   (.env.example)
T021: Run mdformat                          (*.md)
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: T001 (setup)
2. Complete Phase 2: T002–T008 (foundation + tests)
3. Complete Phase 3: T009–T012 (incremental sync core)
4. **STOP and VALIDATE**: Run `uv run test`; verify incremental cycle integration test passes
5. Deploy/demo: subsequent sync cycles are measurably faster

### Incremental Delivery

1. Phase 1 + Phase 2 → Foundation verified
2. Phase 3 (US1) → Incremental sync works ✅ Deploy MVP
3. Phase 4 (US2) → First-run verified ✅ Deploy
4. Phase 5 (US3) → Fallback resilience ✅ Deploy
5. Phase 6 → Polish, docs, quality gates ✅ Merge-ready

---

## Notes

- `[P]` tasks touch different files and have no incomplete-task dependencies
- `run_started_at` must be captured with `datetime.now(timezone.utc)` **before** the first API call in `sync_project()` — this is the value stored in `last_sync_at`
- Mock only `ado_wit_client`, `asana.TasksApi` and similar external API clients in tests — use real `App`, real `Database`, and real `determine_sync_mode()`
- `set_sync_checkpoint()` is called **only** inside the success path — never in exception handlers
- PR sync (`pull_request_sync.py`) is **not modified** in any task
- After each task, run `uv run check` to catch ruff/mypy issues early
