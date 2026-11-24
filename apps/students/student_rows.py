"""학생 한 줄 행(공용 학생 목록 부품)에 쓰는 표시 값을 만든다.

서버가 그리는 화면(templates/components/student_row.html)과 브라우저가 그리는 화면
(static/js/global/student-browser.js 의 row 함수)이 같은 값을 쓰도록, 표시 문구는 여기서만 만든다.
"""
from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from django.core.exceptions import ImproperlyConfigured
from django.db import DatabaseError
from django.utils.connection import ConnectionDoesNotExist

from apps.learning.models import LearningGroup
from apps.lms.access import staff_group_ids
from apps.lms.models import GroupMember
from apps.operations.models import TeacherStudentAccess

from .selection import STUDENT_SELECTION_LIMIT, student_to_selector_item

logger = logging.getLogger(__name__)

CLASS_LABEL_LIMIT = 2
SEARCH_FIELDS = ("name", "english_name", "student_id", "school", "grade", "branch", "country", "city")
STATUS_LABELS = {"P": "진행", "W": "예정"}


def class_label(classes: Iterable[dict[str, Any]], limit: int = CLASS_LABEL_LIMIT) -> str:
    names = [str(c.get("name") or "").strip() for c in classes]
    names = [name for name in names if name]
    if len(names) <= limit:
        return " · ".join(names)
    return " · ".join(names[:limit]) + f" 외 {len(names) - limit}"


def decorate(item: dict[str, Any]) -> dict[str, Any]:
    """행에 필요한 표시 값을 더한 새 dict를 돌려준다(원본은 바꾸지 않는다)."""
    row = dict(item)
    classes = list(row.get("classes") or [])
    text = lambda key: str(row.get(key) or "").strip()  # noqa: E731
    row["classes"] = classes
    row["school_grade"] = " · ".join(value for value in (text("school"), text("grade")) if value)
    row["class_label"] = class_label(classes)
    row["class_ids"] = " ".join(str(c.get("id")) for c in classes if c.get("id"))
    row["search_text"] = " ".join(text(key) for key in SEARCH_FIELDS if text(key)).casefold()
    return row


def with_classes(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """각 학생에 진행·예정 수업을 붙인다. 수업 조회에 실패하면 수업 없이 돌려준다(목록은 계속 보이게)."""
    from apps.students.bulk_selector import current_classes_for  # bulk_selector 가 이 모듈을 가져오므로 여기서

    ids = [str(item.get("student_id") or "").strip() for item in items]
    try:
        by_student = current_classes_for([sid for sid in ids if sid])
    except (DatabaseError, ImproperlyConfigured, ConnectionDoesNotExist) as exc:
        logger.warning("student_classes_unavailable type=%s", type(exc).__name__)
        by_student = {}
    return [decorate({**item, "classes": by_student.get(sid, [])}) for item, sid in zip(items, ids)]


def item_matches(item: dict[str, Any], keyword: str) -> bool:
    if not keyword:
        return True
    haystack = " ".join(
        str(item.get(key, ""))
        for key in ("student_id", "name", "english_name", "grade", "school", "country", "city", "branch", "status")
    ).casefold()
    return keyword.casefold() in haystack


def assigned_student_items(*, user, student_service, keyword: str = "", limit: int | None = STUDENT_SELECTION_LIMIT) -> tuple[list[dict], int, int]:
    """담당 학생을 이름순으로 해석하고, 인트라넷에서 못 찾은 학생도 '확인 필요'로 남긴다(limit=None 이면 전부)."""
    accesses = TeacherStudentAccess.objects.filter(teacher=user, is_active=True).order_by("student_name", "student_no")
    accesses = list(accesses if limit is None else accesses[:limit])
    ordered_ids = [str(access.student_no).strip() for access in accesses]
    student_map = {student.student_id: student for student in student_service.get_students(ordered_ids)}

    items: list[dict] = []
    unresolved_count = 0
    for access in accesses:
        student_id = str(access.student_no).strip()
        student = student_map.get(student_id)
        if student is not None:
            item = student_to_selector_item(student)
            item.update({"is_resolved": True, "selectable": True})
        else:
            unresolved_count += 1
            item = {
                "student_id": student_id,
                "name": str(access.student_name or "").strip() or f"학생 {student_id}",
                "english_name": "", "grade": "", "school": "", "country": "", "city": "", "branch": "",
                "status": "인트라넷 학생 정보 확인 필요",
                "is_resolved": False,
                "selectable": False,
            }
        if item_matches(item, keyword):
            items.append(item)
    return items, len(accesses), unresolved_count


def scope_options(user, rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """담당 학생 화면 드롭다운 항목: (인트라넷 수업, EduTrack 반).

    수업은 행에 붙은 진행·예정 수업과 그 수업의 담당 학생 수,
    반은 사용자가 가르치는 반 중 담당 학생이 한 명 이상 있는 반과 그 학생 번호 목록이다.
    """
    counts: dict[str, dict[str, Any]] = {}
    for row in rows:
        for cls in row.get("classes") or []:
            key = str(cls.get("id"))
            entry = counts.setdefault(key, {"id": key, "name": str(cls.get("name") or ""),
                                            "status_label": STATUS_LABELS.get(str(cls.get("status") or ""), ""), "count": 0})
            entry["count"] += 1
    classes = sorted(counts.values(), key=lambda c: (c["name"], c["id"]))

    ids = {str(row.get("student_id")) for row in rows}
    groups = list(LearningGroup.objects.filter(pk__in=staff_group_ids(user)).order_by("title", "pk"))
    members: dict[int, set[str]] = {}
    for group_id, student_no in GroupMember.objects.filter(group__in=groups, active=True, student_no__in=ids).values_list("group_id", "student_no"):
        members.setdefault(group_id, set()).add(str(student_no))
    return classes, [{"id": g.pk, "name": g.title, "members": sorted(members[g.pk])} for g in groups if members.get(g.pk)]


def pool_student_pairs(user, group_id: int | None = None) -> list[tuple[str, str]]:
    """화면에 보일 학생(번호, 이름) — 관리자: 모든 반 학생 + 모든 담당 지정, 강사: 담당 지정 + 자기 반 학생, TA: 담당 반 학생(11/19).
    group_id 를 주면 그 반 학생만(볼 수 있는 반일 때). 이름순."""
    from apps.lms.access import staff_group_ids
    from apps.lms.models import GroupMember
    from apps.operations.access import is_admin, is_teacher

    group_ids = list(staff_group_ids(user))
    if group_id is not None:
        group_ids = [gid for gid in group_ids if gid == group_id]
    pairs: dict[str, str] = {}
    for no, name in GroupMember.objects.filter(group_id__in=group_ids, active=True).values_list("student_no", "student_name"):
        no = str(no).strip()
        if no:
            pairs.setdefault(no, str(name or "").strip())
    if group_id is None and (is_admin(user) or is_teacher(user)):
        accesses = TeacherStudentAccess.objects.filter(is_active=True)
        if not is_admin(user):
            accesses = accesses.filter(teacher=user)
        for no, name in accesses.values_list("student_no", "student_name"):
            no = str(no).strip()
            if no:
                pairs.setdefault(no, str(name or "").strip())
    return sorted(pairs.items(), key=lambda item: (item[1], item[0]))


def pool_student_items(*, user, student_service, keyword: str = "", group_id: int | None = None) -> list[dict]:
    """pool_student_pairs 를 인트라넷 학생 정보로 풀어 선택 목록 줄(dict)로. 못 찾은 학생은 '확인 필요'로 남깁니다."""
    pairs = pool_student_pairs(user, group_id)
    student_map = {student.student_id: student for student in student_service.get_students([no for no, _ in pairs])}
    items: list[dict] = []
    for no, name in pairs:
        student = student_map.get(no)
        if student is not None:
            item = student_to_selector_item(student)
            item.update({"is_resolved": True, "selectable": True})
        else:
            item = {"student_id": no, "name": name or f"학생 {no}", "english_name": "", "grade": "", "school": "",
                    "country": "", "city": "", "branch": "", "status": "인트라넷 학생 정보 확인 필요",
                    "is_resolved": False, "selectable": False}
        if item_matches(item, keyword):
            items.append(item)
    return items
