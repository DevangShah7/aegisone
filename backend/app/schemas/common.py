"""Shared schema helpers.

``ErrorBody`` is the canonical wire shape for all error responses —
``{"code": "...", "message": "..."}`` — so the dashboard can map
``code`` strings to UI states without parsing free-text messages.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ErrorBody(BaseModel):
    """Canonical 4xx/5xx body returned by every error in AegisOne."""

    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
