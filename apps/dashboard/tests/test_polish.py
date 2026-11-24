"""디자인 다듬기: 메뉴 아이콘·색 구역, 마지막 다듬기 CSS, 제목 위 영문 라벨 제거, 관리자 홈 할 일, 미완성 메뉴 연결."""
import re
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.assignments.models import Assignment, AssignmentRecipient, Submission
from apps.communications.models import Notice

ICON_RE = re.compile(r'<use href="#i-([a-z-]+)"')


@override_settings(STUDENT_DATA_SOURCE="demo", ASSESSMENT_DATA_SOURCE="demo", CLASS_CATALOG_DATA_SOURCE="demo")
class PolishShellTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.users = {role: User.objects.create_user(f"polish_{role.lower()}", password="x-Polish!2026", role=role)
                     for role in ("ADMIN", "TEACHER", "STUDENT", "PARENT")}

    def test_every_menu_link_has_an_icon_and_a_colour_area(self):
        for role, user in self.users.items():
            self.client.force_login(user)
            response = self.client.get(reverse("dashboard"))
            items = [child for item in response.context["sidebar_navigation"]
                     for child in (item.get("children") or [item])]
            with self.subTest(role=role):
                self.assertTrue(items)
                self.assertEqual([i["label"] for i in items if not i.get("icon") or not i.get("area")], [])
                html = response.content.decode()
                sprite_ids = set(re.findall(r'<symbol id="i-([a-z-]+)"', html))
                used = set(ICON_RE.findall(html))
                self.assertTrue(used)
                self.assertEqual(used - sprite_ids, set())

    def test_icon_sprite_takes_no_space_above_the_page(self):
        self.client.force_login(self.users["STUDENT"])
        html = self.client.get(reverse("dashboard")).content.decode()
        sprite = re.search(r'<svg[^>]*class="et-icon-sprite"[^>]*>', html)[0]
        self.assertIn('width="0"', sprite)
        self.assertIn('height="0"', sprite)
        self.assertIn("position:absolute", sprite)

    def test_each_page_tells_its_colour_area(self):
        self.client.force_login(self.users["TEACHER"])
        for name, area in [("dashboard", "home"), ("assignments:list", "learning"), ("lms:inbox", "messages"),
                           ("communications:notice-list", "notices"), ("students:list", "students"),
                           ("lms:gradebook", "grades"), ("classroom:board-list", "learning")]:  # 과목 자료는 강사 메뉴에서 반별 학습 아래(10/29)
            with self.subTest(page=name):
                self.assertContains(self.client.get(reverse(name)), f'data-area="{area}"')

    def test_polish_layer_is_the_last_stylesheet(self):
        self.client.force_login(self.users["STUDENT"])
        html = self.client.get(reverse("dashboard")).content.decode()
        styles = re.findall(r'<link[^>]+rel="stylesheet"[^>]*>', html)
        self.assertIn("99-unify.css?v=", styles[-1])  # 11/19: 99-unify 가 마지막 층
        self.assertIn("98-refine.css?v=", styles[-2])  # 11/10: 98-refine 은 97-polish 뒤
        self.assertIn("97-polish.css?v=", styles[-3])

    def test_no_kicker_labels_above_headings(self):
        roots = [Path(settings.BASE_DIR) / "templates", Path(settings.BASE_DIR) / "apps"]
        found = [str(p) for root in roots for p in root.rglob("*.html") if 'class="eyebrow"' in p.read_text(encoding="utf-8")]
        self.assertEqual(found, [])

    def test_placeholder_admin_pages_lead_to_real_screens(self):
        self.client.force_login(self.users["ADMIN"])
        self.assertRedirects(self.client.get(reverse("admin_students")), reverse("students:list"), fetch_redirect_response=False)
        self.assertRedirects(self.client.get(reverse("admin_operations")), reverse("communications:notice-manage"), fetch_redirect_response=False)


@override_settings(STUDENT_DATA_SOURCE="demo", ASSESSMENT_DATA_SOURCE="demo", CLASS_CATALOG_DATA_SOURCE="demo")
class AdminHomeWorkQueueTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("home_admin", password="x-Home!2026", role="ADMIN")
        self.teacher = User.objects.create_user("home_teacher", password="x-Home!2026", role="TEACHER")
        soon = timezone.now() + timedelta(days=2)
        done = Assignment.objects.create(title="에세이", description="", due_at=soon, created_by=self.teacher)
        Assignment.objects.create(title="단어", description="", due_at=timezone.now() + timedelta(days=30), created_by=self.teacher)
        recipient = AssignmentRecipient.objects.create(assignment=done, student_id="6333", student_name="김지훈")
        Submission.objects.create(recipient=recipient, submitted_at=timezone.now())
        Notice.objects.create(title="이번 주 공지", content="본문", created_by=self.admin, is_published=True,
                              for_admin=True, for_teacher=True, for_student=True, for_parent=True)
        self.client.force_login(self.admin)

    def test_admin_home_lists_real_work_instead_of_static_labels(self):
        response = self.client.get(reverse("dashboard"))
        queue = response.context["admin_home"]["queue"]
        counts = {row["key"]: row["count"] for row in queue}
        self.assertEqual(counts["feedback"], 1)
        self.assertEqual(counts["due_week"], 1)
        self.assertEqual(counts["notices_week"], 1)
        for text in ["채점할 제출", "이번 주 마감 과제", "최근 7일 공지"]:
            self.assertContains(response, text)
        for gone in ["QUICK ACCESS", "STP 기준 조회", "premium-link-number"]:
            self.assertNotContains(response, gone)

    def test_home_notice_list_names_academy_notices(self):
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, "학원 공지")


class ClassListRowTests(TestCase):
    def test_class_rows_do_not_shrink_and_cut_their_second_line(self):
        # 담당 학생 지정 ① 수업 찾기: 높이가 정해진 세로 목록에서 줄이 눌려 두 번째 줄이 잘리지 않게(줄어들지 않음).
        css = (Path(settings.BASE_DIR) / "static/css/layers/97-polish.css").read_text(encoding="utf-8")
        rule = re.search(r"\.portal-class-panel \.portal-class-row \{([^}]*)\}", css)
        self.assertIsNotNone(rule)
        self.assertIn("flex: 0 0 auto", rule.group(1))
