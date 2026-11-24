from unittest.mock import patch

from django.db.utils import DatabaseError
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.dashboard.class_catalog import (
    ClassCatalogFilters,
    ClassCatalogService,
    DemoClassCatalogRepository,
)


@override_settings(CLASS_CATALOG_DATA_SOURCE="demo")
class AdminClassCatalogTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="class_admin",
            password="1234",
            role=User.Role.ADMIN,
        )
        self.teacher = User.objects.create_user(
            username="class_teacher",
            password="1234",
            role=User.Role.TEACHER,
        )
        self.student = User.objects.create_user(
            username="class_student",
            password="1234",
            role=User.Role.STUDENT,
        )
        self.demo_service = ClassCatalogService(
            repository=DemoClassCatalogRepository()
        )
        self.service_patcher = patch(
            "apps.dashboard.views.get_class_catalog_service",
            return_value=self.demo_service,
        )
        self.service_patcher.start()
        self.addCleanup(self.service_patcher.stop)

    def test_admin_can_search_and_view_class_catalog(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("admin_classes"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response,
            "dashboard/admin_class_catalog.html",
        )
        self.assertContains(response, "Class 리스트")
        self.assertContains(response, "AP Human Geography")
        self.assertContains(response, "미주 Journal Reading")

    def test_filters_are_applied_to_catalog(self):
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("admin_classes"),
            {
                "q": "Human",
                "status": "W",
                "learning_method": "ONLINE",
                "start_date": "2026-08-01",
                "end_date": "2026-12-31",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "AP Human Geography")
        self.assertNotContains(response, "미주 Journal Reading")
        self.assertEqual(response.context["result_count"], 1)

    def test_non_admin_roles_cannot_open_class_catalog(self):
        for user in (self.teacher, self.student):
            with self.subTest(role=user.role):
                self.client.force_login(user)
                response = self.client.get(reverse("admin_classes"))
                self.assertEqual(response.status_code, 403)
                self.client.logout()

    @patch("apps.dashboard.views.logger.exception", new=lambda *args, **kwargs: None)
    def test_database_error_is_shown_without_breaking_dashboard(self):
        self.client.force_login(self.admin)
        with patch(
            "apps.dashboard.views.get_class_catalog_service"
        ) as service_factory:
            service_factory.return_value.search.side_effect = DatabaseError(
                "connection failed"
            )
            response = self.client.get(reverse("admin_classes"))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["database_error"])
        self.assertContains(response, "수업 정보를 불러오지 못했습니다.")
