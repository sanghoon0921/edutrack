from __future__ import annotations

import json

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.classroom.forms import CourseBoardForm, CourseCategoryForm, CourseResourceForm
from apps.classroom.models import CourseBoard, CourseCategory

from apps.operations.models import AccountAuditLog, TeacherStudentAccess


@override_settings(STUDENT_DATA_SOURCE="demo")
class TeacherSelfAssignmentTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="operating_v5_admin",
            password="StrongPass!2026",
            role=User.Role.ADMIN,
        )
        self.teacher = User.objects.create_user(
            username="operating_v5_teacher",
            password="StrongPass!2026",
            role=User.Role.TEACHER,
        )
        self.student = User.objects.create_user(
            username="operating_v5_student",
            password="StrongPass!2026",
            role=User.Role.STUDENT,
        )
        TeacherStudentAccess.objects.create(
            teacher=self.teacher,
            student_no="6333",
            student_name="김지훈",
            assigned_by=self.admin,
            is_active=True,
        )

    def test_teacher_management_page_uses_two_box_transfer_ui(self):
        self.client.force_login(self.teacher)

        response = self.client.get(
            reverse("operations:teacher-student-assignment")
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "인트라넷 학생 찾기")
        self.assertContains(response, "현재 담당 학생")
        self.assertContains(response, "선택 추가")
        self.assertContains(response, "선택 제외")
        self.assertContains(response, "김지훈")
        self.assertContains(response, "data-teacher-self-assignment")

    def test_non_teacher_cannot_open_or_modify_teacher_scope(self):
        for user in (self.admin, self.student):
            with self.subTest(role=user.role):
                self.client.force_login(user)
                self.assertEqual(
                    self.client.get(
                        reverse("operations:teacher-student-assignment")
                    ).status_code,
                    403,
                )
                self.assertEqual(
                    self.client.get(
                        reverse("students:selector-browse"),
                        {"mode": "teacher", "q": "김지훈"},
                    ).status_code,
                    403,
                )
                self.assertEqual(
                    self.client.post(
                        reverse("operations:teacher-student-assignment-update"),
                        data=json.dumps(
                            {"action": "add", "student_nos": ["7102"]}
                        ),
                        content_type="application/json",
                    ).status_code,
                    403,
                )

    def test_teacher_can_search_all_intranet_students_and_see_assignment_state(self):
        self.client.force_login(self.teacher)

        response = self.client.get(
            reverse("students:selector-browse"),
            {"mode": "teacher", "q": "Ekamai"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["results"][0]["student_id"], "6333")
        self.assertTrue(payload["results"][0]["assigned"])

        unassigned = self.client.get(
            reverse("students:selector-browse"),
            {"mode": "teacher", "q": "7102"},
        ).json()
        self.assertEqual(unassigned["results"][0]["student_id"], "7102")
        self.assertFalse(unassigned["results"][0]["assigned"])

    def test_teacher_can_add_student_to_own_scope_with_audit_log(self):
        self.client.force_login(self.teacher)

        response = self.client.post(
            reverse("operations:teacher-student-assignment-update"),
            data=json.dumps({"action": "add", "student_nos": ["7102"]}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        access = TeacherStudentAccess.objects.get(
            teacher=self.teacher,
            student_no="7102",
        )
        self.assertTrue(access.is_active)
        self.assertEqual(access.assigned_by, self.teacher)
        self.assertTrue(
            AccountAuditLog.objects.filter(
                actor=self.teacher,
                target_user=self.teacher,
                action=AccountAuditLog.Action.TEACHER_STUDENT_ADDED,
                metadata__student_no="7102",
            ).exists()
        )

    def test_teacher_can_remove_student_from_own_scope(self):
        access = TeacherStudentAccess.objects.get(
            teacher=self.teacher,
            student_no="6333",
        )
        self.client.force_login(self.teacher)

        response = self.client.post(
            reverse("operations:teacher-student-assignment-update"),
            data=json.dumps({"action": "remove", "student_nos": ["6333"]}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        access.refresh_from_db()
        self.assertFalse(access.is_active)
        self.assertTrue(
            AccountAuditLog.objects.filter(
                actor=self.teacher,
                target_user=self.teacher,
                action=AccountAuditLog.Action.TEACHER_STUDENT_REMOVED,
                metadata__student_no="6333",
            ).exists()
        )

    def test_teacher_pages_show_current_registered_students(self):
        self.client.force_login(self.teacher)

        classes = self.client.get(reverse("teacher_classes"))
        students = self.client.get(reverse("teacher_students"))
        directory = self.client.get(reverse("students:list"))

        for response in (classes, students, directory):
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "김지훈")
        self.assertContains(classes, "담당 학생 관리")
        self.assertContains(students, "학생 추가·제외")
        self.assertContains(directory, "학생 추가·제외")


class CompactCourseContentTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(
            username="operating_v5_course_teacher",
            password="StrongPass!2026",
            role=User.Role.TEACHER,
        )
        self.board = CourseBoard.objects.create(
            title="운영 V5 과목",
            term="2026 가을",
            subject="SAT",
            created_by=self.teacher,
            is_published=True,
        )
        self.category = CourseCategory.objects.create(
            board=self.board,
            title="TEXTBOOK",
            description="교재",
            is_published=True,
        )

    def test_normal_course_forms_hide_sort_and_public_controls(self):
        board_form = CourseBoardForm(user=self.teacher)
        category_form = CourseCategoryForm()
        resource_form = CourseResourceForm(initial_type="PDF")

        for form in (board_form, category_form, resource_form):
            self.assertNotIn("sort_order", form.fields)
            self.assertNotIn("is_published", form.fields)

    def test_course_pages_load_compact_styles_without_public_or_sort_controls(self):
        self.client.force_login(self.teacher)

        board_form = self.client.get(reverse("classroom:board-create"))
        category_form = self.client.get(
            reverse("classroom:category-update", args=[self.board.pk, self.category.pk])
        )
        resource_form = self.client.get(
            reverse(
                "classroom:resource-create",
                args=[self.board.pk, self.category.pk],
            ),
            {"type": "PDF"},
        )

        for response in (board_form, category_form, resource_form):
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "compact-pages.css")
            self.assertNotContains(response, "정렬 순서")
            self.assertNotContains(response, "학생 공개")

    def test_compact_resource_actions_keep_existing_workflow_labels(self):
        self.client.force_login(self.teacher)

        response = self.client.get(
            reverse("classroom:board-detail", args=[self.board.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "＋ PDF 등록")
        self.assertContains(response, "＋ 파일 등록")
        self.assertContains(response, "＋ 링크 등록")
        self.assertContains(response, "et-v5-action is-resource")

    def test_hidden_public_field_is_saved_as_published(self):
        category = CourseCategory.objects.create(
            board=self.board,
            title="비공개였던 자료",
            description="",
            is_published=False,
        )
        form = CourseCategoryForm(
            {"title": "항상 공개", "description": "자동 공개"},
            instance=category,
        )

        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()
        self.assertTrue(saved.is_published)
