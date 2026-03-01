FROM python:3.12-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy everything and install in one step
COPY . .
RUN pip install --no-cache-dir -e .

# Create non-root user
RUN useradd -m -u 1000 atp && chown -R atp:atp /app
USER atp

# Default: run API
EXPOSE 8000
CMD ["python", "main.py"]
