from __future__ import annotations

import logging

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.utils import DatabaseError
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET

from apps.accounts.decorators import teacher_required, class_staff_required
from apps.accounts.demo_account_binding import (
    bind_demo_accounts_to_student,
    demo_account_auto_binding_enabled,
)
from apps.accounts.models import User
from apps.operations.access import is_admin, require_student_access

from .attendance_services import AttendanceService
from .bulk_selector import DIRECTORY_SIZES, browse_students
from .course_services import CourseService
from .forms import StudentSearchForm
from .selection import student_to_selector_item
from .student_rows import assigned_student_items, decorate, scope_options, with_classes, pool_student_items, pool_student_pairs
from .services import StudentService


logger = logging.getLogger(__name__)


def get_student_service() -> StudentService:
    return StudentService()


def get_course_service() -> CourseService:
    return CourseService()


def get_attendance_service() -> AttendanceService:
    return AttendanceService()


def render_database_error(
    request: HttpRequest,
) -> HttpResponse:
    return render(
        request,
        "errors/503.html",
        {
            "page_title": "인트라넷 연결 오류",
        },
        status=503,
    )


def ensure_student_access(
    request: HttpRequest,
    *,
    student,
    student_service: StudentService,
) -> None:
    require_student_access(
        request.user,
        student.student_id,
    )


def _selector_matches(student, keyword: str) -> bool:
    if not keyword:
        return True
    haystack = " ".join(
        (
            student.student_id,
            student.name,
            student.english_name,
            student.grade,
            student.school,
            student.country,
            student.city,
            student.branch,
        )
    ).casefold()
    return keyword.casefold() in haystack


@teacher_required
@require_GET
def student_selector_search(request: HttpRequest) -> JsonResponse:
    """과제·토론·퀴즈와 강사 대시보드가 함께 쓰는 권한 제한 검색 API입니다."""

    keyword = (request.GET.get("q") or "").strip()[:100]
    limit = 30
    assigned_count = 0
    unresolved_count = 0

    try:
        student_service = get_student_service()
        teacher_mode = request.user.role == User.Role.TEACHER and not is_admin(request.user)
        if teacher_mode:
            filtered_items, assigned_count, unresolved_count = assigned_student_items(
                user=request.user,
                student_service=student_service,
                keyword=keyword,
            )
        else:
            students = student_service.search_students(keyword) if keyword else []
            filtered_items = []
            for student in students:
                item = student_to_selector_item(student)
                item.update({"is_resolved": True, "selectable": True})
                filtered_items.append(item)
    except DatabaseError:
        logger.exception("학생 선택 검색 중 DB 오류 발생")
        return JsonResponse(
            {
                "results": [],
                "message": "학생 정보를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.",
            },
            status=503,
        )

    visible = filtered_items[:limit]
    if request.user.role == User.Role.TEACHER and not is_admin(request.user):
        if assigned_count == 0:
            message = (
                "담당 학생이 아직 배정되지 않았습니다. "
                "담당 학생 관리에서 학생을 직접 검색해 추가해 주세요."
            )
        elif not visible and keyword:
            message = f"담당 학생 {assigned_count}명 중 검색어와 일치하는 학생이 없습니다."
        elif unresolved_count and unresolved_count == assigned_count:
            message = (
                "담당 학생 등록은 확인됐지만 인트라넷 학생 정보를 불러오지 못했습니다. "
                "담당 학생 관리에서 학생번호를 다시 확인해 주세요."
            )
        elif unresolved_count:
            message = (
                f"담당 학생 {assigned_count}명 중 {unresolved_count}명의 학생 정보는 "
                "추가 확인이 필요합니다."
            )
        else:
            message = f"담당 학생 {assigned_count}명을 표시합니다."
    else:
        message = ""

    return JsonResponse(
        {
            "results": visible,
            "result_count": len(visible),
            "assigned_count": assigned_count,
            "unresolved_count": unresolved_count,
            "has_more": len(filtered_items) > limit,
            "message": message,
        }
    )


@class_staff_required
def student_list(
    request: HttpRequest,
) -> HttpResponse:
    assigned_mode = (
        request.user.role in (User.Role.TEACHER, User.Role.TA)
        and not is_admin(request.user)
    )
    students = None
    keyword = ""
    assigned_count = 0
    unresolved_count = 0
    scope_classes: list[dict] = []
    scope_groups: list[dict] = []

    if assigned_mode:
        form = StudentSearchForm(request.GET or None)
        has_searched = True
        keyword = (request.GET.get("q") or "").strip()
        if request.GET and not form.is_valid():
            keyword = ""
        elif request.GET:
            keyword = form.cleaned_data["q"]
        try:
            # 담당 학생 화면은 쪽 없이 전부 보여 준다(200명 제한은 선택 API에만 해당).
            if request.user.role == User.Role.TA:
                # TA(11/19): 담당 반 학생
                items = pool_student_items(user=request.user, student_service=get_student_service(), keyword=keyword)
                assigned_count = len(pool_student_pairs(request.user))
                unresolved_count = sum(1 for item in items if not item.get("is_resolved"))
            else:
                items, assigned_count, unresolved_count = assigned_student_items(
                    user=request.user,
                    student_service=get_student_service(),
                    keyword=keyword,
                    limit=None,
                )
            students = with_classes(items)
            scope_classes, scope_groups = scope_options(request.user, students)
        except DatabaseError:
            logger.exception("담당 학생 조회 중 DB 오류 발생")
            return render_database_error(request)
    else:
        # 학생 관리: 인트라넷 목록처럼 검색하지 않아도 첫 쪽(이름순 50명)을 바로 보여 줍니다.
        # 쪽 넘김·즉시 검색은 화면의 student-browser.js 가 이어서 맡습니다.
        has_searched = "q" in request.GET
        form = StudentSearchForm(request.GET) if has_searched else StudentSearchForm()
        if has_searched and form.is_valid():
            keyword = form.cleaned_data["q"]
        try:
            # 기본 20명, 20·50·100명 중 고름(11/11, 인트라넷 학생 리스트와 같게)
            raw_size = request.GET.get("size", "")
            page_size = int(raw_size) if raw_size.isdigit() and int(raw_size) in DIRECTORY_SIZES else DIRECTORY_SIZES[0]
            items, directory_total = browse_students(None, q=keyword, offset=0, limit=page_size)
        except DatabaseError:
            logger.exception("인트라넷 학생 목록 조회 중 DB 오류 발생")
            return render_database_error(request)
        students = with_classes(items)

    return render(
        request,
        "students/student_list.html",
        {
            "page_title": "담당 학생" if assigned_mode else "학생 관리",
            "form": form,
            "students": students,
            "has_searched": has_searched,
            "keyword": keyword,
            "assigned_mode": assigned_mode,
            "assigned_count": assigned_count if assigned_mode else None,
            "unresolved_count": unresolved_count if assigned_mode else 0,
            "scope_classes": scope_classes,
            "scope_groups": scope_groups,
            "page_size": page_size if not assigned_mode else None,
            "page_sizes": DIRECTORY_SIZES,
            "directory_total": directory_total if not assigned_mode else None,
            "directory_pages": max(1, -(-directory_total // page_size)) if not assigned_mode else 1,
        },
    )


@login_required
def student_detail(
    request: HttpRequest,
    student_id: str,
) -> HttpResponse:
    try:
        student_service = (
            get_student_service()
        )

        student = (
            student_service.get_student(
                student_id
            )
        )

    except DatabaseError:
        logger.exception(
            "학생 상세 조회 중 DB 오류"
        )
        return render_database_error(
            request
        )

    if student is None:
        raise Http404(
            "학생 정보를 찾을 수 없습니다."
        )

    ensure_student_access(
        request,
        student=student,
        student_service=student_service,
    )

    # 로컬 테스트 기간에는 관리자가 마지막으로 연 학생을
    # student_test·parent_test의 대표 학생으로 유지합니다.
    if is_admin(request.user) and demo_account_auto_binding_enabled():
        bind_demo_accounts_to_student(student.student_id)

    try:
        course_service = (
            get_course_service()
        )
        attendance_service = (
            get_attendance_service()
        )

        current_courses = (
            course_service
            .get_current_student_courses(
                student.student_id
            )
        )

        course_items = []
        bulk_attendance_loader = getattr(
            attendance_service,
            "get_attendance_for_courses",
            None,
        )
        if callable(bulk_attendance_loader):
            attendance_by_assign = bulk_attendance_loader(
                student.student_id,
                [course.assign_id for course in current_courses],
            )
        else:
            attendance_by_assign = {
                course.assign_id: attendance_service.get_attendance(
                    student.student_id,
                    course.assign_id,
                )
                for course in current_courses
            }

        for course in current_courses:
            attendance_pair = attendance_by_assign.get(course.assign_id)
            if attendance_pair is None:
                attendance_pair = attendance_service.get_attendance(
                    student.student_id,
                    course.assign_id,
                )
            records, summary = attendance_pair

            grouped = (
                attendance_service
                .split_grouped_records(
                    records
                )
            )

            metrics = (
                attendance_service
                .calculate_extended_metrics(
                    summary
                )
            )

            recent_history = (
                grouped[
                    "history_groups"
                ][:3]
            )
            next_upcoming = (
                grouped[
                    "upcoming_groups"
                ][:2]
            )

            course_items.append(
                {
                    "course": course,
                    "summary": summary,
                    "metrics": metrics,
                    "recent_history": (
                        recent_history
                    ),
                    "next_upcoming": (
                        next_upcoming
                    ),
                }
            )

    except DatabaseError:
        logger.exception(
            "현재 수강 수업 조회 중 DB 오류"
        )
        return render_database_error(
            request
        )

    total_planned_count = sum(
        max(item["summary"].scheduled_count, item["course"].planned_count)
        for item in course_items
    )

    return render(
        request,
        "students/student_detail.html",
        {
            "page_title": (
                f"{student.name} 학생 정보"
            ),
            "student": student,
            "course_items": course_items,
            "current_course_count": (
                len(course_items)
            ),
            "total_planned_count": (
                total_planned_count
            ),
        },
    )


@login_required
def attendance_detail(
    request: HttpRequest,
    student_id: str,
    assign_id: str,
) -> HttpResponse:
    try:
        student_service = (
            get_student_service()
        )

        student = (
            student_service.get_student(
                student_id
            )
        )

    except DatabaseError:
        logger.exception(
            "출결 화면 학생 조회 중 DB 오류"
        )
        return render_database_error(
            request
        )

    if student is None:
        raise Http404(
            "학생 정보를 찾을 수 없습니다."
        )

    ensure_student_access(
        request,
        student=student,
        student_service=student_service,
    )

    try:
        course_service = (
            get_course_service()
        )

        course_groups = (
            course_service
            .get_student_course_groups(
                student.student_id
            )
        )
        visible_courses = (
            course_groups["current"]
            + course_groups["completed"]
        )

    except DatabaseError:
        logger.exception(
            "출결 화면 수업 조회 중 DB 오류"
        )
        return render_database_error(
            request
        )

    course = next(
        (
            course
            for course in visible_courses
            if course.assign_id == assign_id
        ),
        None,
    )

    if course is None:
        raise Http404(
            "진행 중이거나 완료된 수업이 아닙니다."
        )

    try:
        attendance_service = (
            get_attendance_service()
        )

        records, summary = (
            attendance_service
            .get_attendance(
                student.student_id,
                course.assign_id,
            )
        )

    except DatabaseError:
        logger.exception(
            "출결 조회 중 DB 오류"
        )
        return render_database_error(
            request
        )

    grouped = (
        attendance_service
        .split_grouped_records(
            records
        )
    )

    metrics = (
        attendance_service
        .calculate_extended_metrics(
            summary
        )
    )

    upcoming_groups = grouped[
        "upcoming_groups"
    ]
    history_groups = grouped[
        "history_groups"
    ]

    visible_history_groups = (
        history_groups[:8]
    )
    older_history_groups = (
        history_groups[8:]
    )

    return render(
        request,
        "students/attendance_detail.html",
        {
            "page_title": (
                f"{student.name} · "
                f"{course.class_name} 출결"
            ),
            "student": student,
            "course": course,
            "course_mode": (
                "current"
                if course in course_groups["current"]
                else "history"
            ),
            "has_attendance_records": bool(records),
            "summary": summary,
            "metrics": metrics,
            "upcoming_groups": (
                upcoming_groups
            ),
            "visible_history_groups": (
                visible_history_groups
            ),
            "older_history_groups": (
                older_history_groups
            ),
            "older_history_count": (
                len(older_history_groups)
            ),
            # '녹화' 칸을 누르면 녹화 회차와 녹화본 발송 일시를 보여 줍니다(운영팀 10/29).
            "recorded_records": sorted(
                (r for r in records if r.status_kind == "recorded"),
                key=lambda r: r.lesson_date.toordinal() if r.lesson_date else 0,
                reverse=True,
            ),
        },
    )


@login_required
def my_student_detail(
    request: HttpRequest,
) -> HttpResponse:
    student_service = (
        get_student_service()
    )

    student_id = (
        student_service
        .get_student_id_for_username(
            request.user.username
        )
    )

    if student_id is None:
        raise Http404(
            "현재 계정에 연결된 "
            "학생 정보가 없습니다."
        )

    return redirect(
        "students:detail",
        student_id=student_id,
    )
