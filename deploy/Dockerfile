# syntax=docker/dockerfile:1
# 고사리잇 앱 이미지: Node build → Python runtime (SRS 실행환경 v1.2)
# 빌드 컨텍스트는 레포 루트. .local/비밀/개인 자료는 .dockerignore로 제외한다.

FROM node:26-slim AS web-build
WORKDIR /build
COPY package.json bun.lock ./
COPY apps/web/package.json apps/web/
RUN corepack enable && corepack prepare bun@1.4.2 --activate 2>/dev/null || npm install -g bun@1.4.2
RUN bun install --frozen-lockfile
COPY apps/web apps/web
COPY biome.json ./
RUN cd apps/web && bun run build

FROM python:3.14-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./
COPY apps/api/pyproject.toml apps/api/README.md apps/api/
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-workspace
COPY apps/api/src apps/api/src
COPY apps/api/alembic apps/api/alembic
COPY apps/api/alembic.ini apps/api/
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev
COPY fixtures /app/fixtures
COPY --from=web-build /build/apps/web/dist /app/web-dist
RUN groupadd -g 10001 gosari && useradd -u 10001 -g gosari -m gosari \
    && chown -R gosari:gosari /app
USER 10001:10001
ENV PATH="/app/.venv/bin:$PATH" \
    FIXTURES_DIR=/app/fixtures \
    APP_PROFILE=center \
    EXTERNAL_REQUESTS_ENABLED=false
EXPOSE 8765
CMD ["python", "-m", "uvicorn", "gosari.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8765", "--loop", "asyncio", "--workers", "1", "--no-access-log"]