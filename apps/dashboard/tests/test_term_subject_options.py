"""Term·Subject 드롭다운 값: 데모 값, 인트라넷 조회와 10분 캐시, 실패 시 ok=False."""

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from apps.dashboard.class_catalog import term_subject_cache_key, term_subject_options


class TermSubjectOptionTests(SimpleTestCase):
    def setUp(self):
        cache.delete(term_subject_cache_key("intranet"))
        self.addCleanup(cache.delete, term_subject_cache_key("intranet"))

    @override_settings(CLASS_CATALOG_DATA_SOURCE="demo")
    def test_demo_values(self):
        options = term_subject_options()
        self.assertTrue(options.ok)
        self.assertIn("2026 여름특강", options.terms)
        self.assertIn("SAT", options.subjects)
        self.assertIn("AP", options.subjects)
        self.assertEqual(list(options.subjects), sorted(options.subjects))
        self.assertEqual(list(options.terms), sorted(options.terms, reverse=True))



