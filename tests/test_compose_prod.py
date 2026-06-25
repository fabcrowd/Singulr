"""Structural checks for production Docker Compose overlay."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
COMPOSE_PROD = REPO / "docker-compose.prod.yml"


def test_compose_prod_file_exists() -> None:
    """Production compose overlay is present."""
    assert COMPOSE_PROD.is_file()


def test_compose_prod_defines_app_service_on_port_8000() -> None:
    """App service builds from Dockerfile and exposes port 8000."""
    text = COMPOSE_PROD.read_text(encoding="utf-8").lower()
    assert "app:" in text
    assert "build:" in text
    assert "8000" in text


def test_compose_prod_wires_database_url_to_db_service() -> None:
    """App uses DATABASE_URL pointing at the compose db service."""
    text = COMPOSE_PROD.read_text(encoding="utf-8")
    assert "DATABASE_URL" in text
    assert "@db:" in text or "@db/" in text
