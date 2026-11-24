from __future__ import annotations

import logging
from time import perf_counter
from uuid import uuid4

from django.conf import settings
from django.http import HttpRequest, HttpResponse


logger = logging.getLogger("edutrack.performance")


class RequestTimingMiddleware:
    """느린 요청을 경로의 개인정보 없이 측정하고 요청 ID를 부여합니다."""

    def __init__(self, get_response):
        self.get_response = get_response
        self.slow_threshold_ms = float(
            getattr(settings, "REQUEST_SLOW_LOG_MS", 750)
        )
        self.server_timing_enabled = bool(
            getattr(settings, "SERVER_TIMING_ENABLED", settings.DEBUG)
        )

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request_id = self._request_id(request)
        request.request_id = request_id
        started_at = perf_counter()

        response = self.get_response(request)

        duration_ms = (perf_counter() - started_at) * 1000
        response["X-Request-ID"] = request_id
        if self.server_timing_enabled:
            response["Server-Timing"] = f"app;dur={duration_ms:.1f}"

        if (
            duration_ms >= self.slow_threshold_ms
            and not request.path.startswith(("/static/", "/media/", "/health/"))
        ):
            resolver_match = getattr(request, "resolver_match", None)
            route = getattr(resolver_match, "view_name", "") or "unresolved"
            user = getattr(request, "user", None)
            role = getattr(user, "role", "anonymous") if user else "anonymous"
            logger.warning(
                "slow_request request_id=%s method=%s route=%s status=%s "
                "duration_ms=%.1f role=%s",
                request_id,
                request.method,
                route,
                response.status_code,
                duration_ms,
                role,
            )

        return response

    @staticmethod
    def _request_id(request: HttpRequest) -> str:
        candidate = (request.headers.get("X-Request-ID") or "").strip()
        normalized = candidate.replace("-", "")
        if candidate and len(candidate) <= 64 and normalized.isalnum():
            return candidate
        return uuid4().hex
