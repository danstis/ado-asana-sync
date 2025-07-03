This document provides guidance for AI agents to interact with and contribute to this project.

## Project Overview

This repository implements a robust synchronization tool between Azure DevOps (ADO) and Asana. All core logic resides in the `ado_asana_sync` directory, with a primary focus on synchronizing tasks between these platforms.

## Getting Started

Follow these steps to set up your development environment:

1. Install [Poetry](https://python-poetry.org/).
2. Run `poetry install` to install all project dependencies.
3. Copy `.env.example` to `.env` and provide the required environment variable values.

## Development

### Main Components

- `ado_asana_sync/sync/app.py`: Serves as the main application entry point.
- `ado_asana_sync/sync/sync.py`: Contains the core synchronization logic between ADO and Asana.
- `ado_asana_sync/sync/asana.py`: Manages all interactions with the Asana API.
- `ado_asana_sync/sync/task_item.py`: Defines the `TaskItem` data structure for task representation.
- `data/projects.json.example`: Provides an example of the project data structure required for configuration.

### Coding Conventions

- Write all code in Python.
- Enforce linting with `pylint` (see `.pylintrc`).
- Adhere to formatting rules defined in `.editorconfig`.

## Testing

- Place all tests in the `tests/` directory.
- Use `pytest` as the testing framework.
- Run the test suite with the `tox` command, as configured in `tox.ini`.
- Ensure that test coverage remains above 60% for all changes. Add or update tests as necessary to maintain this threshold.

## CI/CD

- Use GitHub Actions for all CI/CD workflows.
- Define workflows in the `.github/workflows/` directory.
- Ensure all code is built, analyzed with CodeQL, and released through these workflows.

## Dependencies

- Manage dependencies exclusively with Poetry. All dependencies are listed in `pyproject.toml`.
- Add new dependencies using `poetry add <dependency>`.

## Configuration

- Manage all configuration through environment variables. Reference `.env.example` for required variables.
- Configure project data in JSON format, as demonstrated in `data/projects.json.example`.

## Commits

- Follow the [Conventional Commits](https://www.conventionalcommits.org/) specification for all commit messages.
