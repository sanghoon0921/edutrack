"""글 속 주소를 파란 링크로(11/10 요청): static/js/global/linkify.js 의 나누기 규칙을 Node.js로 실제 실행해 확인합니다.
Node.js가 없는 컴퓨터에서는 건너뜁니다."""
import json
import shutil
import subprocess
from pathlib import Path
from unittest import skipUnless

from django.conf import settings
from django.test import SimpleTestCase, TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse

NODE = shutil.which('node')
HARNESS = Path(__file__).resolve().parent / 'js' / 'linkify_harness.js'
SCRIPT = Path(settings.BASE_DIR) / 'static' / 'js' / 'global' / 'linkify.js'


@skipUnless(NODE, 'Node.js가 없어 건너뜀')
class SplitTests(SimpleTestCase):
    def split(self, *texts):
        done = subprocess.run([NODE, str(HARNESS), str(SCRIPT), json.dumps(texts, ensure_ascii=False)],
                              capture_output=True, text=True, encoding='utf-8', timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)

    def links(self, text):
        return [(p['url'], p['href']) for p in self.split(text)[0] if 'url' in p]

    def test_url_between_korean_words(self):
        parts = self.split('참고: https://example.com/vocab 를 보세요.')[0]
        self.assertEqual(parts, [{'text': '참고: '}, {'url': 'https://example.com/vocab', 'href': 'https://example.com/vocab'},
                                 {'text': ' 를 보세요.'}])

    def test_trailing_punctuation_and_brackets_stay_outside(self):
        self.assertEqual(self.links('링크 https://a.com/x.'), [('https://a.com/x', 'https://a.com/x')])
        self.assertEqual(self.links('(https://a.com/x)'), [('https://a.com/x', 'https://a.com/x')])
        self.assertEqual(self.links('https://en.wikipedia.org/wiki/Foo_(bar)'),
                         [('https://en.wikipedia.org/wiki/Foo_(bar)', 'https://en.wikipedia.org/wiki/Foo_(bar)')])

    def test_korean_right_after_the_url_is_not_part_of_it(self):
        self.assertEqual(self.links('https://a.com/q?x=1에서 확인'), [('https://a.com/q?x=1', 'https://a.com/q?x=1')])

    def test_www_gets_https(self):
        self.assertEqual(self.links('www.veteransedu.co.kr 참고'), [('www.veteransedu.co.kr', 'https://www.veteransedu.co.kr')])

    def test_no_script_links_and_plain_text_untouched(self):
        self.assertEqual(self.split('javascript:alert(1)', '주소 없음')[0:2], [[{'text': 'javascript:alert(1)'}], [{'text': '주소 없음'}]])


class LoadedOnEveryPageTests(TestCase):
    def test_base_layout_loads_linkify(self):
        user = get_user_model().objects.create_user('lk_admin', password='x', role='ADMIN')
        self.client.force_login(user)
        self.assertContains(self.client.get(reverse('communications:notice-list')), 'js/global/linkify.js')
