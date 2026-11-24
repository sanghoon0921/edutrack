from __future__ import annotations

import csv
import io
from types import SimpleNamespace
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import StudentAccountLink, User
from apps.assignments.models import Assignment, AssignmentRecipient, Submission
from apps.operations.models import AccountAuditLog

from apps.data_imports.models import ImportBatch, ImportRowResult, LegacyObjectMap
from apps.data_imports.services import (
    ImportValidationError,
    apply_assignment_import,
    apply_user_import,
    generate_temporary_password,
    preview_user_import,
)


class DataImportTestMixin:
    def setUp(self):
        self.admin = User.objects.create_user(
            username="import_admin",
            password="Admin!2026Strong",
            display_name="이전 관리자",
            role=User.Role.ADMIN,
            is_active=True,
        )
        self.superuser = User.objects.create_superuser(
            username="import_root",
            password="1234",
            display_name="최고관리자",
            role=User.Role.ADMIN,
        )
        self.teacher = User.objects.create_user(
            username="teacher_test",
            password="Teacher!2026Strong",
            display_name="테스트 강사",
            role=User.Role.TEACHER,
            is_active=True,
        )
        self.student_lookup_patcher = patch(
            "apps.students.services.StudentService.get_student",
            side_effect=lambda student_no: SimpleNamespace(
                student_id=str(student_no),
                name=f"학생 {student_no}",
            )
            if str(student_no) in {"3228", "4001", "4002"}
            else None,
        )
        self.student_lookup_patcher.start()
        self.addCleanup(self.student_lookup_patcher.stop)

    def csv_upload(self, headers, rows, *, name="import.csv", encoding="utf-8-sig"):
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(headers)
        writer.writerows(rows)
        return SimpleUploadedFile(
            name,
            output.getvalue().encode(encoding),
            content_type="text/csv",
        )

    def user_upload(self, rows, *, encoding="utf-8-sig"):
        # 구버전 테스트 행(8열)이 남아 있어도 is_active 열은 버리고
        # 현재 표준 7열 CSV로 변환합니다. 실제 양식에는 is_active가 없습니다.
        normalized_rows = [
            tuple(row[:6]) + tuple(row[7:]) if len(row) == 8 else tuple(row)
            for row in rows
        ]
        return self.csv_upload(
            (
                "username",
                "display_name",
                "email",
                "role",
                "student_no",
                "is_primary",
                "temporary_password",
            ),
            normalized_rows,
            name="users.csv",
            encoding=encoding,
        )

    def assignment_upload(self, rows):
        return self.csv_upload(
            (
                "legacy_assignment_key",
                "title",
                "description",
                "due_at",
                "teacher_username",
                "student_no",
                "student_name",
                "is_published",
                "submitted_at",
                "text_answer",
                "feedback",
                "feedback_by_username",
                "feedback_at",
            ),
            rows,
            name="assignments.csv",
        )


class DataImportPermissionTests(DataImportTestMixin, TestCase):
    def test_admin_can_open_import_dashboard(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("data_imports:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "데이터 이전 센터")

    def test_non_admin_cannot_open_import_dashboard(self):
        self.client.force_login(self.teacher)
        response = self.client.get(reverse("data_imports:dashboard"))
        self.assertEqual(response.status_code, 403)

    def test_operations_dashboard_has_import_link(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("operations:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("data_imports:dashboard"))

    def test_templates_download_as_utf8_csv(self):
        self.client.force_login(self.admin)
        user_response = self.client.get(reverse("data_imports:user-template"))
        assignment_response = self.client.get(reverse("data_imports:assignment-template"))
        self.assertEqual(user_response.status_code, 200)
        self.assertTrue(user_response.content.startswith(b"\xef\xbb\xbf"))
        decoded = user_response.content.decode("utf-8-sig")
        header = decoded.splitlines()[0]
        self.assertIn("username", header)
        self.assertIn("temporary_password", header)
        self.assertNotIn("is_active", header)
        example_response = self.client.get(reverse("data_imports:user-example"))
        self.assertEqual(example_response.status_code, 200)
        self.assertIn("student_3228", example_response.content.decode("utf-8-sig"))
        self.assertEqual(assignment_response.status_code, 200)
        self.assertIn(b"legacy_assignment_key", assignment_response.content)


class TemporaryPasswordTests(TestCase):
    def test_generated_password_starts_with_csv_safe_character(self):
        for _ in range(100):
            password = generate_temporary_password()
            self.assertTrue(password[0].isalnum())
            self.assertNotIn(password[0], "=+-@")


class UserImportTests(DataImportTestMixin, TestCase):
    def test_cp949_preview_supports_parent_siblings_without_writes(self):
        upload = self.user_upload(
            [
                ("parent_family", "가족 학부모", "p@example.com", "학부모", "4001", "Y", "Y", ""),
                ("parent_family", "가족 학부모", "p@example.com", "학부모", "4002", "N", "Y", ""),
            ],
            encoding="cp949",
        )
        preview = preview_user_import(upload, mode=ImportBatch.Mode.CREATE_ONLY)
        self.assertTrue(preview.is_valid)
        self.assertEqual(preview.encoding, "cp949")
        self.assertEqual(preview.items[0]["student_nos"], ["4001", "4002"])
        self.assertFalse(User.objects.filter(username="parent_family").exists())

    def test_web_apply_creates_accounts_links_and_one_time_credentials(self):
        self.client.force_login(self.admin)
        upload = self.user_upload(
            [
                ("student_3228", "학생 3228", "s@example.com", "STUDENT", "3228", "Y", "Y", ""),
                ("parent_3228", "학생 학부모", "p@example.com", "PARENT", "3228", "Y", "Y", ""),
            ]
        )
        response = self.client.post(
            reverse("data_imports:user-import"),
            {
                "csv_file": upload,
                "mode": ImportBatch.Mode.CREATE_ONLY,
                "confirm_apply": "on",
                "action": "apply",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"].split(";")[0], "text/csv")
        decoded = response.content.decode("utf-8-sig")
        rows = list(csv.DictReader(io.StringIO(decoded)))
        self.assertEqual({row["username"] for row in rows}, {"student_3228", "parent_3228"})

        for row in rows:
            user = User.objects.get(username=row["username"])
            self.assertTrue(user.check_password(row["temporary_password"]))
        self.assertEqual(StudentAccountLink.objects.filter(is_active=True).count(), 2)

        batch = ImportBatch.objects.get(kind=ImportBatch.Kind.USERS)
        self.assertEqual(batch.created_count, 2)
        self.assertEqual(batch.status, ImportBatch.Status.COMPLETED)
        persisted = str(batch.summary) + " ".join(
            result.message + str(result.safe_data) for result in batch.row_results.all()
        ) + " ".join(str(log.metadata) for log in AccountAuditLog.objects.all())
        for row in rows:
            self.assertNotIn(row["temporary_password"], persisted)

    def test_create_only_skips_existing_user(self):
        existing = User.objects.create_user(
            username="existing_student",
            password="Existing!2026Strong",
            display_name="기존 이름",
            role=User.Role.STUDENT,
        )
        upload = self.user_upload(
            [("existing_student", "변경 이름", "", "STUDENT", "3228", "Y", "Y", "")]
        )
        outcome = apply_user_import(
            upload,
            mode=ImportBatch.Mode.CREATE_ONLY,
            actor=self.admin,
        )
        existing.refresh_from_db()
        self.assertEqual(existing.display_name, "기존 이름")
        self.assertEqual(outcome.batch.skipped_count, 1)

    def test_upsert_updates_profile_but_not_password(self):
        existing = User.objects.create_user(
            username="update_student",
            password="Original!2026Strong",
            display_name="기존 이름",
            role=User.Role.STUDENT,
        )
        upload = self.user_upload(
            [("update_student", "수정 이름", "new@example.com", "STUDENT", "3228", "Y", "N", "NewPass!2026Strong")]
        )
        outcome = apply_user_import(upload, mode=ImportBatch.Mode.UPSERT, actor=self.admin)
        existing.refresh_from_db()
        self.assertEqual(existing.display_name, "수정 이름")
        self.assertEqual(existing.email, "new@example.com")
        self.assertTrue(existing.is_active)
        self.assertTrue(existing.check_password("Original!2026Strong"))
        self.assertEqual(outcome.batch.updated_count, 1)

    def test_student_multiple_links_fails_without_creating_user(self):
        upload = self.user_upload(
            [
                ("invalid_student", "잘못된 학생", "", "STUDENT", "4001", "Y", "Y", "Strong!2026Pass"),
                ("invalid_student", "잘못된 학생", "", "STUDENT", "4002", "N", "Y", "Strong!2026Pass"),
            ]
        )
        outcome = apply_user_import(upload, mode=ImportBatch.Mode.CREATE_ONLY, actor=self.admin)
        self.assertEqual(outcome.batch.status, ImportBatch.Status.FAILED)
        self.assertFalse(User.objects.filter(username="invalid_student").exists())
        self.assertGreater(outcome.batch.error_count, 0)

    def test_unknown_student_number_is_rejected(self):
        upload = self.user_upload(
            [("unknown_student", "없는 학생", "", "STUDENT", "9999", "Y", "Y", "Strong!2026Pass")]
        )
        preview = preview_user_import(upload, mode=ImportBatch.Mode.CREATE_ONLY)
        self.assertFalse(preview.is_valid)
        self.assertIn("찾지 못했습니다", " ".join(issue.message for issue in preview.issues))

    def test_student_upsert_deactivates_old_extra_link(self):
        user = User.objects.create_user(
            username="linked_student",
            password="Original!2026Strong",
            display_name="연결 학생",
            role=User.Role.STUDENT,
        )
        StudentAccountLink.objects.create(
            user=user,
            student_no="4001",
            relationship=StudentAccountLink.Relationship.SELF,
            is_primary=True,
            is_active=True,
        )
        upload = self.user_upload(
            [("linked_student", "연결 학생", "", "STUDENT", "3228", "Y", "Y", "")]
        )
        outcome = apply_user_import(upload, mode=ImportBatch.Mode.UPSERT, actor=self.admin)
        self.assertEqual(outcome.batch.updated_count, 1)
        self.assertFalse(
            StudentAccountLink.objects.get(user=user, student_no="4001").is_active
        )
        self.assertTrue(
            StudentAccountLink.objects.get(user=user, student_no="3228").is_active
        )

    def test_normal_admin_cannot_create_or_change_admin_role(self):
        create_upload = self.user_upload(
            [("forbidden_admin", "금지 관리자", "", "ADMIN", "", "", "bulk-pass-2026")]
        )
        create_outcome = apply_user_import(
            create_upload,
            mode=ImportBatch.Mode.CREATE_ONLY,
            actor=self.admin,
        )
        self.assertFalse(User.objects.filter(username="forbidden_admin").exists())
        self.assertGreater(create_outcome.batch.error_count, 0)

        existing = User.objects.create_user(
            username="role_target",
            password="1234",
            role=User.Role.TEACHER,
        )
        update_upload = self.user_upload(
            [("role_target", "역할 대상", "", "PARENT", "3228", "Y", "")]
        )
        update_outcome = apply_user_import(
            update_upload,
            mode=ImportBatch.Mode.UPSERT,
            actor=self.admin,
        )
        existing.refresh_from_db()
        self.assertEqual(existing.role, User.Role.TEACHER)
        self.assertGreater(update_outcome.batch.error_count, 0)

    def test_superuser_can_create_admin_role(self):
        upload = self.user_upload(
            [("bulk_admin", "일괄 관리자", "", "ADMIN", "", "", "bulk-pass-2026")]
        )
        outcome = apply_user_import(
            upload,
            mode=ImportBatch.Mode.CREATE_ONLY,
            actor=self.superuser,
        )
        self.assertEqual(outcome.batch.error_count, 0)
        self.assertEqual(User.objects.get(username="bulk_admin").role, User.Role.ADMIN)



class AssignmentImportTests(DataImportTestMixin, TestCase):
    def assignment_rows(self, *, title="기존 과제", key="LEGACY-1"):
        return [
            (
                key,
                title,
                "기존 과제 설명",
                "2026-08-31 23:59",
                "teacher_test",
                "3228",
                "학생 3228",
                "Y",
                "2026-08-29 20:10",
                "제출 답안",
                "피드백 완료",
                "teacher_test",
                "2026-08-30 10:00",
            )
        ]

    def test_apply_creates_assignment_recipient_submission_and_map(self):
        upload = self.assignment_upload(self.assignment_rows())
        outcome = apply_assignment_import(
            upload,
            mode=ImportBatch.Mode.CREATE_ONLY,
            actor=self.admin,
        )
        self.assertEqual(outcome.batch.status, ImportBatch.Status.COMPLETED)
        assignment = Assignment.objects.get(title="기존 과제")
        recipient = AssignmentRecipient.objects.get(assignment=assignment, student_id="3228")
        submission = Submission.objects.get(recipient=recipient)
        self.assertEqual(submission.text_answer, "제출 답안")
        self.assertEqual(submission.feedback, "피드백 완료")
        self.assertEqual(submission.feedback_by, self.teacher)
        mapping = LegacyObjectMap.objects.get(external_key="LEGACY-1")
        self.assertEqual(mapping.target_object_id, assignment.pk)

    def test_create_only_is_idempotent_and_skips_existing_mapping(self):
        first = apply_assignment_import(
            self.assignment_upload(self.assignment_rows()),
            mode=ImportBatch.Mode.CREATE_ONLY,
            actor=self.admin,
        )
        second = apply_assignment_import(
            self.assignment_upload(self.assignment_rows()),
            mode=ImportBatch.Mode.CREATE_ONLY,
            actor=self.admin,
        )
        self.assertEqual(first.batch.created_count, 1)
        self.assertEqual(second.batch.skipped_count, 1)
        self.assertEqual(Assignment.objects.count(), 1)

    def test_upsert_updates_existing_assignment(self):
        apply_assignment_import(
            self.assignment_upload(self.assignment_rows()),
            mode=ImportBatch.Mode.CREATE_ONLY,
            actor=self.admin,
        )
        outcome = apply_assignment_import(
            self.assignment_upload(self.assignment_rows(title="수정된 과제")),
            mode=ImportBatch.Mode.UPSERT,
            actor=self.admin,
        )
        self.assertEqual(outcome.batch.updated_count, 1)
        self.assertEqual(Assignment.objects.get().title, "수정된 과제")

    def test_invalid_teacher_causes_validation_failure(self):
        rows = [list(row) for row in self.assignment_rows()]
        rows[0][4] = "missing_teacher"
        outcome = apply_assignment_import(
            self.assignment_upload(rows),
            mode=ImportBatch.Mode.CREATE_ONLY,
            actor=self.admin,
        )
        self.assertEqual(outcome.batch.status, ImportBatch.Status.FAILED)
        self.assertFalse(Assignment.objects.exists())

    def test_web_preview_renders_expected_action(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("data_imports:assignment-import"),
            {
                "csv_file": self.assignment_upload(self.assignment_rows()),
                "mode": ImportBatch.Mode.CREATE_ONLY,
                "action": "preview",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "실제 반영 가능")
        self.assertContains(response, "LEGACY-1")


class ImportBatchTests(DataImportTestMixin, TestCase):
    def test_batch_detail_and_result_csv(self):
        batch = ImportBatch.objects.create(
            kind=ImportBatch.Kind.USERS,
            mode=ImportBatch.Mode.CREATE_ONLY,
            status=ImportBatch.Status.COMPLETED,
            source_filename="users.csv",
            source_sha256="a" * 64,
            actor=self.admin,
            total_rows=1,
            created_count=1,
        )
        ImportRowResult.objects.create(
            batch=batch,
            row_number=2,
            external_key="student_3228",
            action=ImportRowResult.Action.CREATED,
            target_type="accounts.User",
            target_id="10",
            message="생성 완료",
        )
        self.client.force_login(self.admin)
        detail = self.client.get(reverse("data_imports:batch-detail", args=[batch.pk]))
        result = self.client.get(reverse("data_imports:batch-results", args=[batch.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "생성 완료")
        self.assertEqual(result.status_code, 200)
        self.assertTrue(result.content.startswith(b"\xef\xbb\xbf"))
        self.assertIn("student_3228", result.content.decode("utf-8-sig"))

    def test_apply_requires_confirmation(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("data_imports:user-import"),
            {
                "csv_file": self.user_upload(
                    [("student_no_confirm", "확인 학생", "", "STUDENT", "3228", "Y", "Y", "Strong!2026Pass")]
                ),
                "mode": ImportBatch.Mode.CREATE_ONLY,
                "action": "apply",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "실제 반영 확인이 필요합니다")
        self.assertFalse(User.objects.filter(username="student_no_confirm").exists())
