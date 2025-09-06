# ADO-Asana-Sync Constitution

## Core Principles

### I. Module-First Development
Every feature starts as a standalone module within the `ado_asana_sync` package; Modules must be self-contained, independently testable, and well-documented; Each module should have a single, clear responsibility (sync, database, API clients); No circular dependencies between modules allowed

### II. Poetry-Managed Dependencies
All dependencies managed through Poetry with exact version constraints; Development tools (pytest, pylint, flake8, mypy, bandit) configured in `tox.ini`; Run all tools via `poetry run` to ensure environment consistency; New dependencies added only via `poetry add` with justification

### III. Test-First Development (NON-NEGOTIABLE)
TDD mandatory: Tests written → Tests fail → Implementation → Tests pass; All tests in `tests/` directory using pytest framework; Maintain >60% test coverage for all changes; Integration tests required for API client interactions and sync logic

### IV. API Integration Testing
Integration tests required for: Azure DevOps API interactions, Asana API interactions, Database operations, Cross-platform sync operations; Mock external APIs for unit tests, use real APIs for integration tests; Test error handling and rate limiting scenarios

### V. Code Quality & Standards
All code must pass: `poetry run tox -e flake8,pylint,bandit,mypy` before commit; Line length max 127 characters; Markdown files formatted with `mdformat`; Follow Conventional Commits specification; Use GitVersion for semantic versioning

## Security & Configuration Requirements

All secrets and tokens managed via environment variables (`.env` file for development); Never commit secrets to repository - use `.env.example` for documentation; Personal Access Tokens (PAT) required for both Azure DevOps and Asana APIs; Database operations must be atomic to prevent data corruption during sync; Rate limiting respect for both Azure DevOps and Asana APIs

## Development Workflow

All changes go through Pull Request review process; GitHub Actions CI/CD must pass (build, test, lint, security scan); SonarCloud quality gates must be satisfied; Container images built and published to GitHub Container Registry; Manual testing checklist must be completed for sync-related changes; Breaking changes require version bump and migration documentation

## Governance

This constitution supersedes all other development practices; All PRs must verify compliance with code quality tools; Complexity must be justified with documentation; Use `CLAUDE.md` for runtime development guidance; Breaking changes to sync logic require extensive testing with real ADO/Asana instances

**Version**: 1.0.0 | **Ratified**: 2025-09-06 | **Last Amended**: 2025-09-06