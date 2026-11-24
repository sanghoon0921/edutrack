"""Readability contracts. Production data, routes and document marks are not rewritten."""
import colorsys
import re
from pathlib import Path
from django.conf import settings
from django.test import TestCase, SimpleTestCase, override_settings
from django.urls import reverse
from apps.accounts.models import User
from apps.lms.documents import clean_annotations

STYLE_NAMES = (
 'css/layers/00-base.css','css/layers/10-premium-portal.css','css/layers/20-workflow.css','css/layers/30-stability.css',
 'css/layers/40-navigation-editor.css','css/layers/50-intranet-theme.css','css/layers/60-visual-refresh.css','css/layers/80-readability.css',
 'css/components/student-transfer-selector.css','css/components/learning-overview.css','css/components/compact-pages.css',
 'dashboard/css/class-catalog.css','lms/css/workspace.css','css/layers/97-polish.css','css/layers/98-refine.css','css/layers/99-unify.css','css/components/quiz.css','reports/css/report-card.css',
)

def green(rgb):
    r,g,b=[v/255 for v in rgb]
    h,l,s=colorsys.rgb_to_hls(r,g,b)
    return 67 <= h*360 <= 195 and s > .01 and g > r+.005

class ReadabilityAssetTests(SimpleTestCase):
    def path(self,name):
        from django.contrib.staticfiles import finders
        found=finders.find(name)
        self.assertIsNotNone(found,name)
        return Path(found)

    def test_active_css_has_no_green_literal(self):
        for name in STYLE_NAMES:
            css=self.path(name).read_text(encoding='utf-8')
            css=re.sub(r'/\*.*?\*/','',css,flags=re.S)
            colors=[]
            for m in re.finditer(r'#([\da-f]{8}|[\da-f]{6}|[\da-f]{4}|[\da-f]{3})(?![\w-])',css,re.I):
                hexval=m[1]
                if len(hexval) in (3,4): hexval=''.join(c*2 for c in hexval)
                colors.append((m[0],[int(hexval[i:i+2],16) for i in (0,2,4)]))
            for m in re.finditer(r'rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)',css,re.I):
                colors.append((m[0],[int(m[i]) for i in (1,2,3)]))
            with self.subTest(file=name):
                self.assertEqual([c for c,rgb in colors if green(rgb)],[])

    def test_no_classic_serif_in_ui_font_declarations(self):
        for name in STYLE_NAMES:
            text=self.path(name).read_text(encoding='utf-8')
            fonts=re.findall(r'font-family\s*:\s*([^;}]+)',text,re.I)
            with self.subTest(file=name):
                self.assertFalse(any(re.search(r'Georgia|Times New Roman|(?<![\w-])serif\b',x,re.I) for x in fonts))

    def test_no_sub_14px_absolute_ui_fonts(self):
        for name in STYLE_NAMES:
            text=self.path(name).read_text(encoding='utf-8')
            sizes=re.findall(r'font-size\s*:\s*([\d.]+)px',text)
            with self.subTest(file=name):self.assertFalse([x for x in sizes+re.findall(r'--fs-[a-z0-9]+\s*:\s*([\d.]+)px',text) if float(x)<12])  # 12px: 보조 글씨(사용자 요청 11/10 '전체 글꼴 축소', 전에는 10/26 13px)

    def test_font_stack_has_offline_korean_fallback(self):
        css=self.path('css/layers/80-readability.css').read_text(encoding='utf-8')
        for text in ['"Malgun Gothic"','"Noto Sans CJK KR"','sans-serif','font-size: 16px !important']:
            self.assertIn(text,css)
        self.assertNotIn('@import',css)
        self.assertNotIn('@font-face',css)
        self.assertNotIn('url(',css)

    def test_annotation_geometry_is_not_overridden(self):
        css=self.path('css/layers/80-readability.css').read_text(encoding='utf-8')
        self.assertNotRegex(css,r'\.lms-paper\s*\{')
        self.assertNotRegex(css,r'#ann-overlay\b[^{}]*\{')
        self.assertNotIn('all: unset',css)
        self.assertIn('input[type=hidden]',css)

    def test_user_selected_green_annotation_stays_supported(self):
        mark={'id':'00000000-0000-4000-8000-000000000001','type':'point','page':1,
              'x':.2,'y':.3,'w':0,'h':0,'color':'#16a34a','size':16,'text':'원본 첨삭 색상','points':[]}
        result=clean_annotations([mark],1)
        self.assertEqual(result[0]['color'],'#16a34a')
        self.assertEqual(result[0]['size'],16)

@override_settings(STUDENT_DATA_SOURCE='demo',ASSESSMENT_DATA_SOURCE='demo',CLASS_CATALOG_DATA_SOURCE='demo',ADMIN_AUTO_LINK_TEST_ACCOUNTS=False)
class ReadabilityPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.users={r:User.objects.create_user('readability_'+r,password='qa-only',role=r) for r in ('ADMIN','TEACHER','STUDENT','PARENT')}

    def test_each_role_loads_final_styles_once(self):
        for user in self.users.values():
            self.client.force_login(user)
            for name in ['dashboard','lms:rooms','lms:gradebook']:
                with self.subTest(role=user.role,name=name):
                    response=self.client.get(reverse(name))
                    self.assertContains(response,'data-readability-version="2"')
                    html=response.content.decode()
                    self.assertEqual(html.count('css/layers/80-readability.css'),1)
                    styles=re.findall(r'<link[^>]+rel="stylesheet"[^>]*>',html)
                    self.assertIn('99-unify.css',styles[-1])
                    self.assertIn('98-refine.css',styles[-2])
                    self.assertIn('97-polish.css',styles[-3])
                    self.assertIn('95-portal-focus.css',styles[-4])
                    self.assertLess(html.index('80-readability.css'),html.index('95-portal-focus.css'))
                    self.assertLess(html.index('90-usability.css'),html.index('95-portal-focus.css'))
                    for style in styles:self.assertIn('?v=',style)

    def test_login_uses_readable_ui(self):
        for name in ['login']:
            with self.subTest(name=name):
                response=self.client.get(reverse(name))
                self.assertContains(response,'data-readability-version="2"')
                self.assertContains(response,'name="csrfmiddlewaretoken"')
                self.assertContains(response,'name="username"')
                self.assertContains(response,'name="password"')
                self.assertNotContains(response,'cinematic-login.css')
                self.assertNotContains(response,'login-hero.css')

    def test_student_keeps_hidden_staff_controls(self):
        self.client.force_login(self.users['STUDENT'])
        self.assertEqual(self.client.get(reverse('operations:user-list')).status_code,403)
        self.assertNotContains(self.client.get(reverse('dashboard')),'class="intranet-topbar-search"')

    def test_header_interactions_and_post_logout_kept(self):
        self.client.force_login(self.users['TEACHER'])
        response=self.client.get(reverse('dashboard'))
        for marker in ['data-mobile-menu-button','data-mobile-menu-close','ui-shell.js','method="post" action="'+reverse('logout')+'"']:
            self.assertContains(response,marker)
        self.assertEqual(self.client.get(reverse('logout')).status_code,405)
        self.assertEqual(self.client.post(reverse('logout')).status_code,302)

    def test_invalid_login_still_reports_error(self):
        response=self.client.post(reverse('login'),{'username':'bad','password':'bad'})
        self.assertContains(response,'role="alert"')
        self.assertContains(response,'아이디 또는 비밀번호를 다시 확인해 주세요.')

    def test_valid_login_still_preserves_next(self):
        response=self.client.post(reverse('login'),{'username':'readability_TEACHER','password':'qa-only'})
        self.assertEqual(response.status_code,302)
        self.assertEqual(self.client.get(reverse('lms:rooms')).status_code,200)
