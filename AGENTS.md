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

- Linting, formatting, security: `uv run tox -e ruff` (max line length 127, complexity 10)
- Types: `uv run tox -e mypy`
- All at once: `uv run tox -e ruff,mypy`
- Tests + coverage: `uv run tox -e pytest` (coverage enforced ≥ 60%)
- Markdown: `uv run mdformat --check *.md` then `uv run mdformat *.md`

## Coding Style & Naming

- Python 3.13, 4‑space indent, `snake_case` for modules/functions
- Follow `pyproject.toml`, `.editorconfig`, and `tox.ini` strictly

## Testing Guidelines

- Framework: `pytest` with coverage/branch coverage
- Name tests `test_*.py` under `tests/`
- Write small, deterministic tests around sync logic and API boundaries

## Commits, PRs, and CI

- Commits: Conventional Commits (e.g., `feat: add PR reviewer sync cache`)
- PRs: clear description, linked issues, screenshots/notes if user‑visible
- Before submitting: run ruff, mypy, pytest, and mdformat (as above)
- CI: GitHub Actions runs builds, CodeQL analysis, and releases; keep docs/examples current
