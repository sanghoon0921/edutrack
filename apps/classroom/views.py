from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Max
from django.db.utils import DatabaseError
from django.http import FileResponse, Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.decorators import teacher_required
from apps.accounts.models import User
from apps.operations.access import is_admin, learner_student_ids
from apps.students.selection import build_student_selector_context

from .forms import CourseBoardForm, CourseCategoryForm, CourseResourceForm
from .models import CourseBoard, CourseCategory, CourseResource
from .services import UnknownStudentsError, can_manage_board, ensure_manage_board, save_board


def _staff_user(user) -> bool:
    return bool(is_admin(user) or user.role == User.Role.TEACHER)


def _can_view_board(user, board: CourseBoard) -> bool:
    if can_manage_board(user, board):
        return True
    if not board.is_published:
        return False
    student_ids = learner_student_ids(user)
    return bool(student_ids and board.recipients.filter(student_id__in=student_ids).exists())


def _viewable_board(request: HttpRequest, board_id: int) -> CourseBoard:
    board = get_object_or_404(
        CourseBoard.objects.select_related("created_by").prefetch_related(
            "recipients", "categories__resources__created_by"
        ),
        pk=board_id,
    )
    if not _can_view_board(request.user, board):
        raise PermissionDenied("이 과목 자료를 확인할 권한이 없습니다.")
    return board


def _manageable_board(request: HttpRequest, board_id: int) -> CourseBoard:
    board = get_object_or_404(CourseBoard.objects.select_related("created_by"), pk=board_id)
    ensure_manage_board(request.user, board)
    return board


@login_required
def board_list(request: HttpRequest) -> HttpResponse:
    if _staff_user(request.user):
        boards = CourseBoard.objects.select_related("created_by").prefetch_related(
            "recipients", "categories__resources"
        )
        if not is_admin(request.user):
            boards = boards.filter(created_by=request.user)
        page_title = "과목 자료 관리"
        manage_mode = True
    else:
        student_ids = learner_student_ids(request.user)
        boards = (
            CourseBoard.objects.select_related("created_by")
            .prefetch_related("categories__resources")
            .filter(
                is_published=True,
                recipients__student_id__in=student_ids,
            )
            .distinct()
        )
        page_title = "수업 자료"
        manage_mode = False

    rows = []
    for board in boards:
        rows.append(
            {
                "board": board,
                "recipient_count": board.recipients.count() if manage_mode else None,
                "category_count": board.categories.count(),
                "resource_count": sum(category.resources.count() for category in board.categories.all()),
            }
        )
    return render(
        request,
        "classroom/board_list.html",
        {
            "page_title": page_title,
            "rows": rows,
            "manage_mode": manage_mode,
        },
    )


@teacher_required
def board_create(request: HttpRequest) -> HttpResponse:
    form = CourseBoardForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            board = save_board(form=form, user=request.user)
        except UnknownStudentsError as error:
            form.add_error("student_ids", error)
        except DatabaseError:
            form.add_error(
                "student_ids",
                "학생 정보를 확인하지 못했습니다. 잠시 후 다시 검색해 주세요.",
            )
        else:
            messages.success(request, "과목 자료 공간을 만들었습니다.")
            return redirect("classroom:board-detail", board_id=board.pk)
    return render(
        request,
        "classroom/board_form.html",
        {
            "page_title": "과목 자료 등록",
            "form": form,
            "form_mode": "create",
            "student_selector": build_student_selector_context(form=form, user=request.user),
        },
    )


@teacher_required
def board_update(request: HttpRequest, board_id: int) -> HttpResponse:
    board = _manageable_board(request, board_id)
    form = CourseBoardForm(request.POST or None, instance=board, user=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            board = save_board(form=form, user=request.user)
        except UnknownStudentsError as error:
            form.add_error("student_ids", error)
        except DatabaseError:
            form.add_error(
                "student_ids",
                "학생 정보를 확인하지 못했습니다. 잠시 후 다시 검색해 주세요.",
            )
        else:
            messages.success(request, "과목 자료 설정을 저장했습니다.")
            return redirect("classroom:board-detail", board_id=board.pk)
    return render(
        request,
        "classroom/board_form.html",
        {
            "page_title": "과목 자료 수정",
            "form": form,
            "form_mode": "update",
            "board": board,
            "student_selector": build_student_selector_context(
                form=form,
                user=request.user,
                recipients=board.recipients.all(),
            ),
        },
    )


@teacher_required
@require_POST
def board_delete(request: HttpRequest, board_id: int) -> HttpResponse:
    board = _manageable_board(request, board_id)
    title = board.title
    board.delete()
    messages.success(request, f"‘{title}’ 과목 자료를 삭제했습니다.")
    return redirect("classroom:board-list")


@login_required
def board_detail(request: HttpRequest, board_id: int) -> HttpResponse:
    board = _viewable_board(request, board_id)
    manage_mode = can_manage_board(request.user, board)
    categories = []
    for category in board.categories.all():
        if not manage_mode and not category.is_published:
            continue
        resources = [
            resource
            for resource in category.resources.all()
            if manage_mode or resource.is_published
        ]
        categories.append({"category": category, "resources": resources})
    return render(
        request,
        "classroom/board_detail.html",
        {
            "page_title": board.title,
            "board": board,
            "categories": categories,
            "manage_mode": manage_mode,
        },
    )


@teacher_required
def category_create(request: HttpRequest, board_id: int) -> HttpResponse:
    board = _manageable_board(request, board_id)
    form = CourseCategoryForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        category = form.save(commit=False)
        category.board = board
        highest_order = board.categories.aggregate(value=Max("sort_order"))["value"] or 0
        category.sort_order = highest_order + 10
        category.is_published = True
        category.save()
        messages.success(request, "카테고리를 추가했습니다.")
        return redirect("classroom:board-detail", board_id=board.pk)
    return render(
        request,
        "classroom/category_form.html",
        {"page_title": "카테고리 추가", "board": board, "form": form},
    )


@teacher_required
def category_update(request: HttpRequest, board_id: int, category_id: int) -> HttpResponse:
    board = _manageable_board(request, board_id)
    category = get_object_or_404(CourseCategory, pk=category_id, board=board)
    form = CourseCategoryForm(request.POST or None, instance=category)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "카테고리를 수정했습니다.")
        return redirect("classroom:board-detail", board_id=board.pk)
    return render(
        request,
        "classroom/category_form.html",
        {"page_title": "카테고리 수정", "board": board, "category": category, "form": form},
    )


@teacher_required
@require_POST
def category_delete(request: HttpRequest, board_id: int, category_id: int) -> HttpResponse:
    board = _manageable_board(request, board_id)
    category = get_object_or_404(CourseCategory, pk=category_id, board=board)
    title = category.title
    category.delete()
    messages.success(request, f"‘{title}’ 카테고리와 안의 자료를 삭제했습니다.")
    return redirect("classroom:board-detail", board_id=board.pk)


def _save_resource(form: CourseResourceForm, *, category: CourseCategory, user) -> CourseResource:
    resource = form.save(commit=False)
    resource.category = category
    if not resource.pk:
        resource.created_by = user
        highest_order = category.resources.aggregate(value=Max("sort_order"))["value"] or 0
        resource.sort_order = highest_order + 10
    resource.is_published = True

    previous_file_name = ""
    previous_storage = None
    if resource.pk:
        previous = CourseResource.objects.filter(pk=resource.pk).only("file").first()
        if previous and previous.file:
            previous_file_name = previous.file.name
            previous_storage = previous.file.storage

    uploaded = form.cleaned_data.get("file")
    if resource.resource_type == CourseResource.Type.LINK:
        resource.file = ""
        resource.original_name = ""
        resource.size = 0
    elif uploaded:
        resource.original_name = Path(uploaded.name).name[:255]
        resource.size = uploaded.size
    resource.save()

    current_file_name = resource.file.name if resource.file else ""
    if previous_file_name and previous_file_name != current_file_name and previous_storage:
        transaction.on_commit(
            lambda storage=previous_storage, name=previous_file_name: storage.delete(name)
        )
    return resource


def _requested_resource_type(request: HttpRequest, *, fallback: str = CourseResource.Type.PDF) -> str:
    raw = (request.GET.get("type") or fallback or CourseResource.Type.PDF).strip().upper()
    return raw if raw in CourseResource.Type.values else CourseResource.Type.PDF


def _resource_page_title(resource_type: str, *, update: bool = False) -> str:
    action = "수정" if update else "등록"
    return {
        CourseResource.Type.PDF: f"PDF {action}",
        CourseResource.Type.FILE: f"일반 파일 {action}",
        CourseResource.Type.LINK: f"외부 링크 {action}",
    }.get(resource_type, f"자료 {action}")


@teacher_required
def resource_create(request: HttpRequest, board_id: int, category_id: int) -> HttpResponse:
    board = _manageable_board(request, board_id)
    category = get_object_or_404(CourseCategory, pk=category_id, board=board)
    requested_type = _requested_resource_type(request)
    form = CourseResourceForm(
        request.POST or None,
        request.FILES or None,
        initial_type=requested_type,
    )
    selected_type = (
        str(form.data.get("resource_type") or requested_type).strip().upper()
        if form.is_bound
        else requested_type
    )
    if selected_type not in CourseResource.Type.values:
        selected_type = CourseResource.Type.PDF

    if request.method == "POST" and form.is_valid():
        resource = _save_resource(form, category=category, user=request.user)
        messages.success(request, f"{resource.get_resource_type_display()} 자료를 등록했습니다.")
        return redirect("classroom:resource-detail", resource_id=resource.pk)
    return render(
        request,
        "classroom/resource_form.html",
        {
            "page_title": _resource_page_title(selected_type),
            "board": board,
            "category": category,
            "form": form,
            "form_mode": "create",
            "selected_resource_type": selected_type,
            "resource_max_mb": max(1, int(getattr(settings, "COURSE_RESOURCE_MAX_MB", 25))),
        },
    )


@teacher_required
def resource_update(request: HttpRequest, resource_id: int) -> HttpResponse:
    resource = get_object_or_404(
        CourseResource.objects.select_related("category__board"), pk=resource_id
    )
    board = resource.category.board
    ensure_manage_board(request.user, board)
    form = CourseResourceForm(
        request.POST or None,
        request.FILES or None,
        instance=resource,
        initial_type=resource.resource_type,
    )
    selected_type = (
        str(form.data.get("resource_type") or resource.resource_type).strip().upper()
        if form.is_bound
        else resource.resource_type
    )
    if selected_type not in CourseResource.Type.values:
        selected_type = resource.resource_type

    if request.method == "POST" and form.is_valid():
        resource = _save_resource(form, category=resource.category, user=request.user)
        messages.success(request, "자료를 수정했습니다.")
        return redirect("classroom:resource-detail", resource_id=resource.pk)
    return render(
        request,
        "classroom/resource_form.html",
        {
            "page_title": _resource_page_title(selected_type, update=True),
            "board": board,
            "category": resource.category,
            "resource": resource,
            "form": form,
            "form_mode": "update",
            "selected_resource_type": selected_type,
            "resource_max_mb": max(1, int(getattr(settings, "COURSE_RESOURCE_MAX_MB", 25))),
        },
    )


@teacher_required
@require_POST
def resource_delete(request: HttpRequest, resource_id: int) -> HttpResponse:
    resource = get_object_or_404(
        CourseResource.objects.select_related("category__board"), pk=resource_id
    )
    board = resource.category.board
    ensure_manage_board(request.user, board)
    title = resource.title
    resource.delete()
    messages.success(request, f"‘{title}’ 자료를 삭제했습니다.")
    return redirect("classroom:board-detail", board_id=board.pk)


def _viewable_resource(request: HttpRequest, resource_id: int) -> CourseResource:
    resource = get_object_or_404(
        CourseResource.objects.select_related("category__board", "created_by"),
        pk=resource_id,
    )
    board = resource.category.board
    if not _can_view_board(request.user, board):
        raise PermissionDenied("이 자료를 볼 권한이 없습니다.")
    if not can_manage_board(request.user, board):
        if not resource.is_published or not resource.category.is_published:
            raise PermissionDenied("공개되지 않은 자료입니다.")
    return resource


@login_required
def resource_detail(request: HttpRequest, resource_id: int) -> HttpResponse:
    resource = _viewable_resource(request, resource_id)
    board = resource.category.board
    return render(
        request,
        "classroom/resource_detail.html",
        {
            "page_title": resource.title,
            "resource": resource,
            "board": board,
            "manage_mode": can_manage_board(request.user, board),
        },
    )


@login_required
def resource_preview(request: HttpRequest, resource_id: int) -> HttpResponse:
    resource = _viewable_resource(request, resource_id)
    if not resource.is_pdf or not resource.file:
        raise Http404
    preview_name = resource.original_name or f"{resource.title}.pdf"
    response = FileResponse(
        resource.file.open("rb"),
        as_attachment=False,
        filename=Path(preview_name).name,
        content_type="application/pdf",
    )
    response["X-Frame-Options"] = "SAMEORIGIN"
    response["Cache-Control"] = "private, max-age=300"
    return response


@login_required
def resource_download(request: HttpRequest, resource_id: int) -> HttpResponse:
    resource = _viewable_resource(request, resource_id)
    if resource.resource_type == CourseResource.Type.LINK or not resource.file:
        raise Http404
    return FileResponse(
        resource.file.open("rb"),
        as_attachment=True,
        filename=resource.original_name or Path(resource.file.name).name,
    )
