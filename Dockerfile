# syntax=docker/dockerfile:1.7

FROM ghcr.io/astral-sh/uv:0.8.22 AS uv
FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    MCP_ABFALL_CACHE_DIR=/var/cache/mcp-abfall \
    PORT=8000 \
    PATH="/app/.venv/bin:$PATH"

COPY --from=uv /uv /uvx /bin/

WORKDIR /app

# Dieser Layer bleibt bei reinen Quellcodeaenderungen im Build-Cache.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
COPY data ./data
COPY LICENSE NOTICE ./
COPY vendor/hacs_waste_collection_schedule/LICENSE \
    ./vendor/hacs_waste_collection_schedule/LICENSE
COPY vendor/hacs_waste_collection_schedule/custom_components/waste_collection_schedule/waste_collection_schedule \
    ./vendor/hacs_waste_collection_schedule/custom_components/waste_collection_schedule/waste_collection_schedule

RUN uv sync --frozen --no-dev \
    && groupadd --system mcp-abfall \
    && useradd --system --gid mcp-abfall --create-home mcp-abfall \
    && mkdir -p "$MCP_ABFALL_CACHE_DIR" \
    && chown -R mcp-abfall:mcp-abfall "$MCP_ABFALL_CACHE_DIR"

USER mcp-abfall

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; port = os.environ.get('PORT', '8000'); urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=3)"]

ENTRYPOINT ["mcp-abfall"]
CMD ["--http", "--host", "0.0.0.0", "--log-level", "INFO"]
