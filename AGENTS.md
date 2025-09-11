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
- `ado_asana_sync/sync/asana.py`: Manages all interactions with the Asana API.
- `ado_asana_sync/sync/task_item.py`: Defines the `TaskItem` data structure for task representation.
- `ado_asana_sync/sync/pull_request_item.py`: Defines the `PullRequestItem` data structure for PR-reviewer relationships.
- `ado_asana_sync/sync/pull_request_sync.py`: Contains the pull request synchronization logic.
- `data/projects.json.example`: Provides an example of the project data structure required for configuration.

### Coding Conventions

- Write all code in Python.
- Run tools using `uv run`.
- Enforce linting and formatting with `ruff` (configured in `pyproject.toml`).
- Adhere to formatting rules defined in `.editorconfig`.
- Ensure all code passes `ruff` checks for style, formatting, and security.
- Always update the readme and other documentation based on the changes made.

## Testing

- Place all tests in the `tests/` directory.
- Use `pytest` as the testing framework.
- Run the test suite with the `tox` command, as configured in `tox.ini`.
- Ensure that test coverage remains above 60% for all changes. Add or update tests as necessary to maintain this threshold.
- Check coverage with `pytest-cov`.

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
  - `sync/asana.py`: Asana API helpers
  - `sync/task_item.py`, `sync/pull_request_item.py`: data models
  - `sync/pull_request_sync.py`: PR reviewer task sync
  - `utils/`: logging/tracing, time helpers
  - `database/`: TinyDB persistence
- Config example: `data/projects.json.example`
- Tests: `tests/`

## Setup & Configuration

- Install dependencies: `uv sync --dev`
- Configure env: copy `.env.example` → `.env` and fill required values
- Dependencies: manage with uv only (`uv add <name>`)

## Quality & Tooling (use tox.ini settings)

- Linting: `uv run lint`, Formatting check: `uv run format-check` (max line length 127, complexity 10)
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
