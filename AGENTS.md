# AGENTS.md

This document provides guidance for AI agents to interact with and contribute to this project.

## Project Overview

This repository implements a robust synchronization tool between Azure DevOps (ADO) and Asana. All core logic resides in the `ado_asana_sync` directory, with a primary focus on synchronizing tasks and pull requests between these platforms.

## Getting Started

Follow these steps to set up your development environment:

1. Install [uv](https://docs.astral.sh/uv/).
1. Run `uv sync --dev` to install all project dependencies.
1. Copy `.env.example` to `.env` and provide the required environment variable values.

## Development

### Main Components

- `ado_asana_sync/sync/app.py`: Serves as the main application entry point.
- `ado_asana_sync/sync/sync.py`: Contains the core synchronization logic between ADO and Asana.
- `ado_asana_sync/sync/asana.py`: Manages all interactions with the Asana API (tags, task lookups).
- `ado_asana_sync/sync/asana_client.py`: Asana API helpers for workspaces, projects, tasks, and user membership queries.
- `ado_asana_sync/sync/ado_parser.py`: ADO-specific item parsing utilities (extracts assigned user details from work items).
- `ado_asana_sync/sync/matching.py`: User and task matching logic between ADO and Asana (email/display-name lookup).
- `ado_asana_sync/sync/dry_run.py`: Dry-run tracking helpers; records planned create/update/close actions without writing to Asana.
- `ado_asana_sync/sync/task_item.py`: Defines the `TaskItem` data structure for task representation.
- `ado_asana_sync/sync/task_factory.py`: Logic for building Asana task request bodies and saving newly created tasks.
- `ado_asana_sync/sync/pull_request_item.py`: Defines the `PullRequestItem` data structure for PR-reviewer relationships.
- `ado_asana_sync/sync/pr_sync_core.py`: PR sync orchestration (`sync_pull_requests`, `process_repository_pull_requests`, `process_closed_pull_requests`).
- `ado_asana_sync/sync/pr_processor.py`: Logic for processing individual PRs and reviewers, including group-reviewer detection and fallback handling (`process_pull_request`, `process_pr_reviewer`, `handle_removed_reviewers`, `create_new_pr_reviewer_task`, `update_existing_pr_reviewer_task`, `is_group_reviewer`, `_handle_group_reviewer`).
- `ado_asana_sync/sync/pr_asana_helpers.py`: Asana helpers specific to PRs (`create_asana_pr_task`, `update_asana_pr_task`, `add_tag_to_pr_task`, `add_closure_comment_to_pr_task`).
- `ado_asana_sync/sync/pull_request_sync.py`: Re-export facade for backward compatibility.
- `ado_asana_sync/sync/utils.py`: Shared utility functions (reviewer vote extraction, date conversion, URL encoding).
- `ado_asana_sync/database/connection.py`: SQLite `Database` and `DatabaseTable` classes; exposes `search_by_json_fields`, `update_by_json_fields`, `upsert_by_json_fields`, and `remove_by_json_fields` for index-backed hot-path queries.
- `ado_asana_sync/database/migrations.py`: `DatabaseMigrationsMixin` with schema versioning and migration helpers; currently at schema version 3 with indexes on `ado_id`, `asana_gid`, `ado_pr_id`, and `reviewer_gid`.
- `data/projects.json.example`: Provides an example of the project data structure required for configuration.

### Database Query Guidelines

For **hot-path queries** that filter by indexed fields (`ado_id`, `asana_gid`, `ado_pr_id`, `reviewer_gid`), always use the SQL-backed methods on `DatabaseTable` instead of `.all()` or `.get()`. This avoids full table scans and prevents performance regressions as the database grows:

- `table.search_by_json_fields({"ado_id": value})` — indexed lookup; use instead of `.all()` + manual filtering
- `table.update_by_json_fields(data, {"ado_id": value})` — indexed update; use instead of `.update(data, query_func)`
- `table.upsert_by_json_fields(data, {"ado_id": value})` — indexed upsert; use instead of `.upsert(data, query_func)`
- `table.remove_by_json_fields({"ado_id": value})` — indexed delete; use instead of `.remove(query_func=...)`

Reserve `.all()` for operations that genuinely require every row (e.g. bulk exports, test assertions on full state). Reserve `.search(query_func)` for complex predicates that cannot be expressed as simple equality conditions on indexed fields.

### Coding Conventions

- Write all code in Python.
- Keep every function at or below a cyclomatic complexity of 15 (enforced by Ruff's McCabe check, `C901`).
- Run tools using `uv run`.
- Enforce linting and formatting with `ruff` (configured in `pyproject.toml`).
- Adhere to formatting rules defined in `.editorconfig`.
- Ensure all code passes `ruff` checks for style, formatting, and security.
- Always update the readme and other documentation based on the changes made.

### AI Agentic Coding Optimization

- **Context-Optimized File Structure**: Break code into smaller, focused files containing only related functions. This ensures files are easily read into context by AI agents without over-stuffing the context window.
- Each module should have a single, clear responsibility so agents can load only the relevant context for a given task.
- Prefer many small, focused files over large files with mixed concerns.

## Testing

- Place all tests in the `tests/` directory.
- Use `pytest` as the testing framework.
- Run the full test suite (including E2E) with `uv run test`.
- Ensure that test coverage remains above 60% for all changes. Add or update tests as necessary to maintain this threshold.
- Check coverage with `pytest-cov`.

### End-to-End Tests

The E2E test suite lives in `tests/e2e/` and validates the complete sync workflow without requiring real ADO or Asana credentials.

**Running E2E tests:**

```bash
uv run pytest tests/e2e/ -v
```

The suite is currently split across:

- `tests/e2e/test_e2e_work_items.py`: work item sync scenarios
- `tests/e2e/test_e2e_pull_requests.py`: pull request reviewer sync scenarios

**Key principles for E2E tests:**

- Use real `App` instances with real SQLite databases in temporary directories.
- Mock only ADO and Asana API boundaries (never internal business logic).
- Pre-seed `app.matches` / `app.pr_matches` to set up the initial database state.
- Assert on actual database state and Asana API call arguments.
- All tests are non-destructive: temporary directories are cleaned up in `tearDown`.

**Adding a new E2E scenario:**

1. Add a test method to `TestE2ESyncWorkItems` in `tests/e2e/test_e2e_work_items.py` (for work items) or `TestE2ESyncPullRequests` in `tests/e2e/test_e2e_pull_requests.py` (for PRs).
1. Pre-seed DB if testing an update/close/reopen scenario using `app.matches.insert(...)`.
1. Set up ADO mock responses via `mock_wit.get_work_item.return_value = ...`.
1. Assert on `tasks_api.create_task` / `tasks_api.update_task` call arguments and on `app.matches.all()` / `app.pr_matches.all()` database state.

### Group Reviewer Fallback Strategies

ADO pull requests can include group/container reviewers such as `[Project]\\Contributors`. The sync behavior is controlled by `GROUP_REVIEWER_STRATEGY`:

- `ignore`: skip group reviewers entirely. This is the default.
- `default_user`: create or update the reviewer task and assign it to `GROUP_REVIEWER_DEFAULT_USER`. The fallback user can be resolved by Asana email, GID, or display name.
- `unassigned_task`: create or update the reviewer task without an assignee, preserving the group name in the task title.

If `GROUP_REVIEWER_STRATEGY=default_user` but `GROUP_REVIEWER_DEFAULT_USER` is unset or cannot be resolved, the group reviewer is skipped.

## CI/CD

- Use GitHub Actions for all CI/CD workflows.
- Define workflows in the `.github/workflows/` directory.
- Ensure all code is built, analyzed with CodeQL, and released through these workflows.

## Dependencies

- Manage dependencies exclusively with uv. All dependencies are listed in `pyproject.toml`.
- Add new dependencies using `uv add <dependency>`.

## Configuration

- Manage all configuration through environment variables. Reference `.env.example` for required variables.
- Configure project data in JSON format, as demonstrated in `data/projects.json.example`.

## Commits

- Follow the [Conventional Commits](https://www.conventionalcommits.org/) specification for all commit messages.

# Repository Guidelines

## Project Structure & Module Organization

- Source: `ado_asana_sync/`
  - `sync/app.py`: entry point
  - `sync/sync.py`: ADO ↔ Asana sync core
  - `sync/asana.py`: Asana API helpers (tags, task lookups)
  - `sync/asana_client.py`: workspace/project/task/membership queries
  - `sync/ado_parser.py`: ADO work item parsing (assigned user extraction)
  - `sync/matching.py`: ADO ↔ Asana user matching by email/display name
  - `sync/dry_run.py`: dry-run report tracking (no writes to Asana)
  - `sync/task_item.py`, `sync/pull_request_item.py`: data models
  - `sync/task_factory.py`: Asana task body construction and save helpers
  - `sync/pr_sync_core.py`: PR sync orchestration
  - `sync/pr_processor.py`: individual PR and reviewer processing
  - `sync/pr_asana_helpers.py`: Asana helpers specific to PRs
  - `sync/pull_request_sync.py`: re-export facade for backward compatibility
  - `sync/utils.py`: shared utilities (vote extraction, date conversion, URL encoding)
  - `utils/`: logging/tracing, time helpers
  - `database/connection.py`: `Database` and `DatabaseTable` classes (SQLite persistence)
  - `database/migrations.py`: schema versioning and migration helpers
- Config example: `data/projects.json.example`
- Tests: `tests/`

## Setup & Configuration

- Install dependencies: `uv sync --dev`
- Configure env: copy `.env.example` → `.env` and fill required values
- Dependencies: manage with uv only (`uv add <name>`)

## Quality & Tooling (use tox.ini settings)

- Linting: `uv run lint`, Formatting check: `uv run format-check` (max line length 127, complexity 15)
- Types: `uv run type-check`
- All at once: `uv run check` (runs in parallel)
- Tests + coverage: `uv run test` (coverage enforced ≥ 60%)
- Markdown: `uv run mdformat --check *.md` then `uv run mdformat *.md`

## Coding Style & Naming

- Python 3.13, 4‑space indent, `snake_case` for modules/functions
- Follow `pyproject.toml` and `.editorconfig` strictly

## Testing Guidelines

**CRITICAL**: Follow these testing principles to create effective, non-brittle tests that provide real confidence:

### Test Architecture Principles

- **Framework**: `pytest` with coverage/branch coverage
- **Location**: Name tests `test_*.py` under `tests/`
- **Integration Focus**: 70% integration tests, 20% unit tests, 10% system tests
- **Mock-Only-At-Boundaries**: Mock external APIs only, use real internal objects

### The Golden Rules of Testing

#### ✅ DO (Mock External Dependencies)

- External APIs: Asana API, ADO API calls
- Network requests and HTTP operations
- File system roots (redirect to temp directories)
- System clocks for deterministic timestamps

#### ❌ DO NOT (Mock Internal Code)

- Internal utility functions (`extract_due_date_from_ado`, `matching_user`, etc.)
- Business logic classes (`TaskItem`, `App`, `PullRequestItem`)
- Internal data transformations and validations
- Database operations (use real test databases)

### Test Construction Standards

1. **Use Real Objects**: Create REAL App instances, real business objects, real databases in temp directories
1. **Test Real Flows**: Let internal functions work together naturally to test actual integration
1. **Verify Real Behavior**: Assert on actual data outcomes, not mock interactions
1. **Real Error Handling**: Test actual exception paths and error conditions

### Test Builder Pattern

Use test builders to create real objects:

```python
# ✅ GOOD - Integration test with real objects
def test_due_date_sync_real_integration(self):
    with tempfile.TemporaryDirectory() as temp_dir:
        app = TestDataBuilder.create_real_app(temp_dir)
        work_item = TestDataBuilder.create_ado_work_item(due_date="2025-12-31")
        
        # Only mock external APIs
        with patch("sync.asana.TasksApi") as mock_api:
            process_backlog_item(app, work_item, ...)
            # Test real database operations and business logic

# ❌ BAD - Over-mocked test  
def test_due_date_sync_over_mocked(self):
    app = MagicMock()  # Mocking internal business object
    work_item = MagicMock()  # Mocking internal data
    
    with patch("sync.extract_due_date") as mock_extract:  # Mocking internal logic
        # Tests mock interactions, not real behavior
```

### Integration Test Requirements

Integration tests MUST:

- Use real App instances with real databases
- Process real business objects with real data
- Exercise 80%+ of actual code paths
- Test real internal function integration
- Only mock at external API boundaries
- Verify real data outcomes, not mock calls

### Test Quality Verification

Before submitting tests, verify:

1. **Real Object Usage**: Are you using `TestDataBuilder.create_real_app()` instead of `MagicMock(spec=App)`?
1. **Integration Depth**: Does your test exercise multiple internal functions working together?
1. **Boundary Mocking**: Are you only mocking external APIs and network calls?
1. **Behavior Testing**: Are you asserting on real data outcomes, not mock interactions?
1. **Error Path Coverage**: Does your test exercise real error handling and edge cases?

### Test Naming and Documentation

- Integration tests: `test_feature_name_real_integration`
- Unit tests: `test_function_name_specific_case`
- System tests: `test_workflow_name_end_to_end`
- Document integration level and what real code paths are tested

### When Internal Mocking is Acceptable

Only mock internal code when:

1. Testing specific error conditions that are hard to trigger naturally
1. Isolating slow operations in performance-critical tests
1. Testing timeout/retry logic that would make tests slow
1. **Always justify internal mocking in test comments**

The goal is tests that catch real bugs, are maintainable, and provide confidence that production code actually works.

## Commits, PRs, and CI

- Commits: Conventional Commits (e.g., `feat: add PR reviewer sync cache`)
- PRs: clear description, linked issues, screenshots/notes if user‑visible
- Before submitting: run `uv run check`, `uv run test`, and mdformat (as above)
- CI: GitHub Actions runs builds, CodeQL analysis, and releases; keep docs/examples current
