from __future__ import annotations

import logging

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.utils import DatabaseError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render

from apps.accounts.decorators import (
    class_staff_required,
    admin_required,
    student_required,
    teacher_required,
)
from apps.accounts.models import User
from apps.accounts.student_links import get_primary_student_no

from apps.students.course_services import CourseService
from apps.students.services import StudentService
from apps.operations.models import TeacherStudentAccess

from .class_catalog import ClassCatalogFilters, ClassCatalogService
from .forms import ClassCatalogSearchForm


logger = logging.getLogger(__name__)


def get_class_catalog_service() -> ClassCatalogService:
    return ClassCatalogService()


def _assigned_student_rows(user) -> list[dict[str, str]]:
    """담당 학생 연결은 기본 DB에서만 읽어 외부 DB 지연을 만들지 않습니다."""
    if getattr(user, "role", None) != User.Role.TEACHER:
        return []
    return [
        {
            "student_no": str(access.student_no).strip(),
            "student_name": (str(access.student_name or "").strip() or f"학생 {access.student_no}"),
        }
        for access in TeacherStudentAccess.objects.filter(
            teacher=user,
            is_active=True,
        ).order_by("student_name", "student_no", "id")
    ]


@login_required
def home(
    request: HttpRequest,
) -> HttpResponse:
    user = request.user
    is_parent = user.role == User.Role.PARENT

    if (
        user.is_superuser
        or user.role == User.Role.ADMIN
    ):
        template_name = "dashboard/admin.html"
        page_title = "관리자 홈"
    elif user.role == User.Role.TEACHER:
        template_name = "dashboard/teacher.html"
        page_title = "강사 홈"
    elif user.role == User.Role.TA:
        template_name = "dashboard/ta.html"
        page_title = "TA 홈"
    elif is_parent:
        # 학부모도 6단계 학생 홈 디자인을 그대로 사용합니다.
        template_name = "dashboard/student.html"
        page_title = "학부모 홈"
    else:
        template_name = "dashboard/student.html"
        page_title = "학생 홈"

    extra_context = {}
    if user.role == User.Role.STUDENT and not user.is_superuser:
        from .student_home import home_context
        extra_context = home_context(user)
    elif is_parent and not user.is_superuser:
        # 학부모도 학생 홈과 같은 구성(11/10): 연결된 자녀의 마감·공지
        from apps.accounts.student_links import get_linked_student_nos
        from .student_home import home_context
        extra_context = home_context(user, ids=get_linked_student_nos(user))
    elif user.role == User.Role.TEACHER and not user.is_superuser:
        from .teacher_home import home_context
        extra_context = home_context(user)
    elif user.is_superuser or user.role == User.Role.ADMIN:
        from .admin_home import home_context
        extra_context = home_context(user)
    elif user.role == User.Role.TA:
        from apps.reports.formats import FORMS
        from apps.reports.models import ReportBatch
        from apps.reports.views import report_group_ids
        batches = (ReportBatch.objects.filter(group_id__in=report_group_ids(user)).select_related('group')
                   .order_by('-period_end', 'group__title')[:30])
        extra_context = {"ta_batches": [{"batch": b, "form_label": FORMS.get(b.form, {}).get("label", b.form)} for b in batches]}

    return render(
        request,
        template_name,
        {
            "page_title": page_title,
            "display_name": user.effective_name,
            "is_parent": is_parent,
            **extra_context,
        },
    )


def _placeholder(
    request: HttpRequest,
    *,
    title: str,
    description: str,
    category: str,
) -> HttpResponse:
    return render(
        request,
        "dashboard/placeholder.html",
        {
            "page_title": title,
            "section_title": title,
            "section_description": description,
            "section_category": category,
        },
    )


@admin_required
def admin_students(
    request: HttpRequest,
) -> HttpResponse:
    # 예전 빈 안내 화면 대신 실제 학생 검색으로 보냅니다.
    return redirect("students:list")


@admin_required
def admin_classes(
    request: HttpRequest,
) -> HttpResponse:
    form = ClassCatalogSearchForm(request.GET)
    page_number = request.GET.get("page", "1")

    try:
        page_number_int = max(1, int(page_number))
    except (TypeError, ValueError):
        page_number_int = 1

    filters = ClassCatalogFilters()
    if form.is_valid():
        filters = ClassCatalogFilters(
            start_date=form.cleaned_data.get("start_date"),
            end_date=form.cleaned_data.get("end_date"),
            status=form.cleaned_data.get("status", ""),
            learning_method=form.cleaned_data.get("learning_method", ""),
            keyword=form.cleaned_data.get("q", ""),
        )

    classes = []
    total_count = 0
    database_error = False

    if form.is_valid():
        try:
            classes, total_count = get_class_catalog_service().search(
                filters,
                page=page_number_int,
                page_size=30,
            )
        except DatabaseError:
            logger.exception("관리자 수업 검색 중 인트라넷 DB 오류가 발생했습니다.")
            database_error = True

    paginator = Paginator(range(total_count), 30)
    page_obj = paginator.get_page(page_number_int)

    query_params = request.GET.copy()
    query_params.pop("page", None)

    return render(
        request,
        "dashboard/admin_class_catalog.html",
        {
            "page_title": "수업 관리",
            "form": form,
            "classes": classes,
            "result_count": total_count,
            "page_obj": page_obj,
            "query_string": query_params.urlencode(),
            "database_error": database_error,
        },
    )


@admin_required
def admin_assignments(
    request: HttpRequest,
) -> HttpResponse:
    return _placeholder(
        request,
        title="과제·채점",
        description=(
            "과제 등록, 제출 확인, 채점 기능을 관리합니다."
        ),
        category="관리자",
    )


@admin_required
def admin_operations(
    request: HttpRequest,
) -> HttpResponse:
    # 예전 빈 안내 화면 대신 실제 공지 관리로 보냅니다.
    return redirect("communications:notice-manage")


@teacher_required
def teacher_classes(
    request: HttpRequest,
) -> HttpResponse:
    assigned_students = _assigned_student_rows(request.user)
    return render(
        request,
        "dashboard/teacher_classes.html",
        {
            "page_title": "담당 수업",
            "assigned_students": assigned_students,
            "assigned_count": len(assigned_students),
            "teacher_scope": request.user.role == User.Role.TEACHER,
        },
    )


@teacher_required
def teacher_students(
    request: HttpRequest,
) -> HttpResponse:
    assigned_students = _assigned_student_rows(request.user)
    return render(
        request,
        "dashboard/teacher_students.html",
        {
            "page_title": "담당 학생",
            "assigned_students": assigned_students,
            "assigned_count": len(assigned_students),
            "teacher_scope": request.user.role == User.Role.TEACHER,
        },
    )


@teacher_required
def teacher_assignments(
    request: HttpRequest,
) -> HttpResponse:
    return _placeholder(
        request,
        title="과제·채점",
        description=(
            "과제 등록, 제출물 확인, 채점 대기를 관리합니다."
        ),
        category="강사",
    )


@class_staff_required  # 11/19: TA도 담당 반 학생의 DSG
def teacher_grades(request: HttpRequest) -> HttpResponse:
    from .grade_hub import teacher_grades as live_grades
    return live_grades(request)


def _linked_student_id_for_dashboard(user) -> str | None:
    linked = get_primary_student_no(user)
    if linked:
        return str(linked).strip()

    account_map = getattr(settings, "STUDENT_ACCOUNT_MAP", {})
    if isinstance(account_map, dict):
        mapped = str(account_map.get(user.username, "")).strip()
        if mapped:
            return mapped

    demo_usernames = {
        getattr(settings, "DEMO_STUDENT_USERNAME", "student_test"),
        getattr(settings, "DEMO_PARENT_USERNAME", "parent_test"),
    }
    if user.username in demo_usernames:
        fallback = str(getattr(settings, "STUDENT_TEST_STUDENT_ID", "6333")).strip()
        if fallback:
            return fallback

    if user.username.isdigit():
        return user.username
    return None


def _learner_page_base_context(request: HttpRequest, *, title: str) -> dict:
    return {
        "page_title": title,
        "is_parent": request.user.role == User.Role.PARENT,
        "student": None,
        "student_id": None,
        "linked_student_missing": False,
        "unlinked_account": False,
    }


def _load_learner_student_context(
    request: HttpRequest,
    *,
    title: str,
) -> tuple[dict, bool]:
    context = _learner_page_base_context(request, title=title)
    student_id = _linked_student_id_for_dashboard(request.user)
    if not student_id:
        context["unlinked_account"] = True
        return context, False

    context["student_id"] = student_id
    student = StudentService().get_student(student_id)
    if student is None:
        context["linked_student_missing"] = True
        return context, False

    context["student"] = student
    return context, True


def _load_learner_course_context(
    request: HttpRequest,
    *,
    title: str,
) -> tuple[dict, bool]:
    context, loaded = _load_learner_student_context(
        request,
        title=title,
    )
    if not loaded:
        return context, False

    context["course_groups"] = CourseService().get_student_course_groups(
        context["student_id"]
    )
    return context, True


def _render_learner_database_error(request: HttpRequest) -> HttpResponse:
    logger.exception("학생 학습 화면 조회 중 인트라넷 DB 오류가 발생했습니다.")
    return render(
        request,
        "errors/503.html",
        {"page_title": "인트라넷 연결 오류"},
        status=503,
    )


@student_required
def student_classes(
    request: HttpRequest,
) -> HttpResponse:
    is_parent = request.user.role == User.Role.PARENT
    title = "자녀 수업" if is_parent else "내 수업"
    try:
        context, loaded = _load_learner_course_context(request, title=title)
    except DatabaseError:
        return _render_learner_database_error(request)

    if loaded:
        groups = context["course_groups"]
        context.update(
            {
                "current_courses": groups["current"],
                "upcoming_courses": groups["upcoming"],
                "completed_courses": groups["completed"],
                "course_count": sum(len(items) for items in groups.values()),
            }
        )
    return render(request, "dashboard/student_classes.html", context)


@student_required
def student_attendance(
    request: HttpRequest,
) -> HttpResponse:
    is_parent = request.user.role == User.Role.PARENT
    title = "자녀 출결" if is_parent else "내 출결"
    try:
        context, loaded = _load_learner_course_context(request, title=title)
    except DatabaseError:
        return _render_learner_database_error(request)

    if loaded:
        groups = context["course_groups"]
        if groups["current"]:
            visible_courses = groups["current"]
            course_mode = "current"
        elif groups["completed"]:
            visible_courses = groups["completed"]
            course_mode = "history"
        else:
            visible_courses = []
            course_mode = "empty"
        context.update(
            {
                "visible_courses": visible_courses,
                "course_mode": course_mode,
            }
        )
    return render(request, "dashboard/student_attendance.html", context)


@student_required
def student_assignments(
    request: HttpRequest,
) -> HttpResponse:
    is_parent = (
        request.user.role
        == User.Role.PARENT
    )

    return _placeholder(
        request,
        title=(
            "자녀 과제"
            if is_parent
            else "내 과제"
        ),
        description=(
            "연결된 학생의 마감일별 과제와 제출 상태를 표시합니다."
            if is_parent
            else "마감일별 과제와 제출 상태를 표시합니다."
        ),
        category=(
            "학부모"
            if is_parent
            else "학생"
        ),
    )


@student_required
def student_grades(
    request: HttpRequest,
) -> HttpResponse:
    is_parent = request.user.role == User.Role.PARENT
    title = "자녀 성적" if is_parent else "내 성적"
    try:
        context, _ = _load_learner_student_context(request, title=title)
    except DatabaseError:
        return _render_learner_database_error(request)

    # 성적 화면은 인트라넷 수업 이력과 분리하고 DSG 시험 결과만 표시합니다.
    # 불필요한 CourseService 조회도 실행하지 않습니다.
    return render(request, "dashboard/student_grades.html", context)


def permission_denied(
    request,
    exception,
):
    return render(
        request,
        "errors/403.html",
        status=403,
    )


def page_not_found(
    request,
    exception,
):
    return render(
        request,
        "errors/404.html",
        status=404,
    )
