"""11/11 요청(인트라넷 '학생 리스트' PDF 참고): 학생 관리 기본 20명, 20/50/100명 드롭다운, 쪽 이동은 맨 아래 가운데.
표 모양은 인트라넷처럼 번호·학생번호·이름(파란 링크)·지점·학년·학교·국가·도시·상태·듣는 수업."""
import re
from dataclasses import replace
from unittest.mock import patch

from django.urls import reverse

from apps.lms.tests.test_lms import LmsFixture
from apps.students.repositories import DEMO_STUDENTS


def many(n):
    return tuple(replace(DEMO_STUDENTS[0], student_id=str(i + 10000), name=f'학생{i:03}') for i in range(n))


class DirectoryPageSizeTests(LmsFixture):
    def browse(self, **query):
        self.login(self.admin)
        return self.client.get(reverse('students:selector-browse'), query).json()

    def test_size_param_controls_rows_and_pages(self):
        with patch('apps.students.bulk_selector.DEMO_STUDENTS', many(125)):
            r = self.browse(size='20', page='2')
            self.assertEqual((len(r['results']), r['pages'], r['page_size']), (20, 7, 20))
            self.assertEqual(r['results'][0]['name'], '학생020')
            r = self.browse(size='100', page='2')
            self.assertEqual((len(r['results']), r['pages']), (25, 2))

    def test_unknown_size_falls_back_to_the_usual_page(self):
        with patch('apps.students.bulk_selector.DEMO_STUDENTS', many(125)):
            r = self.browse(size='7')
            self.assertEqual((len(r['results']), r['page_size']), (50, 50))

    def test_admin_directory_starts_with_20_rows_in_a_table(self):
        self.login(self.admin)
        with patch('apps.students.bulk_selector.DEMO_STUDENTS', many(125)):
            html = self.client.get(reverse('students:list')).content.decode()
        body = html.split('<tbody', 1)[1].split('</tbody>', 1)[0]
        self.assertEqual(body.count('<tr'), 20)
        for head in ('번호', '학생번호', '이름', '지점', '학년', '학교', '국가', '도시', '상태', '듣는 수업'):
            self.assertIn(f'>{head}</th>', html)
        self.assertIn('class="st-dir-name"', body)
        self.assertIn('총 <b>125</b>명', html)

    def test_size_dropdown_and_pager_below_the_table(self):
        self.login(self.admin)
        html = self.client.get(reverse('students:list'), {'size': '50'}).content.decode()
        select = re.search(r'<select[^>]*data-page-size[^>]*>(.*?)</select>', html, re.S).group(1)
        self.assertEqual(re.findall(r'value="(\d+)"', select), ['20', '50', '100'])
        self.assertRegex(select, r'value="50"[^>]*selected')
        self.assertLess(html.index('</table>'), html.index('data-directory-pager'))
