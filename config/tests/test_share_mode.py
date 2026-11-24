"""share 모드(운영팀 외부 공유, 가짜 데이터): 설정 값, 업로드 파일 내보내기, 테스트용 사본 만들기."""
import importlib
import sqlite3
import tempfile
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, TestCase, override_settings

from config.share_copy import ShareCopyError, make_share_copy


def run_sql(path, *statements):
    # Windows는 열린 DB 파일을 지우지 못하므로 매번 닫는다(with sqlite3.connect 는 닫지 않음)
    db = sqlite3.connect(path)
    try:
        for statement in statements:
            db.execute(statement)
        db.commit()
    finally:
        db.close()


def share_settings():
    return importlib.import_module("config.settings.share")


class ShareSettingsTests(SimpleTestCase):
    def test_tunnel_address_is_accepted_and_error_details_are_hidden(self):
        s = share_settings()
        self.assertFalse(s.DEBUG)
        self.assertIn(".trycloudflare.com", s.ALLOWED_HOSTS)
        self.assertIn("https://*.trycloudflare.com", s.CSRF_TRUSTED_ORIGINS)
        self.assertEqual(s.SECURE_PROXY_SSL_HEADER, ("HTTP_X_FORWARDED_PROTO", "https"))

    def test_uses_fake_data_and_its_own_copy_never_the_real_db(self):
        s = share_settings()
        self.assertEqual((s.STUDENT_DATA_SOURCE, s.ASSESSMENT_DATA_SOURCE, s.CLASS_CATALOG_DATA_SOURCE), ("demo", "demo", "demo"))
        self.assertEqual(Path(s.DATABASES["default"]["NAME"]), Path(s.BASE_DIR) / "data" / "share" / "db.sqlite3")
        self.assertEqual(Path(s.MEDIA_ROOT), Path(s.BASE_DIR) / "data" / "share" / "media")
        demo = importlib.import_module("config.settings.demo")
        self.assertEqual(Path(demo.DATABASES["default"]["NAME"]), Path(demo.BASE_DIR) / "data" / "demo" / "db.sqlite3")

    def test_serves_static_and_uploaded_files_without_the_debug_server(self):
        s = share_settings()
        self.assertTrue(s.SERVE_MEDIA)
        security = s.MIDDLEWARE.index("django.middleware.security.SecurityMiddleware")
        self.assertEqual(s.MIDDLEWARE[security + 1], "whitenoise.middleware.WhiteNoiseMiddleware")
        self.assertNotIn("whitenoise.middleware.WhiteNoiseMiddleware", settings.MIDDLEWARE)  # 다른 모드는 그대로

    def test_errors_and_slow_pages_are_written_to_a_log_file(self):
        logging = share_settings().LOGGING
        handler = logging["handlers"]["server_file"]
        self.assertEqual(Path(handler["filename"]), Path(settings.BASE_DIR) / "data" / "share" / "server.log")
        self.assertIn("server_file", logging["loggers"]["django.request"]["handlers"])
        self.assertIn("server_file", logging["loggers"]["edutrack.performance"]["handlers"])


class MediaFileTests(TestCase):  # 11/24: 로그인 사용자를 만들므로 DB 사용
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        for folder in ("assignments/materials/2026/10", "lms_private"):
            (Path(self.root.name) / folder).mkdir(parents=True)
        (Path(self.root.name) / "assignments/materials/2026/10/note.txt").write_text("자료", encoding="utf-8")
        (Path(self.root.name) / "lms_private/secret.pdf").write_bytes(b"%PDF-1.4")

    def test_share_mode_serves_uploaded_material(self):
        # 11/24: 업로드 파일은 로그인한 사람만 받습니다(로그인 안 하면 로그인 화면으로, config/tests/test_stage1_1124.py).
        from django.contrib.auth import get_user_model
        self.client.force_login(get_user_model().objects.create_user("share_viewer", password="x-Share!2026", role="STUDENT"))
        with override_settings(SERVE_MEDIA=True, MEDIA_ROOT=self.root.name):
            response = self.client.get("/media/assignments/materials/2026/10/note.txt")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(b"".join(response.streaming_content).decode("utf-8"), "자료")

    def test_private_folders_stay_blocked_in_share_mode(self):
        with override_settings(SERVE_MEDIA=True, MEDIA_ROOT=self.root.name):
            self.assertEqual(self.client.get("/media/lms_private/secret.pdf").status_code, 404)

    def test_uploaded_files_are_not_served_without_debug_or_share_mode(self):
        with override_settings(SERVE_MEDIA=False, MEDIA_ROOT=self.root.name):
            self.assertEqual(self.client.get("/media/assignments/materials/2026/10/note.txt").status_code, 404)


class ShareCopyTests(SimpleTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        demo = self.root / "data" / "demo"
        (demo / "media" / "notes").mkdir(parents=True)
        (demo / "media" / "notes" / "a.txt").write_text("첨부", encoding="utf-8")
        self.source = demo / "db.sqlite3"
        run_sql(self.source, "create table t (x integer)", "insert into t values (1)")
        self.target = self.root / "data" / "share" / "db.sqlite3"

    def rows(self, path):
        db = sqlite3.connect(path)
        try:
            return [row[0] for row in db.execute("select x from t order by x")]
        finally:
            db.close()

    def test_first_run_copies_demo_db_and_uploads_without_touching_the_original(self):
        before = self.source.read_bytes()
        self.assertEqual(make_share_copy(self.root), "copied")
        self.assertEqual(self.rows(self.target), [1])
        self.assertEqual((self.root / "data" / "share" / "media" / "notes" / "a.txt").read_text(encoding="utf-8"), "첨부")
        self.assertEqual(self.source.read_bytes(), before)

    def test_existing_copy_is_kept_so_test_work_survives_a_restart(self):
        make_share_copy(self.root)
        run_sql(self.target, "insert into t values (2)")
        self.assertEqual(make_share_copy(self.root), "kept")
        self.assertEqual(self.rows(self.target), [1, 2])

    def test_reset_starts_over_from_the_demo_db(self):
        make_share_copy(self.root)
        run_sql(self.target, "insert into t values (2)")
        self.assertEqual(make_share_copy(self.root, reset=True), "copied")
        self.assertEqual(self.rows(self.target), [1])

    def test_missing_demo_db_is_reported(self):
        self.source.unlink()
        with self.assertRaises(ShareCopyError):
            make_share_copy(self.root)


class StaticCacheTests(SimpleTestCase):
    def test_served_modes_let_browsers_keep_versioned_assets(self):
        import importlib
        for name in ('config.settings.share',):
            with self.subTest(name=name):
                source = importlib.util.find_spec(name).origin
                text = open(source, encoding='utf-8').read()
                self.assertIn('WHITENOISE_MAX_AGE = 60 * 60 * 24 * 7', text)
