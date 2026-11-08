# syntax=docker/dockerfile:1@sha256:4edf897a3ffa55b89f906fc8cc78afdb3f1834cc9c7083565e611a8a7d5fe99e
# 고사리잇 앱 이미지: Node build → Python runtime (SRS 실행환경 v1.2)
# 빌드 컨텍스트는 레포 루트. .local/비밀/개인 자료는 .dockerignore로 제외한다.

FROM node:26-slim@sha256:5adad64f9a1fca2d51972caa65983634c8a774eb300d72b20f7f2a0f60368072 AS web-build
WORKDIR /build
COPY package.json bun.lock ./
COPY apps/web/package.json apps/web/
RUN npm install --global bun@1.4.2 && bun install --frozen-lockfile
COPY apps/web apps/web
COPY biome.json ./
WORKDIR /build/apps/web
RUN bun run build

FROM python:3.14-slim@sha256:9aaa474097d094040649f2162a627c0049b408f52138d980916788d80f04802f AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:latest@sha256:96f40d3904aad8d0bd010539001d36c8e2188b981e1334471a90c4a1d93bb490 /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./
COPY apps/api/pyproject.toml apps/api/README.md apps/api/
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-workspace
ARG EMBEDDING_REVISION=614241f622f53c4eeff9890bdc4f31cfecc418b3
ENV EMBEDDING_MODEL_PATH=/app/models/multilingual-e5-small \
    EMBEDDING_REVISION=${EMBEDDING_REVISION}
# 런타임은 읽기 전용·오프라인 모델 로딩이므로 고정 revision을 이미지에 포함한다.
RUN --mount=type=cache,target=/root/.cache/huggingface \
    .venv/bin/python -c "import os; from huggingface_hub import snapshot_download; snapshot_download(repo_id='intfloat/multilingual-e5-small', revision=os.environ['EMBEDDING_REVISION'], local_dir=os.environ['EMBEDDING_MODEL_PATH'], allow_patterns=['1_Pooling/config.json', 'README.md', 'config.json', 'model.safetensors', 'modules.json', 'sentence_bert_config.json', 'sentencepiece.bpe.model', 'special_tokens_map.json', 'tokenizer.json', 'tokenizer_config.json'])"
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
    HF_HUB_OFFLINE=1 \
    APP_PROFILE=center \
    EXTERNAL_REQUESTS_ENABLED=false
EXPOSE 8765
CMD ["python", "-m", "uvicorn", "gosari.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8765", "--loop", "asyncio", "--workers", "1", "--no-access-log"]
