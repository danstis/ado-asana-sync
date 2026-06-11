# ado-asana-sync

[![Test and Lint](https://github.com/danstis/ado-asana-sync/actions/workflows/build.yml/badge.svg)](https://github.com/danstis/ado-asana-sync/actions/workflows/build.yml)
[![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=danstis_ado-asana-sync&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=danstis_ado-asana-sync)
[![Coverage](https://sonarcloud.io/api/project_badges/measure?project=danstis_ado-asana-sync&metric=coverage)](https://sonarcloud.io/summary/new_code?id=danstis_ado-asana-sync)

[![Release](https://img.shields.io/github/release/danstis/ado-asana-sync.svg?style=flat-square)](https://github.com/danstis/ado-asana-sync/releases/latest)
[![PyPI - Version](https://img.shields.io/pypi/v/ado-asana-sync)](https://pypi.org/project/ado-asana-sync/)

[![Open in Visual Studio Code](https://img.shields.io/static/v1?logo=visualstudiocode&label=&message=Open%20in%20Visual%20Studio%20Code&labelColor=2c2c32&color=007acc&logoColor=007acc)](https://open.vscode.dev/danstis/ado-asana-sync)

This project aims to synchronize work items and pull requests between Azure DevOps (ADO) and Asana. It's currently in development and not ready for use. Breaking changes will occur as needed.

## Setup and Configuration

This guide covers everything you need to configure and run the sync tool, either locally for development or via Docker.

### Prerequisites

- **Python** (if running locally): Install [uv](https://docs.astral.sh/uv/) to manage dependencies and run the application.
- **Docker** (if running via containers): Install Docker and Docker Compose.
- **Azure DevOps (ADO) PAT**: A Personal Access Token with read access to Work Items, and Code (Read) access (which is required to sync pull requests).
- **Asana PAT**: A Personal Access Token with access to the target workspace and projects.

### Configuration

The application requires environment variables and a project mapping file.

#### 1. Environment Variables

Create a `.env` file in the root directory. You can copy the example file to get started:

```bash
cp .env.example .env
```

**Required Variables:**

- `ADO_PAT`: Your Personal Access Token for Azure DevOps.
- `ADO_URL`: The full URL of your Azure DevOps instance (e.g., `https://dev.azure.com/your-org`).
- `ASANA_TOKEN`: Your Personal Access Token for Asana.
- `ASANA_WORKSPACE_NAME`: The exact name of your Asana workspace.

**Optional Variables:**

- `CLOSED_STATES`: Comma-separated ADO states considered closed (default: `Closed,Removed,Done`).
- `THREAD_COUNT`: Number of projects to sync in parallel (default: `8`).
- `SLEEP_TIME`: Seconds to sleep between sync runs (default: `300`).
- `RUN_ONCE`: Run a single sync cycle and exit with a normal process status (default: `false`).
- `DRY_RUN`: Compute and log planned create/update/close actions without writing to Asana or the local sync database. The log summary includes separate create/update/close counts and ADO/PR IDs for both work items and PR reviewer tasks. Because no local mappings are persisted, repeated dry runs re-evaluate the same items from scratch (default: `false`).
- `SYNC_THRESHOLD`: Days to continue syncing closed tasks before unmapping (default: `30`).
- `SYNCED_TAG_NAME`: Asana tag appended to all synced items (default: `synced`).
- `LOGLEVEL`: Console log level (default: `INFO`).
- `GROUP_REVIEWER_STRATEGY`: How to handle ADO group/container reviewers (e.g. `[Project]\Contributor`). Options: `ignore` (default, skips them), `default_user` (assigns tasks to `GROUP_REVIEWER_DEFAULT_USER`), `unassigned_task` (creates an unassigned task with the group name).
- `GROUP_REVIEWER_DEFAULT_USER`: Asana user email, GID, or display name to assign group reviewer tasks to when `GROUP_REVIEWER_STRATEGY=default_user`.
- `OTEL_TRACES_SAMPLER_ARG`: Trace sampling percentage for Application Insights (e.g. `0.05` = 5%, `1.0` = 100%; default: `0.05`).
- `APPINSIGHTS_LOGLEVEL`: Minimum log level forwarded to Application Insights telemetry (default: `WARNING`).
- `APPINSIGHTS_SAMPLE_DEBUG` / `APPINSIGHTS_SAMPLE_INFO`: Sampling rate for DEBUG/INFO logs sent to Application Insights (default: `0.05`).
- `APPINSIGHTS_SAMPLE_WARNING` / `APPINSIGHTS_SAMPLE_ERROR` / `APPINSIGHTS_SAMPLE_CRITICAL`: Sampling rate for WARNING/ERROR/CRITICAL logs (default: `1.0`). These default to 100% to preserve incident visibility.

#### 2. Project Mapping

The application needs to know which ADO teams map to which Asana projects. Create a `projects.json` file in the `data/` directory:

```bash
cp data/projects.json.example data/projects.json
```

**Mapping Structure:**

```json
[
  {
    "adoProjectName": "your-ado-project",
    "adoTeamName": "Backend Team",
    "asanaProjectName": "your-asana-project-backend"
  }
]
```

- `adoProjectName`: The name of your Azure DevOps project.
- `adoTeamName`: The specific team within the ADO project whose backlog you want to sync.
- `asanaProjectName`: The corresponding Asana project name.

#### 3. Persistence (Data Directory)

The application stores its sync state in a SQLite database at `data/appdata.db`. This file tracks which ADO items have been synced to Asana so that subsequent runs perform incremental updates rather than recreating everything from scratch.

**Important:** Ensure the `data/` directory is persisted across restarts (e.g. via a Docker volume or bind mount). Without this, the sync database is lost and all Asana tasks will be recreated on the next run.

### Running the Application

You can run the sync tool either locally using `uv` or via Docker.

#### Option A: Running Locally (Development)

1. **Install dependencies:**
   ```bash
   uv sync
   ```
1. **Run the application:**
   ```bash
   uv run python -m ado_asana_sync.sync
   ```
   Alternatively, use the installed script entry point defined in `pyproject.toml`:
   ```bash
   uv run ado-asana-sync
   ```
1. **Run a single dry-run or one-shot sync with inline variables:**
   ```bash
   DRY_RUN=true RUN_ONCE=true uv run python -m ado_asana_sync.sync
   ```

In dry-run mode, expect log-only output such as create/update/close summaries. No Asana writes are sent, and no new entries are saved to `data/appdata.db`.

#### Option B: Running via Docker

The repository includes a `compose.yml` file for easy deployment.

1. **Build and start the container:**
   ```bash
   docker compose up --build
   ```

To run in the background, append `-d` to the command. The container will automatically pick up your `.env` file and mount the `data/projects.json` configuration.

### Verifying the Setup

Once running, the application will:

1. Connect to Azure DevOps and Asana to validate credentials.
1. Read the `data/projects.json` mapping.
1. Begin synchronizing active work items and pull requests based on the mapping.
1. Output logs indicating the sync progress.

You can verify the first sync by checking your mapped Asana project for newly created tasks with the configured synced tag.

## Features

### Work Item Synchronization

- Synchronizes Azure DevOps work items (User Stories, Bugs, Tasks, etc.) to Asana tasks
- Maintains bidirectional sync for updates, assignments, and status changes
- Automatic user matching between ADO and Asana based on email addresses
- Configurable closed states mapping

### Pull Request Synchronization

- Synchronizes active Pull Requests from Azure DevOps to Asana
- Creates separate reviewer tasks for each assigned reviewer
- Task titles follow the format: "Pull Request 5: Update readme (Reviewer Name)"
- Automatic status management:
  - Approved reviews (approve/approve with suggestions) → Close Asana task
  - Other review states (waiting for author, reject, no vote) → Keep task open
  - PR completion/abandonment → Close all reviewer tasks
  - Reviewer removal → Close reviewer's task
- Handles reviewer additions, removals, and approval resets
- Syncs PR title changes to Asana task titles

#### Pull Request Selection Logic

The system follows this logic to determine which PRs to sync:

1. **Repository Discovery**: For each configured ADO project, discover all Git repositories
1. **Active PR Filtering**: Query only PRs with `status="active"` (excludes completed/abandoned PRs)
1. **Reviewer Requirements**: Only sync PRs that have at least one assigned reviewer
1. **User Matching**: Only create tasks for reviewers who have matching Asana accounts (by email)
1. **Deduplication**: Prevent duplicate reviewer processing by unique email identifier
1. **Cleanup Processing**: Additionally process previously synced PRs that may now be closed/completed

**Exclusion Criteria:**

- PRs without reviewers are skipped (logs: "No reviewers found for PR X")
- Reviewers not found in Asana are skipped (logs: "PR X: reviewer Y not found in Asana")
- Repositories/projects without Git API access are skipped gracefully

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for a detailed history of changes and new features.

## Development

### Commit message style

This repo uses [Conventional Commits](https://www.conventionalcommits.org/) to ensure the build numbering is generated correctly

### End-to-End Tests

The project includes a comprehensive end-to-end (E2E) test suite under `tests/e2e/` that validates the complete sync workflow using mocked API endpoints and a real temporary SQLite database. These tests run automatically as part of the standard test suite.

**Running E2E tests:**

```bash
uv run pytest tests/e2e/ -v
```

**What is tested:**

| Scenario          | Description                                                 |
| ----------------- | ----------------------------------------------------------- |
| New work item     | ADO item not in Asana → task created                        |
| Work item update  | ADO item changed → Asana task updated                       |
| Work item close   | ADO item removed from backlog → Asana task completed        |
| Work item reopen  | Closed ADO item returns to backlog → Asana task uncompleted |
| Subtask hierarchy | Parent-child ADO relations → Asana subtask hierarchy        |
| Preexisting match | ADO item matches existing Asana task by name → no duplicate |
| PR open           | New PR with reviewer → reviewer task created                |
| PR close          | PR completed/abandoned → reviewer task completed            |
| PR reopen         | Reactivated PR → reviewer task uncompleted                  |
| PR status update  | Reviewer vote changed → Asana task updated                  |

These tests are non-destructive: they use isolated temporary directories and mocked external APIs, so they never impact real databases or Asana/ADO workspaces.

### Manual testing

To test the application manually, you can use the following steps:

#### Work Item Testing

1. Create new ADO work item and ensure it is synced to Asana.
1. Rename Asana task and ensure it is reverted back to the ADO name.
1. Rename ADO task and ensure it is synced to Asana.
1. Remove Synced tag from item in Asana and ensure it is replaced.
1. Delete synced tag from Asana workspace and from appdata.json file and ensure it is re-created and assigned to all synced tasks.
1. Mark Asana task as complete and ensure it is re-opened.
1. Mark ADO task as complete and ensure it is marked as complete in Asana.
1. Re-open ADO task and ensure it is re-opened in Asana.

#### Pull Request Testing

1. Create new Pull Request in ADO with reviewers and ensure reviewer tasks are created in Asana.
1. Change the PR title in ADO and ensure the title updates in Asana tasks on next sync.
1. Add a reviewer to the PR and ensure a new task is created for them.
1. Remove a reviewer from the PR and ensure their task is closed.
1. Remove all reviewers from the PR and ensure all tasks are closed.
1. Approve the PR as a reviewer and ensure the reviewer's task is closed.
1. Approve with suggestions and ensure the reviewer's task is closed.
1. Reject or request changes and ensure the reviewer's task remains open.
1. Reset approval and ensure the reviewer's task is reopened.
1. Complete/abandon the PR and ensure all reviewer tasks are closed.

### Reference

#### ADO

- [azure-devops PyPi](https://pypi.org/project/azure-devops/)
- [azure-devops GitHub](https://github.com/microsoft/azure-devops-python-api)
- [azure-devops API reference](https://learn.microsoft.com/en-us/rest/api/azure/devops/?view=azure-devops-rest-7.1&viewFallbackFrom=azure-devops-rest-5.1)
- [azure-devops samples](https://github.com/microsoft/azure-devops-python-samples/blob/main/src/samples/work_item_tracking.py)

#### Asana

- [Asana PyPi](https://pypi.org/project/asana/)
- [Asana GitHub](https://github.com/asana/python-asana)
- [Asana API Reference](https://developers.asana.com/docs/rich-text)
