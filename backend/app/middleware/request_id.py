"""Request id middleware.

Assigns a stable ``X-Request-Id`` to every request, either from the
inbound header (if present and well-formed) or a freshly minted ULID-like
string. The id is exposed via ``request.state.request_id`` and on the
``X-Request-Id`` response header so the dashboard and Android agent
can correlate logs across services.
"""

from __future__ import annotations

import logging
import re
import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_HEADER = "X-Request-Id"
# Restrict accepted inbound ids to a sane charset / length.
_VALID = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
_log = logging.getLogger(__name__)


def _new_id() -> str:
    return secrets.token_urlsafe(12)


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        inbound = request.headers.get(_HEADER, "").strip()
        request_id = inbound if _VALID.match(inbound) else _new_id()
        request.state.request_id = request_id

        # Bind to the logger context. We use a LoggerAdapter so every
        # downstream log line carries the request id.
        old_factory = logging.getLogRecordFactory()

        def factory(*args, **kwargs):
            record = old_factory(*args, **kwargs)
            record.request_id = request_id
            return record

        logging.setLogRecordFactory(factory)
        try:
            response: Response = await call_next(request)
        finally:
            logging.setLogRecordFactory(old_factory)

        response.headers[_HEADER] = request_id
        return response
