import base64
import io
import os
from dataclasses import dataclass
from pathlib import Path

import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
from PIL import Image
import numpy as np

from config import settings


@dataclass
class DetectionResult:
    present: bool
    look_direction: float  # -1 (left), 0 (center), 1 (right)
    confidence: float


# Download model if not exists
MODEL_PATH = Path(__file__).parent / "blaze_face_short_range.tflite"


def _download_model():
    """Download the face detection model if not present."""
    if MODEL_PATH.exists():
        return

    import urllib.request
    url = "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite"
    print(f"[Vision] Downloading face detection model...")
    urllib.request.urlretrieve(url, MODEL_PATH)
    print(f"[Vision] Model downloaded to {MODEL_PATH}")


class FaceDetector:
    def __init__(self):
        _download_model()

        # Create face detector with new Tasks API
        base_options = python.BaseOptions(model_asset_path=str(MODEL_PATH))
        options = vision.FaceDetectorOptions(
            base_options=base_options,
            min_detection_confidence=settings.min_detection_confidence
        )
        self.detector = vision.FaceDetector.create_from_options(options)

    def detect(self, image_base64: str) -> DetectionResult:
        """Detect face in base64 JPEG image and return presence info."""
        try:
            # Decode base64 to image
            image_data = base64.b64decode(image_base64)
            image = Image.open(io.BytesIO(image_data))

            # Convert to RGB if needed
            if image.mode != "RGB":
                image = image.convert("RGB")

            # Convert to numpy array and create MediaPipe Image
            image_np = np.array(image)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=image_np)

            # Process with MediaPipe
            results = self.detector.detect(mp_image)

            if not results.detections:
                print("[Vision] No face detected")
                return DetectionResult(present=False, look_direction=0, confidence=0)

            # Get first (most confident) detection
            detection = results.detections[0]
            confidence = detection.categories[0].score
            print(f"[Vision] Face detected with confidence={confidence:.2f}")

            # Calculate look direction based on face bounding box center X
            bbox = detection.bounding_box
            image_width = image_np.shape[1]
            face_center_x = (bbox.origin_x + bbox.width / 2) / image_width

            # Map 0-1 range to -1 to 1 (left to right)
            # 0.5 = center, <0.33 = left, >0.66 = right
            if face_center_x < 0.33:
                look_direction = -1.0
            elif face_center_x > 0.66:
                look_direction = 1.0
            else:
                # Linear interpolation for center region
                look_direction = (face_center_x - 0.5) * 6  # Scale to roughly -1 to 1
                look_direction = max(-1.0, min(1.0, look_direction))

            return DetectionResult(
                present=True,
                look_direction=round(look_direction, 2),
                confidence=round(confidence, 2)
            )

        except Exception as e:
            # Log error but don't crash - return no detection
            print(f"Detection error: {e}")
            return DetectionResult(present=False, look_direction=0, confidence=0)

    def close(self):
        pass  # New API doesn't require explicit close


# Singleton instance
_detector: FaceDetector | None = None


def get_detector() -> FaceDetector:
    global _detector
    if _detector is None:
        _detector = FaceDetector()
    return _detector
