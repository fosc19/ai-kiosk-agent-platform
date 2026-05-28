# Speech Service - Local ASR/TTS (no API keys needed)
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies (heavy - cached in layer)
RUN pip install --no-cache-dir \
    "fastapi>=0.108.0" \
    "uvicorn[standard]>=0.25.0" \
    "pydantic>=2.5.0" \
    "pydantic-settings>=2.1.0" \
    "structlog>=24.1.0" \
    "torch>=2.0.0" \
    "torchaudio>=2.0.0" \
    "numpy>=1.24.0" \
    "soundfile>=0.12.0" \
    "faster-whisper>=1.0.0" \
    "piper-tts>=1.2.0" \
    "pydub>=0.25.0"

# Download Piper Spanish voice model (Laura = female voice)
RUN mkdir -p /models && \
    curl -L -o /models/es_MX-laura-high.onnx \
    "https://huggingface.co/HirCoir/Piper-TTS-Laura/resolve/main/es_MX-laura-high.onnx" && \
    curl -L -o /models/es_MX-laura-high.onnx.json \
    "https://huggingface.co/HirCoir/Piper-TTS-Laura/resolve/main/es_MX-laura-high.onnx.json"

# Pre-download Whisper model (cached in image)
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu')"

# Copy application code
COPY . .

# Environment defaults for local mode
ENV SPEECH_ASR_MODE=local \
    SPEECH_TTS_MODE=local \
    SPEECH_WHISPER_MODEL_SIZE=small \
    SPEECH_PIPER_MODEL_PATH=/models/es_MX-laura-high.onnx \
    SPEECH_TTS_CACHE_ENABLED=true \
    SPEECH_TTS_CACHE_PRELOAD=true

EXPOSE 9001

HEALTHCHECK --interval=10s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:9001/healthz || exit 1

CMD ["python", "main.py"]
