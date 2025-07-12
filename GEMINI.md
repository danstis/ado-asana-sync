# Gemini CLI Agent Instructions

## Project Overview

- This project syncs tasks between Azure DevOps (ADO) and Asana.
- All main logic is in the `ado_asana_sync` directory.

## Setup Steps

1. Install Poetry: [https://python-poetry.org/](https://python-poetry.org/)
2. Run `poetry install` to install dependencies.
3. Copy `.env.example` to `.env` and fill in required environment variables.

## Development Guidelines

- Main files:
  - `ado_asana_sync/sync/app.py`: Application entry point.
  - `ado_asana_sync/sync/sync.py`: Core sync logic.
  - `ado_asana_sync/sync/asana.py`: Asana API interactions.
  - `ado_asana_sync/sync/task_item.py`: Task data structure.
  - `data/projects.json.example`: Project config example.
- Write Python code only.
- Use `pylint`, `flake8`, and `.editorconfig` for linting and formatting.
- Add dependencies with `poetry add <dependency>`.
- Run tools using `poetry run`.
- Always update the readme and other documentation based on the changes made.

## Testing

- Place tests in `tests/`.
- Use `pytest` and run tests with `tox`.
- Maintain >60% coverage. Check with `pytest-cov`.

## CI/CD

- Use GitHub Actions in `.github/workflows/`.
- Build, analyze (CodeQL), and release via workflows.

## Configuration

- Use environment variables as in `.env.example`.
- Project data is JSON, see `data/projects.json.example`.

## Commits

- Use Conventional Commits: [https://www.conventionalcommits.org/](https://www.conventionalcommits.org/)
