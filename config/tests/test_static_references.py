"""모든 화면(HTML)의 {% static %} 경로가 실제 파일을 가리키는지 확인합니다.

CSS/JS 파일 이름을 바꾸거나 옮긴 뒤 이 테스트가 실패하면, 실패 메시지에 나온 화면의 경로를 고치세요.
"""
import re
from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles import finders
from django.test import SimpleTestCase

STATIC_TAG = re.compile(r"""\{%\s*static\s+['"]([^'"]+)['"]\s*%\}""")


def template_files():
    root = Path(settings.BASE_DIR)
    yield from (root / "templates").rglob("*.html")
    yield from root.glob("apps/*/templates/**/*.html")


class StaticReferenceTests(SimpleTestCase):
    def test_every_static_reference_exists(self):
        missing = []
        for path in template_files():
            for ref in STATIC_TAG.findall(path.read_text(encoding="utf-8")):
                if not finders.find(ref):
                    missing.append(f"{path.relative_to(settings.BASE_DIR).as_posix()}: {ref}")
        self.assertEqual(missing, [])

    def test_base_layout_loads_css_layers_in_number_order(self):
        base = (Path(settings.BASE_DIR) / "templates/layouts/base.html").read_text(encoding="utf-8")
        numbers = re.findall(r"css/layers/(\d\d)-", base)
        self.assertEqual(len(numbers), 14)  # 11/19: 99-unify 추가
        self.assertEqual(numbers, sorted(numbers))
