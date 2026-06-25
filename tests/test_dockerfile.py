"""Structural checks for production Dockerfile."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DOCKERFILE = REPO / "Dockerfile"


def test_dockerfile_exists() -> None:
    """Production Dockerfile is present."""
    assert DOCKERFILE.is_file()


def test_dockerfile_uses_slim_python_and_uvicorn() -> None:
    """Image is Python-based and runs uvicorn on port 8000."""
    text = DOCKERFILE.read_text(encoding="utf-8").lower()
    assert "python" in text
    assert "slim" in text or "alpine" in text
    assert "uvicorn" in text
    assert "8000" in text


def test_dockerfile_does_not_copy_env_file() -> None:
    """Secrets are not baked into the image."""
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert ".env" not in text or "#" in text.split(".env")[0][-20:]
