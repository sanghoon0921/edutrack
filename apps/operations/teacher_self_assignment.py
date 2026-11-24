from __future__ import annotations

import json
import logging
from typing import Any
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ImproperlyConfigured, PermissionDenied, ValidationError
from django.db import DatabaseError, transaction
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from config.cache_utils import safe_cache_delete_many
from apps.accounts.models import User
from apps.students.repositories import get_student_repository
from apps.students.services import StudentService
from apps.dashboard.class_catalog import term_subject_options
from apps.students.student_rows import assigned_student_items, decorate, with_classes
from .models import TeacherStudentAccess
from .services import add_teacher_student_access, remove_teacher_student_access

logger = logging.getLogger(__name__)
SEARCH_RESULT_LIMIT = 30
UPDATE_STUDENT_LIMIT = 100
CLASS_STATUSES = (("P", "진행중"), ("W", "대기"), ("E", "종료"), ("C", "폐강"))


def _is_teacher(user: Any) -> bool:
    return bool(getattr(user, "is_authenticated", False)
                and getattr(user, "is_active", False)
                and getattr(user, "role", None) == User.Role.TEACHER)


def _teacher_only_response() -> HttpResponse:
    return HttpResponse("강사 계정에서만 담당 학생을 직접 관리할 수 있습니다.",
                        status=403, content_type="text/plain; charset=utf-8")


def _active_accesses(user) -> list[TeacherStudentAccess]:
    return list(TeacherStudentAccess.objects.filter(teacher=user, is_active=True)
                .order_by("student_name", "student_no", "id"))


def _access_payload(access: TeacherStudentAccess) -> dict[str, str]:
    number = str(access.student_no).strip()
    return {"student_no": number,
            "student_name": str(access.student_name or "").strip() or f"학생 {number}",
            "detail_url": reverse("students:detail", args=[number])}


def _assigned_payload(user) -> list[dict[str, str]]:
    return [_access_payload(access) for access in _active_accesses(user)]


def _student_payload(student, *, assigned: bool) -> dict[str, Any]:
    number = str(student.student_id).strip()
    return {"student_no": number, "student_name": student.name,
            "english_name": student.english_name, "grade": student.grade,
            "school": student.school, "country": student.country,
            "city": student.city, "branch": student.branch, "status": student.status,
            "assigned": assigned, "detail_url": reverse("students:detail", args=[number])}


def _parse_update_payload(request: HttpRequest) -> tuple[str, list[str]]:
    # Reject malformed/overlong input rather than partially applying a batch.
    try:
        if request.content_type == "application/json":
            payload = json.loads(request.body.decode("utf-8") or "{}")
            if not isinstance(payload, dict):
                return "", []
            action, raw = payload.get("action"), payload.get("student_nos")
        else:
            action, raw = request.POST.get("action"), request.POST.getlist("student_nos")
        if not isinstance(action, str) or not isinstance(raw, list) or len(raw) > UPDATE_STUDENT_LIMIT:
            return "", []
        numbers = []
        for value in raw:
            if isinstance(value, bool) or not isinstance(value, (str, int)):
                return "", []
            value = str(value).strip()
            if not value or len(value) > 50 or any(ord(c) < 32 or ord(c) == 127 for c in value):
                return "", []
            if value not in numbers:
                numbers.append(value)
        return action.strip().lower(), numbers
    except (UnicodeDecodeError, ValueError, TypeError):
        return "", []


def _search_payload(user, keyword: str) -> tuple[dict, int]:
    if not keyword:
        return {"ok": True, "results": [], "result_count": 0,
                "message": "수업을 선택하거나 학생 이름·학생번호로 검색하세요."}, 200
    try:
        students = StudentService().search_students(keyword)[:SEARCH_RESULT_LIMIT]
        assigned = {str(n).strip() for n in TeacherStudentAccess.objects.filter(
            teacher=user, is_active=True).values_list("student_no", flat=True)}
        results = [_student_payload(s, assigned=str(s.student_id).strip() in assigned) for s in students]
    except (DatabaseError, ImproperlyConfigured) as exc:
        logger.warning("teacher_assignment_search_failed type=%s", type(exc).__name__)
        return {"ok": False, "results": [], "result_count": 0, "code": "student_source_unavailable",
                "message": "학생 조회 연결을 확인하지 못했습니다. 담당 학생이 없는 상태와 다릅니다. VPN·DB 설정을 확인한 뒤 다시 검색하세요."}, 503
    return {"ok": True, "results": results, "result_count": len(results),
            "message": f"검색 결과 {len(results)}명입니다. 등록 버튼 또는 체크 후 선택 추가를 누르세요."
                       if results else "검색 조건에 맞는 학생이 없습니다."}, 200


def _apply_assignments(request, action: str, numbers: list[str]) -> tuple[dict, int]:
    if action not in {"add", "remove"} or not numbers:
        return {"ok": False, "code": "invalid_selection",
                "message": "추가하거나 제외할 학생을 선택해 주세요. 한 번에 최대 100명입니다."}, 400
    try:
        students = {}
        if action == "add":
            # Fresh repository read: do not reuse an old negative student-profile cache.
            service = StudentService(repository=get_student_repository())
            students = {str(s.student_id).strip(): s for s in service.get_students(numbers)}
            missing = [n for n in numbers if n not in students]
            if missing:
                return {"ok": False, "code": "student_missing", "missing": missing,
                        "message": "인트라넷에서 확인되지 않는 학생이 포함되어 있어 전체 등록을 취소했습니다."}, 400
        changed = 0
        with transaction.atomic():
            # Caller-supplied teacher/user IDs are deliberately never used.
            if action == "add":
                for number in numbers:
                    student = students[number]
                    existing = TeacherStudentAccess.objects.filter(teacher=request.user, student_no=number).first()
                    if existing and existing.is_active and existing.student_name == student.name:
                        continue
                    add_teacher_student_access(request=request, teacher=request.user,
                                               student_no=number, student_name=student.name)
                    changed += 1
            else:
                accesses = list(TeacherStudentAccess.objects.filter(
                    teacher=request.user, student_no__in=numbers, is_active=True))
                for access in accesses:
                    remove_teacher_student_access(request=request, teacher=request.user, access=access)
                    changed += 1
            assigned = _assigned_payload(request.user)
            if action == "add":
                keys = tuple(StudentService._cache_key(number) for number in numbers)
                transaction.on_commit(lambda: safe_cache_delete_many(keys))
        message = (f"{changed}명을 담당 학생으로 등록했습니다. 오른쪽 등록 학생 목록을 확인하세요."
                   if action == "add" else f"{changed}명을 담당 학생에서 제외했습니다. 과거 제출 기록은 삭제하지 않았습니다.")
        if not changed:
            message = "이미 반영된 상태입니다. 현재 담당 학생 목록을 확인하세요."
        return {"ok": True, "message": message, "assigned": assigned,
                "assigned_count": len(assigned), "changed_count": changed}, 200
    except (DatabaseError, ImproperlyConfigured) as exc:
        logger.warning("teacher_assignment_save_failed type=%s", type(exc).__name__)
        return {"ok": False, "code": "save_failed",
                "message": "학생 확인 또는 저장에 실패했습니다. 화면을 새로 열어 현재 목록을 확인한 뒤 다시 시도하세요."}, 503
    except (PermissionDenied, ValidationError):
        return {"ok": False, "code": "permission_denied", "message": "강사 본인의 담당 학생만 변경할 수 있습니다."}, 403


@login_required
@require_GET
@never_cache
def teacher_student_assignment(request: HttpRequest) -> HttpResponse:
    if not _is_teacher(request.user):
        return _teacher_only_response()
    keyword = str(request.GET.get("q") or "").strip()[:100]
    result, _ = _search_payload(request.user, keyword)  # 스크립트가 꺼진 화면(noscript)용 검색
    assigned = _assigned_payload(request.user)
    try:
        items, _count, _unresolved = assigned_student_items(user=request.user, student_service=StudentService(), keyword="", limit=None)
        assigned_rows = with_classes(items)
    except (DatabaseError, ImproperlyConfigured) as exc:
        logger.warning("teacher_assignment_rows_unavailable type=%s", type(exc).__name__)
        assigned_rows = [decorate({"student_id": a["student_no"], "name": a["student_name"]}) for a in assigned]
    options = term_subject_options()
    return render(request, "operations/teacher_student_assignment.html", {
        "page_title": "담당 학생 관리", "assigned_students": assigned, "assigned_rows": assigned_rows,
        "assigned_count": len(assigned), "keyword": keyword,
        "search_results": result["results"], "search_message": result["message"],
        "search_error": not result["ok"],
        "class_statuses": CLASS_STATUSES, "terms": options.terms, "subjects": options.subjects,
        "student_source_label": "실제 인트라넷" if str(getattr(settings, "STUDENT_DATA_SOURCE", "")).lower() == "intranet" else "테스트 데이터",
    })


@login_required
@require_POST
@never_cache
def teacher_student_assignment_update(request: HttpRequest) -> HttpResponse:
    if not _is_teacher(request.user):
        return JsonResponse({"ok": False, "message": "강사 계정에서만 담당 학생을 변경할 수 있습니다."}, status=403)
    action, numbers = _parse_update_payload(request)
    payload, status = _apply_assignments(request, action, numbers)
    if request.content_type == "application/json" or request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse(payload, status=status)
    # Standard forms are a complete fallback when JS/network enhancement fails.
    (messages.success if payload["ok"] else messages.error)(request, payload["message"])
    url = reverse("operations:teacher-student-assignment")
    q = str(request.POST.get("q") or "").strip()[:100]
    return redirect(url + ("?" + urlencode({"q": q}) if q else ""))
