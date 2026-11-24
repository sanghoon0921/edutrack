from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import StudentAccountLink, User
from apps.operations.models import TeacherStudentAccess

from apps.classroom.models import CourseBoard, CourseCategory, CourseResource


@override_settings(STUDENT_DATA_SOURCE="demo")
class ClassroomWorkflowTests(TestCase):
    def setUp(self):
        self.media_dir = TemporaryDirectory()
        self.media_override = override_settings(MEDIA_ROOT=Path(self.media_dir.name))
        self.media_override.enable()
        self.addCleanup(self.media_override.disable)
        self.addCleanup(self.media_dir.cleanup)

        self.admin = User.objects.create_user(
            username="course_admin", password="1234", role=User.Role.ADMIN
        )
        self.teacher = User.objects.create_user(
            username="course_teacher", password="1234", role=User.Role.TEACHER
        )
        self.student = User.objects.create_user(
            username="course_student", password="1234", role=User.Role.STUDENT
        )
        self.other_student = User.objects.create_user(
            username="course_other", password="1234", role=User.Role.STUDENT
        )
        self.parent = User.objects.create_user(
            username="course_parent", password="1234", role=User.Role.PARENT
        )
        TeacherStudentAccess.objects.create(
            teacher=self.teacher,
            student_no="6333",
            student_name="김지훈",
            assigned_by=self.admin,
        )
        StudentAccountLink.objects.create(
            user=self.student,
            student_no="6333",
            relationship=StudentAccountLink.Relationship.SELF,
            is_primary=True,
            is_active=True,
        )
        StudentAccountLink.objects.create(
            user=self.other_student,
            student_no="7102",
            relationship=StudentAccountLink.Relationship.SELF,
            is_primary=True,
            is_active=True,
        )
        StudentAccountLink.objects.create(
            user=self.parent,
            student_no="6333",
            relationship=StudentAccountLink.Relationship.PARENT,
            is_primary=True,
            is_active=True,
        )

    def create_board(self):
        self.client.force_login(self.teacher)
        response = self.client.post(
            reverse("classroom:board-create"),
            {
                "title": "26SM 문학분석 Gold B",
                "term": "2026 여름특강",
                "subject": "SAT",
                "description": "문학 수업 자료",
                "sort_order": "1",
                "is_published": "on",
                "student_ids": "6333",
            },
        )
        self.assertEqual(response.status_code, 302)
        return CourseBoard.objects.get(title="26SM 문학분석 Gold B")

    @staticmethod
    def pdf(name="Jane Eyre.pdf", valid=True):
        data = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n" if valid else b"not-a-pdf"
        return SimpleUploadedFile(name, data, content_type="application/pdf")

    def test_teacher_creates_board_with_default_categories(self):
        board = self.create_board()
        self.assertEqual(
            list(board.categories.values_list("title", flat=True)),
            ["TEXTBOOK", "수업 자료", "VOCAB"],
        )
        self.assertTrue(board.recipients.filter(student_id="6333").exists())

    def test_teacher_cannot_assign_unassigned_student(self):
        self.client.force_login(self.teacher)
        response = self.client.post(
            reverse("classroom:board-create"),
            {
                "title": "권한 위반 과목",
                "sort_order": "0",
                "is_published": "on",
                "student_ids": "7102",
            },
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(CourseBoard.objects.filter(title="권한 위반 과목").exists())

    def test_assigned_student_sees_board_and_other_student_is_denied(self):
        board = self.create_board()
        self.client.force_login(self.student)
        listing = self.client.get(reverse("classroom:board-list"))
        self.assertEqual(listing.status_code, 200)
        self.assertContains(listing, board.title)
        self.assertEqual(
            self.client.get(reverse("classroom:board-detail", kwargs={"board_id": board.pk})).status_code,
            200,
        )

        self.client.force_login(self.other_student)
        denied = self.client.get(
            reverse("classroom:board-detail", kwargs={"board_id": board.pk})
        )
        self.assertEqual(denied.status_code, 403)

    def test_pdf_upload_preview_and_download(self):
        board = self.create_board()
        category = board.categories.get(title="TEXTBOOK")
        self.client.force_login(self.teacher)
        response = self.client.post(
            reverse(
                "classroom:resource-create",
                kwargs={"board_id": board.pk, "category_id": category.pk},
            ),
            {
                "title": "5. Jane Eyre (GOLD W8-9)",
                "resource_type": CourseResource.Type.PDF,
                "description": "교재 PDF",
                "file": self.pdf(),
                "sort_order": "1",
                "is_published": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        resource = CourseResource.objects.get()

        self.client.force_login(self.student)
        detail = self.client.get(
            reverse("classroom:resource-detail", kwargs={"resource_id": resource.pk})
        )
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "PDF 미리보기")

        preview = self.client.get(
            reverse("classroom:resource-preview", kwargs={"resource_id": resource.pk})
        )
        # FileResponse keeps the underlying PDF handle open until close().
        # Register it before assertions so Windows can remove MEDIA_ROOT even
        # when a later assertion fails. Test cleanups run in LIFO order.
        self.addCleanup(preview.close)
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview["Content-Type"], "application/pdf")
        self.assertIn("inline", preview["Content-Disposition"])
        self.assertEqual(preview["X-Frame-Options"], "SAMEORIGIN")

        download = self.client.get(
            reverse("classroom:resource-download", kwargs={"resource_id": resource.pk})
        )
        self.addCleanup(download.close)
        self.assertEqual(download.status_code, 200)
        self.assertIn("attachment", download["Content-Disposition"])
        self.assertIn("Jane", download["Content-Disposition"])

    def test_fake_pdf_is_rejected(self):
        board = self.create_board()
        category = board.categories.get(title="TEXTBOOK")
        self.client.force_login(self.teacher)
        response = self.client.post(
            reverse(
                "classroom:resource-create",
                kwargs={"board_id": board.pk, "category_id": category.pk},
            ),
            {
                "title": "가짜 PDF",
                "resource_type": CourseResource.Type.PDF,
                "file": self.pdf("fake.pdf", valid=False),
                "sort_order": "0",
                "is_published": "on",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "실제 PDF 파일")
        self.assertFalse(CourseResource.objects.exists())

    def test_board_page_has_clear_delete_and_resource_actions(self):
        board = self.create_board()
        self.client.force_login(self.teacher)
        response = self.client.get(
            reverse("classroom:board-detail", kwargs={"board_id": board.pk})
        )
        self.assertContains(response, "과목 영구 삭제")
        self.assertContains(response, "카테고리 삭제")
        self.assertContains(response, "＋ PDF 등록")
        self.assertContains(response, "＋ 파일 등록")
        self.assertContains(response, "＋ 링크 등록")



    def test_pdf_registration_form_is_explicit_and_file_input_is_visible(self):
        board = self.create_board()
        category = board.categories.get(title="TEXTBOOK")
        self.client.force_login(self.teacher)
        url = reverse(
            "classroom:resource-create",
            kwargs={"board_id": board.pk, "category_id": category.pk},
        )

        response = self.client.get(url, {"type": "PDF"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected_resource_type"], CourseResource.Type.PDF)
        self.assertContains(response, "PDF 등록")
        self.assertContains(response, "PDF 파일 선택")
        self.assertContains(response, 'name="file"', html=False)
        self.assertContains(response, '.pdf,application/pdf', html=False)
        self.assertContains(response, "PDF 자료 등록")

    def test_resource_registration_type_can_be_opened_directly(self):
        board = self.create_board()
        category = board.categories.get(title="TEXTBOOK")
        self.client.force_login(self.teacher)
        url = reverse(
            "classroom:resource-create",
            kwargs={"board_id": board.pk, "category_id": category.pk},
        )

        file_response = self.client.get(url, {"type": "FILE"})
        link_response = self.client.get(url, {"type": "LINK"})

        self.assertEqual(file_response.context["selected_resource_type"], CourseResource.Type.FILE)
        self.assertContains(file_response, "일반 파일 등록")
        self.assertEqual(link_response.context["selected_resource_type"], CourseResource.Type.LINK)
        self.assertContains(link_response, "외부 링크 등록")

    def test_linked_parent_can_open_child_course_board(self):
        board = self.create_board()
        self.client.force_login(self.parent)
        listing = self.client.get(reverse("classroom:board-list"))
        self.assertEqual(listing.status_code, 200)
        self.assertContains(listing, board.title)
        detail = self.client.get(
            reverse("classroom:board-detail", kwargs={"board_id": board.pk})
        )
        self.assertEqual(detail.status_code, 200)

    def test_unpublished_category_and_resource_are_hidden_from_student(self):
        board = self.create_board()
        category = board.categories.get(title="TEXTBOOK")
        category.is_published = False
        category.save(update_fields=("is_published", "updated_at"))
        resource = CourseResource.objects.create(
            category=category,
            title="비공개 교재",
            resource_type=CourseResource.Type.PDF,
            file=self.pdf("private.pdf"),
            original_name="private.pdf",
            size=20,
            created_by=self.teacher,
            is_published=True,
        )

        self.client.force_login(self.student)
        detail = self.client.get(
            reverse("classroom:board-detail", kwargs={"board_id": board.pk})
        )
        self.assertEqual(detail.status_code, 200)
        self.assertNotContains(detail, "비공개 교재")
        preview = self.client.get(
            reverse("classroom:resource-preview", kwargs={"resource_id": resource.pk})
        )
        self.assertEqual(preview.status_code, 403)


    def test_replacing_pdf_deletes_old_file_after_database_commit(self):
        board = self.create_board()
        category = board.categories.get(title="TEXTBOOK")
        resource = CourseResource.objects.create(
            category=category,
            title="교체 전 PDF",
            resource_type=CourseResource.Type.PDF,
            file=self.pdf("old.pdf"),
            original_name="old.pdf",
            size=20,
            created_by=self.teacher,
            is_published=True,
        )
        old_path = Path(resource.file.path)
        self.assertTrue(old_path.exists())

        self.client.force_login(self.teacher)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse("classroom:resource-update", kwargs={"resource_id": resource.pk}),
                {
                    "title": "교체 후 PDF",
                    "resource_type": CourseResource.Type.PDF,
                    "description": "새 교재",
                    "file": self.pdf("new.pdf"),
                    "sort_order": "1",
                    "is_published": "on",
                },
            )
        self.assertEqual(response.status_code, 302)
        resource.refresh_from_db()
        self.assertFalse(old_path.exists())
        self.assertTrue(Path(resource.file.path).exists())
