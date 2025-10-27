FROM python:3.14-slim AS base

ENV PYTHONFAULTHANDLER=1 \
    PYTHONHASHSEED=random \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Build image
FROM base AS builder

ENV PIP_DEFAULT_TIMEOUT=100 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

# Install build dependencies for compiling C extensions (cffi, cryptography, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    build-essential \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy project files needed for dependency resolution
COPY pyproject.toml uv.lock /app/
COPY README.md LICENSE /app/
COPY ado_asana_sync/ /app/ado_asana_sync/

# Install dependencies
RUN uv sync --frozen --no-dev

ARG VERSION=0.0.1
RUN sed -i "s/version = \"0.0.0-dev\"/version = \"${VERSION}\"/g" pyproject.toml \
    && uv build

# Final Image
FROM base AS final

RUN useradd -m syncuser

ENV ADO_PAT=${ADO_PAT} \
    ADO_URL=${ADO_URL} \
    ASANA_TOKEN=${ASANA_TOKEN} \
    ASANA_WORKSPACE_NAME=${ASANA_WORKSPACE_NAME} \
    PIP_DEFAULT_TIMEOUT=100 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

COPY --from=builder /app/dist /app/.tmp
RUN pip install /app/.tmp/*.whl \
    && rm -rf /app/.tmp
USER syncuser
CMD ["python", "-m", "ado_asana_sync.sync"]
