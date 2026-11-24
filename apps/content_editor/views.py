from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404, HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.accounts.decorators import teacher_required
from apps.accounts.models import User
from apps.operations.access import is_admin, learner_student_ids

from .models import PastedImage


_IMAGE_SIGNATURES = (
    ("image/png", lambda data: data.startswith(b"\x89PNG\r\n\x1a\n")),
    ("image/jpeg", lambda data: data.startswith(b"\xff\xd8\xff")),
    ("image/gif", lambda data: data.startswith((b"GIF87a", b"GIF89a"))),
    (
        "image/webp",
        lambda data: len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP",
    ),
)


def _detect_image_type(uploaded) -> str | None:
    position = uploaded.tell() if hasattr(uploaded, "tell") else 0
    head = uploaded.read(32)
    if hasattr(uploaded, "seek"):
        uploaded.seek(position)
    for content_type, predicate in _IMAGE_SIGNATURES:
        if predicate(head):
            return content_type
    return None


@teacher_required
@require_POST
def upload_pasted_image(request: HttpRequest) -> JsonResponse:
    uploaded = request.FILES.get("image")
    if uploaded is None:
        return JsonResponse({"message": "붙여넣을 이미지가 없습니다."}, status=400)

    max_mb = int(getattr(settings, "PASTED_IMAGE_MAX_MB", 8))
    if uploaded.size > max_mb * 1024 * 1024:
        return JsonResponse(
            {"message": f"이미지는 한 장당 {max_mb}MB 이하만 가능합니다."},
            status=400,
        )

    detected = _detect_image_type(uploaded)
    if detected is None:
        return JsonResponse(
            {"message": "PNG, JPG, GIF, WEBP 이미지만 붙여넣을 수 있습니다."},
            status=400,
        )

    original_name = Path(uploaded.name or "pasted-image").name[:255]
    image = PastedImage.objects.create(
        owner=request.user,
        image=uploaded,
        original_name=original_name,
        content_type=detected,
        size=uploaded.size,
    )
    return JsonResponse(
        {
            "token": image.token_markup,
            "preview_url": request.build_absolute_uri(
                reverse("content-editor:image", kwargs={"token": image.token})
            ),
            "name": image.original_name,
            "size": image.size,
        },
        status=201,
    )


def _can_access_target(user, image: PastedImage) -> bool:
    if is_admin(user) or image.owner_id == user.id:
        return True
    if image.target_type == PastedImage.TargetType.DRAFT or image.target_id is None:
        return False

    if image.target_type == PastedImage.TargetType.NOTICE:
        from apps.communications.models import Notice
        from apps.communications.services import can_view_notice

        notice = Notice.objects.filter(pk=image.target_id).first()
        return bool(notice and can_view_notice(user, notice))

    student_ids = learner_student_ids(user)

    if image.target_type == PastedImage.TargetType.ASSIGNMENT:
        from apps.assignments.models import Assignment

        assignment = Assignment.objects.filter(pk=image.target_id).first()
        if assignment is None:
            return False
        if user.role == User.Role.TEACHER:
            return assignment.created_by_id == user.id
        return bool(
            assignment.is_available
            and assignment.recipients.filter(student_id__in=student_ids).exists()
        )

    if image.target_type == PastedImage.TargetType.DISCUSSION:
        from apps.learning.models import Discussion

        discussion = Discussion.objects.filter(pk=image.target_id).first()
        if discussion is None:
            return False
        if user.role == User.Role.TEACHER:
            return discussion.created_by_id == user.id
        return bool(
            discussion.is_available
            and discussion.recipients.filter(student_id__in=student_ids).exists()
        )

    return False


@login_required
def pasted_image(request: HttpRequest, token: str):
    image = get_object_or_404(PastedImage, token=token)
    if not _can_access_target(request.user, image):
        raise PermissionDenied("이 본문 이미지를 볼 권한이 없습니다.")
    if not image.image:
        raise Http404
    response = FileResponse(
        image.image.open("rb"),
        as_attachment=False,
        filename=Path(image.original_name).name,
        content_type=image.content_type,
    )
    response["Cache-Control"] = "private, max-age=300"
    return response
