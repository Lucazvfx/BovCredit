from __future__ import annotations

from flask import Blueprint

api_v1_bp = Blueprint("api_v1", __name__)

from .errors import register_error_handlers  # noqa: E402

register_error_handlers(api_v1_bp)

from . import routes  # noqa: E402,F401

__all__ = ["api_v1_bp"]
