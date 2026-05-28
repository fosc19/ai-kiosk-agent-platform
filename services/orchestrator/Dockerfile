FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .

RUN pip install --no-cache-dir \
    "fastapi>=0.108.0" \
    "uvicorn[standard]>=0.25.0" \
    "websockets>=12.0" \
    "pydantic>=2.5.0" \
    "pydantic-settings>=2.1.0" \
    "redis>=5.0.0" \
    "httpx>=0.25.2" \
    "structlog>=24.1.0" \
    "anthropic>=0.40.0" \
    "google-generativeai>=0.8.0" \
    "openai>=1.50.0"

COPY . .

EXPOSE 8765

HEALTHCHECK --interval=10s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8765/healthz || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8765"]
