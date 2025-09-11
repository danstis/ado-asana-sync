#!/bin/bash

# Install uv manually since we can't use the devcontainer-extra feature
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"

# Install other tools
pipx install coverage

# Sync dependencies
uv sync --dev
