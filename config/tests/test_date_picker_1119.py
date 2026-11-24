"""11/19 날짜 입력: '오늘 밤·내일 밤·1주 뒤' 단추를 없애고, 날짜 칸을 누르면 바로 아래에 달력이 열립니다(외부 라이브러리 없음)."""
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

BASE = Path(settings.BASE_DIR)


class DatePickerTests(SimpleTestCase):
    def test_quick_date_buttons_are_gone(self):
        js = (BASE / 'static/js/global/form-usability.js').read_text(encoding='utf-8')
        for gone in ('오늘 밤', '내일 밤', '1주 뒤', 'ux-date-tools'):
            self.assertNotIn(gone, js)

    def test_form_usability_keeps_strict_mode_first(self):
        js = (BASE / 'static/js/global/form-usability.js').read_text(encoding='utf-8')
        body = js.split('(() => {', 1)[1].lstrip()
        self.assertTrue(body.startswith("'use strict';"))

    def test_base_loads_the_date_picker(self):
        base = (BASE / 'templates/layouts/base.html').read_text(encoding='utf-8')
        self.assertIn("js/global/date-picker.js", base)

    def test_date_picker_handles_date_and_datetime_without_external_assets(self):
        js = (BASE / 'static/js/global/date-picker.js').read_text(encoding='utf-8')
        self.assertIn('input[type=date]', js)
        self.assertIn('input[type=datetime-local]', js)
        self.assertNotIn('http', js)
        for needed in ("'dialog'", 'Escape', "'change'", 'min', 'max'):
            self.assertIn(needed, js)
