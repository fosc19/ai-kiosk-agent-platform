FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for MediaPipe and healthcheck
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy application code first (needed for pip install)
COPY *.py .
COPY pyproject.toml .

# Install Python dependencies
RUN pip install --no-cache-dir \
    "fastapi>=0.108.0" \
    "uvicorn[standard]>=0.25.0" \
    "pydantic>=2.5.0" \
    "pydantic-settings>=2.1.0" \
    "structlog>=24.1.0" \
    "mediapipe>=0.10.9" \
    "pillow>=10.0.0" \
    "numpy>=1.26.0"

EXPOSE 9003

CMD ["python", "main.py"]
