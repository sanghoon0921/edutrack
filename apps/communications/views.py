from __future__ import annotations

from pathlib import Path

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from apps.accounts.decorators import teacher_required, class_staff_required
from apps.accounts.models import User
from apps.content_editor.models import PastedImage
from apps.content_editor.services import sync_pasted_images

from .forms import NoticeForm
from .models import (
    Notice,
    NoticeAttachment,
    NoticeInlineImage,
    NoticeRead,
    Notification,
)
from .services import (
    can_view_notice,
    invalidate_notification_header_cache,
    mark_notice_read,
    notification_is_visible_to_user,
    visible_notices_for_user,
    visible_notifications_for_user,
)


def _is_admin(user) -> bool:
    return user.is_superuser or user.role == User.Role.ADMIN


def _can_manage_notice(user, notice: Notice | None = None) -> bool:
    if _is_admin(user):
        return True
    if user.role not in (User.Role.TEACHER, User.Role.TA):
        return False
    return notice is None or notice.created_by_id == user.id


def _ensure_manage_notice(user, notice: Notice | None = None) -> None:
    if not _can_manage_notice(user, notice):
        raise PermissionDenied("본인이 등록한 공지만 수정할 수 있습니다.")


def _save_notice_uploads(notice: Notice, form: NoticeForm, request: HttpRequest) -> None:
    remove_attachment_ids = request.POST.getlist("remove_attachment_ids")
    remove_image_ids = request.POST.getlist("remove_inline_image_ids")
    if remove_attachment_ids:
        notice.attachments.filter(pk__in=remove_attachment_ids).delete()
    if remove_image_ids:
        notice.inline_images.filter(pk__in=remove_image_ids).delete()

    for uploaded in form.cleaned_data.get("attachments", []):
        NoticeAttachment.objects.create(
            notice=notice,
            file=uploaded,
            original_name=Path(uploaded.name).name,
            size=uploaded.size,
        )
    for uploaded in form.cleaned_data.get("inline_images", []):
        NoticeInlineImage.objects.create(
            notice=notice,
            file=uploaded,
            original_name=Path(uploaded.name).name,
            size=uploaded.size,
        )


NOTICE_KINDS = {"academy": Notice.Category.ACADEMY, "class": Notice.Category.CLASS}


@login_required
def notice_list(request: HttpRequest) -> HttpResponse:
    kind = request.GET.get("kind", "")
    notices = visible_notices_for_user(request.user)
    if kind in NOTICE_KINDS:
        notices = notices.filter(category=NOTICE_KINDS[kind])
    else:
        kind = ""
    notices = list(notices.select_related("group", "created_by"))
    read_notice_ids = set(
        NoticeRead.objects.filter(
            user=request.user,
            notice_id__in=[notice.pk for notice in notices],
        ).values_list("notice_id", flat=True)
    )
    for notice in notices:
        notice.is_read_by_user = notice.pk in read_notice_ids
    # 공지사항은 학원 전체 공지가 먼저, 반에 보낸 공지는 반별로 묶어 아래에(운영팀 10/29).
    class_notices = {}
    for notice in notices:
        if notice.group_id:
            class_notices.setdefault(notice.group.title, []).append(notice)
    return render(
        request,
        "communications/notice_list.html",
        {
            "page_title": "공지사항",
            "notices": [notice for notice in notices if not notice.group_id],
            "class_notices": class_notices,
            "kind": kind,
            "can_manage_notices": request.user.role in {User.Role.ADMIN, User.Role.TEACHER} or request.user.is_superuser,
        },
    )


@login_required
def notice_detail(request: HttpRequest, notice_id: int) -> HttpResponse:
    notice = get_object_or_404(
        Notice.objects.select_related("created_by", "group").prefetch_related("attachments", "inline_images"),
        pk=notice_id,
    )
    if not can_view_notice(request.user, notice):
        if not _can_manage_notice(request.user, notice):
            raise PermissionDenied("이 공지를 확인할 권한이 없습니다.")
    mark_notice_read(request.user, notice)
    return render(
        request,
        "communications/notice_detail.html",
        {"page_title": notice.title, "notice": notice, "can_manage_notice": _can_manage_notice(request.user, notice)},
    )


@class_staff_required
def notice_manage(request: HttpRequest) -> HttpResponse:
    notices = Notice.objects.select_related("created_by", "group").all()
    if not _is_admin(request.user):
        notices = notices.filter(created_by=request.user)
    return render(
        request,
        "communications/notice_manage.html",
        {
            "page_title": "공지 관리",
            "notices": notices,
            "total_count": notices.count(),
            "published_count": notices.filter(is_published=True).count(),
            "pinned_count": notices.filter(is_pinned=True).count(),
            "draft_count": notices.filter(is_published=False).count(),
        },
    )


@class_staff_required
def notice_create(request: HttpRequest) -> HttpResponse:
    form = NoticeForm(request.POST or None, request.FILES or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        notice = form.save(commit=False)
        notice.created_by = request.user
        notice.save()
        _save_notice_uploads(notice, form, request)
        sync_pasted_images(
            text=notice.content,
            owner=request.user,
            target_type=PastedImage.TargetType.NOTICE,
            target_id=notice.pk,
        )
        messages.success(request, "공지사항을 등록했습니다.")
        return redirect("communications:notice-manage")
    return render(
        request,
        "communications/notice_form.html",
        {"page_title": "공지 등록", "form": form, "form_mode": "create"},
    )


@class_staff_required
def notice_update(request: HttpRequest, notice_id: int) -> HttpResponse:
    notice = get_object_or_404(
        Notice.objects.prefetch_related("attachments", "inline_images"),
        pk=notice_id,
    )
    _ensure_manage_notice(request.user, notice)
    form = NoticeForm(
        request.POST or None,
        request.FILES or None,
        instance=notice,
        user=request.user,
    )
    if request.method == "POST" and form.is_valid():
        notice = form.save()
        _save_notice_uploads(notice, form, request)
        sync_pasted_images(
            text=notice.content,
            owner=request.user,
            target_type=PastedImage.TargetType.NOTICE,
            target_id=notice.pk,
        )
        messages.success(request, "공지사항을 수정했습니다.")
        return redirect("communications:notice-manage")
    return render(
        request,
        "communications/notice_form.html",
        {
            "page_title": "공지 수정",
            "form": form,
            "form_mode": "update",
            "notice": notice,
        },
    )


@class_staff_required
def notice_delete(request: HttpRequest, notice_id: int) -> HttpResponse:
    notice = get_object_or_404(Notice, pk=notice_id)
    _ensure_manage_notice(request.user, notice)
    if request.method == "POST":
        title = notice.title
        notice.delete()
        messages.success(request, f"‘{title}’ 공지를 삭제했습니다.")
        return redirect("communications:notice-manage")
    return render(
        request,
        "communications/notice_confirm_delete.html",
        {"page_title": "공지 삭제", "notice": notice},
    )


@login_required
def notice_attachment_download(
    request: HttpRequest,
    notice_id: int,
    attachment_id: int,
) -> HttpResponse:
    notice = get_object_or_404(Notice, pk=notice_id)
    if not can_view_notice(request.user, notice) and not _can_manage_notice(request.user, notice):
        raise PermissionDenied("첨부파일을 받을 권한이 없습니다.")
    attachment = get_object_or_404(NoticeAttachment, pk=attachment_id, notice=notice)
    return FileResponse(
        attachment.file.open("rb"),
        as_attachment=True,
        filename=attachment.original_name,
    )


@login_required
def notice_inline_image(
    request: HttpRequest,
    notice_id: int,
    image_id: int,
) -> HttpResponse:
    notice = get_object_or_404(Notice, pk=notice_id)
    if not can_view_notice(request.user, notice) and not _can_manage_notice(request.user, notice):
        raise PermissionDenied("이미지를 볼 권한이 없습니다.")
    image = get_object_or_404(NoticeInlineImage, pk=image_id, notice=notice)
    response = FileResponse(image.file.open("rb"), as_attachment=False)
    response["Content-Disposition"] = f'inline; filename="{image.original_name}"'
    return response


@login_required
def notification_list(request: HttpRequest) -> HttpResponse:
    notifications = visible_notifications_for_user(request.user)
    return render(
        request,
        "communications/notification_list.html",
        {
            "page_title": "알림",
            "notifications": notifications,
            "unread_count": sum(
                1 for notification in notifications if not notification.is_read
            ),
        },
    )


@login_required
def notification_open(request: HttpRequest, notification_id: int) -> HttpResponse:
    if request.method != "POST":
        raise Http404
    notification = get_object_or_404(
        Notification,
        pk=notification_id,
        user=request.user,
    )

    # 테스트 계정의 연결 학생이 바뀌었거나 대상 배정이 취소된 알림은
    # 상세 URL로 보내지 않고 안전하게 읽음 처리한 뒤 목록으로 돌아갑니다.
    if not notification_is_visible_to_user(request.user, notification):
        notification.mark_read()
        return redirect("communications:notification-list")

    notification.mark_read()
    target = notification.target_url
    if target and url_has_allowed_host_and_scheme(
        target,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(target)
    return redirect("communications:notification-list")


@login_required
def notification_mark_all_read(request: HttpRequest) -> HttpResponse:
    if request.method != "POST":
        raise Http404
    updated = Notification.objects.filter(user=request.user, is_read=False).update(
        is_read=True,
        read_at=timezone.now(),
    )
    if updated:
        invalidate_notification_header_cache(request.user.id)
    messages.success(request, "모든 알림을 읽음 처리했습니다.")
    return redirect("communications:notification-list")
