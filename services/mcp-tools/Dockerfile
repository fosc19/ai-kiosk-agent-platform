FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY pyproject.toml .

# Install Python dependencies
RUN pip install --no-cache-dir \
    fastapi>=0.108.0 \
    uvicorn[standard]>=0.25.0 \
    sqlalchemy>=2.0.0 \
    "psycopg[binary]>=3.1.0" \
    alembic>=1.13.0 \
    pydantic>=2.5.0 \
    pydantic-settings>=2.1.0 \
    rapidfuzz>=3.0.0 \
    structlog>=24.1.0

# Copy source code
COPY src/ src/
COPY alembic/ alembic/
COPY alembic.ini .
COPY entrypoint.sh .

# Make entrypoint executable
RUN chmod +x entrypoint.sh

# Set Python path
ENV PYTHONPATH=/app/src

# Expose port
EXPOSE 9002

# Health check
HEALTHCHECK --interval=10s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:9002/healthz || exit 1

# Use entrypoint script
ENTRYPOINT ["./entrypoint.sh"]
