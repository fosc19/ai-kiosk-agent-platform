import logging
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from config import settings
from detector import get_detector, DetectionResult


# Configure structured logging
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(
        getattr(logging, settings.log_level)
    ),
    logger_factory=structlog.PrintLoggerFactory(),
)

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize detector
    log.info("vision_service_starting", port=settings.port)
    detector = get_detector()
    log.info("mediapipe_initialized")
    yield
    # Shutdown: cleanup
    detector.close()
    log.info("vision_service_stopped")


app = FastAPI(
    title="Vision Service",
    description="Face detection service using MediaPipe",
    version="0.1.0",
    lifespan=lifespan,
)


class DetectRequest(BaseModel):
    image_data: str  # JPEG base64


class DetectResponse(BaseModel):
    present: bool
    look_direction: float
    confidence: float


@app.get("/healthz")
async def health_check():
    return {
        "status": "healthy",
        "service": "vision",
        "version": "0.1.0",
    }


@app.post("/detect", response_model=DetectResponse)
async def detect_face(request: DetectRequest):
    """Detect face in image and return presence information."""
    if not request.image_data:
        raise HTTPException(status_code=400, detail="image_data is required")

    detector = get_detector()
    result: DetectionResult = detector.detect(request.image_data)

    log.debug(
        "detection_complete",
        present=result.present,
        direction=result.look_direction,
        confidence=result.confidence,
    )

    return DetectResponse(
        present=result.present,
        look_direction=result.look_direction,
        confidence=result.confidence,
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )
