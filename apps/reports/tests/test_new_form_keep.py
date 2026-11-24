"""11/10 요청: 새 리포트카드에서 양식·수업 유형·기간·제목을 먼저 고른 뒤 반을 골라도 입력이 그대로 남습니다.
(반을 고르면 그 반의 인트라넷 수업·모의고사 목록을 다시 읽느라 화면을 새로 여는데, 그때 입력값을 주소에 실어 보냅니다.)"""
import re

from django.urls import reverse

from apps.reports.tests.test_views import ReportFixture


class KeepInputTests(ReportFixture):
    def test_values_in_the_address_fill_the_form(self):
        self.client.force_login(self.admin)
        html = self.client.get(reverse('reports:new'), {
            'group': self.group.pk, 'form': 'TOEFL', 'course_type': '특강',
            'period_start': '2026-11-02', 'period_end': '2026-11-06'}).content.decode()
        self.assertRegex(html, r'<input[^>]*value="TOEFL"[^>]*checked|<input[^>]*checked[^>]*value="TOEFL"')
        self.assertRegex(html, r'<input[^>]*value="특강"[^>]*checked|<input[^>]*checked[^>]*value="특강"')
        self.assertRegex(html, r'name="period_start"[^>]*value="2026-11-02"|value="2026-11-02"[^>]*name="period_start"')

    def test_group_change_script_carries_the_inputs(self):
        from pathlib import Path
        from django.conf import settings
        js = (Path(settings.BASE_DIR) / 'apps/reports/static/reports/js/report-card.js').read_text(encoding='utf-8')
        self.assertIn('KEEP_ON_GROUP_CHANGE', js)
