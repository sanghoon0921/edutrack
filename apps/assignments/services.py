from __future__ import annotations

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from apps.operations.access import restrict_student_ids_for_user
from apps.students.services import StudentService

from .models import Assignment, AssignmentRecipient


class UnknownStudentsError(ValidationError):
    pass


class AssignmentService:
    def __init__(self, student_service: StudentService | None = None) -> None:
        self.student_service = student_service or StudentService()

    def _resolve_students(self, student_ids: list[str], *, user) -> list[tuple[str, str]]:
        allowed_ids = restrict_student_ids_for_user(user, student_ids)
        if set(allowed_ids) != set(student_ids):
            raise PermissionDenied("강사는 담당 학생에게만 과제를 배정할 수 있습니다.")

        students = self.student_service.get_students(student_ids)
        student_map = {student.student_id: student for student in students}
        unknown = [student_id for student_id in student_ids if student_id not in student_map]
        if unknown:
            raise UnknownStudentsError("확인되지 않은 학생번호: " + ", ".join(unknown))
        return [
            (student_id, student_map[student_id].name)
            for student_id in student_ids
        ]

    @transaction.atomic
    def save_assignment(self, *, form, user) -> Assignment:
        assignment = form.save(commit=False)
        if not assignment.pk:
            assignment.created_by = user
        assignment.save()

        from apps.lms.integrations import scoped_roster
        students = scoped_roster(user, assignment.group, form.cleaned_data["student_ids"])
        if students is None:
            students = self._resolve_students(form.cleaned_data["student_ids"], user=user)
        keep_ids: list[int] = []
        for student_id, student_name in students:
            recipient, _ = AssignmentRecipient.objects.update_or_create(
                assignment=assignment,
                student_id=student_id,
                defaults={"student_name": student_name},
            )
            keep_ids.append(recipient.pk)
        removed=assignment.recipients.exclude(pk__in=keep_ids)
        if removed.filter(submission__isnull=False).exists():
            raise UnknownStudentsError("제출 기록이 있는 학생은 배정에서 제외할 수 없습니다. 기존 제출·점수를 보존하고 새 과제를 만들어 주세요.")
        removed.delete()
        return assignment
