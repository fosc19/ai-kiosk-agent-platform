"""Integration tests for Orchestrator <-> Services communication.

F7: Tests that verify orchestrator correctly communicates with backend services.
These tests require services to be running (use `task dev:docker`).
"""

import asyncio
import json
import time
import base64

import pytest
import httpx


# Skip tests if services not running
pytestmark = pytest.mark.integration


class TestOrchestratorHealth:
    """Test orchestrator health and connectivity."""

    @pytest.mark.asyncio
    async def test_orchestrator_healthz(self):
        """Test orchestrator health endpoint."""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get("http://localhost:8765/healthz", timeout=5.0)
                assert response.status_code == 200

                data = response.json()
                assert data["status"] == "healthy"
                assert data["service"] == "orchestrator"

            except httpx.ConnectError:
                pytest.skip("Orchestrator not running at localhost:8765")


class TestOrchestratorToSpeech:
    """Test Orchestrator -> Speech service communication."""

    @pytest.mark.asyncio
    async def test_speech_service_health(self):
        """Test speech service is reachable."""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get("http://localhost:9001/healthz", timeout=5.0)
                assert response.status_code == 200

            except httpx.ConnectError:
                pytest.skip("Speech service not running at localhost:9001")

    @pytest.mark.asyncio
    async def test_validate_audio_endpoint(self):
        """Test audio validation endpoint."""
        # Create minimal valid WAV header
        import struct
        import io

        # Create 1 second of silence at 16kHz mono 16-bit
        sample_rate = 16000
        duration = 1
        num_samples = sample_rate * duration

        wav_buffer = io.BytesIO()
        # RIFF header
        wav_buffer.write(b"RIFF")
        wav_buffer.write(struct.pack("<I", 36 + num_samples * 2))  # File size - 8
        wav_buffer.write(b"WAVE")
        # fmt chunk
        wav_buffer.write(b"fmt ")
        wav_buffer.write(struct.pack("<I", 16))  # Chunk size
        wav_buffer.write(struct.pack("<H", 1))   # Audio format (PCM)
        wav_buffer.write(struct.pack("<H", 1))   # Num channels
        wav_buffer.write(struct.pack("<I", sample_rate))  # Sample rate
        wav_buffer.write(struct.pack("<I", sample_rate * 2))  # Byte rate
        wav_buffer.write(struct.pack("<H", 2))   # Block align
        wav_buffer.write(struct.pack("<H", 16))  # Bits per sample
        # data chunk
        wav_buffer.write(b"data")
        wav_buffer.write(struct.pack("<I", num_samples * 2))  # Data size
        wav_buffer.write(b"\x00\x00" * num_samples)  # Silence

        audio_b64 = base64.b64encode(wav_buffer.getvalue()).decode()

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    "http://localhost:9001/validate-audio",
                    json={
                        "audio_data": audio_b64,
                        "session_id": "test_session",
                        "turn_id": "test_turn",
                    },
                    timeout=10.0,
                )

                assert response.status_code == 200
                data = response.json()
                assert "valid" in data

            except httpx.ConnectError:
                pytest.skip("Speech service not running")


class TestOrchestratorToVision:
    """Test Orchestrator -> Vision service communication."""

    @pytest.mark.asyncio
    async def test_vision_service_health(self):
        """Test vision service is reachable."""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get("http://localhost:9003/healthz", timeout=5.0)
                assert response.status_code == 200

            except httpx.ConnectError:
                pytest.skip("Vision service not running at localhost:9003")

    @pytest.mark.asyncio
    async def test_vision_detect_endpoint(self):
        """Test vision detection endpoint."""
        from PIL import Image
        import io

        # Create a simple test image (no face)
        img = Image.new("RGB", (640, 480), color="gray")
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG")
        image_b64 = base64.b64encode(buffer.getvalue()).decode()

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    "http://localhost:9003/detect",
                    json={"image_data": image_b64},
                    timeout=10.0,
                )

                assert response.status_code == 200
                data = response.json()

                # Should return detection result structure
                assert "present" in data
                assert "look_direction" in data
                assert "confidence" in data

                # No face in gray image
                assert data["present"] is False

            except httpx.ConnectError:
                pytest.skip("Vision service not running")


class TestOrchestratorToMCPTools:
    """Test Orchestrator -> MCP Tools service communication."""

    @pytest.mark.asyncio
    async def test_mcp_tools_health(self):
        """Test MCP Tools service is reachable."""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get("http://localhost:9002/healthz", timeout=5.0)
                assert response.status_code == 200

            except httpx.ConnectError:
                pytest.skip("MCP Tools service not running at localhost:9002")

    @pytest.mark.asyncio
    async def test_list_stores_tool(self):
        """Test list_stores MCP tool."""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    "http://localhost:9002/tools/list_stores",
                    json={},
                    timeout=10.0,
                )

                assert response.status_code == 200
                data = response.json()

                # Should return stores array
                assert "stores" in data or "result" in data

            except httpx.ConnectError:
                pytest.skip("MCP Tools service not running")

    @pytest.mark.asyncio
    async def test_resolve_store_tool(self):
        """Test resolve_store MCP tool."""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    "http://localhost:9002/tools/resolve_store",
                    json={"query": "demo_fashion"},
                    timeout=10.0,
                )

                assert response.status_code == 200
                data = response.json()

                # Should return store info or no match
                assert "store" in data or "match" in data or "result" in data

            except httpx.ConnectError:
                pytest.skip("MCP Tools service not running")


class TestServiceIntegration:
    """Test full service integration."""

    @pytest.mark.asyncio
    async def test_all_services_healthy(self):
        """Test that all services are healthy."""
        services = [
            ("Orchestrator", "http://localhost:8765/healthz"),
            ("Speech", "http://localhost:9001/healthz"),
            ("Vision", "http://localhost:9003/healthz"),
            ("MCP Tools", "http://localhost:9002/healthz"),
        ]

        async with httpx.AsyncClient() as client:
            results = {}
            for name, url in services:
                try:
                    response = await client.get(url, timeout=5.0)
                    results[name] = response.status_code == 200
                except httpx.ConnectError:
                    results[name] = False

            # Check if at least orchestrator is running
            if not results.get("Orchestrator"):
                pytest.skip("Orchestrator not running - skipping integration tests")

            # Log which services are available
            available = [name for name, ok in results.items() if ok]
            unavailable = [name for name, ok in results.items() if not ok]

            if unavailable:
                pytest.skip(f"Services not available: {unavailable}")

            assert all(results.values()), f"Some services unhealthy: {results}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
