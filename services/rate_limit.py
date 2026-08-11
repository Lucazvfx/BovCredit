from __future__ import annotations

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address


# Shared limiter extension used by the main app and the API v1 blueprint.
# The storage backend is configured on the Flask app; memory:// remains the
# explicit local-dev/test fallback, while production can point to a shared
# backend such as Redis.
limiter = Limiter(get_remote_address, default_limits=[])
