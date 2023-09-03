# ado-asana-sync

[![Test and Lint](https://github.com/danstis/ado-asana-sync/actions/workflows/build.yml/badge.svg)](https://github.com/danstis/ado-asana-sync/actions/workflows/build.yml)
[![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=danstis_ado-asana-sync&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=danstis_ado-asana-sync)
[![Coverage](https://sonarcloud.io/api/project_badges/measure?project=danstis_ado-asana-sync&metric=coverage)](https://sonarcloud.io/summary/new_code?id=danstis_ado-asana-sync)

[![Release](https://img.shields.io/github/release/danstis/ado-asana-sync.svg?style=flat-square)](https://github.com/danstis/ado-asana-sync/releases/latest)
[![PyPI - Version](https://img.shields.io/pypi/v/ado-asana-sync)](https://pypi.org/project/ado-asana-sync/)

[![Open in Visual Studio Code](https://img.shields.io/static/v1?logo=visualstudiocode&label=&message=Open%20in%20Visual%20Studio%20Code&labelColor=2c2c32&color=007acc&logoColor=007acc)](https://open.vscode.dev/danstis/ado-asana-sync)

This project aims to synchronize work items between Azure DevOps (ADO) and Asana. It's currently in development and not ready for use. Breaking changes will occur as needed.

## How to use

* Get the latest container image from the [Github Container Registry](https://github.com/danstis/ado-asana-sync/pkgs/container/ado-asana-sync).
* Configure the environment variables with the relevant values:
  * `ADO_PAT` - Your Personal Access Token for ADO to accesst the work items.
  * `ADO_URL` - The full URL of your Azure DevOps instance.
  * `ASANA_TOKEN` - Your Personal Access Token for Asana to access the work items.
  * `ASANA_WORKSPACE_NAME` - Name of the Asana workspace to sync with.
* Run the container with the configured environment variables.
* The application will start syncing work items between ADO and Asana based on the configured settings.

## Development

### Commit message style

This repo uses [Conventional Commits](https://www.conventionalcommits.org/) to ensure the build numbering is generated correctly

### Reference

#### ADO

* [azure-devops PyPi](https://pypi.org/project/azure-devops/)
* [azure-devops GitHub](https://github.com/microsoft/azure-devops-python-api)
* [azure-devops API reference](https://learn.microsoft.com/en-us/rest/api/azure/devops/?view=azure-devops-rest-7.1&viewFallbackFrom=azure-devops-rest-5.1)
* [azure-devops samples](https://github.com/microsoft/azure-devops-python-samples/blob/main/src/samples/work_item_tracking.py)

#### Asana

* [Asana PyPi](https://pypi.org/project/asana/)
* [Asana GitHub](https://github.com/asana/python-asana)
* [Asana API Reference](https://developers.asana.com/docs/rich-text)
