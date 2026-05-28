"""Tests for Vision face detector.

F7: Unit tests for face detection and look direction tracking.
"""

import base64
import io
from unittest.mock import MagicMock, patch
import numpy as np

import pytest

# Add services path for imports
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "services" / "vision"))


class TestDetectionResult:
    """Test DetectionResult dataclass."""

    def test_create_detection_result(self):
        """Test creating a DetectionResult."""
        from detector import DetectionResult

        result = DetectionResult(
            present=True,
            look_direction=0.5,
            confidence=0.95,
        )

        assert result.present is True
        assert result.look_direction == 0.5
        assert result.confidence == 0.95

    def test_no_detection_result(self):
        """Test creating no-detection result."""
        from detector import DetectionResult

        result = DetectionResult(
            present=False,
            look_direction=0,
            confidence=0,
        )

        assert result.present is False
        assert result.look_direction == 0


class TestFaceDetector:
    """Test FaceDetector class."""

    def _create_mock_detection(self, confidence=0.95, origin_x=256, width=128):
        """Create a mock MediaPipe Tasks API detection.

        Args:
            confidence: Detection confidence score
            origin_x: X coordinate of bounding box origin (pixels)
            width: Width of bounding box (pixels)
        """
        mock_category = MagicMock()
        mock_category.score = confidence

        mock_bbox = MagicMock()
        mock_bbox.origin_x = origin_x
        mock_bbox.width = width

        mock_detection = MagicMock()
        mock_detection.categories = [mock_category]
        mock_detection.bounding_box = mock_bbox

        return mock_detection

    def _create_mock_detector(self, detections=None):
        """Create a mock MediaPipe Tasks face detector."""
        mock_results = MagicMock()
        mock_results.detections = detections

        mock_detector = MagicMock()
        mock_detector.detect.return_value = mock_results

        return mock_detector

    @pytest.fixture
    def mock_mediapipe(self):
        """Create mock MediaPipe face detection (Tasks API)."""
        detection = self._create_mock_detection(
            confidence=0.95,
            origin_x=256,   # ~0.4 * 640, center at ~0.5
            width=128       # ~0.2 * 640
        )
        return self._create_mock_detector([detection])

    def create_test_image_base64(self, width=640, height=480) -> str:
        """Create a test image as base64."""
        from PIL import Image

        # Create a simple test image
        img = Image.new("RGB", (width, height), color="gray")

        # Convert to JPEG bytes
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG")
        buffer.seek(0)

        # Encode to base64
        return base64.b64encode(buffer.read()).decode("utf-8")

    def test_detect_face_present(self, mock_mediapipe):
        """Test detecting a face that is present."""
        from detector import FaceDetector, DetectionResult

        detector = FaceDetector.__new__(FaceDetector)
        detector.detector = mock_mediapipe

        image_b64 = self.create_test_image_base64()
        result = detector.detect(image_b64)

        assert result.present is True
        assert result.confidence == 0.95

    def test_detect_no_face(self):
        """Test when no face is detected."""
        from detector import FaceDetector

        mock_detector = self._create_mock_detector(detections=[])

        detector = FaceDetector.__new__(FaceDetector)
        detector.detector = mock_detector

        image_b64 = self.create_test_image_base64()
        result = detector.detect(image_b64)

        assert result.present is False
        assert result.confidence == 0

    def test_look_direction_left(self):
        """Test look direction when face is on the left."""
        from detector import FaceDetector

        # Face center at ~0.15 (64 + 64/2 = 96 / 640 = 0.15)
        detection = self._create_mock_detection(
            confidence=0.9,
            origin_x=64,   # ~0.1 * 640
            width=64       # ~0.1 * 640, center at 0.15
        )
        mock_detector = self._create_mock_detector([detection])

        detector = FaceDetector.__new__(FaceDetector)
        detector.detector = mock_detector

        image_b64 = self.create_test_image_base64()
        result = detector.detect(image_b64)

        assert result.present is True
        assert result.look_direction == -1.0

    def test_look_direction_right(self):
        """Test look direction when face is on the right."""
        from detector import FaceDetector

        # Face center at ~0.8 (448 + 128/2 = 512 / 640 = 0.8)
        detection = self._create_mock_detection(
            confidence=0.9,
            origin_x=448,  # ~0.7 * 640
            width=128      # ~0.2 * 640, center at 0.8
        )
        mock_detector = self._create_mock_detector([detection])

        detector = FaceDetector.__new__(FaceDetector)
        detector.detector = mock_detector

        image_b64 = self.create_test_image_base64()
        result = detector.detect(image_b64)

        assert result.present is True
        assert result.look_direction == 1.0

    def test_look_direction_center(self):
        """Test look direction when face is centered."""
        from detector import FaceDetector

        # Face center at ~0.5 (256 + 128/2 = 320 / 640 = 0.5)
        detection = self._create_mock_detection(
            confidence=0.9,
            origin_x=256,  # ~0.4 * 640
            width=128      # ~0.2 * 640, center at 0.5
        )
        mock_detector = self._create_mock_detector([detection])

        detector = FaceDetector.__new__(FaceDetector)
        detector.detector = mock_detector

        image_b64 = self.create_test_image_base64()
        result = detector.detect(image_b64)

        assert result.present is True
        assert -0.5 <= result.look_direction <= 0.5

    def test_invalid_base64_image(self, mock_mediapipe):
        """Test handling of invalid base64 image."""
        from detector import FaceDetector

        detector = FaceDetector.__new__(FaceDetector)
        detector.detector = mock_mediapipe

        # Invalid base64
        result = detector.detect("not_valid_base64!!!")

        # Should return no detection on error
        assert result.present is False

    def test_multiple_faces_uses_first(self):
        """Test that with multiple faces, the first is used."""
        from detector import FaceDetector

        detection1 = self._create_mock_detection(confidence=0.95, origin_x=256, width=128)
        detection2 = self._create_mock_detection(confidence=0.8, origin_x=64, width=64)
        mock_detector = self._create_mock_detector([detection1, detection2])

        detector = FaceDetector.__new__(FaceDetector)
        detector.detector = mock_detector

        image_b64 = self.create_test_image_base64()
        result = detector.detect(image_b64)

        # Should use first detection (0.95 confidence)
        assert result.confidence == 0.95

    def test_detector_close(self, mock_mediapipe):
        """Test that detector can be closed without error."""
        from detector import FaceDetector

        detector = FaceDetector.__new__(FaceDetector)
        detector.detector = mock_mediapipe

        # close() is a no-op in new API, just verify it doesn't crash
        detector.close()


class TestGetDetector:
    """Test get_detector singleton function."""

    def test_get_detector_returns_instance(self):
        """Test that get_detector returns a FaceDetector instance."""
        with patch("detector.mp") as mock_mp:
            mock_mp.solutions.face_detection.FaceDetection.return_value = MagicMock()

            with patch("detector.settings") as mock_settings:
                mock_settings.min_detection_confidence = 0.5

                import detector
                detector._detector = None  # Reset singleton

                result = detector.get_detector()

                assert isinstance(result, detector.FaceDetector)

    def test_get_detector_returns_same_instance(self):
        """Test that get_detector returns the same singleton instance."""
        with patch("detector.mp") as mock_mp:
            mock_mp.solutions.face_detection.FaceDetection.return_value = MagicMock()

            with patch("detector.settings") as mock_settings:
                mock_settings.min_detection_confidence = 0.5

                import detector
                detector._detector = None  # Reset singleton

                instance1 = detector.get_detector()
                instance2 = detector.get_detector()

                assert instance1 is instance2


class TestLookDirectionCalculation:
    """Test look direction calculation logic."""

    def test_direction_ranges(self):
        """Test that direction values are within expected range."""
        # Direction should be between -1 and 1
        test_cases = [
            (0.0, -1.0),    # Far left
            (0.33, -1.0),   # Boundary left
            (0.34, None),   # Just past left boundary (center region)
            (0.5, 0.0),     # Center
            (0.65, None),   # Just before right boundary (center region)
            (0.66, 1.0),    # Boundary right
            (1.0, 1.0),     # Far right
        ]

        for face_center_x, expected_direction in test_cases:
            if face_center_x < 0.33:
                direction = -1.0
            elif face_center_x > 0.66:
                direction = 1.0
            else:
                direction = (face_center_x - 0.5) * 6
                direction = max(-1.0, min(1.0, direction))

            if expected_direction is not None:
                assert abs(direction - expected_direction) < 0.1, f"Failed for x={face_center_x}"
            else:
                assert -1.0 <= direction <= 1.0, f"Direction out of range for x={face_center_x}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
