# Copilot Agent Guide

This document provides guidance for Copilot agents contributing to the Azure DevOps (ADO) and Asana synchronization project. Please read carefully to understand the project context, setup, and contribution guidelines.

## Project Context

This repository provides a robust tool for synchronizing tasks between Azure DevOps and Asana. The main logic is located in the `ado_asana_sync` directory, focusing on seamless task synchronization between the two platforms.

## Getting Started

- Install [uv](https://docs.astral.sh/uv/) to manage dependencies and environments.
- Run `uv sync --dev` to set up all required dependencies.
- Copy `.env.example` to `.env` and fill in all necessary environment variables as described in the example file.

## Development Practices

Key files:

- `ado_asana_sync/sync/app.py`: Main entry point.

- `ado_asana_sync/sync/sync.py`: Core sync logic.

- `ado_asana_sync/sync/asana.py`: Handles Asana API.

- `ado_asana_sync/sync/task_item.py`: Task data structure.

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

## Testing Standards - CRITICAL

**AVOID OVER-MOCKING**: Follow these strict testing principles to prevent brittle tests that provide false confidence:

### Mock-Only-At-Boundaries Rule

✅ **ALWAYS Mock**: External APIs (Asana/ADO), network calls, file system roots
❌ **NEVER Mock**: Internal functions, business classes, database operations, internal transformations

### Test Construction Checklist

Before writing any test, verify:

1. **Use Real Objects**: `TestDataBuilder.create_real_app(temp_dir)` not `MagicMock(spec=App)`
1. **Real Integration**: Let internal functions work together naturally
1. **Real Databases**: Use SQLite in temp directories, not database mocks
1. **Test Real Behavior**: Assert on actual data outcomes, not mock interactions
1. **External-Only Mocking**: Mock only Asana API, ADO API, network calls

### Quick Test Quality Check

```python
# ✅ GOOD Integration Test
def test_feature_real_integration(self):
    with tempfile.TemporaryDirectory() as temp_dir:
        app = TestDataBuilder.create_real_app(temp_dir)  # REAL App
        app.connect()  # REAL database
        
        work_item = TestDataBuilder.create_ado_work_item(...)  # REAL object
        
        # Only mock external APIs
        with patch("sync.asana.TasksApi"):
            result = process_backlog_item(app, work_item, ...)  # REAL integration
            
        # Test REAL database results
        saved_items = app.matches.all()  # REAL database query
        self.assertEqual(saved_items[0]["field"], expected)  # REAL data

# ❌ BAD Over-Mocked Test
def test_feature_over_mocked(self):
    app = MagicMock()  # ❌ Mocking internal business object
    work_item = MagicMock()  # ❌ Mocking internal data
    
    with patch("sync.internal_function"):  # ❌ Mocking internal logic
        # Tests mock interactions, not real behavior
        mock_function.assert_called_with(...)  # ❌ Testing mocks
```

### Test Type Distribution

- **70% Integration Tests**: Real objects, real databases, external API mocks only
- **20% Unit Tests**: Individual functions, appropriate mocking for speed/isolation
- **10% System Tests**: End-to-end with external services

### Integration Test Requirements

Every integration test MUST:

- Use `TestDataBuilder.create_real_app()` for real App instances
- Test with real databases in temporary directories
- Exercise 80%+ of actual internal code paths
- Mock only external API boundaries
- Validate real data outcomes and business logic

### Code Quality Tool Configuration

All linting and code quality tools are configured in `pyproject.toml` and orchestrated via Python scripts:

- **ruff**: Handles linting, formatting, and security checks with line length 127 and max complexity 10 - Run with `uv run lint` or `uv run format-check`
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
    - Type Checking: `uv run type-check`
    - All Together: `uv run check` (runs in parallel)
  - **Testing**: `uv run test` to run tests with coverage
  - **Markdown**: `uv run mdformat --check *.md` to check formatting, `uv run mdformat *.md` to fix
  - All tools use the exact settings defined in `pyproject.toml` for consistency with CI/CD

## Dependencies

- Manage dependencies exclusively with uv. All dependencies are listed in `pyproject.toml`.
- Add new dependencies using `uv add <dependency>`.

## Configuration

- All configuration is via environment variables (see `.env.example`).
- Project data is managed in JSON format, as shown in `data/projects.json.example`.

## Commit Standards

- All commits must follow the [Conventional Commits specification](https://www.conventionalcommits.org/).

Thank you for contributing as a Copilot agent! If you have questions, refer to this guide or the main AGENTS.md for further context.
