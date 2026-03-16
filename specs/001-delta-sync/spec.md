# Feature Specification: Delta Sync — Incremental Updates

**Feature Branch**: `001-delta-sync`
**Created**: 2026-03-15
**Status**: Draft
**Input**: User description: "Enhance Sync Performance with Delta Sync (Incremental Updates)"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Incremental Sync on Repeat Runs (Priority: P1)

An operator runs the sync tool repeatedly throughout the day. After the first successful run,
subsequent cycles only process items that changed since the last sync — rather than
re-examining every item in both platforms. This makes each cycle significantly faster and
consumes far fewer API calls, reducing the risk of hitting rate limits.

**Why this priority**: This is the core value of the feature. Without it, all other stories
are moot. It delivers immediate, measurable performance improvements for any deployment
with a growing backlog.

**Independent Test**: Can be fully tested by running two consecutive sync cycles against a
controlled data set where only a small subset of items change between runs. Verify that the
second cycle only processes the changed items and completes in proportionally less time.

**Acceptance Scenarios**:

1. **Given** a project has completed at least one successful sync, **When** a new sync cycle
   starts and no items have changed in either ADO or Asana, **Then** the sync completes
   without creating, updating, or closing any tasks, and the cycle duration is significantly
   shorter than a full scan.
2. **Given** a project has completed at least one successful sync, **When** a new sync cycle
   starts and only 5 of 2 000 ADO work items have been modified, **Then** the sync
   processes only those 5 items (plus any matching Asana tasks) and skips the remaining
   1 995.
3. **Given** a successful incremental sync completes, **When** the next cycle begins,
   **Then** the sync window starts from the end of the previous successful cycle (with a
   small safety overlap), not from the beginning of time.

---

### User Story 2 - First-Run Full Sync (Priority: P2)

An operator deploys the sync tool for the first time against a project, or resets the sync
state for an existing project. Because no previous sync timestamp exists, the system
automatically performs a complete scan of all items to establish the baseline mapping.

**Why this priority**: The incremental mechanism depends on a prior successful sync having
recorded a timestamp. Without a reliable first-run full sync, the feature cannot bootstrap
itself.

**Independent Test**: Can be fully tested by clearing the stored sync timestamp for a
project and triggering a sync cycle. Verify that all items are processed and a timestamp is
recorded at the end.

**Acceptance Scenarios**:

1. **Given** a project has no recorded sync timestamp, **When** a sync cycle starts,
   **Then** the system performs a full scan of all ADO work items and all Asana tasks for
   that project, processes them normally, and records a sync timestamp on successful
   completion.
2. **Given** an operator explicitly resets the sync state for a project, **When** the next
   sync cycle runs, **Then** the system treats that project as a first run and performs a
   full scan regardless of any previously stored data.

---

### User Story 3 - Graceful Fallback to Full Sync (Priority: P3)

If the incremental Asana fetch raises an API error, the system automatically falls back
to a full scan for that cycle rather than failing or producing incomplete results.
The operator is notified via logs that a fallback occurred. Zero results from the
incremental fetch are treated as valid and do NOT trigger a fallback.

**Why this priority**: Ensures correctness and resilience when the preferred incremental
path is unavailable, without requiring operator intervention for transient issues.

**Independent Test**: Can be tested by injecting an `ApiException` from the incremental
Asana fetch call. Verify that the system falls back to a full Asana task scan for that
cycle, completes successfully, and emits a warning-level log entry. Zero results from
the incremental fetch are treated as valid and do NOT trigger a fallback.

**Acceptance Scenarios**:

1. **Given** the incremental Asana fetch mechanism is unavailable or returns unreliable
   results, **When** a sync cycle runs, **Then** the system falls back to fetching all
   tasks for that project, logs a warning indicating the fallback occurred, and completes
   the sync successfully.
2. **Given** a fallback full sync completes successfully, **When** the next cycle runs,
   **Then** the system attempts the incremental path again (i.e., the fallback is not
   permanent).

---

### Edge Cases

- What happens when the sync process is interrupted mid-cycle? The timestamp MUST NOT be
  updated; the next run MUST re-process from the previous successful timestamp.
- What happens when an ADO work item is deleted? The system MUST detect the absence during
  periodic full scans or via status-based detection and clean up the corresponding Asana
  mapping.
- What happens when the sync has not run for an extended period (e.g., several days)?
  The system MUST still process all changes since the last recorded timestamp, regardless
  of elapsed time.
- What happens when both ADO and Asana report a change to the same mapped item? The system
  MUST process the item once using existing conflict-resolution logic.
- What happens when clocks between ADO and the sync host differ? The system MUST apply a
  safety overlap window so no changes fall into an unprocessed gap.

## Out of Scope

- **Pull request sync**: Delta sync optimisations do NOT apply to pull request processing.
  The ADO API does not support filtering PRs by last-modified time (only by creation or
  close date), and the Python SDK has a known open bug that omits date fields from
  `GitPullRequestSearchCriteria` entirely. Pull request sync continues to operate as today:
  all active PRs are fetched and evaluated on every cycle. A separate future feature may
  revisit this if the ADO API adds last-modified filtering for PRs.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST record the **start** timestamp of each successful sync cycle
  per project (i.e., the time at which the incremental fetch queries were issued, not the
  time the cycle finished). This ensures the next incremental window begins at the query
  boundary of the previous run, so any items modified during processing are not missed.
- **FR-002**: On subsequent sync cycles, the system MUST fetch only ADO work items whose
  last-modified date falls after the recorded timestamp for that project.
- **FR-003**: On subsequent sync cycles, the system MUST attempt to fetch only Asana tasks
  modified after the recorded timestamp for that project.
- **FR-004**: When no sync timestamp exists for a project, the system MUST perform a full
  scan of all ADO work items and all Asana tasks for that project.
- **FR-005**: The system MUST apply a globally configurable safety overlap window (default:
  5 minutes, controlled by the `SYNC_OVERLAP_MINUTES` environment variable) when computing
  the incremental fetch boundary to guard against clock skew. The same value applies to all
  projects.
- **FR-006**: If the incremental Asana fetch raises an API error, the system MUST fall back
  to a full Asana task fetch for that cycle and emit a warning-level log entry. A zero-result
  incremental fetch is treated as valid and does NOT trigger a fallback.
- **FR-007**: The sync timestamp (captured at the start of the run) MUST only be persisted
  after a cycle completes successfully; a mid-cycle failure MUST leave the previous stored
  timestamp intact so the next run re-processes from the previous successful boundary.
- **FR-008**: The system MUST support an operator-initiated full-sync reset via an
  environment variable (`FORCE_FULL_SYNC=true`) that, when set, causes the next run to
  perform a full scan for all projects and ignore stored sync timestamps. The timestamps
  MUST be refreshed on successful completion of that forced full run.
- **FR-009**: The system MUST log, at INFO level, whether each project sync cycle ran as
  incremental or full, and how many items were fetched from each platform.
- **FR-010**: The system MUST preserve all existing sync correctness guarantees (idempotency,
  bidirectional propagation, user-modification preservation) when operating in incremental
  mode.
- **FR-011**: The system MUST perform a full scan for each project at least once every
  24 hours to detect deleted ADO items and clean up stale Asana mappings, regardless of
  whether incremental sync is active.
- **FR-012**: Pull request sync MUST continue to fetch and evaluate all active PRs on every
  cycle, unchanged from current behaviour. Pull requests are not subject to incremental
  optimisation.

### Key Entities

- **Sync Checkpoint**: A per-project record of the UTC timestamp marking the **start**
  (query time) of the last successful sync cycle. Used to bound the next incremental fetch
  window. Has a relationship to the Project entity (one checkpoint per project).
- **Project**: An existing entity representing an ADO project paired with an Asana project.
  Extended to carry an optional Sync Checkpoint.
- **Candidate Item Set**: The union of ADO items changed since the last checkpoint and
  Asana tasks changed since the last checkpoint. Processed by existing sync logic.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After the first incremental sync cycle, subsequent cycles where fewer than
  5% of items changed complete in 10% or less of the time taken by a full scan of the same
  data set.
- **SC-002**: The number of external API calls made per sync cycle decreases proportionally
  to the fraction of items that changed since the last successful cycle.
- **SC-003**: No item that changed in ADO or Asana after the last sync checkpoint is missed
  by the incremental fetch (zero-miss correctness), validated over a 30-day observation
  period.
- **SC-004**: A first-run full sync on a project with 5 000+ work items completes without
  errors and records a valid checkpoint timestamp.
- **SC-005**: The system handles a graceful fallback without operator intervention and
  without data loss or skipped updates in 100% of simulated fallback scenarios.

## Clarifications

### Session 2026-03-15

- Q: Should pull request processing be included in delta sync optimisation? → A: No — PRs continue to be processed via full active-PR scan every cycle. Delta sync for PRs is explicitly out of scope for this feature due to ADO API limitations (no last-modified filter for PRs; Python SDK bug Issue #491).
- Q: How frequently should a periodic full sync run to catch deleted ADO items? → A: Daily — one full scan per project every 24 hours.
- Q: How should an operator trigger a forced full-sync reset? → A: Via environment variable (e.g., `FORCE_FULL_SYNC=true`) — consistent with the project's existing all-env-var configuration pattern.
- Q: What signal triggers the fallback from incremental to full Asana fetch? → A: API errors only — fall back only when the incremental fetch raises an exception; zero results are treated as valid (no heuristic checking).
- Q: Should the safety overlap window be configurable per-project or globally? → A: Global only — one environment variable (e.g., `SYNC_OVERLAP_MINUTES`) applies to all projects, defaulting to 5 minutes.

## Assumptions

- ADO's `ChangedDate` field is updated whenever a work item is modified, including state
  transitions and field edits relevant to sync.
- Asana's `modified_since` parameter on the tasks endpoint is available and honoured when
  filtering by project. If the call raises an `ApiException`, the system falls back to a
  full Asana task scan for that cycle (FR-006). The Events API (Option B) and in-memory
  filtering were evaluated and rejected during planning — Option B due to sync-token
  management complexity, in-memory filtering due to not reducing API call volume.
- The safety overlap window defaults to 5 minutes and is configurable via the
  `SYNC_OVERLAP_MINUTES` environment variable, consistent with the project's all-env-var
  configuration pattern. This single value applies globally to all projects.
- Deleted ADO items will be handled by a daily full-sync run (once every 24 hours per
  project) rather than real-time detection via delta sync. Stale Asana mappings may persist
  for up to 24 hours after an item is deleted in ADO.
- The existing per-project data structure is extensible to store the sync checkpoint without
  requiring a breaking schema migration for existing deployments.
