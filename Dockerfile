FROM python:3.12-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy project files and install dependencies
COPY . .
RUN uv sync --no-dev

# Create non-root user
RUN useradd -m -u 1000 atp && chown -R atp:atp /app
USER atp

# Default: run API
EXPOSE 8000
CMD ["uv", "run", "python", "main.py"]
