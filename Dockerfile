# Stage 1: build exported Next.js frontend
# Use Node 20 for Next.js build compatibility (SWC musl binaries are most reliable here).
FROM node:20-alpine AS web-builder

WORKDIR /app/web

COPY web/package.json ./package.json
RUN npm install --no-audit --no-fund

COPY web/ ./

# Empty means "same origin" API calls from browser.
ARG NEXT_PUBLIC_API_URL=
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

RUN npm run build

# Stage 2: Python API + static frontend in one container
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# trader engine uses npx/uvx-backed MCP tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    nodejs \
    npm \
    curl \
    && rm -rf /var/lib/apt/lists/*
RUN npm install -g --no-audit --no-fund @modelcontextprotocol/server-brave-search mcp-memory-libsql

COPY api/requirements.txt /app/api/requirements.txt
RUN pip install --no-cache-dir -r /app/api/requirements.txt
RUN pip install --no-cache-dir uv

COPY pyproject.toml /app/pyproject.toml
COPY uv.lock /app/uv.lock
COPY api /app/api

# Exported Next.js app is served by FastAPI static mount.
COPY --from=web-builder /app/web/out /app/api/static

WORKDIR /app/api

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
