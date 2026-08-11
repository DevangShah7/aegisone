"""Security headers middleware.

Adds the hardened set of response headers we send on every response.
The set follows the OWASP Secure Headers Project recommendations.

We honor ``X-Forwarded-Proto`` only when the request came from a CIDR
listed in ``settings.trusted_proxies``. Anything else is ignored, so a
malicious client can't downgrade the proto.
"""

from __future__ import annotations

import ipaddress
import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.core.config import settings

_log = logging.getLogger(__name__)


# Static defaults; the HSTS value comes from settings so we can disable
# it for local HTTP development without code changes.
_BASE_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "()",
    "X-Developer": settings.developer_name,
    "X-AegisOne-App": settings.app_name,
    "X-AegisOne-Version": settings.app_version,
}

_DOCS_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "connect-src 'self'"
    ),
}


def _client_ip(request: Request) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    host = request.client.host if request.client else None
    if not host:
        return None
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None


def _is_trusted(request: Request) -> bool:
    ip = _client_ip(request)
    if ip is None:
        return False
    return any(ip in net for net in settings.trusted_proxy_networks)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)

        for header, value in _BASE_HEADERS.items():
            response.headers.setdefault(header, value)

        # HSTS only over HTTPS (or when a trusted proxy says so).
        is_https = request.url.scheme == "https"
        if not is_https and _is_trusted(request):
            forwarded_proto = request.headers.get("x-forwarded-proto", "").lower().strip()
            if forwarded_proto == "https":
                is_https = True
        if is_https:
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains; preload",
            )

        # Swagger UI and ReDoc need inline scripts and styles; tighten CSP there.
        path = request.url.path
        if path.startswith("/docs") or path.startswith("/redoc"):
            for header, value in _DOCS_HEADERS.items():
                response.headers.setdefault(header, value)
        else:
            response.headers.setdefault(
                "Content-Security-Policy",
                "default-src 'none'; frame-ancestors 'none'",
            )

        return response
