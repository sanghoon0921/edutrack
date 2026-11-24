from __future__ import annotations

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Max

from apps.operations.access import restrict_student_ids_for_user
from apps.students.services import StudentService

from .models import CourseBoard, CourseBoardRecipient, CourseCategory


class UnknownStudentsError(ValidationError):
    pass


def can_manage_board(user, board: CourseBoard) -> bool:
    return bool(
        user.is_superuser
        or getattr(user, "role", "") == "ADMIN"
        or board.created_by_id == user.id
    )


def ensure_manage_board(user, board: CourseBoard) -> None:
    if not can_manage_board(user, board):
        raise PermissionDenied("본인이 만든 과목 자료만 관리할 수 있습니다.")


def resolve_students(student_ids: list[str], *, user) -> list[tuple[str, str]]:
    cleaned = list(dict.fromkeys(str(item).strip() for item in student_ids if str(item).strip()))
    allowed = restrict_student_ids_for_user(user, cleaned)
    if set(allowed) != set(cleaned):
        raise PermissionDenied("강사는 담당 학생에게만 과목 자료를 공개할 수 있습니다.")
    students = StudentService().get_students(cleaned)
    student_map = {student.student_id: student for student in students}
    unknown = [student_id for student_id in cleaned if student_id not in student_map]
    if unknown:
        raise UnknownStudentsError("확인되지 않은 학생번호: " + ", ".join(unknown))
    return [(student_id, student_map[student_id].name) for student_id in cleaned]


@transaction.atomic
def save_board(*, form, user) -> CourseBoard:
    board = form.save(commit=False)
    is_new = not board.pk
    if is_new:
        board.created_by = user
        highest_order = CourseBoard.objects.aggregate(value=Max("sort_order"))["value"] or 0
        board.sort_order = highest_order + 10
    else:
        ensure_manage_board(user, board)
    board.is_published = True
    board.save()

    recipients = resolve_students(form.cleaned_data["student_ids"], user=user)
    keep_ids: list[int] = []
    for student_id, student_name in recipients:
        recipient, _ = CourseBoardRecipient.objects.update_or_create(
            board=board,
            student_id=student_id,
            defaults={"student_name": student_name},
        )
        keep_ids.append(recipient.pk)
    board.recipients.exclude(pk__in=keep_ids).delete()

    if is_new:
        defaults = (
            ("TEXTBOOK", "교재와 필수 읽기 자료", 10),
            ("수업 자료", "주차별 수업 자료", 20),
            ("VOCAB", "어휘 연습과 단어 목록", 30),
        )
        for title, description, sort_order in defaults:
            CourseCategory.objects.create(
                board=board,
                title=title,
                description=description,
                sort_order=sort_order,
                is_published=True,
            )
    return board
