"""UI V2 contract regressions. Visual geometry is audited separately in Chromium."""
from pathlib import Path
from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse
from apps.accounts.models import User, StudentAccountLink
from apps.operations.models import TeacherStudentAccess


@override_settings(STUDENT_DATA_SOURCE="demo", ASSESSMENT_DATA_SOURCE="demo", CLASS_CATALOG_DATA_SOURCE="demo", ADMIN_AUTO_LINK_TEST_ACCOUNTS=False)
class IntranetV2ContractTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.users={}
        for role in ["ADMIN","TEACHER","STUDENT","PARENT"]:
            cls.users[role]=User.objects.create_user(username="ui2_"+role.lower(),password="local-test-only",role=role)
        for role,rel in [("STUDENT",StudentAccountLink.Relationship.SELF),("PARENT",StudentAccountLink.Relationship.PARENT)]:
            StudentAccountLink.objects.create(user=cls.users[role],student_no="6333",relationship=rel,is_primary=True,is_active=True)
        TeacherStudentAccess.objects.create(teacher=cls.users["TEACHER"],student_no="6333",student_name="김지훈",assigned_by=cls.users["ADMIN"])

    def dashboard(self,role="ADMIN"):
        self.client.force_login(self.users[role])
        return self.client.get(reverse("dashboard"))

    def test_four_roles_keep_their_dashboard(self):
        for role in self.users:
            with self.subTest(role=role):
                self.assertContains(self.dashboard(role),'data-ui-version="intranet-v2"')

    def test_new_css_is_the_last_common_stylesheet(self):
        html=self.dashboard().content.decode()
        links=[line for line in html.splitlines() if 'rel="stylesheet"' in line]
        self.assertIn('css/layers/99-unify.css',links[-1])  # 11/19 마지막 층: 페이지 통일
        self.assertIn('css/layers/98-refine.css',links[-2])  # 11/10 디자인 층은 그 바로 앞
        self.assertIn('css/layers/97-polish.css',links[-3])
        self.assertIn('css/layers/95-portal-focus.css',links[-4])
        self.assertIn('css/layers/80-readability.css',html)
        self.assertIn('css/layers/90-usability.css',html)
        self.assertIn('css/layers/50-intranet-theme.css',html)
        self.assertLess(html.index('css/layers/50-intranet-theme.css'), html.index('css/layers/60-visual-refresh.css'))
        self.assertNotIn('css/intranet_2026.css',html)

    def test_new_script_does_not_double_bind_v1_navigation(self):
        html=self.dashboard().content.decode()
        self.assertIn('js/global/ui-shell.js',html)
        self.assertNotIn('src="/static/js/app.js',html)

    def test_login_uses_versioned_assets(self):
        response=self.client.get(reverse("login"))
        self.assertContains(response,'50-intranet-theme.css')
        self.assertContains(response,'?v=20261008-r2')
        self.assertContains(response,'name="csrfmiddlewaretoken"')

    def test_legacy_header_pseudo_element_is_disconnected(self):
        html=self.dashboard().content.decode()
        self.assertIn('class="intranet-topbar"',html)
        self.assertNotIn('intranet-topbar premium-site-header',html)

    def test_keyboard_navigation_and_mobile_close_controls_exist(self):
        response=self.dashboard()
        for value in ['intranet-skip-link','id="main-content"','data-mobile-menu-close','aria-controls="primary-navigation"','aria-current="page"']:
            self.assertContains(response,value)

    def test_logout_keeps_post_and_csrf(self):
        response=self.dashboard()
        self.assertContains(response,'method="post" action="'+reverse("logout")+'"')
        self.assertContains(response,'name="csrfmiddlewaretoken"')
        self.assertEqual(self.client.get(reverse("logout")).status_code,405)

    def test_teacher_assignment_hidden_form_and_assets_are_preserved(self):
        self.client.force_login(self.users['TEACHER'])
        response=self.client.get(reverse('operations:teacher-student-assignment'))
        self.assertContains(response,'<form hidden data-assignment-csrf>')
        self.assertContains(response,'teacher-assignment.js')
        self.assertContains(response,'data-assignment-search-input')

    def test_student_does_not_receive_admin_controls(self):
        self.client.force_login(self.users['STUDENT'])
        self.assertEqual(self.client.get(reverse('operations:user-list')).status_code,403)
        self.assertNotContains(self.client.get(reverse('dashboard')),'class="intranet-topbar-search"')

    def test_visual_guardrails_are_explicit_and_scoped(self):
        css=(Path(settings.BASE_DIR)/'static/css/layers/50-intranet-theme.css').read_text(encoding='utf-8')
        self.assertIn('body.intranet-app-body [hidden]',css)
        self.assertIn('body.intranet-app-body .premium-dashboard-brief',css)
        self.assertIn('content: none !important',css)
        self.assertIn('prefers-reduced-motion',css)
        self.assertIn('max-width: 1024px',css)
