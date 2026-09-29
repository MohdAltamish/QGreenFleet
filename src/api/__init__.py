"""FastAPI endpoints for prediction, optimization, scenarios, reports."""

from __future__ import annotations

__all__ = ["app"]


def __getattr__(name: str):  # pragma: no cover - thin lazy re-export
    """Expose `app` lazily so importing the package stays cheap."""
    if name == "app":
        from src.api.main import app

        return app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
