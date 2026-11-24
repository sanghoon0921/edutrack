from django.apps import apps
from django.test import SimpleTestCase


class AssessmentsConfigurationTests(SimpleTestCase):
    def test_assessments_app_is_registered(self):
        # 파이썬 경로는 apps.assessments, DB와 연결되는 label은 예전 이름 그대로입니다.
        config = apps.get_app_config("assessments")
        self.assertEqual(config.name, "apps.assessments")
        self.assertEqual(config.label, "assessments")
