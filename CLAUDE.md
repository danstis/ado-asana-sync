# Claude CLI Agent Guide

Welcome! This document is tailored for Claude CLI agents contributing to the Azure DevOps (ADO) and Asana synchronization project. Please read carefully to understand the project context, setup, and contribution guidelines.

## Project Context

This repository provides a robust tool for synchronizing tasks between Azure DevOps and Asana. The main logic is located in the `ado_asana_sync` directory, focusing on seamless task synchronization between the two platforms.

## Getting Started

- Install [uv](https://docs.astral.sh/uv/) to manage dependencies and environments.
- Run `uv sync --dev` to set up all required dependencies.
- Copy `.env.example` to `.env` and fill in all necessary environment variables as described in the example file.

## Development Practices

- Key files:
  - `ado_asana_sync/sync/app.py`: Main entry point.
  - `ado_asana_sync/sync/sync.py`: Core sync logic including due date synchronization.
  - `ado_asana_sync/sync/asana.py`: Handles Asana API.
  - `ado_asana_sync/sync/task_item.py`: Task data structure with due_date field support.
  - `ado_asana_sync/sync/pull_request_item.py`: Pull request data structure.
  - `ado_asana_sync/sync/pull_request_sync.py`: Pull request sync logic.
  - `data/projects.json.example`: Example project configuration.
- Write all code in Python.
- Enforce linting and formatting with `ruff` (configured in `pyproject.toml`).
- Enforce markdown formatting with `mdformat` for all `.md` files.
- Add dependencies only with `uv add <dependency>`.
- Run tools using `uv run`.
- Always update the readme and other documentation based on the changes made.

## Code Quality Requirements

- **Python Code**: Use `ruff` for linting, formatting, and security checks
- **Type Checking**: Use `mypy` for static type analysis
- **Markdown Files**: Use `mdformat` to ensure consistent formatting
- **Testing**: Place all tests in the `tests/` directory and use `pytest`
- **Coverage**: Ensure test coverage remains above 60% for all changes
- **Tool Configuration**: **ALWAYS** use the settings defined in `pyproject.toml` for all code quality and linting tools

## Test Quality Standards

**CRITICAL**: Follow these testing principles to avoid brittle, over-mocked tests that provide false confidence:

### The Mock-Only-At-Boundaries Principle

✅ **DO Mock (External Dependencies)**:

- External APIs (Asana API, ADO API)
- Network calls and HTTP requests
- File system roots (redirect to temp directories)
- External services and databases (when not using test instances)
- System clocks and timestamps (for deterministic tests)

❌ **DO NOT Mock (Internal Code)**:

- Internal utility functions (`extract_due_date_from_ado`, `matching_user`, etc.)
- Internal business logic classes (`TaskItem`, `App`)
- Internal data transformations and validations
- Internal error handling and logging
- Database operations (use real test databases instead)

### Test Types and Integration Levels

1. **Unit Tests** (20% of test suite):

   - Test individual functions in isolation
   - Mock dependencies that would make test slow/flaky
   - Focus on edge cases and error conditions

1. **Integration Tests** (70% of test suite):

   - Test multiple internal components working together
   - Use REAL App instances with REAL databases (in temp directories)
   - Use REAL business objects and data structures
   - Mock ONLY external API boundaries
   - Test actual business logic flows end-to-end

1. **System Tests** (10% of test suite):

   - Test complete workflows with external services
   - Use test/staging environments for external APIs
   - Validate end-to-end functionality

### Test Object Construction

Use test builders that create REAL objects:

```python
# ✅ GOOD - Create real objects
app = TestDataBuilder.create_real_app(temp_dir)
reviewer = RealObjectBuilder.create_real_ado_reviewer(...)
work_item = TestDataBuilder.create_ado_work_item(...)

# ❌ BAD - Over-use of mocks
app = MagicMock(spec=App)  
reviewer = MagicMock()
work_item = MagicMock()
```

### Test Database Strategy

- **Use real SQLite databases** in temporary directories
- **Test actual database operations** (CREATE, READ, UPDATE, DELETE)
- **Verify real data persistence and retrieval**
- **Test database migration and fallback logic**

```python
# ✅ GOOD - Real database integration
with tempfile.TemporaryDirectory() as temp_dir:
    app = TestDataBuilder.create_real_app(temp_dir)
    app.connect()  # Real database initialization
    
    # Test real database operations
    result = read_projects(app)  # Uses real App with real DB

# ❌ BAD - Mocked database
app = MagicMock()
app.db = MagicMock()
app.db.get_projects.return_value = [...]
```

### Integration Test Requirements

Integration tests MUST achieve 80%+ real code path coverage by:

1. **Using real App instances** with real database connections
1. **Processing real business objects** with real data
1. **Testing real internal function integration** working together
1. **Validating real data transformations** and business logic
1. **Exercising real error handling** and edge cases
1. **Only mocking at external API boundaries**

### Test Assertion Quality

Focus on **behavior verification** not **interaction verification**:

```python
# ✅ GOOD - Test actual outcomes
saved_items = app.matches.all()  # Real database query
self.assertEqual(saved_items[0]["due_date"], "2025-12-31")  # Real data

# ❌ BAD - Test mock interactions  
mock_insert.assert_called_once_with(...)  # Just tests mocking
```

### Test Naming Convention

- Unit tests: `test_function_name_specific_case`
- Integration tests: `test_feature_name_real_integration` or `test_workflow_name_integration`
- Mark integration levels clearly in docstrings

### When Mocking Internal Code is Acceptable

Only mock internal components when:

1. **Testing error conditions** that are hard to trigger naturally
1. **Testing specific branches** in complex conditional logic
1. **Isolating performance-critical code** from slow dependencies
1. **Testing timeout/retry logic** that would make tests slow

Always justify internal mocking in test comments and prefer real object approaches when possible.

### Code Quality Tool Configuration

All linting and code quality tools are configured in `pyproject.toml` and orchestrated via Python scripts:

- **ruff**: Handles linting, formatting, and security checks with line length 127 and max complexity 10 - Run with `uv run lint` or `uv run format-check` (scans entire project, respects `.gitignore`)
- **pytest**: Includes coverage reporting with branch coverage - Run with `uv run test`
- **mypy**: Static type checking with missing import ignoring - Run with `uv run type-check`
- **All together**: Run all quality checks in parallel - Run with `uv run check`

**IMPORTANT**: Always use `uv run <command>` to run quality checks. This ensures exact consistency with CI/CD pipelines and uses the precise settings defined in `pyproject.toml`.

### Markdown Linting Workflow

When editing markdown files (`.md`), always run the markdown formatter:

1. **Check formatting**: `uv run mdformat --check *.md`
1. **Auto-fix formatting**: `uv run mdformat *.md`
1. **Verify changes**: Review any changes made by the formatter before committing

The markdown formatter ensures:

- Consistent heading styles
- Proper list formatting
- Table formatting (with GitHub Flavored Markdown support)
- Line ending consistency

## CI/CD Workflow

- All CI/CD is managed with GitHub Actions, defined in `.github/workflows/`.
- Workflows must build, analyze (CodeQL), and release the code.
- **IMPORTANT**: When you modify any code or markdown files, you MUST run quality checks before completing your work:
  - **Code Quality Tools**:
    - Linting: `uv run lint`
    - Formatting check: `uv run format-check`
    - **Auto-fix formatting**: `uv run ruff format` on modified files to ensure correct formatting
    - Type Checking: `uv run type-check`
    - All Together: `uv run check` (runs in parallel)
  - **Testing**: `uv run test` to run tests with coverage
  - **Markdown**: `uv run mdformat --check *.md` to check formatting, `uv run mdformat *.md` to fix
  - All tools use the exact settings defined in `pyproject.toml` for consistency with CI/CD

### Dependency Management and Security Scanning

This project uses **uv** for dependency management with `pyproject.toml` and `uv.lock` files. For security scanning compatibility with tools like Mend Bolt:

- **Automated requirements.txt sync**: The `sync-requirements.yml` workflow automatically generates and commits `requirements.txt` from `uv.lock` whenever dependency files change
- **When it runs**: Triggers on PRs and pushes to main when `pyproject.toml` or `uv.lock` are modified
- **What it does**: Exports dependencies using `uv export --format requirements-txt --no-hashes` and commits changes
- **Why**: Mend Bolt and similar security scanning tools don't yet support `uv.lock` files, but do support `requirements.txt`
- **Manual generation**: You can also generate it manually with `uv export --format requirements-txt --no-hashes > requirements.txt`

## Current Features

### Due Date Synchronization (Feature 001)

- Syncs due dates from ADO work items to Asana tasks during **initial creation only**
- Preserves user modifications in Asana to prevent data loss
- Uses ADO field: `Microsoft.VSTS.Scheduling.DueDate` → Asana field: `due_on`
- Handles invalid dates gracefully with warning logs, continues sync operation
- TaskItem extended with optional `due_date` field stored in JSON database
- Performance tested for 5000+ work items without degradation

## Configuration

- All configuration is via environment variables (see `.env.example`).
- Project data is managed in JSON format, as shown in `data/projects.json.example`.

## Commit Standards

- All commits must follow the [Conventional Commits specification](https://www.conventionalcommits.org/).

Thank you for contributing as a Claude CLI agent! If you have questions, refer to this guide or the main AGENTS.md for further context.
