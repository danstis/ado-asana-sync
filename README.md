# ado-asana-sync

[![Test and Lint](https://github.com/danstis/ado-asana-sync/actions/workflows/build.yml/badge.svg)](https://github.com/danstis/ado-asana-sync/actions/workflows/build.yml)
[![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=danstis_ado-asana-sync&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=danstis_ado-asana-sync)
[![Coverage](https://sonarcloud.io/api/project_badges/measure?project=danstis_ado-asana-sync&metric=coverage)](https://sonarcloud.io/summary/new_code?id=danstis_ado-asana-sync)

[![Release](https://img.shields.io/github/release/danstis/ado-asana-sync.svg?style=flat-square)](https://github.com/danstis/ado-asana-sync/releases/latest)
[![PyPI - Version](https://img.shields.io/pypi/v/ado-asana-sync)](https://pypi.org/project/ado-asana-sync/)

[![Open in Visual Studio Code](https://img.shields.io/static/v1?logo=visualstudiocode&label=&message=Open%20in%20Visual%20Studio%20Code&labelColor=2c2c32&color=007acc&logoColor=007acc)](https://open.vscode.dev/danstis/ado-asana-sync)

This project aims to synchronize work items and pull requests between Azure DevOps (ADO) and Asana. It's currently in development and not ready for use. Breaking changes will occur as needed.

## How to use

- Get the latest container image from the [Github Container Registry](https://github.com/danstis/ado-asana-sync/pkgs/container/ado-asana-sync).
- Configure the environment variables with the relevant values:
  - `ADO_PAT` - Your Personal Access Token for ADO to accesst the work items.
  - `ADO_URL` - The full URL of your Azure DevOps instance.
  - `ASANA_TOKEN` - Your Personal Access Token for Asana to access the work items.
  - `ASANA_WORKSPACE_NAME` - Name of the Asana workspace to sync with.
  - `CLOSED_STATES` - Comma separated list of states that will be considered closed.
  - `THREAD_COUNT` - Number of projects to sync in parallel. Must be a positive integer.
  - `SYNC_THRESHOLD` - Number of days to continue syncing closed tasks before removing their mappings (default: 30). Must be a non-negative integer.
  - `SLEEP_TIME` - Duration in seconds to sleep between sync runs. Must be a positive integer.
  - `SYNCED_TAG_NAME` - Name of the tag in Asana to append to all synced items. Must be a valid Asana tag name.
- Run the container with the configured environment variables.
- The application will start syncing work items and pull requests between ADO and Asana based on the configured settings.

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
