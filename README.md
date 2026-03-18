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
- **Azure DevOps (ADO) PAT**: A Personal Access Token with read access to work items, pull requests, and source code.
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
- `SYNC_THRESHOLD`: Days to continue syncing closed tasks before unmapping (default: `30`).
- `SYNCED_TAG_NAME`: Asana tag appended to all synced items (default: `synced`).
- `LOGLEVEL`: Console log level (default: `INFO`).
- *See `.env.example` for additional Application Insights telemetry configurations.*

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
- `adoTeamName`: The specific team within the ADO project.
- `asanaProjectName`: The corresponding Asana project name.

### Running the Application

You can run the sync tool either locally using `uv` or via Docker.

#### Option A: Running Locally (Development)

1. **Install dependencies:**
   ```bash
   uv sync
   ```
2. **Run the application:**
   ```bash
   uv run python -m ado_asana_sync.sync
   ```

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
2. Read the `data/projects.json` mapping.
3. Begin synchronizing active work items and pull requests based on the mapping.
4. Output logs indicating the sync progress.

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
