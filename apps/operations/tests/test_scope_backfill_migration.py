from __future__ import annotations

from importlib import import_module
from datetime import timedelta

from django.apps import apps
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.assignments.models import Assignment, AssignmentRecipient

from apps.operations.models import TeacherStudentAccess


class LegacyTeacherScopeBackfillTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(
            username="legacy_scope_teacher",
            password="1234",
            role=User.Role.TEACHER,
        )
        self.assignment = Assignment.objects.create(
            title="기존 강사 과제",
            description="담당 학생 모델 도입 전 배정 데이터",
            due_at=timezone.now() + timedelta(days=7),
            created_by=self.teacher,
            is_published=True,
        )
        AssignmentRecipient.objects.create(
            assignment=self.assignment,
            student_id="6333",
            student_name="김지훈",
        )
        self.migration = import_module(
            "apps.operations.migrations.0003_backfill_legacy_teacher_student_access"
        )

    def test_existing_teacher_assignment_is_backfilled(self):
        self.assertFalse(
            TeacherStudentAccess.objects.filter(
                teacher=self.teacher,
                student_no="6333",
            ).exists()
        )

        self.migration._backfill_teacher_student_access(apps, None)

        access = TeacherStudentAccess.objects.get(
            teacher=self.teacher,
            student_no="6333",
        )
        self.assertTrue(access.is_active)
        self.assertEqual(access.student_name, "김지훈")

    def test_inactive_manual_scope_is_not_reactivated(self):
        TeacherStudentAccess.objects.create(
            teacher=self.teacher,
            student_no="6333",
            student_name="김지훈",
            is_active=False,
        )

        self.migration._backfill_teacher_student_access(apps, None)

        access = TeacherStudentAccess.objects.get(
            teacher=self.teacher,
            student_no="6333",
        )
        self.assertFalse(access.is_active)
