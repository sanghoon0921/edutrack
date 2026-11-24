"""공용 거르기 막대·한 줄 행이 학생 선택 화면에 쓰이는지 확인한다."""
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.operations.models import TeacherStudentAccess


def asset(path):
    return (Path(settings.BASE_DIR) / path).read_text(encoding="utf-8")


class PickerAssetTests(SimpleTestCase):
    def test_browser_has_shared_row_scope_and_ime_safe_input(self):
        js = asset("static/js/global/student-browser.js")
        # 즉시 검색의 한글 입력 동작은 test_student_browser_script.py 가 실제로 실행해 확인한다
        for text in ["function row(", "function scopeOf(", "function liveInput(", "compositionend",
                     "data-browse-scope", "requireInput", "setScope", "'인트라넷 수업'", "'EduTrack 반'", "data-class-find",
                     "data-browse-retry"]:
            self.assertIn(text, js)
        for text in ["data-browse-source", "data-browse-search", "data-class-state"]:
            self.assertNotIn(text, js)

    def test_transfer_selector_draws_rows_with_shared_row(self):
        js = asset("static/js/components/student-transfer-selector.js")
        self.assertIn("window.EduStudentBrowser.row(", js)
        self.assertNotIn("ux-student-row", js)

    def test_double_click_moves_a_student_to_the_other_list(self):
        js = asset("static/js/components/student-transfer-selector.js")
        self.assertIn("'dblclick'", js)
        self.assertIn("side==='result'", js)

    def test_one_bulk_add_button_and_class_autofill(self):
        js = asset("static/js/components/student-transfer-selector.js")
        filters = asset("templates/components/student_filters.html")
        self.assertNotIn("data-selector-page-all", filters)
        self.assertIn("검색된 학생 모두 추가", filters)
        self.assertIn("autoFill", js)

    def test_select_all_checkbox_on_both_lists(self):
        # 학생 추가: 하나씩 고르지 않아도 되게, 조회된 학생·선택된 학생 위에 '전체 선택' 체크칸.
        html = asset("templates/components/student_transfer_selector.html")
        js = asset("static/js/components/student-transfer-selector.js")
        self.assertIn('data-selector-all="result"', html)
        self.assertIn('data-selector-all="selected"', html)
        self.assertIn("[data-selector-all]", js)
        self.assertIn("indeterminate", js)

    def test_transfer_selector_shows_failure_notice_in_the_result_list(self):
        js = asset("static/js/components/student-transfer-selector.js")
        self.assertIn("meta?.error", js)
        self.assertIn("errorBox(", js)

    def test_row_styles_are_one_line_with_narrow_fallback(self):
        css = asset("static/css/layers/90-usability.css")
        for text in [".st-row", ".st-head", ".st-more", "@container", "container-type:inline-size"]:
            self.assertIn(text, css)
        self.assertNotIn("ux-student-row", css)

    def test_changed_assets_have_new_version(self):
        base = asset("templates/layouts/base.html")
        self.assertIn("js/global/student-browser.js' %}?v=1111d", base)
        self.assertIn("css/layers/90-usability.css' %}?v=1110nv3", base)


@override_settings(STUDENT_DATA_SOURCE="demo", CLASS_CATALOG_DATA_SOURCE="demo")
class PickerPageTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_user("ui_admin", password="x-Ui!2026", role="ADMIN")
        self.teacher = User.objects.create_user("ui_teacher", password="x-Ui!2026", role="TEACHER")
        TeacherStudentAccess.objects.create(teacher=self.teacher, student_no="6333", student_name="김지훈", assigned_by=self.admin)

    def test_selector_pages_use_scope_dropdown_without_search_button(self):
        pages = [(self.admin, "assignments:create"), (self.admin, "learning:quiz-create"),
                 (self.admin, "learning:discussion-create"), (self.teacher, "classroom:board-create")]
        for user, name in pages:
            with self.subTest(page=name):
                self.client.force_login(user)
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "data-browse-scope")
                self.assertContains(response, "data-browse-q")
                self.assertNotContains(response, "data-browse-source")
                self.assertNotContains(response, "data-browse-search")
                self.assertContains(response, "js/components/student-transfer-selector.js?v=ux6")
