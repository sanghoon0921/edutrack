from __future__ import annotations

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import StudentAccountLink, User


@override_settings(
    STUDENT_DATA_SOURCE="demo",
    ASSESSMENT_DATA_SOURCE="demo",
    CLASS_CATALOG_DATA_SOURCE="demo",
    SERVER_TIMING_ENABLED=True,
)
class Stage13PerformanceAndAssetTests(TestCase):
    def setUp(self) -> None:
        self.admin = User.objects.create_user(
            username="stage13_admin",
            password="1234",
            role=User.Role.ADMIN,
        )
        self.student = User.objects.create_user(
            username="stage13_student",
            password="1234",
            role=User.Role.STUDENT,
        )
        StudentAccountLink.objects.create(
            user=self.student,
            student_no="6333",
            relationship=StudentAccountLink.Relationship.SELF,
            is_primary=True,
            is_active=True,
        )

    def test_liveness_and_readiness_endpoints(self):
        live = self.client.get(reverse("health-live"))
        ready = self.client.get(reverse("health-ready"))

        self.assertEqual(live.status_code, 200)
        self.assertEqual(live.json()["status"], "ok")
        self.assertEqual(ready.status_code, 200)
        self.assertEqual(ready.json()["components"]["default_database"], "ok")

    def test_request_timing_headers_are_added(self):
        response = self.client.get(reverse("health-live"))

        self.assertTrue(response.headers.get("X-Request-ID"))
        self.assertIn("app;dur=", response.headers.get("Server-Timing", ""))

    def test_common_pages_do_not_load_page_specific_heavy_assets(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("dashboard"))

        self.assertContains(response, "css/layers/30-stability.css")
        self.assertNotContains(response, "dashboard/css/class-catalog.css")
        self.assertNotContains(response, "css/components/student-transfer-selector.css")
        self.assertNotContains(response, "js/components/student-transfer-selector.js")
        self.assertNotContains(response, "css/components/learning-overview.css")

    def test_assignment_editor_loads_student_selector_assets_only_when_needed(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("assignments:create"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "css/components/student-transfer-selector.css")
        self.assertContains(response, "js/components/student-transfer-selector.js")
        self.assertNotContains(response, "dashboard/css/class-catalog.css")

    def test_class_catalog_loads_only_class_catalog_asset(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("admin_classes"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "dashboard/css/class-catalog.css")
        self.assertNotContains(response, "css/components/student-transfer-selector.css")
        self.assertNotContains(response, "css/components/learning-overview.css")

    def test_student_learning_page_loads_only_learning_asset(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("student_classes"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "css/components/learning-overview.css")
        self.assertNotContains(response, "dashboard/css/class-catalog.css")
        self.assertNotContains(response, "css/components/student-transfer-selector.css")
