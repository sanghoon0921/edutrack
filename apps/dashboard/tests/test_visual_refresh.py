"""Template/route and asset contracts; no database or auth-policy changes."""
from html.parser import HTMLParser
from pathlib import Path
from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import resolve, reverse
from apps.accounts.models import User

class Links(HTMLParser):
    def __init__(self):
        super().__init__(); self.hrefs=[]
    def handle_starttag(self, tag, attrs):
        if tag == "a": self.hrefs.append(dict(attrs).get("href", ""))

@override_settings(STUDENT_DATA_SOURCE="demo", ASSESSMENT_DATA_SOURCE="demo", CLASS_CATALOG_DATA_SOURCE="demo", ADMIN_AUTO_LINK_TEST_ACCOUNTS=False)
class VisualRefresh11Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.users={role:User.objects.create_user(username="refresh_"+role.lower(),password="QA-only",role=role) for role in ["ADMIN","TEACHER","STUDENT","PARENT"]}

    def test_profile_route_and_all_role_links_resolve(self):
        for role,user in self.users.items():
            with self.subTest(role=role):
                self.client.force_login(user)
                response=self.client.get(reverse("dashboard"))
                self.assertEqual(response.status_code,200)
                html=response.content.decode(); self.assertIn(reverse("profile"),html)
                part=html.split('<nav class="intranet-side-navigation"',1)[1].split('</nav>',1)[0]
                parser=Links(); parser.feed(part)
                self.assertGreater(len(parser.hrefs),5)
                for href in parser.hrefs:
                    self.assertTrue(href.startswith('/'),href)
                    resolve(href.split('?', 1)[0])  # 공지 하위 메뉴는 ?kind= 로 거름(11/10)
                self.assertIn(reverse('lms:rooms'),parser.hrefs)
                # 관리자·강사는 성적·제출현황을 반 화면 탭에서 엽니다(운영팀 요청 10.29). 학생·학부모 메뉴에는 그대로.
                if role in ('STUDENT','PARENT'): self.assertIn(reverse('lms:gradebook'),parser.hrefs)
                else: self.assertNotIn(reverse('lms:gradebook'),parser.hrefs)
                if role != 'PARENT': self.assertIn(reverse('lms:inbox'),parser.hrefs)
                else: self.assertNotIn(reverse('lms:inbox'),parser.hrefs)

    def test_lms_page_keeps_module_assets(self):
        self.client.force_login(self.users['TEACHER'])
        response=self.client.get(reverse('lms:rooms'))
        html=response.content.decode()
        self.assertEqual(response.status_code,200)
        self.assertIn('workspace.css',html)
        self.assertLess(html.index('workspace.css'),html.index('60-visual-refresh.css'))
        self.assertEqual(html.count('js/global/ui-shell.js'),1)
        self.assertNotIn('src="/static/js/app.js',html)

    def test_login_csrf_labels_password_are_kept(self):
        response=self.client.get(reverse('login'))
        for value in ['name="csrfmiddlewaretoken"','name="username"','name="password"','type="password"','autocomplete="current-password"','data-vr-password-toggle']:
            self.assertContains(response,value)

    def test_invalid_login_still_reports_error(self):
        response=self.client.post(reverse('login'),{'username':'doesnotexist','password':'bad'})
        self.assertContains(response,'role="alert"')
        self.assertContains(response,'아이디 또는 비밀번호를 다시 확인해 주세요.')

    def test_valid_login_and_post_logout_still_work(self):
        response=self.client.post(reverse('login'),{'username':'refresh_teacher','password':'QA-only'})
        self.assertEqual(response.status_code,302)
        self.assertEqual(self.client.get(reverse('dashboard')).status_code,200)
        self.assertEqual(self.client.get(reverse('logout')).status_code,405)
        self.assertEqual(self.client.post(reverse('logout')).status_code,302)
        self.assertEqual(self.client.get(reverse('dashboard')).status_code,302)

    def test_csrf_required(self):
        from django.test import Client
        client=Client(enforce_csrf_checks=True)
        self.assertEqual(client.post(reverse('login'),{'username':'refresh_teacher','password':'QA-only'}).status_code,403)

    def test_css_does_not_resize_annotation_geometry(self):
        css=(Path(settings.BASE_DIR)/'static/css/layers/60-visual-refresh.css').read_text()
        self.assertNotIn('.lms-paper{',css)
        self.assertIn('body.visual-refresh-body [hidden]',css)
        self.assertNotIn('all: unset',css)

    def test_enhancement_does_not_bind_lms_or_menu(self):
        js=(Path(settings.BASE_DIR)/'apps/accounts/static/accounts/js/login.js').read_text()
        self.assertNotIn('data-mobile-menu',js)
        self.assertNotIn('localStorage',js)
        self.assertNotIn('fetch(',js)
