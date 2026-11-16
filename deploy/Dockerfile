# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src

RUN groupadd --gid 10001 idml && useradd --uid 10001 --gid idml --create-home idml

WORKDIR /app
COPY pyproject.toml requirements.lock ./
COPY src ./src
COPY config ./config
COPY prompts ./prompts
COPY schemas ./schemas
COPY openclaw ./openclaw
COPY profiles ./profiles
COPY vendor ./vendor
COPY alembic.ini ./
COPY migrations ./migrations
RUN python -m pip install --require-hashes -r requirements.lock

USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "idml_foundation.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
