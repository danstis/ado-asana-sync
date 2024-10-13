FROM python:3.13-slim AS base

ENV PYTHONFAULTHANDLER=1 \
    PYTHONHASHSEED=random \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Build image
FROM base AS builder

ENV PIP_DEFAULT_TIMEOUT=100 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    POETRY_VERSION=1.6.1

RUN pip install "poetry==${POETRY_VERSION}"

COPY pyproject.toml poetry.lock /app/
RUN poetry config virtualenvs.create false \
    && poetry install --no-root --no-interaction --no-ansi

COPY ado_asana_sync/ /app/ado_asana_sync/
COPY tests/ /app/tests/
COPY README.md LICENSE /app/

ARG VERSION=0.0.1
RUN poetry version ${VERSION} \
    && poetry build

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
