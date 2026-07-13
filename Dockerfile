FROM oven/bun:1.3.14-slim@sha256:d56a2534ffd262e92c12fd3249d3924d296d97086da773f821d7d0477435ea04 AS web-builder

WORKDIR /app/web

COPY web/package.json web/bun.lock ./
RUN bun install --frozen-lockfile

COPY web/ ./
RUN bun run build


FROM python:3.13-slim-bookworm@sha256:fcbd8dfc2605ba7c2eca646846c5e892b2931e41f6227985154a596f26ab8ed7 AS python-builder

COPY --from=ghcr.io/astral-sh/uv:0.11.7@sha256:240fb85ab0f263ef12f492d8476aa3a2e4e1e333f7d67fbdd923d00a506a516a /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/
RUN uv sync --frozen --no-dev


FROM python:3.13-slim-bookworm@sha256:fcbd8dfc2605ba7c2eca646846c5e892b2931e41f6227985154a596f26ab8ed7 AS runtime

WORKDIR /app

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    DATABASE_URL="sqlite:////app/data/infinex.db" \
    ARTIFACT_DIR="/app/data/artifacts" \
    WORKER_DATA_DIR="/app/data/workers" \
    WEB_DIST_DIR="/app/web/dist"

RUN groupadd --gid 10001 infinex \
    && useradd \
        --uid 10001 \
        --gid infinex \
        --create-home \
        --home-dir /home/infinex \
        --shell /usr/sbin/nologin \
        infinex \
    && mkdir -p /app/data/artifacts /app/data/workers \
    && chown -R infinex:infinex /app /home/infinex

COPY --from=python-builder --chown=infinex:infinex /app/.venv ./.venv
COPY --from=python-builder --chown=infinex:infinex /app/src ./src
COPY --chown=infinex:infinex alembic.ini ./
COPY --chown=infinex:infinex migrations/ ./migrations/
COPY --from=web-builder --chown=infinex:infinex /app/web/dist ./web/dist

USER infinex

EXPOSE 8002

CMD ["infinex", "serve"]
