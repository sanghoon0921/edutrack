from __future__ import annotations

from django.db import connections
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from .cache_utils import cache_roundtrip_is_healthy


@never_cache
@require_GET
def live(request):
    """웹 프로세스가 요청을 받을 수 있는지 확인합니다."""

    return JsonResponse({"status": "ok", "service": "edutrack"})


@never_cache
@require_GET
def ready(request):
    """기본 DB는 필수로, 캐시는 선택 가속 장치로 점검합니다."""

    components = {
        "default_database": "ok",
        "cache": "ok",
    }
    status_code = 200

    try:
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        components["default_database"] = "error"
        status_code = 503

    if not cache_roundtrip_is_healthy():
        # Redis 장애 시 서비스는 원본 DB 조회로 계속 동작하므로 degraded로 표시합니다.
        components["cache"] = "degraded"

    return JsonResponse(
        {
            "status": "ok" if status_code == 200 else "unavailable",
            "components": components,
        },
        status=status_code,
    )
