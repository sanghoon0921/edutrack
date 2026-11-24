from __future__ import annotations

from collections import Counter, OrderedDict
from pathlib import Path

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.utils import DatabaseError
from django.db.models import Q
from django.http import FileResponse, Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.accounts.decorators import class_staff_required, role_required, teacher_required
from apps.accounts.models import User
from apps.content_editor.models import PastedImage
from apps.content_editor.services import sync_pasted_images
from apps.learning.models import LearningGroup
from apps.operations.access import is_admin
from apps.students.selection import build_student_selector_context
from apps.students.services import StudentService

from .forms import AssignmentFilterForm, AssignmentForm, FeedbackForm, SubmissionForm
from .models import Assignment, AssignmentRecipient, Submission
from .services import AssignmentService, UnknownStudentsError


def get_assignment_service() -> AssignmentService:
    return AssignmentService()


def get_student_service() -> StudentService:
    return StudentService()


def _is_admin(user) -> bool:
    return is_admin(user)


def _can_manage_assignment(user, assignment: Assignment) -> bool:
    from apps.lms.access import can_manage
    return can_manage(user,assignment)


def _get_manageable_assignment(request: HttpRequest, assignment_id: int) -> Assignment:
    assignment = get_object_or_404(
        Assignment.objects.select_related("created_by", "group"),
        pk=assignment_id,
    )
    if not _can_manage_assignment(request.user, assignment):
        raise PermissionDenied("이 과제를 관리할 권한이 없습니다.")
    return assignment


def _ensure_teacher_can_modify(request: HttpRequest, assignment: Assignment) -> None:
    if assignment.is_overdue and not _is_admin(request.user):
        raise PermissionDenied("마감된 과제는 강사가 수정하거나 삭제할 수 없습니다.")


def _current_student_id(request: HttpRequest) -> str:
    student_id = get_student_service().get_student_id_for_username(request.user.username)
    if not student_id:
        raise Http404("현재 계정에 연결된 학생번호가 없습니다.")
    return student_id


def _visible_assignment_q() -> Q:
    now = timezone.now()
    return Q(assignment__available_from__isnull=True) | Q(assignment__available_from__lte=now)


def _groups_for_user(user):
    groups = LearningGroup.objects.all()
    if not _is_admin(user):
        from apps.lms.access import staff_group_ids
        groups = groups.filter(pk__in=staff_group_ids(user))
    return groups


@class_staff_required
def assignment_list(request: HttpRequest) -> HttpResponse:
    queryset = (
        Assignment.objects.select_related("created_by", "group")
        .prefetch_related("recipients", "recipients__submission")
    )
    if not _is_admin(request.user):
        from apps.lms.access import staff_scope
        queryset = staff_scope(queryset,request.user)

    form = AssignmentFilterForm(request.GET or None, group_queryset=_groups_for_user(request.user))
    if form.is_valid():
        q = (form.cleaned_data.get("q") or "").strip()
        group = form.cleaned_data.get("group")
        status = form.cleaned_data.get("status")
        date_from = form.cleaned_data.get("date_from")
        date_to = form.cleaned_data.get("date_to")
        now = timezone.now()
        if q:
            queryset = queryset.filter(title__icontains=q)
        if group:
            queryset = queryset.filter(group=group)
        if status == "open":
            queryset = queryset.filter(is_published=True, due_at__gte=now).filter(
                Q(available_from__isnull=True) | Q(available_from__lte=now)
            )
        elif status == "upcoming":
            queryset = queryset.filter(is_published=True, available_from__gt=now)
        elif status == "closed":
            queryset = queryset.filter(due_at__lt=now)
        elif status == "draft":
            queryset = queryset.filter(is_published=False)
        if date_from:
            queryset = queryset.filter(due_at__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(due_at__date__lte=date_to)

    rows = []
    for assignment in queryset.order_by("group__sort_order", "group__title", "due_at", "id"):
        recipients = list(assignment.recipients.all())
        counts = Counter(recipient.status_code for recipient in recipients)
        rows.append(
            {
                "assignment": assignment,
                "recipient_count": len(recipients),
                "submitted_count": counts["SUBMITTED"] + counts["FEEDBACK_COMPLETE"],
                "feedback_count": counts["FEEDBACK_COMPLETE"],
                "teacher_can_edit": _is_admin(request.user) or not assignment.is_overdue,
            }
        )

    grouped: OrderedDict[str, dict] = OrderedDict()
    for row in rows:
        group = row["assignment"].group
        key = str(group.pk) if group else "ungrouped"
        if key not in grouped:
            grouped[key] = {
                "group": group,
                "title": group.title if group else "미분류 과제",
                "rows": [],
            }
        grouped[key]["rows"].append(row)

    return render(
        request,
        "assignments/assignment_list.html",
        {
            "page_title": "과제·채점",
            "assignment_groups": list(grouped.values()),
            "filter_form": form,
            "result_count": len(rows),
        },
    )


@class_staff_required
def assignment_create(request: HttpRequest) -> HttpResponse:
    from apps.lms.integrations import activity_initial
    form = AssignmentForm(request.POST or None, request.FILES or None, user=request.user,initial=activity_initial(request))
    if request.method == "POST" and form.is_valid():
        try:
            assignment = get_assignment_service().save_assignment(form=form, user=request.user)
        except UnknownStudentsError as error:
            form.add_error("student_ids", error)
        except DatabaseError:
            form.add_error(
                "student_ids",
                "학생 정보를 확인하지 못했습니다. 잠시 후 다시 검색해 주세요.",
            )
        else:
            sync_pasted_images(
                text=assignment.description,
                owner=request.user,
                target_type=PastedImage.TargetType.ASSIGNMENT,
                target_id=assignment.pk,
            )
            messages.success(request, "과제를 등록했습니다.")
            return redirect("assignments:list")  # 11/19: 저장하면 과제 목록으로
    return render(
        request,
        "assignments/assignment_form.html",
        {
            "page_title": "과제 등록",
            "form": form,
            "form_mode": "create",
            "student_selector": build_student_selector_context(
                form=form,
                user=request.user,
            ),
        },
    )


@class_staff_required
def assignment_update(request: HttpRequest, assignment_id: int) -> HttpResponse:
    assignment = _get_manageable_assignment(request, assignment_id)
    _ensure_teacher_can_modify(request, assignment)
    form = AssignmentForm(
        request.POST or None,
        request.FILES or None,
        instance=assignment,
        user=request.user,
    )
    if request.method == "POST" and form.is_valid():
        try:
            assignment = get_assignment_service().save_assignment(form=form, user=request.user)
        except UnknownStudentsError as error:
            form.add_error("student_ids", error)
        except DatabaseError:
            form.add_error(
                "student_ids",
                "학생 정보를 확인하지 못했습니다. 잠시 후 다시 검색해 주세요.",
            )
        else:
            sync_pasted_images(
                text=assignment.description,
                owner=request.user,
                target_type=PastedImage.TargetType.ASSIGNMENT,
                target_id=assignment.pk,
            )
            messages.success(request, "과제를 수정했습니다.")
            return redirect("assignments:list")  # 11/19: 저장하면 과제 목록으로
    return render(
        request,
        "assignments/assignment_form.html",
        {
            "page_title": "과제 수정",
            "form": form,
            "form_mode": "update",
            "assignment": assignment,
            "student_selector": build_student_selector_context(
                form=form,
                user=request.user,
                recipients=assignment.recipients.all(),
            ),
        },
    )


@class_staff_required
def assignment_delete(request: HttpRequest, assignment_id: int) -> HttpResponse:
    assignment = _get_manageable_assignment(request, assignment_id)
    _ensure_teacher_can_modify(request, assignment)
    if request.method == "POST":
        title = assignment.title
        assignment.delete()
        messages.success(request, f"‘{title}’ 과제를 삭제했습니다.")
        return redirect("assignments:list")
    return render(
        request,
        "assignments/assignment_confirm_delete.html",
        {"page_title": "과제 삭제", "assignment": assignment},
    )


@class_staff_required
def assignment_detail(request: HttpRequest, assignment_id: int) -> HttpResponse:
    assignment = _get_manageable_assignment(request, assignment_id)
    recipients = list(
        assignment.recipients.select_related("submission", "submission__feedback_by").all()
    )
    status_counts = Counter(recipient.status_code for recipient in recipients)
    return render(
        request,
        "assignments/assignment_detail.html",
        {
            "page_title": assignment.title,
            "assignment": assignment,
            "recipients": recipients,
            "status_counts": status_counts,
            "teacher_can_edit": _is_admin(request.user) or not assignment.is_overdue,
        },
    )


@role_required(User.Role.STUDENT, User.Role.PARENT)
def my_assignments(request: HttpRequest) -> HttpResponse:
    student_id = _current_student_id(request)
    recipients = list(
        AssignmentRecipient.objects.select_related(
            "assignment", "assignment__created_by", "assignment__group", "submission"
        )
        .filter(
            _visible_assignment_q(),
            student_id=student_id,
            assignment__is_published=True,
        )
        .order_by("assignment__due_at", "assignment__id")
    )
    status_counts = Counter(recipient.status_code for recipient in recipients)
    return render(
        request,
        "assignments/my_assignments.html",
        {
            "page_title": "내 과제",
            "student_id": student_id,
            "recipients": recipients,
            "status_counts": status_counts,
        },
    )


@role_required(User.Role.STUDENT, User.Role.PARENT)
def my_assignment_detail(request: HttpRequest, recipient_id: int) -> HttpResponse:
    student_id = _current_student_id(request)
    recipient = get_object_or_404(
        AssignmentRecipient.objects.select_related(
            "assignment",
            "assignment__created_by",
            "assignment__group",
            "submission",
            "submission__feedback_by",
        ).filter(_visible_assignment_q()),
        pk=recipient_id,
        student_id=student_id,
        assignment__is_published=True,
    )
    assignment = recipient.assignment
    try:
        submission = recipient.submission
    except Submission.DoesNotExist:
        submission = Submission(recipient=recipient)

    from django.conf import settings
    can_submit = assignment.can_submit and (request.user.role == User.Role.STUDENT or (request.user.role == User.Role.PARENT and getattr(settings, "LMS_ALLOW_PARENT_SUBMISSION", True)))
    form = SubmissionForm(
        request.POST or None,
        request.FILES or None,
        instance=submission,
        assignment=assignment,
    )
    if request.method == "POST":
        if not can_submit:
            raise PermissionDenied("과제 마감 후에는 제출하거나 재제출할 수 없습니다.")
        if form.is_valid():
            from apps.lms.documents import version_token
            from apps.lms.models import SubmissionFile
            from apps.lms.room_views import audit
            with transaction.atomic():
                AssignmentRecipient.objects.select_for_update().get(pk=recipient.pk)
                previous = Submission.objects.select_for_update().filter(recipient=recipient).first()
                posted_version=form.cleaned_data.get("submission_version")
                if previous and posted_version and version_token(previous)!=posted_version:
                    form.add_error(None,"다른 창에서 제출 내용이 변경되었습니다. 입력 내용을 복사한 뒤 다시 열어 주세요.")
                    return render(request,"assignments/my_assignment_detail.html",{"page_title":assignment.title,"recipient":recipient,"assignment":assignment,"submission":previous,"form":form,"can_submit":can_submit},status=409)
                if not assignment.can_submit:
                    raise PermissionDenied("과제가 마감되었습니다.")
                submission = form.save(commit=False)
                submission.recipient = recipient
                submission.submitted_at = timezone.now()
                submission.feedback = ""
                submission.score = None
                submission.feedback_by = None
                submission.feedback_at = None
                if request.FILES.get("attachment"):
                    submission.attachment_name=Path(request.FILES["attachment"].name).name[:255]
                submission.save()
                for f in form.cleaned_data.get("remove_files",[]):
                    f.delete()  # lms post_delete hook removes the file after commit
                for file in form.cleaned_data.get("uploads",[]):
                    SubmissionFile.objects.create(submission=submission,file=file,original_name=Path(file.name).name[:255])
                audit(request.user,"assignment.submit",submission.pk)
            messages.success(request, "과제를 제출했습니다.")
            return redirect("assignments:my")  # 11/19: 제출하면 내 과제 목록으로

    return render(
        request,
        "assignments/my_assignment_detail.html",
        {
            "page_title": assignment.title,
            "recipient": recipient,
            "assignment": assignment,
            "submission": submission,
            "form": form,
            "can_submit": can_submit,
        },
    )


@class_staff_required
def submission_review(request: HttpRequest, submission_id: int) -> HttpResponse:
    from apps.lms.grade_views import submission_review as enhanced_review
    return enhanced_review(request,submission_id)


@class_staff_required
def assignment_attachment_download(request: HttpRequest, assignment_id: int) -> HttpResponse:
    assignment = get_object_or_404(Assignment, pk=assignment_id)
    if not _can_manage_assignment(request.user, assignment):
        raise PermissionDenied("첨부파일을 열 권한이 없습니다.")
    if not assignment.attachment:
        raise Http404
    return FileResponse(
        assignment.attachment.open("rb"),
        as_attachment=True,
        filename=Path(assignment.attachment.name).name,
    )


@role_required(User.Role.STUDENT, User.Role.PARENT)
def my_assignment_attachment_download(request: HttpRequest, recipient_id: int) -> HttpResponse:
    student_id = _current_student_id(request)
    recipient = get_object_or_404(
        AssignmentRecipient.objects.select_related("assignment").filter(_visible_assignment_q()),
        pk=recipient_id,
        student_id=student_id,
        assignment__is_published=True,
    )
    if not recipient.assignment.attachment:
        raise Http404
    return FileResponse(
        recipient.assignment.attachment.open("rb"),
        as_attachment=True,
        filename=Path(recipient.assignment.attachment.name).name,
    )


@class_staff_required
def submission_attachment_download(request: HttpRequest, submission_id: int) -> HttpResponse:
    submission = get_object_or_404(
        Submission.objects.select_related("recipient__assignment"), pk=submission_id
    )
    if not _can_manage_assignment(request.user, submission.recipient.assignment):
        raise PermissionDenied("제출파일을 열 권한이 없습니다.")
    if not submission.attachment:
        raise Http404
    return FileResponse(
        submission.attachment.open("rb"),
        as_attachment=True,
        filename=Path(submission.attachment.name).name,
    )


@role_required(User.Role.STUDENT, User.Role.PARENT)
def my_submission_attachment_download(request: HttpRequest, recipient_id: int) -> HttpResponse:
    student_id = _current_student_id(request)
    submission = get_object_or_404(
        Submission.objects.select_related("recipient"),
        recipient__pk=recipient_id,
        recipient__student_id=student_id,
    )
    if not submission.attachment:
        raise Http404
    return FileResponse(
        submission.attachment.open("rb"),
        as_attachment=True,
        filename=Path(submission.attachment.name).name,
    )
