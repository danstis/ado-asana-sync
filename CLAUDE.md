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
- **Tool Configuration**: **ALWAYS** use the settings defined in `tox.ini` for all code quality and linting tools

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
  - All tools use the exact settings defined in `tox.ini` for consistency with CI/CD

## Configuration

- All configuration is via environment variables (see `.env.example`).
- Project data is managed in JSON format, as shown in `data/projects.json.example`.

## Commit Standards

- All commits must follow the [Conventional Commits specification](https://www.conventionalcommits.org/).

Thank you for contributing as a Claude CLI agent! If you have questions, refer to this guide or the main AGENTS.md for further context.
