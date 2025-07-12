# Claude CLI Agent Guide

Welcome! This document is tailored for Claude CLI agents contributing to the Azure DevOps (ADO) and Asana synchronization project. Please read carefully to understand the project context, setup, and contribution guidelines.

## Project Context

This repository provides a robust tool for synchronizing tasks between Azure DevOps and Asana. The main logic is located in the `ado_asana_sync` directory, focusing on seamless task synchronization between the two platforms.

## Getting Started

- Install [Poetry](https://python-poetry.org/) to manage dependencies and environments.
- Run `poetry install` to set up all required dependencies.
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
- Enforce linting with `pylint` and `flake8` (see `.pylintrc` and `.editorconfig`).
- Add dependencies only with `poetry add <dependency>`.
- Run tools using `poetry run`.
- Always update the readme and other documentation based on the changes made.

## Testing Requirements

- Place all tests in the `tests/` directory.
- Use `pytest` for testing and run the suite with `tox`.
- Ensure test coverage remains above 60% for all changes. Use `pytest-cov` to check coverage.

## CI/CD Workflow

- All CI/CD is managed with GitHub Actions, defined in `.github/workflows/`.
- Workflows must build, analyze (CodeQL), and release the code.

## Configuration

- All configuration is via environment variables (see `.env.example`).
- Project data is managed in JSON format, as shown in `data/projects.json.example`.

## Commit Standards

- All commits must follow the [Conventional Commits specification](https://www.conventionalcommits.org/).

Thank you for contributing as a Claude CLI agent! If you have questions, refer to this guide or the main AGENTS.md for further context.
