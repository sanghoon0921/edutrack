"""11/11 요청: 학생 관리에서 인트라넷 학생 전체를 쪽 번호로 이동하며 봅니다(7천 명 = 약 148쪽이라 이전·다음만으로는 힘듦).
테스트 서버(가짜 자료)도 쪽 넘김을 시험할 수 있게 가짜 학생을 더 둡니다(실제 학생 정보는 외부 링크에 올리지 않음)."""
import json
import shutil
import subprocess
from pathlib import Path
from unittest import skipUnless

from django.conf import settings
from django.test import SimpleTestCase

NODE = shutil.which('node')
HARNESS = Path(__file__).resolve().parent / 'js' / 'page_list_harness.js'
SCRIPT = Path(settings.BASE_DIR) / 'static' / 'js' / 'global' / 'student-browser.js'


@skipUnless(NODE, 'Node.js가 없어 건너뜀')
class PageListTests(SimpleTestCase):
    def pages(self, *cases):
        done = subprocess.run([NODE, str(HARNESS), str(SCRIPT), json.dumps(cases)], capture_output=True, text=True, encoding='utf-8', timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)

    def test_pages_show_in_blocks_of_ten(self):
        # 11/11 2차: 1~10을 보여 주고, 10을 넘어가면 11~20 (인트라넷 학생 리스트와 같게)
        self.assertEqual(self.pages([1, 148], [10, 148], [11, 148], [148, 148]), [
            list(range(1, 11)), list(range(1, 11)), list(range(11, 21)), list(range(141, 149)),
        ])

    def test_few_pages_show_every_number(self):
        self.assertEqual(self.pages([2, 5], [1, 1]), [[1, 2, 3, 4, 5], [1]])


class TemplateAndShareDataTests(SimpleTestCase):
    def test_directory_pager_has_a_place_for_page_numbers(self):
        html = (Path(settings.BASE_DIR) / 'templates/components/student_filters.html').read_text(encoding='utf-8')
        self.assertIn('data-browse-pages', html)

    def test_fake_students_for_the_test_server(self):
        from apps.students.repositories import extra_demo_students
        extra = extra_demo_students(320)
        self.assertEqual(len(extra), 320)
        self.assertEqual(len({s.student_id for s in extra}), 320)
        self.assertTrue(all(s.student_id.startswith('9') for s in extra))
        share = (Path(settings.BASE_DIR) / 'config/settings/share.py').read_text(encoding='utf-8')
        self.assertIn('DEMO_EXTRA_STUDENTS = 320', share)
