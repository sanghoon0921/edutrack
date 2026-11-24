from __future__ import annotations

import json
import re
from collections.abc import Iterable
from typing import Any

from django.db.utils import DatabaseError
from django.urls import reverse

from apps.operations.access import restrict_student_ids_for_user

from .contracts import StudentSummary
from .services import StudentService


STUDENT_SELECTION_LIMIT = 200
_STUDENT_ID_SPLIT_RE = re.compile(r"[\s,;]+")


def parse_student_ids(value: Any) -> list[str]:
    """폼·기존 텍스트 입력·JSON 배열을 같은 학생번호 목록으로 정규화합니다."""

    if value is None:
        return []

    if isinstance(value, (list, tuple, set)):
        candidates: Iterable[Any] = value
    else:
        raw_value = str(value).strip()
        if not raw_value:
            return []

        if raw_value.startswith("["):
            try:
                parsed = json.loads(raw_value)
            except (TypeError, ValueError, json.JSONDecodeError):
                parsed = None
            if isinstance(parsed, list):
                candidates = parsed
            else:
                candidates = _STUDENT_ID_SPLIT_RE.split(raw_value)
        else:
            candidates = _STUDENT_ID_SPLIT_RE.split(raw_value)

    return list(
        dict.fromkeys(
            str(candidate).strip()
            for candidate in candidates
            if str(candidate).strip()
        )
    )


def student_to_selector_item(student: StudentSummary) -> dict[str, str]:
    return {
        "student_id": student.student_id,
        "name": student.name,
        "english_name": student.english_name,
        "grade": student.grade,
        "school": student.school,
        "country": student.country,
        "city": student.city,
        "branch": student.branch,
        "status": student.status,
    }


def _recipient_fallback_map(recipients: Iterable[Any] | None) -> dict[str, str]:
    fallback: dict[str, str] = {}
    for recipient in recipients or ():
        student_id = str(getattr(recipient, "student_id", "")).strip()
        student_name = str(getattr(recipient, "student_name", "")).strip()
        if student_id:
            fallback[student_id] = student_name
    return fallback


def build_student_selector_context(
    *,
    form,
    user,
    recipients: Iterable[Any] | None = None,
) -> dict[str, Any]:
    """학생 선택 컴포넌트가 필요한 초기 선택값과 안전한 검색 URL을 만듭니다."""

    bound_field = form["student_ids"]
    selected_ids = parse_student_ids(bound_field.value())
    from apps.lms.integrations import selector_scope
    group_scope = selector_scope(form,user) if "group" in form.fields else None
    allowed_ids = [sid for sid in selected_ids if sid in group_scope[1]] if group_scope else restrict_student_ids_for_user(user, selected_ids)
    allowed_set = set(allowed_ids)
    fallback_names = group_scope[1] if group_scope else _recipient_fallback_map(recipients)
    lookup_error = False

    try:
        resolved_students = [] if group_scope else StudentService().get_students(allowed_ids)
    except DatabaseError:
        resolved_students = []
        lookup_error = True

    resolved_map = {
        student.student_id: student
        for student in resolved_students
    }

    selected_items: list[dict[str, str]] = []
    for student_id in selected_ids:
        student = resolved_map.get(student_id)
        if student is not None:
            selected_items.append(student_to_selector_item(student))
            continue

        if student_id not in allowed_set:
            selected_items.append(
                {
                    "student_id": student_id,
                    "name": "선택 권한 없음",
                    "english_name": "",
                    "grade": "",
                    "school": "",
                    "country": "",
                    "city": "",
                    "branch": "",
                    "status": "확인 필요",
                }
            )
            continue

        selected_items.append(
            {
                "student_id": student_id,
                "name": fallback_names.get(student_id) or "학생 정보 확인 필요",
                "english_name": "",
                "grade": "",
                "school": "",
                "country": "",
                "city": "",
                "branch": "",
                "status": "확인 필요",
            }
        )

    if "group" in form.fields:
        form.fields["group"].widget.attrs["data-lms-student-search-pattern"] = reverse("lms:group-students",args=[0]).replace("/0/", "/{group}/")
        form.fields["group"].widget.attrs["data-lms-default-search"] = reverse("students:selector-search")
    component_id = f"student-selector-{bound_field.auto_id.replace('_', '-')}"
    return {
        "component_id": component_id,
        "data_script_id": f"{component_id}-initial-data",
        "field": bound_field,
        "selected_items": selected_items,
        "search_url": reverse("lms:group-students",args=[group_scope[0]]) if group_scope else reverse("students:selector-search"),
        "browse_url": reverse("students:selector-browse"),
        "options_url": reverse("students:selector-options"),
        "activity_group": str(group_scope[0]) if group_scope else "",
        "max_count": STUDENT_SELECTION_LIMIT,
        "lookup_error": lookup_error,
        "teacher_mode": getattr(user, "role", "") == "TEACHER",
    }
