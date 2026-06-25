"""Shared bot application reference for API ↔ bot bridge."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from telegram.ext import Application

_application: Application | None = None


def set_application(app: Application) -> None:
    """Register the running bot application."""
    global _application
    _application = app


def get_application() -> Application | None:
    """Return the running bot application, if started."""
    return _application
