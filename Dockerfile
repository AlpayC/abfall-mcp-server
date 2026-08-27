# syntax=docker/dockerfile:1.7

FROM node:22-alpine AS web-build

WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM ghcr.io/astral-sh/uv:0.8.22 AS uv
FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    ABFALL_MCP_CACHE_DIR=/var/cache/abfall-mcp-server \
    ABFALL_MCP_WEB_DIR=/app/web \
    PORT=8000 \
    PATH="/app/.venv/bin:$PATH"

COPY --from=uv /uv /uvx /bin/

WORKDIR /app

# Dieser Layer bleibt bei reinen Quellcodeaenderungen im Build-Cache.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
COPY data ./data
COPY --from=web-build /web/out ./web
COPY LICENSE NOTICE ./
COPY vendor/hacs_waste_collection_schedule/LICENSE \
    ./vendor/hacs_waste_collection_schedule/LICENSE
COPY vendor/hacs_waste_collection_schedule/custom_components/waste_collection_schedule/waste_collection_schedule \
    ./vendor/hacs_waste_collection_schedule/custom_components/waste_collection_schedule/waste_collection_schedule

RUN uv sync --frozen --no-dev \
    && groupadd --system abfall-mcp-server \
    && useradd --system --gid abfall-mcp-server --create-home abfall-mcp-server \
    && mkdir -p "$ABFALL_MCP_CACHE_DIR" \
    && chown -R abfall-mcp-server:abfall-mcp-server "$ABFALL_MCP_CACHE_DIR"

USER abfall-mcp-server

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; port = os.environ.get('PORT', '8000'); urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=3)"]

ENTRYPOINT ["abfall-mcp-server"]
CMD ["--http", "--host", "0.0.0.0", "--log-level", "INFO"]
