from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.contrib.auth.decorators import login_required
from config.cache_utils import safe_cache_get, safe_cache_set
from django.core.exceptions import PermissionDenied
from django.db import DatabaseError
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import NoReverseMatch, reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET

logger = logging.getLogger(__name__)

CACHE_VERSION = "v1"
DEFAULT_CACHE_SECONDS = 60

CLASS_STATUS_LABELS = {
    "W": "대기",
    "P": "진행",
    "E": "종료",
    "C": "폐강",
}

CLASS_TYPE_LABELS = {
    "ONLINE": "온라인",
    "OFFLINE": "오프라인",
    "ALL": "온·오프라인",
    "ON": "온라인",
    "OFF": "오프라인",
}

LESSON_TYPE_LABELS = {
    "LECTURE": "Lecture",
    "READING": "Reading",
    "WRITING": "Writing",
    "MATH": "Math",
    "SKILL": "Skill",
    "TA": "TA",
}


def _is_admin_user(user: Any) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False

    if getattr(user, "is_superuser", False):
        return True

    role = getattr(user, "role", "")
    role = getattr(role, "value", role)
    return str(role or "").upper() == "ADMIN"


def _format_time(value: Any) -> str:
    if value in (None, ""):
        return "-"

    text = str(value).strip()
    digits = "".join(character for character in text if character.isdigit())
    if len(digits) >= 4:
        return f"{digits[-4:-2]}:{digits[-2:]}"
    return text


def _list_url(request: HttpRequest) -> str:
    requested = request.GET.get("next", "").strip()
    if requested and url_has_allowed_host_and_scheme(
        requested,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return requested

    try:
        return reverse("dashboard:admin-classes")
    except NoReverseMatch:
        try:
            return reverse("admin-classes")
        except NoReverseMatch:
            return "/dashboard/admin/classes/"


def _build_detail_payload(class_no: int) -> dict[str, Any] | None:
    # 실제 서비스에서는 여기서 사내 DB를 읽기 전용으로 조회합니다(공개용 사본에서는 뺐습니다).
    from config.excluded import ExternalSourceExcluded

    raise ExternalSourceExcluded('_build_detail_payload')


@login_required
@require_GET
def admin_class_detail(
    request: HttpRequest,
    class_no: int,
) -> HttpResponse:
    """인트라넷의 클래스 정보를 읽기 전용 상세 화면으로 표시합니다."""

    if not _is_admin_user(request.user):
        raise PermissionDenied("관리자만 클래스 상세를 확인할 수 있습니다.")

    cache_seconds = int(
        getattr(
            settings,
            "ADMIN_CLASS_DETAIL_CACHE_SECONDS",
            DEFAULT_CACHE_SECONDS,
        )
    )
    cache_key = f"edutrack:admin-class-detail:{CACHE_VERSION}:{class_no}"
    detail = safe_cache_get(cache_key) if cache_seconds > 0 else None
    cache_state = "HIT" if detail is not None else "MISS"

    if detail is None:
        try:
            detail = _build_detail_payload(class_no)
        except DatabaseError:
            logger.exception(
                "관리자 클래스 상세 조회 중 인트라넷 DB 오류가 발생했습니다. class_no=%s",
                class_no,
            )
            return render(
                request,
                "errors/503.html",
                {
                    "page_title": "클래스 정보를 불러오지 못했습니다",
                },
                status=503,
            )

        if detail is None:
            raise Http404("해당 클래스를 찾을 수 없습니다.")

        if cache_seconds > 0:
            safe_cache_set(cache_key, detail, timeout=cache_seconds)

    response = render(
        request,
        "dashboard/admin_class_detail.html",
        {
            "page_title": f"{detail['class_name']} · Class 상세",
            "detail": detail,
            "class_list_url": _list_url(request),
        },
    )
    response["Cache-Control"] = "private, max-age=30"
    response["X-EduTrack-Class-Detail-Cache"] = cache_state
    return response
