from __future__ import annotations

from django.db import migrations


def _backfill_teacher_student_access(apps, schema_editor):
    """기존 과제·토론·퀴즈·과목자료 대상에서 강사 담당 학생을 복구합니다.

    TeacherStudentAccess가 도입되기 전에 이미 강사가 학생에게 콘텐츠를
    배정한 데이터가 있을 수 있습니다. 해당 이력을 한 번만 담당 학생 범위로
    옮기되, 관리자가 비활성화한 기존 행은 다시 활성화하지 않습니다.
    """

    TeacherStudentAccess = apps.get_model("operations", "TeacherStudentAccess")
    AssignmentRecipient = apps.get_model("assignments", "AssignmentRecipient")
    DiscussionRecipient = apps.get_model("learning", "DiscussionRecipient")
    QuizRecipient = apps.get_model("learning", "QuizRecipient")
    CourseBoardRecipient = apps.get_model("classroom", "CourseBoardRecipient")

    sources = (
        AssignmentRecipient.objects.filter(
            assignment__created_by__role="TEACHER"
        ).values_list(
            "assignment__created_by_id", "student_id", "student_name"
        ),
        DiscussionRecipient.objects.filter(
            discussion__created_by__role="TEACHER"
        ).values_list(
            "discussion__created_by_id", "student_id", "student_name"
        ),
        QuizRecipient.objects.filter(
            quiz__created_by__role="TEACHER"
        ).values_list(
            "quiz__created_by_id", "student_id", "student_name"
        ),
        CourseBoardRecipient.objects.filter(
            board__created_by__role="TEACHER"
        ).values_list(
            "board__created_by_id", "student_id", "student_name"
        ),
    )

    seen: set[tuple[int, str]] = set()
    for source in sources:
        for teacher_id, raw_student_no, raw_student_name in source.iterator():
            student_no = str(raw_student_no or "").strip()
            if not teacher_id or not student_no:
                continue
            key = (int(teacher_id), student_no)
            if key in seen:
                continue
            seen.add(key)

            student_name = str(raw_student_name or "").strip()[:100]
            access, created = TeacherStudentAccess.objects.get_or_create(
                teacher_id=teacher_id,
                student_no=student_no,
                defaults={
                    "student_name": student_name,
                    "is_active": True,
                },
            )
            # 기존 행이 있으면 활성/비활성 상태는 건드리지 않습니다. 다만 과거
            # 데이터에 이름이 비어 있을 때만 안전하게 보완합니다.
            if not created and not access.student_name and student_name:
                access.student_name = student_name
                access.save(update_fields=("student_name", "updated_at"))


def _noop_reverse(apps, schema_editor):
    # 기존 운영자가 수동 배정한 행과 자동 복구 행을 확실히 구분할 수 없으므로
    # 되돌릴 때 데이터를 삭제하지 않습니다.
    return None


class Migration(migrations.Migration):
    dependencies = [
        ("operations", "0002_teacherstudentaccess_and_audit_actions"),
        ("assignments", "0002_assignment_available_from_assignment_group_and_more"),
        ("learning", "0001_initial"),
        ("classroom", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(
            _backfill_teacher_student_access,
            reverse_code=_noop_reverse,
        )
    ]
