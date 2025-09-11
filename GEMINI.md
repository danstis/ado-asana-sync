# Gemini CLI Agent Instructions

## Project Overview

- This project syncs tasks between Azure DevOps (ADO) and Asana.
- All main logic is in the `ado_asana_sync` directory.

## Setup Steps

1. Install uv: [https://docs.astral.sh/uv/](https://docs.astral.sh/uv/)
1. Run `uv sync --dev` to install dependencies.
1. Copy `.env.example` to `.env` and fill in required environment variables.

## Development Guidelines

- Main files:
  - `ado_asana_sync/sync/app.py`: Application entry point.
  - `ado_asana_sync/sync/sync.py`: Core sync logic.
  - `ado_asana_sync/sync/asana.py`: Asana API interactions.
  - `ado_asana_sync/sync/task_item.py`: Task data structure.
  - `data/projects.json.example`: Project config example.
- Run tools using `uv run <tool and args>`.
- Write Python code only.
- Use `uv run ruff` for linting, formatting, and security checks, plus `.editorconfig`.
- Add dependencies with `uv add <dependency>`.
- Always update the readme and other documentation based on the changes made.

## Testing

- Place tests in `tests/`.
- Use `pytest` and run tests with `uv run pytest`.
- Maintain >60% coverage.

## CI/CD

- Use GitHub Actions in `.github/workflows/`.
- Build, analyze (CodeQL), and release via workflows.

## Configuration

- Use environment variables as in `.env.example`.
- Project data is JSON, see `data/projects.json.example`.

## Commits

- Use Conventional Commits: [https://www.conventionalcommits.org/](https://www.conventionalcommits.org/)
