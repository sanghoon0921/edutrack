"""실행 모드(demo/real/test) 설정이 서로 섞이지 않는지 확인합니다."""
import importlib
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


def load(name):
    return importlib.import_module(f"config.settings.{name}")


class SettingsModeTests(SimpleTestCase):
    def test_demo_uses_fake_data_and_demo_folder(self):
        demo = load("demo")
        self.assertEqual(
            (demo.STUDENT_DATA_SOURCE, demo.ASSESSMENT_DATA_SOURCE, demo.CLASS_CATALOG_DATA_SOURCE),
            ("demo", "demo", "demo"),
        )
        self.assertEqual(Path(demo.DATABASES["default"]["NAME"]).parts[-3:], ("data", "demo", "db.sqlite3"))
        self.assertEqual(Path(demo.MEDIA_ROOT).parts[-3:], ("data", "demo", "media"))

    def test_test_mode_uses_fake_data_and_own_media(self):
        self.assertEqual((settings.STUDENT_DATA_SOURCE, settings.ASSESSMENT_DATA_SOURCE), ("demo", "demo"))
        self.assertEqual(Path(settings.MEDIA_ROOT).parts[-3:], ("data", "test", "media"))

    def test_default_mode_is_demo(self):
        root = Path(settings.BASE_DIR)
        for name in ["manage.py", "config/wsgi.py", "config/asgi.py"]:
            self.assertIn('"config.settings.demo"', (root / name).read_text(encoding="utf-8"), name)

    def test_powershell_scripts_have_utf8_bom(self):
        scripts = sorted((Path(settings.BASE_DIR) / "scripts").glob("*.ps1"))
        self.assertEqual([p.name for p in scripts], ["run.ps1", "setup.ps1", "share.ps1", "test.ps1"])
        for path in scripts:
            self.assertTrue(path.read_bytes().startswith(b"\xef\xbb\xbf"), path.name)

    def test_powershell_scripts_enable_python_utf8_mode(self):
        # 테스트 일부와 코드가 인코딩 지정 없이 UTF-8 파일을 읽으므로, 한국어 Windows(cp949)에서도 같은 결과가 나오게 합니다.
        for name in ["run.ps1", "setup.ps1", "share.ps1", "test.ps1"]:
            text = (Path(settings.BASE_DIR) / "scripts" / name).read_text(encoding="utf-8-sig")
            self.assertIn('$env:PYTHONUTF8 = "1"', text, name)
