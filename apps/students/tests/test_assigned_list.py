"""담당 학생 화면: 한 줄 표, 수업·반 드롭다운, 즉시 거르기 연결, 확인 필요 학생."""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.learning.models import LearningGroup
from apps.lms.models import GroupMember
from apps.operations.models import TeacherStudentAccess


@override_settings(STUDENT_DATA_SOURCE="demo", CLASS_CATALOG_DATA_SOURCE="demo")
class AssignedListPageTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_user("list_admin", password="x-List!2026", role="ADMIN")
        self.teacher = User.objects.create_user("list_teacher", password="x-List!2026", role="TEACHER")
        for number, name in [("6333", "김지훈"), ("7102", "이서연"), ("99999", "미확인 학생")]:
            TeacherStudentAccess.objects.create(teacher=self.teacher, student_no=number, student_name=name, assigned_by=self.admin)
        self.group = LearningGroup.objects.create(title="A반", created_by=self.teacher)
        GroupMember.objects.create(group=self.group, student_no="7102", student_name="이서연")
        self.client.force_login(self.teacher)

    def page(self, **query):
        return self.client.get(reverse("students:list"), query)

    def test_all_assigned_students_listed_as_rows_without_searching(self):
        response = self.page()
        html = response.content.decode()
        self.assertEqual(html.count('class="st-row'), 3)
        self.assertNotIn("premium-student-result-card", html)
        self.assertContains(response, 'data-student-id="6333"')
        self.assertContains(response, 'data-classes="201"')

    def test_unresolved_assigned_student_is_marked_and_not_a_link(self):
        response = self.page()
        self.assertContains(response, 'class="st-row is-unresolved"')
        self.assertContains(response, "확인 필요")
        self.assertNotContains(response, reverse("students:detail", args=["99999"]))

    def test_scope_dropdown_has_classes_and_groups(self):
        response = self.page()
        self.assertContains(response, '<optgroup label="인트라넷 수업">')
        self.assertContains(response, 'value="class:201"')
        self.assertContains(response, '<optgroup label="EduTrack 반">')
        self.assertContains(response, f'value="group:{self.group.pk}" data-members="7102"')

    def test_get_query_still_filters_on_server(self):
        response = self.page(q="Ekamai")
        self.assertContains(response, "김지훈")
        self.assertNotContains(response, 'data-student-id="7102"')
        self.assertContains(response, "담당 학생 이름·번호·학교 검색")

    def test_live_filter_hooks_present(self):
        response = self.page()
        for marker in ["data-local-student-list", "data-local-scope", "data-local-q", "data-local-rows", "data-search="]:
            self.assertContains(response, marker)

    def add_many(self, count):
        TeacherStudentAccess.objects.bulk_create(
            TeacherStudentAccess(teacher=self.teacher, student_no=f"9{n:04d}", student_name=f"추가 학생 {n:03d}", assigned_by=self.admin)
            for n in range(1, count + 1)
        )

    def test_more_than_200_assigned_students_are_all_listed_with_the_true_total(self):
        self.add_many(205)
        response = self.page()
        self.assertEqual(response.content.decode().count('class="st-row'), 208)
        self.assertContains(response, "전체 담당 학생 (208명)")
        self.assertContains(response, 'data-student-id="90205"')

    def test_student_past_the_200th_is_found_by_the_server_filter(self):
        self.add_many(205)
        self.assertContains(self.page(q="추가 학생 205"), 'data-student-id="90205"')

    def test_search_text_is_escaped(self):
        response = self.page(q="<script>alert(1)</script>")
        self.assertNotContains(response, "<script>alert(1)</script>")
        self.assertContains(response, "&lt;script&gt;alert(1)&lt;/script&gt;")

    def test_admin_student_list_shows_students_without_searching(self):
        """학생 관리: 인트라넷처럼 들어오자마자 학생 목록(첫 쪽)이 보이고, 검색은 거르기용."""
        self.client.force_login(self.admin)
        response = self.page()
        self.assertContains(response, "학생 관리")
        self.assertContains(response, 'data-student-id="6333"')
        self.assertContains(response, 'data-student-id="7102"')
        self.assertContains(response, reverse("students:detail", args=["6333"]))
        from pathlib import Path
        from django.conf import settings
        js = (Path(settings.BASE_DIR) / "static/js/global/student-browser.js").read_text(encoding="utf-8")
        self.assertIn("mount(root.querySelector('[data-student-browser]'),{requireInput:false", js)

    def test_admin_directory_uses_remote_browser_without_checkboxes(self):
        self.client.force_login(self.admin)
        response = self.page()
        self.assertContains(response, "data-student-directory")
        self.assertContains(response, "data-browse-scope")
        self.assertContains(response, 'data-detail-url="' + reverse("students:detail", args=["__ID__"]) + '"')
        self.assertNotContains(response, "data-selector-page-all")
