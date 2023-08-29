FROM python:3.10-slim AS base

ENV PYTHONFAULTHANDLER=1 \
    PYTHONHASHSEED=random \
    PYTHONUNBUFFERED=1

WORKDIR /app

FROM base AS builder

ENV PIP_DEFAULT_TIMEOUT=100 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    POETRY_VERSION=1.6.1

RUN pip install "poetry==${POETRY_VERSION}"

COPY pyproject.toml poetry.lock /app/
RUN poetry config virtualenvs.in-project true \
    && poetry install --no-root

COPY . .
ARG VERSION=0.0.1
RUN poetry version ${VERSION} \
    && poetry build
ENV VIRTUAL_ENV="/app/.venv"
ENV PATH="${VIRTUAL_ENV}/bin:${PATH}"
RUN pip install /app/dist/*.whl

FROM base AS final

ENV VIRTUAL_ENV="/app/.venv"
ENV PATH="${VIRTUAL_ENV}/bin:${PATH}" \
    ADO_PAT=${ADO_PAT} \
    ADO_URL=${ADO_URL} \
    ASANA_TOKEN=${ASANA_TOKEN}

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/dist /app/dist
CMD ["python", "-m", "ado_asana_sync.sync"]
