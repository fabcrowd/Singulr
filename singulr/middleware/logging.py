"""Request ID middleware and optional JSON access logging."""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("singulr.access")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Attach X-Request-ID and optionally emit JSON access logs."""

    def __init__(self, app: object, *, log_json: bool = False) -> None:
        """Configure middleware with optional JSON log format."""
        super().__init__(app)
        self._log_json = log_json

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Propagate or generate request ID and log the request."""
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = request_id
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        if self._log_json:
            logger.info(
                json.dumps(
                    {
                        "event": "http_request",
                        "request_id": request_id,
                        "method": request.method,
                        "path": request.url.path,
                        "status": response.status_code,
                        "duration_ms": duration_ms,
                    }
                )
            )
        return response


def configure_access_logging(*, log_json: bool) -> None:
    """Set singulr.access handler format based on LOG_JSON."""
    access_logger = logging.getLogger("singulr.access")
    access_logger.handlers.clear()
    handler = logging.StreamHandler()
    if log_json:
        handler.setFormatter(logging.Formatter("%(message)s"))
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
        )
    access_logger.addHandler(handler)
    access_logger.setLevel(logging.INFO)
    access_logger.propagate = False
