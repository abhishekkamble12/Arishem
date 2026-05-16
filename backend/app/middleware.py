"""
Request/response logging middleware.

Logs every inbound request and its response status + duration.
Useful for debugging and monitoring in production.
"""

import logging
import time

logger = logging.getLogger("arishem.requests")


class RequestLoggingMiddleware:
    """
    Logs method, path, status code, and duration for every request.

    Add to settings.MIDDLEWARE:
        'app.middleware.RequestLoggingMiddleware',
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start = time.monotonic()

        response = self.get_response(request)

        duration_ms = (time.monotonic() - start) * 1000
        logger.info(
            "%s %s → %d  (%.1fms)",
            request.method,
            request.path,
            response.status_code,
            duration_ms,
        )

        return response
