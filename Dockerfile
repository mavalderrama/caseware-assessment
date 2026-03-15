FROM python:3.11-slim

# System deps: libpq for psycopg, curl for healthchecks
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install uv for fast dependency resolution
RUN pip install --no-cache-dir uv

# Copy dependency files first for layer caching
COPY backend/pyproject.toml backend/uv.lock* ./

# Install production dependencies (no dev group)
RUN uv pip install --system --no-cache -r pyproject.toml

# Copy application source
COPY backend/ .

EXPOSE 8000
